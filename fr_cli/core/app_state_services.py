"""
AppState Services Mixin —— 后台服务管理

- _sync_gatekeeper_config:把 Agent HTTP / Cron 等配置同步到 Gatekeeper
- start_all_services:一键启动 MasterAgent / Agent HTTP / Hermes / Gatekeeper
"""
from __future__ import annotations

from typing import Dict, Optional

from fr_cli.core.result import Result


class AppStateServicesMixin:
    """AppState 后台服务管理"""

    def _sync_gatekeeper_config(self):
        """把当前 Agent HTTP / Cron 等配置同步到 Gatekeeper 配置文件"""
        try:
            from fr_cli.gatekeeper.manager import read_daemon_config
            from fr_cli.weapon.cron import CronManager

            existing_cfg = read_daemon_config()
            agent_port = None
            if self.agent_server and self.agent_server.is_running():
                agent_port = self.agent_server.port

            daemon_cfg = {
                "agent_server_port": agent_port,
                "cron_jobs": CronManager().export_jobs(),
                "agent_crons": existing_cfg.get("agent_crons", []),
                "lang": self.lang,
            }
            if hasattr(self.gatekeeper, 'save_daemon_config'):
                self.gatekeeper.save_daemon_config(daemon_cfg)
        except Exception:
            pass

    def start_all_services(self, ports: Optional[Dict[str, int]] = None) -> Dict[str, Result]:
        """一键启动所有可选后台服务

        Returns:
            {service_name: Result} 字典
        """
        ports = ports or {}
        results: Dict[str, Result] = {}

        # 1. MasterAgent
        try:
            if not self.master_agent.is_enabled():
                self.master_agent.toggle(True)
            results["master_agent"] = Result.ok("已启用")
        except Exception as e:
            results["master_agent"] = Result.fail(f"启用失败: {e}")

        # 2. Agent HTTP 服务
        try:
            from fr_cli.agent.server import AgentHTTPServer
            if self.agent_server is None:
                self.agent_server = AgentHTTPServer(
                    self, port=ports.get("agent_server", 17890),
                )
            if not self.agent_server.is_running():
                results["agent_server"] = self.agent_server.start()
            else:
                results["agent_server"] = Result.ok(self.agent_server.status())
        except Exception as e:
            results["agent_server"] = Result.fail(f"启动失败: {e}")

        # 3. Hermes 独立守护
        try:
            from fr_cli.agent.hermes_manager import HermesManager
            hermes_mgr = HermesManager()
            if not hermes_mgr.is_running():
                results["hermes_daemon"] = hermes_mgr.start(
                    port=ports.get("hermes", 8765),
                    host="127.0.0.1",
                    lang=self.lang,
                )
            else:
                results["hermes_daemon"] = Result.ok(hermes_mgr.status())
        except Exception as e:
            results["hermes_daemon"] = Result.fail(f"启动失败: {e}")

        # 4. Gatekeeper 独立守护
        try:
            self._sync_gatekeeper_config()
            if not self.gatekeeper.is_running():
                results["gatekeeper"] = self.gatekeeper.start()
            else:
                results["gatekeeper"] = Result.ok(self.gatekeeper.status())
        except Exception as e:
            results["gatekeeper"] = Result.fail(f"启动失败: {e}")

        # 5. Cron 任务数量
        try:
            from fr_cli.weapon.cron import CronManager
            results["cron"] = Result.ok(f"定时任务: {len(CronManager().jobs)} 个")
        except Exception as e:
            results["cron"] = Result.fail(f"统计失败: {e}")

        return results
