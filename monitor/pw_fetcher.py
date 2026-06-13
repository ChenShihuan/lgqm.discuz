"""
Playwright 浏览器集成 — 用于绕过论坛 JS 挑战 (_dsig)
仅在需要执行 JavaScript 的页面使用，其余请求仍走快速的 requests
"""
import os
import atexit
from typing import Optional, Dict

# Playwright 需要 libnspr4 等系统库（无 sudo 时提取到 /tmp/chromium_libs）
_LIB_PATH = "/tmp/chromium_libs/usr/lib/x86_64-linux-gnu"
if os.path.isdir(_LIB_PATH):
    os.environ.setdefault("LD_LIBRARY_PATH", _LIB_PATH)
    # 如果已有值，追加
    if _LIB_PATH not in os.environ.get("LD_LIBRARY_PATH", ""):
        existing = os.environ.get("LD_LIBRARY_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = f"{_LIB_PATH}:{existing}" if existing else _LIB_PATH

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
