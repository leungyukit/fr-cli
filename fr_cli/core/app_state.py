"""
AppState —— 全局状态容器(组合 5 个 mixin)

把 fr_cli/core/core.py 中的 649 行 AppState 拆成:
- fr_cli/core/app_state_core.py    __init__ + display + bootstrap
- fr_cli/core/app_state_config.py   update_* + save_cfg
- fr_cli/core/app_state_client.py   reinit_client + get_client_for + resolve_agent_llm
- fr_cli/core/app_state_services.py start_all_services + _sync_gatekeeper_config
- fr_cli/core/app_state_status.py   status_summary + _master_failure_patterns

向后兼容:
- from fr_cli.core.core import AppState 仍然工作(re-export)
- 所有方法和属性保持不变

设计原则(参考 MasterAgent 的 mixin 拆分):
- 每个 mixin 单一职责,文件 < 200 行
- 共享初始化通过 AppState.__init__ 委托给 _init_core,避免 mixin __init__ 冲突
- 锁、状态等通过 self._lock / self.cfg 共享
"""
from __future__ import annotations

from typing import Any, Dict

from fr_cli.core.app_state_client import AppStateClientMixin
from fr_cli.core.app_state_config import AppStateConfigMixin
from fr_cli.core.app_state_core import AppStateCoreMixin
from fr_cli.core.app_state_services import AppStateServicesMixin
from fr_cli.core.app_state_status import AppStateStatusMixin


class AppState(
    AppStateCoreMixin,
    AppStateConfigMixin,
    AppStateClientMixin,
    AppStateServicesMixin,
    AppStateStatusMixin,
):
    """应用程序运行时状态容器

    组成:
      - CoreMixin:初始化子系统 + 显示属性 + 启动钩子
      - ConfigMixin:update_* 系列(更新 / 持久化 / 重 init client)
      - ClientMixin:reinit_client / get_client_for / resolve_agent_llm
      - ServicesMixin:start_all_services / _sync_gatekeeper_config
      - StatusMixin:status_summary(聚合所有可查询状态)
    """

    def __init__(self, cfg: Dict[str, Any]):
        # 把所有初始化逻辑委托给 core mixin 的 _init_core
        self._init_core(cfg)


__all__ = ["AppState"]
