"""
WebUI API 路由模块
"""
import json
import os
import re

# 新帖分类规则：标题标签含"原创"的为标准文章
_ORIGINAL_PATTERN = re.compile(r'^[【\[「〈][^】\]」〉]*原创[^】\]」〉]*[】\]」〉]')


def _skip_path(data_dir: str) -> str:
    return os.path.join(data_dir, "skipped.json")


def _load_skipped(data_dir: str) -> dict:
    """加载跳过列表，返回 {tids: set, records: {tid: {title, skipped_at}}}"""
    path = _skip_path(data_dir)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                "tids": set(data.get("tids", [])),
                "records": data.get("records", {}),
            }
    return {"tids": set(), "records": {}}


def _save_skipped(data_dir: str, skipped: dict):
    path = _skip_path(data_dir)
    data = {
        "tids": sorted(list(skipped["tids"])),
        "records": skipped["records"],
        "updated_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def router(method: str, path: str, report_path: str, data_dir: str) -> tuple:
    """API 路由分发，返回 (status_code, data_dict)"""
    # GET /api/report
    if method == "GET" and path == "/api/report":
        return _get_report(report_path, data_dir)

    # GET /api/skipped
    if method == "GET" and path == "/api/skipped":
        s = _load_skipped(data_dir)
        return 200, {"tids": sorted(list(s["tids"])), "records": s["records"]}

    # POST /api/skipped/<tid>
    if method == "POST" and path.startswith("/api/skipped/"):
        tid = int(path.rsplit("/", 1)[-1])
        return _add_skipped(data_dir, tid)

    # DELETE /api/skipped/<tid>
    if method == "DELETE" and path.startswith("/api/skipped/"):
        tid = int(path.rsplit("/", 1)[-1])
        return _remove_skipped(data_dir, tid)

    # POST /api/scan
    if method == "POST" and path == "/api/scan":
        return _run_scan(report_path, data_dir)

    # POST /api/import/<tid>
    if method == "POST" and path.startswith("/api/import/"):
        tid = int(path.rsplit("/", 1)[-1])
        return _run_import(tid)

    return 404, {"error": f"未知端点: {method} {path}"}


def _get_report(report_path: str, data_dir: str) -> tuple:
    """返回 diff_report.json（含新帖分类 + 跳过标记）"""
    if not os.path.exists(report_path):
        return 404, {"error": "报告文件不存在，请先执行监控扫描"}
    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    skipped = _load_skipped(data_dir)
    skip_tids = skipped["tids"]

    # 为新帖添加分类 + 跳过标记
    standard_count = 0
    other_count = 0
    for item in data.get("new_items", []):
        tid = item["forum_thread"]["tid"]
        title = item["forum_thread"]["title"]
        if _ORIGINAL_PATTERN.match(title):
            item["category"] = "standard"
            standard_count += 1
        else:
            item["category"] = "other"
            other_count += 1
        item["skipped"] = tid in skip_tids

    # 更新帖也标记跳过
    for item in data.get("updated_items", []):
        item["skipped"] = item["forum_thread"]["tid"] in skip_tids

    data["summary"]["new_standard"] = standard_count
    data["summary"]["new_other"] = other_count
    data["summary"]["skipped_count"] = len(skip_tids)
    data["skipped_tids"] = sorted(list(skip_tids))

    return 200, data


def _add_skipped(data_dir: str, tid: int) -> tuple:
    """将 TID 加入跳过列表"""
    skipped = _load_skipped(data_dir)
    if tid in skipped["tids"]:
        return 200, {"message": f"TID={tid} 已在跳过列表中", "tids": sorted(list(skipped["tids"]))}
    skipped["tids"].add(tid)
    skipped["records"][str(tid)] = {
        "skipped_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_skipped(data_dir, skipped)
    return 200, {"message": f"已跳过 TID={tid}", "tids": sorted(list(skipped["tids"]))}


def _remove_skipped(data_dir: str, tid: int) -> tuple:
    """从跳过列表中移除 TID"""
    skipped = _load_skipped(data_dir)
    skipped["tids"].discard(tid)
    skipped["records"].pop(str(tid), None)
    _save_skipped(data_dir, skipped)
    return 200, {"message": f"已恢复 TID={tid}", "tids": sorted(list(skipped["tids"]))}


def _run_scan(report_path: str, data_dir: str) -> tuple:
    """触发重新扫描流水线"""
    import threading
    import time

    # 检查是否已在扫描中
    lock_file = os.path.join(data_dir, ".scanning")
    if os.path.exists(lock_file):
        return 409, {"error": "扫描正在进行中，请稍后再试"}

    def _scan():
        os.makedirs(data_dir, exist_ok=True)
        with open(lock_file, "w") as f:
            f.write("1")
        try:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            from monitor.monitor import scan_board, save_threads_index
            from monitor.indexer import scan_wiki_articles, save_wiki_index
            from monitor.diff import detect_diffs, save_report

            threads = scan_board(max_pages=None, verbose=False)
            save_threads_index(threads)
            articles = scan_wiki_articles()
            save_wiki_index(articles)
            report = detect_diffs(threads, articles)
            save_report(report, report_path)
        finally:
            if os.path.exists(lock_file):
                os.remove(lock_file)

    threading.Thread(target=_scan, daemon=True).start()
    time.sleep(0.5)
    return 202, {"message": "扫描已启动，请稍后刷新页面查看结果"}


def _run_import(tid: int) -> tuple:
    """触发导入帖子"""
    import threading

    def _import():
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from monitor.fetcher import fetch_thread, fetch_images
        from monitor.converter import convert_thread_to_wiki
        from monitor.config import tid_text_dir, tid_img_dir
        import os as _os

        posts = fetch_thread(tid, verbose=False)
        if not posts:
            return

        first_post = next((p for p in posts if p.is_first_post), posts[0])
        metadata = {
            "title": first_post.author or f"TID-{tid}",
            "author": first_post.author,
            "forum_url": f"https://lgqmonline.top/thread-{tid}-1-1.html",
            "post_date": first_post.date,
            "tid": str(tid),
        }

        raw_content = convert_thread_to_wiki(posts, metadata=metadata)
        text_dir = tid_text_dir(tid)
        _os.makedirs(text_dir, exist_ok=True)
        raw_path = _os.path.join(text_dir, f"TID-{tid}.raw.mw")
        mw_path = _os.path.join(text_dir, f"TID-{tid}.mw")

        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(raw_content)
        wiki_content = raw_content.replace("{{PAGENAME}}", metadata["title"])
        with open(mw_path, "w", encoding="utf-8") as f:
            f.write(wiki_content)
        fetch_images(tid, output_dir=tid_img_dir(tid), verbose=False)

    threading.Thread(target=_import, daemon=True).start()
    return 202, {"message": f"导入 TID={tid} 已启动"}
