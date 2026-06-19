"""共享 fixtures 和测试工具"""
import pytest
import tempfile
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from monitor.models import ForumThread, WikiArticle, DiffItem, DiffReport, Post


# ============================================================
# 数据模型 fixtures
# ============================================================

@pytest.fixture
def sample_thread():
    """标准测试帖子"""
    return ForumThread(
        tid=12345, title="测试同人", author="tester",
        author_uid="123", post_date="2026-1-1",
        last_reply_date="2026-6-15 20:00",
        reply_count=50, view_count=1000,
        url="https://lgqmonline.top/thread-12345-1-1.html"
    )


@pytest.fixture
def sample_article():
    """标准测试 Wiki 文章"""
    return WikiArticle(
        filename="测试同人.mw", title="测试同人",
        forum_url="https://lgqmonline.top/thread-12345-1-1.html",
        forum_tid=12345, first_publish="2026-1-1",
        last_update="2026-6-1", is_completed=False, author="tester"
    )


@pytest.fixture
def sample_post():
    """标准测试帖"""
    return Post(
        author="tester", date="2026-1-1 12:00",
        content_html="<div>正文内容第一行<br />正文第二行</div>",
        floor=1, is_first_post=True, pid="532600000",
        subject="",
    )


@pytest.fixture
def sample_infobox_text():
    """标准 Infobox 模板文本"""
    return """{{Infobox TongRen
| 同人作品 = 测试文章
| 官方论坛 = tester
| 官坛原帖 = [https://lgqmonline.top/thread-12345-1-1.html 测试同人]
| 首次发布 = 2026-01-01
| 最近更新 = 2026-06-01
| 地点 = 临高
| 涉及方面 = 军事、工业
| 内容关键字 = 测试、样例
| 完结情况 = 未完结
}}"""


@pytest.fixture
def sample_diff_report(sample_thread, sample_article):
    """标准差异报告"""
    return DiffReport(
        scan_time="2026-06-18T23:00:00",
        summary={"new_count": 1, "updated_count": 1, "possible_match_count": 1},
        new_items=[
            DiffItem(type="new", forum_thread=sample_thread,
                     reason="论坛新帖，Wiki 无对应文章"),
        ],
        updated_items=[
            DiffItem(type="updated", forum_thread=sample_thread, wiki_article=sample_article,
                     reason="论坛更新于 2026-6-15，Wiki 最后更新 2026-6-1"),
        ],
    )


# ============================================================
# 临时文件 fixtures
# ============================================================

@pytest.fixture
def tmp_mw_file(tmp_path):
    """在临时目录创建 .mw 文件"""
    def _create(filename, content):
        p = tmp_path / filename
        p.write_text(content, encoding="utf-8")
        return str(p)
    return _create


@pytest.fixture
def tmp_image(tmp_path):
    """在临时目录创建测试图片文件"""
    def _create(filename, magic_bytes):
        p = tmp_path / filename
        p.write_bytes(magic_bytes)
        return str(p)
    return _create


# ============================================================
# 全局状态重置 fixtures
# ============================================================

@pytest.fixture
def reset_converter_state():
    """重置 converter 模块全局状态"""
    import monitor.converter as conv
    conv.last_merged_titles = []
    conv._last_toc_info = {}
    yield
    conv.last_merged_titles = []
    conv._last_toc_info = {}


@pytest.fixture
def reset_session_singleton():
    """重置 ForumSession 单例"""
    import monitor.session as sess
    old_instance = sess.ForumSession._instance
    sess.ForumSession._instance = None
    yield
    sess.ForumSession._instance = old_instance
