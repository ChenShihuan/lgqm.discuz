"""
论坛板块监控器 - 扫描 forum-39 板块，提取所有帖子元数据
"""
import re
import json
import time
from datetime import datetime
from typing import List, Optional
try:
    from lxml import etree
except ImportError:
    etree = None

from .config import get
from .models import ForumThread
from .utils import log, set_verbose, rate_limit
from .session import get_forum_session, BASE_URL


def fetch_page(url: str, referer: str = None, retries: int = 3) -> Optional[etree.HTML]:
    """获取页面并解析为 HTML 树（通过 ForumSession，带完整浏览器指纹）"""
    if etree is None:
        log("lxml 未安装，无法解析 HTML。请 pip install lxml", "ERROR")
        return None

    fs = get_forum_session()
    fs.ensure_logged_in()

    for attempt in range(retries):
        try:
            resp = fs.get(url, referer=referer)
            resp.encoding = 'utf-8'
            if resp.status_code == 200:
                # JS 挑战检测
                if fs.is_js_challenge(resp.text):
                    log(f"遇到反爬 JS 验证: {url}", "ERROR")
                    return None
                return etree.HTML(resp.text)
            log(f"HTTP {resp.status_code} for {url}", "WARN")
        except Exception as e:
            log(f"Request failed (attempt {attempt+1}/{retries}): {e}", "WARN")
        if attempt < retries - 1:
            time.sleep(2)
    return None


def parse_thread_row(tbody) -> Optional[ForumThread]:
    """解析单个帖子行（tbody 元素）"""
    try:
        tbody_id = tbody.get('id', '')

        # 提取 TID
        tid_match = re.search(r'(\d+)', tbody_id)
        if not tid_match:
            return None
        tid = int(tid_match.group(1))

        # 判断是否置顶
        is_sticky = tbody_id.startswith('stickthread_')

        # 链接和标题
        link_elem = tbody.find('.//a[@class="s xst"]')
        if link_elem is None:
            return None
        title = link_elem.text or ""
        title = title.strip()
        href = link_elem.get('href', '')

        # 作者 (td.by cite a)
        author_cell = tbody.find('.//td[@class="by"]')
        author = ""
        author_uid = 0
        if author_cell is not None:
            cite = author_cell.find('.//cite/a')
            if cite is not None:
                author = (cite.text or "").strip()
                uid_match = re.search(r'uid-(\d+)', cite.get('href', ''))
                if uid_match:
                    author_uid = int(uid_match.group(1))

        # 发帖时间
        post_date_str = ""
        if author_cell is not None:
            time_span = author_cell.find('.//em/span')
            if time_span is not None:
                post_date_str = time_span.get('title', '')

        # 回复数和查看数 (td.num)
        num_cell = tbody.find('.//td[@class="num"]')
        reply_count = 0
        view_count = 0
        if num_cell is not None:
            reply_link = num_cell.find('.//a')
            if reply_link is not None:
                try:
                    reply_count = int((reply_link.text or "0").strip())
                except ValueError:
                    reply_count = 0
            view_em = num_cell.find('.//em')
            if view_em is not None:
                try:
                    view_count = int((view_em.text or "0").strip())
                except ValueError:
                    view_count = 0

        # 最后回复时间 (td.by 第二个)
        last_reply_date = ""
        by_cells = tbody.findall('.//td[@class="by"]')
        if len(by_cells) >= 2:
            last_em = by_cells[1].find('.//em/a/span')
            if last_em is None:
                last_em = by_cells[1].find('.//em/span')
            if last_em is not None:
                last_reply_date = last_em.get('title', '')

        # 新人帖标记
        is_newcomer = tbody.find('.//img[@alt="新人帖"]') is not None

        return ForumThread(
            tid=tid,
            title=title,
            author=author,
            author_uid=author_uid,
            post_date=post_date_str,
            last_reply_date=last_reply_date,
            reply_count=reply_count,
            view_count=view_count,
            url=f"https://lgqmonline.top/{href}" if href else "",
            is_sticky=is_sticky,
            is_newcomer=is_newcomer,
        )
    except Exception as e:
        log(f"Parse error in thread row: {e}", "ERROR")
        return None


def get_total_pages(tree: etree.HTML) -> int:
    """从页面分页栏提取总页数"""
    # 查找 <span title="共 N 页">
    page_span = tree.find('.//div[@class="pg"]//label/span')
    if page_span is not None:
        title = page_span.get('title', '')
        match = re.search(r'(\d+)', title)
        if match:
            return int(match.group(1))
    # 备选：找最后一个页码链接
    last_link = tree.find('.//div[@class="pg"]//a[@class="last"]')
    if last_link is not None:
        try:
            return int((last_link.text or "1").strip())
        except ValueError:
            pass
    return 1


def scan_board(mode: str = "quick", verbose: bool = False) -> List[ForumThread]:
    """
    扫描 forum-39 板块，获取帖子列表

    Args:
        mode: "full" 全量扫描（所有页）| "quick" 快速扫描（前 5 页）
        verbose: 详细日志

    Returns:
        帖子列表
    """
    set_verbose(verbose)
    threads: List[ForumThread] = []
    seen_tids = set()

    # 先获取第一页，确认总页数
    first_url = get("forum.board_url_template").format(page=1)
    tree = fetch_page(first_url)
    if tree is None:
        log("无法获取论坛首页，请检查网络或 cookie", "ERROR")
        return threads

    actual_total = get_total_pages(tree)

    # 确定扫描范围
    if mode == "quick":
        scan_pages = min(actual_total, 5)
        log(f"⚡ 快速模式：扫描前 {scan_pages} 页 (共 {actual_total} 页)", "INFO")
    else:
        scan_pages = actual_total
        log(f"📚 全量模式：扫描全部 {scan_pages} 页", "INFO")

    # 逐页扫描（带 Referer 链 + 翻页延迟 + 抖动）
    last_req = 0.0
    board_interval = get("forum.board_page_interval", 1.5)
    board_jitter = get("forum.board_page_jitter", 0.2)
    prev_url = f"{BASE_URL}/"  # 首页作为第一页的 Referer

    for page_num in range(1, scan_pages + 1):
        if page_num > 1:
            rate_limit(last_req, board_interval, board_jitter)

        url = get("forum.board_url_template").format(page=page_num)
        tree = fetch_page(url, referer=prev_url)
        last_req = time.time()
        prev_url = url  # 下一页的 Referer

        if tree is None:
            log(f"跳过第 {page_num} 页（获取失败）", "WARN")
            continue

        # 解析帖子行
        tbodies = tree.xpath('.//tbody[starts-with(@id, "normalthread_") or starts-with(@id, "stickthread_")]')
        page_count = 0
        for tbody in tbodies:
            thread = parse_thread_row(tbody)
            if thread and thread.tid not in seen_tids:
                threads.append(thread)
                seen_tids.add(thread.tid)
                page_count += 1

        if verbose:
            log(f"第 {page_num:>3}/{scan_pages} 页: {page_count} 条", "INFO")
        elif page_num % 10 == 0 or page_num == scan_pages:
            log(f"已扫描 {page_num}/{scan_pages} 页, 累计 {len(threads)} 条", "INFO")

    sticky_count = sum(1 for t in threads if t.is_sticky)
    normal_count = len(threads) - sticky_count
    log(f"扫描完成：共 {len(threads)} 条帖子（{sticky_count} 置顶 + {normal_count} 普通）", "SUCCESS")
    return threads


def save_threads_index(threads: List[ForumThread], filepath: str = None):
    """保存帖子索引到 JSON 文件"""
    if filepath is None:
        from .config import get as cfg
        filepath = f"{cfg('output.data_dir')}/threads_index.json"

    data = {
        "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(threads),
        "threads": [
            {
                "tid": t.tid,
                "title": t.title,
                "author": t.author,
                "author_uid": t.author_uid,
                "post_date": t.post_date,
                "last_reply_date": t.last_reply_date,
                "reply_count": t.reply_count,
                "view_count": t.view_count,
                "url": t.url,
                "is_sticky": t.is_sticky,
                "is_newcomer": t.is_newcomer,
            }
            for t in threads
        ]
    }
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log(f"帖子索引已保存至 {filepath}", "SUCCESS")


def load_threads_index(filepath: str = None) -> List[ForumThread]:
    """从 JSON 文件加载帖子索引"""
    if filepath is None:
        from .config import get as cfg
        filepath = f"{cfg('output.data_dir')}/threads_index.json"

    if not __import__('os').path.exists(filepath):
        return []

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    threads = []
    for item in data.get("threads", []):
        threads.append(ForumThread(
            tid=item["tid"],
            title=item["title"],
            author=item.get("author", ""),
            author_uid=item.get("author_uid", 0),
            post_date=item.get("post_date", ""),
            last_reply_date=item.get("last_reply_date", ""),
            reply_count=item.get("reply_count", 0),
            view_count=item.get("view_count", 0),
            url=item.get("url", ""),
            is_sticky=item.get("is_sticky", False),
            is_newcomer=item.get("is_newcomer", False),
        ))
    return threads
