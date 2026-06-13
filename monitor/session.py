"""
集中式 Session 管理
- 统一浏览器指纹 headers
- Cookie 持久化到磁盘（避免每次启动重新登录）
- 自动 Referer 链 + Sec-Fetch-* 计算
"""
import os
import re
import pickle
import random
import requests
from typing import Optional
from urllib.parse import urlparse

from .config import get
from .utils import log

BASE_URL = "https://lgqmonline.top"
DATA_DIR = get("output.data_dir")


class ForumSession:
    """论坛请求会话（单例），管理登录态、Cookie、完整的浏览器指纹"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._session = requests.Session()
        self._cookie_path = os.path.join(DATA_DIR, "cookies.pkl")
        self._username = get("auth.username", "")
        self._logged_in = False
        self._last_referer = None  # 记录上次访问的 URL 用于 Referer 链

        # 优先加载持久化 cookie
        if self._load_cookies() and self._validate_cookie():
            self._logged_in = True
            log("Cookie 有效，跳过登录", "SUCCESS")

        self._initialized = True

    # ================================================================
    # Headers
    # ================================================================

    @staticmethod
    def _base_headers() -> dict:
        """基础浏览器指纹头（所有请求共用）"""
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8,"
                "application/signed-exchange;v=b3;q=0.7"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": (
                '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'
            ),
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1",
        }

    def _make_headers(self, url: str, referer: str = None) -> dict:
        """
        构建完整请求头，包含 Referer + Sec-Fetch-*。

        Sec-Fetch-Site 规则：
        - 无 referer → none（用户直接输入 URL 或书签）
        - referer 同源 → same-origin
        - referer 异源 → cross-site
        """
        headers = self._base_headers()

        if referer:
            ref_origin = urlparse(referer).netloc
            target_origin = urlparse(url).netloc
            headers["Sec-Fetch-Site"] = "same-origin" if ref_origin == target_origin else "cross-site"
            headers["Referer"] = referer
        else:
            headers["Sec-Fetch-Site"] = "none"

        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-User"] = "?1"

        return headers

    def _image_headers(self, url: str, referer: str) -> dict:
        """图片请求头（线索：从文档跳转，模式 no-cors）"""
        headers = self._base_headers()
        headers["Accept"] = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        headers["Sec-Fetch-Site"] = "same-origin"
        headers["Sec-Fetch-Mode"] = "no-cors"
        headers["Sec-Fetch-Dest"] = "image"
        headers["Referer"] = referer
        return headers

    def _post_headers(self, url: str, referer: str = None) -> dict:
        """POST 请求头（带 Origin）"""
        headers = self._make_headers(url, referer)
        headers["Origin"] = BASE_URL
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers.pop("Cache-Control", None)
        return headers

    # ================================================================
    # Cookie 持久化
    # ================================================================

    def save_cookies(self) -> None:
        """将当前 cookie jar 持久化到磁盘"""
        os.makedirs(DATA_DIR, exist_ok=True)
        try:
            with open(self._cookie_path, "wb") as f:
                pickle.dump(self._session.cookies, f)
        except Exception as e:
            log(f"Cookie 保存失败: {e}", "WARN")

    def _load_cookies(self) -> bool:
        """从磁盘加载持久化的 cookie jar"""
        if not os.path.exists(self._cookie_path):
            return False
        try:
            with open(self._cookie_path, "rb") as f:
                cookies = pickle.load(f)
            self._session.cookies = cookies
            return len(cookies) > 0
        except Exception:
            return False

    # ================================================================
    # Cookie 验证
    # ================================================================

    def _validate_cookie(self) -> bool:
        """
        用轻量端点验证当前 cookie 是否仍然有效。
        使用 home.php?mod=spacecp（用户控制面板）而非板块列表页。
        """
        url = f"{BASE_URL}/home.php?mod=spacecp"
        try:
            resp = self._session.get(
                url,
                headers=self._make_headers(url, referer=f"{BASE_URL}/"),
                timeout=10,
                allow_redirects=False,
            )
        except Exception:
            return False

        # 被重定向到登录页 → cookie 已过期
        if resp.status_code in (301, 302, 303):
            return False

        # JS 挑战检测
        if len(resp.text) < 5000 and resp.text.count("<script") >= 2:
            log("Cookie 验证遇到 JS 挑战", "WARN")
            return False

        # 检查页面是否包含用户标识
        text = resp.text
        if self._username and self._username in text:
            return True
        if "退出" in text or "用户组" in text:
            return True

        return False

    def validate_cookie(self) -> bool:
        """公开的 cookie 有效性检查"""
        return self._validate_cookie()

    # ================================================================
    # 登录
    # ================================================================

    def ensure_logged_in(self) -> None:
        """确保已登录。有效 cookie 跳过，否则执行完整登录。"""
        if self._logged_in:
            return

        # 先检查静态 cookie（配置文件注入，跳过登录）
        static_cookie = get("forum.cookie", "")
        if static_cookie:
            log("使用静态 Cookie", "INFO")
            self._logged_in = True
            return

        if not self._username:
            log("未配置用户名/密码，跳过登录。仅可访问公开内容", "WARN")
            return

        # 尝试用持久化 cookie 验证
        if self._validate_cookie():
            self._logged_in = True
            log("Cookie 有效，跳过登录", "SUCCESS")
            return

        # 完整登录
        self._login()

    def _login(self) -> None:
        """执行 Discuz 登录流程"""
        log(f"正在登录论坛 (用户: {self._username})...", "INFO")

        password = get("auth.password", "")
        if not password:
            log("未配置密码", "ERROR")
            return

        try:
            # Step 1: 获取登录页面 formhash
            login_url = f"{BASE_URL}/member.php?mod=logging&action=login"
            resp = self._session.get(
                login_url,
                headers=self._make_headers(login_url, referer=f"{BASE_URL}/"),
                timeout=get("forum.request_timeout", 30),
            )

            # JS challenge check
            if len(resp.text) < 5000 and resp.text.count("<script") >= 2:
                log("登录页面遇到 JS 挑战——header 修复未能绕过，可能需要 Playwright", "ERROR")
                return

            formhash_match = re.search(r'name="formhash" value="([^"]+)"', resp.text)
            if not formhash_match:
                log("登录失败：未找到 formhash（页面结构可能已变更）", "ERROR")
                return
            formhash = formhash_match.group(1)

            # Step 2: 发送登录 POST
            login_data = {
                "formhash": formhash,
                "referer": f"{BASE_URL}/",
                "username": self._username,
                "password": password,
                "loginsubmit": "yes",
            }

            resp = self._session.post(
                f"{login_url}&loginsubmit=yes",
                data=login_data,
                headers=self._post_headers(login_url, referer=login_url),
                allow_redirects=True,
                timeout=get("forum.request_timeout", 30),
            )

            # Step 3: 轻量验证（用户控制面板）
            verify_url = get("forum.login_verify_url", f"{BASE_URL}/home.php?mod=spacecp")
            resp = self._session.get(
                verify_url,
                headers=self._make_headers(verify_url, referer=f"{BASE_URL}/"),
                timeout=get("forum.request_timeout", 30),
            )

            if self._username in resp.text or "退出" in resp.text or "用户组" in resp.text:
                self._logged_in = True
                self.save_cookies()
                log("登录成功！Cookie 已缓存", "SUCCESS")
            else:
                log("登录验证失败，请检查用户名密码", "ERROR")

        except Exception as e:
            log(f"登录异常: {e}", "ERROR")

    # ================================================================
    # 公开 API
    # ================================================================

    @property
    def session(self) -> requests.Session:
        """获取底层 requests.Session"""
        return self._session

    def get(self, url: str, referer: str = None, timeout: int = None, **kwargs) -> requests.Response:
        """
        发送 GET 请求，自动附带完整浏览器 headers + Referer。
        并更新内部 Referer 链。
        """
        headers = self._make_headers(url, referer)
        if "headers" in kwargs:
            extra = kwargs.pop("headers")
            headers.update(extra)
        t = timeout or get("forum.request_timeout", 30)
        resp = self._session.get(url, headers=headers, timeout=t, **kwargs)
        self._last_referer = url
        return resp

    def get_image(self, url: str, referer: str, timeout: int = None, **kwargs) -> requests.Response:
        """下载图片，附带正确的图片请求头"""
        headers = self._image_headers(url, referer)
        t = timeout or 30
        return self._session.get(url, headers=headers, timeout=t, **kwargs)

    def post(self, url: str, data: dict = None, referer: str = None, timeout: int = None, **kwargs) -> requests.Response:
        """发送 POST 请求，自动附带 Origin + Referer"""
        headers = self._post_headers(url, referer)
        if "headers" in kwargs:
            extra = kwargs.pop("headers")
            headers.update(extra)
        t = timeout or get("forum.request_timeout", 30)
        resp = self._session.post(url, data=data, headers=headers, timeout=t, **kwargs)
        self._last_referer = url
        return resp

    def is_js_challenge(self, text: str) -> bool:
        """检测响应是否是 JS 挑战页面"""
        return len(text) < 5000 and text.count("<script") >= 2

    @property
    def username(self) -> str:
        return self._username

    @property
    def is_logged_in(self) -> bool:
        return self._logged_in


# ================================================================
# 便利函数
# ================================================================

def get_forum_session() -> ForumSession:
    """获取 ForumSession 单例"""
    return ForumSession()


def get_cookie_str() -> str:
    """
    兼容旧接口：返回 cookie 字符串。
    新代码应使用 get_forum_session().session。
    """
    fs = get_forum_session()
    cookies = fs.session.cookies.get_dict()
    return "; ".join([f"{k}={v}" for k, v in cookies.items()])
