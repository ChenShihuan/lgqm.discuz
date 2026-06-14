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

### Step 0: 预分析目录结构（推荐）

对含有目录页的帖子（如《面首》《澳宋大调查》），预分析可显著提升章节检测精度。

1. 运行预分析命令，拉取前几层楼并格式化为可读文本：

   ```bash
   python3 -m monitor.cli preanalyze <TID>
   ```

2. 命令会输出 `pre_analysis.txt` 的路径。**读取该文件**，分析前几层楼中是否存在目录（TOC）。

   查找以下模式：
   - **标准格式**：`[url pid=数字 章节名]` — 目录中含精确的楼层链接
   - **自由格式**：某楼层含「目录」标记 + 楼层号/章节名列表
   - **纯章节列表**：有序或无编号的章节名罗列（如《面首》的 `《临高启明》同人《面首·十》` 等）
   - **无目录**：前几层楼均为正文内容，无需预分析

3. 若检测到目录，将结果保存为 JSON 文件（路径在 `preanalyze` 输出中会显示，通常为 `output/<TID>-<文章名>/toc_analysis.json`）：

   ```json
   {
     "thread_tid": <TID>,
     "source_floor": <含目录的楼层号>,
     "format": "pid_links | freeform_list | numbered",
     "entries": [
       {"floor": 楼层号或null, "pid": "532627258或null", "chapter_name": "章节名"},
       ...
     ]
   }
   ```

   字段说明：
   - `source_floor`: 包含目录的楼层号
   - `format`: TOC 格式类型
   - `entries[].floor`: 章节对应的楼层号（如能确定），否则 `null`
   - `entries[].pid`: 章节对应的 PID 数字部分（如能确定），否则 `null`
   - `entries[].chapter_name`: 章节名称

4. 若**未检测到目录**：跳过此步，直接进入 Step 1。无需生成 `toc_analysis.json`。

### Step 1: 拉取帖子并转换

若 Step 0 生成了 `toc_analysis.json`，传入 `--toc-file` 参数：

```bash
python3 -m monitor.cli import <TID> --download-images --toc-file output/<TID>-<文章名>/toc_analysis.json
```

否则使用默认流程（自动从首楼检测目录）：

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
- 论坛内置表情 → 自动过滤（static/image/smiley + static/image/common）

### Step 2: 进入审阅

导入完成后，使用 review-article skill 进行交互式优化（含段落格式化、章节标题转换、同人注释过滤、重复检测等）：

```
/review-article <文章名>
```

### Step 3: 审阅完成后的处理

#### 3a: 字数统计

审阅完成后，统计正文中文字数并写入 Infobox：

```bash
python3 -m monitor.cli word-count <TARGET_DIR>/text/<NAME>.mw
```

#### 3b: 复制到 Wiki 仓库

```bash
# TARGET_DIR 为 TARGET 的父目录（如 output/22085-淞沪启明同人/）
cp <TARGET_DIR>/text/<NAME>.mw lgqm.huijiwiki.com/
cp <TARGET_DIR>/img/* output/img_sum/ 2>/dev/null  # 如有图片，单独汇总上传
```

> **注意**: `TARGET_DIR` 为 `TARGET` 所在目录（`dirname TARGET`），内含 `text/` 和 `img/` 子目录。

复制完成后，更新同人作品列表：

```bash
python3 -c "
from monitor.index_list import update_from_mw_file
action, seq, name = update_from_mw_file('<TARGET_DIR>/text/<NAME>.mw')
print(f'作品列表已{action}: #{seq} [[{name}]]')
"
```

> 作品列表在审阅完成后更新，确保 Infobox 信息已补全再写入列表。

## 注意事项

- 爬取全文使用常规页面 + cookie 登录态（非 Archiver）
- 文章名称自动清理规则：去「【原创】」标签、去日期后缀（如 "5.14更新"）
- Infobox 中的「最近更新」字段填入当前日期
- 完结情况默认为「未完结」
