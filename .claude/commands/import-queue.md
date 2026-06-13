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

对队列中的每个 item，依次执行：

**2a. CLI 导入：**
```bash
python3 -m monitor.cli import <TID> --download-images --update-list
```

**2b. 审阅优化：**
CLI 导入完成后，找到生成的 `.raw.mw` 文件路径（`output/<TID>-*/text/*.raw.mw`），调用 review-article skill 进行交互式优化（补全 Infobox、格式化章节、清理注释、对比差异）。

**2c. 复制到 Wiki 仓库：**
```bash
TID_DIR=$(ls -d output/<TID>-*/ 2>/dev/null | head -1)
NAME=$(ls "$TID_DIR"text/*.raw.mw 2>/dev/null | head -1 | xargs basename | sed 's/\.raw\.mw$//')
cp "$TID_DIR"text/"$NAME".mw lgqm.huijiwiki.com/
cp "$TID_DIR"img/* lgqm.huijiwiki.com/ 2>/dev/null
cd lgqm.huijiwiki.com && git add "$NAME".mw 同人作品列表.mw && git commit -m "导入同人: $NAME"
```

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
- 审阅步骤不可跳过，确保 Infobox 补全、章节格式化
- 若某篇导入失败，记录错误并继续处理下一篇
- 全部完成后才清空队列
