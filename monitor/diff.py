"""
差异对比引擎 - 对比论坛帖子列表与 Wiki 文章索引，发现新帖和更新
"""
import re
from datetime import datetime
from typing import List, Dict, Optional

from .config import get
from .models import ForumThread, WikiArticle, DiffItem, DiffReport
from .utils import log, parse_datetime, set_verbose, normalize_title
from .session import get_forum_session, BASE_URL


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


def verify_tid(tid: int, timeout: int = 10, use_auth: bool = True,
               forum_url: str = None) -> tuple:
    """
    通过 Archiver / thread URL / article URL 验证 TID 是否可访问。

    Discuz 有两种内容格式：
    - thread-X-Y.html：论坛帖子（同人板块 forum-39 为主）
    - article-X-Y.html：论坛文章（其他板块，如「原创基地」）

    Args:
        tid: 帖子/文章 ID
        timeout: 请求超时秒数
        use_auth: Archiver 不可达时是否尝试 cookie 认证访问
        forum_url: Wiki 中记录的完整论坛 URL（用于检测 article 格式）

    Returns:
        (accessible: bool, source: str)
        source 取值: "thread" (论坛帖子), "article" (论坛文章), "" (不可访问)
        注意：返回 True 仅表示页面可访问（含 JS 挑战保护的情况），
        不保证能解析出正文内容。JS 挑战页面表示帖子确实存在，
        只是需要浏览器执行 JS 后方可查看内容。
    """
    import time as _time
    fs = get_forum_session()

    # 检测是否为 article 格式
    is_article_fmt = bool(forum_url and 'article-' in forum_url)

    # article 格式：直接访问完整 URL 验证（article 页面无需 cookie 即可访问）
    if is_article_fmt:
        had_js_challenge = False
        for attempt in range(3):
            try:
                resp = fs.get(forum_url, referer=f"{BASE_URL}/", timeout=timeout)
                if resp.status_code == 200:
                    if fs.is_js_challenge(resp.text):
                        # JS 挑战 → 帖子存在，只是需要浏览器执行 JS
                        had_js_challenge = True
                        if attempt < 2:
                            _time.sleep(2)
                        continue
                    # 页面正常返回
                    if "提示信息" not in resp.text and "未定义操作" not in resp.text:
                        if len(resp.text) > 500:
                            return True, "article"
                    return False, ""
                if attempt < 2:
                    _time.sleep(2)
            except Exception:
                if attempt < 2:
                    _time.sleep(2)
        # 重试用尽：如果是 JS 挑战，判为有条件可访问
        if had_js_challenge:
            return True, "article"
        return False, ""

    # 以下仅处理 thread 格式

    # 优先尝试 Archiver（公开板块，轻量）
    had_js_challenge = False
    for attempt in range(3):
        archiver_url = f"https://lgqmonline.top/archiver/?tid-{tid}.html"
        try:
            resp = fs.get(archiver_url, referer=f"{BASE_URL}/", timeout=timeout)
            if resp.status_code == 200:
                if fs.is_js_challenge(resp.text):
                    had_js_challenge = True
                    if attempt < 2:
                        _time.sleep(2)
                    continue
                if 'class="author"' in resp.text or "class='author'" in resp.text:
                    return True, "thread"
                # Archiver 正常返回但没有作者 → 页面存在但内容受限
                # 继续，不急于判定
        except Exception:
            if attempt < 2:
                _time.sleep(2)

    # Archiver 不可达或内容受限，尝试用 cookie 访问 thread 页面
    if use_auth:
        had_thread_js_challenge = False
        for attempt in range(3):
            thread_url = f"https://lgqmonline.top/thread-{tid}-1-1.html"
            try:
                resp = fs.get(thread_url, referer=f"{BASE_URL}/forum-39-1.html", timeout=timeout)
                if resp.status_code == 200:
                    if fs.is_js_challenge(resp.text):
                        had_thread_js_challenge = True
                        if attempt < 2:
                            _time.sleep(2)
                        continue
                    # 有作者信息或有帖子内容 → 可访问
                    if ('class="author"' in resp.text or "class='author'" in resp.text or
                            'class="authi"' in resp.text or 'class="pi"' in resp.text):
                        return True, "thread"
                    # 是"提示信息"页面且无帖子内容 → 不可访问
                    if "提示信息" in resp.text or "未定义操作" in resp.text:
                        return False, ""
                    # 非提示信息页面 → 也算可访问
                    if "提示信息" not in resp.text:
                        return True, "thread"
                if attempt < 2:
                    _time.sleep(2)
            except Exception:
                if attempt < 2:
                    _time.sleep(2)

        # 重试用尽：如果 consistently 遇到 JS 挑战，说明帖子存在但受保护
        if had_thread_js_challenge:
            return True, "thread"

    return False, ""


def verify_possible_matches(report: DiffReport, verbose: bool = False) -> DiffReport:
    """
    对 possible_matches 中的每个 TID 验证可访问性。

    支持两种 Discuz 内容格式：
    - thread-X-Y.html：论坛帖子（其他板块）
    - article-X-Y.html：论坛文章（其他板块的文章系统）

    分类与重归类：
    - 公开可访问（thread）→ 自动确认，归入「论坛其他板块」
    - 公开可访问（article）→ 自动确认，归入「论坛其他板块（文章）」
    - 需登录可访问 → 自动确认
    - 不可访问 → 留在 possible_matches，允许人工确认
    """
    from .auth import get_cookie

    accessible_thread = 0   # thread 格式，其他板块
    accessible_article = 0  # article 格式，其他板块文章
    accessible_auth = 0     # 需登录
    inaccessible = 0
    has_auth = bool(get_cookie())

    confirmed = []
    still_possible = []

    for item in report.possible_matches:
        w = item.wiki_article
        tid = w.forum_tid if w else item.forum_thread.tid
        forum_url = w.forum_url if w else ""
        if tid is None:
            item.verified = False
            item.reason = f"不可访问：缺少 TID 信息"
            inaccessible += 1
            still_possible.append(item)
            continue

        # 传递 forum_url 以支持 article 格式检测
        ok, source = verify_tid(tid, use_auth=False, forum_url=forum_url)
        if ok:
            item.verified = True
            item.type = "confirmed_match"
            if source == "article":
                accessible_article += 1
                item.reason = f"已确认：TID={tid} 为论坛文章（article 格式），位于其他板块"
            else:
                accessible_thread += 1
                item.reason = f"已确认：TID={tid} 为论坛帖子（thread 格式），位于其他板块"
            confirmed.append(item)
        elif has_auth:
            ok_auth, source_auth = verify_tid(tid, use_auth=True, forum_url=forum_url)
            if ok_auth:
                item.verified = True
                accessible_auth += 1
                item.type = "confirmed_match"
                src_label = "文章" if source_auth == "article" else "帖子"
                item.reason = f"已确认：TID={tid} 位于非公开板块（{src_label}），需登录后访问"
                confirmed.append(item)
            else:
                item.verified = False
                inaccessible += 1
                fmt_label = "文章" if ('article-' in forum_url) else "帖子"
                item.reason = f"不可访问：TID={tid} 无法访问（{fmt_label}格式，可能已删除，或需人工确认）"
                still_possible.append(item)
        else:
            item.verified = False
            inaccessible += 1
            fmt_label = "文章" if ('article-' in forum_url) else "帖子"
            item.reason = f"不可访问：TID={tid} 无法访问（{fmt_label}格式，未配置 cookie，可能位于非公开板块，或需人工确认）"
            still_possible.append(item)

        if verbose:
            if item.verified:
                tag = "🔒" if "非公开" in item.reason else "✅"
                src = "article" if "文章" in item.reason else "thread"
                log(f"  {tag} TID={tid:>5} {w.title[:40] if w else ''} → 已确认 ({src})", "INFO")
            else:
                log(f"  ❌ TID={tid:>5} {w.title[:40] if w else ''}", "INFO")

    # 重归类：可访问的移入 confirmed_matches，不可访问的留在 possible_matches
    report.confirmed_matches = confirmed
    report.possible_matches = still_possible

    report.summary["confirmed_matches"] = len(confirmed)
    report.summary["possible_matches"] = len(still_possible)
    report.summary["verified_accessible"] = accessible_thread + accessible_article + accessible_auth
    report.summary["verified_accessible_thread"] = accessible_thread
    report.summary["verified_accessible_article"] = accessible_article
    report.summary["verified_accessible_auth"] = accessible_auth
    report.summary["verified_inaccessible"] = inaccessible

    if verbose:
        parts = [f"其他板块帖子 {accessible_thread}"]
        if accessible_article:
            parts.append(f"其他板块文章 {accessible_article}")
        if accessible_auth:
            parts.append(f"需登录 {accessible_auth}")
        parts.append(f"不可访问 {inaccessible}")
        log(f"验证完成：{', '.join(parts)}（其中 {len(confirmed)} 已自动确认为匹配）", "SUCCESS")

    return report


def confirm_match_manually(report: DiffReport, tid: int) -> bool:
    """
    人工确认一个 possible_match 为有效匹配，移入 confirmed_matches。

    Args:
        report: 差异报告
        tid: 要确认的帖子 TID

    Returns:
        True 成功, False 未找到匹配项
    """
    for i, item in enumerate(report.possible_matches):
        item_tid = item.wiki_article.forum_tid if item.wiki_article else item.forum_thread.tid
        if item_tid == tid:
            item.type = "confirmed_match"
            item.verified = True
            item.reason = f"人工确认：TID={tid} 经手动验证为有效匹配"
            report.confirmed_matches.append(item)
            report.possible_matches.pop(i)
            # 更新统计
            report.summary["confirmed_matches"] = len(report.confirmed_matches)
            report.summary["possible_matches"] = len(report.possible_matches)
            report.summary["verified_accessible"] = report.summary.get("verified_accessible", 0) + 1
            report.summary["verified_inaccessible"] = max(0, report.summary.get("verified_inaccessible", 0) - 1)
            log(f"✅ TID={tid} 已人工确认为有效匹配", "SUCCESS")
            return True

    # 可能已经在 confirmed_matches 中
    for item in report.confirmed_matches:
        item_tid = item.wiki_article.forum_tid if item.wiki_article else item.forum_thread.tid
        if item_tid == tid:
            log(f"⚠️  TID={tid} 已在已确认匹配列表中", "WARN")
            return True

    log(f"❌ 未在疑似匹配中找到 TID={tid}", "ERROR")
    return False


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
    lines.append(f"  论坛同人板块 (forum-39): {report.summary['total_forum_threads']} 条帖子")
    lines.append(f"  论坛其他板块 (已验证): {report.summary.get('confirmed_matches', 0)} 条"
                 f"（帖子 {report.summary.get('verified_accessible_thread', 0)} + 文章 {report.summary.get('verified_accessible_article', 0)}"
                 f" + 需登录 {report.summary.get('verified_accessible_auth', 0)}）")
    lines.append(f"  Wiki 同人文章: {report.summary['total_wiki_articles']}")
    lines.append("")
    lines.append(f"  🆕 新帖（待导入）: {report.summary['new_threads']}")
    lines.append(f"  📝 更新帖（有新增内容）: {report.summary['updated_threads']}")
    lines.append(f"  ❓ 疑似匹配（待人工确认）: {report.summary['possible_matches']}"
                 f" (不可访问 {report.summary.get('verified_inaccessible', 0)})")
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

    if report.confirmed_matches:
        # 分组：其他板块帖子 / 其他板块文章 / 需登录
        confirmed_thread = [item for item in report.confirmed_matches
                           if "文章" not in item.reason and "非公开" not in item.reason]
        confirmed_article = [item for item in report.confirmed_matches
                            if "文章" in item.reason and "非公开" not in item.reason]
        confirmed_auth = [item for item in report.confirmed_matches
                         if "非公开" in item.reason]

        if confirmed_thread:
            lines.append("─" * 60)
            lines.append(f"  ✅ 论坛其他板块 — 帖子 ({len(confirmed_thread)} 条) — Wiki↔论坛关联已验证")
            lines.append("─" * 60)
            for i, item in enumerate(confirmed_thread, 1):
                w = item.wiki_article
                lines.append(f"  {i:>2}. [{w.forum_tid}] {w.title[:45]}")
                lines.append(f"      {w.forum_url[:70]}")

        if confirmed_article:
            lines.append("─" * 60)
            lines.append(f"  📄 论坛其他板块 — 文章 ({len(confirmed_article)} 条) — Wiki↔论坛关联已验证")
            lines.append("─" * 60)
            for i, item in enumerate(confirmed_article, 1):
                w = item.wiki_article
                lines.append(f"  {i:>2}. [{w.forum_tid}] {w.title[:45]}")
                lines.append(f"      {w.forum_url[:70]}")

        if confirmed_auth:
            lines.append("─" * 60)
            lines.append(f"  🔒 已确认匹配 — 需登录可访问 ({len(confirmed_auth)} 条)")
            lines.append("─" * 60)
            for i, item in enumerate(confirmed_auth, 1):
                w = item.wiki_article
                lines.append(f"  {i:>2}. [{w.forum_tid}] {w.title[:45]}")
                lines.append(f"      {w.forum_url[:70]}")

    if report.possible_matches:
        lines.append("─" * 60)
        lines.append(f"  ❓ 待人工确认 ({len(report.possible_matches)} 条) — 自动验证不可访问")
        lines.append("─" * 60)
        for i, item in enumerate(report.possible_matches, 1):
            w = item.wiki_article
            lines.append(f"  {i:>2}. [{w.forum_tid}] {w.title[:45]}")
            lines.append(f"      {w.forum_url[:70]}")
        lines.append("")
        lines.append(f"  💡 提示：可手动访问以上链接确认是否有效。")
        lines.append(f"     若确认有效，执行: python3 -m monitor.cli confirm-match <TID>")
        lines.append(f"     若确认失效，可在 Wiki 中清理该文章的论坛链接。")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
