"""
M365 认证层 —— MSAL OAuth2(设备代码流 / 授权码流)

从 fr_cli.weapon.m365 拆出(原文件 456 行)。
只负责"拿到 access token";Graph API 调用与配置向导仍在 fr_cli.weapon.m365。

循环依赖处理:_save_token_cache 需要写回配置(_save_m365_cfg 在主模块),
在函数内延迟导入——认证是低频路径,延迟导入无性能顾虑。
"""
from __future__ import annotations

import time
import webbrowser
from typing import Any, Dict

from fr_cli.core.result import Result
from fr_cli.ui.ui import CYAN, DIM, GREEN, RESET, YELLOW


AUTHORITY_BASE = "https://login.microsoftonline.com"
DEFAULT_SCOPES = ["Mail.Read", "Mail.Send", "User.Read"]


def _ensure_msal():
    """确保 msal 已安装"""
    try:
        import msal
        return msal
    except ImportError as e:
        raise ImportError(
            "Microsoft 365 功能需要 msal 库，请执行: pip install msal"
        ) from e


def _get_app(cfg: Dict[str, Any]):
    """根据配置创建 MSAL 应用实例"""
    msal = _ensure_msal()
    tenant_id = cfg.get("tenant_id", "common")
    client_id = cfg.get("client_id", "")
    authority = f"{AUTHORITY_BASE}/{tenant_id}"

    token_cache = msal.SerializableTokenCache()
    cache_data = cfg.get("token_cache", "")
    if cache_data:
        try:
            token_cache.deserialize(cache_data)
        except Exception:
            pass

    return msal.PublicClientApplication(
        client_id=client_id,
        authority=authority,
        token_cache=token_cache,
    ), token_cache


def _save_token_cache(token_cache, cfg: Dict[str, Any]):
    """持久化 token cache"""
    if token_cache.has_state_changed:
        cfg["token_cache"] = token_cache.serialize()
        # 延迟导入:_save_m365_cfg 在主模块(测试 monkeypatch M365_CONFIG_FILE),
        # 顶层导入会形成循环依赖
        from fr_cli.weapon.m365 import _save_m365_cfg
        _save_m365_cfg(cfg)


def _get_access_token(cfg: Dict[str, Any], lang: str = "zh") -> Result:
    """
    获取有效的 access token。优先使用缓存，无缓存或过期时触发登录流程。
    返回 Result[str]。
    """
    if not cfg.get("client_id"):
        return Result.fail("M365 未配置 client_id，请先执行 /m365_config setup")

    app, token_cache = _get_app(cfg)

    # 1. 尝试从缓存获取 token
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(DEFAULT_SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_token_cache(token_cache, cfg)
            return Result.ok(result["access_token"])

    # 2. 根据 flow 触发交互式登录
    flow = cfg.get("flow", "device_code")

    if flow == "device_code":
        return _login_device_code(app, token_cache, cfg, lang)
    elif flow == "authorization_code":
        return _login_authorization_code(app, token_cache, cfg, lang)
    else:
        return Result.fail(f"不支持的认证流程: {flow}")


def _login_device_code(app, token_cache, cfg: Dict[str, Any], lang: str = "zh") -> Result:
    """设备代码流：终端显示 code，用户到浏览器登录（支持 MFA），返回 Result[str]。"""
    flow = app.initiate_device_flow(scopes=DEFAULT_SCOPES)
    if "user_code" not in flow:
        return Result.fail("无法启动设备代码流，请检查 client_id 和 tenant_id")

    print(f"{CYAN}Microsoft 365 登录{RESET}")
    print(f"{DIM}请在浏览器中打开以下链接并输入代码完成登录（支持 MFA）:{RESET}")
    print(f"  链接: {YELLOW}{flow['verification_uri']}{RESET}")
    print(f"  代码: {YELLOW}{flow['user_code']}{RESET}")
    print(f"{DIM}等待登录中...{RESET}")

    timeout = 300  # 5 分钟
    interval = flow.get("interval", 5)
    elapsed = 0
    result = None
    while elapsed < timeout:
        result = app.acquire_token_by_device_flow(flow)
        if "access_token" in result or "error" in result:
            break
        time.sleep(interval)
        elapsed += interval

    if result and "access_token" in result:
        _save_token_cache(token_cache, cfg)
        print(f"{GREEN}[OK] Microsoft 365 登录成功{RESET}")
        return Result.ok(result["access_token"])

    error = result.get("error_description", "登录超时或失败") if result else "登录超时"
    return Result.fail(f"Microsoft 365 登录失败: {error}")


def _login_authorization_code(app, token_cache, cfg: Dict[str, Any], lang: str = "zh") -> Result:
    """授权码流：启动本地 HTTP 服务接收回调（支持 MFA），返回 Result[str]。"""
    redirect_uri = cfg.get("redirect_uri", "http://localhost:17891")
    from urllib.parse import urlparse
    parsed = urlparse(redirect_uri)
    port = parsed.port or 17891

    # 生成授权 URL
    auth_url = app.get_authorization_request_url(
        scopes=DEFAULT_SCOPES,
        redirect_uri=redirect_uri,
    )

    print(f"{CYAN}Microsoft 365 登录{RESET}")
    print(f"{DIM}正在打开浏览器...{RESET}")
    try:
        webbrowser.open(auth_url)
    except Exception:
        print(f"{YELLOW}无法自动打开浏览器，请手动访问:{RESET}")
        print(f"  {auth_url}")

    # 启动临时 HTTP 服务接收 code
    import http.server
    import socketserver
    from urllib.parse import parse_qs

    code_holder = {"code": None, "error": None}

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            from urllib.parse import urlparse
            query = parse_qs(urlparse(self.path).query)
            if "code" in query:
                code_holder["code"] = query["code"][0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write("登录成功，请返回 fr-cli。".encode("utf-8"))
            elif "error" in query:
                code_holder["error"] = query["error"][0]
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"登录失败: {query['error'][0]}".encode("utf-8"))
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write("等待授权...".encode("utf-8"))

        def log_message(self, format, *args):
            pass

    try:
        with socketserver.TCPServer(("127.0.0.1", port), _Handler) as httpd:
            httpd.timeout = 1.0
            elapsed = 0
            while elapsed < 300:
                httpd.handle_request()
                if code_holder["code"] or code_holder["error"]:
                    break
                elapsed += 1
    except OSError as e:
        return Result.fail(f"无法启动本地回调服务（端口 {port}）: {e}")

    if code_holder["error"]:
        return Result.fail(f"Microsoft 365 登录失败: {code_holder['error']}")
    if not code_holder["code"]:
        return Result.fail("Microsoft 365 登录超时")

    result = app.acquire_token_by_authorization_code(
        code=code_holder["code"],
        scopes=DEFAULT_SCOPES,
        redirect_uri=redirect_uri,
    )
    if "access_token" in result:
        _save_token_cache(token_cache, cfg)
        print(f"{GREEN}[OK] Microsoft 365 登录成功{RESET}")
        return Result.ok(result["access_token"])

    return Result.fail(f"Microsoft 365 登录失败: {result.get('error_description', '未知错误')}")
