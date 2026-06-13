"""
WebUI 看板服务器 — 本地 HTTP 服务
启动: python3 -m monitor.cli webui
"""
import os
import json
import http.server
import urllib.parse
import requests

WEBUI_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(WEBUI_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")
REPORT_PATH = os.path.join(DATA_DIR, "diff_report.json")

FORUM_BASE = "https://lgqmonline.top"

# 缓存 auth cookie 和 headers
_auth_headers = None


def _get_auth_headers() -> dict:
    """获取带论坛登录 cookie 的请求头"""
    global _auth_headers
    if _auth_headers is None:
        import sys
        sys.path.insert(0, PROJECT_DIR)
        from monitor.auth import get_cookie
        cookie = get_cookie()
        _auth_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "identity",
        }
        if cookie:
            _auth_headers["Cookie"] = cookie
    return _auth_headers.copy()


class Handler(http.server.BaseHTTPRequestHandler):
    """静态文件 + API 路由 + 论坛代理"""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/proxy/"):
            self._handle_proxy(parsed)
        elif path.startswith("/api/"):
            self._handle_api("GET", path)
        else:
            self._serve_static(path)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            self._handle_api("POST", path)
        else:
            self.send_error(405)

    def _serve_static(self, path):
        """静态文件服务"""
        if path == "/":
            path = "/index.html"

        filepath = os.path.join(WEBUI_DIR, path.lstrip("/"))
        if not os.path.abspath(filepath).startswith(WEBUI_DIR):
            self.send_error(403)
            return

        if not os.path.isfile(filepath):
            self.send_error(404)
            return

        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml",
        }.get(os.path.splitext(filepath)[1], "application/octet-stream")

        with open(filepath, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(content))
        self.end_headers()
        self.wfile.write(content)

    def _handle_api(self, method, path):
        """API 路由分发"""
        from .api import router
        try:
            status, body = router(method, path, REPORT_PATH, DATA_DIR)
        except Exception as e:
            status, body = 500, {"error": str(e)}

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))

    def _handle_proxy(self, parsed):
        """论坛代理：转发请求到论坛并附带登录 cookie"""
        # /proxy/thread-22085-1-1.html → https://lgqmonline.top/thread-22085-1-1.html
        target_path = parsed.path[len("/proxy"):]
        if parsed.query:
            target_url = f"{FORUM_BASE}{target_path}?{parsed.query}"
        else:
            target_url = f"{FORUM_BASE}{target_path}"

        try:
            resp = requests.get(target_url, headers=_get_auth_headers(), timeout=30, allow_redirects=True)
        except Exception as e:
            self.send_error(502, f"代理请求失败: {e}")
            return

        # 跳过 Discuz JS challenge 页面
        content = resp.text
        if len(content) < 5000 and content.count("<script") >= 2:
            content = (
                "<html><body style='font-family:sans-serif;padding:2em'>"
                "<h2>论坛需要 JavaScript 验证</h2>"
                "<p>请先在浏览器中直接访问一次论坛完成验证，之后代理即可正常工作。</p>"
                f"<p><a href='{target_url}' target='_blank'>打开论坛原页面</a></p>"
                "</body></html>"
            )

        content_type = resp.headers.get("Content-Type", "text/html")
        if "charset" not in content_type:
            # Discuz 默认 utf-8
            content = content.encode(resp.encoding or "utf-8")

        self.send_response(resp.status_code)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        if isinstance(content, str):
            self.wfile.write(content.encode("utf-8"))
        else:
            self.wfile.write(content)

    def log_message(self, format, *args):
        pass  # 静默日志


def serve(port: int = 8080):
    """启动 WebUI 服务器"""
    addr = ("127.0.0.1", port)
    server = http.server.HTTPServer(addr, Handler)
    print(f"\n  临高启明同人监控看板")
    print(f"  ────────────────────")
    print(f"  地址: http://127.0.0.1:{port}")
    print(f"  数据: {REPORT_PATH}")
    print(f"  按 Ctrl+C 退出\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")
        server.shutdown()
