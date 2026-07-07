"""
Notifier 通知推送器测试
覆盖：通道配置、webhook 发送、跨平台适配
"""
from unittest.mock import patch, MagicMock

import pytest

from fr_cli.weapon.notifier import (
    add_channel, remove_channel, list_channels, notify, notify_all,
    _load_notifiers, _mask_url,
)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """隔离测试环境"""
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))
    import fr_cli.conf.paths as _paths_mod
    monkeypatch.setattr(_paths_mod._root_holder, "value", fake_home / ".fr_cli")
    yield


def test_add_and_list_channel():
    """添加通道 + 列出"""
    r = add_channel("lark", "https://open.feishu.cn/hook/abc123def456")
    assert r.is_ok()

    channels = list_channels()
    assert len(channels) == 1
    assert channels[0]["channel"] == "lark"
    # webhook 应该被脱敏
    assert "***" in channels[0]["webhook"]


def test_add_channel_with_secret():
    """带 secret 的通道"""
    r = add_channel("dingtalk", "https://oapi.dingtalk.com/robot/send?access_token=xxx",
                    secret="SEC123")
    assert r.is_ok()

    channels = list_channels()
    assert channels[0]["has_secret"] is True


def test_remove_channel():
    """删除通道"""
    add_channel("lark", "https://open.feishu.cn/hook/test")
    r = remove_channel("lark")
    assert r.is_ok()
    assert len(list_channels()) == 0


def test_remove_nonexistent_channel():
    """删除不存在的通道"""
    r = remove_channel("never_existed")
    assert r.is_fail()


def test_notify_without_config():
    """未配置的通道返回 fail"""
    r = notify("lark", "hello")
    assert r.is_fail()
    assert "未配置" in r.error


def test_notify_lark_success():
    """飞书通知发送成功"""
    add_channel("lark", "https://open.feishu.cn/hook/test")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"code": 0, "msg": "ok"}'
    mock_resp.json.return_value = {"code": 0, "msg": "ok"}

    with patch("fr_cli.weapon.notifier.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        r = notify("lark", "测试消息")

    assert r.is_ok(), r.error
    mock_post.assert_called_once()


def test_notify_lark_with_signature():
    """带签名的飞书通知（secret 模式）"""
    add_channel("feishu", "https://open.feishu.cn/hook/sig", secret="SEC123")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"code": 0}'
    mock_resp.json.return_value = {"code": 0}

    with patch("fr_cli.weapon.notifier.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        r = notify("feishu", "测试签名消息")

    assert r.is_ok()
    # 验证请求体包含 timestamp 和 sign
    call_kwargs = mock_post.call_args.kwargs
    payload = call_kwargs["json"]
    assert "timestamp" in payload
    assert "sign" in payload


def test_notify_dingtalk():
    """钉钉通知"""
    add_channel("dingtalk", "https://oapi.dingtalk.com/robot/send?access_token=xxx")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"errcode": 0, "errmsg": "ok"}'
    mock_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}

    with patch("fr_cli.weapon.notifier.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        r = notify("dingtalk", "钉钉测试")

    assert r.is_ok()


def test_notify_wecom():
    """企微通知"""
    add_channel("wecom", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"errcode": 0, "errmsg": "ok"}'
    mock_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}

    with patch("fr_cli.weapon.notifier.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        r = notify("wecom", "企微测试")

    assert r.is_ok()


def test_notify_slack():
    """Slack 通知"""
    add_channel("slack", "https://hooks.slack.com/services/T00/B00/XXX")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "ok"

    with patch("fr_cli.weapon.notifier.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        r = notify("slack", "Slack test")

    assert r.is_ok()


def test_notify_discord():
    """Discord 通知"""
    add_channel("discord", "https://discord.com/api/webhooks/XXX/YYY")

    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_resp.text = ""

    with patch("fr_cli.weapon.notifier.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        r = notify("discord", "Discord test")

    assert r.is_ok()


def test_notify_telegram():
    """Telegram 通知"""
    add_channel("telegram", "https://api.telegram.org/botXXX/sendMessage")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"ok": true, "result": {}}'
    mock_resp.json.return_value = {"ok": True, "result": {}}

    with patch("fr_cli.weapon.notifier.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        r = notify("telegram", "Telegram test")

    assert r.is_ok()


def test_notify_all():
    """群发所有通道"""
    add_channel("lark", "https://open.feishu.cn/hook/a")
    add_channel("dingtalk", "https://oapi.dingtalk.com/robot/send?x=y")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"errcode": 0, "code": 0}'
    mock_resp.json.return_value = {"errcode": 0, "code": 0}

    with patch("fr_cli.weapon.notifier.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        results = notify_all("群发测试")

    assert "lark" in results
    assert "dingtalk" in results
    assert results["lark"].is_ok()
    assert results["dingtalk"].is_ok()


def test_notify_network_error():
    """网络错误处理"""
    add_channel("lark", "https://open.feishu.cn/hook/test")
    with patch("fr_cli.weapon.notifier.requests.post") as mock_post:
        mock_post.side_effect = Exception("Connection refused")
        r = notify("lark", "test")

    assert r.is_fail()
    assert "失败" in r.error


def test_notify_api_error_response():
    """API 返回错误码"""
    add_channel("lark", "https://open.feishu.cn/hook/test")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"code": 99991, "msg": "频率限制"}'
    mock_resp.json.return_value = {"code": 99991, "msg": "频率限制"}

    with patch("fr_cli.weapon.notifier.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        r = notify("lark", "test")

    assert r.is_fail()
    assert "错误" in r.error


def test_mask_url_long_token():
    """长 token URL 脱敏"""
    url = "https://open.feishu.cn/open-apis/bot/v2/hook/abcdef0123456789"
    masked = _mask_url(url)
    assert "***" in masked
    # 完整 token 不应该出现
    assert "abcdef0123456789" not in masked
    # 但应该保留协议头和域名
    assert "https://open.feishu.cn" in masked


def test_mask_url_short_token():
    """短 token URL 脱敏"""
    url = "https://x.com/abc"
    masked = _mask_url(url)
    assert "***" in masked


def test_mask_url_empty():
    """空 URL 脱敏"""
    assert _mask_url("") == ""


def test_add_channel_validates_inputs():
    """添加通道时校验输入"""
    r = add_channel("", "https://x.com")
    assert r.is_fail()
    r = add_channel("lark", "")
    assert r.is_fail()


def test_channel_persistence():
    """通道配置应该持久化到主配置"""
    add_channel("lark", "https://open.feishu.cn/hook/persist")
    notifiers = _load_notifiers()
    assert "lark" in notifiers
    assert notifiers["lark"]["webhook_url"].startswith("https://")


def test_remove_channel_keeps_others():
    """删除一个通道不影响其他"""
    add_channel("lark", "https://x.com/lark")
    add_channel("slack", "https://x.com/slack")
    remove_channel("lark")
    assert len(list_channels()) == 1
    assert list_channels()[0]["channel"] == "slack"
