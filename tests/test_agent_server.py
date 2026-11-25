"""
Agent HTTP 服务测试 —— 验证 /run 与 /workflow 接口的认证、超时与异常处理。
"""
import http.client
import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from fr_cli.agent.server import _AgentHTTPHandler, AgentHTTPServer
from fr_cli.core.http_base import BaseHTTPServer

AGENT_EXISTS = "fr_cli.agent.manager.agent_exists"


@pytest.fixture
def state():
    return MagicMock()


@pytest.fixture
def server(state):
    srv = AgentHTTPServer(state, host="127.0.0.1", port=0)
    ok, _ = srv.start()
    assert ok
    try:
        yield srv
    finally:
        if srv.is_running():
            srv.stop()


def _request(srv, method, path, body=None, token=None):
    port = srv._server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Authorization": f"Bearer {token or srv._token}"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=headers)
    else:
        conn.request(method, path, headers=headers)
    resp = conn.getresponse()
    data = json.loads(resp.read().decode("utf-8"))
    conn.close()
    return resp.status, data


def test_run_success(server):
    captured = {}

    def fake_run_with_timeout(self, func, timeout, *args, **kwargs):
        from fr_cli.core.result import Result
        captured["func"] = func
        captured["timeout"] = timeout
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Result.ok("agent-result")

    with patch(AGENT_EXISTS, return_value=True), \
         patch.object(_AgentHTTPHandler, "_run_with_timeout", fake_run_with_timeout):
        status, data = _request(
            server,
            "POST",
            "/agents/demo/run",
            {"input": "hi", "timeout": 60, "kwargs": {"x": 1}},
        )

    assert status == 200
    assert data == {"result": "agent-result", "error": None}
    assert captured["timeout"] == 60
    assert captured["args"][0] == "demo"
    assert captured["kwargs"]["user_input"] == "hi"
    assert captured["kwargs"]["x"] == 1


def test_run_timeout(server):
    with patch(AGENT_EXISTS, return_value=True), \
         patch.object(_AgentHTTPHandler, "_run_with_timeout", side_effect=TimeoutError):
        status, data = _request(server, "POST", "/agents/demo/run", {"input": "hi"})

    assert status == 504
    assert data["result"] is None
    assert "120" in data["error"]


def test_run_exception(server):
    with patch(AGENT_EXISTS, return_value=True), \
         patch.object(_AgentHTTPHandler, "_run_with_timeout", side_effect=RuntimeError("boom")):
        status, data = _request(server, "POST", "/agents/demo/run", {"input": "hi"})

    assert status == 500
    assert "boom" in data["error"]


def test_workflow_success(server):
    captured = {}

    def fake_run_with_timeout(self, func, timeout, *args, **kwargs):
        from fr_cli.core.result import Result
        captured["timeout"] = timeout
        captured["kwargs"] = kwargs
        return Result.ok(("workflow-result", ["step1"]))

    with patch(AGENT_EXISTS, return_value=True), \
         patch.object(_AgentHTTPHandler, "_run_with_timeout", fake_run_with_timeout):
        status, data = _request(
            server,
            "POST",
            "/agents/demo/workflow",
            {"input": "analyze", "timeout": 90},
        )

    assert status == 200
    assert data == {"result": "workflow-result", "error": None, "steps": ["step1"]}
    assert captured["timeout"] == 90
    assert captured["kwargs"]["user_input"] == "analyze"


def test_workflow_timeout(server):
    with patch(AGENT_EXISTS, return_value=True), \
         patch.object(_AgentHTTPHandler, "_run_with_timeout", side_effect=TimeoutError):
        status, data = _request(server, "POST", "/agents/demo/workflow", {"input": "hi"})

    assert status == 504
    assert data["steps"] == []
    assert "180" in data["error"]


def test_agent_not_found(server):
    with patch(AGENT_EXISTS, return_value=False):
        status, data = _request(server, "POST", "/agents/missing/run", {"input": "hi"})

    assert status == 404
    assert "missing" in data["error"]


def test_run_failure_does_not_leak_partial_data(server):
    """工作流失败时 Result.data 带着已成功步骤的结果，但 HTTP 响应不暴露它。

    v3.1：agent/executor.py 改为 Result.fail(error, data=wf_result.data)，
    失败结果的 data 不得泄漏到 /run 的响应体里。
    """
    from fr_cli.core.result import Result

    failed = Result.fail("步骤 2 (B) 失败: boom", data=("partial", [{"step": 1, "result": "ok"}]))
    with patch(AGENT_EXISTS, return_value=True), \
         patch("fr_cli.agent.server.run_agent", return_value=failed):
        status, data = _request(server, "POST", "/agents/demo/run", {"input": "hi"})

    assert status == 500
    assert data == {"result": None, "error": "步骤 2 (B) 失败: boom"}


def test_unauthorized(server):
    conn = http.client.HTTPConnection("127.0.0.1", server._server.server_address[1], timeout=5)
    conn.request("GET", "/agents", headers={})
    resp = conn.getresponse()
    data = json.loads(resp.read().decode("utf-8"))
    conn.close()
    assert resp.status == 401
    assert "Unauthorized" in data["error"]


def test_uses_threading_server(server):
    """P2-4：服务骨架必须是 BaseHTTPServer（继承标准库 ThreadingHTTPServer，此前是单线程 HTTPServer）"""
    assert isinstance(server._server, BaseHTTPServer)


def test_concurrent_requests_are_not_serialized(server):
    """并发请求不再排队：3 个各耗时 1s 的请求应并行完成"""
    def slow_run(*args, **kwargs):
        time.sleep(1.0)
        from fr_cli.core.result import Result
        return Result.ok("slow-ok")

    results = []

    def worker():
        results.append(
            _request(server, "POST", "/agents/demo/run", {"input": "hi", "timeout": 30})
        )

    with patch(AGENT_EXISTS, return_value=True), \
         patch("fr_cli.agent.server.run_agent", slow_run):
        start = time.time()
        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        elapsed = time.time() - start

    assert len(results) == 3
    assert all(status == 200 for status, _ in results)
    # 串行执行需要 3s 以上；线程化后应约 1s 完成
    assert elapsed < 2.0, f"请求被串行化了，耗时 {elapsed:.2f}s"


def test_run_timeout_returns_promptly(server):
    """真实超时路径：_run_with_timeout 必须及时返回 504。

    历史实现用 `with ThreadPoolExecutor(...)`，退出时 shutdown(wait=True)
    会阻塞到挂起任务结束 —— 超时名不副实，调用方依旧要等任务跑完。
    """
    def slow_run(*args, **kwargs):
        time.sleep(1.5)
        from fr_cli.core.result import Result
        return Result.ok("late")

    with patch(AGENT_EXISTS, return_value=True), \
         patch("fr_cli.agent.server.run_agent", slow_run):
        start = time.time()
        status, data = _request(
            server, "POST", "/agents/demo/run", {"input": "hi", "timeout": 0.5}
        )
        elapsed = time.time() - start

    assert status == 504
    assert "0.5" in data["error"]
    # 旧实现会阻塞到任务结束(~1.5s)，新实现应当立刻返回
    assert elapsed < 1.0, f"超时未及时返回，耗时 {elapsed:.2f}s"
