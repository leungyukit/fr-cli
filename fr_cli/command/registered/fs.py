"""
注册表分组：文件系统类工具
- write_file / read_file / list_files / change_dir / append_file / delete_file

为了让 registry.py 瘦身，所有 @register 调用按类目拆分到独立模块。
fr_cli/command/registry.py 只保留核心调度逻辑。
"""
from fr_cli.command.registry import register, _TRIGGERS_FILE


@register(
    name="write_file",
    triggers=_TRIGGERS_FILE,
    description="写入文件",
    params={"path": str, "content": str},
    security="sec_write",
    aliases=["/write"],
)
def _write_file(deps, **kwargs):
    ok, msg = deps.vfs.write(kwargs["path"], kwargs["content"], deps.lang)
    return (msg, None) if ok else (None, msg)


@register(
    name="read_file",
    triggers=_TRIGGERS_FILE,
    description="读取文件",
    params={"path": str},
    security="sec_read",
    aliases=["/cat"],
)
def _read_file(deps, **kwargs):
    txt, err = deps.vfs.read(kwargs["path"], deps.lang)
    return (txt, None) if not err else (None, err)


@register(
    name="list_files",
    triggers=_TRIGGERS_FILE,
    description="列出文件",
    params={},
    aliases=["/ls"],
)
def _list_files(deps, **kwargs):
    items, err = deps.vfs.ls(deps.lang)
    return ("\n".join(items), None) if not err else (None, err)


@register(
    name="change_dir",
    triggers=_TRIGGERS_FILE,
    description="切换目录",
    params={"path": str},
    aliases=["/cd"],
)
def _change_dir(deps, **kwargs):
    ok, msg = deps.vfs.cd(kwargs["path"], deps.lang)
    return (msg, None) if ok else (None, msg)


@register(
    name="append_file",
    triggers=_TRIGGERS_FILE,
    description="追加文件",
    params={"path": str, "content": str},
    security="sec_write",
    aliases=["/append"],
)
def _append_file(deps, **kwargs):
    ok, msg = deps.vfs.append(kwargs["path"], kwargs["content"], deps.lang)
    return (msg, None) if ok else (None, msg)


@register(
    name="delete_file",
    triggers=_TRIGGERS_FILE,
    description="删除文件",
    params={"path": str},
    security="sec_write",
    aliases=["/delete"],
)
def _delete_file(deps, **kwargs):
    ok, msg = deps.vfs.delete(kwargs["path"], deps.lang)
    return (msg, None) if ok else (None, msg)