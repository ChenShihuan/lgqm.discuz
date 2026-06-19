#!/usr/bin/env python3
"""
临时脚本：对 .mw 文件运行段落分隔修复。

处理规则：
- 相邻非空行之间插入空行，确保 MediaWiki 正确分段
- 仅在 {{首行缩进start}}...{{首行缩进end}} 范围内处理，避免污染 Infobox/模板
- 自动备份原文件

用法：
    python3 fix_paragraphs.py lgqm.huijiwiki.com/进击旅顺口【游戏设计】.mw
    python3 fix_paragraphs.py --dry-run lgqm.huijiwiki.com/进击旅顺口【游戏设计】.mw
"""
import sys
import os
import shutil
import re

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from monitor.converter import _insert_paragraph_breaks


def fix_file(filepath: str, dry_run: bool = False) -> bool:
    """对单个 .mw 文件运行段落修复，返回是否修改"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    START = '{{首行缩进start}}'
    END = '{{首行缩进end}}'

    start_idx = content.find(START)
    end_idx = content.find(END)

    if start_idx == -1 or end_idx == -1:
        # 无首行缩进包装 → 对整个正文区域（Infobox 之外）处理
        # 找到 Infobox 结尾
        ibox_end = content.find('\n}}')
        if ibox_end != -1:
            ibox_end = content.index('\n}}', ibox_end) + 3
            body = content[ibox_end:]
            prefix = content[:ibox_end]
        else:
            print(f"  ⚠️  无法定位正文区域，跳过")
            return False
    else:
        # 仅处理首行缩进区域内的内容
        body_start = start_idx + len(START)
        body_end = end_idx
        prefix = content[:body_start]
        body = content[body_start:body_end]
        suffix = content[body_end:]

    # 只对正文非模板区域做段落修复（避开 {{table}}、{{同人注释}} 等）
    # 简单策略：按块分拆，只处理不在 {{...}} 内的纯文本段
    new_body = _insert_paragraph_breaks(body)

    if body == new_body:
        return False  # 无变化

    if dry_run:
        print(f"  ✅ 将修改（dry-run 模式，未实际写入）")
        return True

    # 备份
    bak = filepath + '.bak'
    if not os.path.exists(bak):
        shutil.copy2(filepath, bak)
        print(f"  📦 已备份: {bak}")

    # 写回
    if start_idx != -1 and end_idx != -1:
        new_content = prefix + new_body + suffix
    else:
        new_content = prefix + new_body

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return True


def main():
    dry_run = '--dry-run' in sys.argv
    files = [a for a in sys.argv[1:] if not a.startswith('--')]

    if not files:
        print(__doc__)
        sys.exit(1)

    total = 0
    for fp in files:
        if not os.path.isfile(fp):
            print(f"  ❌ 文件不存在: {fp}")
            continue
        print(f"📄 {fp}")
        changed = fix_file(fp, dry_run=dry_run)
        status = "✅ 已修复" if changed else "⏭️  无需修改"
        print(f"  {status}")
        if changed:
            total += 1

    mode = "（dry-run）" if dry_run else ""
    print(f"\n共处理 {total} 个文件 {mode}")


if __name__ == '__main__':
    main()
