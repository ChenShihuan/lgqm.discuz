# lgqm.discuz — 临高启明论坛同人监控与 Wiki 同步系统

本代码库用于从临高启明论坛拉取待更新同人，论坛地址 https://lgqmonline.top/，论坛基于 Discuz X3.4 部署。

## 功能概览

参照 @doc/design.md

## 目录结构

参照 @README.md

### git-mediawiki 拉取

lgqm.huijiwiki.com 仓库当中拉取更新，应当采用如下指令：

```bash
git rebase refs/remotes/origin/master
```

其余参照 @doc/git-mediawiki-setup.md


## 工作流

本代码库工作流**必须**调用已有skill进行

```
论坛监控 → 差异审阅 → 导入文章(.raw.mw) → 审阅优化(.mw) → 预览确认 → 复制到 Wiki 仓库
                                   ↗ 批量导入可并行分派 DeepSeek subagent ↓
```

1. **监控**：扫描 forum-39 → 对比 Wiki 索引 → 差异报告
2. **导入**：Playwright 拉取帖子 + 下载图片 → 转换 Wiki 格式 → `.raw.mw`（原始）+ `.mw`（基础处理）
3. **审阅**：调用**review-article** skill进行
4. **预览**：VS Code 内一键预览 / `preview.html` / `pw_parse_wikitext()` API
5. **提交**：复制 `.mw` 到 Wiki 仓库 → **人工审阅后** git commit

### 批量导入（DeepSeek Subagent 并行派工）

@.claude/skills/import-queue.md

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
  │    ├─ 审阅: 按照**review-article** skill进行，review-info → 优化 .mw（11 项 checklist）
  │    ├─ 定稿: word-count → cp Wiki 仓库 → 更新作品列表
  │    └─ 返回 JSON 状态
  │
  ├─ 3. 抽样验证各 subagent 产物（Infobox 字段、文件存在性）
  ├─ 4. 清空队列
  └─ 5. 输出汇总报告
```

> 审阅优化是纯文件编辑，无网络依赖，DeepSeek subagent 可并行无冲突处理。
> 审阅过程必须按照**review-article** skill进行


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

其余详细规则见 @.claude/skills/review-article.md

## 同人注释规则

- 仅保留有**实质补充说明价值**的讨论，剔除纯催更/赞美/灌水
- 楼主回复读者内容 → `读者: 问题 — 作者回复` 格式归入注释
- 其他用户有值讨论 → 归入注释；无实质内容 → 直接删除
- 附件图片按原始位置嵌入（在讨论文字中引用时，图片嵌入同人注释块内）
- `review-article.md` 含 `should_keep()` 批量过滤脚本

其余详细规则见 @.claude/skills/review-article.md

## skill工作规则
- 编辑过程中使用的临时脚本或者临时文件**必须放置在 output/TID-<NAME> 的指定目录下**

## License

GPL-v3
