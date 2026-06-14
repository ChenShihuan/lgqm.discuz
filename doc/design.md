# 论坛同人监控与 Wiki 同步系统 — 设计文档

> 版本: 2.0 | 日期: 2026-06-14

---

## 1. 概述

### 1.1 背景

临高启明论坛（lgqmonline.top）「同人发布」板块（forum-39）持续有新同人作品发布和更新。灰机 Wiki（lgqm.huijiwiki.com）已收录约 1200 篇同人作品。论坛启用了 Cloudflare JS 挑战反爬（`_dsig` 签名验证），纯 HTTP 请求无法获取帖子详情页。

### 1.2 目标

构建 Python 工具链 + Claude Code Skill + VS Code 扩展工作流，实现全链路自动化。

---

## 2. 架构设计

### 2.1 数据流（v2.0）

```
forum-39 (Discuz X3.4 + Cloudflare)
     │
     ├─ requests (板块列表，无 JS 挑战)
     │  └─ ForumSession (浏览器指纹头 + Cookie 持久化)
     │
     ├─ Playwright headless Chromium (帖子详情，绕过 _dsig)
     │  └─ pw_fetcher.py (浏览器单例 + Cookie 注入)
     │
     ▼
┌─────────────┐
│  monitor.py │  扫描板块页面，提取帖子元数据 → data/threads_index.json
└─────────────┘
     │
     ▼
┌─────────────┐
│ indexer.py  │  解析 Wiki .mw 文件，提取 Infobox 字段 → data/wiki_index.json
└─────────────┘
     │
     ▼
┌─────────────┐
│   diff.py   │  TID 匹配 + 标题匹配 + 日期比较 → data/diff_report.json
└─────────────┘
     │
     ├─ WebUI 看板 (webui/)
     │  └─ 分类浏览、队列管理、Wiki 预览、论坛代理
     │
     ├─ VS Code 扩展 (lgqm-wiki-helper/)
     │  └─ 状态栏入口 + .mw 预览按钮
     │
     ▼ (人工审阅)
┌──────────────┐
│  fetcher.py  │  Playwright 拉取帖子 + 附件图片 → Post[]
└──────────────┘
     │
     ▼
┌──────────────┐
│ converter.py │  HTML → Wiki 标记 + Infobox + 章节检测 + Q&A 回复格式
│              │  → output/{tid}-{name}/text/{name}.raw.mw + .mw
└──────────────┘
     │
     ▼
┌──────────────┐
│ pw_fetcher   │  pw_parse_wikitext() → Wiki API 渲染预览
│ (preview)    │  → iframe srcdoc 完整渲染（含内联 CSS + <base>）
└──────────────┘
     │
     ▼ (人工审阅)
  复制 → huijiwiki 仓库 → git commit / mw_push.py
```

### 2.2 模块职责

| 模块 | 文件 | 核心职责 |
|------|------|---------|
| 配置 | `config.py` | 统一配置，环境变量注入，目录路径函数 |
| HTTP 会话 | `session.py` | ForumSession 单例：浏览器指纹头、Cookie pickle 持久化、自动 Referer + Sec-Fetch-* |
| 认证 | `auth.py` | 委托给 ForumSession，保持旧 API 兼容 |
| Playwright | `pw_fetcher.py` | 浏览器单例、Cookie 注入登录态、JS 挑战自动绕过、Wiki API 预览 |
| 模型 | `models.py` | ForumThread, Post, WikiArticle, DiffReport |
| 工具 | `utils.py` | TID 提取、URL 解析、日期处理、速率限制（含 ±30% 抖动） |
| 监控 | `monitor.py` | 扫描 forum-39，Referer 链 + 翻页延迟 |
| 索引 | `indexer.py` | 解析 .mw 文件，提取 Infobox，多 TID 支持 |
| 对比 | `diff.py` | TID 匹配、日期比较、标题匹配搬运文章 |
| 拉取 | `fetcher.py` | Playwright 驱动拉取帖子和图片，章节日期追踪 |
| 转换 | `converter.py` | HTML→Wiki 标记，章节自动检测，Q&A 回复格式（读者: — 作者）|
| 列表维护 | `index_list.py` | 同人作品列表追加/更新/序号校正/分卷识别 |
| Wiki 推送 | `mw_push.py` | MediaWiki API 直接推送，绕过 git-remote-mediawiki |
| CLI | `cli.py` | 命令行入口：import, update, review-info, webui, renumber-list 等 |
| WebUI | `webui/` | HTTP 看板 + API（报告/队列/跳过/预览/扫描） |
| 扩展 | `lgqm-wiki-helper/` | VS Code 扩展：状态栏面板按钮 + .mw 预览 |

---

## 3. 关键技术决策

### 3.1 反爬绕过：Phase A（Header 修复）+ Phase B（Playwright）

论坛对板块列表页和帖子详情页采用不同级别的反爬保护：

| 页面 | 反爬级别 | 方案 |
|------|---------|------|
| forum-39-1.html（板块列表） | 指纹检测 | requests + 完整浏览器头 + Referer 链 |
| thread-XXX-1.html（帖子详情） | JS 挑战 (_dsig) | Playwright headless Chromium |
| archiver/?tid-XXX.html（Archiver） | JS 挑战 | 已废弃（不含图片，不适合导入） |

**Phase A 成果**：
- 补全 `Sec-Fetch-*`、`Sec-CH-UA`、`Accept-Encoding` 等浏览器指纹头
- Referer 链模拟浏览流（首页 → 板块 → 帖子）
- Cookie pickle 持久化（`data/cookies.pkl`），二次启动跳过登录
- 请求速率 ±30% 抖动

**Phase B 成果**：
- Playwright 浏览器单例（`pw_fetcher.py`），自动解决 `_dsig` 签名
- Cookie 从 requests.Session 注入 Playwright context（保持登录态）
- 帖子拉取 ~3s/页，渲染正确

### 3.2 章节自动检测

导入时自动识别章节：

| 楼层类型 | 判断条件 | 输出格式 |
|---------|---------|---------|
| 作者正文（≥200 字，无引用） | 无 blockquote + 长度 ≥ 200 | `== 首行标题 ==` |
| 作者回复读者 | 含 `<blockquote>` | `{{同人注释start}}读者: 问题\n— 作者回复{{同人注释end}}` |
| 作者短内容（<200 字） | 无引用 + 长度 < 200 | `{{同人注释start}}...{{同人注释end}}` |
| 非作者回复 | 非作者 | `{{同人注释start}}...{{同人注释end}}` |

### 3.3 Infobox 日期追踪

| 字段 | 来源 | 示例 |
|------|------|------|
| 首次发布 | 论坛首楼日期 | `2023-12-20` |
| 最近更新 | 最新作者章节日期（排除回复帖） | `2026-06-04` |

### 3.4 Wiki 预览渲染

```
wikitext → POST /api/preview → Playwright 访问 huijiwiki API (action=parse)
         → 提取 headhtml + body → 内联模板 CSS + <base> → 完整 HTML 文档
         → iframe srcdoc 渲染
```

内联 CSS 覆盖：Infobox、同人注释、版权声明、首行缩进、目录、MediaWiki 标准样式。

### 3.5 WebUI 看板架构

```
webui/server.py (HTTP 1.0, Python stdlib)
├── /                  → index.html (监控看板)
├── /preview.html      → Wiki 在线预览
├── /proxy/thread-XXX  → 论坛页面代理（Playwright + Cookie）
├── /api/report        → 差异报告（含分类 + 跳过 + 队列标记）
├── /api/preview       → wikitext 渲染为 HTML (POST)
├── /api/wiki          → Wiki 文章列表
├── /api/queue         → 导入队列 CRUD
├── /api/skipped       → 跳过列表 CRUD
├── /api/scan          → 触发重新扫描
└── /api/import/<tid>  → 触发导入
```

### 3.6 VS Code 扩展

纯 JS 扩展（无需编译），通过软链安装：

```
lgqm-wiki-helper/
├── package.json  → activationEvents: onStartupFinished, contributes.commands, menus
└── extension.js  → 状态栏按钮 + .mw 预览命令
```

- 状态栏 `📊 监控面板`：`vscode.window.createWebviewPanel` + iframe 加载 WebUI
- .mw 预览：`POST /api/preview` → WebView srcdoc iframe

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
filename, title, forum_url, forum_tid, forum_tids[],
first_publish, last_update, is_completed, author
```

### DiffReport（差异报告）
```
scan_time, summary{total_forum_threads, total_wiki_articles,
new_threads, updated_threads, possible_matches,
new_standard, new_other, new_video, skipped_count, queue_count},
new_items[], updated_items[], possible_matches[]
```

---

## 5. Claude Code Skill 工作流

### 5.1 monitor-forum

```
用户: "监控论坛"
  ↓
monitor.py → scan forum-39 → threads_index.json
indexer.py → parse wiki .mw → wiki_index.json
diff.py    → compare        → diff_report.json
  ↓
展示摘要: N 新帖, M 更新, K 疑似
```

### 5.2 import-article

```
用户: "导入 <tid>"
  ↓
fetcher.py   → Playwright 拉取（含附件） → Post[] 
converter.py → 格式转换 + 章节检测 + Q&A 格式 → .raw.mw + .mw
index_list   → 更新同人作品列表
  ↓
进入 review-article 审阅优化
```

### 5.3 review-article

```
用户: "审阅 <文章名>"
  ↓
Step 1: review-info → 空白 Infobox 字段、章节标记、注释统计、重复检测
Step 2: 交互式优化:
  2a: 补全 Infobox（地点、涉及方面、内容关键字、图像）
  2b: 格式化章节标题 + __TOC__
  2c: 同人注释过滤（should_keep 脚本）
  2d: 段落格式化（长空格→换行、smiley 清理、\xa0 清理）
  2e: 更新文章专项（增量合并、指纹去重）
Step 3: diff -u 对比差异
Step 4: 复制到 Wiki 仓库
```

### 5.4 update-article

```
用户: "更新 <tid>"
  ↓
读取现有 .mw → 保留 Infobox + 正文
fetcher.py   → Playwright 拉取最新内容
converter.py → update_existing_wiki() 增量追加
  ↓
展示 diff → 用户确认
```

### 5.5 import-queue

```
用户: "/import-queue"
  ↓
读取 data/import_queue.json
  ↓
逐篇: CLI import → review-article → 复制到 Wiki
  ↓
清空队列 → 输出汇总
```

---

## 6. 文件格式参考

### 6.1 Infobox TongRen 模板

```mediawiki
{{同人作品版权声明}}
{{Infobox TongRen
| 同人作品 = {{PAGENAME}}
| 官坛原帖 = [https://lgqmonline.top/thread-{tid}-1-1.html 帖子标题]
| 官方论坛 = 作者名
| 首次发布 = 2023-12-20
| 最近更新 = 2026-06-04
| 地点 = 越南
| 涉及方面 = 军事、工业、外交、殖民
| 内容关键字 = 越南攻略, 骑兵, 红河公司
| 完结情况 = 未完结
| ...
}}
{{首行缩进start}}
__TOC__

正文内容...
{{首行缩进end}}
[[分类:同人作品]]
```

### 6.2 同人注释格式

```mediawiki
{{同人注释start}}
读者名: 引用的内容
— 楼主的回复内容
{{同人注释end}}
```

### 6.3 Wiki 格式转换规则

| HTML | MediaWiki |
|------|-----------|
| `<br />` | 换行 |
| `<strong>text</strong>` | `'''text'''` |
| `<a href="url">text</a>` | `[url text]` |
| `<img file="xxx.jpg">` | `[[File:xxx.jpg\|600px]]` |
| `<img zoomfile="xxx.jpg">` | `[[File:xxx.jpg\|600px]]` |
| `<blockquote>` 作者回复 | Q&A 同人注释格式 |
| 附件下载/大小/时间 | 自动清理 |
| 「XXX 发表于 HH:MM」 | 自动删除 |
| `&nbsp;` | 空格 |
| `static/image/smiley/` | 自动过滤 |

---

## 7. 性能与安全

- Cookie 通过 pickle 持久化，避免重复登录
- Playwright 浏览器单例，复用 context
- 请求节流 + 随机抖动，避免触发反爬
- 板块列表用 requests（快速），帖子详情用 Playwright（绕过 _dsig）
- 图片下载用 requests（无 JS 挑战）
- WebUI 预览缓存：灰机 API 响应由 wiki 端缓存 24 小时
- `data/`, `output/`, `*.pkl` 加入 `.gitignore`

## 8. 附录

### 论坛 URL 格式参考

| 类型 | 格式 | 示例 |
|------|------|------|
| 板块列表 | `forum-{fid}-{page}.html` | `forum-39-1.html` |
| 帖子（常规） | `thread-{tid}-{page}-1.html` | `thread-22231-1-1.html` |
| 帖子（Archiver） | `/archiver/?tid-{tid}.html` | `/archiver/?tid-22231.html` |

### Wiki API 端点

| 用途 | 端点 |
|------|------|
| Wikitext 渲染 | `POST /api.php?action=parse` |
| API 沙盒 | `Special:ApiSandbox` |
| 页面渲染 | `?action=render` |
