"""命令处理器 —— session"""

from fr_cli.command.registry import register, _TRIGGERS_SESSION

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


# ------------------------------------------------------------------

