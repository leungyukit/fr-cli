"""
四阶安全确认管理器
将安全状态从 main.py 的闭包中提取为可复用的类

v2.4.4 行为变更：
- fconfirm / sconfirm 改为 dict，按 sec_* 类别独立
- 提供 unconfirm_all() 方法供 /unconfirm 命令使用
"""
from fr_cli.security.security import ask, clear_all_auto_confirm, _migrate_fconfirm


class SecurityManager:
    """
    封装安全确认状态（Y/A/F/N）
    - fconfirm: 永久放行（dict，key 为 sec_* 类别名）
    - sconfirm: 本次会话放行（dict 或 bool）
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

    def check(self, k, d):
        """
        执行安全确认检查
        :param k: 操作类型键名 (如 sec_read, sec_exec)
        :param d: 具体操作描述
        :return: bool 是否放行
        """
        allowed, self.sconfirm, self.fconfirm = ask(
            k, d, self.lang, self.fconfirm, self.sconfirm, self.cfg
        )
        # ask() 内部可能更新 cfg["auto_confirm"]，同步 self.fconfirm
        self.fconfirm = self.cfg.get("auto_confirm", self.fconfirm)
        return allowed

    def unconfirm_all(self):
        """撤销所有 sec_* 类别的永久放行（/unconfirm 命令入口）"""
        clear_all_auto_confirm(self.cfg)
        self.fconfirm = {}
