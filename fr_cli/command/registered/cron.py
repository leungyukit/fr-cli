"""
注册表分组:定时任务命令（cron_add / cron_list / cron_del）

(从 services.py 按功能拆分,registry 目录扫描自动加载)
"""
from fr_cli.command.registry import register, _TRIGGERS_CRON
from fr_cli.core.result import Result


# ============== 定时任务 ==============

@register(
    name="cron_add",
    triggers=_TRIGGERS_CRON,
    description="添加定时任务（支持 interval/cron/at 三种调度）",
    params={"command": str, "schedule": str},
    security="sec_exec",
    aliases=["/cron_add"],
)
def _cron_add(deps, **kwargs):
    """添加定时任务。

    新接口（推荐）：/cron_add <schedule> <command...>
      schedule 可以是：
        - 数字（秒） → interval 模式
        - "every 60s"→ interval 60 秒
        - "0 9 * * *"→ cron 表达式
        - "2026-12-31 23:59"→ at 一次性任务
    旧接口（向后兼容）：/cron_add <command> <interval>
      当 command 是纯文本且 schedule 是数字时，自动按旧式解析
    """
    from fr_cli.weapon.cron import _default_manager
    from fr_cli.gatekeeper.manager import sync_gatekeeper_cron_jobs

    cmd = kwargs.get("command", "")
    schedule = kwargs.get("schedule", "")

    if not cmd:
        return Result.fail("用法: /cron_add <schedule> <command...>\n"
                            "示例: /cron_add 60 echo hello")
    if not schedule:
        schedule = "60"  # 默认 60 秒

    # 直接调 manager.add_job
    try:
        # 兼容旧式：schedule 是纯数字 → interval
        interval_val = float(schedule)
        jid, m = _default_manager.add_job(cmd=cmd, interval=interval_val, lang=deps.lang)
    except ValueError:
        jid, m = _default_manager.add_job(cmd=cmd, schedule=schedule, lang=deps.lang)

    if jid is not None:
        sync_gatekeeper_cron_jobs(cron_jobs=_default_manager.export_jobs())
        return Result.ok(m)
    return Result.fail(m)


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
    if err:
        return Result.ok("")  # 空结果用 ok 而非 fail,避免 router 当成未知命令
    if not res:
        return Result.ok("(暂无定时任务)")
    return Result.ok("\n".join(res))


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
        sync_gatekeeper_cron_jobs(cron_jobs=_default_manager.export_jobs())
        return Result.ok(m)
    return Result.fail(m)
