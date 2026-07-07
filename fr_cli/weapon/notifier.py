"""
Notifier 通知推送器 —— 凡人传讯
支持通过 Webhook 推送消息到多个协作平台（飞书/钉钉/企业微信/Slack/Discord）。

设计目标：
  - 零依赖（除 requests）
  - 单向推送（fr-cli 不接收消息，只推送通知）
  - 各平台 webhook 配置独立，按通道管理

使用场景：
  - 定时任务执行结果 → 推送到飞书
  - 数据采集完成 → 推送到钉钉群
  - 异常告警 → 推送到企微机器人
  - 配合 /cron 使用：
      /cron_add "0 9 * * *" "/notify lark '早安,今日数据已就绪'"
"""
import re
import time
from typing import Any, Dict, List, Optional

import requests

from fr_cli.conf.config import load_namespace, save_namespace
from fr_cli.core.result import Result


# 通知通道 → 颜色标记
CHANNEL_ICONS = {
    "lark": "📘",
    "feishu": "📘",
    "dingtalk": "📗",
    "wechat_work": "📙",
    "wecom": "📙",
    "slack": "💬",
    "discord": "🎮",
    "telegram": "✈️",
}


def _load_notifiers() -> Dict[str, Any]:
    """从主配置 notifier 命名空间读取所有通道配置"""
    return load_namespace("notifier", default={}, old_path=None) or {}


def _save_notifiers(notifiers: Dict[str, Any]):
    save_namespace("notifier", notifiers)


def add_channel(channel: str, webhook_url: str, secret: Optional[str] = None,
                extra: Optional[Dict[str, Any]] = None) -> Result:
    """添加/更新一个通知通道。

    Args:
        channel: 通道名（lark / dingtalk / wecom / slack / discord）
        webhook_url: webhook URL
        secret: 签名密钥（钉钉/企微可选）
        extra: 平台特定配置（如 @用户列表、消息类型等）
    """
    channel = channel.lower().strip()
    if not channel or not webhook_url:
        return Result.fail("通道名和 webhook URL 必填")

    notifiers = _load_notifiers()
    notifiers[channel] = {
        "webhook_url": webhook_url,
        "secret": secret or "",
        "extra": extra or {},
        "created_at": time.time(),
    }
    _save_notifiers(notifiers)
    return Result.ok(f"已配置通知通道: {channel}")


def remove_channel(channel: str) -> Result:
    """移除一个通知通道"""
    notifiers = _load_notifiers()
    if channel not in notifiers:
        return Result.fail(f"通道 {channel} 不存在")
    del notifiers[channel]
    _save_notifiers(notifiers)
    return Result.ok(f"已删除通知通道: {channel}")


def list_channels() -> List[Dict[str, Any]]:
    """列出所有已配置的通道（脱敏显示 webhook）"""
    notifiers = _load_notifiers()
    result = []
    for name, cfg in notifiers.items():
        url = cfg.get("webhook_url", "")
        masked = _mask_url(url)
        result.append({
            "channel": name,
            "webhook": masked,
            "has_secret": bool(cfg.get("secret")),
        })
    return result


def _mask_url(url: str) -> str:
    """脱敏 webhook URL（保留协议和域名，隐藏 token）"""
    if not url:
        return ""
    m = re.match(r"(https?://[^/]+)/(.*)", url)
    if not m:
        return url[:30] + "***"
    prefix, path = m.group(1), m.group(2)
    if len(path) <= 8:
        return f"{prefix}/{path[:3]}***"
    return f"{prefix}/{path[:3]}***{path[-3:]}"


# ============ 平台适配器 ============

def _send_lark(webhook_url: str, message: str, secret: Optional[str] = None,
               extra: Optional[Dict] = None) -> Result:
    """飞书机器人 webhook 发送"""
    extra = extra or {}
    payload = {
        "msg_type": extra.get("msg_type", "text"),
        "content": {"text": message} if extra.get("msg_type", "text") == "text" else {},
    }
    # 支持富文本（post）
    if payload["msg_type"] == "post":
        payload["content"] = {
            "post": {
                "zh_cn": {
                    "title": extra.get("title", ""),
                    "content": [[{"tag": "text", "text": message}]],
                }
            }
        }
    # @用户
    if extra.get("at_user_ids"):
        payload["content"]["at"] = {"user_id": extra["at_user_ids"]}
    if extra.get("at_all"):
        payload["content"]["at"] = {"is_at_all": True}

    # 签名校验（如果提供 secret）
    if secret:
        import hmac
        import hashlib
        import base64
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(string_to_sign.encode("utf-8"), b"", digestmod=hashlib.sha256).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")
        payload["timestamp"] = timestamp
        payload["sign"] = sign

    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        if r.status_code != 200:
            return Result.fail(f"飞书返回 {r.status_code}: {r.text[:200]}")
        data = r.json() if r.text else {}
        # 飞书的 code 字段：0 表示成功
        code = data.get("code", 0)
        if code != 0:
            return Result.fail(f"飞书错误(code={code}): {data.get('msg', data)}")
        return Result.ok({"channel": "lark", "response": data})
    except Exception as e:
        return Result.fail(f"飞书发送失败: {e}")


def _send_dingtalk(webhook_url: str, message: str, secret: Optional[str] = None,
                   extra: Optional[Dict] = None) -> Result:
    """钉钉机器人 webhook 发送"""
    extra = extra or {}
    payload = {
        "msgtype": extra.get("msgtype", "text"),
        "text": {"content": message},
    }
    if payload["msgtype"] == "markdown":
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": extra.get("title", "通知"),
                "text": message,
            }
        }
    if extra.get("at_mobiles"):
        payload["at"] = {"atMobiles": extra["at_mobiles"]}
    if extra.get("at_all"):
        payload["at"] = {"isAtAll": True}

    # 加签
    if secret:
        import hmac
        import hashlib
        import base64
        import urllib.parse
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"),
                             digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        webhook_url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"

    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        if r.status_code != 200:
            return Result.fail(f"钉钉返回 {r.status_code}: {r.text[:200]}")
        data = r.json() if r.text else {}
        if data.get("errcode", 0) != 0:
            return Result.fail(f"钉钉错误: {data.get('errmsg', data)}")
        return Result.ok({"channel": "dingtalk", "response": data})
    except Exception as e:
        return Result.fail(f"钉钉发送失败: {e}")


def _send_wecom(webhook_url: str, message: str, secret: Optional[str] = None,
                extra: Optional[Dict] = None) -> Result:
    """企业微信机器人 webhook 发送"""
    extra = extra or {}
    payload = {
        "msgtype": extra.get("msgtype", "text"),
        "text": {"content": message},
    }
    if payload["msgtype"] == "markdown":
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": message},
        }
    if extra.get("mentioned_list"):
        payload["markdown" if payload["msgtype"] == "markdown" else "text"]["mentioned_list"] = extra["mentioned_list"]
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        if r.status_code != 200:
            return Result.fail(f"企微返回 {r.status_code}: {r.text[:200]}")
        data = r.json() if r.text else {}
        if data.get("errcode", 0) != 0:
            return Result.fail(f"企微错误: {data.get('errmsg', data)}")
        return Result.ok({"channel": "wecom", "response": data})
    except Exception as e:
        return Result.fail(f"企微发送失败: {e}")


def _send_slack(webhook_url: str, message: str, secret: Optional[str] = None,
                extra: Optional[Dict] = None) -> Result:
    """Slack incoming webhook 发送"""
    payload = {"text": message}
    if extra.get("blocks"):
        payload["blocks"] = extra["blocks"]
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        if r.status_code != 200:
            return Result.fail(f"Slack 返回 {r.status_code}: {r.text[:200]}")
        return Result.ok({"channel": "slack", "response": r.text})
    except Exception as e:
        return Result.fail(f"Slack 发送失败: {e}")


def _send_discord(webhook_url: str, message: str, secret: Optional[str] = None,
                  extra: Optional[Dict] = None) -> Result:
    """Discord webhook 发送"""
    payload = {"content": message}
    if extra.get("username"):
        payload["username"] = extra["username"]
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        if r.status_code in (200, 204):
            return Result.ok({"channel": "discord", "response": r.text})
        return Result.fail(f"Discord 返回 {r.status_code}: {r.text[:200]}")
    except Exception as e:
        return Result.fail(f"Discord 发送失败: {e}")


def _send_telegram(webhook_url: str, message: str, secret: Optional[str] = None,
                   extra: Optional[Dict] = None) -> Result:
    """Telegram bot webhook 发送"""
    # 格式: https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=XXX
    # 或者直接传完整 URL
    payload = {"text": message, "parse_mode": "Markdown"} if extra.get("markdown") else {"text": message}
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        if r.status_code != 200:
            return Result.fail(f"Telegram 返回 {r.status_code}: {r.text[:200]}")
        data = r.json() if r.text else {}
        if not data.get("ok"):
            return Result.fail(f"Telegram 错误: {data.get('description', data)}")
        return Result.ok({"channel": "telegram", "response": data})
    except Exception as e:
        return Result.fail(f"Telegram 发送失败: {e}")


_SENDERS = {
    "lark": _send_lark,
    "feishu": _send_lark,  # alias
    "dingtalk": _send_dingtalk,
    "wechat_work": _send_wecom,
    "wecom": _send_wecom,
    "slack": _send_slack,
    "discord": _send_discord,
    "telegram": _send_telegram,
}


def notify(channel: str, message: str, extra: Optional[Dict] = None) -> Result:
    """向指定通道发送一条通知。

    Args:
        channel: 通道名
        message: 消息内容
        extra: 临时覆盖配置（如 @用户、消息类型等）

    Returns:
        Result: ok(error=None) 表示成功
    """
    channel = channel.lower().strip()
    notifiers = _load_notifiers()
    cfg = notifiers.get(channel)
    if not cfg:
        return Result.fail(f"通知通道 {channel} 未配置。用 /notify add <通道> <webhook_url> 添加")

    sender = _SENDERS.get(channel)
    if not sender:
        return Result.fail(f"通道 {channel} 暂不支持")

    # 合并 extra（参数 > 配置）
    merged_extra = dict(cfg.get("extra") or {})
    if extra:
        merged_extra.update(extra)

    return sender(
        cfg["webhook_url"],
        message,
        secret=cfg.get("secret"),
        extra=merged_extra,
    )


def notify_all(message: str, extra: Optional[Dict] = None) -> Dict[str, Result]:
    """向所有已配置的通道发送通知（用于重要告警）"""
    notifiers = _load_notifiers()
    results = {}
    for channel in notifiers:
        results[channel] = notify(channel, message, extra=extra)
    return results
