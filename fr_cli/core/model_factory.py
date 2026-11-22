"""
模型工厂 - 从配置文件加载模型

默认 provider/model/base_url/client 等配置已从 Python 代码中移除，
统一收敛到 fr_cli/conf/default_models.yaml 包内资源与 ~/.fr_cli/models.yaml 用户配置。

加载语义：包内 default_models.yaml 是底座，用户 ~/.fr_cli/models.yaml 覆盖在其上
（用户字段优先、内置补缺）。用户文件写得不全不会再把内置厂商目录整体遮蔽掉。
"""

import json
import yaml
import importlib.resources as resources
from typing import Dict, Optional

from fr_cli.conf.paths import MODELS_YAML


# 顶层非 provider 键：旧版嵌套格式里的 settings 段，合并时必须跳过，
# 否则会被当成一个 provider 混进厂商列表。
NON_PROVIDER_KEYS = frozenset({"settings", "providers"})

# 旧 schema → 当前 schema 的字段名映射（加载时幂等升级）
LEGACY_FIELD_ALIASES = {
    "protocol": "compat",      # protocol(旧) → compat(新)
}


class ModelFactory:
    """模型工厂 - 从配置文件加载并创建模型"""

    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load_config(self, config_path: str = None):
        """从配置文件加载模型配置。

        合并语义：包内 default_models.yaml 作为底座，用户 MODELS_YAML 覆盖在其上
        （provider 级 + 字段级深度合并，用户字段优先，内置补缺）。

        这样用户文件只有 3 个 provider 时，不再整体遮蔽内置厂商目录；
        用户独有 provider（如自建的 volcengine-plan）也会被保留。
        """
        if config_path is None:
            config_path = MODELS_YAML

        user_cfg = self._read_config_file(config_path)
        user_cfg = self._normalize_config(user_cfg)
        builtin_cfg = self._get_default_config()
        self._config = self._merge_configs(builtin_cfg, user_cfg)
        return self

    @staticmethod
    def _read_config_file(config_path):
        """读取用户配置文件。

        不存在 / 损坏 / 内容非 dict 时返回 {} —— 由 _merge_configs 用内置目录兜底，
        不再走 _get_default_config 的“最小兜底”分支（那会丢掉大部分内置厂商）。
        """
        from pathlib import Path
        p = Path(config_path)
        if not p.exists():
            return {}
        try:
            with open(p, "r", encoding="utf-8") as f:
                # Path.suffix 而不是 str.endswith，避免 PosixPath 无 endswith 的报错
                if p.suffix in (".yaml", ".yml"):
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _normalize_config(cfg):
        """归一化配置为扁平 provider 字典(顶层键即 provider id)。

        兼容旧版嵌套格式:早期 ~/.fr_cli/models.yaml 形如
            providers: {deepseek: {...}, ...}
            settings:   {default_provider: ...}
        不归一化会把 providers/settings 当成两个 provider,
        导致向导列表错乱、default_model=None 进而在格式化时崩溃。
        """
        if not isinstance(cfg, dict):
            return {}
        inner = cfg.get("providers")
        if isinstance(inner, dict) and inner and all(isinstance(v, dict) for v in inner.values()):
            return inner
        return cfg

    @staticmethod
    def _upgrade_entry(entry):
        """把旧 schema 字段名映射到当前 schema（幂等，返回新 dict）"""
        upgraded = dict(entry)
        for legacy, current in LEGACY_FIELD_ALIASES.items():
            if current not in upgraded and upgraded.get(legacy):
                upgraded[current] = upgraded[legacy]
        return upgraded

    @classmethod
    def _merge_configs(cls, builtin, user):
        """以内置目录为底座合并用户配置。

        - 仅内置有：保留内置条目
        - 两边都有：用户字段逐个覆盖，内置字段补缺（用户优先）
        - 仅用户有：原样并入（自建 provider）
        - 顶层非 provider 键（settings 等）与值非 dict 的条目：跳过
        """
        merged = {}
        for pid, cfg in (builtin or {}).items():
            merged[pid] = dict(cfg) if isinstance(cfg, dict) else {}

        for pid, cfg in (user or {}).items():
            if pid in NON_PROVIDER_KEYS or not isinstance(cfg, dict):
                continue
            cfg = cls._upgrade_entry(cfg)
            if pid in merged:
                merged[pid].update(cfg)
            else:
                merged[pid] = cfg
        return merged

    def _get_default_config(self):
        """获取默认配置 —— 从包内 default_models.yaml 加载。

        仅在包内资源缺失或损坏时使用最小兜底配置。
        """
        try:
            ref = resources.files("fr_cli.conf") / "default_models.yaml"
            with ref.open("r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
                if cfg:
                    return cfg
        except Exception:
            pass

        # 最小兜底：确保至少有一个可用 provider
        return {
            "zhipu": {
                "name": "智谱",
                "model": "glm-4-flash",
                "models": ["glm-4-flash", "glm-4-plus", "glm-4", "glm-4v-plus", "glm-4-air", "glm-4-long"],
                "client": "ZhipuLLMClient",
                "base_url": None,
                "token_plan_base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
                "is_token_plan": False,
                "image_model": "cogview-3-plus"
            }
        }

    def create_client(self, provider_id: str, api_key: str):
        """工厂方法：创建模型客户端"""
        config = self._config.get(provider_id)
        if not config:
            raise ValueError(f"Provider {provider_id} not found")

        client_type = config.get("client", "OpenAICompatibleClient")

        from fr_cli.core.llm import ZhipuLLMClient, OpenAICompatibleClient, WenxinLLMClient

        if client_type == "ZhipuLLMClient":
            return ZhipuLLMClient(api_key)
        elif client_type == "OpenAICompatibleClient":
            base_url = config.get("base_url")
            return OpenAICompatibleClient(api_key, base_url)
        elif client_type == "WenxinLLMClient":
            return WenxinLLMClient(api_key)
        else:
            raise ValueError(f"Unknown client type: {client_type}")

    def get_model_name(self, provider_id: str) -> Optional[str]:
        """获取模型名称；未知 provider 返回 None"""
        config = self._config.get(provider_id)
        if not config:
            return None
        return config.get("model")

    def list_providers(self):
        """列出所有 Provider"""
        return list(self._config.keys())

    def get_config(self, provider_id: str) -> Dict:
        """获取 Provider 配置"""
        return self._config.get(provider_id, {})


# 全局工厂实例
_factory = None

def get_model_factory() -> ModelFactory:
    """获取模型工厂实例"""
    global _factory
    if _factory is None:
        _factory = ModelFactory().load_config()
    return _factory


