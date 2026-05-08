"""
四阶安全确认管理器
将安全状态从 main.py 的闭包中提取为可复用的类
"""
from fr_cli.security.security import ask


class SecurityManager:
    """
    封装安全确认状态（Y/A/F/N）
    - fconfirm: 永久放行
    - sconfirm: 本次会话放行
    """
    def __init__(self, lang, cfg):
        self.lang = lang
        self.cfg = cfg
        self.fconfirm = cfg.get("auto_confirm_forever", False)
        self.sconfirm = False

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
        return allowed
