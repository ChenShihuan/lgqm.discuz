"""
WebUI API 路由模块
"""
import json
import os
import re

# 提取标题中所有【标签】和（标签）
_TAG_PATTERN = re.compile(r'[【\[「〈（]([^】\]」〉）]*)[】\]」〉）]')


def _classify(title: str) -> str:
    """
    根据标题所有标签分类（不限于首个）：
    - 'video':    含「视频」标签
    - 'standard': 含「原创」或「短篇」（包括短篇同人/超短篇等变体）
    - 'other':    其他
    """
    tags = [t.strip() for t in _TAG_PATTERN.findall(title)]
    for tag in tags:
        if '视频' in tag:
            return 'video'
    for tag in tags:
        if '原创' in tag or '短篇' in tag or '同人' in tag or '原創' in tag:
            return 'standard'
    return 'other'


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


# ---- 导入队列 ----

def _queue_path(data_dir: str) -> str:
    return os.path.join(data_dir, "import_queue.json")


def _load_queue(data_dir: str) -> list:
    path = _queue_path(data_dir)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("items", [])
    return []


def _save_queue(data_dir: str, items: list):
    path = _queue_path(data_dir)
    data = {
        "items": items,
        "updated_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def router(method: str, path: str, report_path: str, data_dir: str) -> tuple:
    """API 路由分发，返回 (status_code, data_dict)"""
    # GET /api/report
    if method == "GET" and path == "/api/report":
        return _get_report(report_path, data_dir)

    # GET /api/wiki
    if method == "GET" and path == "/api/wiki":
        return _get_wiki(data_dir)

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

    # GET /api/queue
    if method == "GET" and path == "/api/queue":
        return 200, {"items": _load_queue(data_dir)}

    # POST /api/queue/<tid>
    if method == "POST" and path.startswith("/api/queue/"):
        tid = int(path.rsplit("/", 1)[-1])
        return _add_to_queue(data_dir, tid)

    # DELETE /api/queue/<tid>
    if method == "DELETE" and path.startswith("/api/queue/"):
        tid = int(path.rsplit("/", 1)[-1])
        return _remove_from_queue(data_dir, tid)

    # DELETE /api/queue
    if method == "DELETE" and path == "/api/queue":
        _save_queue(data_dir, [])
        return 200, {"message": "队列已清空", "items": []}

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
    video_count = 0
    for item in data.get("new_items", []):
        tid = item["forum_thread"]["tid"]
        item["category"] = _classify(item["forum_thread"]["title"])
        if item["category"] == "standard":
            standard_count += 1
        elif item["category"] == "video":
            video_count += 1
        else:
            other_count += 1
        item["skipped"] = tid in skip_tids

    # 更新帖也标记跳过
    for item in data.get("updated_items", []):
        item["skipped"] = item["forum_thread"]["tid"] in skip_tids

    data["summary"]["new_standard"] = standard_count
    data["summary"]["new_other"] = other_count
    data["summary"]["new_video"] = video_count
    # 队列 TID
    queue_items = _load_queue(data_dir)
    queue_tids = {q["tid"] for q in queue_items}
    for item in data.get("new_items", []):
        item["queued"] = item["forum_thread"]["tid"] in queue_tids
    for item in data.get("updated_items", []):
        item["queued"] = item["forum_thread"]["tid"] in queue_tids

    data["summary"]["skipped_count"] = len(skip_tids)
    data["summary"]["queue_count"] = len(queue_items)
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


def _find_title_in_report(report_path: str, tid: int) -> str:
    """从报告中查找 TID 对应的标题"""
    if not os.path.exists(report_path):
        return ""
    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for item in data.get("new_items", []) + data.get("updated_items", []):
        if item["forum_thread"]["tid"] == tid:
            return item["forum_thread"]["title"]
    return ""


def _add_to_queue(data_dir: str, tid: int) -> tuple:
    """将 TID 加入导入队列"""
    items = _load_queue(data_dir)
    if any(q["tid"] == tid for q in items):
        return 200, {"message": f"TID={tid} 已在队列中", "count": len(items)}

    title = _find_title_in_report(os.path.join(data_dir, "diff_report.json"), tid)
    items.append({
        "tid": tid,
        "title": title,
        "added_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    _save_queue(data_dir, items)
    return 200, {"message": f"已加入队列: [{tid}] {title[:40]}", "count": len(items)}


def _get_wiki(data_dir: str) -> tuple:
    """返回 Wiki 文章列表"""
    wiki_path = os.path.join(data_dir, "wiki_index.json")
    if not os.path.exists(wiki_path):
        return 404, {"error": "wiki_index.json 不存在，请先运行 index-wiki"}
    with open(wiki_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 附加上跳过状态
    skipped = _load_skipped(data_dir)
    for a in data.get("articles", []):
        a["skipped"] = a.get("forum_tid") in skipped["tids"]
    return 200, data


def _remove_from_queue(data_dir: str, tid: int) -> tuple:
    """从导入队列中移除 TID"""
    items = _load_queue(data_dir)
    items = [q for q in items if q["tid"] != tid]
    _save_queue(data_dir, items)
    return 200, {"message": f"已移出队列 TID={tid}", "count": len(items)}


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


def _clean_article_name(title: str) -> str:
    """从论坛帖子标题生成 Wiki 文章名（对齐 cli.py 逻辑）"""
    name = title.strip()
    name = re.sub(r'^[【\[「〈](?:原创|同人|完结[了]?|转正)[】\]」〉]\s*', '', name)
    name = re.sub(r'\s*\d{1,2}[\.\-]\d{1,2}[\.\-]?\d{0,2}\s*更新?(?:至第?\w+章)?$', '', name)
    name = re.sub(r'\s*\d+年\d+月\d+日\s*(?:更新|彩蛋|尾声).*$', '', name)
    name = re.sub(r'\s*更新至第?\w+章$', '', name)
    return name.strip() or title.strip()


def _run_import(tid: int) -> tuple:
    """触发导入帖子（与 cmd_import 逻辑一致）"""
    import threading

    def _import():
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from monitor.fetcher import fetch_thread, fetch_images, get_thread_title
        from monitor.converter import convert_thread_to_wiki
        from monitor.config import tid_text_dir, tid_img_dir
        import os as _os

        posts = fetch_thread(tid, verbose=False)
        if not posts:
            return

        # 提取并清理文章名
        thread_title = get_thread_title(tid)
        article_name = _clean_article_name(thread_title) if thread_title else f"TID-{tid}"

        first_post = next((p for p in posts if p.is_first_post), posts[0])
        metadata = {
            "title": article_name,
            "author": first_post.author,
            "forum_url": f"https://lgqmonline.top/thread-{tid}-1-1.html",
            "post_date": first_post.date,
            "tid": str(tid),
        }

        raw_content = convert_thread_to_wiki(posts, metadata=metadata)
        text_dir = tid_text_dir(tid, article_name)
        _os.makedirs(text_dir, exist_ok=True)
        raw_path = _os.path.join(text_dir, f"{article_name}.raw.mw")
        mw_path = _os.path.join(text_dir, f"{article_name}.mw")

        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(raw_content)

        # 基础处理（对齐 cmd_import）
        wiki_content = raw_content
        wiki_content = wiki_content.replace("{{PAGENAME}}", article_name)
        wiki_content = _os.linesep.join(
            line.replace('<!--作者ID-->', '') for line in wiki_content.split('\n')
        )
        with open(mw_path, "w", encoding="utf-8") as f:
            f.write(wiki_content)

        fetch_images(tid, output_dir=tid_img_dir(tid, article_name), verbose=False)

    threading.Thread(target=_import, daemon=True).start()
    return 202, {"message": f"导入 TID={tid} 已启动"}
