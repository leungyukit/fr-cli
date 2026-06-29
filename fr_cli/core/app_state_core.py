"""
AppState Core Mixin —— 初始化与基础显示

负责:
- __init__:初始化所有子系统(VFS / Security / MCP / Master / Hermes / Gatekeeper 等)
- display_provider / display_model:用于 UI 显示
- _restore_cron_jobs / _bootstrap_dynamic_tools:启动钩子
- _user_configured_model:辅助判断

不含:
- update_* 方法(在 app_state_config.py)
- 客户端管理(在 app_state_client.py)
- 后台服务(在 app_state_services.py)
- 状态汇总(在 app_state_status.py)
"""
from __future__ import annotations

import threading
import uuid
from typing import Any, Dict


class AppStateCoreMixin:
    """AppState 核心初始化与基础显示"""

    def _init_core(self, cfg: Dict[str, Any]):
        """初始化所有子系统(由 __init__ 调用,而不是 mixin __init__)

        由于 AppState 由多个 mixin 组合,统一在此方法内初始化所有属性。
        这样 mixin 的方法可以安全访问 self.cfg / self.client / self.lang 等。
        """
        self.cfg = cfg
        self.lang = cfg.get("lang", "zh")
        self.limit = cfg.get("limit", 4096)
        self.sn = cfg.get("session_name", "")
        self.aliases = cfg.get("aliases", {})
        self.thinking_mode = cfg.get("thinking_mode", "direct")
        self.ui_mode = cfg.get("ui_mode", "dev")
        self.context_compress_threshold = cfg.get("context_compress_threshold", 4000)
        self.context_compress_keep_recent = cfg.get("context_compress_keep_recent", 5)

        # 计划模式运行时状态
        self.active_plan = None
        self.plan_step_idx = 0
        self.active_plan_total_steps = 0

        # 唯一会话标识(UUID)
        self.session_id = str(uuid.uuid4())

        # LLM 客户端初始化(委托给 client mixin)
        self._init_llm_client(cfg)

        # 核心子系统
        self._init_subsystems(cfg)

        # 运行时消息 / 上下文
        self.messages = []
        self.context_summary = ""
        from fr_cli.weapon.loader import load_weapon_md
        self.weapon_tools, self.weapon_triggers = load_weapon_md()
        self.mcp_tools = []
        self.auto_session_path = None
        self._client_cache = {}

        # 命令执行引擎
        from fr_cli.command.executor import CommandExecutor
        self.executor = CommandExecutor(self)

        # LLM 用量统计(订阅 v3 bus)
        from fr_cli.core.usage import UsageTracker
        self.usage = UsageTracker(cfg=cfg)
        try:
            self.usage.install_listener()
        except Exception:
            pass

        # v3.0+:订阅 EventBus → ErrorLedger
        try:
            from fr_cli.core.error_ledger import get_error_ledger, install_bus_listeners
            get_error_ledger()
            install_bus_listeners()
        except Exception:
            pass

        # v3.0+:安装 MetricsPlugin
        try:
            from fr_cli.core.metrics import install_metrics
            self.metrics = install_metrics()
        except Exception:
            self.metrics = None

        # Master / Gatekeeper / Hermes
        from fr_cli.agent.master import MasterAgent
        self.master_agent = MasterAgent(self)
        self.agent_server = None
        from fr_cli.gatekeeper.manager import GatekeeperManager
        self.gatekeeper = GatekeeperManager()
        from fr_cli.agent.hermes import HermesEngine
        self.hermes = HermesEngine(state_provider=lambda: self)

        self._lock = threading.RLock()

        # 启动钩子
        self._warmup_client_async()
        self._bootstrap_dynamic_tools()
        self._restore_cron_jobs()

    def _init_llm_client(self, cfg):
        """初始化 LLM 客户端(由 client mixin 覆盖)"""
        from fr_cli.core.llm import create_llm_client, resolve_active_model
        self._active_resolution = resolve_active_model(cfg)
        active_provider = self._active_resolution["provider"]
        active_model = self._active_resolution["model"]
        active_source = self._active_resolution["source"]

        if active_provider:
            self.cfg["provider"] = active_provider
            if active_model:
                self.cfg["model"] = active_model
            self.client, self.provider, self.model_name = create_llm_client(cfg, prefer_saved_model=True)
            self._fallback_notice = (
                self._active_resolution["reason"] if active_source == "backup" else None
            )
        else:
            self.client, self.provider, self.model_name = create_llm_client(cfg, prefer_saved_model=True)
            self._fallback_notice = self._active_resolution["reason"]
            if not self._user_configured_model(cfg):
                self.model_name = None

        self.api_key = self.client.api_key
        self.active_model_source = active_source
        self.is_fallback_active = (active_source == "backup")

    def _init_subsystems(self, cfg):
        """初始化文件系统 / 安全 / MCP / 邮件 / 网盘 / Web 等子系统"""
        from fr_cli.weapon.fs import VFS
        from fr_cli.weapon.mail import MailClient
        from fr_cli.weapon.m365 import _load_m365_cfg
        from fr_cli.weapon.web import WebRaider
        from fr_cli.weapon.disk import CloudDisk
        from fr_cli.addon.plugin import init_plugins
        from fr_cli.command.security import SecurityManager
        from fr_cli.weapon.mcp import MCPManager

        self.vfs = VFS(cfg.get("allowed_dirs", []))
        self.plugins = init_plugins()
        self.mail_c = MailClient(cfg.get("mail", {}))
        self.m365_cfg = _load_m365_cfg()
        self.web_c = WebRaider()
        self.disk_c = CloudDisk(cfg.get("disk", {}))
        self.security = SecurityManager(self.lang, cfg)
        self.mcp = MCPManager(cfg=cfg)

    # ---------------- 显示属性 ----------------

    @property
    def display_provider(self) -> str:
        """用于显示的 provider 名称:若用户未配置 provider,显示'未配置'"""
        if not self.cfg.get("provider"):
            return "未配置"
        return self.provider or "未配置"

    @property
    def display_model(self) -> str:
        """用于显示的模型名称:若用户未配置 provider/model,显示'未配置'"""
        if not self.cfg.get("provider"):
            return "未配置"
        if not self.model_name:
            return "未配置"
        providers_cfg = self.cfg.get("providers", {})
        pcfg = providers_cfg.get(self.provider, {})
        if not self.cfg.get("model") and not pcfg.get("model"):
            return "未配置"
        return self.model_name

    # ---------------- 启动钩子 ----------------

    def _restore_cron_jobs(self):
        """从 ~/.fr_cli/cron.json 恢复定时任务"""
        try:
            from fr_cli.weapon.cron import CronManager
            state_provider = lambda: self
            CronManager().load_persistent_jobs(lang=self.lang, state_provider=state_provider)
        except Exception:
            pass

    def _bootstrap_dynamic_tools(self):
        """加载 ~/.fr_cli/dynamic_tools/ 下已构建的工具"""
        try:
            from fr_cli.dynamic_builder import bootstrap_dynamic_tools
            count, errors = bootstrap_dynamic_tools()
        except Exception:
            pass

    # ---------------- 辅助 ----------------

    @staticmethod
    def _user_configured_model(cfg: Dict[str, Any]) -> bool:
        """检查用户是否在配置中显式指定了 model"""
        provider = cfg.get("provider")
        if not provider:
            return False
        providers_cfg = cfg.get("providers", {})
        pcfg = providers_cfg.get(provider, {})
        return bool(cfg.get("model") or pcfg.get("model"))
