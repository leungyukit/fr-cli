"""
Web Console HTTP handler

构造 _make_handler(token) 返回 BaseHTTPRequestHandler 子类,处理:
- GET: 首页 / 静态资源 / SSE / API
- POST: 客户端事件上传

服务骨架(鉴权 / 响应包裹 / 异常处理)统一到 fr_cli.core.http_base:
- 响应包裹保持历史的 {"ok", "data"} 形状
- 鉴权:全部方法都需要 Bearer Token;只读公开白名单=首页与 PWA 静态资源
  (白名单只对 GET/HEAD/OPTIONS 生效)

所有端点:
- GET /, /index.html          首页 HTML
- GET /manifest.json          PWA manifest
- GET /icon.svg               PWA 图标
- GET /sw.js                  Service worker
- GET /api/events             SSE 长连接(需鉴权)
- GET /api/status             全局状态
- GET /api/sessions           会话列表
- GET /api/sessions/<idx>     会话详情
- GET /api/tasks              Hermes 任务
- GET /api/worktrees          Worktree
- GET /api/bookmarks          Bookmark
- GET /api/stats              统计
- GET /api/health             健康检查
- GET /api/metrics            指标查询(json/prom/summary)
- POST /api/event             客户端发事件到 SSE
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from fr_cli.core.http_base import (
    WRAP_OK_DATA,
    AuthPolicy,
    BaseHTTPHandler,
)
from fr_cli.web.console.api_queries import (
    get_bookmarks, get_global_status, get_hermes_tasks, get_session_detail,
    get_sessions_list, get_stats, get_worktrees,
)
from fr_cli.web.console.events import (
    add_sse_client, get_recent_events, push_event, remove_sse_client,
)

# PWA 静态资源目录
# handler.py 位于 fr_cli/web/console/,而静态资源实际在 fr_cli/web/static/(差一级)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# 只读公开端点(免鉴权):首页与 PWA 静态资源
_CONSOLE_PUBLIC_PATHS = frozenset({
    "/",
    "/index.html",
    "/manifest.json",
    "/icon.svg",
    "/sw.js",
})

# 鉴权失败文案(保持历史文案不变)
_AUTH_ERROR_MESSAGE = "Unauthorized, use Authorization: Bearer <token> or ?token=<token>"


def generate_token() -> str:
    """生成随机 token"""
    return secrets.token_hex(16)


def _make_auth_policy(token: str) -> AuthPolicy:
    """构造 Web 控制台的鉴权策略

    - 全部方法都需要鉴权
    - 只读公开白名单:首页与 PWA 静态资源(仅 GET/HEAD/OPTIONS 生效)
    - 允许 ?token= 查询参数:浏览器 EventSource 无法自定义请求头
    - 未配置 token 时一律拒绝
    """
    return AuthPolicy(
        token=token,
        protected_methods=None,  # 所有方法都要鉴权
        public_paths=set(_CONSOLE_PUBLIC_PATHS),
        allow_query_token=True,
        deny_without_token=True,
        missing_status=401,
        missing_message=_AUTH_ERROR_MESSAGE,
        invalid_status=401,
        invalid_message=_AUTH_ERROR_MESSAGE,
    )


def _handle_sse_response(handler: BaseHTTPRequestHandler):
    """SSE 长连接处理(在 BaseHTTPRequestHandler 实例上调用)"""
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()

    # 先发历史
    try:
        for event in get_recent_events(limit=20):
            line = f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            handler.wfile.write(line.encode("utf-8"))
            handler.wfile.flush()
    except Exception:
        return

    # 注册客户端
    event_signal = threading.Event()
    add_sse_client(event_signal)

    try:
        last_ping = time.time()
        while True:
            signaled = event_signal.wait(timeout=15.0)
            if signaled:
                event_signal.clear()
                try:
                    for event in get_recent_events(limit=10):
                        line = f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                        handler.wfile.write(line.encode("utf-8"))
                        handler.wfile.flush()
                except Exception:
                    return

            # 心跳
            now = time.time()
            if now - last_ping > 10:
                try:
                    handler.wfile.write(b": ping\n\n")
                    handler.wfile.flush()
                except Exception:
                    return
                last_ping = now
    finally:
        remove_sse_client(event_signal)


def _handle_metrics_request(handler: BaseHTTPRequestHandler, qs):
    """处理 /api/metrics 端点(支持 format=json|prom|summary)"""
    fmt = qs.get("format", ["json"])[0]
    try:
        from fr_cli.core.metrics import get_metrics
        plugin = get_metrics()
        if plugin is None:
            handler._send_json(503, {"ok": False, "error": "metrics 未安装(应用未启用)"})
            return
        if fmt in ("prom", "prometheus"):
            text = plugin.metrics_text()
            handler.send_response(200)
            handler.send_header("Content-Type", "text/plain; charset=utf-8")
            handler.end_headers()
            handler.wfile.write(text.encode("utf-8"))
        elif fmt == "summary":
            text = plugin.metrics_summary()
            handler.send_response(200)
            handler.send_header("Content-Type", "text/plain; charset=utf-8")
            handler.end_headers()
            handler.wfile.write(text.encode("utf-8"))
        else:
            handler._send_json(200, {"ok": True, "data": plugin.metrics_json()})
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})


def _serve_static(handler: BaseHTTPRequestHandler, filename: str,
                  content_type: str, cache_max_age: int = 3600):
    """服务 PWA 静态文件"""
    static_file = STATIC_DIR / filename
    # 防止路径穿越(文件名来自代码常量,这里再做一次兜底校验)
    try:
        if static_file.resolve().parent != STATIC_DIR.resolve():
            handler.send_response(404)
            handler.end_headers()
            return
    except OSError:
        handler.send_response(404)
        handler.end_headers()
        return
    if not static_file.exists():
        handler.send_response(404)
        handler.end_headers()
        return
    try:
        body = static_file.read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", f"max-age={cache_max_age}")
        handler.send_header("Service-Worker-Allowed", "/")
        handler.end_headers()
        handler.wfile.write(body)
    except Exception:
        handler.send_response(500)
        handler.end_headers()


def _check_auth(handler: BaseHTTPRequestHandler, token: str) -> bool:
    """Bearer Token 鉴权(支持 Authorization header + ?token=)—— 兼容旧接口

    新实现统一走 fr_cli.core.http_base.AuthPolicy。
    """
    policy = _make_auth_policy(token)
    return policy.verify(handler.headers, handler.path, handler.command)


def make_handler(token: str):
    """构造 HTTP handler 类(工厂)"""
    policy = _make_auth_policy(token)

    class ConsoleHandler(BaseHTTPHandler):
        # 响应包裹策略:保持历史的 {"ok", "data"} 形状
        wrap_mode = WRAP_OK_DATA

        def auth_policy(self) -> AuthPolicy:
            """鉴权策略(闭包捕获 token)"""
            return policy

        def _send_json(self, status: int, payload: Any,
                       extra_headers: Optional[Dict[str, str]] = None) -> None:
            """发送 JSON 响应(保留历史的 no-store 缓存头)"""
            headers = {"Cache-Control": "no-store"}
            headers.update(extra_headers or {})
            super()._send_json(status, payload, headers)

        def _send_html(self, html: str, status: int = 200):
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_static(self, filename: str, content_type: str,
                          cache_max_age: int = 3600):
            return _serve_static(self, filename, content_type, cache_max_age)

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path
            # 基类的 _check_auth 失败时已经发送了 401 错误 JSON
            if not self._check_auth():
                return

            length = int(self.headers.get("Content-Length", 0))
            body_raw = self.rfile.read(length) if length > 0 else b""
            try:
                body = json.loads(body_raw.decode("utf-8")) if body_raw else {}
            except Exception:
                body = {}

            if path == "/api/command":
                # 预留:从 web 端发命令 —— **默认保持关闭**
                #
                # 关闭理由(三条,缺一不可):
                # 1. handler 是工厂闭包,拿不到 AppState —— REPL 命令执行依赖
                #    AppState 里的 executor / VFS / LLM 客户端,闭包里没有,
                #    强行实现只能另起一套旁路执行,等于绕过安全中间件。
                # 2. token 走 query 参数(?token=)有泄漏面 —— 会进浏览器历史、
                #    Referer 头、代理日志;而 /api/command 需要的是高权限 token,
                #    和只读 token 不能混用,一旦复用就等于把只读 token 提权。
                # 3. 命令执行会走到 input() 抢终端 stdin —— FR_CLI_NON_INTERACTIVE
                #    只在 batch 模式设置,交互模式下 HTTP 线程的 input() 会与
                #    REPL 主循环抢同一个 stdin,直接把终端搞挂。
                #
                # 若将来要开放,必须同时具备:独立高权限 token(与只读 token 区分)
                # + 命令白名单 + 强制非交互(设置 FR_CLI_NON_INTERACTIVE)。
                self._send_json(403, {"ok": False, "error": "Web 命令未启用(安全考虑)"})
            elif path == "/api/event":
                # 接收客户端发来的事件(上传日志等)
                try:
                    push_event(body.get("type", "client"), body.get("data", {}))
                    self._send_json(200, {"ok": True})
                except Exception as e:
                    self._send_json(200, {"ok": False, "error": str(e)})
            else:
                self._send_json(404, {"ok": False, "error": f"Unknown endpoint: {path}"})

        def do_GET(self):  # noqa: F811
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            # PWA 静态资源(免鉴权)
            if path == "/manifest.json":
                self._serve_static("manifest.json", "application/manifest+json")
                return
            if path == "/icon.svg":
                self._serve_static("icon.svg", "image/svg+xml")
                return
            if path == "/sw.js":
                self._serve_static("sw.js", "application/javascript", cache_max_age=0)
                return

            # 首页(免鉴权)
            if path == "/" or path == "/index.html":
                from fr_cli.web.console.templates import render_homepage
                self._send_html(render_homepage(token))
                return

            # SSE 实时推送
            if path == "/api/events":
                if not self._check_auth():
                    return
                _handle_sse_response(self)
                return

            # 鉴权(后续 API 都需要)
            if not self._check_auth():
                return

            # API
            if path == "/api/status":
                self._send_json(200, {"ok": True, "data": get_global_status()})
            elif path == "/api/sessions":
                limit = int(qs.get("limit", [50])[0])
                self._send_json(200, {"ok": True, "data": get_sessions_list(limit)})
            elif path.startswith("/api/sessions/"):
                idx = int(path.split("/")[-1])
                detail = get_session_detail(idx)
                if detail:
                    self._send_json(200, {"ok": True, "data": detail})
                else:
                    self._send_json(404, {"ok": False, "error": "会话不存在"})
            elif path == "/api/tasks":
                self._send_json(200, {"ok": True, "data": get_hermes_tasks()})
            elif path == "/api/worktrees":
                self._send_json(200, {"ok": True, "data": get_worktrees()})
            elif path == "/api/bookmarks":
                limit = int(qs.get("limit", [100])[0])
                self._send_json(200, {"ok": True, "data": get_bookmarks(limit)})
            elif path == "/api/stats":
                self._send_json(200, {"ok": True, "data": get_stats()})
            elif path == "/api/health":
                self._send_json(200, {"ok": True, "service": "fr-cli-console"})
            elif path == "/api/metrics":
                _handle_metrics_request(self, qs)
            else:
                self._send_json(404, {"ok": False, "error": f"Unknown endpoint: {path}"})

    return ConsoleHandler
