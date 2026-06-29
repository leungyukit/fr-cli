"""
fr-cli 用户面错误处理

v3.0+ 重构说明:
- v2 历史上的 10+ 错误子类(NetworkError / RateLimitError 等)从未被引用 → 已删除
- 真正在用的只有:
  - FrCliError:基类(带 emoji/hint/log 用户体验)
  - APIKeyError:被外部 import 唯一保留的子类
  - friendly_print / safe_run:用户面错误格式化
  - set_debug / is_debug:全局调试开关
- 完整的 Provider/Tool/MCP 错误族在 fr_cli.v3.core.errors,这里不再重复定义
"""
import os
import traceback
import logging

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


class FrCliError(Exception):
    """所有 fr-cli 错误的基类

    Attributes:
        emoji: 终端显示用 emoji
        hint:  给用户的可执行建议
        original: 包装的原始异常(可选)
    """
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
        """记录到日志(含 traceback)"""
        msg = f"[{self.__class__.__name__}] {self.message}"
        if self.original:
            msg += f"\n  Original: {type(self.original).__name__}: {self.original}"
            msg += "\n" + "".join(traceback.format_exception(
                type(self.original), self.original, self.original.__traceback__
            ))
        _logger.error(msg)


class APIKeyError(FrCliError):
    """API Key 无效或缺失"""
    emoji = "🔑"
    hint = "用 /key <your-key> 设置,或 /providers use <提供商> 切换"


# ==================== 用户面辅助 ====================

def _is_truthy(s: str) -> bool:
    return s.strip().lower() in ("1", "true", "yes", "on")


def friendly_print(exc: Exception, debug: bool = False) -> str:
    """把异常格式化为用户友好字符串

    Args:
        exc: 任意异常
        debug: True 时输出 traceback,默认 False

    Returns:
        用户可读的字符串(可能多行)
    """
    if isinstance(exc, FrCliError):
        text = exc.format()
        if debug or is_debug():
            text += "\n" + traceback.format_exc()
        return text
    # 第三方 / 标准库异常
    name = type(exc).__name__
    msg = str(exc) or repr(exc)
    text = f"❌ {name}: {msg}"
    if debug or is_debug():
        text += "\n" + traceback.format_exc()
    return text


def safe_run(fn, *args, **kwargs):
    """运行 fn,捕获所有异常并返回 None + 错误日志(永不抛)

    用于 background daemon / retry loop,异常绝不能冒泡。
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        if isinstance(e, FrCliError):
            e.log()
        else:
            _logger.error(f"safe_run {fn}: {type(e).__name__}: {e}", exc_info=True)
        return None


# ==================== Debug 开关 ====================

_debug_on = _is_truthy(os.environ.get("FR_CLI_DEBUG", ""))


def set_debug(on: bool):
    """开启/关闭调试模式(影响 friendly_print 是否带 traceback)"""
    global _debug_on
    _debug_on = bool(on)


def is_debug() -> bool:
    """当前是否处于调试模式"""
    return _debug_on
