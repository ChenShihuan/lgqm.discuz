---
name: monitor-forum
description: 扫描临高启明论坛同人板块，对比灰机 Wiki 已有文章，发现新帖和更新帖
model: haiku
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

`--verify` 会自动验证疑似匹配的 TID 可访问性：
- 可访问（公开/需登录）→ 自动确认为匹配，归入 `confirmed_matches`
- 不可访问 → 保留在 `possible_matches`，待人工确认

不验证疑似匹配：`python3 -m monitor.cli diff`

### Step 4: 人工确认不可访问项（可选）

对于自动验证不可访问的项，可手动在浏览器中打开链接确认。若确认有效：

```bash
python3 -m monitor.cli confirm-match <TID>       # 确认单个
python3 -m monitor.cli confirm-match --all       # 批量确认全部
python3 -m monitor.cli confirm-match             # 交互模式
```

### Step 5: 展示结果

将摘要输出给用户，提示可用操作：
- `导入 <tid>` — 导入新文章
- `更新 <tid>` — 更新已有文章
- `查看差异` — 进入 diff-review 详细模式
- `python3 -m monitor.cli confirm-match <TID>` — 人工确认疑似匹配
