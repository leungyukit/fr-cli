"""
注册表分组:云盘命令（disk_ls / disk_up / disk_down / disk_cd / disk_setup）

(从 services.py 按功能拆分,registry 目录扫描自动加载)
"""
from fr_cli.command.registry import register, _TRIGGERS_DISK
from fr_cli.core.result import Result


# ============== 云盘 ==============

@register(
    name="disk_ls",
    triggers=_TRIGGERS_DISK,
    description="列出云盘文件",
    params={},
    aliases=["/disk_ls"],
)
def _disk_ls(deps, **kwargs):
    from fr_cli.lang.i18n import T
    if not _ensure_disk(deps):
        return Result.fail(T("disk_no_cfg", deps.lang))
    result = deps.disk_c.ls(deps.lang)
    if result.is_fail():
        return Result.fail(result.error)
    return Result.ok("\n".join(result.unwrap()) if result.unwrap() else T("empty", deps.lang))


@register(
    name="disk_up",
    triggers=_TRIGGERS_DISK,
    description="上传文件到云盘",
    params={"local": str, "remote": str},
    security="sec_upload_disk",
    aliases=["/disk_up"],
)
def _disk_up(deps, **kwargs):
    from fr_cli.lang.i18n import T
    if not _ensure_disk(deps):
        return Result.fail(T("disk_no_cfg", deps.lang))
    result = deps.disk_c.up(kwargs["local"], kwargs["remote"], deps.lang)
    return result


@register(
    name="disk_down",
    triggers=_TRIGGERS_DISK,
    description="从云盘下载文件",
    params={"remote": str, "local": str},
    security="sec_download_disk",
    aliases=["/disk_down"],
)
def _disk_down(deps, **kwargs):
    from fr_cli.lang.i18n import T
    if not _ensure_disk(deps):
        return Result.fail(T("disk_no_cfg", deps.lang))
    loc = kwargs.get("local") or kwargs["remote"].split("/")[-1]
    result = deps.disk_c.down(kwargs["remote"], loc, deps.lang)
    return result


@register(
    name="disk_cd",
    triggers=_TRIGGERS_DISK,
    description="切换云盘目录",
    params={"path": str},
    aliases=["/disk_cd"],
)
def _disk_cd(deps, **kwargs):
    from fr_cli.lang.i18n import T
    if not _ensure_disk(deps):
        return Result.fail(T("disk_no_cfg", deps.lang))
    result = deps.disk_c.cd(kwargs["path"], deps.lang)
    return result


@register(
    name="disk_setup",
    description="云盘配置向导",
    params={},
    aliases=["/disk_setup"],
)
def _disk_setup(deps, **kwargs):
    from fr_cli.conf.wizard import disk_wizard
    ok, deps.cfg = disk_wizard(deps.cfg, deps.lang)
    if ok:
        from fr_cli.weapon.disk import CloudDisk
        deps.disk_c = CloudDisk(deps.cfg.get("disk", {}))
    return Result.ok("OK") if ok else Result.fail("Cancelled")


def _ensure_disk(deps):
    if deps.disk_c and getattr(deps.disk_c, "type", None):
        return True
    from fr_cli.conf.wizard import disk_wizard
    ok, deps.cfg = disk_wizard(deps.cfg, deps.lang)
    if ok:
        from fr_cli.weapon.disk import CloudDisk
        deps.disk_c = CloudDisk(deps.cfg.get("disk", {}))
    return ok
