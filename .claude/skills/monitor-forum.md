# Monitor Forum — 论坛同人板块监控

## 描述

扫描临高启明论坛「同人发布」板块（forum-39），对比灰机 Wiki 已有文章，发现新帖和更新帖。

## 触发条件

- "监控论坛"
- "检查论坛更新"
- "scan forum"
- "monitor"

## 执行流程

### Step 1: 扫描论坛板块

```bash
cd /mnt/e/code/lgqm.discuz && python3 -c "
import sys
sys.path.insert(0, '.')
from monitor.monitor import scan_board, save_threads_index

# 增量扫描前 5 页（日常）, 全量传 max_pages=None
threads = scan_board(max_pages=None, incremental=False, verbose=True)
save_threads_index(threads)
print(f'共扫描到 {len(threads)} 个帖子')
"
```

### Step 2: 索引 Wiki 文章

```bash
cd /mnt/e/code/lgqm.discuz && python3 -c "
import sys
sys.path.insert(0, '.')
from monitor.indexer import scan_wiki_articles, save_wiki_index

articles = scan_wiki_articles(verbose=True)
save_wiki_index(articles)
"
```

### Step 3: 生成差异报告

```bash
cd /mnt/e/code/lgqm.discuz && python3 -c "
import sys
sys.path.insert(0, '.')
from monitor.monitor import load_threads_index
from monitor.indexer import load_wiki_index, build_tid_index
from monitor.diff import detect_diffs, format_report_summary

threads = load_threads_index()
articles = load_wiki_index()
tid_index = build_tid_index(articles)

report = detect_diffs(threads, articles, tid_index, verbose=True)
report.to_json('data/diff_report.json')

# 打印摘要
print(format_report_summary(report))
"
```

### Step 4: 展示结果

将摘要输出给用户，提示可用操作：
- `导入 <tid>` — 导入新文章
- `更新 <tid>` — 更新已有文章
- `查看差异` — 进入 diff-review 详细模式

## 配置

- `--incremental`: 仅扫描前 5 页（快速检查）
- `--full`: 全量扫描 60 页
- `--pages N`: 扫描前 N 页
