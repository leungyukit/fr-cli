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
    """应用程序运行时状态容器 —— 本命元神"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.lang = cfg.get("lang", "zh")
        self.limit = cfg.get("limit", 4096)
        self.sn = cfg.get("session_name", "")
        self.aliases = cfg.get("aliases", {})
        self.thinking_mode = cfg.get("thinking_mode", "direct")

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

        # MCP 法宝管理器
        self.mcp = MCPManager(cfg)

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

    def reinit_client(self):
        """API Key、提供商或模型变更后重铸客户端"""
        self.client, self.provider, self.model_name = create_llm_client(self.cfg)
        self.api_key = self.client.api_key

    def save_cfg(self):
        """持久化当前配置"""
        from fr_cli.conf.config import save_config
        save_config(self.cfg)

    def update_provider(self, provider_id):
        """切换 LLM 提供商（召唤新的道统）"""
        info = get_provider_info(provider_id)
        if not info:
            return False
        self.cfg["provider"] = provider_id
        # 如果新提供商没有设置过模型，使用其默认模型
        providers_cfg = self.cfg.setdefault("providers", {})
        if provider_id not in providers_cfg or not providers_cfg[provider_id].get("model"):
            self.cfg["model"] = info["default_model"]
            self.model_name = info["default_model"]
        else:
            self.model_name = providers_cfg[provider_id].get("model", info["default_model"])
            self.cfg["model"] = self.model_name
        self.save_cfg()
        self.reinit_client()
        return True

    def update_model(self, arg):
        """
        切换法器模型
        支持格式：
          - "deepseek-chat"              仅切换模型（保持当前提供商）
          - "deepseek:deepseek-chat"     同时切换提供商和模型
        """
        new_provider, new_model = resolve_provider_model(arg)
        if new_provider and new_provider != self.provider:
            # 切换提供商 + 模型
            if not self.update_provider(new_provider):
                return False
        self.cfg["model"] = new_model
        self.model_name = new_model
        # 同步到 providers 配置中当前提供商的 model
        providers_cfg = self.cfg.setdefault("providers", {})
        pcfg = providers_cfg.setdefault(self.provider, {})
        pcfg["model"] = new_model
        self.save_cfg()
        self.reinit_client()
        return True

    def update_key(self, key):
        """重铸 API 密钥（针对当前提供商）"""
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
        """更新轮回名"""
        self.sn = name
        self.cfg["session_name"] = name
        self.save_cfg()

    def update_thinking_mode(self, mode):
        """切换思维模式"""
        self.cfg["thinking_mode"] = mode
        self.thinking_mode = mode
        self.save_cfg()

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
