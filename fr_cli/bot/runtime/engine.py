"""
Bot 运行时引擎 —— 从配置装配出「网关 + 调度器 + 通道」

v2.8.7 新增。

配置位置：``~/.fr_cli/bot/config.json``

.. code-block:: json

    {
      "host": "127.0.0.1",
      "port": 8790,
      "pool_size": 2,
      "bot_names": ["凡人"],
      "group_whitelist": [],
      "require_mention_in_group": true,
      "confirm_timeout": 120,
      "dedup_ttl": 3600,
      "channels": {
        "lark": {"app_id": "", "app_secret": "", "verification_token": ""},
        "telegram": {"bot_token": ""}
      }
    }

装配顺序刻意保持**可插拔**：新增平台只需在 ``channels`` 里加一段配置，
通道实现由 ``fr_cli/bot/channels/`` 里的 ``@register_channel`` 自动登记。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from fr_cli.bot.core.channel import Channel, get_channel, list_channel_classes
from fr_cli.bot.core.confirm_broker import ConfirmBroker
from fr_cli.bot.core.dispatcher import BotDispatcher
from fr_cli.bot.core.idempotency import IdempotencyGuard
from fr_cli.bot.core.router import Router
from fr_cli.bot.core.session_store import SessionStore
from fr_cli.bot.core.state_pool import StatePool
from fr_cli.bot.runtime.gateway import DEFAULT_PORT, BotGateway

__all__ = ["BotEngine", "load_bot_config", "save_bot_config", "DEFAULT_BOT_CONFIG"]

#: 默认配置
DEFAULT_BOT_CONFIG: Dict[str, Any] = {
    "host": "127.0.0.1",
    "port": DEFAULT_PORT,
    "pool_size": 2,
    "bot_names": [],
    "group_whitelist": [],
    "require_mention_in_group": True,
    "confirm_timeout": 120,
    "dedup_ttl": 3600,
    "channels": {},
}


def _config_path() -> Path:
    from fr_cli.conf.paths import BOT_CONFIG_FILE
    return Path(BOT_CONFIG_FILE)


def load_bot_config() -> Dict[str, Any]:
    """读取 bot 配置（不存在时返回默认配置的副本）。"""
    cfg = dict(DEFAULT_BOT_CONFIG)
    path = _config_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update(data)
        except Exception:
            pass
    cfg.setdefault("channels", {})
    return cfg


def save_bot_config(cfg: Dict[str, Any]) -> bool:
    """保存 bot 配置。"""
    path = _config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        try:
            path.chmod(0o600)
        except Exception:
            pass
        return True
    except Exception:
        return False


class BotEngine:
    """把配置装配成可运行的 bot 运行时。

    Args:
        cfg:      fr-cli 主配置（模型 / key 等）
        bot_cfg:  bot 配置（见模块 docstring）
    """

    def __init__(self, cfg: Dict[str, Any], bot_cfg: Optional[Dict[str, Any]] = None):
        self.cfg = dict(cfg or {})
        self.bot_cfg = dict(bot_cfg or load_bot_config())
        self.channels: Dict[str, Channel] = {}
        self.dispatcher: Optional[BotDispatcher] = None
        self.gateway: Optional[BotGateway] = None
        self._lock = threading.Lock()

    # ---------- 装配 ----------

    def build_channels(self) -> Dict[str, Channel]:
        """按配置实例化通道。"""
        from fr_cli.bot.channels import load_channels
        load_channels()

        channels: Dict[str, Channel] = {}
        for name, ch_cfg in (self.bot_cfg.get("channels") or {}).items():
            if not isinstance(ch_cfg, dict):
                continue
            if ch_cfg.get("enabled") is False:
                continue
            channel = get_channel(name, ch_cfg)
            if channel is None:
                continue
            channels[name] = channel
        self.channels = channels
        return channels

    def build_dispatcher(self) -> BotDispatcher:
        """构造调度器。"""
        from fr_cli.conf.paths import BOT_SESSIONS_DIR

        pool_size = int(self.bot_cfg.get("pool_size") or 2)
        pool = StatePool(self.cfg, size=pool_size)

        store = SessionStore(persist_dir=Path(BOT_SESSIONS_DIR))
        router = Router(
            bot_names=list(self.bot_cfg.get("bot_names") or []),
            group_whitelist=self.bot_cfg.get("group_whitelist") or None,
            require_mention_in_group=bool(
                self.bot_cfg.get("require_mention_in_group", True)
            ),
        )
        guard = IdempotencyGuard(ttl=int(self.bot_cfg.get("dedup_ttl") or 3600))
        broker = ConfirmBroker(default_timeout=int(self.bot_cfg.get("confirm_timeout") or 120))

        self.dispatcher = BotDispatcher(
            state_pool=pool,
            session_store=store,
            router=router,
            idempotency=guard,
            confirm_broker=broker,
            ask_user=self._make_ask_user(),
        )
        return self.dispatcher

    def _make_ask_user(self):
        """构造"把确认问题发回聊天窗口"的回调。"""
        def _ask(channel: str, chat_id: str, thread_id: str, text: str) -> None:
            ch = self.channels.get(channel)
            if ch is None:
                return
            from fr_cli.bot.core.message import BotReply
            try:
                ch.send(BotReply(chat_id=chat_id, text=text, thread_id=thread_id))
            except Exception:
                pass
        return _ask

    def build_gateway(self) -> BotGateway:
        """构造 HTTP 网关。"""
        if self.dispatcher is None:
            self.build_dispatcher()
        if not self.channels:
            self.build_channels()
        self.gateway = BotGateway(
            dispatcher=self.dispatcher,
            channels=self.channels,
            host=str(self.bot_cfg.get("host") or "127.0.0.1"),
            port=int(self.bot_cfg.get("port") or DEFAULT_PORT),
            token=self.bot_cfg.get("token") or None,
        )
        return self.gateway

    def build(self):
        """一次性装配全部组件。返回 (dispatcher, gateway)。"""
        self.build_channels()
        self.build_dispatcher()
        self.build_gateway()
        return self.dispatcher, self.gateway

    # ---------- 自述 ----------

    def available_channels(self) -> List[str]:
        """列出所有已实现的通道（不管有没有配置）。"""
        from fr_cli.bot.channels import load_channels
        load_channels()
        return list_channel_classes()

    def status(self) -> Dict[str, Any]:
        """运行状态。"""
        return {
            "running": bool(self.gateway and self.gateway.is_running()),
            "channels": sorted(self.channels.keys()),
            "available_channels": self.available_channels(),
            "gateway": self.gateway.status() if self.gateway else None,
        }
