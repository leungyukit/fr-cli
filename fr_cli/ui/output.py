"""
统一输出层 — 所有 REPL 命令的 print 都应该走这里

设计原则:
- 6 种语义化前缀: success / failure / warning / info / step / header
- 自动 TTY 降级:非 TTY 环境下,emoji 退化为可读字符
- 自动加色,不在调用方管颜色
- 可关闭颜色(环境变量 FR_CLI_NO_COLOR 或非 TTY)

用法:
    from fr_cli.ui.output import success, failure, warning, info, header, kv

    success("任务完成")
    failure("加载失败", reason="网络超时", suggestion="重试或检查网络")
    warning("目录已存在")
    info("正在分析...")
    header("扫描结果")
    kv("模型", "glm-4-flash")
    kv("用量", "1234 tokens", indent=1)
"""

import os
import sys
from typing import Optional

# 复用现有颜色常量(保持与其他 UI 模块一致)
from fr_cli.ui.ui import (
    GREEN, RED, YELLOW, CYAN, DIM, RESET,
)


# ---------- TTY / 颜色感知 ----------

def _isatty() -> bool:
    """检测 stdout 是否 TTY(非 TTY 走纯文本模式)"""
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _color_enabled() -> bool:
    """是否启用颜色:环境变量 NO_COLOR / FR_CLI_NO_COLOR / 非 TTY 都关"""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FR_CLI_NO_COLOR"):
        return False
    return _isatty()


_COLOR = _color_enabled()


def _c(color: str, text: str) -> str:
    """带颜色码的字符串(若颜色关闭则原样返回)"""
    if not _COLOR:
        return text
    return f"{color}{text}{RESET}"


# ---------- 6 种语义化输出 ----------

def success(message: str, detail: Optional[str] = None) -> None:
    """✅ 成功消息(绿色)"""
    line = f"✅ {message}"
    if detail:
        line += f"  {_c(DIM, detail)}"
    print(_c(GREEN, line))


def failure(
    message: str,
    reason: Optional[str] = None,
    suggestion: Optional[str] = None,
) -> None:
    """❌ 失败消息(红色),可带原因和建议"""
    line = f"❌ {message}"
    if reason:
        line += f"\n  {_c(DIM, '原因:')} {reason}"
    if suggestion:
        line += f"\n  {_c(CYAN, '建议:')} {suggestion}"
    print(_c(RED, line))


def warning(message: str, detail: Optional[str] = None) -> None:
    """⚠️ 警告消息(黄色)"""
    line = f"⚠️  {message}"
    if detail:
        line += f"  {_c(DIM, detail)}"
    print(_c(YELLOW, line))


def info(message: str) -> None:
    """ℹ️ 普通信息(蓝色/青色)"""
    print(_c(CYAN, f"ℹ️  {message}"))


def step(message: str, current: Optional[int] = None,
         total: Optional[int] = None) -> None:
    """→ 步骤/进度提示(灰色)"""
    if current is not None and total is not None:
        prefix = f"[{current}/{total}]"
    else:
        prefix = "→"
    print(_c(DIM, f"{prefix} {message}"))


def header(title: str) -> None:
    """═══ 区块标题(青色加粗)"""
    print()
    print(_c(CYAN, f"═══ {title} ═══"))


# ---------- key/value 列表 ----------

def kv(key: str, value: str, indent: int = 0) -> None:
    """格式化 key: value(对齐到 16 字符)"""
    prefix = "  " * indent
    k = f"{key:<16}"
    print(f"{prefix}{_c(CYAN, k)} {value}")


def kv_block(rows: list, indent: int = 0) -> None:
    """一次性打多行 key: value

    rows: [(key, value), ...] 或 [(key, value, color), ...]
    """
    prefix = "  " * indent
    for row in rows:
        if len(row) == 2:
            k, v = row
            v_color = None
        else:
            k, v, v_color = row
        k_padded = f"{k:<16}"
        v_styled = _c(v_color, v) if v_color else v
        print(f"{prefix}{_c(CYAN, k_padded)} {v_styled}")


# ---------- 列表 / 表格辅助 ----------

def bullet(items: list, indent: int = 0) -> None:
    """项目符号列表(• )"""
    prefix = "  " * indent
    for item in items:
        print(f"{prefix}{_c(DIM, '•')} {item}")


def separator() -> None:
    """空行 + 分隔线"""
    print()
    print(_c(DIM, "─" * 60))


# ---------- Result 适配器 ----------

def result(r, success_msg: Optional[str] = None) -> None:
    """统一输出 Result 对象

    Args:
        r: Result 对象(fr_cli.core.result.Result) 或 (data, error) tuple
        success_msg: 自定义成功提示(默认用 r.data)

    行为:
        - 成功: ✅ success_msg or data
        - 失败: ❌ error
    """
    # 兼容旧风格 tuple
    if isinstance(r, tuple) and len(r) == 2:
        data, error = r
        if error:
            failure(str(error))
        else:
            success(success_msg or (str(data) if data is not None else "完成"))
        return

    # Result 对象 — 通过 error 字段判定
    err = getattr(r, "error", None)
    if err:
        failure(str(err))
    else:
        data = getattr(r, "data", None)
        success(success_msg or (str(data) if data is not None else "完成"))
