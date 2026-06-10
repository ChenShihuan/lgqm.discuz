# Update Article — 更新已有 Wiki 文章

## 描述

对 Wiki 已收录的同人文章，从论坛拉取最新内容，更新 .mw 文件（保留原有 Infobox，替换正文）。

## 触发条件

- "更新 TID XXXXX"
- "更新 XXXXX.mw"
- "update 22231"
- 从 diff-review 中选择更新

## 执行流程

### Step 1: 确定目标文章

通过 TID 在 wiki_index.json 中找到对应的 Wiki 文章，确认其存在并查看当前状态。

### Step 2: 读取现有 Wiki 文章

读取 .mw 文件，提取 Infobox 头部（保留所有手动填写字段）。

### Step 3: 拉取最新内容

使用 fetcher.py 的 Archiver 模式拉取全帖最新内容。

### Step 4: 生成更新版

使用 converter.py 的 `update_existing_wiki()` 函数：
- 保留原有 Infobox（图像、地点、关键字等）
- 自动更新「最近更新」日期
- 正文替换为最新论坛内容

### Step 5: 展示差异

对比新旧 .mw 文件，展示差异供用户审阅。

### Step 6: 确认提交

用户确认后，将更新文件覆盖到 Wiki 仓库并 `git commit`。

## 注意事项

- 更新操作**保留**原有 Infobox 中的所有手动填写字段
- 仅自动更新「最近更新」日期
- 完结状态不会被更改
- 建议先 diff 审阅，确认内容变化合理后提交
