"""
Cron 调度解析 —— 纯函数层

从 fr_cli.weapon.cron 拆出(原文件 439 行)。
只含调度规格的解析 / 计算 / 描述,不碰线程与持久化:
- _parse_schedule: spec -> (mode, value)
- _next_run:       (mode, value) -> 下次执行 datetime
- _schedule_desc:  (mode, value) -> 人类可读描述

三种模式:
  interval: 间隔秒数(兼容旧式 "every 60s" / "interval:60")
  cron:     标准 cron 表达式(croniter 验证)
  at:       一次性任务,ISO 时间字符串
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Tuple

from croniter import croniter

# 最小执行间隔（秒）—— interval 模式限制，cron/at 模式不受此限制
MIN_INTERVAL = 5


def _parse_schedule(spec) -> Tuple[str, object]:
    """解析调度规格，返回 (mode, value) 元组。

    支持：
      - "every 60s" / "every 60" / "interval:60"  → ("interval", 60.0)
      - "0 9 * * *" / "cron:0 9 * * *"            → ("cron", "0 9 * * *")
      - "2026-12-31 23:59:59" / "at:..."           → ("at", datetime)

    如果无法解析，抛 ValueError。
    """
    if not spec or not isinstance(spec, str):
        raise ValueError(f"无效的调度规格: {spec!r}")

    s = spec.strip()

    # at: 模式
    if s.startswith("at:"):
        return ("at", datetime.fromisoformat(s[3:].strip()))
    # ISO 时间
    try:
        return ("at", datetime.fromisoformat(s))
    except ValueError:
        pass

    # every 模式（旧式 interval 兼容）
    if s.startswith("every"):
        rest = s[5:].strip().rstrip("sS").strip()
        try:
            return ("interval", float(rest))
        except ValueError:
            raise ValueError(f"无法解析 interval: {spec!r}")
    if s.startswith("interval:"):
        try:
            return ("interval", float(s[9:].strip()))
        except ValueError:
            raise ValueError(f"无法解析 interval: {spec!r}")

    # cron: 前缀或裸 cron 表达式
    if s.startswith("cron:"):
        s = s[5:].strip()

    # 用 croniter 验证是否为合法 cron 表达式
    try:
        croniter(s, datetime.now())
        return ("cron", s)
    except Exception as e:
        raise ValueError(f"无效的 cron 表达式: {spec!r} ({e})")


def _next_run(mode, value, after: Optional[datetime] = None) -> datetime:
    """计算下一次执行时间（datetime）。

    mode = "interval":  value 是秒数 → after + timedelta
    mode = "cron":      value 是 cron 表达式 → croniter.get_next
    mode = "at":        value 是 datetime → 直接返回
    """
    base = after or datetime.now()
    if mode == "interval":
        return base + timedelta(seconds=float(value))
    if mode == "cron":
        return croniter(value, base).get_next(datetime)
    if mode == "at":
        return value
    raise ValueError(f"未知调度模式: {mode}")


def _schedule_desc(mode, value) -> str:
    """把调度规格格式化成可读字符串。"""
    if mode == "interval":
        return f"every {value}s"
    if mode == "cron":
        return f"cron: {value}"
    if mode == "at":
        if isinstance(value, datetime):
            return f"at: {value.isoformat()}"
        return f"at: {value}"
    return f"{mode}: {value}"
