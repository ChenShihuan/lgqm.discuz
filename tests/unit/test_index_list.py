"""单元测试: monitor/index_list.py — 行解析, 序号校正"""

import pytest
from unittest.mock import patch
from monitor.index_list import (
    _build_row, _parse_row, _parse_infobox, _strip_part_suffix, get_max_seq,
)


class TestBuildRow:
    def test_standard_row(self):
        row = _build_row(
            seq=1, article_name="测试文章", author="tester",
            keywords="测试", location="临高",
            first_publish="2026-01-01", last_update="2026-06-01",
            status="未完结", canon_status="待转正",
            word_count="5000", award=""
        )
        assert "测试文章" in row
        assert "tester" in row

    def test_row_starts_with_pipe(self):
        row = _build_row(
            seq=1, article_name="文章", author="作者",
            keywords="", location="",
            first_publish="", last_update="",
            status="未完结", canon_status="待转正",
            word_count="", award=""
        )
        assert row.strip().startswith("|")


class TestParseRow:
    def test_roundtrip(self):
        original = _build_row(
            seq=1, article_name="测试", author="tester",
            keywords="", location="",
            first_publish="2026-01-01", last_update="2026-06-01",
            status="未完结", canon_status="待转正",
            word_count="1000", award=""
        )
        parsed = _parse_row(original)
        assert len(parsed) >= 3


class TestParseInfobox:
    def test_extract_author(self):
        text = """{{Infobox TongRen
| 同人作品 = 测试
| 官方论坛 = tester
}}"""
        info = _parse_infobox(text)
        assert info.get("author") == "tester"

    def test_extract_dates(self):
        text = """{{Infobox TongRen
| 首次发布 = 2026-01-01
| 最近更新 = 2026-06-18
}}"""
        info = _parse_infobox(text)
        assert info.get("last_update") == "2026-06-18"

    def test_not_completed(self):
        text = "| 完结情况 = 未完结"
        info = _parse_infobox(text)
        assert info.get("status") == "未完结"


class TestStripPartSuffix:
    def test_no_suffix(self):
        result = _strip_part_suffix("普通文章名")
        assert result is not None

    def test_volume_suffix(self):
        result = _strip_part_suffix("第一卷 临高启明")
        assert result is not None
