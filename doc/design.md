# 论坛同人监控与 Wiki 同步系统 — 设计文档

> 版本: 1.0 | 日期: 2026-06-07

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
│ fetcher.py  │  Archiver 模式拉取帖子（无需 cookie）
│             │  → Post 列表 + 图片下载
└─────────────┘
     │
     ▼
┌─────────────┐
│converter.py │  HTML → MediaWiki 标记 + Infobox 生成
│             │  → output/{filename}.mw
└─────────────┘
     │
     ▼ (人工审阅)
  复制 → huijiwiki 仓库 → git commit
```

### 2.2 模块职责

| 模块 | 文件 | 核心职责 |
|------|------|---------|
| 配置 | `config.py` | 统一配置，环境变量注入敏感信息 |
| 模型 | `models.py` | ForumThread, Post, WikiArticle, DiffReport |
| 工具 | `utils.py` | TID 提取, URL 解析, 日期处理, 日志 |
| 监控 | `monitor.py` | 扫描 forum-39, 解析 Discuz HTML, 提取帖子元数据 |
| 索引 | `indexer.py` | 解析 .mw 文件, 提取 Infobox 字段, 构建 TID 索引 |
| 对比 | `diff.py` | TID 匹配, 日期比较, 生成差异报告 |
| 拉取 | `fetcher.py` | Archiver 模式获取, 楼层解析, 图片下载 |
| 转换 | `converter.py` | HTML→Wiki 标记, Infobox 生成, 文件保存 |

---

## 3. 关键技术决策

### 3.1 内容获取：Discuz Archiver 模式

经过对三种内容获取方式的对比研究，选择 **Archiver 模式**作为主力：

| 模式 | HTML 清洁度 | 图片 | 需 Cookie | URL |
|------|------------|------|----------|-----|
| **Archiver** ⭐ | 极干净 | 无 | **否** | `/archiver/?tid-{tid}.html` |
| Printable | 中等(div 过多) | 有限 | 否 | `forum.php?mod=viewthread&action=printable` |
| 普通页面 | 复杂(JS/CSS 多) | 完整 | 是 | `thread-{tid}-{page}-1.html` |

**Archiver 结构**（每层楼）：
```html
<p class="author">
    <strong>作者名</strong>
    发表于 <span title="YYYY-M-D HH:MM:SS">时间</span>
</p>
<h3>帖子标题</h3>      ← 仅首楼
正文内容<br />
...
```

**优势**：
- 无需 cookie 即可获取内容（Archiver 公开访问）
- HTML 极简，仅 `<strong>`, `<br>`, `<a>` 等基础标签
- 代码量 ~100 行 vs 旧 lgqmtr 的 ~400 行递归解析
- 函数式 API 接口

### 3.2 图片处理：独立通道

Archiver 不含图片，需从常规页面单独下载（需要 cookie 登录态）。

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
fetcher.py   → Archiver 拉取 → Post[] 
converter.py → 格式转换     → .mw 文件
  ↓
复制到 huijiwiki 仓库 → git commit
  ↓
展示 .mw 供审阅
```

### 5.4 update-article — 更新文章

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
| `<img src="...">` | `[[Image:...]]` |
| `<blockquote>` | `{{同人注释start}}...{{同人注释end}}` |

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
