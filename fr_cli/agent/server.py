"""
Agent HTTP 服务 —— 将分身能力发布为 Web API
供外部系统通过 REST 接口调用 Agent 的推理与执行能力。
使用 Python 标准库 http.server，无需额外依赖。

安全特性：
- 默认仅绑定 127.0.0.1（本地回环）
- 启动时自动生成随机 Token，所有请求需携带 Authorization: Bearer <token>
- CORS 限制为同源，不再开放 *
- 支持 IP 白名单（可选）
"""
import concurrent.futures
import json
import secrets
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from fr_cli.agent.manager import list_agents, load_persona, load_memory, load_skills
from fr_cli.agent.workflow import load_workflow
from fr_cli.agent.executor import run_agent
from fr_cli.agent.workflow import run_workflow as wf_run
from fr_cli.core.result import Result


class _AgentHTTPHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器 —— 路由分发 + Token 认证 + CORS + IP 白名单"""

    # 关闭默认日志输出（避免污染 CLI 界面）
    def log_message(self, format, *args):
        pass

    def _check_auth(self):
        """校验请求是否携带正确的 Bearer Token"""
        expected = getattr(self.server, "_token", None)
        if not expected:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth[7:] == expected:
            return True
        return False

    def _check_ip(self):
        """IP 白名单校验"""
        whitelist = getattr(self.server, "_ip_whitelist", None)
        if not whitelist:
            return True
        client_ip = self.client_address[0]
        return client_ip in whitelist

    def _send_cors_headers(self):
        """发送 CORS 响应头"""
        allowed_origins = getattr(self.server, "_allowed_origins", [])
        origin = self.headers.get("Origin", "")
        if allowed_origins and origin in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
        elif not allowed_origins:
            # 未配置时默认只允许同源（不发送 CORS 头）
            pass
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_result(self, result: Result, status_ok=200, status_fail=500):
        """将 Result 对象序列化为标准 JSON 响应"""
        if result.is_ok():
            self._send_json(status_ok, {"result": result.unwrap(), "error": None})
        else:
            self._send_json(status_fail, {"result": None, "error": result.error})

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length:
                body = self.rfile.read(length).decode("utf-8")
                return json.loads(body)
            return {}
        except Exception:
            return {}

    def do_OPTIONS(self):
        """处理 CORS 预检请求"""
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if not self._check_ip():
            self._send_json(403, {"error": "IP not allowed"})
            return
        if not self._check_auth():
            self._send_json(401, {"error": "Unauthorized"})
            return

        parsed = urlparse(self.path)
        path = parsed.path
        parts = [p for p in path.split("/") if p]

        # /health
        if path == "/health":
            self._send_json(200, {"status": "ok"})
            return

        # /capabilities — 服务元数据与能力声明
        if path == "/capabilities":
            agents = list_agents()
            self._send_json(200, {
                "service": "fr-cli-agent-api",
                "version": "2.1.0",
                "agents": [
                    {
                        "name": a["name"],
                        "has_persona": a["has_persona"],
                        "has_memory": a["has_memory"],
                        "has_skills": a["has_skills"],
                    }
                    for a in agents
                ],
                "endpoints": {
                    "list_agents": "GET /agents",
                    "agent_info": "GET /agents/<name>",
                    "agent_run": "POST /agents/<name>/run",
                    "agent_workflow": "POST /agents/<name>/workflow",
                    "capabilities": "GET /capabilities",
                },
            })
            return

        # /agents
        if path == "/agents":
            agents = list_agents()
            self._send_json(200, {"agents": agents})
            return

        # /agents/<name>
        if len(parts) == 2 and parts[0] == "agents":
            name = parts[1]
            from fr_cli.agent.manager import agent_exists
            if not agent_exists(name):
                self._send_json(404, {"error": f"Agent not found: {name}"})
                return
            info = {
                "name": name,
                "persona": load_persona(name),
                "memory": load_memory(name),
                "skills": load_skills(name),
                "has_workflow": load_workflow(name) is not None,
            }
            self._send_json(200, info)
            return

        self._send_json(404, {"error": "Not found"})

    def _extract_timeout(self, body, default=120, max_timeout=600):
        """从请求体中解析超时时间，限制在合理范围内"""
        timeout = body.get("timeout", default)
        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            timeout = default
        if timeout <= 0:
            timeout = default
        return min(timeout, max_timeout)

    def _run_with_timeout(self, func, timeout, *args, **kwargs):
        """在线程池中执行函数并设置超时；超时后尝试取消任务"""
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                # 若任务尚未开始，可取消；已开始则无法强行中断
                future.cancel()
                raise

    def do_POST(self):
        if not self._check_ip():
            self._send_json(403, {"error": "IP not allowed"})
            return
        if not self._check_auth():
            self._send_json(401, {"error": "Unauthorized"})
            return

        parsed = urlparse(self.path)
        path = parsed.path
        parts = [p for p in path.split("/") if p]
        body = self._read_json()

        # /agents/<name>/run
        if len(parts) == 3 and parts[0] == "agents" and parts[2] == "run":
            name = parts[1]
            from fr_cli.agent.manager import agent_exists
            if not agent_exists(name):
                self._send_json(404, {"error": f"Agent not found: {name}"})
                return
            state = self.server._state
            user_input = body.get("input", "")
            kwargs = body.get("kwargs") or {}
            if user_input:
                kwargs["user_input"] = user_input
            timeout = self._extract_timeout(body, default=120, max_timeout=600)
            try:
                result = self._run_with_timeout(run_agent, timeout, name, state, **kwargs)
            except concurrent.futures.TimeoutError:
                self._send_result(Result.fail(f"Agent 执行超时（{timeout:g}秒）"), status_fail=504)
                return
            except Exception as exc:
                self._send_result(Result.fail(f"Agent 执行异常: {exc}"), status_fail=500)
                return
            self._send_result(result, status_ok=200, status_fail=500)
            return

        # /agents/<name>/workflow
        if len(parts) == 3 and parts[0] == "agents" and parts[2] == "workflow":
            name = parts[1]
            from fr_cli.agent.manager import agent_exists
            if not agent_exists(name):
                self._send_json(404, {"error": f"Agent not found: {name}"})
                return
            state = self.server._state
            user_input = body.get("input", "")
            kwargs = body.get("kwargs") or {}
            timeout = self._extract_timeout(body, default=180, max_timeout=600)
            try:
                wf_result = self._run_with_timeout(
                    wf_run, timeout, name, state, user_input=user_input, **kwargs
                )
            except concurrent.futures.TimeoutError:
                self._send_json(
                    504, {"result": None, "error": f"工作流执行超时（{timeout:g}秒）", "steps": []}
                )
                return
            except Exception as exc:
                self._send_json(500, {"result": None, "error": f"工作流执行异常: {exc}", "steps": []})
                return
            if wf_result.is_ok():
                final, steps = wf_result.unwrap()
                self._send_json(200, {"result": final, "error": None, "steps": steps})
            else:
                self._send_json(500, {"result": None, "error": wf_result.error, "steps": []})
            return

        self._send_json(404, {"error": "Not found"})


class AgentHTTPServer:
    """Agent HTTP 服务守护线程 —— 可启动、停止、查询状态"""

    def __init__(self, state, host="127.0.0.1", port=17890):
        self.state = state
        self.host = host
        self.port = port
        self._server = None
        self._thread = None
        self._token = None
        self._allowed_origins = []
        self._ip_whitelist = []

    def set_cors(self, origins):
        """设置允许的 CORS 来源（默认空列表=不允许跨域）"""
        self._allowed_origins = origins or []

    def set_ip_whitelist(self, ips):
        """设置 IP 白名单（默认空列表=不限制）"""
        self._ip_whitelist = ips or []
        if self._server is not None:
            self._server._ip_whitelist = self._ip_whitelist

    def start(self):
        """启动 HTTP 服务（后台线程），返回 Result[msg]"""
        if self.is_running():
            return Result.fail(f"服务已在运行: http://{self.host}:{self.port}")

        self._token = secrets.token_urlsafe(16)
        self._server = HTTPServer((self.host, self.port), _AgentHTTPHandler)
        self._server._state = self.state
        self._server._token = self._token
        self._server._allowed_origins = self._allowed_origins
        self._server._ip_whitelist = self._ip_whitelist
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        msg = (
            f"Agent HTTP 服务已启动: http://{self.host}:{self.port}\n"
            f"  Token: {self._token}\n"
            f"  使用示例: curl -H 'Authorization: Bearer {self._token}' http://{self.host}:{self.port}/agents\n"
            f"  能力声明: curl -H 'Authorization: Bearer {self._token}' http://{self.host}:{self.port}/capabilities"
        )
        if self.host == "127.0.0.1":
            msg += "\n  ⚠️ 当前仅绑定 127.0.0.1，外部无法访问。如需公网暴露请使用 ngrok 或修改 host。"
        return Result.ok(msg)

    def stop(self):
        """停止 HTTP 服务，返回 Result[msg]"""
        if not self.is_running():
            return Result.fail("服务未运行")
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None
        self._token = None
        return Result.ok("Agent HTTP 服务已停止")

    def is_running(self):
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    def status(self):
        if self.is_running():
            return f"运行中: http://{self.host}:{self.port} (Token: {self._token})"
        return "未运行"

    def get_publish_info(self):
        """获取对外发布的连接信息"""
        if not self.is_running():
            return None
        import socket
        hostname = socket.gethostname()
        try:
            local_ip = socket.getaddrinfo(hostname, None)[0][4][0]
        except Exception:
            local_ip = "127.0.0.1"
        return {
            "url": f"http://{self.host}:{self.port}",
            "token": self._token,
            "local_ip": local_ip,
            "hostname": hostname,
        }
