"""
Web Console 生命周期管理

封装 HTTP server 的启动/停止/状态查询。
"""
from __future__ import annotations

import os
import platform
import subprocess
import threading
from http.server import ThreadingHTTPServer
from typing import Any, Dict, Optional

from fr_cli.web.console.events import attach_event_bus, detach_event_bus
from fr_cli.web.console.handler import generate_token, make_handler

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7777

_console_state: Dict[str, Any] = {
    "server": None,
    "thread": None,
    "token": None,
    "host": DEFAULT_HOST,
    "port": DEFAULT_PORT,
    "running": False,
}


def _open_browser(url: str):
    """跨平台打开浏览器"""
    try:
        if platform.system() == "Darwin":
            subprocess.Popen(["open", url])
        elif platform.system() == "Linux":
            subprocess.Popen(["xdg-open", url])
        elif platform.system() == "Windows":
            os.startfile(url)  # type: ignore
    except Exception:
        pass


def start_console(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                  token: Optional[str] = None,
                  open_browser: bool = True,
                  reuse_port: bool = True) -> Dict[str, Any]:
    """启动 Web 控制台

    Args:
        host: 绑定地址(默认 127.0.0.1)
        port: 端口
        token: Bearer Token(默认随机生成)
        open_browser: 是否自动打开浏览器
        reuse_port: 启用 SO_REUSEADDR,允许 TIME_WAIT 状态下立即重用端口(测试用)

    Returns:
        {"ok": bool, "url": str, "token": str, ...}
    """
    if _console_state["running"]:
        return {
            "ok": False,
            "error": f"控制台已在运行: http://{_console_state['host']}:{_console_state['port']}",
        }

    token = token or generate_token()
    handler_cls = make_handler(token)

    # 允许端口 TIME_WAIT 状态下立即重用(测试场景)
    if reuse_port:
        ThreadingHTTPServer.allow_reuse_address = True

    try:
        server = ThreadingHTTPServer((host, port), handler_cls)
    except OSError as e:
        return {"ok": False, "error": f"无法绑定 {host}:{port}: {e}"}

    thread = threading.Thread(
        target=server.serve_forever, daemon=True, name="fr-cli-console"
    )
    thread.start()

    _console_state.update({
        "server": server,
        "thread": thread,
        "token": token,
        "host": host,
        "port": port,
        "running": True,
    })

    # 桥接 v3 EventBus → SSE(全应用事件实时推送)
    try:
        attach_event_bus()
    except Exception:
        pass

    url = f"http://{host}:{port}"

    if open_browser:
        _open_browser(url)

    return {
        "ok": True,
        "url": url,
        "url_with_token": f"{url}/?token={token}",
        "token": token,
        "host": host,
        "port": port,
    }


def stop_console() -> Dict[str, Any]:
    """停止 Web 控制台"""
    if not _console_state["running"]:
        return {"ok": False, "error": "控制台未运行"}

    # 解除 EventBus 桥接
    try:
        detach_event_bus()
    except Exception:
        pass

    try:
        _console_state["server"].shutdown()
        _console_state["server"].server_close()
    except Exception:
        pass

    _console_state.update({
        "server": None,
        "thread": None,
        "running": False,
    })
    return {"ok": True}


def console_status() -> Dict[str, Any]:
    """获取控制台状态"""
    return {
        "running": _console_state["running"],
        "host": _console_state["host"],
        "port": _console_state["port"],
        "url": (
            f"http://{_console_state['host']}:{_console_state['port']}"
            if _console_state["running"] else None
        ),
        "token": _console_state["token"] if _console_state["running"] else None,
    }


def reset_for_testing():
    """重置控制台状态(测试用)"""
    _console_state.update({
        "server": None,
        "thread": None,
        "token": None,
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "running": False,
    })
