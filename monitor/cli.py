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
    import re, os as _os
    from monitor.fetcher import fetch_thread, fetch_images, get_thread_title
    from monitor.converter import convert_thread_to_wiki, save_wiki_file

    tid = args.tid

    # Step 1: 拉取帖子
    posts = fetch_thread(tid, verbose=True)

    if not posts:
        print(f"错误：未能拉取 TID={tid} 的任何内容")
        return

    # Step 2: 提取线程标题并生成文章名
    thread_title = get_thread_title(tid)
    if thread_title:
        # 清理标题：去前缀标签（【原创】等）、去日期后缀
        article_name = _clean_article_name(thread_title)
        print(f"\n📌 帖子标题: {thread_title}")
        print(f"📝 文章名称: {article_name}")
    else:
        article_name = f"TID-{tid}"
        thread_title = article_name
        print(f"\n⚠️  未能提取标题，使用默认名: {article_name}")

    # Step 3: 构建元数据
    first_post = next((p for p in posts if p.is_first_post), posts[0])
    metadata = {
        "title": article_name,
        "author": first_post.author,
        "forum_url": f"https://lgqmonline.top/thread-{tid}-1-1.html",
        "post_date": first_post.date,
        "tid": str(tid),
    }

    # Step 4: 转换为 Wiki 格式（原始版，不做任何替换）
    raw_content = convert_thread_to_wiki(posts, metadata=metadata)

    # 保存原始版 (.raw.mw) — 供 review skill 使用
    safe_name = _sanitize_filename(article_name)
    from monitor.config import tid_text_dir, tid_img_dir
    raw_dir = tid_text_dir(tid, safe_name)
    _os.makedirs(raw_dir, exist_ok=True)
    raw_path = _os.path.join(raw_dir, f"{safe_name}.raw.mw")
    with open(raw_path, 'w', encoding='utf-8') as f:
        f.write(raw_content)
    print(f"\n📄 原始文件: {raw_path}")

    # 生成初步处理版 (.mw) — 仅做基础替换
    wiki_content = raw_content
    wiki_content = wiki_content.replace("{{PAGENAME}}", article_name)
    wiki_content = wiki_content.replace(
        f"[https://lgqmonline.top/thread-{tid}-1-1.html TID-{tid}]",
        f"[https://lgqmonline.top/thread-{tid}-1-1.html {thread_title}]"
    )
    # 移除 <!--作者ID--> 注释
    wiki_content = _os.linesep.join(
        line.replace('<!--作者ID-->', '') for line in wiki_content.split('\n')
    )

    filepath = save_wiki_file(wiki_content, safe_name, tid=tid)
    print(f"📝 处理文件: {filepath}")
    print(f"共 {len(posts)} 楼")
    print()

    # Step 5: 图片下载
    images = []
    if args.download_images:
        print("--- 下载图片 ---")
        images = fetch_images(tid, output_dir=tid_img_dir(tid, safe_name), verbose=True)
        if images:
            print(f"下载了 {len(images)} 张图片")
            if len(images) == 1:
                img_file = _os.path.basename(images[0].get("local_path", ""))
                print(f"💡 建议在 Infobox 图像字段填入: [[Image:{img_file}|class=img-responsive]]")
        else:
            print("无图片或下载失败")

    # Step 6: 统计信息
    _print_stats(raw_content, article_name, images)
    _print_suggestions(wiki_content, article_name, images)

    # 预览
    print("\n--- 内容预览（前 500 字）---")
    print(wiki_content[:500])

    # Step 7: 更新同人作品列表
    if args.update_list:
        print("\n--- 更新同人作品列表 ---")
        try:
            from monitor.index_list import update_from_mw_file
            action, seq, name = update_from_mw_file(filepath)
            print(f"✅ 作品列表已{action}: #{seq} [[{name}]]")
        except Exception as e:
            print(f"⚠️  作品列表更新失败: {e}")


def _clean_article_name(title: str) -> str:
    """从论坛帖子标题生成 Wiki 文章名"""
    import re
    name = title.strip()

    # 去掉前缀标签：【原创】、「同人」等
    name = re.sub(r'^[【\[「〈](?:原创|同人|完结[了]?|转正)[】\]」〉]\s*', '', name)

    # 去掉日期/更新后缀：如 " XX.XX.XX更新"、" 5.14更新"、" 更新至XX章"
    name = re.sub(r'\s*\d{1,2}[\.\-]\d{1,2}[\.\-]?\d{0,2}\s*更新?(?:至第?\w+章)?$', '', name)
    name = re.sub(r'\s*\d+年\d+月\d+日\s*(?:更新|彩蛋|尾声).*$', '', name)
    name = re.sub(r'\s*更新至第?\w+章$', '', name)

    # 去掉多余空格
    name = name.strip()

    return name if name else title.strip()


def _sanitize_filename(name: str) -> str:
    """清理文件名，替换不允许的字符"""
    import re
    # Windows/Linux 文件名不允许的字符
    name = re.sub(r'[<>:"/\\|?*]', '-', name)
    # 去掉首尾空格和点
    name = name.strip('. ')
    return name if name else "untitled"


def _print_suggestions(content: str, article_name: str, images: list):
    """分析内容并输出优化建议"""
    suggestions = []

    # 1. 检查 Infobox 字段完整性
    if "| 地点 =" in content and "<!--" in content.split("| 地点 =")[1].split("\n")[0]:
        suggestions.append("「地点」字段为空，建议填写故事发生地")
    if "| 涉及方面 =" in content and "<!--" in content.split("| 涉及方面 =")[1].split("\n")[0]:
        suggestions.append("「涉及方面」字段为空，建议填写关键词（如：工业、军事、外交等）")
    if "| 内容关键字 =" in content and "<!--" in content.split("| 内容关键字 =")[1].split("\n")[0]:
        suggestions.append("「内容关键字」字段为空，建议补充标签")

    # 2. 检查是否包含 TOC
    if "__TOC__" not in content and content.count("\n==") >= 3:
        suggestions.append("正文超过 3 节，建议在 Infobox 后添加 __TOC__ 自动生成目录")

    # 3. 图片建议
    if not images:
        suggestions.append("未检测到图片，如原文有配图可后续手动补传")

    if suggestions:
        print("\n💡 优化建议：")
        for s in suggestions:
            print(f"  • {s}")


def _print_stats(content: str, article_name: str, images: list):
    """打印内容统计信息"""
    import re
    annotation_blocks = len(re.findall(r'\{\{同人注释start\}\}', content))
    chapters = len(re.findall(r'=== .+ ===', content))
    chars = len(content)
    print(f"\n📊 统计: 章节 {chapters} | 同人注释 {annotation_blocks} 块 | 总字符 {chars}")


def cmd_review_info(args):
    """显示待审阅项的详细信息"""
    import re, os as _os

    raw_file = args.file
    if not _os.path.exists(raw_file):
        print(f"错误：文件不存在 {raw_file}")
        return

    with open(raw_file, 'r', encoding='utf-8') as f:
        content = f.read()

    print(f"📄 文件: {raw_file}")
    print(f"   大小: {_os.path.getsize(raw_file)} bytes")
    print()

    # 空 Infobox 字段
    empty_fields = []
    for field in ['地点', '涉及方面', '内容关键字', '图像']:
        pattern = rf'\| {field} = (?:<!--[^>]*-->)?\s*$'
        if re.search(pattern, content, re.MULTILINE):
            empty_fields.append(field)
    if empty_fields:
        print(f"🔲 空白 Infobox 字段: {', '.join(empty_fields)}")

    # 章节
    chapters = re.findall(r'(?:第[一二三四五六七八九十百千]+章|序章|终章|尾声)[^\n]*', content)
    if chapters:
        print(f"\n📑 发现的章节标记 ({len(chapters)}):")
        for c in chapters[:15]:
            is_header = re.match(r'^=== .+ ===$', c.strip())
            tag = '✅' if is_header else '  '
            print(f"   {tag} {c.strip()[:50]}")

    # 同人注释
    annotations = re.findall(r'\{\{同人注释start\}\}', content)
    print(f"\n💬 同人注释块: {len(annotations)}")

    # 残留检查
    residuals = re.findall(r'.*(?:发表于|本帖最后由).*', content)
    if residuals:
        print(f"\n⚠️  残留「发表于/本帖最后由」: {len(residuals)} 处")
        for r in residuals[:5]:
            print(f"   → {r.strip()[:80]}")

    # 重复内容检查
    lines = [l.strip() for l in content.split('\n') if len(l.strip()) > 30]
    seen = {}
    for i, line in enumerate(lines):
        key = line[:100]
        if key in seen:
            print(f"\n🔁 疑似重复内容 (行 {seen[key]}, {i}): {key[:60]}...")
        else:
            seen[key] = i

    print(f"\n💡 使用 review-article skill 进行交互式审阅优化")


def cmd_fetch_images(args):
    """下载帖子图片"""
    from monitor.fetcher import fetch_images

    tid = args.tid
    images = fetch_images(tid, verbose=True)
    if images:
        print(f"下载了 {len(images)} 张图片")
    else:
        print("无图片或下载失败")


def cmd_renumber_list(args):
    """校正同人作品列表序号"""
    from monitor.index_list import renumber_list

    print("正在分析列表序号...")
    result = renumber_list(dry_run=args.dry_run)

    print(f"总条目: {result['total']}")
    print(f"修正序号: {result['changed']} 处")
    print(f"分卷共享序号: {result['issues_fixed']} 组")

    if args.dry_run:
        print("\n⚠️  --dry-run 模式，未实际修改文件")
    else:
        print("\n✅ 列表序号已校正")


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
    new_filepath = save_wiki_file(new_content, f"TID-{tid}-updated", tid=tid)

    print(f"\n原文件: {filepath}")
    print(f"新文件: {new_filepath}")
    print(f"共 {len(posts)} 楼")
    print()
    print("--- 更新后内容预览（前 500 字）---")
    print(new_content[:500])

    # 更新同人作品列表
    if args.update_list:
        print("\n--- 更新同人作品列表 ---")
        try:
            from monitor.index_list import update_article
            import re as _re

            # 从原文件提取文章名
            name_match = _re.search(r'\|\s*同人作品\s*=\s*(.+)', existing_content)
            if name_match:
                article_name = name_match.group(1).strip()
                # 提取最近更新日期
                date = ""
                posts_sorted = sorted(posts, key=lambda p: p.date or "", reverse=True)
                if posts_sorted:
                    date_match = _re.match(r'(\d{4}-\d{1,2}-\d{1,2})', posts_sorted[0].date or "")
                    if date_match:
                        date = date_match.group(1)

                if article_name and date:
                    update_article(article_name, last_update=date)
                    print(f"✅ 作品列表已更新: [[{article_name}]] 最近更新 → {date}")
                else:
                    print("⚠️  无法提取文章名或日期")
        except Exception as e:
            print(f"⚠️  作品列表更新失败: {e}")


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
    p_im.add_argument("--update-list", action="store_true", help="更新同人作品列表")

    # fetch-images
    p_fi = subparsers.add_parser("fetch-images", help="下载帖子图片")
    p_fi.add_argument("tid", type=int, help="帖子 TID")

    # review-info
    p_ri = subparsers.add_parser("review-info", help="显示待审阅项")
    p_ri.add_argument("file", type=str, help=".raw.mw 文件路径")

    # update
    p_up = subparsers.add_parser("update", help="更新 Wiki 文章")
    p_up.add_argument("tid", type=int, help="帖子 TID")
    p_up.add_argument("--update-list", action="store_true", help="更新同人作品列表")

    # renumber-list
    p_rl = subparsers.add_parser("renumber-list", help="校正同人作品列表序号")
    p_rl.add_argument("--dry-run", action="store_true", help="仅预览，不实际修改")

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
        "review-info": cmd_review_info,
        "update": cmd_update,
        "renumber-list": cmd_renumber_list,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
