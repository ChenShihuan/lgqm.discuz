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
    forum_tid: Optional[int] = None  # 提取的帖子TID（主）
    forum_tids: list = None     # 提取的所有TID（含跨行多链接）
    first_publish: str = ""     # 首次发布日期
    last_update: str = ""       # 最近更新日期（Wiki侧）
    is_completed: str = ""      # 完结情况：未完结/完结
    author: str = ""            # 作者

    def __post_init__(self):
        if self.forum_tids is None:
            self.forum_tids = []
        if self.forum_tid is not None and self.forum_tid not in self.forum_tids:
            self.forum_tids.append(self.forum_tid)


@dataclass
class DiffItem:
    """差异项"""
    type: str                   # "new" | "updated" | "possible_match"
    forum_thread: ForumThread
    wiki_article: Optional[WikiArticle] = None
    confidence: float = 1.0     # 匹配置信度
    reason: str = ""            # 差异原因
    verified: Optional[bool] = None  # None=未验证, True=可访问, False=不可访问


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
        "verified_accessible": 0,
        "verified_inaccessible": 0,
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

    def _item_from_dict(self, item_data: dict) -> DiffItem:
        """从字典重建 DiffItem"""
        ft = item_data.get("forum_thread", {})
        wa = item_data.get("wiki_article")
        return DiffItem(
            type=item_data.get("type", ""),
            forum_thread=ForumThread(
                tid=ft.get("tid", 0),
                title=ft.get("title", ""),
                author=ft.get("author", ""),
                author_uid=ft.get("author_uid", 0),
                url=ft.get("url", ""),
                post_date=ft.get("post_date"),
                last_reply_date=ft.get("last_reply_date"),
                reply_count=ft.get("reply_count", 0),
                view_count=ft.get("view_count", 0),
                is_sticky=ft.get("is_sticky", False),
            ),
            wiki_article=WikiArticle(
                filename=wa.get("filename", ""),
                title=wa.get("title", ""),
                forum_url=wa.get("forum_url", ""),
                forum_tid=wa.get("forum_tid"),
                first_publish=wa.get("first_publish", ""),
                last_update=wa.get("last_update", ""),
                is_completed=wa.get("is_completed", ""),
                author=wa.get("author", ""),
            ) if wa else None,
            confidence=item_data.get("confidence", 1.0),
            reason=item_data.get("reason", ""),
            verified=item_data.get("verified"),
        )

    @classmethod
    def from_json(cls, filepath: str) -> "DiffReport":
        """从 JSON 文件完整加载报告（含所有差异项）"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        report = cls()
        report.scan_time = data.get("scan_time", "")
        report.summary = data.get("summary", report.summary)
        for item_data in data.get("new_items", []):
            report.new_items.append(report._item_from_dict(item_data))
        for item_data in data.get("updated_items", []):
            report.updated_items.append(report._item_from_dict(item_data))
        for item_data in data.get("possible_matches", []):
            report.possible_matches.append(report._item_from_dict(item_data))
        return report
