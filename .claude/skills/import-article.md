# Import Article — 导入新文章到 Wiki

## 描述

从论坛拉取指定帖子，转换为 MediaWiki 格式，保存到灰机 Wiki 仓库。

## 触发条件

- "导入 thread-XXXXX"
- "导入 TID XXXXX"
- "import 22231"
- 从 diff-review 中选择导入

## 执行流程

### Step 1: 拉取帖子内容

```bash
cd /mnt/e/code/lgqm.discuz && python3 -c "
import sys
sys.path.insert(0, '.')
from monitor.fetcher import fetch_thread
from monitor.converter import convert_thread_to_wiki, save_wiki_file

TID = <TID_PLACEHOLDER>

# 拉取帖子（Archiver 模式，无需 cookie）
posts = fetch_thread(TID, verbose=True)

# 构建元数据
first_post = next((p for p in posts if p.is_first_post), posts[0] if posts else None)
if first_post:
    metadata = {
        'title': f'TID-{TID}',
        'author': first_post.author,
        'forum_url': f'https://lgqmonline.top/thread-{TID}-1-1.html',
        'post_date': first_post.date,
        'tid': str(TID),
    }
else:
    metadata = {'title': f'TID-{TID}', 'tid': str(TID)}

# 转换为 Wiki 格式
wiki_content = convert_thread_to_wiki(posts, metadata=metadata)
filepath = save_wiki_file(wiki_content, f'TID-{TID}')

print(f'\\n生成文件: {filepath}')
print(f'共 {len(posts)} 楼')
print()
print('--- 内容预览（前 500 字）---')
print(wiki_content[:500])
"
```

### Step 2: 尝试下载图片

```bash
cd /mnt/e/code/lgqm.discuz && python3 -c "
import sys
sys.path.insert(0, '.')
from monitor.fetcher import fetch_images

TID = <TID_PLACEHOLDER>
images = fetch_images(TID, verbose=True)
if images:
    print(f'下载了 {len(images)} 张图片')
else:
    print('无图片或下载失败')
"
```

### Step 3: 复制到 Wiki 仓库

```bash
# 找到生成的 .mw 文件
MW_FILE=$(ls -t /mnt/e/code/lgqm.discuz/output/*.mw | head -1)
echo "生成的文件: $MW_FILE"

# 复制到 Wiki 仓库
cp "$MW_FILE" /mnt/e/code/lgqm.huijiwiki.com/
echo "已复制到 Wiki 仓库"

# 提交
cd /mnt/e/code/lgqm.huijiwiki.com
git add "$(basename "$MW_FILE")"
git commit -m "导入同人: $(basename "$MW_FILE" .mw)"
echo "已提交到 Git"
```

### Step 4: 展示供审阅

展示生成的 .mw 文件内容的关键部分（Infobox + 前 300 字正文），让用户确认格式正确。

## 注意事项

- 如果帖子标题能提取到，优先使用帖子标题作为文件名
- Infobox 中的「最近更新」字段填入当前日期
- 完结情况默认为「未完结」
- 图片下载需要有效的 cookie
