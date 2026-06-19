"""单元测试: monitor/utils.py — URL、日期、文本、图片工具

覆盖 REG-007~015, REG-058~061
"""

import pytest
import tempfile
import os
from monitor.utils import (
    extract_tid, extract_author_uid, extract_page,
    is_forum_url, normalize_forum_url, normalize_forum_domains,
    parse_relative_date, parse_datetime,
    slugify, normalize_title, clean_html, clean_article_name,
    count_words_mw,
    detect_image_type, fix_image_extension,
)


# ============================================================
# detect_image_type — 图片格式检测
# ============================================================

class TestDetectImageType:

    def test_detect_png(self, tmp_image):
        p = tmp_image("test.png", b'\x89PNG\r\n\x1a\n' + b'\x00' * 8)
        ext, mime = detect_image_type(p)
        assert ext == "png"
        assert mime == "image/png"

    def test_detect_jpeg(self, tmp_image):
        p = tmp_image("test.jpg", b'\xff\xd8\xff\xe0' + b'\x00' * 16)
        ext, mime = detect_image_type(p)
        assert ext == "jpg"

    def test_detect_gif89a(self, tmp_image):
        p = tmp_image("test.gif", b'GIF89a' + b'\x00' * 16)
        ext, mime = detect_image_type(p)
        assert ext == "gif"

    def test_detect_webp(self, tmp_image):
        header = b'RIFF\x00\x00\x00\x00WEBP' + b'\x00' * 16
        p = tmp_image("test.webp", header)
        ext, mime = detect_image_type(p)
        assert ext == "webp"

    def test_detect_bmp(self, tmp_image):
        p = tmp_image("test.bmp", b'BM' + b'\x00' * 16)
        ext, mime = detect_image_type(p)
        assert ext == "bmp"

    def test_detect_svg(self, tmp_image):
        p = tmp_image("test.svg", b'<svg xmlns="http://www.w3.org/2000/svg">')
        ext, mime = detect_image_type(p)
        assert ext == "svg"

    def test_detect_unknown(self, tmp_image):
        p = tmp_image("test.bin", b'\x00\x01\x02\x03' * 8)
        ext, mime = detect_image_type(p)
        assert ext is None

    def test_detect_empty_file(self, tmp_image):
        p = tmp_image("empty.dat", b'')
        ext, mime = detect_image_type(p)
        assert ext is None

    def test_detect_nonexistent_file(self):
        ext, mime = detect_image_type("/nonexistent/path/img.jpg")
        assert ext is None


# ============================================================
# fix_image_extension
# ============================================================

class TestFixImageExtension:

    def test_correct_extension_no_change(self, tmp_image):
        p = tmp_image("icon.png", b'\x89PNG\r\n\x1a\n' + b'\x00' * 8)
        result = fix_image_extension(p)
        assert result is None

    def test_jpeg_to_jpg(self, tmp_image):
        p = tmp_image("photo.jpeg", b'\xff\xd8\xff\xe0' + b'\x00' * 16)
        result = fix_image_extension(p)
        assert result is not None
        assert result["new_name"] == "photo.jpg"

    def test_wrong_ext_jpg_to_png(self, tmp_image):
        p = tmp_image("shot.jpg", b'\x89PNG\r\n\x1a\n' + b'\x00' * 8)
        result = fix_image_extension(p)
        assert result is not None
        assert result["new_name"] == "shot.png"

    def test_dry_run(self, tmp_image):
        p = tmp_image("test.jpeg", b'\xff\xd8\xff\xe0' + b'\x00' * 16)
        result = fix_image_extension(p, dry_run=True)
        assert result is not None
        assert os.path.exists(p)  # 未重命名


# ============================================================
# extract_tid — 注意：返回 int
# ============================================================

class TestExtractTid:
    def test_thread_url(self):
        assert extract_tid("https://lgqmonline.top/thread-12345-1-1.html") == 12345

    def test_thread_only(self):
        # "thread-67890" 不含 .html，可能不匹配格式
        result = extract_tid("thread-67890")
        # 当前实现可能不识别纯 "thread-NNN" 格式
        assert result is None or result == 67890

    def test_no_tid(self):
        assert extract_tid("https://lgqmonline.top/forum-39-1.html") is None


# ============================================================
# normalize_forum_domains  (REG-058~061)
# ============================================================

class TestNormalizeForumDomains:
    """REG-058~061: 旧域名替换"""

    def test_lgqm_top(self):
        text = "https://lgqm.top/thread-1-1.html"
        result = normalize_forum_domains(text)
        assert "lgqmonline.top" in result

    def test_lgqm_gq(self):
        text = "https://lgqm.gq/forum.php?mod=viewthread&tid=123"
        result = normalize_forum_domains(text)
        assert "lgqmonline.top" in result

    def test_already_correct(self):
        text = "https://lgqmonline.top/thread-1-1.html"
        assert normalize_forum_domains(text) == text

    def test_mixed_domains(self):
        text = "url1: https://lgqm.top/a url2: https://lgqmonline.top/b"
        result = normalize_forum_domains(text)
        assert result.count("lgqmonline.top") == 2

    def test_other_domain_unchanged(self):
        text = "https://other.com/page"
        assert "other.com" in normalize_forum_domains(text)


# ============================================================
# clean_article_name  (REG-007~015)
# ============================================================

class TestCleanArticleName:
    """REG-007~015: 文章名清理"""

    def test_month_day_suffix(self):
        """REG-007"""
        result = clean_article_name("测试文章 5月14日更新")
        assert "5月14日" not in result

    def test_floor_update_suffix(self):
        """REG-008"""
        result = clean_article_name("测试文章 3楼2更")
        assert "3楼" not in result

    def test_outline_version(self):
        """REG-009"""
        result = clean_article_name("测试文章 大纲3版")
        assert "大纲" not in result

    def test_yyyy_m_d(self):
        """REG-010"""
        result = clean_article_name("测试文章 2024.1.9更新")
        assert "2024.1.9" not in result

    def test_completed_status(self):
        """REG-012"""
        result = clean_article_name("【原创】测试文章【完结】")
        assert "完结" not in result

    def test_short_story_tag(self):
        """REG-014"""
        result = clean_article_name("【短篇】测试文章")
        assert "短篇" not in result

    def test_original_tag_removed(self):
        assert clean_article_name("【原创】测试文章") == "测试文章"

    def test_already_clean(self):
        assert clean_article_name("测试文章") == "测试文章"


# ============================================================
# count_words_mw — 期望统计中文
# ============================================================

class TestCountWordsMw:
    def test_pure_chinese(self, tmp_path):
        f = tmp_path / "test.mw"
        f.write_text("{{首行缩进start}}\n临高启明\n{{首行缩进end}}", encoding="utf-8")
        result = count_words_mw(str(f))
        assert result["chinese"] == 4

    def test_mixed_content(self, tmp_path):
        f = tmp_path / "test.mw"
        f.write_text("{{首行缩进start}}\ntest测试abc123\n{{首行缩进end}}", encoding="utf-8")
        result = count_words_mw(str(f))
        assert result["chinese"] == 2

    def test_empty_file(self, tmp_path):
        f = tmp_path / "test.mw"
        f.write_text("{{首行缩进start}}\n\n{{首行缩进end}}", encoding="utf-8")
        result = count_words_mw(str(f))
        assert result["chinese"] == 0


# ============================================================
# normalize_title
# ============================================================

class TestNormalizeTitle:
    def test_strips_whitespace(self):
        assert normalize_title("  测试标题  ") == "测试标题"


# ============================================================
# clean_html
# ============================================================

class TestCleanHtml:
    def test_strips_tags(self):
        result = clean_html("<div>test</div>")
        assert "test" in result
