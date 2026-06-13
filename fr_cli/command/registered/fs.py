"""
注册表分组：文件系统类工具
- write_file / read_file / list_files / change_dir / append_file / delete_file

为了让 registry.py 瘦身，所有 @register 调用按类目拆分到独立模块。
fr_cli/command/registry.py 只保留核心调度逻辑。
"""
from fr_cli.command.registry import register, _TRIGGERS_FILE
from fr_cli.core.result import Result


@register(
    name="write_file",
    triggers=_TRIGGERS_FILE,
    description="写入文件",
    params={"path": str, "content": str},
    security="sec_write",
    aliases=["/write"],
)
def _write_file(deps, **kwargs):
    result = deps.vfs.write(kwargs["path"], kwargs["content"], deps.lang)
    return result


@register(
    name="read_file",
    triggers=_TRIGGERS_FILE,
    description="读取文件",
    params={"path": str},
    security="sec_read",
    aliases=["/cat"],
)
def _read_file(deps, **kwargs):
    result = deps.vfs.read(kwargs["path"], deps.lang)
    return result


@register(
    name="list_files",
    triggers=_TRIGGERS_FILE,
    description="列出文件",
    params={},
    aliases=["/ls"],
)
def _list_files(deps, **kwargs):
    result = deps.vfs.ls(deps.lang)
    return Result.ok("\n".join(result.unwrap())) if result.is_ok() else Result.fail(result.error)


@register(
    name="change_dir",
    triggers=_TRIGGERS_FILE,
    description="切换目录",
    params={"path": str},
    aliases=["/cd"],
)
def _change_dir(deps, **kwargs):
    result = deps.vfs.cd(kwargs["path"], deps.lang)
    return result


@register(
    name="append_file",
    triggers=_TRIGGERS_FILE,
    description="追加文件",
    params={"path": str, "content": str},
    security="sec_write",
    aliases=["/append"],
)
def _append_file(deps, **kwargs):
    result = deps.vfs.append(kwargs["path"], kwargs["content"], deps.lang)
    return result


@register(
    name="delete_file",
    triggers=_TRIGGERS_FILE,
    description="删除文件",
    params={"path": str},
    security="sec_write",
    aliases=["/delete"],
)
def _delete_file(deps, **kwargs):
    result = deps.vfs.delete(kwargs["path"], deps.lang)
    return result


@register(
    name="rename_file",
    triggers=["重命名", "改名", "rename", "move"],
    description="重命名或移动文件",
    params={"old_path": str, "new_path": str},
    security="sec_write",
    aliases=["/rename"],
)
def _rename_file(deps, **kwargs):
    result = deps.vfs.rename(kwargs["old_path"], kwargs["new_path"], deps.lang)
    return result


@register(
    name="replace_text",
    triggers=["替换", "replace", "文本替换", "正则替换"],
    description="替换文件中的文本（支持正则）",
    params={"path": str, "old_text": str, "new_text": str, "use_regex": bool},
    security="sec_write",
    aliases=["/replace"],
)
def _to_bool(v):
    """把字符串或布尔值统一转为 bool"""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes", "on")
    return bool(v)


def _replace_text(deps, **kwargs):
    result = deps.vfs.replace_text(
        kwargs["path"],
        kwargs["old_text"],
        kwargs["new_text"],
        _to_bool(kwargs.get("use_regex", False)),
        deps.lang,
    )
    return result


@register(
    name="grep_text",
    triggers=["搜索", "查找", "grep", "正则匹配", "匹配"],
    description="在文件中搜索文本（支持正则）",
    params={"path": str, "pattern": str, "use_regex": bool},
    security="sec_read",
    aliases=["/grep"],
)
def _grep_text(deps, **kwargs):
    result = deps.vfs.grep_text(
        kwargs["path"],
        kwargs["pattern"],
        _to_bool(kwargs.get("use_regex", False)),
        deps.lang,
    )
    return result
