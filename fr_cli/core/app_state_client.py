"""
AppState Client Mixin —— LLM 客户端管理与 Agent 专属模型

- reinit_client:API Key / provider / model 变更后重建 client
- _warmup_client_async:后台预热连接(省 1-2s 冷启动)
- get_client_for:为指定 provider+model 创建/缓存 client
- resolve_agent_llm:解析 Agent 的专属 LLM 配置(回退到全局默认)
"""
from __future__ import annotations

import threading
from typing import Any, Tuple


class AppStateClientMixin:
    """AppState LLM 客户端管理"""

    def reinit_client(self, *, prefer_active: bool = True):
        """API Key / provider / model 变更后更新 client

        Args:
            prefer_active: True 时优先按 default/backup 优先级重新选择活跃模型;
                          False 时直接用 cfg['provider']/'model'(用户手动 /model 切时)
        """
        from fr_cli.core.llm import create_llm_client, resolve_active_model
        if prefer_active:
            resolution = resolve_active_model(self.cfg)
            self._active_resolution = resolution
            if resolution["provider"]:
                self.cfg["provider"] = resolution["provider"]
                if resolution["model"]:
                    self.cfg["model"] = resolution["model"]
                self.active_model_source = resolution["source"]
                self.is_fallback_active = (resolution["source"] == "backup")
                self._fallback_notice = (
                    resolution["reason"] if resolution["source"] == "backup" else None
                )
            else:
                self.active_model_source = None
                self.is_fallback_active = False
                self._fallback_notice = resolution["reason"]
        else:
            self.active_model_source = "manual"
            self.is_fallback_active = False
            self._fallback_notice = None

        self.client, self.provider, self.model_name = create_llm_client(self.cfg, prefer_saved_model=True)
        if not self._user_configured_model(self.cfg):
            self.model_name = None
        self.api_key = self.client.api_key
        # 重新预热
        self._warmup_client_async()

    def _warmup_client_async(self):
        """后台线程预热 LLM 连接(首次调用省 1-2s 冷启动)"""
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

    def get_client_for(self, provider: str, model: str, override_key: str = None):
        """获取指定 provider + model 的 LLM 客户端,带缓存

        override_key 优先使用(如 Agent 专属 key)
        """
        from fr_cli.core.llm import create_llm_client_for
        cache_key = (provider, model, override_key)
        cached = self._client_cache.get(cache_key)
        if cached is not None:
            return cached
        client, _, _ = create_llm_client_for(provider, model, self.cfg, override_key)
        self._client_cache[cache_key] = client
        return client

    def resolve_agent_llm(self, agent_name: str) -> Tuple[Any, str, str]:
        """解析 Agent 的 LLM 配置

        优先读取 Agent 的 config.json(专属 provider/model/key),
        若无专属配置则回退到全局默认。

        返回: (client, provider, model)
        """
        from fr_cli.agent.manager import load_agent_config
        agent_cfg = load_agent_config(agent_name)

        provider = agent_cfg.get("provider")
        model = agent_cfg.get("model")
        override_key = agent_cfg.get("key") or None

        # 防御性校验:provider 和 model 必须均为非空字符串才生效
        if (provider and model
                and isinstance(provider, str) and isinstance(model, str)):
            client = self.get_client_for(provider, model, override_key)
            return client, provider, model

        # 回退到全局默认
        return self.client, self.provider, self.model_name
