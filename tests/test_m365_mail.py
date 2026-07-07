"""
Microsoft 365 邮件模块测试
重点覆盖：
  - 配置加载/保存与文件权限
  - Graph API 调用（收件、读邮件、发邮件）
  - 安全校验（邮件头注入、无效地址）
  - 未配置场景的错误提示
  - 状态/登出工具函数
"""
import json
import stat
from pathlib import Path
from unittest import mock

import pytest

from fr_cli.weapon import m365 as m365_mod
from fr_cli.weapon.m365 import (
    M365MailClient,
    m365_config_wizard,
    m365_logout,
    m365_send,
    m365_status,
    _load_m365_cfg,
    _save_m365_cfg,
)


@pytest.fixture(autouse=True)
def _isolate_m365_cfg(tmp_path, monkeypatch):
    """每个测试使用独立的 HOME（隔离主配置）+ 老 m365.json 路径"""
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))

    fake_fr_cli = fake_home / ".fr_cli"
    fake_fr_cli.mkdir(parents=True, exist_ok=True)
    old_cfg = fake_fr_cli / "m365.json"

    monkeypatch.setattr(m365_mod, "M365_CONFIG_FILE", old_cfg)
    monkeypatch.setattr(m365_mod, "M365_FILE", old_cfg)
    # 通过 _root_holder 改路径
    import fr_cli.conf.paths as _paths_mod
    monkeypatch.setattr(_paths_mod._root_holder, "value", fake_fr_cli)
    yield
    m365_logout()


def test_cfg_file_permissions(tmp_path):
    """主配置 config.json 应保持 0o600 权限"""
    _save_m365_cfg({"client_id": "x"})
    config_file = Path.home() / ".fr_cli" / "config.json"
    assert config_file.exists()
    mode = stat.S_IMODE(config_file.stat().st_mode)
    assert mode == 0o600


# ------------------------------------------------------------------
# 配置持久化
# ------------------------------------------------------------------

def test_save_and_load_cfg(tmp_path):
    cfg = {
        "tenant_id": "common",
        "client_id": "test-client-id",
        "flow": "device_code",
    }
    _save_m365_cfg(cfg)
    loaded = _load_m365_cfg()
    assert loaded == cfg


# ------------------------------------------------------------------
# 未配置场景
# ------------------------------------------------------------------

def test_inbox_without_config():
    client = M365MailClient({})
    result = client.inbox()
    assert result.is_fail()
    assert "client_id" in result.error


def test_send_without_config():
    result = m365_send("a@b.com", "sub", "body", {})
    assert result.is_fail()
    assert "client_id" in result.error


# ------------------------------------------------------------------
# Graph API 调用（mock）
# ------------------------------------------------------------------

def _fake_token(*args, **kwargs):
    from fr_cli.core.result import Result
    return Result.ok("fake-access-token")


def test_inbox_success():
    fake_messages = {
        "value": [
            {
                "id": "msg-1",
                "subject": "Hello M365",
                "from": {"emailAddress": {"address": "sender@example.com"}},
                "receivedDateTime": "2026-06-12T10:00:00Z",
                "hasAttachments": False,
            }
        ]
    }
    client = M365MailClient({"client_id": "x"})
    with mock.patch.object(m365_mod, "_get_access_token", _fake_token), \
         mock.patch("requests.request") as mock_req:
        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(fake_messages)
        mock_resp.json.return_value = fake_messages
        mock_req.return_value = mock_resp

        result = client.inbox()
        assert result.is_ok()
        mails = result.unwrap()
        assert len(mails) == 1
        assert mails[0]["id"] == "msg-1"
        assert mails[0]["sub"] == "Hello M365"
        assert mails[0]["from"] == "sender@example.com"


def test_read_success():
    fake_msg = {
        "subject": "Test",
        "from": {"emailAddress": {"address": "from@example.com"}},
        "receivedDateTime": "2026-06-12T10:00:00Z",
        "body": {"contentType": "text", "content": "plain body"},
        "toRecipients": [{"emailAddress": {"address": "to@example.com"}}],
        "ccRecipients": [],
    }
    client = M365MailClient({"client_id": "x"})
    with mock.patch.object(m365_mod, "_get_access_token", _fake_token), \
         mock.patch("requests.request") as mock_req:
        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(fake_msg)
        mock_resp.json.return_value = fake_msg
        mock_req.return_value = mock_resp

        result = client.read("msg-1")
        assert result.is_ok()
        m = result.unwrap()
        assert m["sub"] == "Test"
        assert m["body"] == "plain body"


def test_send_success():
    client = M365MailClient({"client_id": "x"})
    with mock.patch.object(m365_mod, "_get_access_token", _fake_token), \
         mock.patch("requests.request") as mock_req:
        mock_resp = mock.Mock()
        mock_resp.status_code = 202
        mock_resp.text = ""
        mock_req.return_value = mock_resp

        result = client.send("to@example.com", "Subject", "Body")
        assert result.is_ok()

        # 验证调用参数
        call_args = mock_req.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "https://graph.microsoft.com/v1.0/me/sendMail"
        payload = call_args[1]["json"]
        assert payload["message"]["subject"] == "Subject"
        assert payload["message"]["toRecipients"][0]["emailAddress"]["address"] == "to@example.com"


def test_send_graph_api_error():
    client = M365MailClient({"client_id": "x"})
    with mock.patch.object(m365_mod, "_get_access_token", _fake_token), \
         mock.patch("requests.request") as mock_req:
        mock_resp = mock.Mock()
        mock_resp.status_code = 401
        mock_resp.text = json.dumps({"error": {"message": "Unauthorized"}})
        mock_resp.json.return_value = {"error": {"message": "Unauthorized"}}
        mock_req.return_value = mock_resp

        result = client.send("to@example.com", "Subject", "Body")
        assert result.is_fail()
        assert "Graph API 错误" in result.error


# ------------------------------------------------------------------
# 安全校验
# ------------------------------------------------------------------

def test_send_rejects_header_injection():
    client = M365MailClient({"client_id": "x"})
    result = client.send("to@example.com\r\nBCC: bad@evil.com", "Subject", "Body")
    assert result.is_fail()
    assert "非法字符" in result.error


def test_send_rejects_invalid_address():
    client = M365MailClient({"client_id": "x"})
    result = client.send("not-an-email", "Subject", "Body")
    assert result.is_fail()
    assert "无效" in result.error


# ------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------

def test_status_and_logout():
    _save_m365_cfg({
        "tenant_id": "common",
        "client_id": "my-client-id",
        "flow": "device_code",
        "token_cache": "cached",
    })
    status = m365_status()
    assert status["configured"] is True
    assert status["has_token"] is True
    assert status["flow"] == "device_code"
    assert status["client_id"].startswith("my-cli")

    assert m365_logout() is True
    assert m365_mod.M365_CONFIG_FILE.exists() is False


def test_status_empty():
    status = m365_status()
    assert status["configured"] is False
    assert status["has_token"] is False


# ------------------------------------------------------------------
# 配置向导（mock 输入）
# ------------------------------------------------------------------

def test_config_wizard_cancelled(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "n")
    ok, cfg = m365_config_wizard("zh")
    assert not ok
