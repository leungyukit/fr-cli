"""
Microsoft 365 邮件客户端 —— 腾云驾雾之现代认证

支持 OAuth2 设备代码流 / 授权码流，兼容 Microsoft 365 的 MFA 多因素认证。
邮件收发通过 Microsoft Graph API。

配置项收敛在 ~/.fr_cli/config.json 的 m365 命名空间：
  tenant_id:     Azure AD 租户 ID（common 表示个人/多租户）
  client_id:     Azure AD 应用注册 ID
  flow:          "device_code"（默认）或 "authorization_code"
  redirect_uri:  授权码流回调地址（默认 http://localhost:17891）
  token_cache:   MSAL 序列化后的 token 缓存（由程序自动维护）

旧文件 ~/.fr_cli/m365.json 会在首次加载时一次性迁移。

模块拆分(原单文件 456 行):
- m365.py:       本文件——配置读写 + Graph 邮件客户端 + 向导/状态/登出
- m365_auth.py:  MSAL OAuth2 认证层(设备代码流 / 授权码流,拿 access token)
"""
import time  # noqa: F401 (保留:历史导入,部分调用方 from fr_cli.weapon.m365 import * 场景)
import webbrowser  # noqa: F401 (保留:同上)
from typing import Any, Dict, List, Optional, Tuple

import requests

from fr_cli.conf.paths import M365_FILE
from fr_cli.conf.config import load_namespace, save_namespace
from fr_cli.ui.ui import CYAN, GREEN, RED, RESET, YELLOW, DIM
from fr_cli.core.result import Result

from fr_cli.weapon.m365_auth import (  # noqa: F401 (re-export,旧导入路径兼容)
    AUTHORITY_BASE,
    DEFAULT_SCOPES,
    _ensure_msal,
    _get_access_token,
    _get_app,
    _login_authorization_code,
    _login_device_code,
    _save_token_cache,
)


# 保留用于一次性迁移（已弃用，新数据写入 ~/.fr_cli/config.json）
M365_CONFIG_FILE = M365_FILE
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


def _load_m365_cfg() -> Dict[str, Any]:
    """加载 M365 配置（从主配置 m365 命名空间，老文件一次性迁移）"""
    return load_namespace("m365", default={}, old_path=M365_CONFIG_FILE)


def _save_m365_cfg(cfg: Dict[str, Any]):
    """保存 M365 配置到主配置 m365 命名空间"""
    save_namespace("m365", cfg)


class M365MailClient:
    """Microsoft 365 邮件客户端"""

    def __init__(self, cfg: Optional[Dict[str, Any]] = None):
        self.cfg = cfg or _load_m365_cfg()

    def _request(self, method: str, endpoint: str, json_data: Optional[Dict] = None,
                 lang: str = "zh") -> Result:
        """统一 Graph API 请求，返回 Result。"""
        token_result = _get_access_token(self.cfg, lang)
        if token_result.is_fail():
            return Result.fail(token_result.error)
        access_token = token_result.unwrap()

        url = f"{GRAPH_BASE_URL}{endpoint}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.request(method, url, headers=headers, json=json_data, timeout=30)
            if resp.status_code >= 400:
                try:
                    err_info = resp.json()
                    err_msg = err_info.get("error", {}).get("message", resp.text)
                except Exception:
                    err_msg = resp.text
                return Result.fail(f"Graph API 错误 ({resp.status_code}): {err_msg}")
            if resp.status_code == 204:
                return Result.ok(None)
            return Result.ok(resp.json() if resp.text else None)
        except requests.RequestException as e:
            return Result.fail(f"网络请求失败: {e}")

    def inbox(self, lang: str = "zh", limit: int = 10) -> Result:
        """获取收件箱列表，返回 Result[list]。"""
        endpoint = f"/me/messages?$top={limit}&$select=id,subject,from,receivedDateTime,hasAttachments"
        request_result = self._request("GET", endpoint, lang=lang)
        if request_result.is_fail():
            return request_result
        data = request_result.unwrap()

        messages = data.get("value", []) if isinstance(data, dict) else []
        result = []
        for msg in messages:
            from_addr = msg.get("from", {}).get("emailAddress", {}).get("address", "Unknown")
            result.append({
                "id": msg.get("id", ""),
                "sub": msg.get("subject", "")[:50],
                "from": from_addr[:30],
                "date": msg.get("receivedDateTime", ""),
                "has_attachments": msg.get("hasAttachments", False),
            })
        return Result.ok(result)

    def read(self, mail_id: str, lang: str = "zh") -> Result:
        """读取指定邮件，返回 Result[dict]。"""
        endpoint = f"/me/messages/{mail_id}?$select=subject,from,receivedDateTime,body,toRecipients,ccRecipients"
        request_result = self._request("GET", endpoint, lang=lang)
        if request_result.is_fail():
            return request_result
        msg = request_result.unwrap()

        from fr_cli.weapon.mail import _html_to_text
        body_html = msg.get("body", {}).get("content", "")
        content_type = msg.get("body", {}).get("contentType", "text")
        body_text = body_html if content_type == "text" else _html_to_text(body_html)

        return Result.ok({
            "sub": msg.get("subject", ""),
            "from": msg.get("from", {}).get("emailAddress", {}).get("address", "Unknown"),
            "to": [r.get("emailAddress", {}).get("address", "") for r in msg.get("toRecipients", [])],
            "cc": [r.get("emailAddress", {}).get("address", "") for r in msg.get("ccRecipients", [])],
            "date": msg.get("receivedDateTime", ""),
            "body": body_text,
        })

    def send(self, to: str, subject: str, body: str, lang: str = "zh",
             cc: Optional[List[str]] = None) -> Result:
        """发送邮件，返回 Result。"""
        # 安全校验：防止邮件头注入
        if '\n' in to or '\r' in to or '\n' in subject or '\r' in subject:
            return Result.fail("[x] 邮件地址或主题包含非法字符")

        import email.utils
        parsed = email.utils.parseaddr(to)
        if not parsed[1] or '@' not in parsed[1]:
            return Result.fail("[x] 收件人地址格式无效")

        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "Text",
                    "content": body,
                },
                "toRecipients": [
                    {"emailAddress": {"address": to}}
                ],
            },
            "saveToSentItems": True,
        }
        if cc:
            payload["message"]["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in cc if addr
            ]

        result = self._request("POST", "/me/sendMail", json_data=payload, lang=lang)
        return result


def m365_inbox(cfg, lang="zh", limit=10):
    """便捷函数：收件箱，返回 Result[list]。"""
    client = M365MailClient(cfg)
    return client.inbox(lang=lang, limit=limit)


def m365_read(mail_id: str, cfg, lang="zh"):
    """便捷函数：读邮件，返回 Result[dict]。"""
    client = M365MailClient(cfg)
    return client.read(mail_id, lang=lang)


def m365_send(to: str, subject: str, body: str, cfg, lang="zh", cc=None):
    """便捷函数：发邮件，返回 Result。"""
    client = M365MailClient(cfg)
    return client.send(to, subject, body, lang=lang, cc=cc)


# ------------------------------------------------------------------
# 配置向导与工具函数
# ------------------------------------------------------------------

def m365_config_wizard(lang: str = "zh") -> Tuple[bool, Dict[str, Any]]:
    """
    Microsoft 365 邮件配置交互向导
    引导用户注册 Azure AD 应用、输入 tenant_id/client_id、完成 OAuth2 登录。
    """
    uf = lang == "zh"

    def _prompt(text, default=""):
        if default:
            val = input(f"{CYAN}{text} [{default}]: {RESET}").strip()
            return val if val else default
        return input(f"{CYAN}{text}: {RESET}").strip()

    def _confirm(text):
        r = input(f"{YELLOW}{text} (Y/n): {RESET}").strip().lower()
        return r in ("", "y", "yes", "是")

    print(f"\n{CYAN}Microsoft 365 邮箱配置向导{RESET}")
    print(f"{DIM}{'你需要先注册一个 Azure AD 应用。以下是简要步骤：' if uf else 'You need to register an Azure AD app first. Quick steps:'}{RESET}")
    print("  1. 访问 https://portal.azure.com/ → Azure Active Directory → App registrations")
    print("  2. New registration → 名称任意 → Supported account types: 'Accounts in any organizational directory and personal Microsoft accounts'")
    print("  3. 点击 Register，复制 Application (client) ID 和 Directory (tenant) ID")
    print("  4. 进入 API permissions → Add permission → Microsoft Graph → Delegated permissions:")
    print("     - Mail.Read")
    print("     - Mail.Send")
    print("     - User.Read")
    print("  5. 点击 Grant admin consent for ...（个人账户无需此步）")
    if not _confirm("是否继续?" if uf else "Continue?"):
        return False, {}

    tenant_id = _prompt("Tenant ID (输入 common 表示通用/个人账户)", "common")
    client_id = _prompt("Application (client) ID").strip()
    if not client_id:
        print(f"{RED}{'[x] client_id 不能为空' if uf else '[x] client_id is required'}{RESET}")
        return False, {}

    print(f"\n{CYAN}{'选择 OAuth2 登录方式:' if uf else 'Select OAuth2 login flow:'}{RESET}")
    print("  [1] 设备代码流 device_code（推荐：无需浏览器与本应用同机）")
    print("  [2] 授权码流 authorization_code（需浏览器与本应用同机）")
    flow_choice = _prompt("选择" if uf else "Choice", "1")
    flow = "device_code" if flow_choice != "2" else "authorization_code"
    redirect_uri = ""
    if flow == "authorization_code":
        redirect_uri = _prompt("Redirect URI", "http://localhost:17891")

    cfg = {
        "tenant_id": tenant_id or "common",
        "client_id": client_id,
        "flow": flow,
    }
    if redirect_uri:
        cfg["redirect_uri"] = redirect_uri

    _save_m365_cfg(cfg)
    print(f"{GREEN}{'[OK] 配置已保存，现在尝试登录...' if uf else '[OK] Config saved, trying to login...'}{RESET}")

    # 触发一次登录以验证配置并缓存 token
    try:
        token_result = _get_access_token(cfg, lang)
        if token_result.is_fail():
            print(f"{RED}{'[x] 登录失败:' if uf else '[x] Login failed:'} {token_result.error}{RESET}")
            return False, cfg
        print(f"{GREEN}{'[OK] Microsoft 365 登录成功并已缓存 token' if uf else '[OK] Microsoft 365 login succeeded and token cached'}{RESET}")
        return True, cfg
    except ImportError as e:
        print(f"{RED}{'[x]' if uf else '[x]'} {e}{RESET}")
        return False, cfg


def m365_logout() -> bool:
    """清除本地 M365 配置与 token 缓存"""
    try:
        # 清理主配置中的 m365 命名空间
        from fr_cli.conf.config import load_config, save_config
        cfg = load_config()
        if "m365" in cfg:
            del cfg["m365"]
            save_config(cfg)
        # 兼容旧独立文件
        if M365_CONFIG_FILE.exists():
            M365_CONFIG_FILE.unlink()
        return True
    except Exception:
        return False


def m365_status() -> Dict[str, Any]:
    """返回当前 M365 配置状态（不触发网络请求）"""
    cfg = _load_m365_cfg()
    has_cfg = bool(cfg.get("client_id"))
    has_token = bool(cfg.get("token_cache"))
    return {
        "configured": has_cfg,
        "has_token": has_token,
        "tenant_id": cfg.get("tenant_id", ""),
        "client_id": cfg.get("client_id", "")[:6] + "..." if cfg.get("client_id") else "",
        "flow": cfg.get("flow", "device_code"),
    }
