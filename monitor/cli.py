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
    from monitor.utils import clean_article_name

    tid = args.tid

    # Step 0: 加载外部 TOC 分析结果（如有）
    toc_analysis = None
    if args.toc_file:
        from monitor.preanalyze import load_toc_analysis
        toc_analysis = load_toc_analysis(args.toc_file)
        if toc_analysis:
            print(f"📋 使用预分析目录: {len(toc_analysis.get('entries', []))} 个章节")
        else:
            print("⚠️  TOC 文件加载失败，回退到默认章节检测")

    # Step 1: 拉取帖子
    posts = fetch_thread(tid, verbose=True)

    if not posts:
        print(f"错误：未能拉取 TID={tid} 的任何内容")
        return

    # Step 2: 提取线程标题并生成文章名
    thread_title = get_thread_title(tid)
    if thread_title:
        # 清理标题：去前缀标签（【原创】等）、去日期后缀
        article_name = clean_article_name(thread_title)
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
    raw_content = convert_thread_to_wiki(posts, metadata=metadata, toc_analysis=toc_analysis)

    # 输出被合并/过滤的标题清单，供人工复核
    from monitor.converter import last_merged_titles
    from monitor.converter import _last_toc_info as toc_info
    if toc_info:
        print(f"\n📋 主楼目录章节: {len(toc_info)} 个")
    if last_merged_titles:
        print(f"\n🔀 被过滤未设为章节的标题 ({len(last_merged_titles)} 条)：")
        for i, t in enumerate(last_merged_titles, 1):
            print(f"   {i:>3}. {t}")
        print("   💡 如有意为之的章节标题，请在审阅时手动恢复为 == 标题 ==")

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
        result = fetch_images(tid, output_dir=tid_img_dir(tid, safe_name), verbose=True)
        images = result["images"]
        rename_map = result.get("rename_map", {})
        if images:
            print(f"下载了 {len(images)} 张图片")
            if rename_map:
                print(f"🔧 已修正 {len(rename_map)} 个文件扩展名")
                # 立即更新 .mw 文件中的图片引用
                _apply_rename_map_to_mw_files(rename_map, _os.path.dirname(filepath))
            if len(images) == 1:
                img_file = _os.path.basename(images[0].get("local_path", ""))
                print(f"💡 建议在 Infobox 图像字段填入: [[Image:{img_file}|class=img-responsive]]")
        else:
            print("无图片或下载失败")

        # Step 5b: 上传图片到 Wiki
        if args.upload_images and images:
            print("\n--- 上传图片到 Wiki ---")
            img_dir = tid_img_dir(tid, safe_name)
            if _os.path.isdir(img_dir) and _os.listdir(img_dir):
                from monitor.wiki_uploader import pw_upload_images
                result = pw_upload_images(img_dir=img_dir, wiki_domain="lgqm",
                                         skip_existing=True, verbose=True)
                print(f"上传: {result['uploaded']}/{result['total']} 张图片")
            else:
                print("无图片可上传")

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


def _sanitize_filename(name: str) -> str:
    """清理文件名，替换不允许的字符"""
    import re
    # Windows/Linux 文件名不允许的字符
    name = re.sub(r'[<>:"/\\|?*]', '-', name)
    # 去掉首尾空格和点
    name = name.strip('. ')
    return name if name else "untitled"


def _apply_rename_map_to_mw_files(rename_map: dict, text_dir: str):
    """
    更新 .mw 文件中重命名图片的 [[File:...]] 引用。

    仅在 [[File:xxx|...]] wikitext 标签内替换，避免误伤正文中的普通文本。

    Args:
        rename_map: {old_filename: new_filename}
        text_dir: 包含 .mw 和 .raw.mw 文件的目录
    """
    import re as _re, glob as _glob, os as _os

    if not rename_map:
        return

    mw_files = _glob.glob(_os.path.join(text_dir, "*.mw"))
    for mw_path in mw_files:
        with open(mw_path, "r", encoding="utf-8") as f:
            content = f.read()

        new_content = content
        changed = False
        for old_name, new_name in rename_map.items():
            if old_name not in new_content:
                continue
            # 仅在 [[File:xxx|...]] 或 [[File:xxx]] 中替换
            pattern = _re.compile(
                rf'\[\[File:{_re.escape(old_name)}(\||\])'
            )
            replacement = f'[[File:{new_name}\\1'
            new_text = pattern.sub(replacement, new_content)
            if new_text != new_content:
                changed = True
                new_content = new_text

        if changed:
            with open(mw_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"  📝 {_os.path.basename(mw_path)}: 已更新 {len(rename_map)} 处图片引用")


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
    if "__TOC__" not in content and re.search(r'^={1,3} .+ ={1,3}$', content, re.MULTILINE):
        suggestions.append("正文有章节标题，建议在 Infobox 后添加 __TOC__ 自动生成目录")

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
    chapters = len(re.findall(r'^={1,3} .+ ={1,3}$', content, re.MULTILINE))
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
            is_header = re.match(r'^={1,3} .+ ={1,3}$', c.strip())
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
    from monitor.config import tid_img_dir
    import os as _os, glob as _glob

    tid = args.tid

    # 尝试找到已有输出目录（含文章名）
    output_dir = None
    pattern = f"output/{tid}-*/text"
    matches = _glob.glob(pattern)
    if matches:
        base = _os.path.dirname(matches[0])
        output_dir = _os.path.join(base, "img")
        print(f"📂 输出目录: {output_dir}")

    result = fetch_images(tid, output_dir=output_dir, verbose=True)
    images = result["images"]
    if images:
        print(f"下载了 {len(images)} 张图片")
        rename_map = result.get("rename_map", {})
        if rename_map:
            print(f"🔧 已修正 {len(rename_map)} 个文件扩展名")
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


def cmd_preanalyze(args):
    """预分析帖子目录结构，供 AI 辅助判断章节"""
    from monitor.preanalyze import run_preanalysis

    tid = args.tid
    result = run_preanalysis(tid)

    if "error" in result:
        print(f"❌ 错误: {result['error']}")
        return

    print(f"\n帖子标题: {result['thread_title']}")
    print(f"文章名称: {result['article_name']}")
    print(f"已拉取前 {result['floor_count']} 层楼")
    print(f"\n📄 预分析文本: {result['text_path']}")
    print(f"\n请 AI 分析此文件中的目录结构，结果保存为:")
    print(f"  {result['toc_path']}")
    print(f"\nTOC 分析 JSON 格式:")
    print("""
{
  "thread_tid": <tid>,
  "source_floor": <包含目录的楼层号>,
  "format": "pid_links | freeform_list | numbered",
  "entries": [
    {"floor": 楼层号或null, "pid": "数字或null", "chapter_name": "章节名", "level": 1|2|3},
    ...
  ]
}
level: 1=卷/案(顶层), 2=标准章节(默认), 3=子章节""")


def cmd_normalize_domains(args):
    """批量替换 .mw 文件中的旧论坛域名为 lgqmonline.top"""
    import os as _os, glob as _glob
    from monitor.utils import normalize_forum_domains, OLD_FORUM_DOMAINS

    target_dir = args.path
    if target_dir is None:
        target_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "lgqm.huijiwiki.com")

    if not _os.path.isdir(target_dir):
        print(f"错误：目录不存在: {target_dir}")
        return

    mw_files = _glob.glob(_os.path.join(target_dir, "*.mw"))
    if not mw_files:
        print(f"目录中没有 .mw 文件: {target_dir}")
        return

    print(f"扫描 {len(mw_files)} 个 .mw 文件...")
    print(f"旧域名: {', '.join(OLD_FORUM_DOMAINS)}")
    print(f"新域名: lgqmonline.top")
    print()

    total_files = 0
    total_replacements = 0

    for filepath in sorted(mw_files):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        new_content = normalize_forum_domains(content)
        if new_content != content:
            total_files += 1
            # 统计替换次数
            changes = 0
            for old_domain in OLD_FORUM_DOMAINS:
                changes += content.count(old_domain)
            total_replacements += changes

            filename = _os.path.basename(filepath)
            if args.dry_run:
                print(f"  📄 {filename}: {changes} 处旧域名")
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"  ✅ {filename}: {changes} 处已替换")

    print()
    if args.dry_run:
        print(f"⚠️  --dry-run 模式：发现 {total_files} 个文件、{total_replacements} 处旧域名（未修改）")
        print(f"   执行 python3 -m monitor.cli normalize-domains 实际修改")
    else:
        print(f"✅ 完成：{total_files} 个文件、{total_replacements} 处旧域名已替换为 lgqmonline.top")


def cmd_upload_images(args):
    """上传图片到灰机 Wiki"""
    from monitor.wiki_uploader import pw_upload_images
    import os as _os

    img_dir = args.dir
    if img_dir is None:
        # 默认扫描 output/*/img/
        img_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "output")

    if not _os.path.isdir(img_dir):
        print(f"错误：目录不存在: {img_dir}")
        return

    result = pw_upload_images(
        img_dir=img_dir,
        wiki_domain=args.wiki,
        skip_existing=not args.force,
        dry_run=args.dry_run,
        verbose=True,
    )

    if not args.dry_run:
        print()
        print(f"--- 上传汇总 ---")
        print(f"总计: {result['total']}")
        print(f"已上传: {result['uploaded']}")
        print(f"已跳过: {result['skipped']}")
        print(f"失败: {result['failed']}")
        if result.get('renamed'):
            print(f"格式修正: {result['renamed']} 个文件")
        if result.get('mw_updated'):
            print(f".mw 引用更新: {result['mw_updated']} 个文件")
        if result.get('errors'):
            print(f"\n失败详情:")
            for err in result['errors']:
                print(f"  - {err['filename']}: {err['reason']}")


def cmd_fix_image_extensions(args):
    """检测并修正图片扩展名"""
    from monitor.wiki_uploader import _scan_image_dirs
    from monitor.utils import fix_image_extension

    img_dir = args.dir
    if img_dir is None:
        import os as _os
        img_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "output")

    images = _scan_image_dirs(img_dir)
    if not images:
        print("未找到图片文件")
        return

    print(f"扫描到 {len(images)} 张图片")
    if args.dry_run:
        print("⚠️  --dry-run 模式：仅预览，不实际修改\n")

    fixed = 0
    for filepath in images:
        result = fix_image_extension(filepath, dry_run=args.dry_run)
        if result:
            fixed += 1
            print(f"  🔧 {result['old_name']} → {result['new_name']}")
            print(f"     {result['reason']}")

    print(f"\n{'将' if args.dry_run else '已'}修正 {fixed} 个文件")


def cmd_img_sum(args):
    """归集 output/*/img/ 下的图片到 output/img_sum/"""
    import os, shutil
    src = os.path.join(os.path.dirname(__file__), "..", "output")
    dst = os.path.join(src, "img_sum")
    os.makedirs(dst, exist_ok=True)

    count = 0
    for root, dirs, files in os.walk(src):
        if root.endswith("/img") or root.endswith("\\img"):
            for f in files:
                src_file = os.path.join(root, f)
                dst_file = os.path.join(dst, f)
                if not os.path.exists(dst_file):
                    shutil.copy2(src_file, dst_file)
                    count += 1

    total = len(os.listdir(dst))
    print(f"已归集 {count} 张新图片，img_sum 共 {total} 张")


def cmd_confirm_match(args):
    """人工确认疑似匹配为有效匹配"""
    from monitor.diff import confirm_match_manually, format_report_summary
    from monitor.models import DiffReport

    report = DiffReport.from_json("data/diff_report.json")

    if args.tid:
        # 确认单个 TID
        ok = confirm_match_manually(report, args.tid)
        if ok:
            report.to_json("data/diff_report.json")
            print(f"✅ TID={args.tid} 已确认为有效匹配")
        else:
            print(f"❌ 未找到 TID={args.tid}")
    elif args.all:
        # 批量确认所有 possible_matches
        tids = []
        for item in list(report.possible_matches):
            item_tid = item.wiki_article.forum_tid if item.wiki_article else item.forum_thread.tid
            if item_tid:
                tids.append(item_tid)
        if tids:
            for tid in tids:
                confirm_match_manually(report, tid)
            report.to_json("data/diff_report.json")
            print(f"✅ 已确认 {len(tids)} 条匹配")
        else:
            print("没有待确认的疑似匹配")
    else:
        # 交互模式：列出疑似匹配，让用户选择
        if not report.possible_matches:
            print("没有待确认的疑似匹配")
            return

        print(f"待确认的疑似匹配 ({len(report.possible_matches)} 条):\n")
        for i, item in enumerate(report.possible_matches, 1):
            w = item.wiki_article
            tid = w.forum_tid if w else item.forum_thread.tid
            print(f"  {i:>2}. [TID={tid}] {w.title if w else '?'}")
            print(f"      {w.forum_url if w else ''}")
        print()
        print("输入序号确认（多个用逗号分隔，a=全部，q=退出）: ", end="")
        choice = input().strip()

        if choice.lower() == 'q':
            return
        elif choice.lower() == 'a':
            tids = []
            for item in report.possible_matches:
                item_tid = item.wiki_article.forum_tid if item.wiki_article else item.forum_thread.tid
                if item_tid:
                    tids.append(item_tid)
            for tid in tids:
                confirm_match_manually(report, tid)
            report.to_json("data/diff_report.json")
            print(f"✅ 已确认全部 {len(tids)} 条匹配")
        else:
            indices = [int(x.strip()) for x in choice.split(",") if x.strip().isdigit()]
            confirmed = 0
            for idx in indices:
                if 1 <= idx <= len(report.possible_matches):
                    item = report.possible_matches[idx - 1]
                    tid = item.wiki_article.forum_tid if item.wiki_article else item.forum_thread.tid
                    if tid and confirm_match_manually(report, tid):
                        confirmed += 1
            if confirmed > 0:
                report.to_json("data/diff_report.json")
                print(f"✅ 已确认 {confirmed} 条匹配")

    print()
    print(format_report_summary(report))


def cmd_match_titles(args):
    """基于标题匹配搬运文章"""
    from monitor.monitor import scan_board, save_threads_index
    from monitor.indexer import scan_wiki_articles
    from monitor.diff import title_match_articles, apply_title_matches
    import os as _os

    print("--- 加载数据 ---")
    print("扫描论坛帖子...")
    threads = scan_board(mode="full", verbose=False)
    print(f"  {len(threads)} 篇")

    print("索引 Wiki 文章...")
    articles = scan_wiki_articles()
    orphan = sum(1 for a in articles if a.forum_tid is None)
    print(f"  {len(articles)} 篇 (其中 {orphan} 篇未关联论坛)")

    print("\n--- 标题匹配 ---")
    matches = title_match_articles(threads, articles, verbose=True)
    if not matches:
        print("未发现匹配的搬运文章")
        return

    print(f"\n发现 {len(matches)} 组搬运文章匹配：")
    for i, m in enumerate(matches, 1):
        t = m["forum_thread"]
        a = m["wiki_article"]
        print(f"  {i:>3}. [{t.tid}] {t.title[:50]}")
        print(f"       Wiki: {a.filename}  (论坛: {m['forum_title_norm']} = Wiki: {m['wiki_title_norm']})")

    if args.dry_run:
        print(f"\n⚠️  --dry-run 模式，未修改文件。添加 --apply 以实际更新。")
        return

    if not args.apply:
        print(f"\n💡 使用 --apply 以实际更新 .mw 文件和 wiki_index")
        return

    print("\n--- 应用更新 ---")
    data_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "data")
    result = apply_title_matches(matches, data_dir=data_dir, dry_run=False)
    print(f"  .mw 更新: {result['updated_mw']} 篇")
    print(f"  wiki_index 更新: {result['updated_index']} 条")


def cmd_webui(args):
    """启动本地看板服务器"""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from webui.server import serve
    serve(port=args.port)


def cmd_update(args):
    """更新已有 Wiki 文章"""
    from monitor.fetcher import fetch_thread, fetch_images
    from monitor.indexer import load_wiki_index
    from monitor.converter import update_existing_wiki, save_wiki_file
    from monitor.config import tid_img_dir
    import os as _os, re as _re

    tid = args.tid

    # 找到对应的 Wiki 文章
    articles = load_wiki_index()
    matched = [a for a in articles
               if a.forum_tid == tid or tid in (a.forum_tids or [])]
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

    # 提取文章名（用于输出目录）
    article_name = article.title
    name_match = _re.search(r'\|\s*同人作品\s*=\s*(.+)', existing_content)
    if name_match:
        v = name_match.group(1).strip()
        if v and v != "{{PAGENAME}}":
            article_name = v

    # 拉取最新内容
    print(f"正在拉取 TID={tid} 最新内容...")
    posts = fetch_thread(tid, verbose=True)

    # 构建 metadata（传递日期信息）
    date = ""
    if posts:
        posts_sorted = sorted(posts, key=lambda p: p.date or "", reverse=True)
        if posts_sorted and posts_sorted[0].date:
            dm = _re.match(r'(\d{4}-\d{1,2}-\d{1,2})', posts_sorted[0].date)
            if dm:
                date = dm.group(1)
    metadata = {"post_date": date} if date else None

    # 生成更新版（增量追加）
    new_content = update_existing_wiki(existing_content, posts, metadata=metadata)
    new_filepath = save_wiki_file(new_content, article_name, tid=tid)

    print(f"\n原文件: {filepath}")
    print(f"新文件: {new_filepath}")
    print(f"共 {len(posts)} 楼")
    print()

    # 下载图片
    if args.download_images:
        print("--- 下载图片 ---")
        result = fetch_images(tid, output_dir=tid_img_dir(tid, article_name), verbose=True)
        images = result["images"]
        if images:
            print(f"下载了 {len(images)} 张图片")
            rename_map = result.get("rename_map", {})
            if rename_map:
                print(f"🔧 已修正 {len(rename_map)} 个文件扩展名")
                # 更新 .mw 文件中的图片引用
                _apply_rename_map_to_mw_files(rename_map, _os.path.dirname(new_filepath))

    print("--- 更新后内容预览（前 500 字）---")
    print(new_content[:500])

    # 更新同人作品列表
    if args.update_list:
        print("\n--- 更新同人作品列表 ---")
        try:
            from monitor.index_list import update_article
            if article_name and date:
                update_article(article_name, last_update=date)
                print(f"✅ 作品列表已更新: [[{article_name}]] 最近更新 → {date}")
            else:
                print("⚠️  无法提取文章名或日期")
        except Exception as e:
            print(f"⚠️  作品列表更新失败: {e}")


def cmd_word_count(args):
    """统计 .mw 文件字数并更新 Infobox"""
    from .utils import count_words_mw
    result = count_words_mw(args.file, dry_run=args.dry_run)
    print(f"字数统计: {result['word_count']} (中文 {result['chinese']} 字, 英文 {result['english']} 字符)")
    if args.dry_run:
        print("[dry-run] 未修改文件")


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
    p_im.add_argument("--toc-file", type=str, default=None,
                      help="预分析的 TOC JSON 文件路径")
    p_im.add_argument("--upload-images", action="store_true", help="下载图片后上传到 Wiki")

    # fetch-images
    p_fi = subparsers.add_parser("fetch-images", help="下载帖子图片")
    p_fi.add_argument("tid", type=int, help="帖子 TID")

    # review-info
    p_ri = subparsers.add_parser("review-info", help="显示待审阅项")
    p_ri.add_argument("file", type=str, help=".raw.mw 文件路径")

    # update
    p_up = subparsers.add_parser("update", help="更新 Wiki 文章")
    p_up.add_argument("tid", type=int, help="帖子 TID")
    p_up.add_argument("--download-images", action="store_true", help="同时下载图片")
    p_up.add_argument("--update-list", action="store_true", help="更新同人作品列表")

    # webui
    p_wb = subparsers.add_parser("webui", help="启动本地看板服务器")
    p_wb.add_argument("--port", type=int, default=8080, help="监听端口 (默认 8080)")

    # confirm-match
    p_cm = subparsers.add_parser("confirm-match", help="人工确认疑似匹配为有效匹配")
    p_cm.add_argument("tid", type=int, nargs="?", help="要确认的帖子 TID（不指定则交互模式）")
    p_cm.add_argument("--all", action="store_true", help="批量确认所有疑似匹配")

    # match-titles
    p_mt = subparsers.add_parser("match-titles", help="标题匹配搬运文章")
    p_mt.add_argument("--dry-run", action="store_true", help="仅预览匹配结果")
    p_mt.add_argument("--apply", action="store_true", help="实际更新 .mw 和索引")

    # renumber-list
    p_rl = subparsers.add_parser("renumber-list", help="校正同人作品列表序号")
    p_rl.add_argument("--dry-run", action="store_true", help="仅预览，不实际修改")

    # word-count
    p_wc = subparsers.add_parser("word-count", help="统计 .mw 文件字数并写入 Infobox")
    p_wc.add_argument("file", type=str, help=".mw 文件路径")
    p_wc.add_argument("--dry-run", action="store_true", help="仅统计，不修改文件")

    # preanalyze
    p_pa = subparsers.add_parser("preanalyze", help="预分析帖子目录结构")
    p_pa.add_argument("tid", type=int, help="帖子 TID")

    # normalize-domains
    p_nd = subparsers.add_parser("normalize-domains", help="批量替换 .mw 文件中的旧论坛域名")
    p_nd.add_argument("path", type=str, nargs="?", default=None,
                      help="目标目录路径（默认 lgqm.huijiwiki.com）")
    p_nd.add_argument("--dry-run", action="store_true", help="仅预览，不实际修改")

    # img-sum
    p_is = subparsers.add_parser("img-sum", help="归集 output/*/img/ 图片到 output/img_sum/")

    # upload-images
    p_ui = subparsers.add_parser("upload-images", help="上传本地图片到灰机 Wiki")
    p_ui.add_argument("--dir", type=str, default=None,
                      help="图片目录（默认扫描 output/*/img/）")
    p_ui.add_argument("--force", action="store_true", help="覆盖 Wiki 已有图片")
    p_ui.add_argument("--wiki", type=str, default="lgqm", help="Wiki 子域名 (默认 lgqm)")
    p_ui.add_argument("--dry-run", action="store_true", help="仅预览，不实际上传")

    # fix-image-extensions
    p_fe = subparsers.add_parser("fix-image-extensions", help="检测并修正图片扩展名（不上传）")
    p_fe.add_argument("--dir", type=str, default=None,
                      help="图片目录（默认扫描 output/*/img/）")
    p_fe.add_argument("--dry-run", action="store_true", help="仅预览，不实际重命名")

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
        "confirm-match": cmd_confirm_match,
        "match-titles": cmd_match_titles,
        "word-count": cmd_word_count,
        "preanalyze": cmd_preanalyze,
        "normalize-domains": cmd_normalize_domains,
        "upload-images": cmd_upload_images,
        "fix-image-extensions": cmd_fix_image_extensions,
        "img-sum": cmd_img_sum,
        "webui": cmd_webui,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
