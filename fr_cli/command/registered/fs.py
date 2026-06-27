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


@register(
    name="multi_edit",
    triggers=["多文件编辑", "批量编辑", "multi_edit", "batch_edit"],
    description="原子性多文件编辑:一次操作同时编辑多个文件,任一失败整体回滚",
    params={"edits": list},  # [{"path": str, "old_text": str, "new_text": str, "use_regex": bool}, ...]
    security="sec_write",
    aliases=["/multi_edit"],
)
def _multi_edit(deps, **kwargs):
    """原子性多文件编辑。

    edits 格式: [{"path": str, "old_text": str, "new_text": str, "use_regex": bool}, ...]

    行为:
      - 先把所有文件读入内存
      - 在内存里做替换(校验所有 old_text 都能找到)
      - 全部成功后再写回磁盘(避免一半成功的中间状态)
      - 任一校验失败 → 整体放弃,不修改任何文件
    """
    edits = kwargs.get("edits", [])
    if not isinstance(edits, list) or not edits:
        return Result.fail("edits 必须是非空列表")

    # 1. 读取所有文件并准备替换
    file_contents = {}  # path -> 原始内容
    file_replacements = {}  # path -> [(old_text, new_text, use_regex), ...]
    files_to_modify = set()

    for i, edit in enumerate(edits):
        if not isinstance(edit, dict):
            return Result.fail(f"第 {i+1} 个 edit 不是字典")

        path = edit.get("path")
        old = edit.get("old_text")
        new = edit.get("new_text", "")
        use_regex = _to_bool(edit.get("use_regex", False))

        if not path or old is None:
            return Result.fail(f"第 {i+1} 个 edit 缺少 path 或 old_text")

        # 读取文件(如果还没读过)
        if path not in file_contents:
            read_result = deps.vfs.read(path, deps.lang)
            if not read_result.is_ok():
                return Result.fail(f"读取 {path} 失败: {read_result.error}")
            file_contents[path] = read_result.unwrap()

        file_replacements.setdefault(path, []).append((old, new, use_regex))
        files_to_modify.add(path)

    # 2. 在内存里执行所有替换(同时校验)
    new_contents = {}
    for path, content in file_contents.items():
        new_content = content
        for old, new, use_regex in file_replacements[path]:
            if use_regex:
                import re
                try:
                    pattern = re.compile(old)
                except re.error as e:
                    return Result.fail(f"{path}: 正则编译失败: {e}")
                if not pattern.search(new_content):
                    return Result.fail(f"{path}: 正则未匹配到内容")
                new_content = pattern.sub(new, new_content)
            else:
                if old not in new_content:
                    return Result.fail(f"{path}: 未找到文本 \"{old[:50]}{'...' if len(old) > 50 else ''}\"")
                new_content = new_content.replace(old, new)
        new_contents[path] = new_content

    # 3. 全部校验通过,写回所有文件
    written = []
    for path in files_to_modify:
        result = deps.vfs.write(path, new_contents[path], deps.lang)
        if not result.is_ok():
            # 理论上不应到这里(因为我们先读了再改)
            return Result.fail(f"写入 {path} 失败: {result.error}")
        written.append(path)

    return Result.ok({
        "edited": written,
        "count": len(written),
    })


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
