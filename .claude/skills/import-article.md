---
name: import-article
description: 从论坛拉取指定帖子，转换为 MediaWiki 格式，保存到灰机 Wiki 仓库
---

# Import Article — 导入新文章到 Wiki

## 描述

从论坛拉取指定帖子，转换为 MediaWiki 格式，保存到灰机 Wiki 仓库。

## 触发条件

- "导入 thread-XXXXX"
- "导入 TID XXXXX"
- "import 22231"
- 从 diff-review 中选择导入

## 执行流程

### Step 1: 拉取帖子并转换

```bash
python3 -m monitor.cli import <TID>
```

如需同时下载图片：

```bash
python3 -m monitor.cli import <TID> --download-images
```

### Step 2: 单独下载图片（可选）

```bash
python3 -m monitor.cli fetch-images <TID>
```

### Step 3: 复制到 Wiki 仓库

```bash
# 找到生成的 .mw 文件
MW_FILE=$(ls -t output/*.mw | head -1)
echo "生成的文件: $MW_FILE"

# 复制到 Wiki 仓库
cp "$MW_FILE" lgqm.huijiwiki.com/
echo "已复制到 Wiki 仓库"

# 提交
cd lgqm.huijiwiki.com
git add "$(basename "$MW_FILE")"
git commit -m "导入同人: $(basename "$MW_FILE" .mw)"
echo "已提交到 Git"
```

### Step 4: 展示供审阅

展示生成的 .mw 文件内容的关键部分（Infobox + 前 300 字正文），让用户确认格式正确。

## 注意事项

- 如果帖子标题能提取到，优先使用帖子标题作为文件名
- Infobox 中的「最近更新」字段填入当前日期
- 完结情况默认为「未完结」
- 图片下载需要有效的 cookie
