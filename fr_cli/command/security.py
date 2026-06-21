"""
四阶安全确认管理器
将安全状态从 main.py 的闭包中提取为可复用的类

v2.4.4 行为变更：
- fconfirm / sconfirm 改为 dict，按 sec_* 类别独立
- 提供 unconfirm_all() 方法供 /unconfirm 命令使用

v2.5.1 行为变更：
- 新增 autonomous_mode 分级：manual / sandbox_auto / full_auto
- sandbox_auto 下自动放行沙盒内操作，系统级操作仍确认
"""
import os

from fr_cli.ui.ui import DIM, RESET
from fr_cli.security.security import ask, clear_all_auto_confirm, _migrate_fconfirm
from fr_cli.security.policy import (
    SANDBOX_SECURITY_KEYS,
    normalize_autonomous_mode,
)


class SecurityManager:
    """
    封装安全确认状态（Y/A/F/N）
    - fconfirm: 永久放行（dict，key 为 sec_* 类别名）
    - sconfirm: 本次会话放行（dict 或 bool）
    - autonomous_mode: manual / sandbox_auto / full_auto
    """
    def __init__(self, lang, cfg):
        self.lang = lang
        self.cfg = cfg
        # 迁移旧版 auto_confirm_forever bool → 新版 auto_confirm dict
        legacy = cfg.get("auto_confirm_forever", False)
        if isinstance(legacy, bool) and legacy:
            # 旧版一键放行迁移：写入新版 dict 并保存一次
            fconfirm = _migrate_fconfirm(legacy)
            cfg["auto_confirm"] = dict(fconfirm)
            if "auto_confirm_forever" in cfg:
                del cfg["auto_confirm_forever"]
            from fr_cli.conf.config import save_config
            save_config(cfg)
        else:
            fconfirm = cfg.get("auto_confirm", {})
        self.fconfirm = fconfirm
        self.sconfirm = {}  # 本次会话放行（按类别），不持久化
        self.autonomous_mode = normalize_autonomous_mode(cfg.get("autonomous_mode", "manual"))
        self._auto_echoed = set()  # 避免重复打印自动放行提示

    def _effective_mode(self) -> str:
        """环境变量可单次覆盖配置中的 autonomous_mode"""
        return normalize_autonomous_mode(os.environ.get("FR_CLI_AUTONOMOUS_MODE", self.autonomous_mode))

    def check(self, k, d):
        """
        执行安全确认检查
        :param k: 操作类型键名 (如 sec_read, sec_exec)
        :param d: 具体操作描述
        :return: bool 是否放行
        """
        mode = self._effective_mode()

        # full_auto：所有 sec_* 自动放行（危险，等价于永久 F）
        if mode == "full_auto":
            return True

        # sandbox_auto：仅沙盒内操作自动放行
        if mode == "sandbox_auto" and k in SANDBOX_SECURITY_KEYS:
            if k not in self._auto_echoed:
                print(f"{DIM}🤖 自动放行沙盒操作: {k} ({d}){RESET}")
                self._auto_echoed.add(k)
            return True

        # 其余情况走原有 Y/A/F/N 流程
        allowed, self.sconfirm, self.fconfirm = ask(
            k, d, self.lang, self.fconfirm, self.sconfirm, self.cfg
        )
        # ask() 内部可能更新 cfg["auto_confirm"]，同步 self.fconfirm
        self.fconfirm = self.cfg.get("auto_confirm", self.fconfirm)
        return allowed

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
