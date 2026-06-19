"""
灰机 Wiki 图片上传模块 — 通过 MediaWiki API 上传本地图片文件

使用 Playwright 解决 Cloudflare JS 挑战，复用 pw_fetcher 的浏览器单例。
上传前自动检测图片真实格式并修正扩展名，同步更新 .mw 文件引用。
"""
import os
import re
import glob
import base64
import json as _json
from typing import Optional, Dict, List

from .utils import log, set_verbose, detect_image_type, fix_image_extension
from .pw_fetcher import _get_context

WIKI_DOMAIN = "lgqm"
WIKI_BASE = f"https://{WIKI_DOMAIN}.huijiwiki.com"

# 允许上传的图片扩展名
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp'}

# 从 git config 读取的 wiki 认证信息（延迟加载）
_wiki_auth = None


def _get_wiki_auth() -> dict:
    """从 lgqm.huijiwiki.com/.git/config 读取 wiki bot 凭据"""
    global _wiki_auth
    if _wiki_auth is not None:
        return _wiki_auth

    _wiki_auth = {}
    git_config_paths = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)),
                     "lgqm.huijiwiki.com", ".git", "config"),
    ]
    for config_path in git_config_paths:
        if not os.path.exists(config_path):
            continue
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
            for key in ["mwLogin", "mwPassword", "mwAuthKey"]:
                m = re.search(rf'^\s*{key}\s*=\s*(.+?)\s*$', content, re.MULTILINE)
                if m:
                    _wiki_auth[key] = m.group(1).strip()
            break
        except Exception:
            pass

    return _wiki_auth


def _get_wiki_page():
    """
    获取已通过 Cloudflare 验证的 Wiki Playwright Page。
    使用 pw_fetcher 的浏览器单例，导航到 wiki 并等待 JS 挑战完成，
    然后访问 api.php 建立 API 会话。
    """
    import time as _time

    context = _get_context()
    page = context.new_page()

    try:
        # Step 1: 访问 wiki 首页，等待 Cloudflare 挑战解决
        page.goto(f"{WIKI_BASE}/", wait_until="domcontentloaded", timeout=30000)
        for _ in range(20):
            _time.sleep(0.5)
            title = page.title()
            if "Just a moment" not in title:
                break

        # Step 2: 访问 api.php 建立 API 会话（沿用 pw_parse_wikitext 的模式）
        page.goto(f"{WIKI_BASE}/api.php?action=query&meta=siteinfo&format=json",
                  wait_until="domcontentloaded", timeout=15000)
        _time.sleep(0.5)

        return page
    except Exception:
        page.close()
        raise


def _wiki_api_fetch(page, params: dict, files: dict = None) -> dict:
    """
    在 Playwright page 上下文中通过 fetch() 调用 Wiki API。

    Args:
        page: Playwright Page（已在 wiki 域名下）
        params: API 参数 dict（不含 token 时自动获取）
        files: 可选，用于文件上传的 {field_name: (filename, bytes, mime_type)}

    Returns:
        API 响应的 JSON dict
    """
    import time as _time

    wiki_base = WIKI_BASE
    api_url = f"{wiki_base}/api.php"

    if files:
        # 文件上传：通过 base64 将二进制数据传入 JS 上下文
        field_name, (filename, file_bytes, mime_type) = next(iter(files.items()))
        b64_data = base64.b64encode(file_bytes).decode('ascii')

        raw = page.evaluate(f"""
            async () => {{
                const binaryStr = atob({_json.dumps(b64_data)});
                const bytes = new Uint8Array(binaryStr.length);
                for (let i = 0; i < binaryStr.length; i++) {{
                    bytes[i] = binaryStr.charCodeAt(i);
                }}
                const blob = new Blob([bytes], {{ type: {_json.dumps(mime_type)} }});

                const formData = new FormData();
                for (const [k, v] of Object.entries({_json.dumps(params)})) {{
                    formData.append(k, String(v));
                }}
                formData.append('{field_name}', blob, {_json.dumps(filename)});

                const resp = await fetch('{api_url}', {{
                    method: 'POST',
                    body: formData,
                }});
                return await resp.text();
            }}
        """)
    else:
        # 普通 API 调用 — 用 URLSearchParams 构造 body
        params_js = _json.dumps(params)
        raw = page.evaluate(f"""
            async () => {{
                const formData = new URLSearchParams();
                const params = {params_js};
                for (const [k, v] of Object.entries(params)) {{
                    formData.append(k, String(v));
                }}
                const resp = await fetch('{api_url}', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
                    body: formData.toString(),
                }});
                return await resp.text();
            }}
        """)

    if not raw:
        return {"error": {"info": "API 返回空响应"}}

    try:
        return _json.loads(raw)
    except _json.JSONDecodeError:
        return {"error": {"info": f"非 JSON 响应: {raw[:200]}"}}


def pw_login_wiki(page) -> bool:
    """
    登录灰机 Wiki（使用 bot 凭据）。

    使用标准 MediaWiki login API 流程：
    1. 获取 login token
    2. 用 token + 凭据确认登录
    """
    auth = _get_wiki_auth()
    if not auth.get("mwLogin") or not auth.get("mwPassword"):
        log("未找到 Wiki 认证信息（需要 mwLogin + mwPassword）", "WARN")
        return False

    # Step 1: 获取 login token
    result = _wiki_api_fetch(page, {
        "action": "query",
        "meta": "tokens",
        "type": "login",
        "format": "json",
    })
    login_token = result.get("query", {}).get("tokens", {}).get("logintoken", "")

    if not login_token:
        log(f"获取 login token 失败: {str(result)[:200]}", "ERROR")
        return False

    # Step 2: 确认登录
    result = _wiki_api_fetch(page, {
        "action": "login",
        "lgname": auth["mwLogin"],
        "lgpassword": auth["mwPassword"],
        "lgtoken": login_token,
        "format": "json",
    })
    login_result = result.get("login", {}).get("result", "")
    if login_result == "Success":
        log(f"Wiki 登录成功 ({auth['mwLogin']})", "SUCCESS")
        return True

    # 可能需要第二步确认（某些 MediaWiki 版本）
    if login_result == "NeedToken":
        confirm_token = result.get("login", {}).get("token", "")
        if confirm_token:
            result = _wiki_api_fetch(page, {
                "action": "login",
                "lgname": auth["mwLogin"],
                "lgpassword": auth["mwPassword"],
                "lgtoken": confirm_token,
                "format": "json",
            })
            if result.get("login", {}).get("result") == "Success":
                log(f"Wiki 登录成功 ({auth['mwLogin']})", "SUCCESS")
                return True

    reason = result.get("login", {}).get("reason", str(result)[:200])
    log(f"Wiki 登录失败: {reason}", "ERROR")
    return False


def pw_get_csrf_token(page) -> str:
    """获取 CSRF token"""
    result = _wiki_api_fetch(page, {
        "action": "query",
        "meta": "tokens",
        "type": "csrf",
        "format": "json",
    })
    token = result.get("query", {}).get("tokens", {}).get("csrftoken", "")
    if token:
        log(f"CSRF token: {token[:8]}...", "INFO")
    else:
        log("获取 CSRF token 失败", "WARN")
    return token


def pw_check_file_exists(page, filename: str) -> bool:
    """
    检查文件是否已存在于 Wiki。

    Args:
        page: Playwright Page
        filename: Wiki 文件名（如 xxx.jpg）

    Returns:
        True 如果文件已存在
    """
    result = _wiki_api_fetch(page, {
        "action": "query",
        "titles": f"File:{filename}",
        "prop": "imageinfo",
        "format": "json",
    })
    pages = result.get("query", {}).get("pages", {})
    for page_id, info in pages.items():
        if page_id != "-1" and "missing" not in info:
            return True
    return False


def pw_upload_file(page, local_path: str, filename: str,
                   csrf_token: str, comment: str = "") -> dict:
    """
    上传单个文件到 Wiki。

    Args:
        page: Playwright Page
        local_path: 本地文件路径
        filename: Wiki 目标文件名
        csrf_token: CSRF token
        comment: 上传摘要

    Returns:
        API 响应 dict，含 upload.result 或 error
    """
    import time as _time

    # 读取文件并检测 MIME 类型
    try:
        with open(local_path, 'rb') as f:
            file_bytes = f.read()
    except (IOError, OSError) as e:
        return {"error": {"info": f"无法读取文件: {e}"}}

    if len(file_bytes) == 0:
        return {"error": {"info": "文件为空"}}

    _, mime_type = detect_image_type(local_path)
    if mime_type is None:
        mime_type = "application/octet-stream"

    params = {
        "action": "upload",
        "filename": filename,
        "token": csrf_token,
        "format": "json",
        "ignorewarnings": "1",
    }
    if comment:
        params["comment"] = comment

    _time.sleep(0.5)  # 短暂延迟，避免请求过于密集

    result = _wiki_api_fetch(page, params,
                             files={"file": (filename, file_bytes, mime_type)})

    return result


def _scan_image_dirs(base_dir: str = None) -> List[str]:
    """
    扫描图片目录，返回所有图片文件的绝对路径列表。

    如果 base_dir 指定了具体目录，直接扫描该目录。
    否则扫描 output/*/img/ 下所有子目录。
    """
    if base_dir is None:
        base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")

    if not os.path.isdir(base_dir):
        return []

    # 如果 base_dir 本身包含图片文件（直接指定了 img 目录）
    direct_images = []
    for f in os.listdir(base_dir):
        ext = os.path.splitext(f)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            direct_images.append(os.path.join(base_dir, f))

    if direct_images:
        return sorted(direct_images)

    # 扫描 output/*/img/ 模式
    images = []
    img_dirs = glob.glob(os.path.join(base_dir, "*", "img"))
    for img_dir in sorted(img_dirs):
        for f in sorted(os.listdir(img_dir)):
            ext = os.path.splitext(f)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                images.append(os.path.join(img_dir, f))

    return images


def _update_mw_references(base_dir: str, rename_map: Dict[str, str],
                          dry_run: bool = False) -> int:
    """
    更新 .mw 文件中对重命名图片的引用。

    Args:
        base_dir: 搜索 .mw 文件的根目录
        rename_map: {old_name: new_name} 映射
        dry_run: 仅预览

    Returns:
        更新的 .mw 文件数量
    """
    if not rename_map:
        return 0

    updated_files = 0
    mw_files = glob.glob(os.path.join(base_dir, "**", "*.mw"), recursive=True)

    for mw_path in mw_files:
        with open(mw_path, "r", encoding="utf-8") as f:
            content = f.read()

        new_content = content
        changed = False
        for old_name, new_name in rename_map.items():
            if old_name not in new_content:
                continue
            # 仅在 [[File:xxx|...]] 或 [[File:xxx]] wikitext 引用中替换
            # 使用正则避免误伤正文中的普通文本子串
            pattern = re.compile(
                rf'\[\[File:{re.escape(old_name)}(\||\])'
            )
            replacement = f'[[File:{new_name}\\1'
            new_text = pattern.sub(replacement, new_content)
            if new_text != new_content:
                changed = True
                new_content = new_text

        if changed:
            updated_files += 1
            filename = os.path.basename(mw_path)
            if not dry_run:
                # 确保文件以单个换行结尾（与 save_wiki_file 一致）
                new_content = new_content.rstrip('\n') + '\n'
                with open(mw_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                log(f"  📝 {filename}: 已更新图片引用", "INFO")
            else:
                log(f"  📝 {filename}: 将更新图片引用 (dry-run)", "INFO")

    return updated_files


def pw_upload_images(img_dir: str = None, wiki_domain: str = "lgqm",
                     skip_existing: bool = True, dry_run: bool = False,
                     verbose: bool = True) -> dict:
    """
    批量上传图片到灰机 Wiki。

    流程：
    1. 扫描图片目录
    2. 检测并修正扩展名不匹配的文件
    3. 更新 .mw 文件中的图片引用
    4. 登录 Wiki → 获取 CSRF token
    5. 逐文件检查是否已存在 → 上传

    Args:
        img_dir: 图片目录（默认 output/*/img/）
        wiki_domain: Wiki 子域名（默认 lgqm）
        skip_existing: 跳过 Wiki 已有文件
        dry_run: 仅预览不实际上传
        verbose: 详细输出

    Returns:
        {total, uploaded, skipped, failed, renamed, mw_updated, errors: [{filename, reason}]}
    """
    global WIKI_BASE, WIKI_DOMAIN
    WIKI_DOMAIN = wiki_domain
    WIKI_BASE = f"https://{wiki_domain}.huijiwiki.com"

    if verbose:
        set_verbose(True)

    images = _scan_image_dirs(img_dir)
    if not images:
        log("未找到图片文件", "WARN")
        return {"total": 0, "uploaded": 0, "skipped": 0, "failed": 0,
                "renamed": 0, "mw_updated": 0, "errors": []}

    if verbose:
        log(f"扫描到 {len(images)} 张图片", "INFO")

    # ---- Phase 1: 检测并修正扩展名 ----
    if verbose:
        log("Phase 1: 检测图片格式...", "INFO")

    rename_map = {}  # old_name → new_name
    fixed_images = []
    renamed_count = 0

    for filepath in images:
        result = fix_image_extension(filepath, dry_run=dry_run)
        if result:
            renamed_count += 1
            rename_map[result["old_name"]] = result["new_name"]
            fixed_images.append(result["new_path"])
            if verbose:
                log(f"  🔧 {result['old_name']} → {result['new_name']} ({result['reason']})", "INFO")
        else:
            fixed_images.append(filepath)

    # ---- Phase 2: 更新 .mw 引用 ----
    mw_updated = 0
    if rename_map:
        output_base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
        if verbose:
            log(f"\nPhase 2: 更新 .mw 文件中的 {len(rename_map)} 个图片引用...", "INFO")
        mw_updated = _update_mw_references(output_base, rename_map, dry_run=dry_run)

    # ---- Phase 3: 上传 ----
    if dry_run:
        if verbose:
            log(f"\n⚠️  Dry-run 模式：将上传 {len(fixed_images)} 张图片（未实际执行）", "WARN")
            # 检查哪些已存在于 Wiki
            page = _get_wiki_page()
            try:
                if not pw_login_wiki(page):
                    page.close()
                    return {"total": len(fixed_images), "uploaded": 0, "skipped": 0,
                            "failed": len(fixed_images), "renamed": renamed_count,
                            "mw_updated": mw_updated,
                            "errors": [{"filename": "", "reason": "Wiki 登录失败"}]}
                for fp in fixed_images:
                    fn = os.path.basename(fp)
                    exists = pw_check_file_exists(page, fn)
                    tag = "⏭ 跳过" if exists else "🆕 将上传"
                    log(f"  {tag}: {fn}", "INFO")
            finally:
                page.close()
        return {"total": len(fixed_images), "uploaded": 0, "skipped": 0,
                "failed": 0, "renamed": renamed_count, "mw_updated": mw_updated,
                "errors": []}

    # 实际执行上传
    if verbose:
        log(f"\nPhase 3: 上传 {len(fixed_images)} 张图片到 {WIKI_BASE} ...", "INFO")

    page = _get_wiki_page()
    uploaded = 0
    skipped = 0
    failed = 0
    errors = []

    try:
        if not pw_login_wiki(page):
            page.close()
            return {"total": len(fixed_images), "uploaded": 0, "skipped": 0,
                    "failed": len(fixed_images), "renamed": renamed_count,
                    "mw_updated": mw_updated,
                    "errors": [{"filename": "", "reason": "Wiki 登录失败"}]}

        csrf_token = pw_get_csrf_token(page)
        if not csrf_token:
            page.close()
            return {"total": len(fixed_images), "uploaded": 0, "skipped": 0,
                    "failed": len(fixed_images), "renamed": renamed_count,
                    "mw_updated": mw_updated,
                    "errors": [{"filename": "", "reason": "获取 CSRF token 失败"}]}

        for i, filepath in enumerate(fixed_images, 1):
            filename = os.path.basename(filepath)

            # 检查是否已存在
            if skip_existing and pw_check_file_exists(page, filename):
                skipped += 1
                if verbose:
                    log(f"  [{i}/{len(fixed_images)}] ⏭ 跳过: {filename} (已存在)", "INFO")
                continue

            # 上传
            if verbose:
                log(f"  [{i}/{len(fixed_images)}] ⬆ 上传: {filename} ...", "INFO")

            result = pw_upload_file(page, filepath, filename, csrf_token)

            if "upload" in result and result["upload"].get("result") == "Success":
                uploaded += 1
                if verbose:
                    log(f"    ✅ 成功", "SUCCESS")
            elif "error" in result:
                err_info = result["error"]
                err_code = err_info.get("code", "unknown")
                err_msg = err_info.get("info", str(err_info))

                # CSRF token 过期，重试一次
                if err_code == "badtoken":
                    csrf_token = pw_get_csrf_token(page)
                    if csrf_token:
                        result = pw_upload_file(page, filepath, filename, csrf_token)
                        if "upload" in result and result["upload"].get("result") == "Success":
                            uploaded += 1
                            if verbose:
                                log(f"    ✅ 重试成功", "SUCCESS")
                            continue

                failed += 1
                errors.append({"filename": filename, "reason": f"{err_code}: {err_msg}"})
                if verbose:
                    log(f"    ❌ 失败: {err_code}: {err_msg[:80]}", "ERROR")
            else:
                # 可能是警告（如 duplicate 但 ignorewarnings）
                if "upload" in result:
                    uploaded += 1
                    if verbose:
                        log(f"    ⚠️  警告: {result['upload'].get('warnings', '')}", "WARN")
                else:
                    failed += 1
                    errors.append({"filename": filename, "reason": str(result)[:200]})
                    if verbose:
                        log(f"    ❌ 未知响应", "ERROR")

    finally:
        page.close()

    summary = {
        "total": len(fixed_images),
        "uploaded": uploaded,
        "skipped": skipped,
        "failed": failed,
        "renamed": renamed_count,
        "mw_updated": mw_updated,
        "errors": errors,
    }

    if verbose:
        log(f"\n--- 上传汇总 ---", "INFO")
        log(f"总计: {summary['total']} | 上传: {uploaded} | 跳过: {skipped} | 失败: {failed}", "SUCCESS")
        if renamed_count:
            log(f"格式修正: {renamed_count} 个文件", "INFO")
        if mw_updated:
            log(f".mw 更新: {mw_updated} 个文件", "INFO")

    return summary
