"""
AppState Status Mixin —— 全局状态汇总

- status_summary:聚合所有可查询状态,供 /status 命令渲染
- _master_failure_patterns:读取 MasterAgent 进化记录中的失败模式
"""
from __future__ import annotations

from typing import Dict


class AppStateStatusMixin:
    """AppState 全局状态汇总"""

    def _master_failure_patterns(self) -> Dict:
        """读取 MasterAgent 进化记录中的失败模式摘要"""
        try:
            from fr_cli.agent.master import EVOLUTION_FILE
            import json
            if not EVOLUTION_FILE.exists():
                return {}
            with open(EVOLUTION_FILE, "r", encoding="utf-8") as f:
                evolution = json.load(f)
            hints = evolution.get("failure_hints", [])
            patterns = evolution.get("failure", [])
            return {
                "top_failures": patterns[:5],
                "failure_hints": hints[-5:],
            }
        except Exception:
            return {}

    def status_summary(self) -> dict:
        """聚合所有可查询状态,供 /status 命令渲染"""
        summary = {
            "provider": self.display_provider,
            "model": self.display_model,
            "api_key_configured": bool(
                self.api_key and self.api_key != "" and not getattr(self.client, "is_mock", False)
            ),
            "autonomous_mode": getattr(self.security, "autonomous_mode", "manual"),
            "lang": self.lang,
        }

        # MasterAgent
        try:
            ma_status = self.master_agent.status()
            summary["master_agent"] = {
                "enabled": bool(ma_status.get("enabled")),
                "total_interactions": ma_status.get("total_interactions", 0),
            }
        except Exception:
            summary["master_agent"] = {"enabled": False, "total_interactions": 0}

        # Agent HTTP 服务
        try:
            if self.agent_server and self.agent_server.is_running():
                summary["agent_server"] = {
                    "running": True,
                    "status": self.agent_server.status(),
                    "info": self.agent_server.get_publish_info(),
                }
            else:
                summary["agent_server"] = {"running": False, "status": "未运行"}
        except Exception:
            summary["agent_server"] = {"running": False, "status": "未运行"}

        # Hermes 守护
        try:
            from fr_cli.agent.hermes_manager import HermesManager
            hermes_mgr = HermesManager()
            summary["hermes_daemon"] = {
                "running": hermes_mgr.is_running(),
                "status": hermes_mgr.status(),
            }
        except Exception:
            summary["hermes_daemon"] = {"running": False, "status": "未知"}

        # Hermes 引擎
        try:
            summary["hermes_engine"] = self.hermes.status_report()
            summary["hermes_tasks"] = self.hermes.task_manager.counts()
        except Exception:
            summary["hermes_engine"] = "统计失败"
            summary["hermes_tasks"] = {}

        # Gatekeeper
        try:
            summary["gatekeeper"] = {
                "running": self.gatekeeper.is_running(),
                "status": self.gatekeeper.status(),
            }
        except Exception:
            summary["gatekeeper"] = {"running": False, "status": "未知"}

        # 审核队列
        try:
            from fr_cli.agent.review_queue import PersistentReviewQueue
            summary["review_queue"] = PersistentReviewQueue().counts()
        except Exception:
            summary["review_queue"] = {"total": 0, "pending": 0}

        # RAG watcher
        try:
            from fr_cli.agent.builtins.rag import get_rag_manager
            kb_dir = self.cfg.get("rag", {}).get("kb_dir") if isinstance(self.cfg.get("rag"), dict) else None
            if kb_dir:
                rag_mgr = get_rag_manager(kb_dir)
                thread_alive = (
                    rag_mgr._watcher_thread is not None
                    and rag_mgr._watcher_thread.is_alive()
                )
                summary["rag_watcher"] = {"running": thread_alive, "kb_dir": kb_dir}
            else:
                summary["rag_watcher"] = {"running": False, "kb_dir": None}
        except Exception:
            summary["rag_watcher"] = {"running": False, "kb_dir": None}

        # Cron
        try:
            from fr_cli.weapon.cron import CronManager
            summary["cron_jobs"] = len(CronManager().jobs)
        except Exception:
            summary["cron_jobs"] = 0

        # 插件与 Agent
        try:
            summary["plugins"] = len(self.plugins)
        except Exception:
            summary["plugins"] = 0
        try:
            from fr_cli.agent.manager import list_agents
            summary["agents"] = len(list_agents())
        except Exception:
            summary["agents"] = 0

        # 集中式错误报告
        try:
            from fr_cli.core.error_ledger import get_error_ledger
            ledger = get_error_ledger()
            summary["errors"] = {
                "hermes_failed_tasks": ledger.list_errors("hermes_task", limit=10),
                "dynamic_builder_selftest_failures": ledger.list_errors(
                    "dynamic_builder_selftest", limit=5
                ),
                "review_queue_rejected": ledger.list_errors("review_rejected", limit=5),
                "master_failure_patterns": self._master_failure_patterns(),
            }
        except Exception:
            summary["errors"] = {}

        return summary
