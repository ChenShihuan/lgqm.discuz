# lgqm.discuz — 临高启明论坛同人监控与 Wiki 同步系统

自动监控 [临高启明论坛](https://lgqmonline.top)「同人发布」板块（forum-39），对比 [灰机 Wiki](https://lgqm.huijiwiki.com) 已有同人文章，发现新帖和更新，支持一键拉取、格式转换、预览渲染。

## 目录结构

```
lgqm.discuz/
├── monitor/                 # 核心 Python 模块
│   ├── config.py            # 统一配置
│   ├── models.py            # 数据模型
│   ├── utils.py             # 工具函数（日期解析、日志、速率限制）
│   ├── auth.py              # 论坛登录认证（委托给 session.py）
│   ├── session.py           # 集中式 HTTP 会话管理（Cookie 持久化、浏览器指纹）
│   ├── monitor.py           # 论坛板块扫描
│   ├── indexer.py           # Wiki 文章索引
│   ├── diff.py              # 差异对比 + 标题匹配
│   ├── fetcher.py           # 论坛内容拉取（Playwright 驱动）
│   ├── pw_fetcher.py        # Playwright 浏览器管理 + Wiki 预览渲染
│   ├── converter.py         # 格式转换（HTML → MediaWiki）+ 章节检测
│   ├── index_list.py        # 同人作品列表维护
│   ├── mw_push.py           # MediaWiki API 快速推送（绕过 git-remote-mediawiki）
│   └── cli.py               # 命令行入口
├── webui/                   # WebUI 看板
│   ├── server.py            # HTTP 服务器（静态文件 + API + 论坛代理）
│   ├── index.html           # 监控看板（新帖/更新/匹配/Wiki 文章 Tab）
│   ├── preview.html         # Wiki 在线预览编辑器
│   ├── preview-page.html    # 独立预览页
│   └── api/                 # API 路由（报告、跳过、队列、预览）
├── lgqm-wiki-helper/        # VS Code 扩展
│   ├── package.json         # 扩展清单
│   └── extension.js         # 监控面板 + .mw 预览按钮
├── .claude/                 # Claude Code 配置
│   ├── commands/            # 斜杠命令
│   └── skills/              # 10+ Skills
├── data/                    # 运行时数据（gitignore）
├── doc/                     # 设计文档
├── output/                  # 输出文件（按 TID-文章名 组织）
│   └── {tid}-{name}/
│       ├── text/            # .raw.mw + .mw
│       └── img/             # 附件图片
├── lgqm.huijiwiki.com/      # 灰机 Wiki 仓库
├── lgqmtr/                  # 旧代码（参考）
└── requirements.txt
```

## 安装

```bash
pip install -r requirements.txt
playwright install chromium
```

> WSL 用户若无 sudo 权限，Chromium 依赖库需手动提取。详见下文「Playwright 安装说明」。

## 配置

创建 `data/local.json`：

```json
{
    "username": "你的论坛用户名",
    "password": "你的论坛密码"
}
```

或通过环境变量：

```bash
export LGQM_USERNAME="用户名"
export LGQM_PASSWORD="密码"
```

## 使用方式

### VS Code 扩展（推荐）

安装方式：

```bash
ln -s /mnt/e/code/lgqm.discuz/lgqm-wiki-helper ~/.vscode-server/extensions/lgqm-wiki-helper
```

VS Code 内 `Ctrl+Shift+P` → `Developer: Reload Window` 后生效：

- **监控面板**：底部状态栏 `📊 监控面板` → 在 VS Code 内嵌标签页打开看板
- **.mw 预览**：打开 `.mw` 文件 → 编辑器标题栏 `🔍 预览` 按钮 → 右侧 WebView 渲染

### WebUI 看板

```bash
python3 -m monitor.cli webui
```

浏览器访问 `http://127.0.0.1:8080/`，功能：

| Tab | 功能 |
|-----|------|
| 更新帖 / 新帖 | 分类浏览差异报告，支持类别筛选（标准/视频/其他） |
| 疑似匹配 | 标题相似但 TID 不同的搬运文章 |
| Wiki 文章 | 查看已收录文章，按 TID 有无筛选、按日期排序 |
| 预览 | 在线 Wiki 渲染预览（粘贴 wikitext 或加载 .mw 文件） |

### Claude Code Skills

| 触发词 | 功能 |
|-------|------|
| "监控论坛" | 扫描 forum-39，对比 Wiki，生成差异报告 |
| "查看差异" | 浏览差异报告详情 |
| "导入 \<tid\>" | 拉取帖子 + 下载图片 → .raw.mw + .mw |
| "审阅 \<文章名\>" | 交互式优化：Infobox、章节、注释、段落 |
| "更新 \<tid\>" | 增量更新已有 Wiki 文章 |
| "/import-queue" | 批量导入队列中所有文章 |

### CLI 命令

日常尽量多使用skills

```bash
# 导入新文章（含图片下载 + 作品列表更新）
python3 -m monitor.cli import <TID> --download-images --update-list

# 审阅原始文件
python3 -m monitor.cli review-info output/<TID>-<文章名>/text/<NAME>.raw.mw

# 校正同人作品列表序号
python3 -m monitor.cli renumber-list

# 标题匹配搬运文章
python3 -m monitor.cli match-titles --dry-run
python3 -m monitor.cli match-titles --apply

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

```bash
# CLI 渲染测试
python3 -c "from monitor.pw_fetcher import pw_parse_wikitext; print(pw_parse_wikitext(''''bold''' [[link]]'))"

# API 渲染
curl -X POST http://127.0.0.1:8080/api/preview --data-binary "@file.mw"

# 在线预览
open http://127.0.0.1:8080/preview.html
```

### git-mediawiki 同步

```bash
cd lgqm.huijiwiki.com
git rebase refs/remotes/origin/master
```

已启用 `remote.origin.shallow = true` 加速 fetch。

## 技术栈

- **Python 3** + requests + lxml + Playwright
- **论坛反爬绕过**：Playwright headless Chromium 自动执行 JS 挑战 → 提取内容
- **Cookie 管理**：pickle 持久化到 `data/cookies.pkl`，二次启动跳过登录
- **请求节流**：±30% 随机抖动，避免被识别为爬虫
- **格式转换**：HTML → MediaWiki 标记 + Infobox 生成 + 章节自动检测
- **WebUI**：纯 Python HTTP 服务器，JavaScript 前端

## 工作流

```
论坛监控 → 差异审阅 → 导入文章(.raw.mw) → 审阅优化(.mw) → 复制到 Wiki 仓库
```

1. **监控**：扫描 forum-39 → 对比 Wiki 索引 → 差异报告
2. **导入**：Playwright 拉取帖子 + 下载图片 → 转换 Wiki 格式 → `.raw.mw`（原始）+ `.mw`（基础处理）
3. **审阅**：补全 Infobox → 格式化章节标题 → 清理同人注释 → 段落格式化 → 对比差异
4. **预览**：VS Code 内一键预览 / WebUI 在线渲染
5. **提交**：复制 `.mw` 到 Wiki 仓库 → git commit

## 格式转换规则

| 论坛内容 | MediaWiki 输出 |
|----------|---------------|
| 作者正文 | 保留为正文 |
| 作者章节（≥200 字） | `== 首行标题 ==` |
| 作者回复读者（含 `<blockquote>`） | `{{同人注释start}}读者: 问题\n— 作者回复{{同人注释end}}` |
| 作者短内容（<200 字） | `{{同人注释start}}...{{同人注释end}}` |
| 其他用户回复 | `{{同人注释start}}...{{同人注释end}}` |
| 附件图片 `<img file="...">` | `[[File:xxx.jpg\|600px]]` |
| `<strong>text</strong>` | `'''text'''` |
| `<a href="url">text</a>` | `[url text]` |
| 「XXX 发表于 HH:MM」 | 自动删除 |
| `&nbsp;` | 空格 |
| 论坛内置表情 | 自动过滤 |
| Infobox 日期 | 首楼日期 → 首次发布 / 最新作者章节日期 → 最近更新 |

## Playwright 安装说明

```bash
pip install playwright --break-system-packages
playwright install chromium

# 安装 Chromium 系统依赖（一次性）
playwright install-deps chromium
sudo apt install libnspr4 libnss3 libasound2t64
```

## License

GPL-v3
