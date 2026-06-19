"""单元测试: monitor/models.py — 数据模型

覆盖: ForumThread, Post, WikiArticle, DiffItem, DiffReport
"""

import pytest
import json
import tempfile
import os
from monitor.models import (
    ForumThread, Post, WikiArticle, DiffItem, DiffReport,
)


class TestForumThread:
    def test_canonical_url(self):
        t = ForumThread(tid=1, title="T", author="A", author_uid="1",
                        url="https://lgqmonline.top/thread-1-1-1.html",
                        post_date="", last_reply_date="", reply_count=0, view_count=0)
        assert "thread-1-1-1" in t.canonical_url

    def test_default_values(self):
        t = ForumThread(tid=1, title="T", author="A", author_uid="1",
                        url="", post_date="", last_reply_date="",
                        reply_count=0, view_count=0)
        assert t.is_sticky is False
        assert t.is_newcomer is False


class TestWikiArticle:
    def test_forum_tids_includes_forum_tid(self):
        a = WikiArticle(filename="test.mw", title="Test",
                        forum_url="https://lgqmonline.top/thread-1-1.html",
                        forum_tid=1, first_publish="2026-1-1", last_update="2026-6-1")
        assert 1 in a.forum_tids

    def test_multi_tid(self):
        a = WikiArticle(filename="test.mw", title="Test",
                        forum_url="", forum_tid=1801,
                        first_publish="2026-1-1", last_update="2026-6-1")
        a.forum_tids.append(4190)
        assert len(a.forum_tids) == 2

    def test_default_completed(self):
        a = WikiArticle(filename="x.mw", title="X", forum_url="", forum_tid=1)
        assert a.is_completed == ""


class TestDiffReport:
    def test_write_and_read_json(self):
        """to_json(filepath) writes to file; from_json(filepath) reads"""
        report = DiffReport(
            scan_time="2026-06-18T23:00:00",
            summary={"new_count": 5, "updated_count": 2},
            new_items=[
                DiffItem(type="new",
                         forum_thread=ForumThread(
                             tid=1, title="新帖", author="A", author_uid="1",
                             url="https://lgqmonline.top/thread-1-1-1.html",
                             post_date="2026-1-1", last_reply_date="2026-6-18",
                             reply_count=10, view_count=100),
                         reason="新帖"),
            ],
            updated_items=[], possible_matches=[], confirmed_matches=[],
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filepath = f.name

        try:
            report.to_json(filepath)
            parsed = DiffReport.from_json(filepath)
            assert parsed.summary["new_count"] == 5
            assert parsed.summary["updated_count"] == 2
            assert len(parsed.new_items) == 1
            assert parsed.new_items[0].forum_thread.tid == 1
        finally:
            os.unlink(filepath)

    def test_empty_report(self):
        report = DiffReport(
            scan_time="2026-06-18T00:00:00",
            summary={},
            new_items=[], updated_items=[], possible_matches=[], confirmed_matches=[],
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filepath = f.name

        try:
            report.to_json(filepath)
            parsed = DiffReport.from_json(filepath)
            assert parsed.summary == {}
        finally:
            os.unlink(filepath)

    def test_roundtrip_with_possible_match(self):
        report = DiffReport(
            scan_time="2026-06-18",
            summary={"possible_match_count": 1},
            new_items=[], updated_items=[],
            possible_matches=[
                DiffItem(type="possible_match",
                         forum_thread=ForumThread(
                             tid=999, title="疑似", author="B", author_uid="2",
                             url="https://lgqmonline.top/thread-999-1-1.html",
                             post_date="2026-1-1", last_reply_date="2026-6-18",
                             reply_count=5, view_count=50),
                         wiki_article=WikiArticle(
                             filename="m.mw", title="疑似",
                             forum_url="https://lgqmonline.top/thread-1-1.html",
                             forum_tid=1, first_publish="2026-1-1", last_update="2026-6-1"),
                         confidence=0.7, reason="标题匹配"),
            ],
            confirmed_matches=[],
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filepath = f.name

        try:
            report.to_json(filepath)
            parsed = DiffReport.from_json(filepath)
            assert len(parsed.possible_matches) == 1
            assert parsed.possible_matches[0].wiki_article.forum_tid == 1
        finally:
            os.unlink(filepath)


class TestPost:
    def test_creation(self):
        p = Post(author="tester", date="2026-1-1",
                 content_html="<div>test</div>",
                 floor=1, is_first_post=True, pid="532600000")
        assert p.author == "tester"
        assert p.floor == 1

    def test_subject_default_empty(self):
        """subject 字段默认值为空字符串"""
        p = Post(author="tester", date="2026-1-1",
                 content_html="<div>test</div>",
                 floor=1, is_first_post=True, pid="532600000")
        assert p.subject == ""

    def test_subject_from_h2(self):
        """从 Discuz <h2> 提取的楼层标题"""
        p = Post(author="tester", date="2026-1-1",
                 content_html="<div>test</div>",
                 floor=2, is_first_post=False, pid="532610786",
                 subject="1～无边绝望的降临")
        assert p.subject == "1～无边绝望的降临"


class TestDiffItem:
    def test_item_types(self):
        t = ForumThread(tid=1, title="T", author="A", author_uid="1",
                        url="", post_date="", last_reply_date="",
                        reply_count=0, view_count=0)
        assert DiffItem(type="new", forum_thread=t).type == "new"
        assert DiffItem(type="updated", forum_thread=t).type == "updated"
