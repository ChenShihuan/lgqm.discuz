"""
工具函数：URL解析、TID提取、日期处理、日志
"""
import re
import sys
import time
from datetime import datetime
from typing import Optional, List
from urllib.parse import urlparse, parse_qs


# ============ URL 解析 ============

# 多种 Discuz 线程 URL 模式
THREAD_URL_PATTERNS = [
    re.compile(r'thread-(\d+)-\d+-\d+\.html'),
    re.compile(r'thread-(\d+)-\d+\.html'),
    re.compile(r'article-(\d+)-\d+\.html'),
    re.compile(r'[?&]tid=(\d+)'),
    re.compile(r'[?&]ptid=(\d+)'),  # Discuz redirect URL 里的帖子ID
]

# Discuz 论坛域名变体
FORUM_DOMAINS = {'lgqmonline.top', 'lgqmonline.top', 'lgqmonline.top', 'lgqmonline.top', 'lgqm.online'}


def extract_tid(url: str) -> Optional[int]:
    """从论坛 URL 中提取帖子 TID"""
    if not url:
        return None
    # 如果输入本身就是纯数字
    if url.strip().isdigit():
        return int(url.strip())
    for pattern in THREAD_URL_PATTERNS:
        match = pattern.search(url)
        if match:
            return int(match.group(1))
    return None


def extract_author_uid(url: str) -> Optional[int]:
    """从 URL 中提取作者 UID"""
    match = re.search(r'authorid=(\d+)', url)
    if match:
        return int(match.group(1))
    return None


def extract_page(url: str) -> int:
    """从 URL 中提取页码，默认为 1"""
    match = re.search(r'page=(\d+)', url)
    if match:
        return int(match.group(1))
    return 1


def is_forum_url(url: str) -> bool:
    """判断是否为已知论坛域名"""
    if not url:
        return False
    try:
        domain = urlparse(url).netloc
        return domain in FORUM_DOMAINS
    except Exception:
        return False


def normalize_forum_url(url: str, base_url: str = "https://lgqmonline.top") -> str:
    """
    标准化论坛 URL：将旧域名统一为 lgqmonline.top
    """
    if not url:
        return ""
    url = url.strip()
    for domain in FORUM_DOMAINS:
        if domain in url:
            # 提取路径部分
            try:
                parsed = urlparse(url)
                path_query = parsed.path
                if parsed.query:
                    path_query += "?" + parsed.query
                return f"{base_url}/{path_query.lstrip('/')}"
            except Exception:
                pass
    return url


# ============ 日期处理 ============

def parse_relative_date(text: str) -> str:
    """
    解析 Discuz 相对时间文本为 YYYY-MM-DD 格式
    支持格式：
    - "2026-6-7 21:58" (title属性中的绝对时间)
    - "1 分钟前", "20 小时前", "昨天 12:34"
    - "前天 08:15", "3 天前"
    - "2026-6-7"
    """
    if not text:
        return ""

    text = text.strip()

    # 已经是绝对时间
    abs_match = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?', text)
    if abs_match:
        y, m, d = abs_match.group(1), abs_match.group(2), abs_match.group(3)
        return f"{y}-{int(m):02d}-{int(d):02d}"

    # 无法解析的相对时间（先返回空，后续可扩展）
    return ""


def parse_datetime(text: str) -> Optional[datetime]:
    """解析日期时间字符串为 datetime 对象"""
    if not text:
        return None
    date_str = parse_relative_date(text)
    if date_str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            pass
    return None


# ============ 文本处理 ============

def slugify(title: str) -> str:
    """
    将帖子标题转为安全的文件名
    """
    # 去除危险字符
    title = re.sub(r'[\\/:*?"<>|]', '', title)
    # 限制长度
    if len(title) > 80:
        title = title[:80]
    return title.strip()


def normalize_title(title: str) -> str:
    """
    标准化标题用于匹配比较。
    去除前缀标签（【原创】等）、日期/更新后缀、空白差异。
    用于搬运文章标题匹配。
    """
    name = title.strip()

    # 去掉前缀标签：【原创】【半原创】【同人】【完结】【转正】等
    name = re.sub(r'^[【\[「〈][^】\]」〉]*[】\]」〉]\s*', '', name)

    # 去掉日期/更新后缀：XX.XX.XX更新、5.14更新、更新至XX章
    name = re.sub(r'\s*\d{1,2}[\.\-]\d{1,2}[\.\-]?\d{0,2}\s*更新?(?:至第?\w+章)?$', '', name)
    name = re.sub(r'\s*\d+年\d+月\d+日\s*(?:更新|彩蛋|尾声).*$', '', name)
    name = re.sub(r'\s*更新至第?\w+章$', '', name)

    # 去掉末尾的章节号/节号
    name = re.sub(r'\s+第[\d一二三四五六七八九十]+[章节].*$', '', name)

    # 全角/半角标点统一
    name = name.replace('（', '(').replace('）', ')').replace('：', ':').replace('，', ',')

    # 多余空白归一化
    name = re.sub(r'\s+', ' ', name).strip()

    return name


def clean_html(text: str) -> str:
    """基础 HTML 清理：去除 script/style 标签"""
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    return text


# ============ 日志 ============

_verbose = False


def set_verbose(v: bool):
    global _verbose
    _verbose = v


def log(msg: str, level: str = "INFO"):
    """简单日志输出"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    prefix = f"[{timestamp}]"
    if level == "ERROR":
        print(f"{prefix} ❌ {msg}", file=sys.stderr)
    elif level == "WARN":
        print(f"{prefix} ⚠️  {msg}")
    elif level == "SUCCESS":
        print(f"{prefix} ✅ {msg}")
    elif _verbose:
        print(f"{prefix}    {msg}")


# ============ HTTP 工具 ============

def rate_limit(last_request_time: float, interval: float = 2.0):
    """请求限速：确保两次请求间隔 >= interval 秒"""
    elapsed = time.time() - last_request_time
    if elapsed < interval:
        wait = interval - elapsed
        time.sleep(wait)
