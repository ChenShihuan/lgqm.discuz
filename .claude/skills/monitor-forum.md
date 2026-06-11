---
name: monitor-forum
description: 扫描临高启明论坛同人板块，对比灰机 Wiki 已有文章，发现新帖和更新帖
---

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
python3 -m monitor.cli scan --full
```

增量扫描（默认 5 页）：`python3 -m monitor.cli scan`
指定页数：`python3 -m monitor.cli scan --pages 10`

### Step 2: 索引 Wiki 文章

```bash
python3 -m monitor.cli index-wiki
```

### Step 3: 生成差异报告

```bash
python3 -m monitor.cli diff --verify
```

不验证疑似匹配：`python3 -m monitor.cli diff`

### Step 4: 展示结果

将摘要输出给用户，提示可用操作：
- `导入 <tid>` — 导入新文章
- `更新 <tid>` — 更新已有文章
- `查看差异` — 进入 diff-review 详细模式
