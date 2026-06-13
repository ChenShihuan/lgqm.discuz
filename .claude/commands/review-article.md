---
name: review-article
description: 审阅已下载的原始文件，并进行优化
argument-hint: [.raw.mw 文件路径]
---

调用 review-article skill，按照 .claude/skills/review-article.md 中的流程执行。如果用户指定了文件路径参数 `$ARGUMENTS`，则审阅该指定文件；如果用户在 IDE 中选中了某个 .raw.mw 文件，则以选中文件为目标；否则扫描 output/ 目录下的 .raw.mw 文件供用户选择。
