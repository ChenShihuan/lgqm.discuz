"""
内容拉取器 - 基于 Discuz Archiver 模式拉取帖子内容
Archiver 模式优势：极简 HTML、无需 cookie、函数式接口
"""
import re
import os
import time
from typing import List, Optional

from .config import get, tid_img_dir
from .models import Post, ForumThread
from .utils import log, rate_limit, set_verbose, clean_html
from .session import get_forum_session, BASE_URL
from .pw_fetcher import pw_get_html


# Archiver URL 模板
ARCHIVER_URL = "https://lgqmonline.top/archiver/?tid-{tid}.html"
ARCHIVER_PAGE_URL = "https://lgqmonline.top/archiver/?tid-{tid}.html&page={page}"

# 帖子分割正则：<p class="author"> 标记每一楼的开始
AUTHOR_PATTERN = re.compile(
    r'<p class="author">\s*<strong>([^<]+)</strong>\s*发表于\s*'
    r'<span title="([^"]+)">[^<]*</span>\s*</p>',
    re.DOTALL
)

# 分页链接正则
PAGE_LINK_PATTERN = re.compile(r'<a href="\?tid-\d+\.html&page=(\d+)">(\d+)</a>')



def fetch_archiver_page(tid: int, page: int = 1, retries: int = 3) -> Optional[str]:
    """
    获取单个 Archiver 页面的 HTML

    Args:
        tid: 帖子ID
        page: 页码
        retries: 重试次数

    Returns:
        HTML 文本，失败返回 None
    """
    if page == 1:
        url = ARCHIVER_URL.format(tid=tid)
    else:
        url = ARCHIVER_PAGE_URL.format(tid=tid, page=page)

    fs = get_forum_session()
    fs.ensure_logged_in()
    referer = f"{BASE_URL}/forum-39-1.html"  # Archiver 访问也伪装从板块列表进入

    for attempt in range(retries):
        try:
            resp = fs.get(url, referer=referer)
            resp.encoding = 'utf-8'
            if resp.status_code == 200:
                if fs.is_js_challenge(resp.text):
                    log(f"Archiver tid={tid} 遇到 JS 验证", "WARN")
                    return None
                return resp.text
            log(f"HTTP {resp.status_code} for archiver tid={tid} page={page}", "WARN")
        except Exception as e:
            log(f"Archiver request failed (attempt {attempt+1}/{retries}): {e}", "WARN")
        if attempt < retries - 1:
            time.sleep(2)
    return None


def get_archiver_pages(tid: int) -> int:
    """
    获取帖子的 Archiver 总页数

    先请求第一页，从分页栏中解析页数
    """
    html = fetch_archiver_page(tid, 1)
    if not html:
        return 1

    # 查找分页链接中的最大页码
    pages = PAGE_LINK_PATTERN.findall(html)
    if pages:
        return max(int(p[0]) for p in pages)
    return 1


def parse_archiver_posts(html: str) -> List[dict]:
    """
    从 Archiver HTML 中提取所有楼层

    Args:
        html: Archiver 页面 HTML

    Returns:
        楼层数据列表 [{author, date, content, is_first_post}]
    """
    posts = []

    # 提取 content div 内的内容
    content_match = re.search(r'<div id="content">(.*?)(?:<div class="page">|</div>\s*</div>\s*<div id="end">)', html, re.DOTALL)
    if not content_match:
        return posts

    content = content_match.group(1)

    # 按 <p class="author"> 分割
    parts = re.split(r'(<p class="author">.*?</p>)', content, flags=re.DOTALL)

    current_author = ""
    current_date = ""
    floor_count = 0

    for i, part in enumerate(parts):
        # 检查是否是作者块
        author_match = re.search(
            r'<p class="author">\s*<strong>([^<]+)</strong>\s*发表于\s*<span title="([^"]+)">',
            part, re.DOTALL
        )
        if author_match:
            current_author = author_match.group(1).strip()
            current_date = author_match.group(2).strip()
            floor_count += 1
        elif current_author and part.strip():
            # 内容块
            content_text = part.strip()
            # 提取 <h3> 标题（首楼）
            title_match = re.search(r'<h3>(.*?)</h3>', content_text, re.DOTALL)
            is_first = bool(title_match and title_match.group(1).strip())
            if title_match:
                # 从内容中移除 h3 标签
                content_text = re.sub(r'<h3>.*?</h3>', '', content_text, flags=re.DOTALL).strip()

            posts.append({
                "author": current_author,
                "date": current_date,
                "content_html": content_text,
                "floor": floor_count,
                "is_first_post": is_first,
            })
            current_author = ""  # 重置，避免重复匹配

    return posts


def fetch_thread(tid: int, verbose: bool = False) -> List[Post]:
    """
    拉取指定帖子的全部内容。
    优先使用常规页面（cookie 登录），失败时回退到 Archiver 模式。

    Args:
        tid: 帖子ID
        verbose: 详细日志

    Returns:
        Post 列表，按楼层顺序排列
    """
    set_verbose(verbose)
    log(f"开始拉取帖子 TID={tid} (常规页面模式)...", "INFO")

    posts = _fetch_thread_regular(tid, verbose=verbose)

    if len(posts) == 0:
        log("常规页面模式返回 0 楼（Archiver 回退已禁用——Archiver 不含图片，不适用于文章拉取）", "ERROR")

    log(f"拉取完成：共 {len(posts)} 楼", "SUCCESS" if posts else "WARN")
    return posts


def get_thread_title(tid: int) -> str:
    """
    从常规页面提取帖子标题

    Args:
        tid: 帖子ID

    Returns:
        帖子标题，失败返回空字符串
    """
    try:
        from lxml import etree
    except ImportError:
        return ""

    fs = get_forum_session()
    fs.ensure_logged_in()

    try:
        url = f"https://lgqmonline.top/thread-{tid}-1-1.html"
        html = pw_get_html(url, timeout=15000)
        tree = etree.HTML(html)

        # 标题：<span id="thread_subject"> 或 <h1> 或 <title>
        for xpath in [
            '//span[@id="thread_subject"]/text()',
            '//h1//text()',
            '//title/text()',
        ]:
            results = tree.xpath(xpath)
            for text in results:
                text = text.strip()
                # 清理 title 标签的后缀
                if " - " in text and "Powered by" in text:
                    text = text.split(" - ")[0].strip()
                if text and len(text) > 1:
                    return text
    except Exception:
        pass
    return ""


def _fetch_thread_archiver(tid: int, verbose: bool = False) -> List[Post]:
    """通过 Archiver 模式拉取（旧版回退方案）"""
    # 获取总页数
    total_pages = get_archiver_pages(tid)
    if verbose:
        log(f"Archiver: 帖子共 {total_pages} 页", "INFO")

    all_posts_data = []
    interval = get("forum.request_interval", 2.0)
    last_req = 0.0

    for page in range(1, total_pages + 1):
        if page > 1:
            rate_limit(last_req, interval)

        html = fetch_archiver_page(tid, page)
        last_req = time.time()

        if html is None:
            log(f"Archiver 第 {page} 页获取失败", "WARN")
            continue

        posts_data = parse_archiver_posts(html)
        all_posts_data.extend(posts_data)
        if verbose:
            log(f"Archiver 第 {page}/{total_pages} 页: {len(posts_data)} 楼", "INFO")

    posts = []
    for data in all_posts_data:
        posts.append(Post(
            author=data["author"],
            date=data["date"],
            content_html=data["content_html"],
            floor=data["floor"],
            is_first_post=data["is_first_post"],
        ))
    return posts


def _fetch_thread_regular(tid: int, verbose: bool = False) -> List[Post]:
    """通过常规页面拉取帖子（使用 ForumSession，含完整浏览器指纹 + Referer 链）"""
    try:
        from lxml import etree
    except ImportError:
        log("常规页面模式需要 lxml: pip install lxml", "ERROR")
        return []

    # 确保已登录（cookie 会注入 Playwright）
    fs = get_forum_session()
    fs.ensure_logged_in()

    all_posts_data = []
    page = 1
    interval = get("forum.request_interval", 2.0)
    jitter = get("forum.request_jitter", 0.3)
    last_req = 0.0

    while True:
        url = f"https://lgqmonline.top/thread-{tid}-{page}-1.html"

        if page > 1:
            rate_limit(last_req, interval, jitter)

        try:
            html = pw_get_html(url)
            last_req = time.time()
        except Exception as e:
            log(f"第 {page} 页 Playwright 请求失败: {e}", "WARN")
            break

        tree = etree.HTML(html)
        post_tables = tree.xpath('//table[contains(@id, "pid")]')
        if not post_tables:
            break

        for i, table in enumerate(post_tables):
            # 作者
            auth_elem = table.xpath('.//*[contains(@class,"authi")]')
            author = ""
            auth_text = ""
            if auth_elem:
                auth_text = auth_elem[0].xpath("string()").strip()
                a_tag = auth_elem[0].find(".//a")
                author = a_tag.text.strip() if a_tag is not None and a_tag.text else ""

            # 日期：authi 里的 <em> 或 <span>；或 <em id="authorposton...">
            date = ""
            if auth_elem:
                em_tag = auth_elem[0].find(".//em")
                if em_tag is not None and em_tag.text:
                    date = em_tag.text.strip()
                else:
                    span_tag = auth_elem[0].find(".//span")
                    if span_tag is not None:
                        date = (span_tag.text or "").strip() or (span_tag.get("title") or "")
            # Playwright 渲染下日期在 <em id="authorposton...">
            if not date:
                poston = table.xpath('.//em[contains(@id, "authorposton")]')
                if poston and poston[0].text:
                    date = poston[0].text.strip().lstrip("发表于 ")

            # 内容（含附件图片）
            t_fsz = table.xpath('.//div[contains(@class,"t_fsz")]')
            content_html = ""
            if t_fsz:
                content_html = etree.tostring(t_fsz[0], encoding="unicode")
            else:
                content_elem = table.xpath('.//td[contains(@class,"t_f")]')
                if content_elem:
                    content_html = etree.tostring(content_elem[0], encoding="unicode")

            if author or content_html:
                all_posts_data.append({
                    "author": author,
                    "date": date,
                    "content_html": content_html,
                    "floor": len(all_posts_data) + 1,
                    "is_first_post": len(all_posts_data) == 0,
                })

        if verbose:
            log(f"第 {page} 页: {len(post_tables)} 楼", "INFO")

        # 检查是否有下一页
        next_page = tree.xpath('//a[contains(@class,"nxt")]')
        if not next_page:
            break
        prev_url = url  # 下一页的 Referer
        page += 1

    posts = []
    for data in all_posts_data:
        posts.append(Post(
            author=data["author"],
            date=data["date"],
            content_html=data["content_html"],
            floor=data["floor"],
            is_first_post=data["is_first_post"],
        ))
    return posts


def fetch_images(tid: int, output_dir: str = None, verbose: bool = False) -> List[dict]:
    """
    从普通帖子页面拉取图片。
    页面请求使用 ForumSession（含完整浏览器指纹），
    图片下载使用 get_image()（正确的图片请求头）。

    Args:
        tid: 帖子ID
        output_dir: 图片保存目录
        verbose: 详细日志

    Returns:
        图片信息列表 [{url, filename, local_path}]
    """
    set_verbose(verbose)

    if output_dir is None:
        output_dir = tid_img_dir(tid)

    os.makedirs(output_dir, exist_ok=True)

    images = []
    url = f"https://lgqmonline.top/thread-{tid}-1-1.html"

    log(f"获取帖子图片 (常规模式): {url}", "INFO")

    try:
        from lxml import etree
    except ImportError:
        log("图片下载需要 lxml 库: pip install lxml", "WARN")
        return images

    fs = get_forum_session()
    fs.ensure_logged_in()

    try:
        # 使用 Playwright 获取帖子页面 HTML（绕过 JS 挑战）
        html = pw_get_html(url, timeout=30000)

        tree = etree.HTML(html)

        # 查找 <img file="..."> 标签（Discuz 附件图片）
        img_elems = tree.findall('.//img[@file]')
        for img in img_elems:
            file_attr = img.get('file', '')
            if not file_attr:
                continue

            # 构建完整图片 URL
            if file_attr.startswith('http'):
                img_url = file_attr
            elif file_attr.startswith('//'):
                img_url = f"https:{file_attr}"
            elif file_attr.startswith('/'):
                img_url = f"https://lgqmonline.top{file_attr}"
            else:
                img_url = f"https://lgqmonline.top/{file_attr}"

            # 提取文件名
            filename_match = re.search(r'([^/]+\.(?:gif|jpg|jpeg|png|svg))', file_attr, re.IGNORECASE)
            filename = filename_match.group(1) if filename_match else f"img_{hash(file_attr)}"

            local_path = os.path.join(output_dir, filename)

            # 下载图片（使用图片专用请求头）
            try:
                rate_limit(time.time(), 1.0)
                img_resp = fs.get_image(img_url, referer=url)
                if img_resp.status_code == 200:
                    with open(local_path, 'wb') as f:
                        f.write(img_resp.content)
                    images.append({
                        "url": img_url,
                        "filename": filename,
                        "local_path": local_path,
                    })
                    if verbose:
                        log(f"  图片: {filename}", "INFO")
            except Exception as e:
                log(f"图片下载失败 {filename}: {e}", "WARN")

        # 也查找常规 <img> 标签（非附件图片）
        normal_imgs = tree.findall('.//img[@src]')
        for img in normal_imgs:
            src = img.get('src', '')
            if not src or 'attachment' not in src or 'image' not in src:
                continue
            # 处理附件图片的另一种格式
            if 'forum.php?mod=attachment' in src or 'data/attachment' in src:
                if src.startswith('//'):
                    img_url = f"https:{src}"
                elif src.startswith('/'):
                    img_url = f"https://lgqmonline.top{src}"
                else:
                    img_url = src

                filename_match = re.search(r'([^/&?]+\.(?:gif|jpg|jpeg|png|svg))', src, re.IGNORECASE)
                if not filename_match:
                    continue
                filename = filename_match.group(1)
                local_path = os.path.join(output_dir, filename)

                try:
                    rate_limit(time.time(), 1.0)
                    img_resp = fs.get_image(img_url, referer=url)
                    if img_resp.status_code == 200:
                        with open(local_path, 'wb') as f:
                            f.write(img_resp.content)
                        images.append({
                            "url": img_url,
                            "filename": filename,
                            "local_path": local_path,
                        })
                except Exception:
                    pass

    except Exception as e:
        log(f"图片拉取异常: {e}", "ERROR")

    log(f"图片拉取完成：共 {len(images)} 张", "SUCCESS" if images else "INFO")
    return images


def fetch_thread_with_images(tid: int, download_images: bool = True,
                              verbose: bool = False) -> tuple:
    """
    一次性拉取帖子内容和图片

    Returns:
        (posts: List[Post], images: List[dict])
    """
    posts = fetch_thread(tid, verbose=verbose)
    images = []
    if download_images:
        images = fetch_images(tid, verbose=verbose)
    return posts, images
