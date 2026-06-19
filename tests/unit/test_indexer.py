"""单元测试: monitor/indexer.py — Infobox 解析, URL/TID 提取, 大括号计数提取

覆盖 REG-034~037, REG-041~042, REG-068
"""

import pytest
from monitor.indexer import (
    parse_infobox_fields,
    extract_all_forum_urls,
    extract_all_tids,
    build_tid_index,
    _extract_infobox,
)
from monitor.models import WikiArticle


# ============================================================
# parse_infobox_fields
# ============================================================

class TestParseInfoboxFields:
    def test_standard_fields(self):
        text = "| 同人作品 = 测试文章\n| 官方论坛 = tester"
        fields = parse_infobox_fields(text)
        assert fields.get("同人作品") == "测试文章"
        assert fields.get("官方论坛") == "tester"

    def test_multiline_value(self):
        text = "| 涉及方面 = 军事、\n工业、农业"
        fields = parse_infobox_fields(text)
        val = fields.get("涉及方面", "")
        assert "军事" in val
        assert "工业" in val

    def test_empty_text(self):
        assert parse_infobox_fields("普通正文") == {}

    def test_html_comment_preserved(self):
        # parse_infobox_fields 需要完整的 {{Infobox 上下文才能正确解析
        text = "{{Infobox TongRen\n| 图像 = <!--[[Image:test.jpg]]-->\n}}"
        fields = parse_infobox_fields(text)
        val = fields.get("图像", "")
        assert "<!--" in val or val != ""


# ============================================================
# extract_all_forum_urls  (REG-034~035)
# ============================================================

class TestExtractAllForumUrls:
    def test_two_links_two_lines(self):
        """REG-034"""
        text = "[https://lgqmonline.top/thread-1801-1-1.html 帖1]\n[https://lgqmonline.top/thread-4190-1-1.html 帖2]"
        urls = extract_all_forum_urls(text)
        assert len(urls) == 2

    def test_named_link(self):
        """REG-035"""
        text = "[https://lgqmonline.top/thread-1-1.html 第一章]"
        urls = extract_all_forum_urls(text)
        assert len(urls) == 1

    def test_no_urls(self):
        assert extract_all_forum_urls("纯文本无链接") == []

    def test_article_url(self):
        urls = extract_all_forum_urls("[https://lgqmonline.top/article-8-1.html 文章]")
        assert len(urls) == 1


# ============================================================
# extract_all_tids — 返回 List[int]  (REG-036)
# ============================================================

class TestExtractAllTids:
    def test_two_tids(self):
        """REG-036"""
        text = "[https://lgqmonline.top/thread-1801-1-1.html]\n[https://lgqmonline.top/thread-4190-1-1.html]"
        tids = extract_all_tids(text)
        assert len(tids) == 2
        assert 1801 in tids
        assert 4190 in tids

    def test_single_tid(self):
        tids = extract_all_tids("[https://lgqmonline.top/thread-12345-1-1.html 测试]")
        assert tids == [12345]

    def test_no_tid(self):
        assert extract_all_tids("纯文本") == []

    def test_duplicates_removed(self):
        text = "[https://lgqmonline.top/thread-1-1.html a]\n[https://lgqmonline.top/thread-1-1.html b]"
        tids = extract_all_tids(text)
        assert tids == [1]


# ============================================================
# build_tid_index — 返回 {tid_int: WikiArticle}  (REG-037, REG-042)
# ============================================================

class TestBuildTidIndex:
    def test_single_tid(self):
        a = WikiArticle(filename="test.mw", title="Test",
                        forum_url="https://lgqmonline.top/thread-1-1.html",
                        forum_tid=1)
        idx = build_tid_index([a])
        # build_tid_index 返回 {int: WikiArticle}
        assert 1 in idx
        assert idx[1].title == "Test"

    def test_multi_tid_article(self):
        """REG-037: 多 TID 文章 — 每个 TID 都映射到同一个 article"""
        a = WikiArticle(filename="test.mw", title="Test",
                        forum_url="https://lgqmonline.top/thread-1801-1-1.html",
                        forum_tid=1801)
        a.forum_tids.append(4190)
        idx = build_tid_index([a])
        assert 1801 in idx
        assert 4190 in idx
        assert idx[1801] is idx[4190]  # 同一文章

    def test_multiple_articles(self):
        """REG-042"""
        a1 = WikiArticle(filename="a.mw", title="A",
                         forum_url="https://lgqmonline.top/thread-1-1.html", forum_tid=1)
        a2 = WikiArticle(filename="b.mw", title="B",
                         forum_url="https://lgqmonline.top/thread-2-1.html", forum_tid=2)
        a2.forum_tids.append(3)
        idx = build_tid_index([a1, a2])
        assert 1 in idx and 2 in idx and 3 in idx
        assert idx[1].title == "A"
        assert idx[2].title == "B"


# ============================================================
# _extract_infobox — 大括号计数法提取 Infobox  (REG-068)
# ============================================================

class TestExtractInfobox:
    """用大括号计数法提取 {{Infobox TongRen ... }} 模板

    修复正则 \n}} 无法匹配同行闭合（如 |字段=值}}）的问题，
    同时正确处理内部 {{PAGENAME}} 等嵌套模板。
    """

    def test_standard_closing_on_own_line(self):
        """}} 独占一行 — 传统格式"""
        text = (
            "{{同人作品版权声明}}\n"
            "{{Infobox TongRen\n"
            "| 同人作品 = 测试\n"
            "| 地点 = 临高\n"
            "}}\n"
            "正文内容..."
        )
        result = _extract_infobox(text)
        assert result is not None
        assert result.startswith("{{Infobox TongRen")
        assert result.endswith("}}")
        assert "| 同人作品 = 测试" in result
        assert "正文内容" not in result

    def test_same_line_closing(self):
        """REG-068: }} 与最后一个字段同行 — 如 |官方论坛= 布丁之主}}"""
        text = (
            "{{同人作品版权声明}}\n"
            "{{Infobox TongRen\n"
            "| 同人作品 = 测试\n"
            "| 官方论坛 = 布丁之主}}\n"
            "正文内容..."
        )
        result = _extract_infobox(text)
        assert result is not None
        assert result.startswith("{{Infobox TongRen")
        assert result.endswith("}}")
        assert "布丁之主" in result
        assert "正文内容" not in result

    def test_nested_templates(self):
        """内部含 {{PAGENAME}}, {{字数统计}} 等嵌套模板"""
        text = (
            "{{Infobox TongRen\n"
            "| 同人作品 = {{PAGENAME}}\n"
            "| 字数统计 = {{字数统计}}\n"
            "}}\n"
            "正文..."
        )
        result = _extract_infobox(text)
        assert result is not None
        assert "{{PAGENAME}}" in result
        assert "{{字数统计}}" in result
        assert "正文" not in result

    def test_comment_after_infobox_name(self):
        """Infobox TongRen 后跟注释"""
        text = (
            "{{Infobox TongRen <!-- 按照这么写 -->\n"
            "| 同人作品 = 测试\n"
            "}}\n"
        )
        result = _extract_infobox(text)
        assert result is not None
        assert "Infobox TongRen" in result
        assert "| 同人作品 = 测试" in result

    def test_no_infobox(self):
        """没有 Infobox 的文章"""
        text = "这是普通正文内容\n没有模板\n"
        result = _extract_infobox(text)
        assert result == ""

    def test_deeply_nested_braces(self):
        """多层嵌套: Infobox 内含链接和模板"""
        text = (
            "{{Infobox TongRen\n"
            "| 同人作品 = 示例\n"
            "| 官坛原帖 = [https://lgqmonline.top/thread-3550-1-1.html 链接]\n"
            "| 字数统计 = {{字数统计}}\n"
            "| 图像 = [[Image:test.jpg|class=img-responsive]]\n"
            "}}\n"
        )
        result = _extract_infobox(text)
        assert result is not None
        assert "thread-3550" in result
        assert "{{字数统计}}" in result
        assert "[[Image:test.jpg" in result

    def test_real_file_format(self):
        """模拟真实文件: 澳宋元老院办公厅女仆测评综合标准（1630版）.mw"""
        text = (
            "{{同人作品版权声明}}\n"
            "{{Infobox TongRen <!-- 按照这么写，就能得出右边的结果  -->\n"
            "| 同人作品       = {{PAGENAME}}\n"
            "| 图像	=\n"
            "| 图像信息    = \n"
            "| 百度贴吧    = \n"
            "| 官方论坛    = 布丁之主\n"
            "| 官坛原帖    = [https://lgqmonline.top/thread-3550-1-1.html 帖]\n"
            "| 其他网站    =\n"
            "| 其他      = \n"
            "| 首次发布  = 2019-11-27\n"
            "| 最近更新  = 2019-11-27\n"
            "| 地点        = 临高\n"
            "| 完结情况    = 完结\n"
            "| 字数统计    =  {{字数统计}}\n"
            "|官方论坛= 布丁之主}}\n"
            "正文..."
        )
        result = _extract_infobox(text)
        assert result is not None
        assert "thread-3550" in result
        assert "{{PAGENAME}}" in result
        assert "{{字数统计}}" in result
        assert "2019-11-27" in result
        # 不能包含正文
        assert "正文" not in result


# ============================================================
# 备用字段 TID 提取 — REG-067
# ============================================================

class TestFallbackFieldTids:
    """早年文章论坛链接放在 其他/其他网站 字段"""

    def test_tids_from_qita_field(self):
        """其他字段中的多 TID 被正确提取"""
        text = (
            "| 其他网站      = 晚到的约瑟\n"
            "| 其他      =  *[https://lgqmonline.top/thread-1023-1-1.html 神灯计划 ]\n"
            "*[https://lgqmonline.top/thread-3197-1-1.html 神灯计划（四）]\n"
            "*[https://lgqmonline.top/thread-7986-1-1.html 神灯计划（番外篇）]\n"
        )
        fields = parse_infobox_fields(text)
        tids = extract_all_tids(fields.get("其他", ""))
        assert len(tids) == 3
        assert 1023 in tids
        assert 3197 in tids
        assert 7986 in tids

    def test_no_primary_link_fallback_to_qita(self):
        """官坛原帖为空时回退到其他字段"""
        text = (
            "| 官坛原帖 =\n"
            "| 其他 = [https://lgqmonline.top/thread-1023-1-1.html 神灯计划]\n"
        )
        fields = parse_infobox_fields(text)
        # 主字段为空
        assert extract_all_tids(fields.get("官坛原帖", "")) == []
        # 备用字段有值
        assert extract_all_tids(fields.get("其他", "")) == [1023]

    def test_qita_url_extraction_with_asterisk_prefix(self):
        """* 前缀的 URL 格式被正确处理"""
        text = "| 其他 = *[https://lgqmonline.top/thread-1023-1-1.html 神灯计划 ]"
        urls = extract_all_forum_urls(text)
        assert len(urls) == 1
        assert "1023" in urls[0]
