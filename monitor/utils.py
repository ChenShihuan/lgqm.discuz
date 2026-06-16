"""
工具函数：URL解析、TID提取、日期处理、日志
"""
import os
import re
import sys
import time
import random
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
FORUM_DOMAINS = {'lgqmonline.top', 'lgqm.online'}

# 旧域名 → 新域名的映射（拉取/转换时自动替换）
OLD_FORUM_DOMAINS = ['www.lgqm.top', 'lgqm.gq', 'lgqm.top']


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
    # 先检查是否已经是目标域名
    if 'lgqmonline.top' in url:
        return url
    # 替换旧域名
    for old_domain in OLD_FORUM_DOMAINS:
        if old_domain in url:
            try:
                parsed = urlparse(url)
                path_query = parsed.path
                if parsed.query:
                    path_query += "?" + parsed.query
                return f"{base_url}/{path_query.lstrip('/')}"
            except Exception:
                pass
    return url


def normalize_forum_domains(text: str) -> str:
    """
    替换文本中所有旧论坛域名为 lgqmonline.top。

    覆盖的旧域名：
    - www.lgqm.top
    - lgqm.gq
    - lgqm.top

    用于拉取/转换文章时自动修正，以及批量更新存量 .mw 文件。
    """
    if not text:
        return text
    # 按长度降序排列，确保先匹配长域名（避免 lgqm.top 先替换了 www.lgqm.top 中的部分）
    for old_domain in sorted(OLD_FORUM_DOMAINS, key=len, reverse=True):
        text = text.replace(old_domain, 'lgqmonline.top')
    return text


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

def rate_limit(last_request_time: float, interval: float = 2.0, jitter: float = 0.0):
    """
    请求限速：确保两次请求间隔 >= interval 秒。
    jitter 参数添加随机抖动（如 0.3 = ±30%），避免机械式精确间隔。
    """
    elapsed = time.time() - last_request_time
    if elapsed < interval:
        wait = interval - elapsed
        if jitter > 0:
            wait += random.uniform(-jitter * interval, jitter * interval)
            wait = max(0.1, wait)  # 防止负值
        time.sleep(wait)


# ============ 字数统计 ============

def count_words_mw(filepath: str, dry_run: bool = False) -> dict:
    """
    统计 .mw 文件正文的字数，更新 Infobox 中的 | 字数统计 字段。

    统计范围：{{首行缩进start}} 到 {{首行缩进end}} 之间的正文，
    排除 {{同人注释start}}...{{同人注释end}} 包裹的讨论内容。

    返回 {"chinese": int, "english": int, "total": int, "word_count": str}
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f".mw 文件不存在: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取正文（首行缩进之间，排除注释块）
    parts = content.split("{{首行缩进start}}")
    if len(parts) < 2:
        raise ValueError("未找到 {{首行缩进start}} 标记")
    body = parts[-1].split("{{首行缩进end}}")[0]

    # 移除同人注释
    body = re.sub(r"{{同人注释start}}.*?{{同人注释end}}", "", body, flags=re.DOTALL)

    # 去除 wiki 标记
    body = re.sub(r"\[\[File:[^\]]+\]\]", "", body)            # 图片
    body = re.sub(r"\[\[分类:[^\]]+\]\]", "", body)            # 分类
    body = re.sub(r"={2,}.*?={2,}", "", body)                  # 章节标题
    body = re.sub(r"<[^>]+>", "", body)                         # HTML 标签
    body = re.sub(r"\[https?://[^\] ]+[^\]]*\]", "", body)     # 外部链接
    body = re.sub(r"\[\[([^\]|]+)\]\]", r"\1", body)           # [[内部链接]]
    body = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", body)   # [[链接|文字]]
    body = re.sub(r"'{2,}", "", body)                           # 粗体/斜体
    body = re.sub(r"{{[^}]+}}", "", body)                       # 模板
    body = re.sub(r"__[A-Z]+__", "", body)                      # 行为开关
    body = re.sub(r"\[\[", "", body)                            # 残留双方括号
    body = re.sub(r"\]\]", "", body)

    # 统计中文和英文
    chinese = len(re.findall(r"[一-鿿㐀-䶿]", body))
    english_words = re.findall(r"[a-zA-Z]+", body)
    english = sum(len(w) for w in english_words)  # 字符数

    total = chinese + english

    # 格式化：>=1000 用千字表示
    word_count = f"{total / 1000:.1f}"

    # 不修改 Infobox —— Infobox 保留 {{字数统计}} 模板由 Wiki 自动计算
    # 字数通过 update_from_mw_file() 写入同人作品列表
    if not dry_run:
        pass

    return {
        "chinese": chinese,
        "english": english,
        "total": total,
        "word_count": word_count,
    }


# ============ 图片格式检测 ============

# 支持检测的图片格式及其 magic bytes
_IMAGE_SIGNATURES = [
    # (canonical_ext, mime_type, magic_bytes, offset)
    ('webp', 'image/webp', b'RIFF', 0, b'WEBP', 8),   # RIFF....WEBP
    ('png',  'image/png',  b'\x89PNG\r\n\x1a\n', 0),
    ('jpg',  'image/jpeg', b'\xff\xd8', 0),
    ('gif',  'image/gif',  b'GIF8', 0),                 # GIF87a or GIF89a
    ('bmp',  'image/bmp',  b'BM', 0),
    ('svg',  'image/svg+xml', b'<svg', 0),
    ('svg',  'image/svg+xml', b'<?xml', 0),             # SVG 可能以 xml 声明开头
]


def detect_image_type(filepath: str) -> tuple:
    """
    通过 magic bytes 检测图片真实格式。

    不依赖 imghdr（Python 3.13 已废弃）或 PIL（额外依赖）。
    支持 JPEG, PNG, GIF, WebP, BMP, SVG。

    Returns:
        (canonical_ext, mime_type) 例如 ('jpg', 'image/jpeg'), ('webp', 'image/webp')
        无法识别时返回 (None, None)
    """
    try:
        with open(filepath, 'rb') as f:
            header = f.read(32)
    except (IOError, OSError):
        return (None, None)

    for ext, mime, magic, offset, *rest in _IMAGE_SIGNATURES:
        if len(header) < offset + len(magic):
            continue
        if header[offset:offset + len(magic)] == magic:
            # WebP 需要额外验证：RIFF 后第 8-11 字节必须是 WEBP
            if rest:
                check_bytes, check_offset = rest
                if len(header) >= check_offset + len(check_bytes):
                    if header[check_offset:check_offset + len(check_bytes)] != check_bytes:
                        continue
            return (ext, mime)

    # 回退：svg 也可能以 <?xml 开头
    if header[:5] == b'<?xml':
        # 在更大范围内搜索 svg 标记
        try:
            with open(filepath, 'rb') as f:
                content = f.read(1024)
            if b'<svg' in content[:512] or b'<SVG' in content[:512]:
                return ('svg', 'image/svg+xml')
        except (IOError, OSError):
            pass

    return (None, None)


def fix_image_extension(filepath: str, dry_run: bool = False) -> dict:
    """
    检测图片扩展名是否与实际格式匹配，不匹配时修正扩展名。

    同时处理 .jpeg → .jpg 规范化。

    Args:
        filepath: 图片文件路径
        dry_run: 仅检测不实际重命名

    Returns:
        None 表示无需修正
        {old_path, new_path, old_name, new_name, old_ext, new_ext, reason} 表示已/需修正
    """
    import os as _os

    if not _os.path.isfile(filepath):
        return None

    dirname = _os.path.dirname(filepath)
    basename = _os.path.basename(filepath)
    stem, old_ext = _os.path.splitext(basename)
    old_ext = old_ext.lower().lstrip('.')

    real_ext, mime = detect_image_type(filepath)

    if real_ext is None:
        return None  # 无法识别格式，不修改

    # 规范化 .jpeg → .jpg
    if old_ext == 'jpeg' and real_ext == 'jpg':
        new_name = f"{stem}.jpg"
        new_path = _os.path.join(dirname, new_name)
        result = {
            'old_path': filepath, 'new_path': new_path,
            'old_name': basename, 'new_name': new_name,
            'old_ext': old_ext, 'new_ext': 'jpg',
            'reason': f'规范化: .jpeg → .jpg'
        }
        if not dry_run:
            _os.rename(filepath, new_path)
        return result

    # 实际格式不匹配
    if old_ext != real_ext:
        new_name = f"{stem}.{real_ext}"
        new_path = _os.path.join(dirname, new_name)
        result = {
            'old_path': filepath, 'new_path': new_path,
            'old_name': basename, 'new_name': new_name,
            'old_ext': old_ext, 'new_ext': real_ext,
            'reason': f'格式不匹配: .{old_ext} 实际为 {mime} → .{real_ext}'
        }
        if not dry_run:
            _os.rename(filepath, new_path)
        return result

    return None

def clean_article_name(title: str) -> str:
    """从论坛帖子标题生成 Wiki 文章名（去除标签、日期后缀等）"""
    name = title.strip()

    # 循环去掉所有前缀标签（【】〖〗等）
    while True:
        old = name
        name = re.sub(r'^[【\[「〈][^】\]」〉]+[】\]」〉]\s*', '', name)
        name = re.sub(r'^[〖][^〗]+[〗]\s*', '', name)
        if name == old:
            break

    # 去掉日期/更新后缀（括号包裹的优先处理）
    # 如 "（26年4月6日更新至第42章）"、"（6.14更新"、"（0118 第42章 广州新城）"、"（12月29日 更新两节）"
    name = re.sub(r'[（(]\s*\d+年\d+月\d+日\s*更新.*[）)]\s*$', '', name)
    name = re.sub(r'[（(]\s*\d+年\d+月\d+日\s*(?:彩蛋|尾声).*[）)]\s*$', '', name)
    # M月D日 格式（无年份，括号包裹）：如 "（12月29日 更新两节  南下青州）"
    name = re.sub(r'[（(]\s*\d{1,2}月\d{1,2}日\s*更新.*[）)]\s*$', '', name)
    # M月D日 格式（无年份，括号包裹，彩蛋/尾声）：如 "（6月1日 彩蛋）"
    name = re.sub(r'[（(]\s*\d{1,2}月\d{1,2}日\s*(?:彩蛋|尾声).*[）)]\s*$', '', name)
    name = re.sub(r'[（(]\s*\d{4}[\.\-]\d{1,2}[\.\-]\d{1,2}\s*更新?(?:至?第?\w+章)?[）)]?\s*', '', name)
    name = re.sub(r'[（(]\s*\d{1,2}[\.\-]\d{1,2}[\.\-]?\d{0,2}\s*更新?(?:至?第?\w+章)?[）)]?\s*', '', name)
    name = re.sub(r'[（(]\s*\d{4}\s*第\S+章.*[）)]\s*$', '', name)
    # 如 " 1.15更新第八案"、" 6.14更新"、" 0118 第42章"
    name = re.sub(r'\s*\d{4}[\.\-]\d{1,2}[\.\-]\d{1,2}\s*更新?.*$', '', name)
    name = re.sub(r'\s*\d{1,2}[\.\-]\d{1,2}[\.\-]?\d{0,2}\s*更新?(?:至第?\w+章)?.*$', '', name)
    name = re.sub(r'\s*\d+年\d+月\d+日\s*(?:更新|彩蛋|尾声).*$', '', name)
    # M月D日 格式（无年份，无括号）：如 " 12月29日 更新两节"
    name = re.sub(r'\s*\d{1,2}月\d{1,2}日\s*(?:更新|彩蛋|尾声).*$', '', name)
    name = re.sub(r'\s*更新至第?\w+章$', '', name)
    # N楼K更格式：如 " 62楼5更"、" 12楼更新"
    name = re.sub(r'\s*\d+楼\d*\s*更.*$', '', name)
    # 大纲版本后缀：如 " 大纲3版"
    name = re.sub(r'\s*大纲\d*\s*版\s*$', '', name)

    # 去掉完结/连载状态后缀：支持（完结）、【完结】等括号
    name = re.sub(r'\s*[（(【\[](?:已?完结|连载中|全文完|未完待续|更新中)[）)】\]]\s*$', '', name)
    # 去掉文体标签后缀：如 "（短篇）"、"（中篇）"、"（长篇）"
    name = re.sub(r'\s*[（(][^）)]*(?:短篇|中篇|长篇)[^）)]*[）)]\s*$', '', name)

    # 去掉书名号《》 — 注意: 主副标题语义连接（如 主标题——副标题）应在审阅阶段由 skill 处理
    name = re.sub(r'[《》]', '', name)
    name = name.strip()

    return name if name else title.strip()
