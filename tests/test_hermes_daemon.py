"""
Hermes HTTP Daemon 测试
覆盖：公开只读端点(/health)、鉴权契约、任务创建、任务查询、/execute 提交为任务。

鉴权契约(v3.x HTTP 服务统一后):
- 所有方法(含 GET)默认都需要 `Authorization: Bearer <token>`
- 只读公开白名单默认仅 /health(可用 daemon.public_paths 扩展)
"""
import json
import threading
import time
from urllib.request import Request, urlopen
from unittest.mock import MagicMock

import pytest

from fr_cli.agent.hermes_daemon import HermesDaemon
from fr_cli.agent.hermes import HermesEngine


@pytest.fixture
def tmp_hermes_dir(tmp_path):
    return tmp_path / "hermes"


@pytest.fixture
def engine(tmp_hermes_dir, monkeypatch):
    monkeypatch.setattr("fr_cli.agent.hermes.HERMES_DIR", tmp_hermes_dir)
    monkeypatch.setattr("fr_cli.agent.hermes.HERMES_TASKS_FILE", tmp_hermes_dir / "tasks.json")
    monkeypatch.setattr("fr_cli.agent.hermes.HERMES_GOALS_FILE", tmp_hermes_dir / "goals.json")
    monkeypatch.setattr("fr_cli.agent.hermes.HERMES_ANALYTICS_FILE", tmp_hermes_dir / "analytics.json")
    monkeypatch.setattr("fr_cli.agent.hermes.HERMES_LOG_FILE", tmp_hermes_dir / "hermes.log")

    state = MagicMock()
    state.model_name = "mock-model"
    state.messages = []
    state.master_agent = MagicMock()
    state.master_agent.handle = MagicMock(return_value=("done", True))

    eng = HermesEngine(state_provider=lambda: state)
    eng.scheduler.stop()
    yield eng
    eng.scheduler.stop()


@pytest.fixture
def daemon_url(engine, tmp_path):
    """启动真实 Hermes daemon，返回 base URL 和 token"""
    daemon = HermesDaemon(port=0, engine=engine)
    daemon.token = "test-token"

    # port=0 会让系统分配端口，但需要先启动才能知道端口
    # 这里先指定一个随机可用端口
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    daemon.port = port

    t = threading.Thread(target=daemon.start, daemon=True)
    t.start()
    time.sleep(0.2)
    yield f"http://127.0.0.1:{port}", "test-token"
    daemon.stop()


def _get(url, daemon_url, auth=False):
    """GET 请求；auth=True 时带 Authorization: Bearer <token>"""
    from urllib.error import HTTPError
    base, token = daemon_url
    full = base + url
    req = Request(full, method="GET")
    if auth:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(req, timeout=2) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        return json.loads(e.read().decode())


def _post(url, data, daemon_url, auth=False):
    from urllib.error import HTTPError
    base, token = daemon_url
    full = base + url
    body = json.dumps(data).encode()
    req = Request(full, data=body, method="POST",
                  headers={"Content-Type": "application/json"})
    if auth:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(req, timeout=2) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        return json.loads(e.read().decode())


class TestHermesDaemonThreading:
    """v2.8.7(P2-4)：daemon 此前用单线程 HTTPServer —— 一个长连接就把服务卡死"""

    def _start(self, engine, port):
        daemon = HermesDaemon(port=port, engine=engine)
        daemon.token = "test-token"
        t = threading.Thread(target=daemon.start, daemon=True)
        t.start()
        time.sleep(0.2)
        return daemon

    def test_uses_threading_server(self, engine):
        from fr_cli.core.http_base import BaseHTTPServer

        daemon = self._start(engine, 0)
        try:
            assert isinstance(daemon._server, BaseHTTPServer)
            # 线程化：主线程退出时不会被挂起连接卡住
            assert daemon._server.daemon_threads is True
        finally:
            daemon.stop()

    def test_concurrent_requests_are_not_serialized(self, engine):
        """并发 GET 都应成功返回 —— 单线程下慢请求会把后续请求全堵住"""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        daemon = self._start(engine, port)
        base = f"http://127.0.0.1:{port}"
        try:
            results = []

            def hit():
                results.append(_get("/health", (base, "test-token")))

            threads = [threading.Thread(target=hit) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            assert len(results) == 5
            assert all(r.get("status") == "ok" for r in results)
        finally:
            daemon.stop()

    def test_stop_takes_effect_promptly(self, engine):
        """stop() 应在半秒内生效 —— server.timeout 让轮询循环能退出"""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        daemon = self._start(engine, port)
        started = time.time()
        daemon.stop()
        # running 标志立即翻转；服务器 socket 在 start() 的循环退出时关闭
        assert daemon.running is False
        assert time.time() - started < 2.0


class TestHermesDaemonEndpoints:
    def test_health_public(self, daemon_url):
        """只读公开白名单：/health 无需 token"""
        response = _get("/health", daemon_url)
        assert response["status"] == "ok"
        assert response["daemon"] == "hermes"
        assert "engine_ready" in response

    def test_get_requires_auth(self, daemon_url):
        """GET 不再无条件免鉴权：缺少 Authorization 头返回 401"""
        response = _get("/tasks", daemon_url)
        assert "error" in response
        assert "Missing Authorization" in response["error"]

    def test_get_invalid_token(self, daemon_url):
        """token 不匹配返回 403"""
        from urllib.error import HTTPError
        base, _ = daemon_url
        req = Request(base + "/tasks", method="GET")
        req.add_header("Authorization", "Bearer wrong-token")
        try:
            with urlopen(req, timeout=2) as resp:
                payload = json.loads(resp.read().decode())
        except HTTPError as e:
            payload = json.loads(e.read().decode())
        assert payload["error"] == "Invalid token"

    def test_public_paths_configurable(self, engine):
        """公开只读白名单可通过 daemon.public_paths 配置"""
        import socket
        daemon = HermesDaemon(port=0, engine=engine)
        daemon.token = "test-token"
        daemon.public_paths = {"/health", "/info"}
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        daemon.port = port
        t = threading.Thread(target=daemon.start, daemon=True)
        t.start()
        time.sleep(0.2)
        try:
            base = (f"http://127.0.0.1:{port}", "test-token")
            # /info 在自定义白名单里 -> 免鉴权
            info = _get("/info", base)
            assert info["daemon"] == "hermes"
            # /tasks 不在白名单 -> 仍然需要鉴权
            tasks = _get("/tasks", base)
            assert "Missing Authorization" in tasks["error"]
        finally:
            daemon.stop()

    def test_create_task_requires_auth(self, daemon_url):
        response = _post("/task", {"task": "hello"}, daemon_url, auth=False)
        assert "error" in response
        assert "Missing Authorization" in response["error"]

    def test_create_task_with_auth(self, daemon_url):
        response = _post("/task", {"task": "hello"}, daemon_url, auth=True)
        assert "id" in response
        assert response["status"] == "pending"

    def test_execute_queued_as_task(self, daemon_url):
        response = _post("/execute", {"command": "ls -la"}, daemon_url, auth=True)
        assert "id" in response
        assert response["status"] == "pending"
        assert "queued as Hermes task" in response["note"]

    def test_get_task(self, daemon_url):
        created = _post("/task", {"task": "research"}, daemon_url, auth=True)
        task_id = created["id"]
        response = _get(f"/tasks/{task_id}", daemon_url, auth=True)
        assert response["task"]["id"] == task_id
        assert response["task"]["description"] == "research"

    def test_get_task_not_found(self, daemon_url):
        response = _get("/tasks/not-exist", daemon_url, auth=True)
        assert response["error"] == "Task not found"

    def test_capabilities_requires_auth(self, daemon_url):
        """/capabilities 不再公开：必须带 token"""
        unauthorized = _get("/capabilities", daemon_url)
        assert "Missing Authorization" in unauthorized["error"]
        response = _get("/capabilities", daemon_url, auth=True)
        assert "endpoints" in response
        paths = [e["path"] for e in response["endpoints"]]
        assert "/task" in paths
        assert "/execute" in paths
        assert "/chat" in paths

    def test_create_autonomous_task_needs_confirmation(self, daemon_url):
        response = _post(
            "/task",
            {"task": "delete everything", "execution_mode": "autonomous"},
            daemon_url,
            auth=True,
        )
        assert "id" in response
        assert response["needs_confirmation"] is True
        # 通过 GET 确认任务状态应为 paused
        task = _get(f"/tasks/{response['id']}", daemon_url, auth=True)
        assert task["task"]["status"] == "paused"

    def test_confirm_autonomous_task(self, daemon_url):
        created = _post(
            "/task",
            {"task": "autonomous job", "execution_mode": "autonomous"},
            daemon_url,
            auth=True,
        )
        task_id = created["id"]
        response = _post(f"/tasks/{task_id}/confirm", {}, daemon_url, auth=True)
        assert response["confirmed"] is True
        task = _get(f"/tasks/{task_id}", daemon_url, auth=True)
        assert task["task"]["status"] == "pending"

    def test_confirm_missing_task(self, daemon_url):
        response = _post("/tasks/not-exist/confirm", {}, daemon_url, auth=True)
        assert response["confirmed"] is False

    def test_review_queue_list(self, daemon_url, tmp_path, monkeypatch):
        from fr_cli.agent.review_queue import PersistentReviewQueue
        monkeypatch.setattr("fr_cli.agent.review_queue.HERMES_REVIEW_QUEUE_FILE", tmp_path / "review_queue.json")
        q = PersistentReviewQueue()
        q.add("plugin", "def run(): pass", task_id="t1")
        response = _get("/review", daemon_url, auth=True)
        assert "items" in response
        assert response["counts"]["pending"] == 1

    def test_review_approve_plugin(self, daemon_url, tmp_path, monkeypatch):
        from fr_cli.agent.review_queue import PersistentReviewQueue
        monkeypatch.setattr("fr_cli.agent.review_queue.HERMES_REVIEW_QUEUE_FILE", tmp_path / "review_queue.json")
        monkeypatch.setattr("fr_cli.agent.artifact_detector.PLUGIN_DIR", tmp_path / "plugins")
        q = PersistentReviewQueue()
        item = q.add("plugin", "def run(args=''):\n    return 'hello'\n", task_id="t1")
        response = _post(f"/review/{item.id}/approve", {"name": "hello_plugin"}, daemon_url, auth=True)
        assert response["approved"] is True
        assert response["installed"] is True
        assert response["name"] == "hello_plugin"

    def test_review_reject(self, daemon_url, tmp_path, monkeypatch):
        from fr_cli.agent.review_queue import PersistentReviewQueue
        monkeypatch.setattr("fr_cli.agent.review_queue.HERMES_REVIEW_QUEUE_FILE", tmp_path / "review_queue.json")
        q = PersistentReviewQueue()
        item = q.add("agent", "def run(context, **kwargs): pass", task_id="t2")
        response = _post(f"/review/{item.id}/reject", {}, daemon_url, auth=True)
        assert response["rejected"] is True
