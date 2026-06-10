"""
注册表分组：会话管理 / 配置管理 / 其他
- save_session / list_sessions / export_session / delete_session
- set_model / set_key / set_limit / set_lang / set_alias
- undo / list_plugins / update_check / update_run
- open_file / launch_app / list_apps
- debug / why
"""
from fr_cli.command.registry import register, _TRIGGERS_SESSION, _TRIGGERS_CONFIG


# ============== 会话管理 ==============

@register(
    name="save_session",
    triggers=_TRIGGERS_SESSION,
    description="保存会话",
    params={"name": str},
    aliases=["/save"],
    needs_msgs=True,
)
def _save_session(deps, msgs=None, **kwargs):
    from fr_cli.memory.history import save_sess
    from fr_cli.conf.config import save_config
    from fr_cli.lang.i18n import T
    sn = kwargs["name"]
    deps.cfg["session_name"] = sn
    save_config(deps.cfg)
    if save_sess(sn, msgs):
        return T('ok_sess_save', deps.lang, sn), None
    return None, "Save failed"


@register(
    name="list_sessions",
    triggers=_TRIGGERS_SESSION,
    description="列出会话",
    params={},
    aliases=["/load"],
)
def _list_sessions(deps, **kwargs):
    from fr_cli.memory.history import get_sessions
    from fr_cli.lang.i18n import T
    ss = get_sessions()
    if not ss:
        return None, T("no_sess", deps.lang)
    return "\n".join([f"[{i}] {s['name']}" for i, s in enumerate(ss)]), None


@register(
    name="export_session",
    triggers=_TRIGGERS_SESSION,
    description="导出会话",
    params={},
    aliases=["/export"],
    needs_msgs=True,
)
def _export_session(deps, msgs=None, **kwargs):
    from fr_cli.memory.history import export_md
    from fr_cli.lang.i18n import T
    out_dir = deps.vfs.cwd if deps.vfs else None
    ok, path = export_md(msgs, deps.lang, out_dir)
    return (T('ok_export', deps.lang, path), None) if ok else (None, "Export failed")


@register(
    name="delete_session",
    description="删除会话",
    params={"id": str},
    aliases=["/del"],
)
def _delete_session(deps, **kwargs):
    from fr_cli.memory.history import get_sessions, del_sess
    from fr_cli.lang.i18n import T
    ss = get_sessions()
    if not ss:
        return None, T("no_sess", deps.lang)
    sid = kwargs.get("id", "")
    if sid and sid.isdigit():
        idx = int(sid)
    else:
        idx = 0
    ok = del_sess(idx)
    return (T('ok_sess_del', deps.lang), None) if ok else (None, "Delete failed")


# ============== 配置管理 ==============

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


# ============== 其他 ==============

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


# ============== 本地应用启动器 ==============

@register(
    name="open_file",
    triggers=["打开", "open", "启动", "launch", "浏览", "播放", "查看"],
    description="用系统默认程序打开文件或 URL",
    params={"path": str},
    aliases=["/open"],
)
def _open_file(deps, **kwargs):
    from fr_cli.weapon.launcher import open_file
    ok, msg = open_file(kwargs["path"], deps.lang)
    return (msg, None) if ok else (None, msg)


@register(
    name="launch_app",
    triggers=["打开应用", "启动程序", "运行软件", "launch app", "打开微信", "打开浏览器", "打开 Word", "打开 Excel"],
    description="启动指定应用程序，可带文件或 URL 参数",
    params={"name": str},
    aliases=["/launch"],
)
def _launch_app(deps, **kwargs):
    from fr_cli.weapon.launcher import launch_app
    ok, msg = launch_app(kwargs["name"], kwargs.get("target"), deps.lang)
    return (msg, None) if ok else (None, msg)


@register(
    name="list_apps",
    description="列出本机可用应用别名",
    params={},
    aliases=["/apps"],
)
def _list_apps(deps, **kwargs):
    from fr_cli.weapon.launcher import list_apps
    res, err = list_apps(deps.lang)
    return (res, None) if not err else (None, err)


# ============== 调试 / 诊断 ==============

@register(
    name="debug",
    description="切换调试模式：显示完整 traceback、详细日志",
    params={},
    aliases=["/debug"],
)
def _debug(deps, **kwargs):
    from fr_cli.core.errors import is_debug, set_debug
    on = not is_debug()
    set_debug(on)
    state = "开" if on else "关"
    return f"🔧 调试模式：{state}\n   错误日志：~/.fr_cli/logs/errors.log", None


@register(
    name="why",
    description="解释 AI 上一步为什么这么做（基于历史 tool call）",
    params={},
    aliases=["/why"],
)
def _why(deps, **kwargs):
    """从最近一次 AI 回复中提取工具调用并展示"""
    return (
        f"💡 /why 命令占位\n"
        f"   查看完整 trace：~/.fr_cli/logs/errors.log\n"
        f"   编辑上一条 AI 回答：按 e 键\n"
        f"   重试上一条：按 r 键\n"
        f"   撤销：按 u 键"
    ), None