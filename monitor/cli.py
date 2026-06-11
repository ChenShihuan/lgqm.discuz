"""
统一命令行接口 — 所有操作通过子命令调用

用法:
    python -m monitor.cli scan [--full] [--pages N]
    python -m monitor.cli index-wiki
    python -m monitor.cli diff [--verify]
    python -m monitor.cli report-summary
    python -m monitor.cli verify-matches
    python -m monitor.cli list-new [--limit N]
    python -m monitor.cli list-updated
    python -m monitor.cli import <TID> [--download-images]
    python -m monitor.cli fetch-images <TID>
    python -m monitor.cli update <TID>
"""
import argparse
import json
import os
import sys

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def cmd_scan(args):
    """扫描论坛板块，保存帖子索引"""
    from monitor.monitor import scan_board, save_threads_index

    mode = "full" if args.full else "quick"
    threads = scan_board(mode=mode, verbose=True)
    save_threads_index(threads)
    print(f"共扫描到 {len(threads)} 个帖子")


def cmd_index_wiki(args):
    """索引 Wiki 文章"""
    from monitor.indexer import scan_wiki_articles, save_wiki_index

    articles = scan_wiki_articles(verbose=True)
    save_wiki_index(articles)


def cmd_diff(args):
    """生成差异报告"""
    from monitor.monitor import load_threads_index
    from monitor.indexer import load_wiki_index, build_tid_index
    from monitor.diff import detect_diffs, verify_possible_matches, format_report_summary

    threads = load_threads_index()
    articles = load_wiki_index()
    tid_index = build_tid_index(articles)

    report = detect_diffs(threads, articles, tid_index, verbose=True)

    if args.verify:
        report = verify_possible_matches(report, verbose=True)

    report.to_json("data/diff_report.json")
    print(format_report_summary(report))


def cmd_report_summary(args):
    """打印差异报告摘要"""
    from monitor.diff import format_report_summary
    from monitor.models import DiffReport

    report = DiffReport.from_json("data/diff_report.json")
    print(format_report_summary(report))


def cmd_verify_matches(args):
    """验证疑似匹配的可访问性"""
    from monitor.diff import verify_possible_matches, format_report_summary
    from monitor.models import DiffReport

    report = DiffReport.from_json("data/diff_report.json")
    report = verify_possible_matches(report, verbose=True)
    report.to_json("data/diff_report.json")
    print()
    print(format_report_summary(report))


def cmd_list_new(args):
    """列出新帖"""
    with open("data/diff_report.json", "r", encoding="utf-8") as f:
        report = json.load(f)

    items = report.get("new_items", [])[: args.limit]
    if not items:
        print("(无新帖)")
        return

    for i, item in enumerate(items, 1):
        t = item["forum_thread"]
        print(f'{i:>3}. [{t["tid"]}] {t["title"][:60]}')
        print(f'     作者: {t["author"]} | 回复: {t.get("reply_count", "?")} | 查看: {t.get("view_count", "?")}')
        print(f'     最后更新: {t.get("last_reply_date", "?")}')
        print(f'     URL: {t["url"]}')
        print()


def cmd_list_updated(args):
    """列出更新帖"""
    with open("data/diff_report.json", "r", encoding="utf-8") as f:
        report = json.load(f)

    items = report.get("updated_items", [])
    if not items:
        print("(无更新帖)")
        return

    for i, item in enumerate(items, 1):
        t = item["forum_thread"]
        w = item.get("wiki_article", {})
        print(f'{i:>2}. [{t["tid"]}] {t["title"][:60]}')
        print(f'    Wiki: {w.get("filename", "?")} | 最近更新: {w.get("last_update", "?")}')
        print(f'    论坛更新: {t.get("last_reply_date", "?")}')
        print(f'    原因: {item.get("reason", "?")}')
        print()


def cmd_import(args):
    """导入帖子为新 Wiki 文章"""
    from monitor.fetcher import fetch_thread, fetch_images
    from monitor.converter import convert_thread_to_wiki, save_wiki_file

    tid = args.tid

    # Step 1: 拉取帖子
    posts = fetch_thread(tid, verbose=True)

    # 构建元数据
    first_post = next((p for p in posts if p.is_first_post), posts[0] if posts else None)
    if first_post:
        metadata = {
            "title": f"TID-{tid}",
            "author": first_post.author,
            "forum_url": f"https://lgqmonline.top/thread-{tid}-1-1.html",
            "post_date": first_post.date,
            "tid": str(tid),
        }
    else:
        metadata = {"title": f"TID-{tid}", "tid": str(tid)}

    # 转换为 Wiki 格式
    wiki_content = convert_thread_to_wiki(posts, metadata=metadata)
    filepath = save_wiki_file(wiki_content, f"TID-{tid}")

    print(f"\n生成文件: {filepath}")
    print(f"共 {len(posts)} 楼")
    print()
    print("--- 内容预览（前 500 字）---")
    print(wiki_content[:500])

    # Step 2: 下载图片
    if args.download_images:
        print("\n--- 下载图片 ---")
        images = fetch_images(tid, verbose=True)
        if images:
            print(f"下载了 {len(images)} 张图片")
        else:
            print("无图片或下载失败")


def cmd_fetch_images(args):
    """下载帖子图片"""
    from monitor.fetcher import fetch_images

    tid = args.tid
    images = fetch_images(tid, verbose=True)
    if images:
        print(f"下载了 {len(images)} 张图片")
    else:
        print("无图片或下载失败")


def cmd_update(args):
    """更新已有 Wiki 文章"""
    from monitor.fetcher import fetch_thread
    from monitor.indexer import load_wiki_index
    from monitor.converter import update_existing_wiki, save_wiki_file
    import os as _os

    tid = args.tid

    # 找到对应的 Wiki 文章
    articles = load_wiki_index()
    matched = [a for a in articles if a.forum_tid == tid]
    if not matched:
        print(f"错误：未找到 TID={tid} 对应的 Wiki 文章")
        return

    article = matched[0]
    repo_path = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "lgqm.huijiwiki.com")
    filepath = _os.path.join(repo_path, article.filename)

    if not _os.path.exists(filepath):
        print(f"错误：Wiki 文件不存在: {filepath}")
        return

    # 读取现有内容
    with open(filepath, "r", encoding="utf-8") as f:
        existing_content = f.read()

    # 拉取最新内容
    print(f"正在拉取 TID={tid} 最新内容...")
    posts = fetch_thread(tid, verbose=True)

    # 生成更新版
    new_content = update_existing_wiki(existing_content, posts)
    new_filepath = save_wiki_file(new_content, f"TID-{tid}-updated")

    print(f"\n原文件: {filepath}")
    print(f"新文件: {new_filepath}")
    print(f"共 {len(posts)} 楼")
    print()
    print("--- 更新后内容预览（前 500 字）---")
    print(new_content[:500])


def main():
    parser = argparse.ArgumentParser(
        description="临高启明论坛同人监控工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # scan
    p_scan = subparsers.add_parser("scan", help="扫描论坛板块")
    p_scan.add_argument("--full", action="store_true", help="全量扫描（默认快速扫描 5 页）")

    # index-wiki
    p_iw = subparsers.add_parser("index-wiki", help="索引 Wiki 文章")

    # diff
    p_diff = subparsers.add_parser("diff", help="生成差异报告")
    p_diff.add_argument("--verify", action="store_true", help="同时验证疑似匹配")

    # report-summary
    p_rs = subparsers.add_parser("report-summary", help="打印差异报告摘要")

    # verify-matches
    p_vm = subparsers.add_parser("verify-matches", help="验证疑似匹配可访问性")

    # list-new
    p_ln = subparsers.add_parser("list-new", help="列出新帖")
    p_ln.add_argument("--limit", type=int, default=30, help="显示条数 (默认 30)")

    # list-updated
    p_lu = subparsers.add_parser("list-updated", help="列出更新帖")

    # import
    p_im = subparsers.add_parser("import", help="导入帖子")
    p_im.add_argument("tid", type=int, help="帖子 TID")
    p_im.add_argument("--download-images", action="store_true", help="同时下载图片")

    # fetch-images
    p_fi = subparsers.add_parser("fetch-images", help="下载帖子图片")
    p_fi.add_argument("tid", type=int, help="帖子 TID")

    # update
    p_up = subparsers.add_parser("update", help="更新 Wiki 文章")
    p_up.add_argument("tid", type=int, help="帖子 TID")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    commands = {
        "scan": cmd_scan,
        "index-wiki": cmd_index_wiki,
        "diff": cmd_diff,
        "report-summary": cmd_report_summary,
        "verify-matches": cmd_verify_matches,
        "list-new": cmd_list_new,
        "list-updated": cmd_list_updated,
        "import": cmd_import,
        "fetch-images": cmd_fetch_images,
        "update": cmd_update,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
