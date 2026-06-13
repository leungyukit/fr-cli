"""
Agent HTTP 服务测试 —— 验证 /run 与 /workflow 接口的认证、超时与异常处理。
"""
import http.client
import json
from unittest.mock import MagicMock, patch

import pytest

from fr_cli.agent.server import _AgentHTTPHandler, AgentHTTPServer

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


def test_unauthorized(server):
    conn = http.client.HTTPConnection("127.0.0.1", server._server.server_address[1], timeout=5)
    conn.request("GET", "/agents", headers={})
    resp = conn.getresponse()
    data = json.loads(resp.read().decode("utf-8"))
    conn.close()
    assert resp.status == 401
    assert "Unauthorized" in data["error"]
