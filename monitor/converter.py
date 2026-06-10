"""
格式转换器 - Archiver HTML → MediaWiki 标记格式
全新重写，基于 Archiver 模式的简洁 HTML 结构
"""
import re
import os
from typing import List, Dict, Optional
from datetime import datetime

from .config import get
from .models import Post
from .utils import log, slugify


def html_to_wiki(html: str) -> str:
    """
    将 Archiver HTML 内容转换为 MediaWiki 标记

    处理规则：
    - <br /> → 换行
    - <br>  → 换行
    - <strong>text</strong> → '''text'''
    - <a href="url">text</a> → [url text]
    - <img src="..."> → [[Image:...]]
    -  → 空格
    - &amp; → &
    - &lt; → <
    - &gt; → >
    - &quot; → "
    """
    text = html

    # HTML 实体解码
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('\r', '')  # 移除 Windows 换行符残留

    # 链接：<a href="url">text</a> → [url text]
    text = re.sub(
        r'<a[^>]*href="([^"]+)"[^>]*>([^<]*)</a>',
        r'[\1 \2]',
        text
    )

    # 加粗：<strong>text</strong> → '''text'''
    text = re.sub(r'<strong>(.*?)</strong>', r"'''\1'''", text, flags=re.DOTALL)

    # 换行：<br /> 或 <br> → \n
    text = re.sub(r'<br\s*/?>', '\n', text)

    # 段落：<p> → 双换行
    text = re.sub(r'</?p[^>]*>', '\n', text)

    # 删除其余 HTML 标签（span, div, font 等）
    text = re.sub(r'<[^>]+>', '', text)

    # 清理多余空白
    text = re.sub(r'\n{3,}', '\n\n', text)  # 最多连续两个换行
    text = text.strip()

    return text


def convert_post(post: Post, config: dict = None) -> str:
    """
    转换单个楼层为 Wiki 文本

    Args:
        post: 楼层数据
        config: 转换配置（可选，用于标题样式、楼层标记等）

    Returns:
        Wiki 格式文本
    """
    if config is None:
        config = {}

    content = html_to_wiki(post.content_html)
    if not content.strip():
        return ""

    lines = []

    # 标题处理：首楼/内容较长的楼层
    auto_title = config.get("auto_title", 1)
    title_style = config.get("title_style", "==")
    auto_threshold = config.get("auto_threshold", 200)
    show_date = config.get("show_date", 0)

    # 首楼始终保留
    if post.is_first_post:
        pass  # 首楼直接用内容
    # 自动标题：内容较长的楼层加标题
    elif auto_title == 4 and len(content) >= auto_threshold:
        lines.append(f'\n{title_style}{post.floor}{title_style}')
    elif auto_title == 5 and len(content) >= auto_threshold and post.floor > 1:
        lines.append(f'\n{title_style}{post.floor - 1}{title_style}')
    elif auto_title == 2 and len(content) >= auto_threshold:
        # 首行作为标题
        lines.append('')

    # 发帖时间标记
    if show_date == 1 and post.date:
        date_match = re.match(r'(\d{4}-\d{1,2}-\d{1,2})', post.date)
        if date_match:
            lines.append(f"\n{date_match.group(1)}\n")
    elif show_date == 2 and post.date:
        lines.append(f"\n{post.date}\n")

    lines.append(content)

    # 分割线（楼层之间）
    if config.get("split_line", False) and not post.is_first_post:
        lines.append("\n----")

    return "\n".join(lines).strip()


def generate_infobox(metadata: dict) -> str:
    """
    根据帖子元数据生成 {{Infobox TongRen}} 模板

    Args:
        metadata: {
            "title": 文章标题,
            "author": 作者,
            "forum_url": 论坛原帖链接,
            "post_date": 首发日期 (YYYY-MM-DD),
            "tid": 帖子ID,
        }

    Returns:
        MediaWiki 模板文本
    """
    title = metadata.get("title", "{{PAGENAME}}")
    author = metadata.get("author", "")
    forum_url = metadata.get("forum_url", "")
    post_date = metadata.get("post_date", datetime.now().strftime("%Y-%m-%d"))
    tid = metadata.get("tid", "")
    thread_name = metadata.get("title", "")

    # 格式化日期
    if isinstance(post_date, str):
        date_match = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})', post_date)
        if date_match:
            y, m, d = date_match.groups()
            post_date = f"{y}-{int(m):02d}-{int(d):02d}"
        else:
            post_date = datetime.now().strftime("%Y-%m-%d")

    # 构建论坛链接
    if forum_url and thread_name:
        forum_link = f"[{forum_url} {thread_name}]"
    elif forum_url:
        forum_link = forum_url
    else:
        forum_link = f"https://lgqmonline.top/thread-{tid}-1-1.html"
        if thread_name:
            forum_link = f"[{forum_link} {thread_name}]"

    # MediaWiki 模板语法使用双花括号 {{ ... }}
    # 此处用占位符避免 Python 字符串解析冲突
    T2 = "{{"
    T2E = "}}"
    T3 = "{{{"
    T3E = "}}}"

    lines = []
    lines.append(f"{T2}同人作品版权声明{T2E}")
    lines.append(f"{T2}Infobox TongRen")
    lines.append(f"| 同人作品 = {T2}PAGENAME{T2E}")
    lines.append(f"| 图像 = <!--[[Image:图片名.jpg|class=img-responsive]]-->")
    lines.append(f"| 图像信息 = ")
    lines.append(f"")
    lines.append(f"| 北朝论坛 = ")
    lines.append(f"| 北朝原帖 = ")
    lines.append(f"| 百度贴吧 = ")
    lines.append(f"| 贴吧原帖 = ")
    lines.append(f"| SC论坛 = ")
    lines.append(f"| SC原帖 = ")
    lines.append(f"| 知乎 = ")
    lines.append(f"| 知乎原帖 = ")
    lines.append(f"| 官方论坛 = <!--作者ID-->{author}")
    lines.append(f"| 官坛原帖 = <!--[原帖网址 原贴名称]-->{forum_link}")
    lines.append(f"| BiliBili = <!--作者ID-->")
    lines.append(f"| B站原帖 = <!--[原帖网址 原贴名称]-->")
    lines.append(f"| 其他网站 = ")
    lines.append(f"| 其他 = ")
    lines.append(f"")
    lines.append(f"| 首次发布 = <!-- XXXX-XX-XX 不足补零 -->{post_date}")
    lines.append(f"| 最近更新 = <!-- XXXX-XX-XX 不足补零 -->{post_date}")
    lines.append(f"")
    lines.append(f"| 地点 = ")
    lines.append(f"| 涉及方面 = <!--非必须。使用中文顿号，即退格号下面的按键「、」作为分隔符-->")
    lines.append(f"| 内容关键字 = ")
    lines.append(f"")
    lines.append(f"| 完结情况 = <!--未完结/完结-->未完结")
    lines.append(f"| 字数统计 = {T2}字数统计{T2E}")
    lines.append(f"| 转正状态 = <!--待转正/已转正-->待转正")
    lines.append(f"| 转正所在章节 = ")
    lines.append(f"")
    lines.append(f"| 同人活动荣誉 = ")
    lines.append(f"{T2E}<!-- 如非必须，可不加 __TOC__ ，三节以上会自动生成目录 -->")
    lines.append(f"{T2}首行缩进start{T2E}")
    lines.append("")

    return "\n".join(lines)


def convert_thread_to_wiki(posts: List[Post], metadata: dict = None,
                            config: dict = None) -> str:
    """
    将整个帖子的所有楼层转换为 Wiki 格式文本

    Args:
        posts: 楼层列表
        metadata: 帖子元数据（用于生成 Infobox）
        config: 转换配置

    Returns:
        完整的 MediaWiki 格式文本
    """
    if config is None:
        config = {
            "auto_title": 0,
            "auto_threshold": 200,
            "title_style": "==",
            "show_date": 0,
            "split_line": False,
        }

    parts = []

    # 1. Infobox 头部
    if metadata:
        parts.append(generate_infobox(metadata))
    else:
        parts.append("{{同人作品版权声明}}\n")

    # 2. 转换每个楼层
    for post in posts:
        wiki_text = convert_post(post, config)
        if wiki_text:
            parts.append(wiki_text)

    # 3. 结束标记
    parts.append("\n{{首行缩进end}}")
    parts.append("[[分类:同人作品]]")

    return "\n\n".join(parts)


def save_wiki_file(content: str, filename: str, output_dir: str = None) -> str:
    """
    保存 .mw 文件

    Args:
        content: Wiki 格式文本
        filename: 文件名（不含后缀）
        output_dir: 输出目录

    Returns:
        保存的完整文件路径
    """
    if output_dir is None:
        output_dir = get("output.output_dir", "output")

    os.makedirs(output_dir, exist_ok=True)

    # 清理文件名
    safe_name = slugify(filename)
    if not safe_name:
        safe_name = f"article_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    filepath = os.path.join(output_dir, f"{safe_name}.mw")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    log(f"Wiki 文件已保存: {filepath}", "SUCCESS")
    return filepath


def update_existing_wiki(existing_content: str, new_posts: List[Post],
                          metadata: dict = None) -> str:
    """
    更新已有的 Wiki 文章：保留原 Infobox 头部，替换正文内容

    Args:
        existing_content: 现有 .mw 文件内容
        new_posts: 新拉取的楼层列表
        metadata: 新的元数据（可选，用于更新日期等）

    Returns:
        更新后的 Wiki 文本
    """
    # 提取现有 Infobox（从开头到 {{首行缩进start}}）
    infobox_match = re.search(
        r'(.*?\{\{首行缩进start\}\})',
        existing_content,
        re.DOTALL
    )
    infobox = infobox_match.group(1) if infobox_match else generate_infobox(metadata or {})

    # 如果提供了新元数据，更新最近更新日期
    if metadata and metadata.get("post_date"):
        date_str = metadata["post_date"]
        if isinstance(date_str, str):
            date_match = re.match(r'(\d{4}-\d{1,2}-\d{1,2})', date_str)
            if date_match:
                date_str = date_match.group(1)
        infobox = re.sub(
            r'(\|\s*最近更新\s*=\s*<!--[^>]*-->)\S*',
            rf'\1{date_str}',
            infobox
        )

    # 转换新内容
    config = {
        "auto_title": 0,
        "auto_threshold": 200,
        "title_style": "==",
        "show_date": 0,
        "split_line": False,
    }

    parts = [infobox.strip()]
    for post in new_posts:
        wiki_text = convert_post(post, config)
        if wiki_text:
            parts.append(wiki_text)

    parts.append("\n{{首行缩进end}}")
    parts.append("[[分类:同人作品]]")

    return "\n\n".join(parts)
