---
name: diff-review
description: 读取并展示论坛与 Wiki 的差异报告，分类浏览新帖、更新帖和疑似匹配项
model: haiku
---

# Diff Review — 差异报告审阅

## 描述

读取并展示论坛与 Wiki 的差异报告，分类浏览新帖、更新帖和疑似匹配项。

## 触发条件

- "查看差异"
- "审阅报告"
- "review diff"
- monitor-forum 完成后自动触发

## 执行流程

### Step 1: 查看报告摘要

```bash
python3 -m monitor.cli report-summary
```

### Step 2: 验证疑似匹配

对 `possible_matches` 中的每个 TID，通过 Archiver 验证可访问性（未登录时非公开板块会显示为不可访问，需要 cookie 才能准确判断）：

```bash
python3 -m monitor.cli verify-matches
```

### Step 3: 分类浏览

**新帖列表**：

```bash
python3 -m monitor.cli list-new --limit 30
```

**更新帖列表**：

```bash
python3 -m monitor.cli list-updated
```

### Step 4: 用户操作

对于每个差异项，用户可选择：
- `skip` / `跳过` — 忽略此项
- `import <tid>` — 导入该帖为新的 Wiki 文章
- `update <tid>` — 更新对应 Wiki 文章
- `open <tid>` — 在浏览器打开论坛帖子
- `wiki <filename>` — 查看对应 Wiki 文章内容
