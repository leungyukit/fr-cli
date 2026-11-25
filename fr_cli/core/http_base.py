"""
HTTP 服务公共基类 —— 统一 fr-cli 三套 HTTP 服务的骨架、鉴权与响应包裹

背景
----
fr-cli 此前有三套各自为政的 HTTP 服务，骨架重复且行为不一致：
- fr_cli/agent/server.py       Agent 分身对外 REST API（{"result","error"} 包裹，单线程）
- fr_cli/agent/hermes_api.py   Hermes 后台任务 API（扁平 JSON，GET 曾完全免鉴权）
- fr_cli/web/console/handler.py Web 控制台（{"ok","data"} 包裹，静态资源路径指向不存在目录）

本模块提供公共骨架
------------------
1. BaseHTTPServer（继承标准库 ThreadingHTTPServer）—— 并发请求不再排队
2. 可插拔响应包裹策略 —— result_error / ok_data / flat
   三个服务各自沿用现有包裹方式，**不改变任何服务的现有响应形状**
3. 统一 Bearer Token 鉴权
   - protected_methods：决定哪些 HTTP 方法需要鉴权（None = 全部方法）
   - public_paths：明确的只读公开白名单（如 Hermes 的 /health），仅对 GET/HEAD/OPTIONS 生效
   - allow_query_token：是否允许 ?token= 查询参数（Web 控制台的 EventSource 不支持自定义头）
4. 统一异常处理 —— handler 内未捕获异常统一转成错误 JSON，且不再往终端打栈

放在 fr_cli/core/ 而不是 fr_cli/web/ 的理由
------------------------------------------
fr_cli/core/ 是全项目共享的基础设施层（agent / web / command 都依赖它）；
若把公共基类放在 fr_cli/web/ 下，fr_cli/agent/* 就得反向依赖 web 层，破坏分层。

只依赖 Python 标准库，不引入新依赖。
"""
from __future__ import annotations

import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Iterable, Optional, Set
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# 响应包裹策略标识
# ---------------------------------------------------------------------------
WRAP_RESULT_ERROR = "result_error"  # {"result": ..., "error": ...}
WRAP_OK_DATA = "ok_data"            # {"ok": bool, "data": ...}
WRAP_FLAT = "flat"                  # 原样返回（扁平 JSON）

WRAP_MODES = (WRAP_RESULT_ERROR, WRAP_OK_DATA, WRAP_FLAT)

# 只读方法 —— 公开白名单只对这些方法生效（POST 到同一路径仍需鉴权）
READ_ONLY_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def wrap_payload(
    mode: str,
    data: Any = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """按包裹策略构造响应体

    Args:
        mode: 包裹策略（result_error / ok_data / flat）
        data: 成功时的负载
        error: 错误文案（非 None 表示失败响应）

    Returns:
        响应体 dict
    """
    if mode == WRAP_RESULT_ERROR:
        if error is not None:
            return {"result": None, "error": error}
        return {"result": data, "error": None}
    if mode == WRAP_OK_DATA:
        if error is not None:
            return {"ok": False, "error": error}
        return {"ok": True, "data": data}
    # flat：成功时原样返回，失败时统一为 {"error": msg}
    if error is not None:
        return {"error": error}
    if isinstance(data, dict):
        return data
    return {"data": data}


class AuthPolicy:
    """统一鉴权策略

    Attributes:
        token: 期望的 Bearer Token；空串表示"未配置 token"
        protected_methods: 需要鉴权的 HTTP 方法集合；None 表示**所有方法**都需要鉴权
        public_paths: 免鉴权的只读路径白名单（仅对 GET/HEAD/OPTIONS 生效）
        allow_query_token: 是否允许 ?token= 查询参数
        deny_without_token: 未配置 token 时是否一律拒绝（Hermes 用；
            agent/console 在未配置 token 时放行，保持历史行为）
        missing_status / missing_message: 缺少 Authorization 头时的响应
        invalid_status / invalid_message: token 不匹配时的响应
    """

    def __init__(
        self,
        token: str = "",
        protected_methods: Optional[Iterable[str]] = None,
        public_paths: Optional[Iterable[str]] = None,
        allow_query_token: bool = False,
        deny_without_token: bool = False,
        missing_status: int = 401,
        missing_message: str = "Missing Authorization: Bearer <token>",
        invalid_status: int = 403,
        invalid_message: str = "Invalid token",
    ) -> None:
        self.token = token or ""
        self.protected_methods: Optional[Set[str]] = (
            None if protected_methods is None
            else {m.upper() for m in protected_methods}
        )
        self.public_paths: Set[str] = set(public_paths or ())
        self.allow_query_token = allow_query_token
        self.deny_without_token = deny_without_token
        self.missing_status = missing_status
        self.missing_message = missing_message
        self.invalid_status = invalid_status
        self.invalid_message = invalid_message

    def requires_auth(self, method: str, path: str) -> bool:
        """判断「某方法 + 某路径」是否需要鉴权

        Args:
            method: HTTP 方法（大小写不敏感）
            path: 请求路径（不含 query）

        Returns:
            True 表示需要鉴权
        """
        if not self.token:
            return self.deny_without_token
        method = (method or "").upper()
        if self.protected_methods is not None and method not in self.protected_methods:
            return False
        # 公开白名单只对只读方法生效 —— 写操作即使路径相同也必须鉴权
        if method in READ_ONLY_METHODS and path in self.public_paths:
            return False
        return True

    def extract_token(self, headers: Any, raw_path: str) -> Optional[str]:
        """从请求头/查询参数中提取 token

        Args:
            headers: 请求头对象（需支持 .get）
            raw_path: 原始请求路径（含 query）

        Returns:
            token 字符串；请求未携带 token 时返回 None（用于区分"缺失"与"错误"）
        """
        auth = headers.get("Authorization", "") or ""
        if auth.startswith("Bearer "):
            return auth[len("Bearer "):].strip()
        if self.allow_query_token:
            qs = parse_qs(urlparse(raw_path).query)
            value = qs.get("token", [None])[0]
            if value:
                return value
        return None

    def verify(self, headers: Any, raw_path: str, method: str = "GET") -> bool:
        """纯逻辑校验（不发送任何响应）

        Returns:
            True 表示放行
        """
        path = urlparse(raw_path).path
        if not self.requires_auth(method, path):
            return True
        provided = self.extract_token(headers, raw_path)
        if provided is None:
            return False
        try:
            return secrets.compare_digest(provided, self.token)
        except TypeError:
            # 非 ASCII token 导致 compare_digest 抛错，视为不匹配
            return False


class BaseHTTPHandler(BaseHTTPRequestHandler):
    """HTTP 处理器公共基类 —— 统一鉴权 / 响应包裹 / 异常处理

    子类只需覆写 do_GET / do_POST 等路由方法；鉴权与响应发送走本基类的统一实现。
    """

    # 响应包裹策略（子类覆盖）
    wrap_mode: str = WRAP_FLAT
    # JSON Content-Type（子类可覆盖，保持各服务历史取值）
    json_content_type: str = "application/json; charset=utf-8"
    # 是否发送 Content-Length（默认发送，便于客户端按长度读取）
    send_content_length: bool = True

    # ------------------------------------------------------------------
    # 基础工具
    # ------------------------------------------------------------------
    def log_message(self, fmt, *args):
        """静默默认日志（避免污染 CLI 界面）"""
        return

    def auth_policy(self) -> AuthPolicy:
        """返回当前请求的鉴权策略

        默认从 server.auth_policy 取；取不到时返回"不鉴权"的空策略。
        子类可覆写以支持动态 token（如 Hermes 从 daemon.token 读取）。
        """
        policy = getattr(self.server, "auth_policy", None)
        if isinstance(policy, AuthPolicy):
            return policy
        return AuthPolicy()

    def _extra_response_headers(self) -> Dict[str, str]:
        """额外的响应头（子类覆盖，如 CORS）"""
        return {}

    # ------------------------------------------------------------------
    # 鉴权
    # ------------------------------------------------------------------
    def _check_auth(self) -> bool:
        """校验请求鉴权；失败时已发送错误响应

        Returns:
            True 表示放行
        """
        policy = self.auth_policy()
        path = urlparse(self.path).path
        if not policy.requires_auth(self.command, path):
            return True
        provided = policy.extract_token(self.headers, self.path)
        if provided is None:
            self._send_auth_error(policy.missing_status, policy.missing_message)
            return False
        try:
            valid = secrets.compare_digest(provided, policy.token)
        except TypeError:
            valid = False
        if not valid:
            self._send_auth_error(policy.invalid_status, policy.invalid_message)
            return False
        return True

    def _send_auth_error(self, status: int, message: str) -> None:
        """发送鉴权失败响应

        三个服务历史上的鉴权失败响应都是扁平的 {"error": ...}，此处保持不变，
        避免因为统一包裹策略而改变任何服务的现有响应形状。
        """
        self._send_json(status, {"error": message})

    # ------------------------------------------------------------------
    # 响应
    # ------------------------------------------------------------------
    def _send_json(
        self,
        status: int,
        payload: Any,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """发送原始 JSON 响应（不套包裹策略）"""
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", self.json_content_type)
        if self.send_content_length:
            self.send_header("Content-Length", str(len(body)))
        for key, value in self._extra_response_headers().items():
            self.send_header(key, value)
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_wrapped(self, status: int, data: Any = None, error: Optional[str] = None) -> None:
        """按包裹策略发送响应"""
        self._send_json(status, wrap_payload(self.wrap_mode, data=data, error=error))

    def _send_error(self, status: int, message: str) -> None:
        """按包裹策略发送错误响应"""
        self._send_json(status, wrap_payload(self.wrap_mode, error=message))

    def _read_json_body(self) -> Dict[str, Any]:
        """读取并解析 JSON 请求体（解析失败返回空 dict）"""
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # 异常处理
    # ------------------------------------------------------------------
    def handle_one_request(self) -> None:
        """统一异常处理：未捕获异常转成错误 JSON，而不是静默断开连接

        同时避免 socketserver 把 traceback 打到终端（污染 CLI 界面）。
        """
        try:
            super().handle_one_request()
        except Exception as exc:  # noqa: BLE001 —— 兜底：任何异常都要转成 JSON
            try:
                self._send_error(500, f"Internal server error: {exc}")
            except Exception:
                pass


class BaseHTTPServer(ThreadingHTTPServer):
    """带鉴权策略的线程化 HTTP 服务器

    - 并发处理：每个连接一个线程，长连接（如 SSE）不再阻塞其它请求
    - daemon_threads = True：主进程退出时不会被挂起连接卡住
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address,
        RequestHandlerClass,
        auth_policy: Optional[AuthPolicy] = None,
        bind_and_activate: bool = True,
    ) -> None:
        self.auth_policy = auth_policy or AuthPolicy()
        super().__init__(server_address, RequestHandlerClass, bind_and_activate)
