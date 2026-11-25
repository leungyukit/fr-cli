"""
Bot 网关 —— 平台 webhook 的统一入口

v2.8.7 新增。

所有平台的入站 webhook 都打到这一个 HTTP 服务：

    POST /bot/<channel>       入站消息（平台 webhook）
    POST /bot/send            主动发送（外部触发 / 测试）
    GET  /bot/health          健康检查
    GET  /bot/status          运行状态与统计

关键设计：
  - **立即 ack，异步处理**。平台 webhook 通常有 3~5 秒超时，
    而 LLM 调用可能几十秒。网关先回 200，再在后台线程里处理并回复用户。
  - **ThreadingHTTPServer**（不是单线程 HTTPServer）——
    fr-cli 的 agent/server.py 是单线程的，并发请求会串行排队。
  - **平台鉴权交给通道自己**（``Channel.verify``），
    网关只对管理类接口（/bot/status 等）做 Bearer Token 校验。

安全：
  - 未知通道直接 404
  - 验签失败返回 401
  - 解析异常返回 400（不泄漏内部堆栈）
"""
from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from fr_cli.bot.core.channel import Channel
from fr_cli.bot.core.dispatcher import BotDispatcher
from fr_cli.bot.core.message import BotMessage, BotReply

__all__ = ["BotGateway", "DEFAULT_PORT"]

#: 网关默认端口
DEFAULT_PORT = 8790


class BotGateway:
    """Bot HTTP 网关。

    Args:
        dispatcher: 调度器
        channels:   通道名 → Channel 实例
        host:       监听地址
        port:       监听端口
        token:      管理接口的 Bearer Token；None 表示自动生成
    """

    def __init__(self, dispatcher: BotDispatcher, channels: Dict[str, Channel],
                 host: str = "127.0.0.1", port: int = DEFAULT_PORT,
                 token: Optional[str] = None):
        self.dispatcher = dispatcher
        self.channels = dict(channels or {})
        self.host = host
        self.port = port
        self.token = token or secrets.token_urlsafe(16)
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._workers: Optional[Any] = None
        self._started_at: Optional[float] = None
        self._lock = threading.Lock()

    # ---------- 生命周期 ----------

    def start(self) -> Dict[str, Any]:
        """启动网关（后台线程）。"""
        with self._lock:
            if self._server is not None:
                return {"ok": False, "error": "网关已在运行"}

            gateway = self

            # BaseHTTPRequestHandler.__init__ 会立刻处理请求，不接受额外 kwargs，
            # 所以用「绑定 gateway 的子类」而不是构造参数。
            class Handler(BotRequestHandler):
                pass

            Handler.gateway = gateway

            try:
                server = ThreadingHTTPServer((self.host, self.port), Handler)
            except OSError as e:
                return {"ok": False, "error": f"无法绑定 {self.host}:{self.port}: {e}"}

            server.daemon_threads = True
            # 端口传 0 时由系统分配 —— 回填真实端口，否则 URL 不可用
            try:
                self.port = server.server_address[1]
            except Exception:
                pass
            self._server = server
            self._thread = threading.Thread(target=server.serve_forever,
                                            daemon=True, name="fr-cli-bot-gateway")
            self._thread.start()
            import time
            self._started_at = time.time()
            return {
                "ok": True,
                "url": f"http://{self.host}:{self.port}",
                "token": self.token,
                "channels": sorted(self.channels.keys()),
            }

    def stop(self) -> Dict[str, Any]:
        """停止网关。"""
        with self._lock:
            if self._server is None:
                return {"ok": False, "error": "网关未运行"}
            try:
                self._server.shutdown()
            except Exception:
                pass
            try:
                self._server.server_close()
            except Exception:
                pass
            self._server = None
            self._thread = None
            self._started_at = None
            return {"ok": True}

    def is_running(self) -> bool:
        return self._server is not None

    def status(self) -> Dict[str, Any]:
        """运行状态与统计。"""
        import time
        return {
            "running": self.is_running(),
            "host": self.host,
            "port": self.port,
            "channels": {name: ch.describe() for name, ch in self.channels.items()},
            "uptime": (time.time() - self._started_at) if self._started_at else 0,
            "stats": self.dispatcher.stats(),
        }


class BotRequestHandler(BaseHTTPRequestHandler):
    """Bot 网关的 HTTP 请求处理器。"""

    gateway: BotGateway = None  # 由 start() 注入
    _raw_body: bytes = b""      # 原始请求体（签名校验用）

    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 静默默认日志
        pass

    # ---------- 工具 ----------

    def _send_json(self, data: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _check_token(self) -> bool:
        """管理接口鉴权。"""
        auth = self.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.startswith("Bearer ") else ""
        if not token:
            qs = parse_qs(urlparse(self.path).query)
            token = (qs.get("token") or [""])[0]
        if not token or token != self.gateway.token:
            self._send_json({"ok": False, "error": "Unauthorized"}, 401)
            return False
        return True

    def _read_body(self) -> Any:
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            self._raw_body = b""
            return {}
        raw = self.rfile.read(length)
        self._raw_body = raw
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            try:
                return json.loads(raw.decode("utf-8", errors="replace"))
            except Exception:
                return {}

    def _headers_dict(self) -> Dict[str, str]:
        """请求头字典。

        额外注入**原始请求体**（``body`` 键）—— 平台签名（飞书 / 企微等）
        必须基于原始字节计算，用重新序列化的 JSON 会对不上。
        """
        headers = {k.lower(): v for k, v in self.headers.items()}
        raw = getattr(self, "_raw_body", b"") or b""
        try:
            headers["body"] = raw.decode("utf-8", errors="replace")
        except Exception:
            headers["body"] = ""
        return headers

    # ---------- 路由 ----------

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/bot/health":
            self._send_json({"ok": True, "running": self.gateway.is_running()})
            return
        if path == "/bot/status":
            if not self._check_token():
                return
            self._send_json({"ok": True, "data": self.gateway.status()})
            return
        self._send_json({"ok": False, "error": f"Unknown endpoint: {path}"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/bot/send":
            if not self._check_token():
                return
            self._handle_send()
            return

        if path.startswith("/bot/"):
            channel_name = path[len("/bot/"):].strip("/")
            self._handle_inbound(channel_name)
            return

        self._send_json({"ok": False, "error": f"Unknown endpoint: {path}"}, 404)

    # ---------- 处理 ----------

    def _handle_inbound(self, channel_name: str):
        """处理平台入站 webhook。"""
        channel = self.gateway.channels.get(channel_name)
        if channel is None:
            self._send_json({"ok": False, "error": f"Unknown channel: {channel_name}"}, 404)
            return

        payload = self._read_body()
        headers = self._headers_dict()

        # 平台握手挑战（如飞书 url_verification）—— 直接回，不进消息流
        try:
            challenge = channel.challenge_response(headers, payload)
        except Exception:
            challenge = None
        if challenge is not None:
            self._send_json(challenge)
            return

        # 平台验签
        try:
            if not channel.verify(headers, payload):
                self._send_json({"ok": False, "error": "验签失败"}, 401)
                return
        except Exception as e:
            self._send_json({"ok": False, "error": f"验签异常: {e}"}, 401)
            return

        # 解析
        try:
            message = channel.parse(headers, payload)
        except Exception as e:
            self._send_json({"ok": False, "error": f"消息解析失败: {e}"}, 400)
            return
        if message is None:
            self._send_json({"ok": True, "note": "非消息 payload"})
            return

        # 立即 ack（平台 webhook 有超时），后续异步处理
        self._send_json({"ok": True, "accepted": True})
        threading.Thread(target=self._process, args=(channel, message),
                         daemon=True, name="fr-cli-bot-worker").start()

    def _process(self, channel: Channel, message: BotMessage):
        """后台处理一条消息并把回复发回平台。"""
        dispatcher = self.gateway.dispatcher
        try:
            # 先看是不是在回答一个待确认的工具调用
            if dispatcher.deliver_answer(message):
                return

            result = dispatcher.handle(message)
            if not result.handled or not result.reply:
                return

            reply = BotReply(
                chat_id=message.chat_id,
                text=result.reply,
                thread_id=message.thread_id,
                reply_to=message.message_id,
            )
            channel.send(reply)
        except Exception:
            pass

    def _handle_send(self):
        """主动发送一条消息。"""
        body = self._read_body()
        if not isinstance(body, dict):
            self._send_json({"ok": False, "error": "body 必须是 JSON 对象"}, 400)
            return
        channel_name = body.get("channel") or ""
        channel = self.gateway.channels.get(channel_name)
        if channel is None:
            self._send_json({"ok": False, "error": f"Unknown channel: {channel_name}"}, 404)
            return
        reply = BotReply(
            chat_id=str(body.get("chat_id") or ""),
            text=str(body.get("text") or ""),
            thread_id=str(body.get("thread_id") or ""),
        )
        try:
            channel.send(reply)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, 500)
            return
        if reply.error:
            self._send_json({"ok": False, "error": reply.error}, 500)
        else:
            self._send_json({"ok": True})
