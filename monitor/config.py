"""
统一配置管理
敏感信息（cookie、密码）通过环境变量注入，不写入代码
"""
import os
import json


def _load_local_settings():
    """加载本地配置文件（gitignore，用于 cookie 等敏感信息）"""
    local_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'local.json')
    if os.path.exists(local_path):
        with open(local_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


_local = _load_local_settings()

CONFIG = {
    "forum": {
        "base_url": "https://lgqmonline.top",
        "board_id": 39,
        "board_url_template": "https://lgqmonline.top/forum-39-{page}.html",
        "thread_url_template": "https://lgqmonline.top/thread-{tid}-1-1.html",
        "archiver_url_template": "https://lgqmonline.top/archiver/?tid-{tid}.html",
        "archiver_page_template": "https://lgqmonline.top/archiver/?tid-{tid}&page={page}.html",
        "cookie": os.environ.get("LGQM_COOKIE", _local.get("cookie", "")),
        "request_interval": 2.0,  # 请求间隔秒数
        "request_timeout": 30,
        "max_retries": 3,
    },
    "wiki": {
        "repo_path": "/mnt/e/code/lgqm.huijiwiki.com",
        "infobox_template": "Infobox TongRen",
        "forum_link_field": "官坛原帖",
        "last_update_field": "最近更新",
        "first_publish_field": "首次发布",
        "author_field": "官方论坛",
    },
    "output": {
        "data_dir": os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data'),
        "html_dir": os.path.join(os.path.dirname(os.path.dirname(__file__)), 'html'),
        "img_dir": os.path.join(os.path.dirname(os.path.dirname(__file__)), 'img'),
        "output_dir": os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output'),
    },
    "auth": {
        "username": os.environ.get("LGQM_USERNAME", _local.get("username", "")),
        "password": os.environ.get("LGQM_PASSWORD", _local.get("password", "")),
    },
}


def get(key_path: str, default=None):
    """
    获取配置值，支持点分隔路径
    例如: get("forum.base_url")
    """
    keys = key_path.split('.')
    value = CONFIG
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return default
        if value is None:
            return default
    return value
