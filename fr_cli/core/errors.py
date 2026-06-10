"""
友好错误处理 —— 把异常转换为可操作的提示

设计：
- 每种错误给一个 Emoji 头 + 一句话解释 + 一个可执行的建议
- 错误日志写入 ~/.fr_cli/logs/errors.log（开发时排查用）
- 用户看不到 traceback（除非显式 /debug）
"""
import os
import sys
import traceback
import logging
from datetime import datetime
from pathlib import Path

from fr_cli.conf.paths import ROOT

# 错误日志
_ERROR_LOG = ROOT / "logs" / "errors.log"
_ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
_logger = logging.getLogger("fr_cli.errors")
_logger.setLevel(logging.DEBUG)
if not _logger.handlers:
    _fh = logging.FileHandler(_ERROR_LOG, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    _logger.addHandler(_fh)


# ==================== 错误分类 ====================

class FrCliError(Exception):
    """所有 fr-cli 错误的基类"""
    emoji = "❌"
    hint = ""

    def __init__(self, message: str = "", hint: str = "", original: Exception = None):
        super().__init__(message)
        self.message = message or self.__class__.__doc__ or "未知错误"
        self.hint = hint or self.hint
        self.original = original

    def format(self) -> str:
        """格式化为终端输出"""
        lines = [f"{self.emoji} {self.message}"]
        if self.hint:
            lines.append(f"   💡 {self.hint}")
        return "\n".join(lines)

    def log(self):
        """记录到日志（含 traceback）"""
        msg = f"[{self.__class__.__name__}] {self.message}"
        if self.original:
            msg += f"\n  Original: {type(self.original).__name__}: {self.original}"
            msg += "\n" + "".join(traceback.format_exception(type(self.original), self.original, self.original.__traceback__))
        _logger.error(msg)


class APIKeyError(FrCliError):
    """API Key 无效或缺失"""
    emoji = "🔑"
    hint = "用 /key <your-key> 设置，或 /providers use <提供商> 切换"


class NetworkError(FrCliError):
    """网络连接失败"""
    emoji = "🌐"
    hint = "检查网络/代理设置；可设环境变量 HTTPS_PROXY"


class RateLimitError(FrCliError):
    """API 限流"""
    emoji = "⏱️"
    hint = "等 30 秒再试；或切到其他提供商（/providers use deepseek）"


class TokenLimitError(FrCliError):
    """上下文超长"""
    emoji = "📏"
    hint = "/undo 删几轮，或 /session_load 换个新 session，或 /limit 调小上限"


class ModelNotFoundError(FrCliError):
    """模型不存在"""
    emoji = "🔮"
    hint = "用 /model <name> 切到支持的模型；/providers list 看所有提供商"


class ConfigError(FrCliError):
    """配置文件问题"""
    emoji = "⚙️"
    hint = "检查 ~/.fr_cli/config.json 是否合法 JSON；删了会自动用默认配置"


class FilePermissionError(FrCliError):
    """文件权限不足"""
    emoji = "🚫"
    hint = "用 /dir 确认文件在允许目录里；或 chmod 改文件权限"


class FileNotFoundError(FrCliError):
    """文件不存在"""
    emoji = "🔍"
    hint = "用 /ls 看当前目录文件；用 /dir <path> 加允许目录"


class ShellExecError(FrCliError):
    """Shell 命令执行失败"""
    emoji = "💥"
    hint = "检查命令语法；非交互 shell 限制（管道/重定向）"


class TimeoutError(FrCliError):
    """执行超时"""
    emoji = "⏰"
    hint = "命令超过 30s；可调整 cron 任务的 interval，或检查网络"


class ArgumentError(FrCliError):
    """参数错误"""
    emoji = "📝"
    hint = "用 /help <cmd> 查看用法"


# ==================== 异常转换器 ====================

def _is_truthy(s: str) -> bool:
    return s.lower() in ("1", "true", "yes", "on")


def friendly_print(exc: Exception, debug: bool = False) -> str:
    """把异常转换为友好提示并返回字符串

    Args:
        exc: 任意异常
        debug: True 时附带 traceback（默认 False）
    """
    # 1. 已知错误类型
    if isinstance(exc, FrCliError):
        if debug:
            return exc.format() + "\n" + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        exc.log()
        return exc.format()

    # 2. 已知 Python 内置异常的分类映射
    msg = str(exc) or type(exc).__name__

    if isinstance(exc, FileNotFoundError):
        e = FileNotFoundError(msg)
    elif isinstance(exc, PermissionError):
        e = FilePermissionError(msg)
    elif isinstance(exc, TimeoutError):
        e = TimeoutError(msg)
    elif isinstance(exc, (ConnectionError, OSError)) and "api" in msg.lower() or "network" in msg.lower():
        e = NetworkError(msg)
    elif "api key" in msg.lower() or "unauthorized" in msg.lower() or "401" in msg:
        e = APIKeyError(msg)
    elif "rate limit" in msg.lower() or "429" in msg:
        e = RateLimitError(msg)
    elif "model" in msg.lower() and "not found" in msg.lower() or "404" in msg:
        e = ModelNotFoundError(msg)
    elif "context length" in msg.lower() or "max tokens" in msg.lower() or "token" in msg.lower():
        e = TokenLimitError(msg)
    elif isinstance(exc, KeyError):
        e = ArgumentError(f"缺少参数: {msg}")
    else:
        # 3. 未知错误
        e = FrCliError(f"{type(exc).__name__}: {msg}", hint="用 /debug 看详细 traceback")

    if debug:
        return e.format() + "\n" + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    e.log()
    return e.format()


def safe_run(fn, *args, **kwargs):
    """运行 fn(*args, **kwargs)，捕所有异常并返回 (result, friendly_msg)

    用于 main.py 的命令处理：
        result, err = safe_run(my_command, state, parts)
        if err:
            print(err)
    """
    try:
        return fn(*args, **kwargs), None
    except Exception as e:
        return None, friendly_print(e, debug=_is_truthy(os.environ.get("FR_CLI_DEBUG", "")))


# ==================== 调试模式 ====================

DEBUG = _is_truthy(os.environ.get("FR_CLI_DEBUG", ""))


def set_debug(on: bool):
    """切换调试模式"""
    global DEBUG
    DEBUG = on
    os.environ["FR_CLI_DEBUG"] = "1" if on else "0"


def is_debug() -> bool:
    return DEBUG
