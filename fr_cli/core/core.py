"""
全局状态管理容器 (AppState) —— 向后兼容 re-export

v3.0+ 重构说明:
- AppState 拆为 5 个 mixin(详见 fr_cli/core/app_state_*.py)
- 老的 `from fr_cli.core.core import AppState` 仍兼容
- 公共 API(方法 / 属性)完全不变

详细模块划分:
  - app_state_core.py    __init__ + display + bootstrap
  - app_state_config.py   update_* + save_cfg
  - app_state_client.py   reinit_client + get_client_for + resolve_agent_llm
  - app_state_services.py start_all_services + _sync_gatekeeper_config
  - app_state_status.py   status_summary + _master_failure_patterns
"""
from fr_cli.core.app_state import AppState

__all__ = ["AppState"]
