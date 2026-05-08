"""
Gateway 功能 - 多平台消息网关
参考 Hermes Agent 实现
支持 Telegram、Discord、Slack 等平台
"""

import os
import asyncio
import json
from typing import Dict, Optional
from dataclasses import dataclass
from enum import Enum


class Platform(Enum):
    """支持的平台"""
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    CLI = "cli"


@dataclass
class GatewayConfig:
    """网关配置"""
    platform: Platform
    enabled: bool = False
    bot_token: Optional[str] = None
    api_key: Optional[str] = None
    chat_id: Optional[str] = None


class GatewayManager:
    """网关管理器"""

    def __init__(self):
        self.config_file = os.path.expanduser("~/.fr_cli/gateway.json")
        self.platforms: Dict[str, GatewayConfig] = {}
        self._load_config()
        self._running = False

    def _load_config(self):
        """加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file) as f:
                    data = json.load(f)
                    for name, cfg in data.items():
                        self.platforms[name] = GatewayConfig(
                            platform=Platform(cfg.get("platform", "cli")),
                            enabled=cfg.get("enabled", False),
                            bot_token=cfg.get("bot_token"),
                            api_key=cfg.get("api_key"),
                            chat_id=cfg.get("chat_id")
                        )
            except Exception:
                pass

    def _save_config(self):
        """保存配置"""
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        data = {}
        for name, cfg in self.platforms.items():
            data[name] = {
                "platform": cfg.platform.value,
                "enabled": cfg.enabled,
                "bot_token": cfg.bot_token,
                "api_key": cfg.api_key,
                "chat_id": cfg.chat_id
            }
        with open(self.config_file, 'w') as f:
            json.dump(data, f, indent=2)

    def configure_telegram(self, bot_token: str, allowed_chat_ids: list = None):
        """配置 Telegram"""
        self.platforms["telegram"] = GatewayConfig(
            platform=Platform.TELEGRAM,
            enabled=True,
            bot_token=bot_token,
            chat_id=json.dumps(allowed_chat_ids or [])
        )
        self._save_config()
        print("✅ Telegram 配置完成")
        print("   使用 /gateway start telegram 启动")

    def configure_discord(self, bot_token: str, guild_id: str = None):
        """配置 Discord"""
        self.platforms["discord"] = GatewayConfig(
            platform=Platform.DISCORD,
            enabled=True,
            bot_token=bot_token,
            chat_id=guild_id
        )
        self._save_config()
        print("✅ Discord 配置完成")
        print("   使用 /gateway start discord 启动")

    def list_platforms(self):
        """列出已配置的平台"""
        print("\n📱 已配置的消息平台:")
        if not self.platforms:
            print("   (无)")
            return

        for name, cfg in self.platforms.items():
            status = "✅ 启用" if cfg.enabled else "❌ 禁用"
            print(f"   {name}: {status}")
        print()

    async def start_telegram(self):
        """启动 Telegram Bot"""
        cfg = self.platforms.get("telegram")
        if not cfg or not cfg.enabled:
            print("❌ Telegram 未配置")
            return

        try:
            from telegram import Bot
            from telegram.ext import Application, CommandHandler, MessageHandler, filters

            bot = Bot(token=cfg.bot_token)

            async def handle_message(update, context):
                from fr_cli.core.core import ask
                message = update.message.text
                result, _ = await asyncio.to_thread(ask, message)
                await update.message.reply_text(result)

            app = Application.builder().token(cfg.bot_token).build()
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            print("🤖 Telegram Bot 已启动!")
            await app.run_polling()

        except ImportError:
            print("❌ 需要安装 python-telegram-bot: pip install python-telegram-bot")
        except Exception as e:
            print(f"❌ Telegram 启动失败: {e}")

    async def start_discord(self):
        """启动 Discord Bot"""
        cfg = self.platforms.get("discord")
        if not cfg or not cfg.enabled:
            print("❌ Discord 未配置")
            return

        try:
            import discord

            intents = discord.Intents.default()
            intents.message_content = True
            client = discord.Client(intents=intents)

            @client.event
            async def on_message(message):
                if message.author == client.user:
                    return

                from fr_cli.core.core import ask
                result, _ = await asyncio.to_thread(ask, message.content)
                await message.channel.send(result)

            print("📢 Discord Bot 已启动!")
            await client.start(cfg.bot_token)

        except ImportError:
            print("❌ 需要安装 discord.py: pip install discord.py")
        except Exception as e:
            print(f"❌ Discord 启动失败: {e}")

    async def start_all(self):
        """启动所有已配置的平台"""
        tasks = []
        if "telegram" in self.platforms and self.platforms["telegram"].enabled:
            tasks.append(self.start_telegram())
        if "discord" in self.platforms and self.platforms["discord"].enabled:
            tasks.append(self.start_discord())

        if tasks:
            await asyncio.gather(*tasks)
        else:
            print("❌ 没有已启用的平台")

    def stop(self):
        """停止网关"""
        self._running = False
        print("🛑 网关已停止")


def run_gateway(platform: str = None):
    """运行网关"""
    manager = GatewayManager()

    if platform:
        if platform == "telegram":
            asyncio.run(manager.start_telegram())
        elif platform == "discord":
            asyncio.run(manager.start_discord())
        else:
            print(f"❌ 不支持的平台: {platform}")
    else:
        asyncio.run(manager.start_all())


# CLI 命令
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "start":
            platform = sys.argv[2] if len(sys.argv) > 2 else None
            run_gateway(platform)
        elif sys.argv[1] == "setup":
            manager = GatewayManager()
            manager.list_platforms()
        else:
            print("用法: fr gateway [start|setup] [platform]")
    else:
        print("""
╔════════════════════════════════════════════════════╗
║           fr-cli Gateway 消息网关                 ║
╚════════════════════════════════════════════════════╝

用法:
  fr gateway setup                    查看已配置的平台
  fr gateway start telegram           启动 Telegram Bot
  fr gateway start discord           启动 Discord Bot
  fr gateway start                   启动所有平台

配置示例:
  from fr_cli.agent.gateway import GatewayManager
  gm = GatewayManager()
  gm.configure_telegram("your-bot-token")
  gm.configure_discord("your-bot-token")
        """)
