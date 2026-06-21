"""
全局状态管理容器 (AppState)
统一管理配置、子系统实例、运行时状态，实现依赖注入。
"""
from typing import List, Dict

from fr_cli.weapon.fs import VFS
import threading
from fr_cli.weapon.mail import MailClient
from fr_cli.weapon.m365 import _load_m365_cfg
from fr_cli.weapon.web import WebRaider
from fr_cli.weapon.disk import CloudDisk
from fr_cli.addon.plugin import init_plugins
from fr_cli.command.security import SecurityManager
from fr_cli.command.executor import CommandExecutor
from fr_cli.weapon.loader import load_weapon_md
from fr_cli.weapon.mcp import MCPManager
from fr_cli.core.llm import create_llm_client, create_llm_client_for, get_provider_info, resolve_provider_model
from fr_cli.core.usage import UsageTracker
from fr_cli.core.result import Result


class AppState:
    """应用程序运行时状态容器 —— 核心状态容器"""

    def __init__(self, cfg):
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
        self.active_plan = None          # 当前激活的结构化计划
        self.plan_step_idx = 0           # 当前执行到第几步
        self.active_plan_total_steps = 0 # 计划总步数（用于状态展示）

        # 唯一会话标识（UUID），贯穿本次运行周期
        import uuid
        self.session_id = str(uuid.uuid4())

        # LLM 客户端统一初始化（万法归一）
        # 优先读取用户保存的模型配置，无配置时保持未配置状态
        self.client, self.provider, self.model_name = create_llm_client(cfg, prefer_saved_model=True)
        # 若用户未显式配置 model，不自动使用 factory 默认
        if not self._user_configured_model(cfg):
            self.model_name = None
        self.api_key = self.client.api_key

        # 核心子系统实例化
        self.vfs = VFS(cfg.get("allowed_dirs", []))
        self.plugins = init_plugins()
        self.mail_c = MailClient(cfg.get("mail", {}))
        self.m365_cfg = _load_m365_cfg()
        self.web_c = WebRaider()
        self.disk_c = CloudDisk(cfg.get("disk", {}))
        self.security = SecurityManager(self.lang, cfg)

        # MCP 工具管理器（配置统一收敛到 ~/.fr_cli/config.json 的 mcp.servers）
        self.mcp = MCPManager(cfg=cfg)

        # 运行时消息与上下文
        self.messages = []
        self.context_summary = ""
        self.weapon_tools, self.weapon_triggers = load_weapon_md()
        self.mcp_tools = []  # 延迟加载，避免启动阻塞

        # 自动会话存档路径（按日期编号）
        self.auto_session_path = None

        # LLM 客户端缓存（供 Agent 专属模型复用）
        self._client_cache = {}

        # 命令执行引擎
        self.executor = CommandExecutor(self)

        # LLM 调用用量统计
        self.usage = UsageTracker(cfg=cfg)

        # 主控 Agent（自我进化型）
        from fr_cli.agent.master import MasterAgent
        self.master_agent = MasterAgent(self)

        # Agent HTTP 服务守护
        self.agent_server = None

        # Gatekeeper 守护进程管理器
        from fr_cli.gatekeeper.manager import GatekeeperManager
        self.gatekeeper = GatekeeperManager()

        # Hermes 后台自治任务引擎（延迟获取 state，避免循环引用）
        from fr_cli.agent.hermes import HermesEngine
        self.hermes = HermesEngine(state_provider=lambda: self)

        # 状态锁：保护配置变更等关键操作（注意：messages/context_summary 仍被多处直接访问）
        self._lock = threading.RLock()

        # 后台预热 LLM 连接（首次调用省 1-2s 冷启动）
        self._warmup_client_async()

        # 启动时加载持久化的动态构建工具
        self._bootstrap_dynamic_tools()

        # 启动时恢复持久化的定时任务
        self._restore_cron_jobs()

    def _restore_cron_jobs(self):
        """从 ~/.fr_cli/cron.json 恢复定时任务（agent 类型使用 state_provider 动态获取 state）"""
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
            if errors:
                # 启动时静默忽略单个工具加载错误，避免阻塞启动
                pass
        except Exception:
            pass

    @property
    def display_provider(self):
        """用于显示的 provider 名称：若用户未配置 provider，显示'未配置'"""
        if not self.cfg.get("provider"):
            return "未配置"
        return self.provider or "未配置"

    @property
    def display_model(self):
        """用于显示的模型名称：若用户未配置 provider/model，显示'未配置'"""
        if not self.cfg.get("provider"):
            return "未配置"
        if not self.model_name:
            return "未配置"
        providers_cfg = self.cfg.get("providers", {})
        pcfg = providers_cfg.get(self.provider, {})
        if not self.cfg.get("model") and not pcfg.get("model"):
            return "未配置"
        return self.model_name

    def reinit_client(self):
        """API Key、提供商或模型变更后更新客户端"""
        # 运行时切换允许读取保存的 model
        self.client, self.provider, self.model_name = create_llm_client(self.cfg, prefer_saved_model=True)
        # 若用户未显式配置 model，不自动使用 factory 默认
        if not self._user_configured_model(self.cfg):
            self.model_name = None
        self.api_key = self.client.api_key
        # 重新预热
        self._warmup_client_async()

    def _warmup_client_async(self):
        """后台线程预热 LLM 连接（首次调用省 1-2s 冷启动）"""
        import threading
        from fr_cli.core.llm import MockLLMClient
        if isinstance(self.client, MockLLMClient):
            return
        def _warmup():
            try:
                list(self.client.stream_chat(
                    model=self.model_name,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=1,
                ))
            except Exception:
                pass  # 预热失败不影响主流程
        t = threading.Thread(target=_warmup, daemon=True, name="llm-warmup")
        t.start()

    def save_cfg(self):
        """持久化当前配置（线程安全）"""
        from fr_cli.conf.config import save_config
        with self._lock:
            save_config(self.cfg)

    def update_provider(self, provider_id):
        """切换 LLM 提供商（召唤新的提供商）（线程安全）

        切换时自动同步 model：优先使用 provider 专属配置中保存的 model，
        否则使用 factory 默认模型，并确保 providers_cfg 和顶层 cfg 保持一致。
        """
        info = get_provider_info(provider_id)
        if not info:
            return False
        with self._lock:
            self.cfg["provider"] = provider_id
            self.provider = provider_id
            providers_cfg = self.cfg.setdefault("providers", {})
            pcfg = providers_cfg.setdefault(provider_id, {})

            default_model = info["default_model"]
            # 优先使用 provider 配置中已保存的 model，否则使用默认
            model = pcfg.get("model", default_model)

            self.cfg["model"] = model
            self.model_name = model
            pcfg["model"] = model  # 确保 providers_cfg 中始终同步
            self.save_cfg()
            self.reinit_client()
        return True

    def update_model(self, arg):
        """
        切换法器模型（线程安全）
        支持格式：
          - "<model-name>"               自动推断 provider 并切换（若模型属于其他 provider）
          - "<provider>:<model-name>"    显式同时切换提供商和模型

        核心原则：provider 与 model 始终强绑定，避免跨 provider 使用错误模型。
        """
        new_provider, new_model = resolve_provider_model(arg)
        with self._lock:
            if new_provider and new_provider != self.provider:
                # 模型名推断出了其他 provider，先切换 provider
                if not self.update_provider(new_provider):
                    return False
            # 同步更新当前 provider 的 model（保持 provider-model 一致性）
            self.cfg["model"] = new_model
            self.model_name = new_model
            providers_cfg = self.cfg.setdefault("providers", {})
            pcfg = providers_cfg.setdefault(self.provider, {})
            pcfg["model"] = new_model
            self.save_cfg()
            self.reinit_client()
        return True

    def update_key(self, key):
        """更新 API 密钥（针对当前提供商）（线程安全）"""
        with self._lock:
            self.cfg["key"] = key
            providers_cfg = self.cfg.setdefault("providers", {})
            pcfg = providers_cfg.setdefault(self.provider, {})
            pcfg["key"] = key
            self.save_cfg()
            self.reinit_client()

    def update_limit(self, limit):
        """设置 Token 上限（线程安全）"""
        with self._lock:
            self.cfg["limit"] = limit
            self.limit = limit
            self.save_cfg()

    def update_context_compress_threshold(self, threshold: int):
        """设置上下文压缩阈值（线程安全）；0 表示关闭自动压缩。"""
        with self._lock:
            self.cfg["context_compress_threshold"] = threshold
            self.context_compress_threshold = threshold
            self.save_cfg()

    def update_context_compress_keep_recent(self, keep_recent: int):
        """设置上下文压缩保留最近轮数（线程安全）。"""
        with self._lock:
            self.cfg["context_compress_keep_recent"] = keep_recent
            self.context_compress_keep_recent = keep_recent
            self.save_cfg()

    def update_lang(self, lang):
        """切换界面语言（线程安全）"""
        with self._lock:
            self.cfg["lang"] = lang
            self.lang = lang
            self.save_cfg()
            self.security = SecurityManager(self.lang, self.cfg)

    def update_session_name(self, name):
        """更新会话名（线程安全）"""
        with self._lock:
            self.sn = name
            self.cfg["session_name"] = name
            self.save_cfg()

    def reset_session(self):
        """重置会话状态 —— 开辟新的轮回"""
        import uuid
        self.session_id = str(uuid.uuid4())
        self.messages = []
        self.auto_session_path = None
        self.context_summary = ""
        self.sn = ""
        self.cfg["session_name"] = ""
        self.save_cfg()

    def update_thinking_mode(self, mode):
        """切换思维模式"""
        self.cfg["thinking_mode"] = mode
        self.thinking_mode = mode
        self.save_cfg()

    def update_ui_mode(self, mode):
        if mode not in ("chat", "dev", "agent"):
            return False
        self.cfg["ui_mode"] = mode
        self.ui_mode = mode
        self.save_cfg()
        return True

    @staticmethod
    def _user_configured_model(cfg):
        """检查用户是否在配置中显式指定了 model"""
        provider = cfg.get("provider")
        if not provider:
            return False
        providers_cfg = cfg.get("providers", {})
        pcfg = providers_cfg.get(provider, {})
        return bool(cfg.get("model") or pcfg.get("model"))

    def get_client_for(self, provider: str, model: str, override_key: str = None):
        """
        获取指定 provider + model 的 LLM 客户端，带缓存避免重复初始化
        若提供了 override_key，则优先使用（如 Agent 专属 key）
        """
        cache_key = (provider, model, override_key)
        cached = self._client_cache.get(cache_key)
        if cached is not None:
            return cached

        client, _, _ = create_llm_client_for(provider, model, self.cfg, override_key)
        self._client_cache[cache_key] = client
        return client

    def resolve_agent_llm(self, agent_name: str):
        """
        解析 Agent 的 LLM 配置：优先读取 Agent 的 config.json，
        若无专属配置则回退到全局默认。

        返回: (client, provider, model)
        """
        from fr_cli.agent.manager import load_agent_config
        agent_cfg = load_agent_config(agent_name)

        provider = agent_cfg.get("provider")
        model = agent_cfg.get("model")
        override_key = agent_cfg.get("key") or None

        # 防御性校验：provider 和 model 必须均为非空字符串才生效
        if provider and model and isinstance(provider, str) and isinstance(model, str):
            client = self.get_client_for(provider, model, override_key)
            return client, provider, model

        # 回退到全局默认
        return self.client, self.provider, self.model_name

    # ---------- 一键启动 / 全局状态 ----------

    def _sync_gatekeeper_config(self):
        """把当前 Agent HTTP、Cron 等配置同步到 Gatekeeper 配置文件"""
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

    def start_all_services(self, ports: dict = None) -> dict:
        """一键启动所有可选后台服务，返回各服务启动结果（Result 对象）。"""
        ports = ports or {}
        results = {}

        # 1. MasterAgent 自动启用
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
                self.agent_server = AgentHTTPServer(self, port=ports.get("agent_server", 17890))
            if not self.agent_server.is_running():
                results["agent_server"] = self.agent_server.start()
            else:
                results["agent_server"] = Result.ok(self.agent_server.status())
        except Exception as e:
            results["agent_server"] = Result.fail(f"启动失败: {e}")

        # 3. Hermes 独立守护进程
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

        # 4. Gatekeeper 独立守护进程
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

    def _master_failure_patterns(self) -> List[Dict]:
        """读取 MasterAgent 进化记录中的失败模式摘要。"""
        try:
            from fr_cli.agent.master import EVOLUTION_FILE
            import json
            if not EVOLUTION_FILE.exists():
                return []
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
        """聚合所有可查询状态，供 /status 命令渲染。"""
        # 模型与自主
        summary = {
            "provider": self.display_provider,
            "model": self.display_model,
            "api_key_configured": bool(self.api_key and self.api_key != "" and not getattr(self.client, "is_mock", False)),
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

        # Hermes 独立守护
        try:
            from fr_cli.agent.hermes_manager import HermesManager
            hermes_mgr = HermesManager()
            summary["hermes_daemon"] = {
                "running": hermes_mgr.is_running(),
                "status": hermes_mgr.status(),
            }
        except Exception:
            summary["hermes_daemon"] = {"running": False, "status": "未知"}

        # Hermes 引擎统计
        try:
            summary["hermes_engine"] = self.hermes.status_report()
            counts = self.hermes.task_manager.counts()
            summary["hermes_tasks"] = counts
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
            rq = PersistentReviewQueue()
            counts = rq.counts()
            summary["review_queue"] = counts
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
                "dynamic_builder_selftest_failures": ledger.list_errors("dynamic_builder_selftest", limit=5),
                "review_queue_rejected": ledger.list_errors("review_rejected", limit=5),
                "master_failure_patterns": self._master_failure_patterns(),
            }
        except Exception:
            summary["errors"] = {}

        return summary
