"""国际化文本引擎"""

from fr_cli.lang.translations import I18N

def T(k, l="zh", *a):
    """根据键名和语言获取国际化文本，支持格式化参数"""
    t = I18N.get(l, I18N["zh"]).get(k, "")
    return t.format(*a) if a else t
