"""单元测试: monitor/diff.py — 差异对比, 日期判断"""

import pytest
from monitor.diff import _check_update, detect_diffs, format_report_summary
from monitor.models import ForumThread, WikiArticle, DiffReport


class TestCheckUpdate:
    def test_thread_newer_than_wiki(self):
        t = ForumThread(tid=1, title="T", author="A", author_uid="1",
                        last_reply_date="2026-6-18 20:00", url="",
                        post_date="2026-1-1", reply_count=0, view_count=0)
        w = WikiArticle(filename="T.mw", title="T", forum_url="", forum_tid=1,
                        last_update="2026-6-10", first_publish="2026-1-1")
        assert _check_update(t, w) is not None

    def test_wiki_no_date(self):
        t = ForumThread(tid=1, title="T", author="A", author_uid="1",
                        last_reply_date="2026-6-18", url="",
                        post_date="2026-1-1", reply_count=0, view_count=0)
        w = WikiArticle(filename="T.mw", title="T", forum_url="", forum_tid=1,
                        last_update="", first_publish="2026-1-1")
        assert _check_update(t, w) is not None

    def test_forum_no_date(self):
        t = ForumThread(tid=1, title="T", author="A", author_uid="1",
                        last_reply_date="", url="",
                        post_date="2026-1-1", reply_count=0, view_count=0)
        w = WikiArticle(filename="T.mw", title="T", forum_url="", forum_tid=1,
                        last_update="2026-6-18", first_publish="2026-1-1")
        assert _check_update(t, w) is None

    def test_both_have_date_thread_newer(self):
        """明确的时间对比：论坛日期晚于 Wiki"""
        t = ForumThread(tid=1, title="T", author="A", author_uid="1",
                        last_reply_date="2026-6-18", url="",
                        post_date="2026-1-1", reply_count=0, view_count=0)
        w = WikiArticle(filename="T.mw", title="T", forum_url="", forum_tid=1,
                        last_update="2026-6-10", first_publish="2026-1-1")
        result = _check_update(t, w)
        assert result is not None
        assert "晚于" in result


class TestDetectDiffs:
    def test_new_thread(self, sample_thread):
        threads = [sample_thread]
        report = detect_diffs(threads, [], {})
        assert report.summary.get("new_threads", 0) >= 1

    def test_sticky_filtered(self):
        t = ForumThread(tid=1, title="置顶帖", author="A", author_uid="1",
                        last_reply_date="2026-6-18", url="",
                        post_date="2026-1-1", reply_count=0, view_count=0,
                        is_sticky=True)
        report = detect_diffs([t], [], {})
        assert report.summary.get("new_threads", 0) == 0

    def test_empty_threads(self):
        report = detect_diffs([], [], {})
        assert report.summary.get("new_threads", 0) == 0

    def test_possible_match(self, sample_article):
        t = ForumThread(tid=999, title="测试同人", author="B", author_uid="2",
                        last_reply_date="2026-6-18",
                        url="https://lgqmonline.top/thread-999-1-1.html",
                        post_date="2026-1-1", reply_count=0, view_count=0)
        tid_idx = {12345: [sample_article]}
        report = detect_diffs([t], [sample_article], tid_idx)
        possible = report.summary.get("possible_matches", 0) + len(report.possible_matches)
        assert possible >= 1


class TestFormatReportSummary:
    def test_produces_output(self):
        report = DiffReport(
            scan_time="2026-06-18T00:00:00",
            summary={"total_forum_threads": 100, "total_wiki_articles": 50,
                      "new_threads": 10, "updated_threads": 0,
                      "possible_matches": 0, "confirmed_matches": 0},
            new_items=[], updated_items=[], possible_matches=[], confirmed_matches=[]
        )
        output = format_report_summary(report)
        assert isinstance(output, str)
        assert len(output) > 0

    def test_empty_report(self):
        report = DiffReport(
            scan_time="2026-06-18T00:00:00",
            summary={"total_forum_threads": 0, "total_wiki_articles": 0,
                      "new_threads": 0, "updated_threads": 0,
                      "possible_matches": 0, "confirmed_matches": 0},
            new_items=[], updated_items=[], possible_matches=[], confirmed_matches=[]
        )
        output = format_report_summary(report)
        assert isinstance(output, str)
