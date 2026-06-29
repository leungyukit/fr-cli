"""
AppState Config Mixin —— 配置更新方法

所有 update_* 方法都在这里,统一通过 self._lock 保护 + save_cfg() 持久化。
"""
from __future__ import annotations


from fr_cli.command.security import SecurityManager


class AppStateConfigMixin:
    """AppState 配置更新(update_provider/model/key/limit/lang/...)"""

    def save_cfg(self):
        """持久化当前配置(线程安全)"""
        from fr_cli.conf.config import save_config
        with self._lock:
            save_config(self.cfg)

    def update_provider(self, provider_id: str) -> bool:
        """切换 LLM 提供商

        用户主动切换:不重新走 default/backup 解析(避免覆盖用户意图)。
        """
        from fr_cli.core.llm import get_provider_info
        info = get_provider_info(provider_id)
        if not info:
            return False
        with self._lock:
            self.cfg["provider"] = provider_id
            self.provider = provider_id
            providers_cfg = self.cfg.setdefault("providers", {})
            pcfg = providers_cfg.setdefault(provider_id, {})

            default_model = info["default_model"]
            model = pcfg.get("model", default_model)

            self.cfg["model"] = model
            self.model_name = model
            pcfg["model"] = model
            self.save_cfg()
            self.reinit_client(prefer_active=False)
        return True

    def update_model(self, arg: str) -> bool:
        """切换模型

        支持格式:
          - "<model-name>"               自动推断 provider 并切换
          - "<provider>:<model-name>"    显式同时切换提供商和模型

        provider 与 model 始终强绑定,避免跨 provider 使用错误模型。
        """
        from fr_cli.core.llm import resolve_provider_model
        new_provider, new_model = resolve_provider_model(arg)
        with self._lock:
            if new_provider and new_provider != self.provider:
                if not self.update_provider(new_provider):
                    return False
            self.cfg["model"] = new_model
            self.model_name = new_model
            providers_cfg = self.cfg.setdefault("providers", {})
            pcfg = providers_cfg.setdefault(self.provider, {})
            pcfg["model"] = new_model
            self.save_cfg()
            self.reinit_client(prefer_active=False)
        return True

    def update_key(self, key: str):
        """更新 API 密钥(针对当前提供商)

        prefer_active=True,因为 key 变更可能让原 default 恢复可用,
        应重新走 default/backup 选择。
        """
        with self._lock:
            self.cfg["key"] = key
            providers_cfg = self.cfg.setdefault("providers", {})
            pcfg = providers_cfg.setdefault(self.provider, {})
            pcfg["key"] = key
            self.save_cfg()
            self.reinit_client(prefer_active=True)

    def update_limit(self, limit: int):
        """设置 Token 上限"""
        with self._lock:
            self.cfg["limit"] = limit
            self.limit = limit
            self.save_cfg()

    def update_context_compress_threshold(self, threshold: int):
        """设置上下文压缩阈值;0 表示关闭自动压缩"""
        with self._lock:
            self.cfg["context_compress_threshold"] = threshold
            self.context_compress_threshold = threshold
            self.save_cfg()

    def update_context_compress_keep_recent(self, keep_recent: int):
        """设置上下文压缩保留最近轮数"""
        with self._lock:
            self.cfg["context_compress_keep_recent"] = keep_recent
            self.context_compress_keep_recent = keep_recent
            self.save_cfg()

    def update_lang(self, lang: str):
        """切换界面语言(同时重建 SecurityManager)"""
        with self._lock:
            self.cfg["lang"] = lang
            self.lang = lang
            self.save_cfg()
            self.security = SecurityManager(self.lang, self.cfg)

    def update_session_name(self, name: str):
        """更新会话名"""
        with self._lock:
            self.sn = name
            self.cfg["session_name"] = name
            self.save_cfg()

    def update_thinking_mode(self, mode: str):
        """切换思维模式"""
        self.cfg["thinking_mode"] = mode
        self.thinking_mode = mode
        self.save_cfg()

    def update_ui_mode(self, mode: str) -> bool:
        """切换 UI 模式(chat/dev/agent)"""
        if mode not in ("chat", "dev", "agent"):
            return False
        self.cfg["ui_mode"] = mode
        self.ui_mode = mode
        self.save_cfg()
        return True

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
