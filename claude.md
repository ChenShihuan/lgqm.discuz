# lgqm.discuz — 临高启明论坛同人监控与 Wiki 同步系统

本代码库用于从临高启明论坛拉取待更新同人，论坛地址 https://lgqmonline.top/，论坛基于 Discuz X3.4 部署。

## 功能概览

| 功能 | 说明 |
|------|------|
| **论坛监控** | 扫描「同人发布」板块（forum-39），对比 Wiki 已有文章，发现新帖和更新帖 |
| **文章导入** | Playwright 驱动从论坛拉取指定帖子，转换为 MediaWiki 格式，下载附件图片 |
| **文章审阅** | 交互式优化 .mw 文件：补全 Infobox、格式化章节标题、清理同人注释 |
| **文章更新** | 增量追加模式更新已有 Wiki 文章 |
| **Wiki 预览** | 通过灰机 Wiki API 渲染 wikitext 为 HTML，支持 VS Code 内预览 |
| **WebUI 看板** | 本地 HTTP 看板：差异浏览、分类筛选、导入队列、Wiki 文章列表 |
| **VS Code 扩展** | 状态栏监控面板入口 + .mw 文件一键预览按钮 |

## 目录结构

```
lgqm.discuz/
├── monitor/                # 核心 Python 模块
│   ├── config.py           # 统一配置
│   ├── models.py           # 数据模型
│   ├── utils.py            # 工具函数（日期解析、日志、速率限制含抖动）
│   ├── auth.py             # 论坛登录认证（委托给 session.py）
│   ├── session.py          # 集中式 HTTP 会话：浏览器指纹头、Cookie pickle 持久化
│   ├── monitor.py          # 论坛板块扫描（Referer 链 + 翻页延迟）
│   ├── indexer.py          # Wiki 文章索引（多 TID 支持）
│   ├── diff.py             # 差异对比 + 标题匹配搬运文章
│   ├── fetcher.py          # 内容拉取（Playwright 驱动，自动 JS 挑战绕过）
│   ├── pw_fetcher.py       # Playwright 浏览器单例 + Wiki wikitext→HTML 预览
│   ├── converter.py        # 格式转换（HTML → MediaWiki）+ 章节自动检测 + Q&A 回复格式
│   ├── index_list.py       # 同人作品列表维护（追加/更新/序号校正/分卷识别）
│   ├── mw_push.py          # 直接通过 MediaWiki API 推送变更（绕过 git-remote-mediawiki）
│   └── cli.py              # 命令行入口
├── webui/                  # WebUI 看板
│   ├── server.py           # HTTP 服务器（静态文件 + API 路由 + 论坛代理）
│   ├── index.html          # 监控看板：更新帖/新帖/疑似匹配/Wiki 文章 + 队列 + 预览入口
│   ├── preview.html        # Wiki 在线预览编辑器（左侧编辑 + 右侧 srcdoc iframe 渲染）
│   └── api/__init__.py     # API 路由：/api/report, /api/preview, /api/queue, /api/skipped 等
├── lgqm-wiki-helper/       # VS Code 扩展（纯 JS，无需编译）
│   ├── package.json
│   └── extension.js        # 状态栏监控面板按钮 + .mw 预览命令
├── .claude/                # Claude Code 配置
│   ├── commands/           # 斜杠命令
│   └── skills/             # Skills（monitor-forum, import-article, review-article, update-article, import-queue）
├── .vscode/
│   └── tasks.json          # 快捷任务：启动 WebUI
├── data/                   # 运行时数据（gitignore）
│   ├── local.json          # 论坛凭据（不纳入版本控制）
│   ├── cookies.pkl         # 持久化 cookie（跳过重复登录）
│   ├── threads_index.json  # 论坛帖子索引
│   ├── wiki_index.json     # Wiki 文章索引
│   └── diff_report.json    # 差异报告
├── doc/                    # 设计文档
│   └── design.md
├── output/                 # 输出文件（按 TID-文章名 组织）
│   └── {tid}-{name}/
│       ├── text/           # {name}.raw.mw + {name}.mw
│       └── img/            # 附件图片
├── lgqm.huijiwiki.com/     # 灰机 Wiki 仓库（git-mediawiki remote）
├── lgqmtr/                 # 旧代码（参考）
└── requirements.txt
```

## 安装与配置

```bash
pip install -r requirements.txt
playwright install chromium
```

> WSL 无 sudo 时 Chromium 依赖库需手动提取到 `/tmp/chromium_libs/`，`pw_fetcher.py` 已在导入时自动设置 `LD_LIBRARY_PATH`。

配置认证信息（二选一）：

1. 创建 `data/local.json`：
```json
{
    "username": "你的论坛用户名",
    "password": "你的论坛密码"
}
```

2. 或通过环境变量：
```bash
export LGQM_USERNAME="用户名"
export LGQM_PASSWORD="密码"
```

Cookie 自动 pickle 持久化到 `data/cookies.pkl`，二次启动跳过登录。

## 使用方式

### Claude Code Skills（推荐）

| 触发词 | 功能 |
|-------|------|
| "监控论坛" | 扫描 forum-39，对比 Wiki，生成差异报告 |
| "查看差异" | 浏览差异报告详情，选择导入/更新 |
| "导入 \<tid\>" | Playwright 拉取帖子 + 下载图片，生成 .raw.mw + .mw |
| "审阅 \<文章名\>" | 交互式优化：补全 Infobox、格式化章节、清理注释、段落格式化 |
| "更新 \<tid\>" | 增量更新已有 Wiki 文章的正文内容 |
| "/import-queue" | 读取队列 → 分派 DeepSeek subagent 并行执行完整导入+审阅+定稿 |
| "/ds \<任务\>" | 显式派工给 DeepSeek subagent（绕过自动决策） |

### VS Code 扩展

安装：
```bash
ln -s /mnt/e/code/lgqm.discuz/lgqm-wiki-helper ~/.vscode-server/extensions/lgqm-wiki-helper
```
重载 VS Code（`Ctrl+Shift+P` → `Developer: Reload Window`）后：
- 状态栏 `📊 监控面板`：VS Code 内嵌标签页打开 WebUI
- 编辑器标题栏 `🔍 预览`：当前 .mw 文件一键 Wiki 渲染

### CLI 命令

```bash
# WebUI 看板
python3 -m monitor.cli webui

# 导入新文章（含图片下载 + 作品列表更新）
python3 -m monitor.cli import <TID> --download-images --update-list

# 审阅原始文件
python3 -m monitor.cli review-info output/<TID>-<文章名>/text/<NAME>.raw.mw

# 更新已有文章
python3 -m monitor.cli update <TID> --download-images --update-list

# 校正作品列表序号
python3 -m monitor.cli renumber-list

# 标题匹配搬运文章
python3 -m monitor.cli match-titles --dry-run    # 仅预览
python3 -m monitor.cli match-titles --apply      # 实际更新

# 快速推送变更到 Wiki（绕过 git-remote-mediawiki）
python3 -m monitor.mw_push
```

### Python API

```python
from monitor.fetcher import fetch_thread, fetch_images
from monitor.converter import convert_thread_to_wiki, save_wiki_file

posts = fetch_thread(22231, verbose=True)
images = fetch_images(22231, verbose=True)
wiki_content = convert_thread_to_wiki(posts, metadata={
    "title": "文章标题", "author": "作者",
    "forum_url": "https://lgqmonline.top/thread-22231-1-1.html",
})
save_wiki_file(wiki_content, "output_filename", tid=22231)
```

### Wiki 预览

```python
from monitor.pw_fetcher import pw_parse_wikitext
html = pw_parse_wikitext("'''bold''' [[link]]")
# 返回完整 HTML 文档（含内联 CSS + <base>），可在 iframe srcdoc 中渲染
```

也可通过 API：
```bash
curl -X POST http://127.0.0.1:8080/api/preview --data-binary "@file.mw"
```

### git-mediawiki 拉取

lgqm.huijiwiki.com 仓库当中拉取更新，应当采用如下指令：

```bash
git rebase refs/remotes/origin/master
```

已启用 `remote.origin.shallow = true` 加速 fetch。git push 慢的问题可用 `monitor.mw_push.py` 绕过。

## 工作流

```
论坛监控 → 差异审阅 → 导入文章(.raw.mw) → 审阅优化(.mw) → 预览确认 → 复制到 Wiki 仓库
                                   ↗ 批量导入可并行分派 DeepSeek subagent ↓
```

1. **监控**：扫描 forum-39 → 对比 Wiki 索引 → 差异报告
2. **导入**：Playwright 拉取帖子 + 下载图片 → 转换 Wiki 格式 → `.raw.mw`（原始）+ `.mw`（基础处理）
3. **审阅**：补全 Infobox → 格式化章节标题 → 清理同人注释 → 段落格式化 → 对比差异
4. **预览**：VS Code 内一键预览 / `preview.html` / `pw_parse_wikitext()` API
5. **提交**：复制 `.mw` 到 Wiki 仓库 → git commit 或 mw_push.py

### 批量导入（DeepSeek Subagent 并行派工）

`/import-queue` 以监工模式分派 DeepSeek subagent：

```
import-queue (Claude 监工)
  │
  ├─ 1. 读取 import_queue.json
  │
  ├─ 2. 并行分派 N 个 DeepSeek subagent（每篇一个）
  │    每个 subagent 独立执行完整流程:
  │    ├─ Read 技能文件: import-article.md + review-article.md
  │    ├─ 导入: python3 -m monitor.cli import <TID> --download-images
  │    ├─ 审阅: review-info → 优化 .mw（11 项 checklist）
  │    ├─ 定稿: word-count → cp Wiki 仓库 → 更新作品列表
  │    └─ 返回 JSON 状态
  │
  ├─ 3. 抽样验证各 subagent 产物（Infobox 字段、文件存在性）
  ├─ 4. 清空队列
  └─ 5. 输出汇总报告
```

> 审阅优化是纯文件编辑，无网络依赖，DeepSeek subagent 可并行无冲突处理。


## 格式转换规则

| 论坛内容 | MediaWiki 输出 |
|----------|---------------|
| 作者正文 | 保留为正文 |
| 作者章节（≥200 字，无 blockquote） | `== 首行标题 ==` |
| 作者回复读者（含 `<blockquote>`） | `{{同人注释start}}读者: 问题\n— 作者回复{{同人注释end}}` |
| 作者短内容（<200 字） | `{{同人注释start}}...{{同人注释end}}` |
| 其他用户回复 | `{{同人注释start}}...{{同人注释end}}` |
| 附件图片 `<img file="...">` | `[[File:xxx.jpg\|600px]]` |
| `<strong>text</strong>` | `'''text'''` |
| `<a href="url">text</a>` | `[url text]` |
| 「XXX 发表于 HH:MM」 | 自动删除 |
| 无意义回复（赞美更新等） | 自动删除 |
| `&nbsp;` | 空格 |
| Infobox 首次发布 | 取首楼日期 |
| Infobox 最近更新 | 取最新作者章节日期（排除回复帖） |

## 同人注释规则

- 仅保留有**实质补充说明价值**的讨论，剔除纯催更/赞美/灌水
- 楼主回复读者内容 → `读者: 问题 — 作者回复` 格式归入注释
- 其他用户有值讨论 → 归入注释；无实质内容 → 直接删除
- 附件图片按原始位置嵌入（在讨论文字中引用时，图片嵌入同人注释块内）
- `review-article.md` 含 `should_keep()` 批量过滤脚本

## License

GPL-v3
