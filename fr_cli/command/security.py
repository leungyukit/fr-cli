"""
四阶安全确认管理器
将安全状态从 main.py 的闭包中提取为可复用的类

v2.4.4 行为变更：
- fconfirm / sconfirm 改为 dict，按 sec_* 类别独立
- 提供 unconfirm_all() 方法供 /unconfirm 命令使用

v2.5.1 行为变更：
- 新增 autonomous_mode 分级：manual / sandbox_auto / full_auto
- sandbox_auto 下自动放行沙盒内操作，系统级操作仍确认

v2.8.7 行为变更：
- 引入可注入的确认策略层（fr_cli.security.strategy）。
  本类不再自己实现 Y/A/F/N 交互，改为持有 strategy 并委托。
  新增 set_strategy()，bot / 服务端进程可在运行时换成
  CallbackStrategy（把确认问题发回聊天窗口）或 AutoDenyStrategy。
  默认策略与 v2.8.6 行为完全一致（TerminalStrategy）。
"""
import copy
import os
from typing import Any, Dict, Optional

from fr_cli.ui.ui import DIM, RESET, print_styled
from fr_cli.security.security import clear_all_auto_confirm, _migrate_fconfirm
from fr_cli.security.permissions import PermissionManager
from fr_cli.security.policy import (
    SANDBOX_SECURITY_KEYS,
    normalize_autonomous_mode,
)
from fr_cli.security.strategy import ConfirmStrategy, TerminalStrategy


class SecurityManager:
    """
    封装安全确认状态（Y/A/F/N）
    - fconfirm: 永久放行（dict，key 为 sec_* 类别名）
    - sconfirm: 本次会话放行（dict 或 bool）
    - autonomous_mode: manual / sandbox_auto / full_auto
    - strategy: 可注入的确认策略（v2.8.7+）
    """
    def __init__(self, lang, cfg, strategy: ConfirmStrategy = None):
        self.lang = lang
        self.cfg = cfg
        # 迁移旧版 auto_confirm_forever bool → 新版 auto_confirm dict
        legacy = cfg.get("auto_confirm_forever", False)
        if isinstance(legacy, bool) and legacy:
            # 旧版一键放行迁移：写入新版 dict 并保存一次
            fconfirm = _migrate_fconfirm(legacy)
            cfg["auto_confirm"] = dict(fconfirm)
            self.fconfirm = fconfirm
            from fr_cli.conf.config import save_config
            save_config(cfg)
        else:
            self.fconfirm = cfg.get("auto_confirm", {})
        self.sconfirm = {}  # 本次会话放行（按类别），不持久化
        self.autonomous_mode = normalize_autonomous_mode(cfg.get("autonomous_mode", "manual"))
        self._auto_echoed = set()  # 避免重复打印自动放行提示
        # v2.8.7：确认策略（默认终端交互，保持既有行为）
        self.strategy = strategy or TerminalStrategy(lang=lang, config=cfg)
        self.strategy.fconfirm = dict(self.fconfirm)
        self.strategy.sconfirm = dict(self.sconfirm)
        # tool 级权限（config.permissions）—— 懒加载，cfg 变化时自动重建
        self._permission_manager: Optional[PermissionManager] = None
        self._permission_src: Optional[Dict[str, Any]] = None

    # ---------- 策略注入 ----------

    def set_strategy(self, strategy: ConfirmStrategy) -> None:
        """替换确认策略（bot / 服务端场景）。"""
        self.strategy = strategy
        # 把当前放行状态带过去，避免语义断裂
        strategy.fconfirm = dict(self.fconfirm)
        strategy.sconfirm = dict(self.sconfirm)
        if strategy.config is not self.cfg:
            strategy.config = self.cfg

    # ---------- tool 级权限（config.permissions）----------

    def _permissions(self) -> PermissionManager:
        """懒加载 PermissionManager；cfg 中的权限发生变化时自动重建。"""
        raw = (self.cfg or {}).get("permissions") or {}
        snapshot = copy.deepcopy(raw)
        if self._permission_manager is None or snapshot != self._permission_src:
            self._permission_manager = PermissionManager(raw)
            self._permission_src = snapshot
        return self._permission_manager

    def check_tool_permission(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> Optional[bool]:
        """tool 级权限判定（薄封装）。

        Returns:
            True  = 允许（无需确认）
            False = 拒绝
            None  = 未命中 tool 级规则（走 sec_* 正常流程）
        """
        decision = self.permission_decision(tool_name, args)
        if decision == "allow":
            return True
        if decision == "deny":
            return False
        return None

    def permission_decision(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> str:
        """tool 级权限的原始决策（四态）。

        Returns:
            "allow" / "deny" / "ask" / "fallthrough"
        """
        try:
            return self._permissions().check_tool(tool_name, args or {})
        except Exception:
            return "fallthrough"

    # ---------- 状态同步 ----------

    def _sync_from_strategy(self):
        """把策略内部状态同步回本对象（保持向后兼容的 fconfirm/sconfirm 属性）。"""
        self.fconfirm = dict(getattr(self.strategy, "fconfirm", {}) or {})
        self.sconfirm = dict(getattr(self.strategy, "sconfirm", {}) or {})
        # 永久放行可能被策略更新过（如 F 选项），同步回 cfg
        # 注意：空集合时不写入，避免给 config.json 塞一个空的 auto_confirm 键
        if self.fconfirm:
            if self.cfg.get("auto_confirm") != self.fconfirm:
                self.cfg["auto_confirm"] = dict(self.fconfirm)
                self.cfg.pop("auto_confirm_forever", None)
        elif "auto_confirm" in self.cfg:
            self.cfg.pop("auto_confirm", None)
            self.cfg.pop("auto_confirm_forever", None)

    def _effective_mode(self) -> str:
        """环境变量可单次覆盖配置中的 autonomous_mode"""
        return normalize_autonomous_mode(os.environ.get("FR_CLI_AUTONOMOUS_MODE", self.autonomous_mode))

    def check(self, k, d, tool_name="", args=None):
        """
        执行安全确认检查
        :param k: 操作类型键名 (如 sec_read, sec_exec)
        :param d: 具体操作描述
        :param tool_name: 工具名（v2.8.7+，供 tool 级权限与策略决策使用）
        :param args: 工具参数（v2.8.7+，供 path_rules 使用）
        :return: bool 是否放行
        """
        mode = self._effective_mode()

        # full_auto：所有 sec_* 自动放行（危险，等价于永久 F）
        if mode == "full_auto":
            return True

        # sandbox_auto：仅沙盒内操作自动放行
        if mode == "sandbox_auto" and k in SANDBOX_SECURITY_KEYS:
            if k not in self._auto_echoed:
                # 同 security.ask: 代理期裸打色会泄漏 ?[2m, 走 print_styled
                print_styled(f"{DIM}自动放行沙盒操作: {k} ({d}){RESET}")
                self._auto_echoed.add(k)
            return True

        # 其余情况交给确认策略（默认 TerminalStrategy = 原有 Y/A/F/N 流程）
        decision = self.strategy.check(k, d, tool_name=tool_name, args=args)
        self._sync_from_strategy()
        return bool(decision)

    def set_autonomous_mode(self, mode: str) -> bool:
        """设置并持久化自治模式"""
        mode = normalize_autonomous_mode(mode)
        self.autonomous_mode = mode
        self.cfg["autonomous_mode"] = mode
        from fr_cli.conf.config import save_config
        return save_config(self.cfg)

    def unconfirm_all(self):
        """撤销所有 sec_* 类别的永久放行（/unconfirm 命令入口）"""
        clear_all_auto_confirm(self.cfg)
        self.fconfirm = {}
        self.sconfirm = {}
        try:
            self.strategy.clear_all()
        except Exception:
            pass
