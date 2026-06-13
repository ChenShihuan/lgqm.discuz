# lgqm.discuz — 临高启明论坛同人监控与 Wiki 同步系统

## 项目简介

自动监控 [临高启明论坛](https://lgqmonline.top)「同人发布」板块（forum-39），对比 [灰机 Wiki](https://lgqm.huijiwiki.com) 已有同人文章，发现新帖和更新，支持一键拉取内容并转换为 Wiki 格式。

## 目录结构

```
lgqm.discuz/
├── monitor/                # 核心 Python 模块
│   ├── config.py           # 统一配置
│   ├── models.py           # 数据模型
│   ├── utils.py            # 工具函数
│   ├── auth.py             # 论坛登录认证
│   ├── monitor.py          # 论坛板块扫描
│   ├── indexer.py          # Wiki 文章索引
│   ├── diff.py             # 差异对比
│   ├── fetcher.py          # 内容拉取（常规页面 + Archiver）
│   ├── converter.py        # 格式转换（→Wiki 标记）
│   └── cli.py              # 命令行入口
├── .claude/skills/         # Claude Code Skills
│   ├── monitor-forum.md    # 论坛监控
│   ├── diff-review.md      # 差异审阅
│   ├── import-article.md   # 导入文章
│   ├── review-article.md   # 审阅优化
│   └── update-article.md   # 更新文章
├── data/                   # 运行时数据（gitignore）
├── doc/                    # 设计文档
├── lgqmtr/                 # 旧代码（参考）
└── requirements.txt
```

## 安装

```bash
pip install -r requirements.txt
```

## 配置

创建 `data/local.json` 保存敏感信息（不纳入版本控制）：

```json
{
    "cookie": "你的论坛 Cookie 字符串"
}
```

或通过环境变量：

```bash
export LGQM_COOKIE="你的论坛 Cookie 字符串"
```

## 使用方式

### 通过 Claude Code Skills

推荐的使用方式，在 Claude Code 会话中说：

| 触发词 | 功能 |
|-------|------|
| "监控论坛" | 扫描 forum-39，对比 Wiki，生成差异报告 |
| "查看差异" | 浏览差异报告详情 |
| "导入 \<tid\>" | 拉取帖子内容，生成 .raw.mw + .mw 文件（含图片下载） |
| "审阅 \<文章名\>" | 交互式审阅优化 .mw 文件（补全 Infobox、格式化章节、清理注释） |
| "更新 \<tid\>" | 更新已有 Wiki 文章的正文内容 |

### 直接调用 Python

```python
# 1. 扫描论坛
from monitor.monitor import scan_board, save_threads_index
threads = scan_board(max_pages=5, verbose=True)
save_threads_index(threads)

# 2. 索引 Wiki
from monitor.indexer import scan_wiki_articles, save_wiki_index
articles = scan_wiki_articles()
save_wiki_index(articles)

# 3. 差异对比
from monitor.diff import detect_diffs, format_report_summary
report = detect_diffs(threads, articles)
print(format_report_summary(report))

# 4. 拉取内容
from monitor.fetcher import fetch_thread
from monitor.converter import convert_thread_to_wiki, save_wiki_file

posts = fetch_thread(22231)
wiki_content = convert_thread_to_wiki(posts, metadata={
    "title": "文章标题",
    "author": "作者",
    "forum_url": "https://lgqmonline.top/thread-22231-1-1.html",
})
save_wiki_file(wiki_content, "output_filename")
```

## 技术栈

- **Python 3** + requests + lxml
- **Discuz 内容获取**：优先常规页面（cookie 登录，含图片附件），回退 Archiver 模式（无需 cookie）
- **格式转换**：HTML → MediaWiki 标记，自动处理附件图片（`<img file>` → `[[File:...]]`）
- **JSON 数据交换**：轻量，可 Git 追踪

## License

GPL-v3
