"""单元测试: monitor/session.py — JS 挑战检测, 请求头

覆盖 REG-001~006, REG-053~054
"""

import pytest
from unittest.mock import MagicMock, patch
from monitor.session import ForumSession

# 创建轻量实例用于测试纯函数方法
# is_js_challenge 不依赖任何实例属性（不使用 self）
@pytest.fixture
def session():
    """创建不验证登录的 ForumSession 实例"""
    with patch.object(ForumSession, '__init__', lambda self: None):
        s = ForumSession.__new__(ForumSession)
        s._username = None
        s._password = None
        return s


# ============================================================
# is_js_challenge — JS 挑战检测  (REG-001~006, REG-053~054)
# ============================================================

class TestIsJsChallenge:
    """REG-001~006, REG-053~054: JS 反爬挑战页面检测"""

    @pytest.fixture(autouse=True)
    def _setup(self, session):
        self.s = session

    # ---- 应检测为 JS 挑战 ----

    def test_getname_caller_confusion(self):
        """REG-001: 变量名混淆版 (function getName / getName.caller)"""
        html = """<html><body>
        <script>function getName(){return getName.caller}</script>
        <script>var _0xabc=...;location.href=...</script>
        </body></html>"""
        assert self.s.is_js_challenge(html) is True

    def test_standard_cf_challenge(self):
        """REG-002: 标准 CF 挑战 (含 jschl)"""
        html = """<html><body>
        <script>var s,t,o,p,b,r,e,a,k,i,n,g,f, jschl={"jschl_vc":"abc"}</script>
        <script>location.href=...</script>
        </body></html>"""
        assert self.s.is_js_challenge(html) is True

    def test_obfuscated_var_location(self):
        """REG-053: location.href 赋值"""
        html = """<html><body>
        <script>var s="https://lgqmonline.top/";location.href=s;</script>
        </body></html>"""
        assert self.s.is_js_challenge(html) is True

    def test_obfuscated_no_keywords(self):
        """REG-054: 无 cloudflare/jschl 关键字, 仅 location 跳转"""
        html = """<html><body>
        <script>var _0x1234=["...","..."];function _0x5678(){};
        location.href=_0x1234[0];</script>
        </body></html>"""
        assert self.s.is_js_challenge(html) is True

    def test_cf_page_with_multiple_scripts(self):
        """Cloudflare 特征页: title + 多个 script"""
        html = '<html><head><title>Just a moment...</title></head><body><script>a=1</script><script>b=2</script></body></html>'
        assert self.s.is_js_challenge(html) is True

    # ---- 不应检测为 JS 挑战 ----

    def test_normal_thread_page(self):
        """REG-003: 正常帖子 HTML (长文本无 script)"""
        html = """<html><body>
        <div>""" + ("旅顺口的防御体系包括了多座棱堡以及相应的火炮配置。" * 200) + """</div>
        </body></html>"""
        assert self.s.is_js_challenge(html) is False

    def test_short_text_no_js(self):
        """REG-004: 短文本无 JS (阈值边界)"""
        html = "<html><body>帖子内容</body></html>"
        assert self.s.is_js_challenge(html) is False

    def test_normal_page_with_scripts(self):
        """含正常 JS 但非挑战"""
        html = """<html><body>
        <script src="/static/js/common.js"></script>
        """ + ("正常帖子内容。" * 500) + """
        </body></html>"""
        assert self.s.is_js_challenge(html) is False

    def test_very_short_html(self):
        assert self.s.is_js_challenge("") is False
        assert self.s.is_js_challenge("short") is False
