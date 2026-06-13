# lgqm.discuz — 临高启明论坛同人监控与 Wiki 同步系统

本代码库用于从临高启明论坛拉取待更新同人，论坛地址 https://lgqmonline.top/，论坛基于 Discuz X3.4 部署。

## 功能概览

| 功能 | 说明 |
|------|------|
| **论坛监控** | 扫描「同人发布」板块（forum-39），对比 Wiki 已有文章，发现新帖和更新帖 |
| **文章导入** | 从论坛拉取指定帖子（常规页面 + cookie），转换为 MediaWiki 格式，下载附件图片 |
| **文章审阅** | 交互式优化 .mw 文件：补全 Infobox、格式化章节标题、清理同人注释 |
| **文章更新** | 对 Wiki 已收录的文章，从论坛拉取最新楼层内容更新 |

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
│   ├── converter.py        # 格式转换（HTML → MediaWiki）
│   └── cli.py              # 命令行入口
├── .claude/                # Claude Code 配置
│   ├── commands/           # 斜杠命令
│   └── skills/             # Skills（monitor-forum, import-article, review-article, update-article）
├── data/                   # 运行时数据（gitignore）
├── doc/                    # 设计文档
├── output/                 # 输出文件（按 TID-文章名 组织，内含 text/ + img/）
│   └── {tid}-{name}/
│       ├── text/           # .raw.mw + .mw
│       └── img/            # 附件图片
├── lgqm.huijiwiki.com/     # 灰机 Wiki 仓库
├── lgqmtr/                 # 旧代码（参考）
└── requirements.txt
```

## 安装与配置

```bash
pip install -r requirements.txt
```

配置认证信息（二选一）：

1. 创建 `data/local.json`：
```json
{
    "auth": {
        "username": "你的论坛用户名",
        "password": "你的论坛密码"
    }
}
```

2. 或通过环境变量：
```bash
export LGQM_USERNAME="用户名"
export LGQM_PASSWORD="密码"
```

## 使用方式

### Claude Code Skills（推荐）

| 触发词 | 功能 |
|-------|------|
| "监控论坛" | 扫描 forum-39，对比 Wiki，生成差异报告 |
| "查看差异" | 浏览差异报告详情，选择导入/更新 |
| "导入 \<tid\>" | 拉取帖子内容 + 下载图片，生成 .raw.mw + .mw |
| "审阅 \<文章名\>" | 交互式优化：补全 Infobox、格式化章节、清理注释 |
| "更新 \<tid\>" | 更新已有 Wiki 文章的正文内容 |

### CLI 命令

```bash
# 导入新文章（含图片下载）
python3 -m monitor.cli import <TID> --download-images

# 审阅原始文件
python3 -m monitor.cli review-info output/<TID>-<文章名>/text/<NAME>.raw.mw

# 下载图片（保存到 output/<TID>-<文章名>/img/）
python3 -m monitor.cli fetch-images <TID>
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

### git-mediawiki拉取

lgqm.huijiwiki.com仓库当中拉取更新，应当采用如下指令

```bash
git rebase refs/remotes/origin/master
```

## 工作流

```
论坛监控 → 差异审阅 → 导入文章(.raw.mw) → 审阅优化(.mw) → 复制到 Wiki 仓库
```

1. **监控**：扫描 forum-39 → 对比 Wiki 索引 → 差异报告
2. **导入**：拉取帖子 + 下载图片 → 转换 Wiki 格式 → `.raw.mw`（原始）+ `.mw`（基础处理）
3. **审阅**：补全 Infobox → 格式化章节标题 → 清理同人注释 → 嵌入图片 → 对比差异
4. **提交**：复制 `.mw` 到 Wiki 仓库 → git commit

## 格式转换规则

| 论坛内容 | MediaWiki 输出 |
|----------|---------------|
| 作者正文 | 保留为正文 |
| 其他用户回复 | `{{同人注释start}}...{{同人注释end}}` |
| 附件图片 `<img file="...">` | `[[File:xxx.jpg\|600px]]` |
| `<strong>text</strong>` | `'''text'''` |
| `<a href="url">text</a>` | `[url text]` |
| 「XXX 发表于 HH:MM」 | 自动删除 |
| 无意义回复（赞美更新等） | 自动删除 |
| `&nbsp;` | 空格 |

## 同人注释规则

- 仅保留有**实质补充说明价值**的讨论，剔除纯催更/赞美/灌水
- 作者回复讨论的内容保留在正文；其他用户有值讨论归入注释
- 附件图片按原始位置嵌入（在讨论文字中引用时，图片嵌入同人注释块内）

## License

GPL-v3
