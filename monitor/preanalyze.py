"""
预分析模块 — 快速拉取前几层楼，格式化为可读文本供 AI 分析目录结构。

不含 AI 逻辑。语义分析由 import-article skill（Claude）完成。
"""
import os
import json
from typing import Optional, List

from .config import tid_base_dir, tid_text_dir
from .utils import log, clean_article_name


def format_posts_for_analysis(posts, max_floors: int = 10) -> str:
    """
    将帖子列表转为可读文本，供 AI 分析目录结构。

    每个楼层标记：楼层号、作者、PID
    正文使用 html_to_wiki() 转换，超长帖截断。
    """
    from .converter import html_to_wiki

    lines = []
    for post in posts[:max_floors]:
        lines.append("=" * 60)
        marker = ">>> 首楼 (OP) <<<" if post.is_first_post else ""
        lines.append(
            f"第 {post.floor} 楼 | 作者: {post.author} | PID: {post.pid} {marker}"
        )
        lines.append("=" * 60)

        wiki_text = html_to_wiki(post.content_html)
        # 截断超长帖（目录分析只需前 3000 字）
        if len(wiki_text) > 3000:
            wiki_text = wiki_text[:3000] + "\n\n[... 后续内容已截断 ...]"
        lines.append(wiki_text)
        lines.append("")

    return "\n".join(lines)


def run_preanalysis(tid: int) -> dict:
    """
    预分析入口：拉取前几层楼 → 转换 → 保存为 pre_analysis.txt。

    Returns:
        {"text_path": str, "toc_path": str, "article_name": str,
         "thread_title": str, "floor_count": int}
        或 {"error": str}
    """
    from .fetcher import fetch_thread, get_thread_title

    # 拉取前 5 层楼（前两楼必定包含，多取几层以防目录在稍后位置）
    posts = fetch_thread(tid, verbose=True, max_floors=5)

    if not posts:
        return {"error": f"无法拉取 TID={tid} 的任何楼层"}

    # 提取标题
    thread_title = get_thread_title(tid) or f"TID-{tid}"
    article_name = clean_article_name(thread_title)

    # 格式化
    text = format_posts_for_analysis(posts)

    # 输出目录
    base_dir = tid_base_dir(tid, article_name)
    os.makedirs(base_dir, exist_ok=True)

    text_path = os.path.join(base_dir, "pre_analysis.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text)

    toc_path = os.path.join(base_dir, "toc_analysis.json")

    log(f"预分析文本已保存: {text_path}", "SUCCESS")
    log(f"共 {len(posts)} 层楼", "INFO")

    return {
        "text_path": text_path,
        "toc_path": toc_path,
        "article_name": article_name,
        "thread_title": thread_title,
        "floor_count": len(posts),
    }


def load_toc_analysis(filepath: str) -> dict:
    """加载 AI 写入的 toc_analysis.json。失败返回 {}（回退默认行为）。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "entries" in data:
            return data
        log(f"TOC 文件格式无效（缺少 entries），忽略", "WARN")
        return {}
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        log(f"TOC 文件 JSON 解析失败: {e}", "WARN")
        return {}
