"""国际化文本引擎"""

from fr_cli.lang.translations import I18N

def T(k, l="zh", *a):
    """根据键名和语言获取国际化文本，支持格式化参数。

    文本中若包含 {{models}} 占位符，会自动替换为当前可用 provider 的默认模型列表。
    """
    t = I18N.get(l, I18N["zh"]).get(k, "")
    if "{{models}}" in t:
        try:
            from fr_cli.core.llm import list_providers
            providers = list_providers()
            models = [p["default_model"] for p in providers if p.get("default_model")]
            if models:
                models_text = ", ".join(models[:8])
                if len(models) > 8:
                    models_text += " ..."
            else:
                models_text = ""
            t = t.replace("{{models}}", models_text)
        except Exception:
            t = t.replace("{{models}}", "")
    return t.format(*a) if a else t
