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

# 模块级变量：存储最近一次转换中被过滤的章节标题和 TOC 信息（供 CLI 输出复核清单）
last_merged_titles = []
_last_toc_info = {}


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

    # 段落：<p> → 换行
    text = re.sub(r'</?p[^>]*>', '\n', text)

    # Div 标签 → 换行
    # Discuz 使用 <div align="left"> 包裹每个段落，并非 <br> 或 <p>
    # 需在标签删除前将 <div> 转为换行，否则段落会连成一片
    text = re.sub(r'</?div[^>]*>', '\n', text)

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


def _should_keep_question(text: str) -> bool:
    """
    判断读者提问是否有实质内容，过滤纯赞美/催更/无意义回复。
    参考 review-article skill 中的 should_keep() 逻辑。
    """
    import re as _re
    clean = _re.sub(r'\[\[Image:[^]]+\]\]', '', text).strip()
    clean = _re.sub(r'\n+', ' ', clean).strip()
    if not clean:
        return False
    if len(clean) < 10:
        return False
    praise = ['赞美', '催更', '加油', '顶', '支持', '楼主加油',
              '前排', '马克', '留名', '先赞后看', '写得好', '等更', '好康',
              '高产', '文笔', '好评', '鼓掌', '撒花', '更新了', '新坑',
              '祝楼主', '文运', '题材好', '期待更新', '快点更', '快更新']
    for pw in praise:
        if pw in clean and len(clean) < 40:
            return False
    # 纯符号/数字/英文短句
    if _re.match(r'^[\s!！。.…\-—~～0-9a-zA-Z]+$', clean) and len(clean) < 15:
        return False
    return True


def _is_chapter_start(first_line: str) -> bool:
    """
    判断作者帖首行是否是真章节标题（而非上一章的延续）。

    返回 True 表示应创建新章节，False 表示应合并到上一章。
    """
    import re as _re
    line = first_line.strip()

    # 非标题内容：图片引用、链接、纯符号
    if _re.match(r'\[\[(?:File|Image):', line):
        return False
    if line.startswith(('http://', 'https://', '[http')):
        return False

    # 加粗/斜体标记包裹的标题：'''第四十三章 达摩克利斯之剑'''
    #   去掉加粗标记后重新检查
    stripped_bold = line.strip("'")
    if stripped_bold != line and stripped_bold:
        return _is_chapter_start(stripped_bold)

    # 规则 1: 以对话引导符开头 → 延续（非章节）
    if line.startswith(('"', '"', '"', '「', '「', '"', '“', '(')):
        return False

    # 规则 2: 超长标题（>50 字）→ 不是有意为之的章节标题
    if len(line) > 50:
        return False

    # 规则 3: 简短有意标题（≤10 字，不含引号、逗号）→ 很可能是真章节
    if len(line) <= 10:
        if not _re.search(r'["「」"\'，,。.]', line):
            if not line.endswith(('了', '呢', '吧', '啊')):
                return True

    # 规则 4: 日期/番外/带括号后缀 → 真章节
    if _re.match(r'圣历|第[一二三四五六七八九十百千]+章|番外', line):
        return True
    # 括号后缀通常是作者有意标注：（一）（上）（自封）（完）等
    if _re.search(r'[（(][^）)]*[）)]', line) and len(line) <= 20:
        return True

    # 规则 5: 小说式场景设定开头 → 真章节
    #   "时间，地点，人物，事件" 式的句子
    if _re.match(r'\d{4}年', line):
        return True

    # 默认：不确定 → 保守地视为延续（不创建新章节）
    return False


def _parse_toc(wikitext: str) -> dict:
    """
    从主楼 wikitext 中解析目录。
    格式示例：
        目录
        [https://...pid=532627258&fromuid=8961 第一章 斜杠青年鹿文渊]
        [https://...pid=532627260&fromuid=8961 第二章 黄骅的来信]

    返回 {numeric_pid: chapter_name} 映射。
    """
    import re as _re
    result = {}
    # 找到"目录"到下一个空行/大标题之间的内容
    toc_start = wikitext.find('目录')
    if toc_start < 0:
        return result
    toc_chunk = wikitext[toc_start:toc_start + 5000]

    # 匹配 [url pid=数字 章节名] 格式
    links = _re.findall(
        r'\[https?://[^\]\s]+pid=(\d+)[^\]\s]*\s+([^\]]+)\]',
        toc_chunk
    )
    for pid, name in links:
        result[pid] = name.strip()

    # 匹配无 pid 的首章链接（指向主题帖本身，URL 中不含 pid=）
    #   排除后续章节链接（URL 含 pid= 的是具体楼层）
    first_chapter = _re.findall(
        r'\[(https?://[^\]]*tid=\d+[^\]]*)\s+(第[一二三四五六七八九十百千]+章\s+[^\]]+)\]',
        toc_chunk
    )
    for url, name in first_chapter:
        if 'pid=' not in url:
            result["_first_post"] = name.strip()
            break  # 只要第一个
    return result


def _parse_toc_external(toc_analysis: dict, posts: List[Post]) -> dict:
    """
    将外部 TOC 分析结果（来自 AI preanalyze）转为内部格式 {numeric_pid: chapter_name}。

    支持三种映射策略：
      1. PID 直接匹配：entry["pid"] 去前缀后作为 key
      2. 楼层号匹配：entry["floor"] → 查找对应 Post 的 PID
      3. 纯名称：存为 "_name:章节名"（后续由 _is_chapter_start 模糊匹配）
    """
    result = {}
    entries = toc_analysis.get("entries", [])
    for entry in entries:
        name = entry.get("chapter_name", "").strip()
        if not name:
            continue

        pid = entry.get("pid", "")
        floor = entry.get("floor")

        # 策略 1: PID 直接匹配
        if pid and pid.strip():
            numeric_pid = pid.strip().replace("pid", "")
            result[numeric_pid] = name
            continue

        # 策略 2: 楼层号 → PID
        if floor is not None:
            try:
                floor_int = int(floor)
            except (ValueError, TypeError):
                floor_int = None
            if floor_int is not None:
                for p in posts:
                    if p.floor == floor_int:
                        numeric_pid = p.pid.replace("pid", "") if p.pid else ""
                        if numeric_pid:
                            result[numeric_pid] = name
                        break
                continue

        # 策略 3: 纯名称（无楼层/PID 对应）
        key = f"_name:{name}"
        result[key] = name

    # 处理首章（TOC 第一个条目若指向首楼）
    if entries and toc_analysis.get("source_floor", 0) >= 0:
        first = entries[0]
        first_floor = first.get("floor")
        if first_floor == 1 or (first_floor is None and not first.get("pid")):
            name = first.get("chapter_name", "").strip()
            if name and "_first_post" not in result:
                result["_first_post"] = name

    return result


def convert_thread_to_wiki(posts: List[Post], metadata: dict = None,
                            config: dict = None,
                            toc_analysis: dict = None) -> str:
    """
    将整个帖子的所有楼层转换为 Wiki 格式文本

    Args:
        posts: 楼层列表
        metadata: 帖子元数据（用于生成 Infobox）
        config: 转换配置
        toc_analysis: 外部 TOC 分析结果（来自 preanalyze + AI 分析），
                      格式: {"entries": [{"floor": int, "pid": str, "chapter_name": str}, ...]}
                      若提供则优先使用；未提供则回退到首楼 _parse_toc()。

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

    # 4. 第一轮：收集作者回复引用的原帖 pid
    import re as _re2
    cited_pids = set()  # 被作者回复引用的读者帖 pid（纯数字格式）
    pid_to_post = {}    # pid（纯数字）→ Post 映射
    author_reply_pids = {}  # {作者帖pid: [引用的读者帖pid列表]}

    for post in posts:
        # 标准化 pid：去除 "pid" 前缀，统一用纯数字做 key
        numeric_pid = post.pid.replace("pid", "") if post.pid else ""
        if numeric_pid:
            pid_to_post[numeric_pid] = post
        is_author = thread_author and post.author.strip() == thread_author.strip()
        if is_author and not post.is_first_post and '<blockquote>' in (post.content_html or ""):
            # 提取 blockquote 中引用的原帖 pid（纯数字格式）
            refs = _re2.findall(r'pid=(\d+)', post.content_html)
            if refs:
                author_reply_pids[post.pid] = refs
                for r in refs:
                    cited_pids.add(r)

    # 4.5. 解析目录（如存在），建立 pid→章节名 映射
    toc_chapters = {}  # {numeric_pid: chapter_name}
    if toc_analysis:
        # 优先使用外部 TOC 分析结果（来自 preanalyze + AI）
        toc_chapters = _parse_toc_external(toc_analysis, posts)
    elif posts and posts[0].content_html:
        # 回退到首楼自动解析
        first_wikitext = html_to_wiki(posts[0].content_html)
        toc_chapters = _parse_toc(first_wikitext)

    # 5. 第二轮：生成输出
    seen_content = set()  # 去重
    last_was_author_chapter = False  # 追踪连续作者帖
    merged_titles = []  # 收集被合并的标题，供人工复核
    for post in posts:
        is_author = thread_author and post.author.strip() == thread_author.strip()
        raw_html = post.content_html or ""
        has_blockquote = '<blockquote>' in raw_html

        # --- 作者回复读者 ---
        if is_author and not post.is_first_post and has_blockquote:
            refs = author_reply_pids.get(post.pid, [])
            qa_parts = []

            # 找到被引用的读者帖，提取原文（过滤无意义赞美/催更）
            for ref_pid in refs:
                cited_post = pid_to_post.get(ref_pid)
                if cited_post:
                    cited_text = html_to_wiki(cited_post.content_html).strip()
                    if cited_text and _should_keep_question(cited_text):
                        qa_parts.append(f"{cited_post.author}: {cited_text}")

            # 作者回复内容（blockquote 之后的部分）
            bq_end = _re2.search(r'</blockquote>', raw_html)
            if bq_end:
                reply_html = raw_html[bq_end.end():]
                reply_wiki = html_to_wiki(reply_html).strip()
                if reply_wiki:
                    qa_parts.append(reply_wiki)

            if qa_parts:
                wiki_text = "\n\n---\n\n".join(qa_parts)
                wiki_text = f"{{{{同人注释start}}}}\n{wiki_text}\n{{{{同人注释end}}}}"
                last_was_author_chapter = False  # 打断连续章节链
            else:
                continue

        # --- 作者纯内容帖 ---
        elif is_author and not post.is_first_post:
            wiki_text = convert_post(post, config)
            if not wiki_text:
                continue
            if len(wiki_text) >= 200:
                lines = wiki_text.split('\n', 1)
                first_line = lines[0].strip()
                rest = lines[1].strip() if len(lines) > 1 else ""
                # 判断是否应作为新章节
                numeric_pid = post.pid.replace("pid", "") if post.pid else ""
                toc_name = toc_chapters.get(numeric_pid, "")
                is_new_chapter = _is_chapter_start(first_line) or bool(toc_name)
                if is_new_chapter and first_line and len(first_line) < 120:
                    numeric_pid = post.pid.replace("pid", "") if post.pid else ""
                    toc_name = toc_chapters.get(numeric_pid, "")
                    # 清理标题中的加粗/斜体标记
                    clean_title = first_line.strip("'").strip()
                    if clean_title != first_line:
                        first_line = clean_title
                    # 优先使用 TOC 中的章节名（匹配 pid）
                    if toc_name:
                        wiki_text = f"== {toc_name} ==\n\n{rest}"
                    else:
                        wiki_text = f"== {first_line} ==\n\n{rest}"
                    last_was_author_chapter = True
                elif last_was_author_chapter and parts:
                    # 连续作者帖 → 合并到上一个章节末尾
                    parts[-1] = parts[-1].rstrip() + "\n\n" + wiki_text
                    merged_titles.append(first_line[:60])
                    last_was_author_chapter = True
                    continue
                else:
                    # 不是章节也不是合并 → 记录被过滤的标题
                    merged_titles.append(first_line[:60])
                    last_was_author_chapter = False
            else:
                # 短注 → 同人注释
                wiki_text = f"{{{{同人注释start}}}}\n{wiki_text}\n{{{{同人注释end}}}}"
                last_was_author_chapter = False

        # --- 首楼 ---
        elif post.is_first_post:
            wiki_text = convert_post(post, config)
            if not wiki_text:
                continue
            # 如果有 TOC：给首楼加上章节标题，并删除目录文字
            if toc_chapters:
                # 去除"目录"及其后的链接列表（非正文内容）
                toc_pos = wiki_text.find('目录')
                if toc_pos >= 0:
                    # 找到目录后第一个非链接行的位置
                    toc_end = toc_pos
                    for i, line in enumerate(wiki_text[toc_pos:].split('\n')):
                        if i > 0 and line.strip() and not line.strip().startswith('['):
                            toc_end = toc_pos + wiki_text[toc_pos:].find(line)
                            break
                    wiki_text = wiki_text[:toc_pos].rstrip() + "\n\n" + wiki_text[toc_end:].lstrip()

            if "_first_post" in toc_chapters:
                toc_name = toc_chapters["_first_post"]
                lines = wiki_text.split('\n', 1)
                body = lines[1].strip() if len(lines) > 1 else wiki_text
                wiki_text = f"== {toc_name} ==\n\n{body}"
                last_was_author_chapter = True

        # --- 读者帖：全部跳过 ---
        #   读者原帖已在作者回复 blockquote 中完整保留（含全文），
        #   同人注释由作者回复的 Q&A 块唯一承载，读者帖不单独输出。
        elif not is_author:
            continue

        # 去重
        text_normalized = wiki_text.strip()[:200]
        if text_normalized and text_normalized in seen_content:
            continue
        if len(text_normalized) > 30:
            seen_content.add(text_normalized)

        parts.append(wiki_text)

    # 5. 结束标记
    parts.append("\n{{首行缩进end}}")
    parts.append("[[分类:同人作品]]")

    result = "\n\n".join(parts)
    # 存储被合并标题 + TOC 匹配信息供 CLI 输出复核
    global last_merged_titles, _last_toc_info
    last_merged_titles = merged_titles
    _last_toc_info = toc_chapters
    return result


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
