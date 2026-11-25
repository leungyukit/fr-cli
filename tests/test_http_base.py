"""
HTTP 公共基类测试 —— 覆盖统一鉴权、三种响应包裹策略、并发处理与异常处理。

被测对象：fr_cli.core.http_base
- AuthPolicy / BaseHTTPHandler / BaseHTTPServer / wrap_payload
"""
import http.client
import json
import threading
import time
from urllib.parse import urlparse

import pytest

from fr_cli.core.http_base import (
    WRAP_FLAT,
    WRAP_OK_DATA,
    WRAP_RESULT_ERROR,
    AuthPolicy,
    BaseHTTPHandler,
    BaseHTTPServer,
    wrap_payload,
)

TOKEN = "unit-test-token"


# ---------------------------------------------------------------------------
# 测试用 handler / server
# ---------------------------------------------------------------------------
class _TestHandler(BaseHTTPHandler):
    """测试用处理器：覆盖三种包裹策略 + 鉴权 + 异常路径"""

    wrap_mode = WRAP_FLAT

    def do_GET(self):
        if not self._check_auth():
            return
        path = urlparse(self.path).path
        if path == "/echo":
            self._send_wrapped(200, data={"path": path})
        elif path == "/boom":
            raise RuntimeError("boom")
        elif path == "/slow":
            time.sleep(getattr(self.server, "delay", 0.5))
            self._send_wrapped(200, data={"slept": True})
        elif path == "/raw":
            self._send_json(200, {"raw": True})
        else:
            self._send_error(404, "Not found")

    def do_POST(self):
        if not self._check_auth():
            return
        path = urlparse(self.path).path
        if path == "/echo":
            self._send_wrapped(200, data=self._read_json_body())
        else:
            self._send_error(404, "Not found")


class _ResultHandler(_TestHandler):
    wrap_mode = WRAP_RESULT_ERROR


class _OkDataHandler(_TestHandler):
    wrap_mode = WRAP_OK_DATA


def _make_server(handler_cls=_TestHandler, policy=None, delay=0.0):
    """启动一个测试服务器（端口 0 = 系统分配）"""
    server = BaseHTTPServer(
        ("127.0.0.1", 0),
        handler_cls,
        auth_policy=policy or AuthPolicy(token=TOKEN),
    )
    server.delay = delay
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _request(server, method, path, body=None, token=None, timeout=5):
    """发起 HTTP 请求，返回 (status, 解析后的 JSON)"""
    port = server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=headers)
    else:
        conn.request(method, path, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    try:
        return resp.status, json.loads(raw)
    except json.JSONDecodeError:
        return resp.status, raw


@pytest.fixture
def server():
    srv = _make_server()
    yield srv
    srv.shutdown()
    srv.server_close()


# ---------------------------------------------------------------------------
# 包裹策略
# ---------------------------------------------------------------------------
class TestWrapPayload:
    def test_result_error_success(self):
        assert wrap_payload(WRAP_RESULT_ERROR, data={"a": 1}) == {
            "result": {"a": 1},
            "error": None,
        }

    def test_result_error_failure(self):
        assert wrap_payload(WRAP_RESULT_ERROR, error="boom") == {
            "result": None,
            "error": "boom",
        }

    def test_ok_data_success(self):
        assert wrap_payload(WRAP_OK_DATA, data={"a": 1}) == {
            "ok": True,
            "data": {"a": 1},
        }

    def test_ok_data_failure(self):
        assert wrap_payload(WRAP_OK_DATA, error="boom") == {
            "ok": False,
            "error": "boom",
        }

    def test_flat_passthrough(self):
        assert wrap_payload(WRAP_FLAT, data={"a": 1}) == {"a": 1}
        assert wrap_payload(WRAP_FLAT, error="boom") == {"error": "boom"}

    def test_flat_non_dict_payload(self):
        assert wrap_payload(WRAP_FLAT, data=[1, 2]) == {"data": [1, 2]}


class TestWrapModesOverHTTP:
    def test_result_error_shape(self):
        srv = _make_server(_ResultHandler)
        try:
            status, data = _request(srv, "GET", "/echo", token=TOKEN)
            assert status == 200
            assert data == {"result": {"path": "/echo"}, "error": None}
        finally:
            srv.shutdown()
            srv.server_close()

    def test_ok_data_shape(self):
        srv = _make_server(_OkDataHandler)
        try:
            status, data = _request(srv, "GET", "/echo", token=TOKEN)
            assert status == 200
            assert data == {"ok": True, "data": {"path": "/echo"}}
        finally:
            srv.shutdown()
            srv.server_close()

    def test_flat_shape(self):
        srv = _make_server(_TestHandler)
        try:
            status, data = _request(srv, "GET", "/echo", token=TOKEN)
            assert status == 200
            assert data == {"path": "/echo"}
        finally:
            srv.shutdown()
            srv.server_close()


# ---------------------------------------------------------------------------
# 鉴权
# ---------------------------------------------------------------------------
class TestAuth:
    def test_missing_token_rejected(self, server):
        status, data = _request(server, "GET", "/echo")
        assert status == 401
        assert data == {"error": "Missing Authorization: Bearer <token>"}

    def test_invalid_token_rejected(self, server):
        status, data = _request(server, "GET", "/echo", token="wrong")
        assert status == 403
        assert data == {"error": "Invalid token"}

    def test_valid_token_allowed(self, server):
        status, data = _request(server, "GET", "/echo", token=TOKEN)
        assert status == 200
        assert data == {"path": "/echo"}

    def test_post_requires_token(self, server):
        status, data = _request(server, "POST", "/echo", body={"a": 1})
        assert status == 401
        assert "Missing Authorization" in data["error"]

    def test_post_with_token(self, server):
        status, data = _request(server, "POST", "/echo", body={"a": 1}, token=TOKEN)
        assert status == 200
        assert data == {"a": 1}

    def test_public_path_is_open(self):
        policy = AuthPolicy(token=TOKEN, public_paths={"/health"})
        srv = _make_server(policy=policy)
        try:
            # 公开白名单内的只读端点免鉴权
            assert policy.requires_auth("GET", "/health") is False
            status, _ = _request(srv, "GET", "/echo", token=TOKEN)
            assert status == 200
        finally:
            srv.shutdown()
            srv.server_close()

    def test_public_path_only_applies_to_read_only_methods(self):
        policy = AuthPolicy(token=TOKEN, public_paths={"/health"})
        # 写方法即使路径在白名单里也必须鉴权
        assert policy.requires_auth("GET", "/health") is False
        assert policy.requires_auth("POST", "/health") is True

    def test_protected_methods_subset(self):
        policy = AuthPolicy(token=TOKEN, protected_methods={"POST", "PUT"})
        assert policy.requires_auth("POST", "/x") is True
        assert policy.requires_auth("PUT", "/x") is True
        assert policy.requires_auth("GET", "/x") is False

    def test_query_token_allowed(self):
        policy = AuthPolicy(token=TOKEN, allow_query_token=True)
        srv = _make_server(policy=policy)
        try:
            conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
            conn.request("GET", f"/echo?token={TOKEN}")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            conn.close()
            assert resp.status == 200
            assert data == {"path": "/echo"}
        finally:
            srv.shutdown()
            srv.server_close()

    def test_query_token_disallowed_by_default(self, server):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", f"/echo?token={TOKEN}")
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        assert resp.status == 401
        assert "Missing Authorization" in data["error"]

    def test_no_token_policy_allows(self):
        policy = AuthPolicy(token="")
        assert policy.requires_auth("GET", "/x") is False

    def test_deny_without_token(self):
        policy = AuthPolicy(token="", deny_without_token=True)
        assert policy.requires_auth("GET", "/x") is True

    def test_verify_helper(self):
        policy = AuthPolicy(token=TOKEN)
        assert policy.verify({"Authorization": f"Bearer {TOKEN}"}, "/x", "GET") is True
        assert policy.verify({"Authorization": "Bearer nope"}, "/x", "GET") is False
        assert policy.verify({}, "/x", "GET") is False

    def test_non_ascii_token_is_rejected(self, server):
        """非 ASCII token（latin-1 可编码）不得触发 compare_digest 的 TypeError"""
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", "/echo", headers={"Authorization": "Bearer café"})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        assert resp.status == 403


# ---------------------------------------------------------------------------
# 异常处理 / 并发
# ---------------------------------------------------------------------------
class TestErrorHandling:
    def test_unhandled_exception_returns_json_error(self, server):
        status, data = _request(server, "GET", "/boom", token=TOKEN)
        assert status == 500
        assert "boom" in data["error"]

    def test_not_found(self, server):
        status, data = _request(server, "GET", "/nope", token=TOKEN)
        assert status == 404
        assert data == {"error": "Not found"}


class TestConcurrency:
    def test_requests_are_served_concurrently(self):
        """4 个各睡 0.5s 的请求：串行需要 ~2s，并发应该远小于此"""
        srv = _make_server(delay=0.5)
        results = []

        def worker():
            results.append(_request(srv, "GET", "/slow", token=TOKEN))

        try:
            start = time.time()
            threads = [threading.Thread(target=worker) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
            elapsed = time.time() - start
            assert len(results) == 4
            assert all(status == 200 for status, _ in results)
            # 串行执行需要 2s 以上；并发（线程化）应在 ~0.5s 完成
            assert elapsed < 1.5, f"并发未生效，耗时 {elapsed:.2f}s"
        finally:
            srv.shutdown()
            srv.server_close()

    def test_server_is_threading_based(self, server):
        assert isinstance(server, BaseHTTPServer)
        assert server.daemon_threads is True
