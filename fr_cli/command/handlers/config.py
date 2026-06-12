"""命令处理器 —— config"""

from fr_cli.command.registry import register, _TRIGGERS_CONFIG

@register(
    name="undo",
    description="撤销最后一条对话（或 /undo N 撤销 N 轮）",
    params={},
    aliases=["/undo", "/u"],
)
def _undo_cmd(deps, **kwargs):
    return "💡 /undo 由 main.py 路由处理", None


@register(
    name="set_model",
    triggers=_TRIGGERS_CONFIG,
    description="切换模型",
    params={"name": str},
    aliases=["/model"],
)
def _set_model(deps, **kwargs):
    from fr_cli.conf.config import save_config
    from fr_cli.lang.i18n import T
    deps.cfg["model"] = kwargs["name"]
    deps.model_name = kwargs["name"]
    save_config(deps.cfg)
    return T('ok_model', deps.lang, kwargs["name"]), None


@register(
    name="set_key",
    triggers=_TRIGGERS_CONFIG,
    description="设置API密钥",
    params={"key": str},
    aliases=["/key"],
)
def _set_key(deps, **kwargs):
    from fr_cli.conf.config import save_config
    from fr_cli.lang.i18n import T
    deps.cfg["key"] = kwargs["key"]
    save_config(deps.cfg)
    return T('ok_key', deps.lang), None


@register(
    name="set_limit",
    triggers=_TRIGGERS_CONFIG,
    description="设置Token上限",
    params={"limit": int},
    aliases=["/limit"],
)
def _set_limit(deps, **kwargs):
    from fr_cli.conf.config import save_config
    from fr_cli.lang.i18n import T
    lim = int(kwargs["limit"])
    if lim < 1000:
        return None, T('err_limit', deps.lang)
    deps.cfg["limit"] = lim
    save_config(deps.cfg)
    return T('ok_limit', deps.lang, lim), None


@register(
    name="set_lang",
    triggers=_TRIGGERS_CONFIG,
    description="切换语言",
    params={"code": str},
    aliases=["/lang"],
)
def _set_lang(deps, **kwargs):
    from fr_cli.conf.config import save_config
    lc = kwargs["code"]
    if lc in ['zh', 'en']:
        deps.cfg["lang"] = lc
        deps.lang = lc
        save_config(deps.cfg)
        return f"Language changed to {lc}", None
    return None, "Invalid language. Use zh or en"


@register(
    name="set_alias",
    description="设置命令别名",
    params={"key": str, "value": str},
    aliases=["/alias"],
)
def _set_alias(deps, **kwargs):
    from fr_cli.conf.config import save_config
    from fr_cli.lang.i18n import T
    k, v = kwargs["key"], kwargs.get("value", "")
    if v:
        aliases = deps.cfg.get("aliases", {})
        aliases[k] = v
        deps.cfg["aliases"] = aliases
        save_config(deps.cfg)
        return T('ok_alias_set', deps.lang, k, v), None
    val = deps.cfg.get("aliases", {}).get(k, "")
    return val if val else T("no_alias", deps.lang), None


# ------------------------------------------------------------------


@register(
    name="undo",
    description="撤销最近一轮对话",
    params={},
    aliases=["/undo"],
    needs_msgs=True,
)
def _undo(deps, msgs=None, **kwargs):
    from fr_cli.lang.i18n import T
    if len(msgs) > 1 and msgs[-1]["role"] == "assistant":
        msgs.pop()
        return T('ok_undo', deps.lang), None
    if len(msgs) > 1 and msgs[-1]["role"] == "user":
        msgs.pop()
        return T('ok_undo', deps.lang), None
    return None, T('err_undo', deps.lang)


@register(
    name="list_plugins",
    description="列出已安装插件",
    params={},
    aliases=["/skills"],
)
def _list_plugins(deps, **kwargs):
    from fr_cli.lang.i18n import T
    if not deps.plugins:
        return None, T("no_plugins", deps.lang)
    return "\n".join([f"/{k}" for k in deps.plugins.keys()]), None


@register(
    name="update_check",
    description="检查更新",
    params={},
    aliases=["/update_check"],
)
def _update_check(deps, **kwargs):
    from fr_cli.breakthrough.update import update_check
    ok, info, err = update_check(verbose=False)
    if err:
        return None, f"检查失败: {err}"
    if not ok:
        return "当前已是最新版本。", None
    ver = info.get("version", "?")
    note = info.get("release_note", "")
    return f"发现新版本: {ver}\n{note}", None


@register(
    name="update_run",
    description="执行更新",
    params={},
    aliases=["/update_run"],
)
def _update_run(deps, **kwargs):
    from fr_cli.breakthrough.update import update_and_restart
    ok, msg = update_and_restart(verbose=True, allow_restart=True)
    return (msg, None) if ok else (None, msg)


# ------------------------------------------------------------------

