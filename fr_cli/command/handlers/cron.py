"""命令处理器 —— cron"""

from fr_cli.command.registry import register, _TRIGGERS_CRON

@register(
    name="cron_add",
    triggers=_TRIGGERS_CRON,
    description="添加定时任务",
    params={"command": str, "interval": int},
    security="sec_exec",
    aliases=["/cron_add"],
)
def _cron_add(deps, **kwargs):
    from fr_cli.weapon.cron import add_job, _default_manager
    from fr_cli.gatekeeper.manager import sync_gatekeeper_cron_jobs
    jid, m = add_job(kwargs["command"], kwargs["interval"], deps.lang)
    if jid is not None:
        # 自动同步到 gatekeeper 配置
        sync_gatekeeper_cron_jobs(cron_jobs=_default_manager.export_jobs())
        return m, None
    return None, m


@register(
    name="cron_list",
    triggers=_TRIGGERS_CRON,
    description="列出定时任务",
    params={},
    aliases=["/cron_list"],
)
def _cron_list(deps, **kwargs):
    from fr_cli.weapon.cron import list_jobs
    res, err = list_jobs(deps.lang)
    return ("\n".join(res), None) if not err else (None, err)


@register(
    name="cron_del",
    triggers=_TRIGGERS_CRON,
    description="删除定时任务",
    params={"id": str},
    aliases=["/cron_del"],
)
def _cron_del(deps, **kwargs):
    from fr_cli.weapon.cron import del_job, _default_manager
    from fr_cli.gatekeeper.manager import sync_gatekeeper_cron_jobs
    ok, m = del_job(int(kwargs["id"]), deps.lang)
    if ok:
        # 自动同步到 gatekeeper 配置
        sync_gatekeeper_cron_jobs(cron_jobs=_default_manager.export_jobs())
        return m, None
    return None, m


# ------------------------------------------------------------------

