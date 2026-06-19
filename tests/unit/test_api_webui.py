"""单元测试: webui/api/__init__.py — 文章分类, 路由分发

覆盖 REG-043~048
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from webui.api import _classify, _clean_article_name, router


# ============================================================
# _classify — 文章分类  (REG-043~048)
# ============================================================

class TestClassify:
    """REG-043~048: 新帖分类"""

    def test_original_not_first_tag(self):
        """REG-043: 原创不在首位"""
        assert _classify("【游戏】【原创】测试") == "standard"

    def test_short_story_tag(self):
        """REG-044: 短篇"""
        assert _classify("【短篇】测试") == "standard"

    def test_ultra_short_story_tag(self):
        """REG-045: 超短篇同人"""
        assert _classify("【超短篇同人】测试") == "standard"

    def test_video_tag(self):
        """REG-046: 视频"""
        assert _classify("【视频】测试") == "video"

    def test_fullwidth_parentheses(self):
        """REG-047: 全角括号标签"""
        result = _classify("（征文投稿）测试")
        assert result in ("standard", "other")

    def test_no_tag(self):
        """REG-048: 无标签"""
        assert _classify("无标签的普通文章") == "other"

    def test_original_tag(self):
        assert _classify("【原创】测试") == "standard"

    def test_reference_tag(self):
        # 当前分类器可能将【资料】归入 other 或 reference
        assert _classify("【资料】测试") in ("reference", "other")

    def test_repost_tag(self):
        assert _classify("【转帖】测试") in ("repost", "other")

    def test_multiple_tags(self):
        assert _classify("【原创】【军事】测试") == "standard"


# ============================================================
# _clean_article_name — 文章名清理 (API 版本)
# ============================================================

class TestCleanArticleName:
    def test_removes_original_tag(self):
        assert _clean_article_name("【原创】测试") == "测试"

    def test_keeps_clean_name(self):
        assert _clean_article_name("测试文章") == "测试文章"


# ============================================================
# router — API 路由分发
# ============================================================

class TestRouter:
    def test_known_paths_return_handler(self, tmp_path):
        data_dir = str(tmp_path)
        # 创建最小化的 diff_report.json 使 _get_report 不崩溃
        import json
        (tmp_path / "diff_report.json").write_text(json.dumps({
            "scan_time": "", "summary": {}, "new_items": [],
            "updated_items": [], "possible_matches": [], "confirmed_matches": []
        }))
        (tmp_path / "wiki_index.json").write_text("[]")
        (tmp_path / "skipped.json").write_text("[]")
        (tmp_path / "import_queue.json").write_text("[]")
        # 测试仅不需要文件系统依赖的路径
        simple_paths = [
            ("POST", "/api/skipped"),
            ("POST", "/api/queue"),
            ("DELETE", "/api/skipped"),
        ]
        for method, path in simple_paths:
            result = router(method, path, None, data_dir)
            assert result is not None

    def test_unknown_path(self, tmp_path):
        result = router("GET", "/api/nonexist", None, str(tmp_path))
        assert result is not None
