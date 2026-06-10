"""
数据模型定义
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from datetime import datetime
import json


@dataclass
class ForumThread:
    """论坛帖子"""
    tid: int                    # 帖子ID
    title: str                  # 帖子标题
    author: str                 # 作者用户名
    author_uid: int             # 作者UID（0表示未知）
    post_date: Optional[str] = None     # 首发日期 (YYYY-MM-DD)
    last_reply_date: Optional[str] = None  # 最后回复日期
    reply_count: int = 0        # 回复数
    view_count: int = 0         # 查看数
    url: str = ""               # 完整URL
    is_sticky: bool = False     # 是否置顶
    is_newcomer: bool = False   # 是否新人帖

    @property
    def canonical_url(self) -> str:
        """返回标准化 URL"""
        if self.url:
            return self.url
        return f"https://lgqmonline.top/thread-{self.tid}-1-1.html"


@dataclass
class Post:
    """单层楼帖"""
    author: str                 # 作者名
    date: str                   # 发布时间 (YYYY-MM-DD HH:MM:SS)
    content_html: str           # 原始 HTML 内容
    floor: int = 0              # 楼层号
    is_first_post: bool = False  # 是否首楼


@dataclass
class WikiArticle:
    """Wiki 文章"""
    filename: str               # .mw 文件名
    title: str                  # 文章标题
    forum_url: str = ""         # 关联的论坛URL（官坛原帖）
    forum_tid: Optional[int] = None  # 提取的帖子TID
    first_publish: str = ""     # 首次发布日期
    last_update: str = ""       # 最近更新日期（Wiki侧）
    is_completed: str = ""      # 完结情况：未完结/完结
    author: str = ""            # 作者


@dataclass
class DiffItem:
    """差异项"""
    type: str                   # "new" | "updated" | "possible_match"
    forum_thread: ForumThread
    wiki_article: Optional[WikiArticle] = None
    confidence: float = 1.0     # 匹配置信度
    reason: str = ""            # 差异原因


@dataclass
class DiffReport:
    """差异报告"""
    scan_time: str = ""
    summary: dict = field(default_factory=lambda: {
        "total_forum_threads": 0,
        "total_wiki_articles": 0,
        "new_threads": 0,
        "updated_threads": 0,
        "possible_matches": 0,
    })
    new_items: List[DiffItem] = field(default_factory=list)
    updated_items: List[DiffItem] = field(default_factory=list)
    possible_matches: List[DiffItem] = field(default_factory=list)

    def to_json(self, filepath: str):
        """保存为 JSON 文件"""
        import os
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, filepath: str) -> "DiffReport":
        """从 JSON 文件加载"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        report = cls()
        report.scan_time = data.get("scan_time", "")
        report.summary = data.get("summary", report.summary)
        return report
