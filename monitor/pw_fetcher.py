"""
Playwright 浏览器集成 — 用于绕过论坛 JS 挑战 (_dsig)
仅在需要执行 JavaScript 的页面使用，其余请求仍走快速的 requests
"""
import os
import atexit
from typing import Optional, Dict

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from .utils import log

BASE_URL = "https://lgqmonline.top"

# 全局单例
_browser: Optional[Browser] = None
_context: Optional[BrowserContext] = None
_pw_instance = None  # sync_playwright 实例


def _get_context() -> BrowserContext:
    """获取或创建持久的 Playwright BrowserContext（含登录 cookie）"""
    global _browser, _context, _pw_instance

    if _context is not None:
        return _context

    # 获取已有登录 cookie（由 ForumSession 管理）
    from .session import get_forum_session
    fs = get_forum_session()
    fs.ensure_logged_in()
    cookies_dict = fs.session.cookies.get_dict()

    _pw_instance = sync_playwright().start()
    _browser = _pw_instance.chromium.launch(headless=True)
    _context = _browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN",
    )

    # 注入已有登录 cookie
    if cookies_dict:
        cookie_list = [
            {
                "name": k,
                "value": v,
                "domain": "lgqmonline.top",
                "path": "/",
            }
            for k, v in cookies_dict.items()
        ]
        _context.add_cookies(cookie_list)

    log("Playwright 浏览器已启动（用于绕过 JS 挑战）", "INFO")
    return _context


def _close_browser():
    """清理 Playwright 资源"""
    global _browser, _context, _pw_instance
    try:
        if _context:
            _context.close()
        if _browser:
            _browser.close()
        if _pw_instance:
            _pw_instance.stop()
    except Exception:
        pass
    _browser = None
    _context = None
    _pw_instance = None


atexit.register(_close_browser)


def pw_get_html(url: str, wait_until: str = "domcontentloaded",
                timeout: int = 30000) -> str:
    """
    使用 Playwright 获取页面渲染后的 HTML（自动执行 JS 解决 _dsig 挑战）

    Args:
        url: 页面 URL
        wait_until: 等待策略 (domcontentloaded / networkidle)
        timeout: 超时毫秒

    Returns:
        渲染后的 HTML 文本
    """
    context = _get_context()
    page: Page = context.new_page()
    try:
        page.goto(url, wait_until=wait_until, timeout=timeout)
        html = page.content()
        return html
    finally:
        page.close()


def pw_get_title(url: str, timeout: int = 15000) -> str:
    """使用 Playwright 获取页面标题"""
    context = _get_context()
    page: Page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        return page.title()
    except Exception:
        return ""
    finally:
        page.close()


def _fetch_wiki_css(page, wiki_base: str) -> str:
    """抓取 wiki 的 site.styles CSS 并返回内联样式文本"""
    import re as _re2
    css_all = []
    # 关键的 CSS 模块
    modules = ["site.styles", "mediawiki.action.view.redirectPage"]
    for mod in modules:
        try:
            css_url = f"{wiki_base}/load.php?modules={mod}&only=styles&skin=huijidragonhide"
            css_text = page.evaluate(f"""
                async () => {{
                    const resp = await fetch('{css_url}');
                    return resp.ok ? await resp.text() : '';
                }}
            """)
            if css_text:
                css_all.append(f"/* {mod} */\n{css_text}")
        except Exception:
            pass
    return "\n".join(css_all)


def pw_refresh_cookies():
    """
    将 Playwright 浏览器中的 cookie 同步回 requests.Session。
    某些论坛 cookie（如 _st_p 等）可能由 JS 挑战解决后设置。
    """
    global _context
    if _context is None:
        return

    from .session import get_forum_session
    fs = get_forum_session()
    for c in _context.cookies():
        fs.session.cookies.set(
            c["name"], c["value"],
            domain=c.get("domain", ""),
            path=c.get("path", "/"),
        )


# 临高启明灰机 Wiki 常用模板 CSS（注入预览 iframe，替代外部 load.php）
_TEMPLATE_CSS = """<style>
/* === 临高启明 Wiki 模板样式 === */

/* 基础背景 */
body { background: #fff; color: #202122; }

/* 首行缩进 */
.textIndent p, .textIndent { text-indent: 2em; }

/* 同人注释 */
blockquote { border-left: 4px solid #c20605; margin: 1em 0; padding: 0.5em 1em; background: #fdf6e3; font-size: 14px; }

/* 版权声明 */
.well.quote-primary { border-left: 10px solid #c20605; padding: 1em; margin: 1em 0; background: #fefaf0; overflow: auto; }

/* Infobox */
table.infobox { margin: 0.5em 0 0.5em 1em; padding: 0.2em; float: right; clear: right; font-size: 88%; line-height: 1.5em; width: 280px; }
.infobox-title { font-size: 125%; font-weight: bold; text-align: center; }
.infobox-image { text-align: center; }
.infobox th { text-align: left; padding: 0.2em 0.5em; vertical-align: top; width: 35%; }
.infobox td { padding: 0.2em 0.5em; }

/* 目录 */
.toc { border: 1px solid #a2a9b1; background: #f8f9fa; padding: 0.5em 1em; margin: 1em 0; display: inline-block; min-width: 240px; font-size: 13px; }
.toc .toctitle { font-weight: bold; text-align: center; margin-bottom: 0.3em; }
.toc ul { list-style: none; margin: 0.3em 0; padding: 0; }
.toc ul ul { margin-left: 1.5em; }
.toc li { margin: 0.1em 0; }
.toc a { color: #0645ad; text-decoration: none; }
.toc .tocnumber { color: #202122; }

/* 通用 MediaWiki 样式 */
.mw-parser-output { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 14px; line-height: 1.7; color: #202122; }
.mw-parser-output h2 { border-bottom: 1px solid #a2a9b1; margin-top: 1.5em; margin-bottom: 0.5em; padding-bottom: 0.2em; font-size: 1.5em; }
.mw-parser-output h3 { font-size: 1.2em; margin-top: 1.2em; font-weight: bold; }
.mw-parser-output a { color: #0645ad; text-decoration: none; }
.mw-parser-output a.new { color: #ba0000; }
.mw-parser-output img { max-width: 100%; height: auto; }
.mw-parser-output p { margin: 0.5em 0; }
</style>"""


def pw_parse_wikitext(wikitext: str, wiki_domain: str = "lgqm") -> str:
    """
    通过灰机 Wiki 的 action=parse API 渲染 wikitext 为 HTML。
    使用 Playwright 解决 Cloudflare JS 挑战。

    Args:
        wikitext: MediaWiki 格式文本
        wiki_domain: huijiwiki 子域名（默认 lgqm）

    Returns:
        渲染后的 HTML 文本，失败返回空字符串
    """
    import urllib.parse, json as _json, time as _time
    context = _get_context()
    page = context.new_page()
    try:
        wiki_base = f"https://{wiki_domain}.huijiwiki.com"

        # Step 1: 先访问 wiki 首页，等待 Cloudflare 挑战自动解决
        page.goto(f"{wiki_base}/", wait_until="domcontentloaded", timeout=30000)
        # 等待最多 10 秒让 Cloudflare 重定向完成
        for _ in range(20):
            _time.sleep(0.5)
            title = page.title()
            if "Just a moment" not in title:
                break

        # Step 2: 调用 parse API（POST 方式，支持大文本）
        api_url = f"{wiki_base}/api.php"
        # 先用一个简单的 GET 建立 session
        page.goto(f"{api_url}?action=query&meta=siteinfo&format=json",
                  wait_until="domcontentloaded", timeout=15000)
        _time.sleep(0.5)
        # 再用 fetch API POST 发送大文本（含 headhtml 获取 wiki CSS）
        raw = page.evaluate(f"""
            async () => {{
                const formData = new URLSearchParams();
                formData.append('action', 'parse');
                formData.append('text', {_json.dumps(wikitext)});
                formData.append('contentmodel', 'wikitext');
                formData.append('disableeditsection', 'true');
                formData.append('prop', 'text|headhtml');
                formData.append('format', 'json');
                const resp = await fetch('{api_url}', {{
                    method: 'POST',
                    body: formData,
                    headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }}
                }});
                return await resp.text();
            }}
        """)
        if not raw:
            log("Wiki API POST 返回空", "WARN")
            return ""

        try:
            data = _json.loads(raw)
            if "parse" in data:
                body_html = data["parse"]["text"]["*"]
                head_html = data["parse"].get("headhtml", {}).get("*", "")
                if head_html:
                    import re as _re2
                    # 清理 headhtml：移除 <script> 和外部 <link> CSS（用内联替代）
                    head_html = _re2.sub(
                        r'<script[^>]*>.*?</script>', '',
                        head_html, flags=_re2.DOTALL
                    )
                    head_html = _re2.sub(
                        r'<link[^>]*rel=["\']stylesheet["\'][^>]*/?\s*>', '',
                        head_html
                    )
                    # 注入内联模板 CSS
                    head_html = head_html.replace(
                        "</head>",
                        _TEMPLATE_CSS + "\n</head>",
                        1
                    )
                    # <base> 使图片等相对链接指向 wiki
                    head_html = head_html.replace(
                        "<head>",
                        f"<head>\n<base href=\"{wiki_base}/\">",
                        1
                    )
                    # 组装完整 HTML 文档
                    return head_html + "<body>\n" + body_html + "\n</body>\n</html>"
                # 无 headhtml 时手动构建最小 HTML 文档
                return (
                    "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"UTF-8\">\n"
                    + f"<base href=\"{wiki_base}/\">\n"
                    + _TEMPLATE_CSS + "\n</head>\n<body>\n"
                    + body_html + "\n</body>\n</html>"
                )
            elif "error" in data:
                err = data["error"]
                log(f"Wiki API 错误: {err.get('info', str(err))}", "WARN")
                return ""
        except _json.JSONDecodeError:
            log(f"Wiki API 返回非 JSON: {raw[:100]}", "WARN")
            return ""
    except Exception as e:
        log(f"Wiki 预览失败: {e}", "WARN")
        return ""
    finally:
        page.close()
