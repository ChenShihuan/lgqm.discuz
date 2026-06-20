---
name: import-queue
description: 批量导入队列，每篇文章分派 DeepSeek subagent 独立执行完整导入+审阅+定稿
model: haiku deepseek-v4-flash[1m]
---

读取 `data/import_queue.json` 中的导入队列，每篇文章分派一个 DeepSeek subagent 并行执行完整流程。

## 执行流程

### Step 1: 读取队列

```bash
python3 -c "import json; d=json.load(open('data/import_queue.json')); print(f'队列共 {len(d[\"items\"])} 篇'); [print(f'  [{q[\"tid\"]}] {q[\"title\"][:50]}') for q in d['items']]"
```

如果队列为空，提示用户先在 WebUI 看板（`http://127.0.0.1:8080`）中添加文章到队列，然后退出。

### Step 2: 并行分派 DeepSeek subagent

对队列中的**每个条目**，并行调用 `mcp__deepseek__delegate_to_deepseek`。**所有调用在同一条响应中发出**（利用并发工具调用），让多个 subagent 同时运行。

#### Task 参数（每个条目，替换 `{tid}` 和 `{title}` 为实际值）：

```
执行完整的文章导入+审阅+定稿流程。

TID: {tid}
标题: {title}

## 流程（严格按顺序执行，每步完成后再做下一步）

### 第一步：阅读规则文件
1. Read .claude/skills/import-article.md — 了解完整导入流程
2. Read .claude/skills/review-article.md — 了解完整审阅规则

### 第二步：导入文章
运行导入命令（网络操作，需 60-120s，耐心等待）:
```bash
python3 -m monitor.cli import {tid} --download-images
```
此命令会: Playwright 拉取论坛帖子 → 转换 Wiki 格式 → 下载附件图片 → 保存 .raw.mw + .mw
输出目录格式: output/{tid}-<文章名>/

**记录 CLI 输出的实际目录路径**（如 output/19392-圣历负一年的秘密/），后续步骤全部基于此路径。
文章名从 CLI 输出中提取（如 "圣历负一年的秘密"）作为初始 NAME，**但 NAME 可能在 Step 3 审阅中被修正**（见"修正文章名"项）。

### 第三步：审阅优化
设 DIR=output/{tid}-<名称>，NAME=<名称>

3a. 运行 review-info 查看待修复项:
```bash
python3 -m monitor.cli review-info DIR/text/NAME.raw.mw
```

3b. 读取 .raw.mw 了解原始内容，然后在 DIR/text/NAME.mw 上执行 review-article.md 规定的**全部优化**:

**必须逐项完成，不要跳过:**
- [ ] 补全 Infobox 空白字段: | 地点 =、| 涉及方面 =、| 内容关键字 =、| 图像 =（如有图片则填文件名）
- [ ] 章节标题规范化: 识别缩进段落(4+nbsps开头)→== 标题 ==，嵌套卷/章/节→=/==/===层级
- [ ] 同人注释过滤: 删除纯催更/赞美/<10字/纯表情回复，保留有实质补充说明的讨论
- [ ] 段落格式化: 4空格缩进→段落间空行分隔；合并误拆的短章节；清理长等号分割线(=======)
- [ ] 删除首楼目录/楼层索引（如果首楼是章节目录而非正文）
- [ ] 清理论坛表情（static/image/smiley/ 和 static/image/common/）
- [ ] 清理附件 UI 元素（下载链接、文件大小、上传时间）
- [ ] 粗体标题（'''第X章 标题'''）→ == 标题 ==
- [ ] 清理图片引用后的裸文件名粗体（[[File:xxx.jpg|600px]] 后面紧跟的 '''xxx.jpg'''）
- [ ] 删除作者碎碎念、收款码、签名等非正文内容
- [ ] **修正文章名**（重要！含以下语义判断）:
    - `《主标题》副标题` → `主标题——副标题`（书名号包裹的为主标题，外部为副标题，用破折号连接）
    - 仅有一个书名号标题且无副标题 → 去除书名号即可
    - 确认 Infobox 中 `| 同人作品 =` 字段使用修正后的名称
    - **如果文章名被修正，必须重命名 .mw 文件本身**（`mv DIR/text/旧名.mw DIR/text/新名.mw`）并更新后续步骤中的 NAME 变量

**审阅规则详见 review-article.md 的 Step 2a-2i，严格按照其中的 Python 正则和规则执行。**

3c. 确认优化完成:
```bash
python3 -m monitor.cli review-info DIR/text/NAME.mw
```
确认 Infobox 各字段已不为空白，章节标记数量合理。

### 第四步：定稿
4a. 字数统计（自动写入 Infobox | 字数 = 字段）:
```bash
python3 -m monitor.cli word-count DIR/text/NAME.mw
```

4b. 复制到 Wiki 仓库:
```bash
cp DIR/text/NAME.mw lgqm.huijiwiki.com/
```

4c. 上传图片（如有）:
```bash
python3 -m monitor.cli upload-images --dir DIR/img/
```

4d. 更新同人作品列表:
```bash
python3 -c "
from monitor.index_list import update_from_mw_file
action, seq, name = update_from_mw_file('DIR/text/NAME.mw')
print(f'作品列表已{action}: #{seq} [[{name}]]')
"
```

### 第五步：报告结果
返回单行 JSON（方便监工程序解析）:
```json
{"tid": {tid}, "status": "ok|failed", "article_name": "实际文章名", "steps": {"import": "ok|failed", "review": "ok|failed", "word_count": 12345, "copy": "ok|failed", "index": "ok|failed"}, "errors": ["错误描述"]}
```

**重要提醒:**
- 不要跳过任何步骤，特别是审阅优化中的 checklist 项目
- 如果某步骤失败，在 errors 数组中记录具体原因，继续执行后续可做的步骤
- 所有文件路径使用相对路径（从项目根目录 /mnt/e/code/lgqm.discuz 出发）
- 第一步必须先 Read 两个技能文件，否则你不知道完整的规则
- **所有产出物必须输出到 DIR（即 output/{tid}-{name}/）子目录下，禁止在项目根目录创建任何文件：**
  - 报告文件 → `DIR/report.json`（不是根目录的 report_{tid}.json）
  - 临时脚本 → `DIR/fix_xxx.py`（不是根目录的 fix_xxx.py）
  - TOC 分析 → `DIR/toc_analysis.json`（不是根目录）
  - 任何其他临时/中间产物 → 一律放在 DIR 下
```

#### Context 参数（所有条目相同）：

```
项目: lgqm.discuz — 临高启明论坛同人监控与 Wiki 同步系统
工作目录: /mnt/e/code/lgqm.discuz

## 项目约定
- 所有 CLI 命令从项目根目录运行
- .raw.mw = 导入原始输出（保留用于对比），.mw = 处理后的最终文件
- Wiki 仓库在 lgqm.huijiwiki.com/ 目录（git-mediawiki remote）
- 图片通过 upload-images 命令直接上传到 Wiki（自动格式检测修正）
- 论坛凭据: data/local.json，Cookie: data/cookies.pkl
- Infobox | 字数 = 由 python3 -m monitor.cli word-count 自动计算并写入
- 格式转换规则见 CLAUDE.md 中的"格式转换规则"表格
- **文件输出分层约定：所有产物（报告、临时脚本、中间文件）必须输出到 `output/{tid}-{name}/` 子目录，禁止在项目根目录（/mnt/e/code/lgqm.discuz/）创建文件**

## 关键文件位置
- import-article 技能: .claude/skills/import-article.md
- review-article 技能: .claude/skills/review-article.md
- CLI 入口: monitor/cli.py
- 转换器: monitor/converter.py
- 配置: monitor/config.py
- 作品列表维护: monitor/index_list.py

## 审阅核心规则速查
以下为 review-article.md 的关键规则摘要，**完整规则务必 Read 原文件**:

### Infobox 补全
- | 地点 = — 从正文内容推断故事发生地点
- | 涉及方面 = — 从内容推断涉及的技术/领域
- | 内容关键字 = — 提取 3-5 个关键词
- | 图像 = — 如有下载的图片，填写 Wiki 图片文件名
- | 完结情况 = — 默认"未完结"

### 章节检测模式
- 缩进模式: 行首 4+ 个 &nbsp; 后跟中文数字/阿拉伯数字 → 很可能是章节标题
- 粗体模式: '''第X章 标题''' → == 标题 ==
- 层级: = 卷 = (level 1) > == 章 == (level 2) > === 节 === (level 3)

### 同人注释过滤 (should_keep 规则)
保留: 有实质讨论、补充信息、读者提问+作者回答
删除: 纯催更("催更""更新啊")、纯赞美("好""赞""顶")、<10字无意义回复、纯表情

### 清理规则
- 论坛表情: 删除所有含 static/image/smiley/ 或 static/image/common/ 的图片引用
- 附件UI: 删除下载链接行、文件大小行、上传时间行
- 长等号线: ======= 及以上长度的分割线 → 删除或替换为短分隔
- 作者碎碎念: 非故事内容的作者闲聊 → 包裹或删除
- 收款码/签名: 删除

### 段落格式化
- 4空格缩进段落 → 段落间加空行（\n\n）分隔
- 同一作者连续短段落（<200字）且无章节标记 → 合并
- 中文段落首行缩进保留（{{首行缩进start}}/{{首行缩进end}} 包裹）
```

#### 驱动逻辑:

对队列中的每个条目 item：
1. 构造 task 字符串（替换 `{tid}` 和 `{title}`）
2. 调用 `mcp__deepseek__delegate_to_deepseek(task=task, context=context)`
3. 收集返回结果

**关键：所有 mcp__deepseek__delegate_to_deepseek 调用应在同一条响应中并行发出。**

### Step 3: 验证产物

对每个 subagent 的返回结果：

1. **解析状态**: 尝试从返回值中提取 JSON 状态对象。如果返回格式不是 JSON，从文本中查找 "status": "ok" 或 "status": "failed" 关键字。

2. **抽样验证**（对 status=ok 的条目）:
   - Read 对应 .mw 文件的前 100 行，确认 Infobox 字段不为空（特别是 `| 地点 =`、`| 涉及方面 =`）
   - 用 Glob 确认 `lgqm.huijiwiki.com/` 中存在对应的 .mw 文件
   - 用 Glob 确认 `output/img_sum/` 中有图片（如有）

3. **失败处理**:
   - import 步骤失败 → 整篇跳过，记录原因
   - review 步骤失败 → 标注"审阅需人工处理"，.raw.mw 已生成可供后续手动审阅
   - 定稿步骤失败 → 标注具体失败步骤，已生成的 .mw 文件保留

### Step 4: 重建 Wiki 索引

导入完成后，**必须重建 `wiki_index.json`**，确保后续监控不会重复识别已导入文章：

```bash
python3 -m monitor.cli index-wiki
```

> 此步骤只执行一次（非 per-article），在所有文章验证通过后运行。

### Step 5: 清空队列

所有文章处理完成后（无论成功失败），清空队列：

```bash
python3 -c "
import json
from datetime import datetime
with open('data/import_queue.json','w') as f:
    json.dump({'items': [], 'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, f, ensure_ascii=False)
print('队列已清空')
"
```

> 如需保留失败的条目以便重试，可在写入前过滤掉已成功的 TID，只保留失败的。

### Step 6: 输出汇总

以表格形式列出本次导入结果：

| TID | 标题 | 导入 | 审阅 | 定稿 | 字数 | 备注 |
|-----|------|------|------|------|------|------|
| 19392 | 圣历负一年的秘密 | ✅ | ✅ | ✅ | 12,345 | |
| 12311 | 余烬... | ✅ | ⚠️ | ✅ | 8,900 | Infobox 地点未补全 |

统计：成功 N 篇，部分成功 M 篇，失败 K 篇。

## 错误处理速查

| 场景 | 策略 |
|------|------|
| 队列为空 | 提示用户，退出 |
| DS subagent 返回 ERROR | 记录失败，继续等其他 subagent 完成 |
| DS 返回 JSON 中 status=failed | 根据 steps 判断：import 失败 → 跳过；review 失败 → 标注"需手动审阅" |
| DS 返回非 JSON 无法解析 | Glob 检查产物文件是否存在，标注"需人工确认" |
| 部分成功 | 全部处理完后清空队列，汇总中标注失败项原因 |

## 注意事项

- **并行上限**: 如果队列超过 4 篇，建议分两批派工（每批 ≤4），避免多个 Playwright 实例内存压力过大
- **网络依赖**: import 步骤需要论坛可访问，确保 `lgqmonline.top` 可达
- **不跳过审阅**: DeepSeek subagent 必须逐项完成审阅 checklist，不可跳过
- **验证不可省略**: Step 3 抽样验证必须执行，不可盲信 DS 自报的"完成"状态
