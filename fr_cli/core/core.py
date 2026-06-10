"""
全局状态管理容器 (AppState)
统一管理配置、子系统实例、运行时状态，实现依赖注入。
"""
from fr_cli.weapon.fs import VFS
from fr_cli.weapon.mail import MailClient
from fr_cli.weapon.web import WebRaider
from fr_cli.weapon.disk import CloudDisk
from fr_cli.addon.plugin import init_plugins
from fr_cli.command.security import SecurityManager
from fr_cli.command.executor import CommandExecutor
from fr_cli.weapon.loader import load_weapon_md
from fr_cli.weapon.mcp import MCPManager
from fr_cli.core.llm import create_llm_client, create_llm_client_for, list_providers, get_provider_info, resolve_provider_model


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

        # LLM 客户端统一初始化（万法归一）
        self.client, self.provider, self.model_name = create_llm_client(cfg)
        self.api_key = self.client.api_key

        # 核心子系统实例化
        self.vfs = VFS(cfg.get("allowed_dirs", []))
        self.plugins = init_plugins()
        self.mail_c = MailClient(cfg.get("mail", {}))
        self.web_c = WebRaider()
        self.disk_c = CloudDisk(cfg.get("disk", {}))
        self.security = SecurityManager(self.lang, cfg)

        # MCP 工具管理器
        self.mcp = MCPManager()
        # 同时从主配置 cfg["mcp"]["servers"] 同步，让两套配置源至少有一处生效
        try:
            self.mcp.sync_from_cfg(cfg)
        except Exception:
            pass

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

        # 主控 Agent（自我进化型）
        from fr_cli.agent.master import MasterAgent
        self.master_agent = MasterAgent(self)

        # Agent HTTP 服务守护
        self.agent_server = None

        # Gatekeeper 守护进程管理器
        from fr_cli.gatekeeper.manager import GatekeeperManager
        self.gatekeeper = GatekeeperManager()

        # 后台预热 LLM 连接（首次调用省 1-2s 冷启动）
        self._warmup_client_async()

    def reinit_client(self):
        """API Key、提供商或模型变更后更新客户端"""
        self.client, self.provider, self.model_name = create_llm_client(self.cfg)
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
        """持久化当前配置"""
        from fr_cli.conf.config import save_config
        save_config(self.cfg)

    def update_provider(self, provider_id):
        """切换 LLM 提供商（召唤新的提供商）

        切换时自动同步 model：优先使用 provider 专属配置中保存的 model，
        否则使用 factory 默认模型，并确保 providers_cfg 和顶层 cfg 保持一致。
        """
        info = get_provider_info(provider_id)
        if not info:
            return False
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
        切换法器模型
        支持格式：
          - "deepseek-chat"              自动推断 provider 并切换（若模型属于其他 provider）
          - "deepseek:deepseek-chat"     显式同时切换提供商和模型

        核心原则：provider 与 model 始终强绑定，避免跨 provider 使用错误模型。
        """
        new_provider, new_model = resolve_provider_model(arg)
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
        """更新 API 密钥（针对当前提供商）"""
        self.cfg["key"] = key
        providers_cfg = self.cfg.setdefault("providers", {})
        pcfg = providers_cfg.setdefault(self.provider, {})
        pcfg["key"] = key
        self.save_cfg()
        self.reinit_client()

    def update_limit(self, limit):
        """设置 Token 上限"""
        self.cfg["limit"] = limit
        self.limit = limit
        self.save_cfg()

    def update_lang(self, lang):
        """切换界面语言"""
        self.cfg["lang"] = lang
        self.lang = lang
        self.save_cfg()
        self.security = SecurityManager(self.lang, self.cfg)

    def update_session_name(self, name):
        """更新会话名"""
        self.sn = name
        self.cfg["session_name"] = name
        self.save_cfg()

    def update_thinking_mode(self, mode):
        """切换思维模式"""
        self.cfg["thinking_mode"] = mode
        self.thinking_mode = mode

    def update_ui_mode(self, mode):
        if mode not in ("chat", "dev", "agent"):
            return False
        self.cfg["ui_mode"] = mode
        self.ui_mode = mode
        self.save_cfg()
        return True

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
