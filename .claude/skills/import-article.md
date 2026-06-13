---
name: import-article
description: 从论坛拉取指定帖子，转换为 MediaWiki 格式，保存到灰机 Wiki 仓库
---

# Import Article — 导入新文章到 Wiki

## 描述

从论坛拉取指定帖子（常规页面 + cookie），自动提取标题生成文章名，转换为 MediaWiki 格式，输出原始版和处理版两份文件。

## 触发条件

- "导入 thread-XXXXX"
- "导入 TID XXXXX"
- "导入帖子 XXXXX"
- "导入贴子 XXXXX"
- "导入新贴 XXXXX"
- "import 22231"
- 从 diff-review 中选择导入

## 执行流程

### Step 1: 拉取帖子并转换

```bash
python3 -m monitor.cli import <TID> --download-images
```

CLI 输出目录结构（按 `TID-文章名` 组织）：
```
output/<TID>-<文章名>/
├── text/
│   ├── <文章名>.raw.mw    — converter 原始输出，用于后续对比
│   └── <文章名>.mw         — 基础处理版（替换 {{PAGENAME}}、去除 <!--作者ID--> 注释）
└── img/
    └── <图片文件>          — 下载的附件图片
```

Converter 自动处理：
- 作者正文 → 保留为正文
- 其他用户回复 → 包裹 `{{同人注释start}}...{{同人注释end}}`
- 「XXX 发表于 HH:MM」行 → 删除
- 「本帖最后由 XXX 编辑」→ 删除
- `&nbsp;` → 空格
- 相邻高度重复楼层 → 去重跳过
- 附件图片 → 自动嵌入为 `[[File:xxx.jpg|600px]]`（需 `--download-images` 下载文件）
- 附件 UI 元素（下载链接、文件大小、上传时间）→ 自动清理

### Step 2: 进入审阅

导入完成后，使用 review-article skill 进行交互式优化：

```
/review-article <文章名>
```

### Step 3: 复制到 Wiki 仓库（审阅完成后）

```bash
cp output/<TID>-<文章名>/text/<NAME>.mw lgqm.huijiwiki.com/
cp output/<TID>-<文章名>/img/* lgqm.huijiwiki.com/   # 如有图片
cd lgqm.huijiwiki.com
git add <NAME>.mw
git commit -m "导入同人: <NAME>"
```

## 注意事项

- 爬取全文使用常规页面 + cookie 登录态（非 Archiver）
- 文章名称自动清理规则：去「【原创】」标签、去日期后缀（如 "5.14更新"）
- Infobox 中的「最近更新」字段填入当前日期
- 完结情况默认为「未完结」
