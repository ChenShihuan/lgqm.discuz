---
name: update-article
description: 对 Wiki 已收录的同人文章，从论坛拉取最新内容更新 .mw 文件
model: haiku
---

# Update Article — 更新已有 Wiki 文章

## 描述

对 Wiki 已收录的同人文章，从论坛拉取最新内容，更新 .mw 文件（保留原有 Infobox，替换正文）。

## 触发条件

- "更新 TID XXXXX"
- "更新 XXXXX.mw"
- "update 22231"
- 从 diff-review 中选择更新

## 执行流程

### Step 1: 更新 Wiki 文章

```bash
python3 -m monitor.cli update <TID> --update-list
```

`--update-list` 会自动更新 `同人作品列表.mw` 中对应条目的「最近更新」日期。

### Step 2: 进入审阅

导入完成后，使用 review-article skill 进行交互式优化：

```
/review-article <文章名>
```

### Step 3: 确认并复制到 Wiki 仓库

TODO 重写此逻辑

## 注意事项

- 更新操作**保留**原有 Infobox 中的所有手动填写字段
- 仅自动更新「最近更新」日期
- 完结状态不会被更改
- 建议先 diff 审阅，确认内容变化合理后提交
