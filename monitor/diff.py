"""
差异对比引擎 - 对比论坛帖子列表与 Wiki 文章索引，发现新帖和更新
"""
import re
import requests
from datetime import datetime
from typing import List, Dict, Optional

from .config import get
from .models import ForumThread, WikiArticle, DiffItem, DiffReport
from .utils import log, parse_datetime, set_verbose, normalize_title


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
            tids = article.forum_tids if article.forum_tids else []
            if article.forum_tid is not None and article.forum_tid not in tids:
                tids.append(article.forum_tid)
            for tid in tids:
                if tid not in tid_index:
                    tid_index[tid] = article

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


def verify_tid(tid: int, timeout: int = 10, use_auth: bool = True) -> bool:
    """
    通过 Archiver 验证 TID 是否可访问。
    公开板块用 Archiver 即可；非公开板块需要用 thread URL + cookie 验证。

    Args:
        tid: 帖子ID
        timeout: 请求超时秒数
        use_auth: Archiver 不可达时是否尝试 cookie 认证访问

    Returns:
        True 可访问, False 不可访问
    """
    from .auth import get_cookie

    # 优先尝试 Archiver（公开板块，无需 cookie）
    archiver_url = f"https://lgqmonline.top/archiver/?tid-{tid}.html"
    try:
        resp = requests.get(
            archiver_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code == 200:
            if 'class="author"' in resp.text or "class='author'" in resp.text:
                return True
    except Exception:
        pass

    # Archiver 不可达，尝试用 cookie 访问 thread 页面（非公开板块）
    if use_auth:
        thread_url = f"https://lgqmonline.top/thread-{tid}-1-1.html"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        cookie = get_cookie()
        if cookie:
            headers["Cookie"] = cookie
        try:
            resp = requests.get(
                thread_url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
            )
            if resp.status_code == 200:
                # 有作者信息或有帖子内容 → 可访问
                if ('class="author"' in resp.text or "class='author'" in resp.text or
                        'class="authi"' in resp.text or 'class="pi"' in resp.text):
                    return True
                # 是"提示信息"页面且无帖子内容 → 不可访问
                if "提示信息" in resp.text or "未定义操作" in resp.text:
                    return False
                # 非提示信息页面（可能是板块列表重定向等）→ 也算可访问
                if "提示信息" not in resp.text:
                    return True
        except Exception:
            pass

    return False


def verify_possible_matches(report: DiffReport, verbose: bool = False) -> DiffReport:
    """
    对 possible_matches 中的每个 TID 验证可访问性。
    先通过公开 Archiver，不可达时用 cookie 尝试 thread URL。

    分类：
    - 公开可访问 → verified=True, 纳入追踪
    - 需登录可访问 → verified=True, reason 中注明"非公开板块"
    - 不可访问 → verified=False, 标记为疑似失效
    """
    from .auth import get_cookie

    accessible_public = 0
    accessible_auth = 0
    inaccessible = 0
    has_auth = bool(get_cookie())

    for item in report.possible_matches:
        tid = item.wiki_article.forum_tid if item.wiki_article else item.forum_thread.tid
        if tid is None:
            item.verified = False
            inaccessible += 1
            continue

        # 先尝试公开 Archiver
        ok = verify_tid(tid, use_auth=False)
        if ok:
            item.verified = True
            accessible_public += 1
            item.reason = f"可访问：TID={tid} 可通过公开 Archiver 访问"
        elif has_auth:
            # 公开不可达，用 cookie 尝试
            ok_auth = verify_tid(tid, use_auth=True)
            if ok_auth:
                item.verified = True
                accessible_auth += 1
                item.reason = f"可访问：TID={tid} 位于非公开板块，需登录后访问"
            else:
                item.verified = False
                inaccessible += 1
                item.reason = f"不可访问：TID={tid} 无法访问（可能已删除）"
        else:
            item.verified = False
            inaccessible += 1
            item.reason = f"不可访问：TID={tid} 无法通过公开 Archiver 访问（未配置 cookie，可能位于非公开板块）"

        if verbose:
            if item.verified:
                tag = "🔒" if accessible_auth > 0 and item.reason.startswith("可访问：") and "非公开" in item.reason else "✅"
            else:
                tag = "❌"
            log(f"  {tag} TID={tid:>5} {item.wiki_article.title[:40] if item.wiki_article else ''}", "INFO")

    report.summary["verified_accessible"] = accessible_public + accessible_auth
    report.summary["verified_accessible_public"] = accessible_public
    report.summary["verified_accessible_auth"] = accessible_auth
    report.summary["verified_inaccessible"] = inaccessible

    if verbose:
        parts = [f"公开 {accessible_public}"]
        if accessible_auth:
            parts.append(f"需登录 {accessible_auth}")
        parts.append(f"不可访问 {inaccessible}")
        log(f"验证完成：{', '.join(parts)}", "SUCCESS")

    return report


def title_match_articles(
    threads: List[ForumThread],
    wiki_articles: List[WikiArticle],
    verbose: bool = False,
) -> List[dict]:
    """
    基于标准化标题匹配论坛帖子与 Wiki 文章。
    用于发现搬运文章（早期发布于其他渠道，论坛上线后搬运，标题一致）。

    匹配条件：
    - Wiki 文章的 forum_tid 为 None（尚未关联论坛帖）
    - 论坛帖与 Wiki 文章的 normalize_title 后完全相同

    Returns:
        [{forum_thread, wiki_article, forum_title_norm, wiki_title_norm}]
    """
    set_verbose(verbose)

    # 筛选未关联论坛的 Wiki 文章
    orphan_articles = [a for a in wiki_articles if a.forum_tid is None]
    log(f"标题匹配：Wiki 未关联文章 {len(orphan_articles)} 篇，论坛帖 {len(threads)} 篇", "INFO")

    # 构建标准化 Wiki 标题索引
    wiki_by_title: Dict[str, List[WikiArticle]] = {}
    for article in orphan_articles:
        norm = normalize_title(article.title)
        if norm:
            wiki_by_title.setdefault(norm, []).append(article)

    # 标准化论坛标题并匹配
    matches = []
    for thread in threads:
        norm = normalize_title(thread.title)
        if not norm:
            continue
        candidates = wiki_by_title.get(norm, [])
        for article in candidates:
            matches.append({
                "forum_thread": thread,
                "wiki_article": article,
                "forum_title_norm": norm,
                "wiki_title_norm": normalize_title(article.title),
            })

    log(f"标题匹配完成：发现 {len(matches)} 组搬运文章", "SUCCESS" if matches else "INFO")
    return matches


def apply_title_matches(
    matches: List[dict],
    wiki_repo_path: str = None,
    data_dir: str = None,
    dry_run: bool = False,
) -> dict:
    """
    将标题匹配结果应用：更新 .mw Infobox 和 wiki_index

    Args:
        matches: title_match_articles 的返回值
        wiki_repo_path: Wiki 仓库路径
        data_dir: data 目录路径
        dry_run: 仅预览

    Returns:
        {total, updated_mw, updated_index}
    """
    import os as _os
    import json as _json

    if wiki_repo_path is None:
        wiki_repo_path = get("wiki.repo_path")
    if data_dir is None:
        data_dir = get("output.data_dir")

    updated_mw = 0
    updated_index = 0

    # 读取现有 wiki_index
    index_path = _os.path.join(data_dir, "wiki_index.json")
    wiki_index = {}
    if _os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            wiki_index = _json.load(f)

    articles_list = wiki_index.get("articles", [])
    articles_by_filename = {a.get("filename", ""): a for a in articles_list}

    for m in matches:
        thread = m["forum_thread"]
        article = m["wiki_article"]
        forum_url = thread.url or f"https://lgqmonline.top/thread-{thread.tid}-1-1.html"
        forum_link = f"[{forum_url} {thread.title}]"

        # 更新 .mw 文件 Infobox
        mw_path = _os.path.join(wiki_repo_path, article.filename)
        if _os.path.exists(mw_path):
            with open(mw_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 检查是否已有 forum_url
            if article.forum_url:
                log(f"  跳过 {article.filename}: 已有论坛链接", "WARN")
                continue

            # 在 官坛原帖 字段填入
            new_content = content
            if "| 官坛原帖 =" in content or "| 官坛原帖=" in content:
                new_content = re.sub(
                    r'\| 官坛原帖\s*=.*',
                    f'| 官坛原帖 = {forum_link}',
                    content
                )
            elif "| 首次发布" in content:
                # 字段不存在，插入在「首次发布」之前
                new_content = content.replace(
                    "| 首次发布",
                    f"| 官方论坛 = {article.author}\n| 官坛原帖 = {forum_link}\n| 首次发布"
                )
            elif "| 最近更新" in content:
                new_content = content.replace(
                    "| 最近更新",
                    f"| 官方论坛 = {article.author}\n| 官坛原帖 = {forum_link}\n| 最近更新"
                )
            else:
                log(f"  ⚠️ {article.filename}: 无法定位插入点", "WARN")
                continue

            if not dry_run:
                with open(mw_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
            updated_mw += 1
            log(f"  ✅ {article.filename} → {forum_url}", "INFO")

            # 更新 wiki_index 内存中的条目
            if article.filename in articles_by_filename:
                articles_by_filename[article.filename]["forum_url"] = forum_url
                articles_by_filename[article.filename]["forum_tid"] = thread.tid
                updated_index += 1

    # 写回 wiki_index
    if updated_index > 0 and not dry_run:
        wiki_index["articles"] = list(articles_by_filename.values())
        wiki_index["total"] = len(wiki_index["articles"])
        with open(index_path, "w", encoding="utf-8") as f:
            _json.dump(wiki_index, f, ensure_ascii=False, indent=2)

    return {
        "total": len(matches),
        "updated_mw": updated_mw,
        "updated_index": updated_index,
    }


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
    lines.append(f"  ❓ 疑似匹配: {report.summary['possible_matches']}"
                 f" (公开 {report.summary.get('verified_accessible_public', 0)},"
                 f" 需登录 {report.summary.get('verified_accessible_auth', 0)},"
                 f" 不可访问 {report.summary.get('verified_inaccessible', 0)})")
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
        # 分组：公开可访问 / 需登录可访问 / 不可访问 / 未验证
        verified_public = [item for item in report.possible_matches
                          if item.verified is True and "非公开" not in item.reason]
        verified_auth = [item for item in report.possible_matches
                        if item.verified is True and "非公开" in item.reason]
        verified_fail = [item for item in report.possible_matches if item.verified is False]
        unverified = [item for item in report.possible_matches if item.verified is None]

        if verified_public:
            lines.append("─" * 60)
            lines.append(f"  ✅ 公开可访问 ({len(verified_public)} 条) — 在其他板块，可纳入追踪")
            lines.append("─" * 60)
            for i, item in enumerate(verified_public, 1):
                w = item.wiki_article
                lines.append(f"  {i:>2}. [{w.forum_tid}] {w.title[:45]}")
                lines.append(f"      {w.forum_url[:70]}")

        if verified_auth:
            lines.append("─" * 60)
            lines.append(f"  🔒 需登录可访问 ({len(verified_auth)} 条) — 位于非公开板块")
            lines.append("─" * 60)
            for i, item in enumerate(verified_auth, 1):
                w = item.wiki_article
                lines.append(f"  {i:>2}. [{w.forum_tid}] {w.title[:45]}")
                lines.append(f"      {w.forum_url[:70]}")

        if verified_fail:
            lines.append("─" * 60)
            lines.append(f"  ❌ 不可访问 ({len(verified_fail)} 条) — 可能已删除")
            lines.append("─" * 60)
            for i, item in enumerate(verified_fail, 1):
                w = item.wiki_article
                lines.append(f"  {i:>2}. [{w.forum_tid}] {w.title[:45]}")
                lines.append(f"      {w.forum_url[:70]}")

        if unverified:
            lines.append("─" * 60)
            lines.append(f"  ❓ 未验证 ({len(unverified)} 条)")
            lines.append("─" * 60)
            for i, item in enumerate(unverified, 1):
                w = item.wiki_article
                lines.append(f"  {i:>2}. [{w.forum_tid}] {w.title[:45]} (Wiki)")
                lines.append(f"      论坛链接: {w.forum_url[:60]}")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
