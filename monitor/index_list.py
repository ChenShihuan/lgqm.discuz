"""
同人作品列表操作 — 追加新条目、更新已有条目
操作对象: lgqm.huijiwiki.com/同人作品列表.mw
"""
import re
import os
from datetime import datetime
from typing import Optional

from .config import get


def _list_path() -> str:
    """获取作品列表文件路径"""
    return os.path.join(get("wiki.repo_path"), "同人作品列表.mw")


def _read_list() -> str:
    """读取作品列表文件"""
    path = _list_path()
    if not os.path.exists(path):
        raise FileNotFoundError(f"作品列表文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_list(content: str):
    """写入作品列表文件"""
    path = _list_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def get_max_seq() -> int:
    """获取当前列表中的最大序号"""
    content = _read_list()
    # 匹配所有行首的 | 数字 ||
    seqs = re.findall(r'^\|\s*(\d+)\s*\|\|', content, re.MULTILINE)
    if seqs:
        return max(int(s) for s in seqs)
    return 0


def find_article_row(article_name: str) -> Optional[tuple]:
    """
    在列表中查找指定文章名的行。
    返回 (start_pos, end_pos, row_text) 或 None。
    """
    content = _read_list()
    # 匹配 [[文章名]]
    escaped = re.escape(article_name)
    pattern = rf'^\|\s*\d+\s*\|\|\s*\[\[{escaped}\]\].*$'
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        return None
    start = match.start()
    end = match.end()
    return (start, end, match.group(0))


def append_article(article_name: str, author: str, keywords: str = "",
                   location: str = "", first_publish: str = "",
                   last_update: str = "", status: str = "未完结",
                   canon_status: str = "待转正", word_count: str = "",
                   award: str = "") -> int:
    """
    追加新文章到作品列表。
    返回新分配的序号。

    Args:
        article_name: 文章名（用于 [[文章名]] 链接）
        author: 作者
        keywords: 内容关键词（顿号分隔）
        location: 涉及方面、地点
        first_publish: 起更时间 YYYY-MM-DD
        last_update: 最近更新 YYYY-MM-DD
        status: 完结/未完结
        canon_status: 待转正/已转正
        word_count: 字数(千字)
        award: 获得奖项（如 {{奖杯|2016|单项}}）
    """
    content = _read_list()

    # 计算新序号
    new_seq = get_max_seq() + 1

    # 构建新行
    row = _build_row(
        seq=new_seq,
        article_name=article_name,
        author=author,
        keywords=keywords,
        location=location,
        first_publish=first_publish,
        last_update=last_update,
        status=status,
        canon_status=canon_status,
        word_count=word_count,
        award=award,
    )

    # 在 |} 前插入新行，前面加 |- 行分隔符
    if "|}" in content:
        content = content.replace("|}", "|-\n" + row + "\n|}")
    else:
        content = content.rstrip() + "\n|-\n" + row + "\n|}"

    _write_list(content)
    return new_seq


def update_article(article_name: str, **fields) -> bool:
    """
    更新已有文章的字段。

    可更新字段: last_update, status, canon_status, keywords, location, word_count, award

    Returns:
        True 如果找到并更新了条目
    """
    found = find_article_row(article_name)
    if not found:
        return False

    content = _read_list()
    start, end, old_row = found

    # 解析旧行的各列
    cols = _parse_row(old_row)

    # 更新字段
    col_map = {
        "last_update": 7,       # 最近更新
        "status": 8,            # 状态
        "canon_status": 9,      # 转正状态
        "keywords": 4,          # 内容关键词
        "location": 5,          # 方面/地点
        "word_count": 10,       # 字数
        "award": 11,            # 奖项
    }

    for field, value in fields.items():
        if field in col_map and value:
            idx = col_map[field] - 1  # 0-based
            if idx < len(cols):
                cols[idx] = value

    # 重建行
    new_row = "| " + " || ".join(
        cols[i] if i < len(cols) else ""
        for i in range(11)
    )

    content = content[:start] + new_row + content[end:]
    _write_list(content)
    return True


def append_or_update(article_name: str, author: str, **fields) -> tuple:
    """
    智能操作：文章已存在则更新，不存在则追加。
    返回 (action: str, seq: int)
    """
    found = find_article_row(article_name)
    if found:
        update_article(article_name, **fields)
        return ("updated", _parse_row(found[2])[0])
    else:
        seq = append_article(article_name, author=author, **fields)
        return ("appended", seq)


def update_from_mw_file(mw_path: str) -> tuple:
    """
    从 .mw 文件解析 Infobox 字段，智能追加或更新到作品列表。
    返回 (action, seq, article_name)
    """
    if not os.path.exists(mw_path):
        raise FileNotFoundError(f".mw 文件不存在: {mw_path}")

    with open(mw_path, "r", encoding="utf-8") as f:
        content = f.read()

    fields = _parse_infobox(content)
    article_name = fields.pop("article_name", "")
    author = fields.pop("author", "")

    if not article_name:
        raise ValueError("无法从 .mw 文件中提取文章名")

    action, seq = append_or_update(article_name, author, **fields)
    return (action, seq, article_name)


def _build_row(seq: int, article_name: str, author: str, keywords: str,
               location: str, first_publish: str, last_update: str,
               status: str, canon_status: str, word_count: str,
               award: str) -> str:
    """构建表格行"""
    date = last_update or first_publish or datetime.now().strftime("%Y-%m-%d")
    return (
        f"| {seq} || [[{article_name}]] || {author} || {keywords} || "
        f"{location} || {first_publish} || {date} || "
        f"{status} || {canon_status} || {word_count} || {award}"
    )


def _parse_row(row: str) -> list:
    """解析表格行为列列表"""
    # 去掉开头的 | 和结尾的 |
    row = row.strip()
    if row.startswith("|"):
        row = row[1:].strip()
    # 按 || 分割
    cols = [c.strip() for c in row.split("||")]
    return cols


def _parse_infobox(content: str) -> dict:
    """
    从 .mw 文件的 Infobox 中提取字段。
    返回 {article_name, author, keywords, location, first_publish, last_update,
           status, canon_status, word_count}
    """
    result = {
        "article_name": "",
        "author": "",
        "keywords": "",
        "location": "",
        "first_publish": "",
        "last_update": "",
        "status": "未完结",
        "canon_status": "待转正",
        "word_count": "",
    }

    # 注意：使用 [ \t]* 避免跨行匹配；使用 [^\n]* 限制在同一行内
    H = r'[ \t]*'  # 水平空白符
    patterns = {
        "article_name": rf'\|{H}同人作品{H}={H}([^\n]*)',
        "keywords": rf'\|{H}内容关键字{H}={H}([^\n]*)',
        "first_publish": rf'\|{H}首次发布{H}=[ \t]*(?:<!--[^>]*-->)?{H}(\S+)',
        "last_update": rf'\|{H}最近更新{H}=[ \t]*(?:<!--[^>]*-->)?{H}(\S+)',
        "status": rf'\|{H}完结情况{H}=[ \t]*(?:<!--[^>]*-->)?{H}([^\n]*)',
        "canon_status": rf'\|{H}转正状态{H}=[ \t]*(?:<!--[^>]*-->)?{H}([^\n]*)',
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, content)
        if match:
            raw = match.group(1).strip()
            # 去除 HTML 注释
            raw = re.sub(r'<!--.*?-->', '', raw).strip()
            if raw:
                result[key] = raw

    # 作者：从 官方论坛 字段提取
    author_match = re.search(rf'\|{H}官方论坛{H}=[ \t]*(?:<!--[^>]*-->)?{H}(\S+)', content)
    if author_match:
        raw = author_match.group(1).strip()
        raw = re.sub(r'<!--.*?-->', '', raw).strip()
        if raw:
            result["author"] = raw

    # 地点 + 涉及方面合并为 location
    loc_match = re.search(rf'\|{H}地点{H}={H}([^\n]*)', content)
    aspect_match = re.search(rf'\|{H}涉及方面{H}=[ \t]*(?:<!--[^>]*-->)?{H}([^\n]*)', content)
    location_parts = []
    if loc_match:
        raw = loc_match.group(1).strip()
        raw = re.sub(r'<!--.*?-->', '', raw).strip()
        if raw:
            location_parts.append(raw)
    if aspect_match:
        raw = aspect_match.group(1).strip()
        raw = re.sub(r'<!--.*?-->', '', raw).strip()
        if raw:
            location_parts.append(raw)
    result["location"] = "、".join(location_parts)

    # 清理 article_name（去除 {{PAGENAME}} 占位符）
    if result["article_name"] == "{{PAGENAME}}":
        result["article_name"] = ""

    return result


# ---------------------------------------------------------------------------
# 列表序号校正
# ---------------------------------------------------------------------------

_MULTI_PART_PATTERN = re.compile(r'[（(]\s*[一二三四五六七八九十\d]+[）)]')


def _strip_part_suffix(name: str) -> str:
    """去除分卷后缀，如 临高启明外传（二） → 临高启明外传"""
    return _MULTI_PART_PATTERN.sub('', name).strip()


def renumber_list(dry_run: bool = False) -> dict:
    """
    校正作品列表中所有序号，返回统计信息。

    规则：
    - 所有条目从 1 开始顺序编号
    - 同一文章的分卷条目（如 外传（二）~（七））共享同一序号
    - 序号 0 → 修正为 1

    Returns:
        {total, changed, issues_fixed}
    """
    content = _read_list()

    # 匹配表格行：| 序号 || [[作品名]] || ...
    row_pattern = re.compile(r'^(\|\s*)\d+(\s*\|\|.*)$', re.MULTILINE)

    rows = []
    for m in row_pattern.finditer(content):
        rows.append({
            "start": m.start(),
            "end": m.end(),
            "prefix": m.group(1),
            "suffix": m.group(2),
            "old_seq": int(re.search(r'\d+', m.group(0)).group()),
            "name": re.search(r'\[\[([^\]]+)\]\]', m.group(2)).group(1) if ']]' in m.group(2) else '',
        })

    if not rows:
        return {"total": 0, "changed": 0, "issues_fixed": 0}

    # 重新编号
    new_content = content
    seq = 0
    prev_base = ""
    changed = 0
    issues = 0

    for i, row in enumerate(rows):
        current_base = _strip_part_suffix(row["name"])
        is_multi_part = (i > 0 and current_base == prev_base and
                         current_base != row["name"])

        new_seq = seq
        if is_multi_part:
            issues += 1

        # 决定下一行是否需要递增 seq
        should_increment = True
        if i < len(rows) - 1:
            next_base = _strip_part_suffix(rows[i + 1]["name"])
            next_name = rows[i + 1]["name"]
            if next_base == current_base and next_base != next_name:
                should_increment = False  # 下一行是分卷，不递增
        if should_increment:
            seq += 1

        if new_seq != row["old_seq"]:
            old_text = content[row["start"]:row["end"]]
            new_text = f'{row["prefix"]}{new_seq}{row["suffix"]}'
            new_content = new_content.replace(old_text, new_text, 1)
            changed += 1

        prev_base = current_base

    if not dry_run:
        _write_list(new_content)

    return {
        "total": len(rows),
        "changed": changed,
        "issues_fixed": issues,
    }
