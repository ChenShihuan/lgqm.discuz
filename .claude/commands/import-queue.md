---
name: import-queue
description: 批量导入队列中的文章，逐篇执行完整导入+审阅+提交流程
argument-hint: 无参数，读取 data/import_queue.json
---

读取 `data/import_queue.json` 中的导入队列，对每篇文章按顺序执行完整的导入流程。

## 执行流程

### Step 1: 读取队列

```bash
python3 -c "import json; d=json.load(open('data/import_queue.json')); print(f'队列共 {len(d[\"items\"])} 篇'); [print(f'  [{q[\"tid\"]}] {q[\"title\"][:50]}') for q in d['items']]"
```

如果队列为空，提示用户先在 WebUI 看板中添加文章到队列。

### Step 2: 逐篇导入

对队列中的每个 item，依次调用 import-article skill，按照 .claude/skills/import-article.md 中的流程执行。

> **注意**: import-article skill 第一步为可选的预分析（Step 0: `preanalyze <TID>` + AI 分析目录结构）。若文章含目录页（如《面首》《澳宋大调查》），建议执行预分析以提升章节检测精度；若无目录或文章简短可跳过。

### Step 3: 清空队列

所有文章处理完成后，清空导入队列：

```bash
curl -X DELETE http://127.0.0.1:8080/api/queue 2>/dev/null || python3 -c "
import json
with open('data/import_queue.json','w') as f: json.dump({'items':[]}, f)
"
```

### Step 4: 输出汇总

列出本次导入的文章清单及处理结果。

## 注意事项

- 每篇文章导入后需等待审阅完成再处理下一篇
- 审阅步骤不可跳过，确保 Infobox 补全、章节格式化、**字数统计**
- 若某篇导入失败，记录错误并继续处理下一篇
- 全部完成后才清空队列
