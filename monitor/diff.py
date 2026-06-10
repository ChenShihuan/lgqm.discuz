"""
差异对比引擎 - 对比论坛帖子列表与 Wiki 文章索引，发现新帖和更新
"""
from datetime import datetime
from typing import List, Dict, Optional

from .config import get
from .models import ForumThread, WikiArticle, DiffItem, DiffReport
from .utils import log, parse_datetime, set_verbose


def detect_diffs(
    threads: List[ForumThread],
    wiki_articles: List[WikiArticle],
    tid_index: Dict[int, WikiArticle] = None,
    verbose: bool = False,
) -> DiffReport:
    """
    对比论坛帖子和 Wiki 文章，生成差异报告

    Args:
        threads: 论坛帖子列表
        wiki_articles: Wiki 文章列表
        tid_index: TID → WikiArticle 字典（可选，自动构建）
        verbose: 详细日志

    Returns:
        DiffReport 差异报告
    """
    set_verbose(verbose)

    if tid_index is None:
        tid_index = {}
        for article in wiki_articles:
            if article.forum_tid is not None:
                tid_index[article.forum_tid] = article

    report = DiffReport()
    report.scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report.summary["total_forum_threads"] = len(threads)
    report.summary["total_wiki_articles"] = len(wiki_articles)

    # 过滤置顶帖（版规等不需要收录）
    normal_threads = [t for t in threads if not t.is_sticky]

    for thread in normal_threads:
        wiki_match = tid_index.get(thread.tid)

        if wiki_match is None:
            # 论坛有新帖，Wiki 无对应文章
            item = DiffItem(
                type="new",
                forum_thread=thread,
                reason=f"新帖：论坛 TID={thread.tid} 在 Wiki 中无匹配",
            )
            report.new_items.append(item)
        else:
            # Wiki 已有收录，检查是否需要更新
            update_reason = _check_update(thread, wiki_match)
            if update_reason:
                item = DiffItem(
                    type="updated",
                    forum_thread=thread,
                    wiki_article=wiki_match,
                    reason=update_reason,
                )
                report.updated_items.append(item)

    # 反向检查：Wiki 中已收录但论坛找不到的（可能被删，或在不同域名）
    thread_tids = {t.tid for t in threads}
    for article in wiki_articles:
        if article.forum_tid and article.forum_tid not in thread_tids:
            item = DiffItem(
                type="possible_match",
                forum_thread=ForumThread(
                    tid=article.forum_tid,
                    title=article.title,
                    author=article.author,
                    author_uid=0,
                    url=article.forum_url,
                ),
                wiki_article=article,
                confidence=0.5,
                reason=f"Wiki 文章 '{article.title}' 关联的论坛帖 TID={article.forum_tid} 未在板块中找到（可能已删除或域名迁移）",
            )
            report.possible_matches.append(item)

    # 更新统计
    report.summary["new_threads"] = len(report.new_items)
    report.summary["updated_threads"] = len(report.updated_items)
    report.summary["possible_matches"] = len(report.possible_matches)

    log(f"差异分析完成：新帖 {report.summary['new_threads']}, "
        f"更新 {report.summary['updated_threads']}, "
        f"疑似 {report.summary['possible_matches']}", "SUCCESS")

    return report


def _check_update(thread: ForumThread, article: WikiArticle) -> Optional[str]:
    """
    检查一篇 Wiki 已收录的文章是否需要更新

    Returns:
        更新原因描述，或 None 表示无需更新
    """
    reasons = []

    # 1. 比较最后回复日期 vs Wiki 最近更新日期
    if thread.last_reply_date and article.last_update:
        thread_date = parse_datetime(thread.last_reply_date)
        wiki_date = parse_datetime(article.last_update)
        if thread_date and wiki_date:
            if thread_date > wiki_date:
                diff_days = (thread_date - wiki_date).days
                reasons.append(f"论坛最后回复 ({thread.last_reply_date}) 晚于 Wiki 更新 ({article.last_update})，相差 {diff_days} 天")

    # 2. 如果 Wiki 没有最近更新日期，但有论坛日期
    elif thread.last_reply_date and not article.last_update:
        reasons.append(f"Wiki 缺少最近更新日期，论坛最后回复: {thread.last_reply_date}")

    # 3. 论坛有更新但 Wiki 无记录（日期解析失败时）
    if not reasons and thread.last_reply_date:
        reasons.append(f"论坛有最近回复 ({thread.last_reply_date})，建议检查")

    return "; ".join(reasons) if reasons else None


def format_report_summary(report: DiffReport) -> str:
    """格式化差异报告摘要为可读文本"""
    lines = []
    lines.append("=" * 60)
    lines.append(f"  论坛同人监控报告 — {report.scan_time}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  论坛总帖子: {report.summary['total_forum_threads']}")
    lines.append(f"  Wiki 同人文章: {report.summary['total_wiki_articles']}")
    lines.append("")
    lines.append(f"  🆕 新帖（待导入）: {report.summary['new_threads']}")
    lines.append(f"  📝 更新帖（有新增内容）: {report.summary['updated_threads']}")
    lines.append(f"  ❓ 疑似匹配: {report.summary['possible_matches']}")
    lines.append("")

    if report.new_items:
        lines.append("─" * 60)
        lines.append(f"  🆕 新帖 ({len(report.new_items)} 条)")
        lines.append("─" * 60)
        for i, item in enumerate(report.new_items[:20], 1):
            t = item.forum_thread
            lines.append(f"  {i:>2}. [{t.tid}] {t.title[:50]}")
            lines.append(f"      作者: {t.author} | 回复: {t.reply_count} | {t.last_reply_date}")

    if report.updated_items:
        lines.append("─" * 60)
        lines.append(f"  📝 更新帖 ({len(report.updated_items)} 条)")
        lines.append("─" * 60)
        for i, item in enumerate(report.updated_items, 1):
            t = item.forum_thread
            w = item.wiki_article
            wiki_name = w.filename[:-3] if w else "?"
            lines.append(f"  {i:>2}. [{t.tid}] {t.title[:50]}")
            lines.append(f"      Wiki: {wiki_name} | 论坛更新: {t.last_reply_date}")

    if report.possible_matches:
        lines.append("─" * 60)
        lines.append(f"  ❓ 疑似匹配 ({len(report.possible_matches)} 条)")
        lines.append("─" * 60)
        for i, item in enumerate(report.possible_matches, 1):
            w = item.wiki_article
            lines.append(f"  {i:>2}. [{w.forum_tid}] {w.title[:50]} (Wiki)")
            lines.append(f"      论坛链接: {w.forum_url[:60]}")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
