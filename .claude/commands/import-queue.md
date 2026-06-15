---
name: import-queue
description: 批量导入队列，每篇文章分派 DeepSeek subagent 独立执行完整导入+审阅+定稿
argument-hint: 无参数，读取 data/import_queue.json
---

调用 import-queue skill，按照 .claude/skills/import-queue.md 中的流程执行。
