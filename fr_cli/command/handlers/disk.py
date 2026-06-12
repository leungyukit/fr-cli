"""命令处理器 —— disk"""

from fr_cli.command.registry import register, _TRIGGERS_DISK

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
        return None, T("disk_no_cfg", deps.lang)
    res, err = deps.disk_c.ls(deps.lang)
    return ("\n".join(res) if res else T("empty", deps.lang), None) if not err else (None, err)


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
        return None, T("disk_no_cfg", deps.lang)
    ok, m = deps.disk_c.up(kwargs["remote"], kwargs["local"], deps.lang)
    return (m, None) if ok else (None, m)


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
        return None, T("disk_no_cfg", deps.lang)
    loc = kwargs.get("local") or kwargs["remote"].split("/")[-1]
    ok, m = deps.disk_c.down(kwargs["remote"], loc, deps.lang)
    return (m, None) if ok else (None, m)


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
        return None, T("disk_no_cfg", deps.lang)
    ok, msg = deps.disk_c.cd(kwargs["path"], deps.lang)
    return (msg, None) if ok else (None, msg)


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
    return ("OK", None) if ok else (None, "Cancelled")


# ------------------------------------------------------------------

