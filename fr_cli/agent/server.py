"""
Agent HTTP 服务 —— 将分身能力发布为 Web API
供外部系统通过 REST 接口调用 Agent 的推理与执行能力。
使用 Python 标准库 http.server，无需额外依赖。
"""
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from fr_cli.agent.manager import list_agents, load_persona, load_memory, load_skills
from fr_cli.agent.workflow import load_workflow
from fr_cli.agent.executor import run_agent
from fr_cli.agent.workflow import run_workflow as wf_run


class _AgentHTTPHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器 —— 路由分发"""

    # 关闭默认日志输出（避免污染 CLI 界面）
    def log_message(self, format, *args):
        pass

    def _send_json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

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
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        parts = [p for p in path.split("/") if p]

        # /health
        if path == "/health":
            self._send_json(200, {"status": "ok"})
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

    def do_POST(self):
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
            kwargs = body.get("kwargs", {})
            if user_input:
                kwargs["user_input"] = user_input
            result, error = run_agent(name, state, **kwargs)
            resp = {"result": result, "error": error}
            self._send_json(200 if not error else 500, resp)
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
            kwargs = body.get("kwargs", {})
            final, error, steps = wf_run(name, state, user_input=user_input, **kwargs)
            resp = {"result": final, "error": error, "steps": steps}
            self._send_json(200 if not error else 500, resp)
            return

        self._send_json(404, {"error": "Not found"})


class AgentHTTPServer:
    """Agent HTTP 服务守护线程 —— 可启动、停止、查询状态"""

    def __init__(self, state, host="0.0.0.0", port=17890):
        self.state = state
        self.host = host
        self.port = port
        self._server = None
        self._thread = None

    def start(self):
        """启动 HTTP 服务（后台线程）"""
        if self.is_running():
            return False, f"服务已在运行: http://{self.host}:{self.port}"

        self._server = HTTPServer((self.host, self.port), _AgentHTTPHandler)
        self._server._state = self.state
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return True, f"Agent HTTP 服务已启动: http://{self.host}:{self.port}"

    def stop(self):
        """停止 HTTP 服务"""
        if not self.is_running():
            return False, "服务未运行"
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None
        return True, "Agent HTTP 服务已停止"

    def is_running(self):
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    def status(self):
        if self.is_running():
            return f"运行中: http://{self.host}:{self.port}"
        return "未运行"
