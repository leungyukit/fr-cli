"""
全局状态管理容器 (AppState)
统一管理配置、子系统实例、运行时状态，实现依赖注入。
"""
from zhipuai import ZhipuAI
from fr_cli.weapon.fs import VFS
from fr_cli.weapon.mail import MailClient
from fr_cli.weapon.web import WebRaider
from fr_cli.weapon.disk import CloudDisk
from fr_cli.addon.plugin import init_plugins
from fr_cli.command.security import SecurityManager
from fr_cli.command.executor import CommandExecutor
from fr_cli.weapon.loader import load_weapon_md


class AppState:
    """应用程序运行时状态容器 —— 本命元神"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.lang = cfg.get("lang", "zh")
        self.model_name = cfg.get("model", "glm-4-flash")
        self.limit = cfg.get("limit", 4096)
        self.api_key = cfg.get("key", "")
        self.sn = cfg.get("session_name", "")
        self.aliases = cfg.get("aliases", {})
        self.thinking_mode = cfg.get("thinking_mode", "direct")

        # 核心子系统实例化
        self.client = ZhipuAI(api_key=self.api_key)
        self.vfs = VFS(cfg.get("allowed_dirs", []))
        self.plugins = init_plugins()
        self.mail_c = MailClient(cfg.get("mail", {}))
        self.web_c = WebRaider()
        self.disk_c = CloudDisk(cfg.get("disk", {}))
        self.security = SecurityManager(self.lang, cfg)

        # 运行时消息与上下文
        self.messages = []
        self.context_summary = ""
        self.weapon_tools, self.weapon_triggers = load_weapon_md()

        # 自动会话存档路径（按日期编号）
        self.auto_session_path = None

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
        """API Key 或模型变更后重铸客户端"""
        self.api_key = self.cfg.get("key", "")
        self.client = ZhipuAI(api_key=self.api_key)

    def save_cfg(self):
        """持久化当前配置"""
        from fr_cli.conf.config import save_config
        save_config(self.cfg)

    def update_model(self, name):
        """切换法器模型"""
        self.cfg["model"] = name
        self.model_name = name
        self.save_cfg()
        self.reinit_client()

    def update_key(self, key):
        """重铸 API 密钥"""
        self.cfg["key"] = key
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
