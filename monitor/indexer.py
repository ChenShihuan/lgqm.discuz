"""
Wiki 文章索引器 - 解析 Huijiwiki .mw 文件，建立论坛帖→Wiki文章映射
"""
import os
import re
import json
from typing import List, Optional, Dict
from datetime import datetime

from .config import get
from .models import WikiArticle
from .utils import log, extract_tid, set_verbose


# Infobox 模板提取：从 {{Infobox TongRen 到 \n}}（模板闭合）
# 注意：部分文件有 {{Infobox TongRen <!-- comment --> 格式
INFOBOX_PATTERN = re.compile(
    r'\{\{Infobox TongRen([\s\S]*?)\n\}\}',
    re.DOTALL
)

# 单字段提取：| 字段名 = 值（跨行兼容：值可能为空或在后续行）
FIELD_PATTERN = re.compile(r'\|\s*(.+?)\s*=\s*(.*)')

# 论坛链接提取
# 格式1: [https://url 名称] → 取 url
# 格式2: 直接 https://url
LINK_URL_PATTERN = re.compile(r'\[(https?://[^\]\s]+)(?:\s+[^\]]*)?\]')
RAW_URL_PATTERN = re.compile(r'(https?://[^\s|}\]<>]+)')

# 论坛域名关键字（用于判断是否是论坛链接）
FORUM_URL_KEYWORDS = ['lgqm', 'thread-', 'article-', 'forum.php', 'tid=']


def parse_infobox_fields(text: str) -> Dict[str, str]:
    """
    解析 Infobox 模板中的字段
    支持跨行值：当一行以 '| 字段名 = ' 结尾且值为空时，
    下一行作为该字段的值（仅当下一行不以 '|' 开头）
    """
    fields = {}
    lines = text.split('\n')
    pending_key = None
    pending_value = ""

    for line in lines:
        stripped = line.strip()
        # 跳过纯注释行
        if not stripped or stripped.startswith('<!--'):
            continue

        # 检查是否是新的字段行
        field_match = FIELD_PATTERN.match(stripped)
        if field_match:
            # 保存上一个 pending 字段
            if pending_key:
                fields[pending_key] = pending_value.strip()

            pending_key = field_match.group(1).strip()
            pending_value = field_match.group(2).strip()
            # 去掉行内注释
            pending_value = re.sub(r'<!--.*?-->', '', pending_value).strip()
        elif pending_key and not stripped.startswith('|'):
            # 当前行不是字段行，追加到 pending 值
            if pending_value:
                pending_value += ' ' + stripped
            else:
                pending_value = stripped

    # 保存最后一个字段
    if pending_key:
        fields[pending_key] = pending_value.strip()

    return fields


def extract_forum_url(field_value: str) -> Optional[str]:
    """从字段值中提取第一个论坛 URL"""
    urls = extract_all_forum_urls(field_value)
    return urls[0] if urls else None


def extract_all_forum_urls(field_value: str) -> list:
    """从字段值中提取所有论坛 URL（支持跨行多链接）"""
    if not field_value:
        return []

    clean = re.sub(r'<!--.*?-->', '', field_value).strip()
    if not clean:
        return []

    urls = []
    # 提取所有 [url name] 格式的链接
    for m in LINK_URL_PATTERN.finditer(clean):
        url = m.group(1)
        if any(kw in url for kw in FORUM_URL_KEYWORDS):
            urls.append(url)

    # 也提取裸 URL
    for m in RAW_URL_PATTERN.finditer(clean):
        url = m.group(1)
        if any(kw in url for kw in FORUM_URL_KEYWORDS) and url not in urls:
            urls.append(url)

    return urls


def extract_all_tids(field_value: str) -> list:
    """从字段值中提取所有 TID"""
    from .utils import extract_tid
    tids = []
    for url in extract_all_forum_urls(field_value):
        tid = extract_tid(url)
        if tid is not None and tid not in tids:
            tids.append(tid)
    return tids


def scan_wiki_articles(repo_path: str = None, verbose: bool = False) -> List[WikiArticle]:
    """
    扫描 Wiki 仓库所有 .mw 文件，建立文章索引

    Args:
        repo_path: Wiki 仓库路径
        verbose: 详细日志

    Returns:
        WikiArticle 列表
    """
    set_verbose(verbose)
    if repo_path is None:
        repo_path = get("wiki.repo_path", os.path.join(os.path.dirname(os.path.dirname(__file__)), "lgqm.huijiwiki.com"))

    articles: List[WikiArticle] = []
    mw_dir = repo_path

    if not os.path.isdir(mw_dir):
        log(f"Wiki 目录不存在: {mw_dir}", "ERROR")
        return articles

    mw_files = [f for f in os.listdir(mw_dir) if f.endswith('.mw')]
    log(f"发现 {len(mw_files)} 个 .mw 文件", "INFO")

    forum_link_field = get("wiki.forum_link_field", "官坛原帖")
    last_update_field = get("wiki.last_update_field", "最近更新")
    first_publish_field = get("wiki.first_publish_field", "首次发布")
    author_field = get("wiki.author_field", "官方论坛")

    for filename in mw_files:
        filepath = os.path.join(mw_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            log(f"读取失败 {filename}: {e}", "WARN")
            continue

        # 提取 Infobox
        infobox_match = INFOBOX_PATTERN.search(content)
        if not infobox_match:
            # 没有 Infobox 的文章（如年表等）
            continue

        fields = parse_infobox_fields(infobox_match.group(1))

        # 提取论坛链接
        forum_url = ""
        forum_tid = None
        forum_tids = []
        raw_url = fields.get(forum_link_field, "")
        all_urls = extract_all_forum_urls(raw_url)
        if all_urls:
            forum_url = all_urls[0]
            forum_tid = extract_tid(forum_url)
            forum_tids = extract_all_tids(raw_url)

        # 提取标题（去掉 .mw 后缀）
        title = filename[:-3]

        article = WikiArticle(
            filename=filename,
            title=title,
            forum_url=forum_url,
            forum_tid=forum_tid,
            forum_tids=forum_tids,
            first_publish=fields.get(first_publish_field, ""),
            last_update=fields.get(last_update_field, ""),
            is_completed=fields.get("完结情况", ""),
            author=fields.get(author_field, ""),
        )
        articles.append(article)

    # 统计
    with_tid = sum(1 for a in articles if a.forum_tid is not None)
    log(f"索引完成：{len(articles)} 篇同人文章，{with_tid} 篇有论坛链接", "SUCCESS")
    return articles


def save_wiki_index(articles: List[WikiArticle], filepath: str = None):
    """保存 Wiki 索引到 JSON 文件"""
    if filepath is None:
        filepath = f"{get('output.data_dir')}/wiki_index.json"

    data = {
        "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(articles),
        "articles": [
            {
                "filename": a.filename,
                "title": a.title,
                "forum_url": a.forum_url,
                "forum_tid": a.forum_tid,
                "forum_tids": a.forum_tids if a.forum_tids else [],
                "first_publish": a.first_publish,
                "last_update": a.last_update,
                "is_completed": a.is_completed,
                "author": a.author,
            }
            for a in articles
        ]
    }
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log(f"Wiki 索引已保存至 {filepath}", "SUCCESS")


def load_wiki_index(filepath: str = None) -> List[WikiArticle]:
    """从 JSON 文件加载 Wiki 索引"""
    if filepath is None:
        filepath = f"{get('output.data_dir')}/wiki_index.json"

    if not os.path.exists(filepath):
        return []

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    articles = []
    for item in data.get("articles", []):
        articles.append(WikiArticle(
            filename=item["filename"],
            title=item["title"],
            forum_url=item.get("forum_url", ""),
            forum_tid=item.get("forum_tid"),
            forum_tids=item.get("forum_tids", []),
            first_publish=item.get("first_publish", ""),
            last_update=item.get("last_update", ""),
            is_completed=item.get("is_completed", ""),
            author=item.get("author", ""),
        ))
    return articles


def build_tid_index(articles: List[WikiArticle]) -> Dict[int, WikiArticle]:
    """构建 TID → WikiArticle 的快速查找字典（含跨行多 TID）"""
    index = {}
    for article in articles:
        tids = article.forum_tids if article.forum_tids else []
        if article.forum_tid is not None and article.forum_tid not in tids:
            tids.append(article.forum_tid)
        for tid in tids:
            if tid not in index:
                index[tid] = article
    return index
