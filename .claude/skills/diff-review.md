# Diff Review — 差异报告审阅

## 描述

读取并展示论坛与 Wiki 的差异报告，分类浏览新帖、更新帖和疑似匹配项。

## 触发条件

- "查看差异"
- "审阅报告"
- "review diff"
- monitor-forum 完成后自动触发

## 执行流程

### Step 1: 读取差异报告

```bash
cd /mnt/e/code/lgqm.discuz && python3 -c "
import json
with open('data/diff_report.json', 'r', encoding='utf-8') as f:
    report = json.load(f)

summary = report['summary']
print(f'扫描时间: {report[\"scan_time\"]}')
print(f'论坛总帖子: {summary[\"total_forum_threads\"]}')
print(f'Wiki 同人文章: {summary[\"total_wiki_articles\"]}')
print()
print(f'🆕 新帖: {summary[\"new_threads\"]}')
print(f'📝 更新: {summary[\"updated_threads\"]}')
print(f'❓ 疑似: {summary[\"possible_matches\"]}')
"
```

### Step 2: 分类浏览

按用户要求展示特定类别的详情：

**新帖列表**：
```bash
cd /mnt/e/code/lgqm.discuz && python3 -c "
import json
with open('data/diff_report.json', 'r', encoding='utf-8') as f:
    report = json.load(f)

for i, item in enumerate(report['new_items'][:30], 1):
    t = item['forum_thread']
    print(f'{i:>2}. [{t[\"tid\"]}] {t[\"title\"][:60]}')
    print(f'    作者: {t[\"author\"]} | 回复: {t[\"reply_count\"]} | 查看: {t[\"view_count\"]}')
    print(f'    最后更新: {t[\"last_reply_date\"]}')
    print(f'    URL: {t[\"url\"]}')
    print()
"
```

**更新帖列表**：
```bash
cd /mnt/e/code/lgqm.discuz && python3 -c "
import json
with open('data/diff_report.json', 'r', encoding='utf-8') as f:
    report = json.load(f)

for i, item in enumerate(report['updated_items'], 1):
    t = item['forum_thread']
    w = item.get('wiki_article', {})
    print(f'{i:>2}. [{t[\"tid\"]}] {t[\"title\"][:60]}')
    print(f'    Wiki: {w.get(\"filename\", \"?\")} | 最近更新: {w.get(\"last_update\", \"?\")}')
    print(f'    论坛更新: {t[\"last_reply_date\"]}')
    print(f'    原因: {item[\"reason\"]}')
    print()
"
```

### Step 3: 用户操作

对于每个差异项，用户可选择：
- `skip` / `跳过` — 忽略此项
- `import <tid>` — 导入该帖为新的 Wiki 文章
- `update <tid>` — 更新对应 Wiki 文章
- `open <tid>` — 在浏览器打开论坛帖子
- `wiki <filename>` — 查看对应 Wiki 文章内容
