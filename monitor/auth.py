"""
论坛认证模块
通过 ForumSession 管理登录态、Cookie 持久化、浏览器指纹
"""
from typing import Optional
import requests

from .config import get
from .session import get_forum_session, get_cookie_str


def login() -> str:
    """
    确保已登录，返回 cookie 字符串。
    优先使用持久化 cookie，过期则自动重新登录。
    """
    fs = get_forum_session()
    fs.ensure_logged_in()
    return get_cookie_str()


def get_cookie() -> str:
    """
    获取当前有效的 cookie 字符串。
    优先使用环境变量/配置文件中的静态 cookie，
    否则通过 ForumSession 管理。
    """
    static_cookie = get("forum.cookie", "")
    if static_cookie:
        return static_cookie

    fs = get_forum_session()
    fs.ensure_logged_in()
    return get_cookie_str()


def get_session() -> Optional[requests.Session]:
    """获取已登录的 requests Session（由 ForumSession 管理）"""
    fs = get_forum_session()
    fs.ensure_logged_in()
    if fs.is_logged_in:
        return fs.session
    return None


def has_auth() -> bool:
    """检查是否配置了认证信息"""
    return bool(get("auth.username", "") and get("auth.password", ""))
