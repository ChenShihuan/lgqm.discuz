"""
格式转换器 - Archiver HTML → MediaWiki 标记格式
全新重写，基于 Archiver 模式的简洁 HTML 结构
"""
import re
import os
from typing import List, Dict, Optional
from datetime import datetime

from .config import get, tid_text_dir
from .models import Post
from .utils import log, slugify


def html_to_wiki(html: str) -> str:
    """
    将 HTML 内容转换为 MediaWiki 标记

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
    - 「XXX 发表于 YYYY-MM-DD HH:MM」行 → 删除
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

    # 图片处理（在其他标签被删除之前）
    # Discuz 附件图片：<img file="data/attachment/.../xxx.jpg" zoomfile="...">
    # 转换为 MediaWiki: [[File:xxx.jpg|600px]]
    def _img_replace(m):
        # 优先取 file 属性，其次 zoomfile，其次 src
        for g in m.groups():
            if g:
                src = g
                break
        else:
            return ''
        # 提取文件名
        filename_match = re.search(r'([^/]+\.(?:gif|jpg|jpeg|png|svg))', src, re.IGNORECASE)
        if filename_match:
            filename = filename_match.group(1)
            return f'\n[[File:{filename}|600px]]\n'
        return ''
    # <img file="...">  (Discuz 附件图片，含缩略信息)
    text = re.sub(
        r'<img[^>]*\bfile="([^"]*)"[^>]*>',
        _img_replace,
        text
    )
    # <img zoomfile="..."> (Discuz 附件图片另一种形式)
    text = re.sub(
        r'<img[^>]*\bzoomfile="([^"]*)"[^>]*>',
        _img_replace,
        text
    )
    # 常规 <img src="..."> (非 Discuz 附件图片，保留完整 URL)
    text = re.sub(
        r'<img[^>]*\bsrc="([^"]+)"[^>]*/?>',
        r'\n[[Image:\1|class=img-responsive]]\n',
        text
    )

    # 清理附件信息块：下载链接、上传时间、文件大小等
    text = re.sub(r'\n\s*下载附件\s*\n', '', text)
    text = re.sub(r'\n?\d{4}-\d{1,2}-\d{1,2} \d{2}:\d{2} 上传\s*\n?', '', text)
    # 附件文件名及大小行：如 "长江口.jpg (301.4 KB, 下载次数: 0)"
    text = re.sub(r'\n?[^\s]+\.\w{3,4}\s*\([\d.]+\s*\w+B[^)]*\)\s*\n?', '', text)
    # 清理 Discuz 附件下载链接（已被转成 [url text] 格式）
    text = re.sub(r'\n?\[forum\.php\?mod=attachment[^\]]+\]\s*\n?', '', text)
    # 清理附件 UI 残留文本
    text = re.sub(r'\n?\([\d.]+\s*\w+B[^)]*\)\s*\n?', '', text)
    # 清理 static/image/ 下的 UI 图标/表情引用（非文章配图）
    text = re.sub(r'\n?\[\[Image:static/image/(?:common|smiley)/[^\]]+\]\]\s*\n?', '', text)

    # 删除其余 HTML 标签（span, div, font 等）
    text = re.sub(r'<[^>]+>', '', text)

    # 清理「XXX 发表于 YYYY-MM-DD HH:MM」行
    text = re.sub(r'\n\s*[^\s]+ 发表于 \d{4}-\d{1,2}-\d{1,2} \d{2}:\d{2}\s*\n', '\n', text)
    # 如果「发表于」在行首，去掉整行
    text = re.sub(r'^[^\s]+ 发表于 \d{4}-\d{1,2}-\d{1,2} \d{2}:\d{2}\s*\n?', '', text, flags=re.MULTILINE)

    # 清理「本帖最后由 XXX 于 YYYY-MM-DD HH:MM 编辑」
    text = re.sub(r'本帖最后由 [^\s]+ 于 \d{4}-\d{1,2}-\d{1,2} \d{2}:\d{2} 编辑\s*', '', text)

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
    # 日期处理：首次发布取首楼日期，最近更新取最新作者章节日期
    for date_key in ("first_publish_date", "last_update_date", "post_date"):
        if date_key not in metadata:
            metadata[date_key] = datetime.now().strftime("%Y-%m-%d")
        raw = metadata[date_key]
        if isinstance(raw, str):
            dm = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})', raw)
            if dm:
                y, m, d = dm.groups()
                metadata[date_key] = f"{y}-{int(m):02d}-{int(d):02d}"
            else:
                metadata[date_key] = datetime.now().strftime("%Y-%m-%d")

    first_publish = metadata["first_publish_date"]
    last_update = metadata["last_update_date"]
    tid = metadata.get("tid", "")
    thread_name = metadata.get("title", "")

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
    lines.append(f"| 首次发布 = <!-- XXXX-XX-XX 不足补零 -->{first_publish}")
    lines.append(f"| 最近更新 = <!-- XXXX-XX-XX 不足补零 -->{last_update}")
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


def _convert_reply(html: str) -> str:
    """
    将楼主回复其他网友的 HTML 转换为同人注释格式：

        {{同人注释start}}
        引用者: 引用的内容
        — 楼主的回复内容
        {{同人注释end}}
    """
    import re as _re

    bq_match = _re.search(r'<blockquote>(.*?)</blockquote>', html, re.DOTALL)
    if not bq_match:
        return html_to_wiki(html)

    bq_inner = bq_match.group(1)
    reply_html = html[bq_match.end():]

    # 提取引用者名字
    name_match = _re.search(r'<a[^>]*>([^<]+)</a>', bq_inner)
    quoter = name_match.group(1).strip() if name_match else ""

    # 去掉引用内的署名行（XXX 发表于 ...）
    bq_clean = _re.sub(r'<font[^>]*>.*?</font>', '', bq_inner, flags=_re.DOTALL)

    quoted = html_to_wiki(bq_clean).strip()
    reply = html_to_wiki(reply_html).strip()

    parts = []
    if quoter:
        parts.append(f"{quoter}: {quoted}" if quoted else f"{quoter}")
    elif quoted:
        parts.append(quoted)
    if reply:
        parts.append(f"— {reply}")

    return "\n".join(parts)


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

    # 1. 确定作者名（用于区分正文与回复）
    thread_author = metadata.get("author", "") if metadata else ""

    # 2. 预扫描：收集首楼日期和最新作者章节日期（Infobox 生成之前）
    first_post_date = ""
    last_author_chapter_date = ""
    for post in posts:
        if post.is_first_post and post.date:
            first_post_date = post.date
        is_author = thread_author and post.author.strip() == thread_author.strip()
        if not post.is_first_post and is_author and post.content_html:
            is_author_reply = '<blockquote>' in post.content_html
            # 只有非回复的楼主正文帖（>=200 字）才算章节更新日期
            if not is_author_reply and len(post.content_html) >= 200 and post.date:
                last_author_chapter_date = post.date
    if metadata:
        if first_post_date:
            metadata["first_publish_date"] = first_post_date
        if last_author_chapter_date:
            metadata["last_update_date"] = last_author_chapter_date
        elif first_post_date:
            metadata["last_update_date"] = first_post_date

    # 3. Infobox 头部（此时日期已正确设置）
    if metadata:
        parts.append(generate_infobox(metadata))
    else:
        parts.append("{{同人作品版权声明}}\n")

    # 4. 转换每个楼层并去重
    seen_content = set()  # 用于去除跨楼引用重复
    for post in posts:
        wiki_text = convert_post(post, config)
        if not wiki_text:
            continue

        is_author = thread_author and post.author.strip() == thread_author.strip()
        raw_html = post.content_html or ""

        # 楼主回复检测：内容中包含 <blockquote> 表示是回复其他网友
        is_author_reply = is_author and not post.is_first_post and '<blockquote>' in raw_html

        if is_author_reply:
            # 楼主回复 → 同人注释（引用+回复 格式）
            wiki_text = _convert_reply(raw_html)
            wiki_text = f"{{{{同人注释start}}}}\n{wiki_text}\n{{{{同人注释end}}}}"
        elif is_author and not post.is_first_post:
            # 楼主纯内容帖：>=200 字视为章节，<200 字视为短注
            if len(wiki_text) >= 200:
                # 作者章节：首行作为标题
                lines = wiki_text.split('\n', 1)
                first_line = lines[0].strip()
                if first_line and len(first_line) < 120:
                    rest = lines[1].strip() if len(lines) > 1 else ""
                    wiki_text = f"== {first_line} ==\n\n{rest}"
            else:
                # 短内容 → 同人注释
                wiki_text = f"{{{{同人注释start}}}}\n{wiki_text}\n{{{{同人注释end}}}}"
        elif not post.is_first_post and not is_author:
            # 其他网友回复 → 同人注释
            wiki_text = f"{{{{同人注释start}}}}\n{wiki_text}\n{{{{同人注释end}}}}"

        # 去重：跳过与前面楼层高度重复的内容（论坛引用导致）
        text_normalized = wiki_text.strip()[:200]
        if text_normalized and text_normalized in seen_content:
            continue
        if len(text_normalized) > 30:
            seen_content.add(text_normalized)

        parts.append(wiki_text)

    # 5. 结束标记
    parts.append("\n{{首行缩进end}}")
    parts.append("[[分类:同人作品]]")

    return "\n\n".join(parts)


def save_wiki_file(content: str, filename: str, output_dir: str = None,
                   tid: int = None) -> str:
    """
    保存 .mw 文件

    Args:
        content: Wiki 格式文本
        filename: 文件名（不含后缀）
        output_dir: 输出目录（优先于 tid）
        tid: 帖子ID（自动使用 output/{tid}/text/ 目录）

    Returns:
        保存的完整文件路径
    """
    if output_dir is None:
        if tid is not None:
            output_dir = tid_text_dir(tid, filename)
        else:
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
    增量更新已有的 Wiki 文章：保留原文全部内容，仅追加论坛新楼层。

    核心原则：以 Wiki 原文为基准，最小修改。
    - 保留 Infobox / 章节 / 格式 / 分类标签
    - 从论坛楼层中找出 Wiki 上次更新之后的新楼层
    - 追加新楼层到原文末尾（{{首行缩进end}} 之前）
    """
    # 1. 解析原文：Infobox + 正文 + 尾部（end/category）
    infobox_match = re.search(
        r'(.*?\{\{首行缩进start\}\})',
        existing_content, re.DOTALL
    )
    infobox = infobox_match.group(1) if infobox_match else generate_infobox(metadata or {})

    # 正文 = Infobox 之后到 {{首行缩进end}} 之前
    after_infobox = existing_content[infobox_match.end():] if infobox_match else existing_content
    end_match = re.search(r'\{\{首行缩进end\}\}', after_infobox)
    if end_match:
        body = after_infobox[:end_match.start()]
        tail = after_infobox[end_match.start():]  # {{首行缩进end}} + categories
    else:
        body = after_infobox
        tail = "\n{{首行缩进end}}\n[[分类:同人作品]]"

    # 2. 更新「最近更新」日期
    if metadata and metadata.get("post_date"):
        date_str = metadata["post_date"]
        if isinstance(date_str, str):
            m = re.match(r'(\d{4}-\d{1,2}-\d{1,2})', date_str)
            if m:
                date_str = m.group(1)
        infobox = re.sub(
            r'(\|\s*最近更新\s*=\s*(?:<!--[^>]*-->)?)\s*\S*',
            rf'\1{date_str}',
            infobox
        )

    # 3. 提取 Wiki 上次更新日期（用于判断新楼层）
    wiki_date = ""
    date_match = re.search(r'\|\s*最近更新\s*=\s*(?:<!--[^>]*-->)?\s*(\S+)', infobox)
    if date_match:
        wiki_date = date_match.group(1).strip()

    # 4. 获取作者名
    thread_author = ""
    author_match = re.search(r'\|\s*官方论坛\s*=\s*(?:<!--[^>]*-->)?\s*(\S+)', infobox)
    if author_match:
        thread_author = author_match.group(1).strip()
    if not thread_author and new_posts:
        first = next((p for p in new_posts if p.is_first_post), new_posts[0])
        thread_author = first.author.strip()

    # 5. 找出论坛新楼层（日期晚于 Wiki 上次更新）
    config = {
        "auto_title": 0, "auto_threshold": 200,
        "title_style": "==", "show_date": 0, "split_line": False,
    }

    new_parts = []
    seen_in_body = set()

    # 从正文中提取已有的内容片段用于去重
    for chunk in body.split('\n\n'):
        chunk = chunk.strip()
        if len(chunk) > 50:
            seen_in_body.add(chunk[:200])

    for post in new_posts:
        # 跳过首楼（已在 Wiki 中）
        if post.is_first_post:
            continue

        wiki_text = convert_post(post, config)
        if not wiki_text or not wiki_text.strip():
            continue

        # 判断是否为新楼层：日期晚于 wiki_date 或内容未在正文中出现
        post_date = ""
        if post.date:
            dm = re.match(r'(\d{4}-\d{1,2}-\d{1,2})', post.date)
            if dm:
                post_date = dm.group(1)

        is_newer = post_date and wiki_date and post_date > wiki_date
        in_body = wiki_text.strip()[:200] in seen_in_body

        if not is_newer and in_body:
            continue  # 已在 Wiki 正文中，跳过

        # 去重（新楼层之间）
        norm = wiki_text.strip()[:200]
        if norm in seen_in_body:
            continue
        if len(norm) > 30:
            seen_in_body.add(norm)

        # 非作者回复包裹同人注释
        if thread_author and post.author.strip() != thread_author:
            wiki_text = f"{{{{同人注释start}}}}\n{wiki_text}\n{{{{同人注释end}}}}"

        new_parts.append(wiki_text)

    # 6. 组装：Infobox + 原正文 + 新楼层 + 尾部
    result = infobox.strip() + "\n" + body.strip()
    if new_parts:
        result += "\n\n" + "\n\n".join(new_parts)
    result += "\n" + tail.strip()

    return result
