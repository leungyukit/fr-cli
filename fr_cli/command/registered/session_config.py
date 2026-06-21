"""
注册表分组：会话管理 / 配置管理 / 其他
- save_session / list_sessions / export_session / delete_session
- set_model / set_key / set_limit / set_lang / set_alias
- undo / list_plugins / update_check / update_run
- open_file / launch_app / list_apps
- debug / why
"""
from fr_cli.command.registry import register, _TRIGGERS_SESSION, _TRIGGERS_CONFIG
from fr_cli.core.result import Result


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
        return Result.ok(T('ok_sess_save', deps.lang, sn))
    return Result.fail("Save failed")


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
        return Result.fail(T("no_sess", deps.lang))
    return Result.ok("\n".join([f"[{i}] {s['name']}" for i, s in enumerate(ss)]))


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
    return Result.ok(T('ok_export', deps.lang, path)) if ok else Result.fail("Export failed")


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
        return Result.fail(T("no_sess", deps.lang))
    sid = kwargs.get("id", "")
    if sid and sid.isdigit():
        idx = int(sid)
    else:
        idx = 0
    ok = del_sess(idx)
    return Result.ok(T('ok_sess_del', deps.lang)) if ok else Result.fail("Delete failed")


# ============== 配置管理 ==============

@register(
    name="set_model",
    triggers=_TRIGGERS_CONFIG,
    description="切换模型",
    params={"name": str},
    security="sec_set_model",
    aliases=["/model"],
)
def _set_model(deps, **kwargs):
    from fr_cli.conf.config import save_config
    from fr_cli.lang.i18n import T
    deps.cfg["model"] = kwargs["name"]
    deps.model_name = kwargs["name"]
    save_config(deps.cfg)
    return Result.ok(T('ok_model', deps.lang, kwargs["name"]))


@register(
    name="set_key",
    triggers=_TRIGGERS_CONFIG,
    description="设置API密钥",
    params={"key": str},
    security="sec_set_key",
    aliases=["/key"],
)
def _set_key(deps, **kwargs):
    from fr_cli.conf.config import save_config
    from fr_cli.lang.i18n import T
    deps.cfg["key"] = kwargs["key"]
    save_config(deps.cfg)
    return Result.ok(T('ok_key', deps.lang))


@register(
    name="set_limit",
    triggers=_TRIGGERS_CONFIG,
    description="设置Token上限",
    params={"limit": int},
    security="sec_set_limit",
    aliases=["/limit"],
)
def _set_limit(deps, **kwargs):
    from fr_cli.conf.config import save_config
    from fr_cli.lang.i18n import T
    lim = int(kwargs["limit"])
    if lim < 1000:
        return Result.fail(T('err_limit', deps.lang))
    deps.cfg["limit"] = lim
    save_config(deps.cfg)
    return Result.ok(T('ok_limit', deps.lang, lim))


@register(
    name="set_lang",
    triggers=_TRIGGERS_CONFIG,
    description="切换语言",
    params={"code": str},
    security="sec_set_lang",
    aliases=["/lang"],
)
def _set_lang(deps, **kwargs):
    from fr_cli.conf.config import save_config
    lc = kwargs["code"]
    if lc in ['zh', 'en']:
        deps.cfg["lang"] = lc
        deps.lang = lc
        save_config(deps.cfg)
        return Result.ok(f"Language changed to {lc}")
    return Result.fail("Invalid language. Use zh or en")


@register(
    name="set_alias",
    description="设置命令别名",
    params={"key": str, "value": str},
    security="sec_set_alias",
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
        return Result.ok(T('ok_alias_set', deps.lang, k, v))
    val = deps.cfg.get("aliases", {}).get(k, "")
    return Result.ok(val if val else T("no_alias", deps.lang))


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
        return Result.ok(T('ok_undo', deps.lang))
    if len(msgs) > 1 and msgs[-1]["role"] == "user":
        msgs.pop()
        return Result.ok(T('ok_undo', deps.lang))
    return Result.fail(T('err_undo', deps.lang))


@register(
    name="list_plugins",
    description="列出已安装插件",
    params={},
    aliases=["/skills"],
)
def _list_plugins(deps, **kwargs):
    from fr_cli.lang.i18n import T
    if not deps.plugins:
        return Result.fail(T("no_plugins", deps.lang))
    return Result.ok("\n".join([f"/{k}" for k in deps.plugins.keys()]))


@register(
    name="update_check",
    description="检查更新",
    params={},
    aliases=["/update_check"],
)
def _update_check(deps, **kwargs):
    from fr_cli.breakthrough.update import update_check
    chk = update_check(verbose=False)
    if chk.is_fail():
        return Result.fail(f"检查失败: {chk.error}")
    has, info = chk.unwrap()
    if not has:
        return Result.ok("当前已是最新版本。")
    ver = info.get("version", "?")
    note = info.get("release_note", "")
    return Result.ok(f"发现新版本: {ver}\n{note}")


@register(
    name="update_run",
    description="执行更新",
    params={},
    security="sec_update",
    aliases=["/update_run"],
)
def _update_run(deps, **kwargs):
    from fr_cli.breakthrough.update import update_and_restart
    return update_and_restart(verbose=True, allow_restart=True)


# ============== 本地应用启动器 ==============

@register(
    name="open_file",
    triggers=["打开", "open", "启动", "launch", "浏览", "播放", "查看"],
    description="用系统默认程序打开文件或 URL",
    params={"path": str},
    security="sec_open_file",
    aliases=["/open"],
)
def _open_file(deps, **kwargs):
    from fr_cli.weapon.launcher import open_file
    return Result.from_tuple(*open_file(kwargs["path"], deps.lang))


@register(
    name="launch_app",
    triggers=["打开应用", "启动程序", "运行软件", "launch app", "打开微信", "打开浏览器", "打开 Word", "打开 Excel"],
    description="启动指定应用程序，可带文件或 URL 参数",
    params={"name": str},
    security="sec_launch_app",
    aliases=["/launch"],
)
def _launch_app(deps, **kwargs):
    from fr_cli.weapon.launcher import launch_app
    return Result.from_tuple(*launch_app(kwargs["name"], kwargs.get("target"), deps.lang))


@register(
    name="list_apps",
    description="列出本机可用应用别名",
    params={},
    aliases=["/apps"],
)
def _list_apps(deps, **kwargs):
    from fr_cli.weapon.launcher import list_apps
    return Result.from_tuple(*list_apps(deps.lang))


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
    return Result.ok(f"🔧 调试模式：{state}\n   错误日志：~/.fr_cli/logs/errors.log")


@register(
    name="why",
    description="解释 AI 上一步为什么这么做（基于历史 tool call）",
    params={},
    aliases=["/why"],
)
def _why(deps, **kwargs):
    """从最近一次 AI 回复中提取工具调用并展示"""
    return Result.ok(
        "💡 /why 命令占位\n"
        "   查看完整 trace：~/.fr_cli/logs/errors.log\n"
        "   编辑上一条 AI 回答：按 e 键\n"
        "   重试上一条：按 r 键\n"
        "   撤销：按 u 键"
    )


# ============== 安全 ==============

@register(
    name="unconfirm",
    description="撤销所有 sec_* 类别的永久放行（清除 auto_confirm 字典）",
    params={},
    aliases=["/unconfirm"],
)
def _unconfirm(deps, **kwargs):
    """撤销所有永久放行：清除 cfg["auto_confirm"] 字典，下次 sec_* 操作恢复确认。

    配套：用户在四阶确认中按 F 仅永久放行当前 sec_* 类别，不再波及其他类别。
    查看当前生效的永久放行：`/unconfirm --show` 或 `fr_cli.conf.config.load_config()`。
    """
    from fr_cli.lang.i18n import T
    existing = deps.cfg.get("auto_confirm", {})
    if not existing and not deps.cfg.get("auto_confirm_forever", False):
        return Result.ok(T("unconfirm_none", deps.lang) if T("unconfirm_none", deps.lang) else "无永久放行需要撤销。")

    # 展示当前被永久放行的类别
    categories = ", ".join(sorted(existing.keys())) if existing else "(legacy: auto_confirm_forever=True)"
    deps.security.unconfirm_all()
    return Result.ok(
        f"✅ 已撤销所有永久放行（共 {len(existing)} 个类别：{categories}）\n"
        f"   下次 sec_* 操作将重新弹窗确认。"
    )
