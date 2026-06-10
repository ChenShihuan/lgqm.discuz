"""
论坛认证模块 - 自动登录获取 Cookie
"""
import re
import requests
from typing import Optional

from .config import get
from .utils import log


# 全局缓存的登录 session
_session: Optional[requests.Session] = None
_cookie_str: str = ""


def _cookie_to_str(session: requests.Session) -> str:
    """将 session 的 cookie 转为字符串"""
    cookies = session.cookies.get_dict()
    return '; '.join([f'{k}={v}' for k, v in cookies.items()])


def login() -> str:
    """
    使用配置文件中的用户名密码登录论坛，返回 cookie 字符串

    登录成功后会缓存 session，后续调用直接返回缓存的 cookie。
    """
    global _session, _cookie_str

    # 已登录则直接返回
    if _cookie_str:
        return _cookie_str

    username = get("auth.username", "")
    password = get("auth.password", "")

    if not username or not password:
        log("未配置用户名/密码，跳过登录。仅可访问公开内容", "WARN")
        return ""

    log(f"正在登录论坛 (用户: {username})...", "INFO")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })

    try:
        # 1. 获取登录页面 formhash
        resp = session.get(
            f"{get('forum.base_url')}/member.php?mod=logging&action=login",
            timeout=get("forum.request_timeout", 30)
        )
        formhash_match = re.search(r'name="formhash" value="([^"]+)"', resp.text)
        if not formhash_match:
            log("登录失败：未找到 formhash", "ERROR")
            return ""

        formhash = formhash_match.group(1)

        # 2. 发送登录请求
        login_data = {
            "formhash": formhash,
            "referer": get("forum.base_url", "https://lgqmonline.top") + "/",
            "username": username,
            "password": password,
            "loginsubmit": "yes",
        }

        resp = session.post(
            f"{get('forum.base_url')}/member.php?mod=logging&action=login&loginsubmit=yes",
            data=login_data,
            allow_redirects=True,
            timeout=get("forum.request_timeout", 30)
        )

        # 3. 验证登录状态
        resp = session.get(
            get("forum.board_url_template").format(page=1),
            timeout=get("forum.request_timeout", 30)
        )

        if username in resp.text or '退出' in resp.text or '用户组' in resp.text:
            _session = session
            _cookie_str = _cookie_to_str(session)
            log(f"登录成功！Cookie 已缓存", "SUCCESS")
            return _cookie_str
        else:
            log("登录验证失败，请检查用户名密码", "ERROR")
            return ""

    except Exception as e:
        log(f"登录异常: {e}", "ERROR")
        return ""


def get_cookie() -> str:
    """
    获取当前有效的 cookie 字符串。
    优先使用环境变量/配置文件中的静态 cookie，
    否则自动登录获取。
    """
    # 先检查是否有配置的静态 cookie
    static_cookie = get("forum.cookie", "")
    if static_cookie:
        return static_cookie

    # 自动登录
    return login()


def get_session() -> Optional[requests.Session]:
    """获取已登录的 requests Session"""
    global _session
    if _session is None:
        # 尝试登录
        cookie = login()
        if not cookie:
            return None
    return _session


def has_auth() -> bool:
    """检查是否配置了认证信息"""
    return bool(get("auth.username", "") and get("auth.password", ""))
