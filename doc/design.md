# 论坛同人监控与 Wiki 同步系统 — 设计文档

> 版本: 1.1 | 日期: 2026-06-13

---

## 1. 概述

### 1.1 背景

临高启明论坛（lgqmonline.top）「同人发布」板块（forum-39）持续有新同人作品发布，已有作品也会持续更新。灰机 Wiki（lgqm.huijiwiki.com）已收录约 267 篇同人作品，但缺乏自动化手段对比和发现差异。

### 1.2 目标

构建 Python 工具链 + Claude Code Skill 工作流，实现：

1. 自动扫描论坛同人板块，获取所有帖子列表
2. 索引 Wiki 已有同人文章，建立论坛帖→Wiki 文章映射
3. 对比发现：新帖（论坛有、Wiki 无）和更新帖（论坛有新回复）
4. 一键拉取帖子内容，转换为 MediaWiki 格式
5. 人工审阅后合入 Wiki 仓库

---

## 2. 架构设计

### 2.1 数据流

```
forum-39 (Discuz X3.4)
     │
     ▼
┌─────────────┐
│  monitor.py │  扫描板块页面（60页），提取帖子元数据
│             │  → data/threads_index.json
└─────────────┘
     │
     ▼
┌─────────────┐
│ indexer.py  │  解析 Wiki 的 .mw 文件，提取 Infobox TongRen
│             │  → data/wiki_index.json
└─────────────┘
     │
     ▼
┌─────────────┐
│   diff.py   │  对比两个索引，按 TID 匹配
│             │  → data/diff_report.json
└─────────────┘
     │
     ▼ (人工审阅)
┌─────────────┐
│ fetcher.py  │  常规页面拉取帖子（cookie）+ 附件图片
│             │  Archiver 模式兜底（无需 cookie）
│             │  → Post 列表 + 图片文件
└─────────────┘
     │
     ▼
┌─────────────┐
│converter.py │  HTML → MediaWiki 标记 + Infobox 生成
│             │  附件图片 <img file> → [[File:xxx.jpg|600px]]
│             │  → output/{filename}.raw.mw + .mw
└─────────────┘
     │
     ▼ (人工审阅)
┌─────────────┐
│ review skill│  补全 Infobox → 格式化章节 → 清理注释
│             │  → 对比差异 → 嵌入图片引用
└─────────────┘
     │
     ▼ (人工审阅)
  复制 → huijiwiki 仓库 → git commit
```

### 2.2 模块职责

| 模块 | 文件 | 核心职责 |
|------|------|---------|
| 配置 | `config.py` | 统一配置，环境变量注入敏感信息 |
| 认证 | `auth.py` | 论坛登录获取 cookie，支持静态/动态 cookie |
| 模型 | `models.py` | ForumThread, Post, WikiArticle, DiffReport |
| 工具 | `utils.py` | TID 提取, URL 解析, 日期处理, 日志 |
| 监控 | `monitor.py` | 扫描 forum-39, 解析 Discuz HTML, 提取帖子元数据 |
| 索引 | `indexer.py` | 解析 .mw 文件, 提取 Infobox 字段, 构建 TID 索引 |
| 对比 | `diff.py` | TID 匹配, 日期比较, 生成差异报告 |
| 拉取 | `fetcher.py` | 常规页面 + Archiver 双模式, 楼层解析, 附件图片下载 |
| 转换 | `converter.py` | HTML→Wiki 标记, 图片嵌入, Infobox 生成, 文件保存 |
| CLI | `cli.py` | 命令行入口: import, fetch-images, review-info 等 |

---

## 3. 关键技术决策

### 3.1 内容获取：双模式策略

优先使用常规页面（cookie 登录，功能完整），Archiver 模式作为兜底：

| 模式 | HTML 清洁度 | 图片附件 | 需 Cookie | URL |
|------|------------|---------|----------|-----|
| **常规页面** ⭐ | 中等 | **完整** | 是 | `thread-{tid}-{page}-1.html` |
| Archiver | 极干净 | 无 | 否 | `/archiver/?tid-{tid}.html` |

**常规页面**通过 cookie 登录获取完整帖子内容（含附件图片的 `<div class="pattl">`），Archiver 模式在 cookie 不可用时自动回退。

### 3.2 图片处理：内联转换

v1.1 重大改进：附件图片不再作为独立下载通道，而是在内容拉取时一并捕获，由 converter 自动内联转换。

**流程**：
1. `fetcher._fetch_thread_regular()` 提取 `div.t_fsz`（包含正文 `td.t_f` + 附件 `div.pattl`）
2. `converter.html_to_wiki()` 识别 `<img file="...">` 和 `<img zoomfile="...">` 标签
3. 自动转换为 `[[File:xxx.jpg|600px]]`，清理附件 UI 残留（下载链接、文件大小、上传时间）
4. `fetch_images()` 并行下载实际图片文件到 `img/{tid}/`

**优势**：图片引用自动嵌入到帖子中的正确位置，无需人工定位插入点。

### 3.3 差异检测算法

- **匹配依据**：论坛帖子 TID ↔ Wiki Infobox `官坛原帖` 中提取的 TID
- **URL 域名兼容**：`lgqmonline.top`, `lgqmonline.top`, `lgqmonline.top`, `lgqmonline.top`
- **更新判断**：论坛 `last_reply_date` > Wiki `最近更新` 日期
- **新帖**：TID 未在 Wiki 索引中找到
- **反向检查**：Wiki 已收录但论坛板块中找不到的（可能域名迁移或已删除）

---

## 4. 数据模型

### ForumThread（论坛帖子）
```
tid, title, author, author_uid, post_date,
last_reply_date, reply_count, view_count,
url, is_sticky, is_newcomer
```

### WikiArticle（Wiki 文章）
```
filename, title, forum_url, forum_tid,
first_publish, last_update, is_completed, author
```

### DiffReport（差异报告）
```
scan_time, summary{total_forum_threads, total_wiki_articles,
new_threads, updated_threads, possible_matches},
new_items[], updated_items[], possible_matches[]
```

---

## 5. Claude Code Skill 工作流

### 5.1 monitor-forum — 论坛监控

```
用户: "监控论坛"
  ↓
monitor.py → scan forum-39 → threads_index.json
indexer.py → parse wiki .mw → wiki_index.json
diff.py    → compare        → diff_report.json
  ↓
展示摘要: N 新帖, M 更新, K 疑似
```

### 5.2 diff-review — 差异审阅

```
用户: "查看差异"
  ↓
读取 diff_report.json
  ↓
分类展示详情（新帖/更新/疑似）
  ↓
用户标记: skip / import / update / open
```

### 5.3 import-article — 导入文章

```
用户: "导入 <tid>"
  ↓
fetcher.py   → 常规页面拉取（含附件） → Post[] 
converter.py → 格式转换（图片自动嵌入） → .raw.mw + .mw
fetch_images → 下载图片文件 → img/{tid}/
  ↓
进入 review-article 审阅优化
```

### 5.4 review-article — 审阅优化

```
用户: "审阅 <文章名>"
  ↓
Step 1: review-info → 空白 Infobox 字段、章节标记、注释统计
Step 2: 交互式优化:
  - 2a: 补全 Infobox（地点、涉及方面、内容关键字、图像）
  - 2b: 格式化章节标题（=== 第X章 标题 ===）+ __TOC__
  - 2c: 边界检查（去重、去无意义、清理残留）
  - 2d: 清理 &nbsp;、压缩空行、替换 {{PAGENAME}}
Step 3: diff -u 对比差异
Step 4: 复制到 Wiki 仓库 → git commit
```

### 5.5 update-article — 更新文章

```
用户: "更新 <tid>"
  ↓
读取现有 .mw → 保留 Infobox 头部
fetcher.py   → Archiver 拉取最新内容
converter.py → update_existing_wiki()
  ↓
展示 diff → 用户确认 → git commit
```

---

## 6. 文件格式参考

### 6.1 Infobox TongRen 模板

```mediawiki
{{同人作品版权声明}}
{{Infobox TongRen
| 同人作品 = {{PAGENAME}}
| 官坛原帖 = [https://lgqmonline.top/thread-{tid}-1-1.html 帖子标题]
| 官方论坛 = <!--作者ID-->作者名
| 首次发布 = 2026-06-07
| 最近更新 = 2026-06-07
| 完结情况 = 未完结
| ...
}}
{{首行缩进start}}
正文内容...
{{首行缩进end}}
[[分类:同人作品]]
```

### 6.2 Wiki 格式转换规则

| HTML | MediaWiki |
|------|-----------|
| `<br />` | 换行 |
| `<strong>text</strong>` | `'''text'''` |
| `<a href="url">text</a>` | `[url text]` |
| `<img file="xxx.jpg">` | `[[File:xxx.jpg\|600px]]` |
| `<img zoomfile="xxx.jpg">` | `[[File:xxx.jpg\|600px]]` |
| `<img src="...">` | `[[Image:...]]` |
| 附件下载/大小/时间 | 自动清理 |
| 「XXX 发表于 HH:MM」 | 自动删除 |
| `&nbsp;` | 空格 |

---

## 7. 安全注意事项

- Cookie/密码通过环境变量或 `data/local.json` 注入，不纳入 Git
- `data/`, `html/`, `img/`, `output/` 加入 `.gitignore`
- 论坛请求间隔 ≥ 2 秒，避免被封
- 图片下载仅在需要时进行（单独步骤）

---

## 8. 附录

### 论坛 URL 格式参考

| 类型 | 格式 | 示例 |
|------|------|------|
| 板块列表 | `forum-{fid}-{page}.html` | `forum-39-1.html` |
| 帖子（常规） | `thread-{tid}-{page}-1.html` | `thread-22231-1-1.html` |
| 帖子（Archiver） | `/archiver/?tid-{tid}.html` | `/archiver/?tid-22231.html` |
| 帖子（老格式） | `forum.php?mod=viewthread&tid={tid}` | `forum.php?mod=viewthread&tid=1449` |
| 用户空间 | `space-uid-{uid}.html` | `space-uid-19550.html` |

### Wiki URL 格式参考

Discuz 论坛链接在 Wiki 中可能以多种域名出现：
- `lgqmonline.top`（当前主域名）
- `lgqmonline.top` / `lgqmonline.top`（旧域名）
- `lgqmonline.top`（已废弃域名）
