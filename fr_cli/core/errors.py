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
- v3.1+ UX:扩展 common exception → 友好提示映射,所有 except 走 friendly_print
"""
import os
import json
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


# ==================== 常见异常 → 友好提示映射 ====================
# 任何 except Exception 调 friendly_print(e) 都会自动用下表查到友好标题 + hint
# 键:异常类型;值:(友好标题, 建议操作)
_ERROR_HINTS: dict = {
    FileNotFoundError: ("文件或目录不存在", "用 /pwd 看当前目录,确认路径是否正确"),
    PermissionError: ("权限不足", "检查文件/目录权限,或用 chmod / sudo 调整"),
    IsADirectoryError: ("期望文件但传入的是目录", "确认路径指向文件而不是目录"),
    NotADirectoryError: ("期望目录但传入的是文件", "确认路径指向目录而不是文件"),
    FileExistsError: ("文件已存在", "如需覆盖请加 --force,或换一个新名字"),
    TimeoutError: ("操作超时", "网络较慢,可重试,或在 /config 中调大 timeout"),
    ConnectionError: ("网络连接失败", "检查网络后重试,或 /ping <host> 诊断"),
    ConnectionRefusedError: ("连接被拒绝", "确认目标服务已启动,端口正确"),
    ConnectionResetError: ("连接被重置", "网络不稳定,稍后重试"),
    json.JSONDecodeError: ("JSON 解析失败", "数据格式可能损坏或不是合法 JSON"),
    UnicodeDecodeError: ("文件编码错误", "文件可能不是 UTF-8 编码,试试指定 encoding"),
    KeyError: ("缺少必填字段", "检查输入参数是否完整"),
    ValueError: ("参数值无效", "检查参数格式和取值范围"),
    TypeError: ("类型错误", "通常是内部 bug,可用 /debug 开启 traceback"),
    ImportError: ("依赖未安装", "运行 `pip install <package>` 安装,或用 `fr-cli doctor` 检查"),
    ModuleNotFoundError: ("模块未找到", "运行 `pip install <package>` 安装,或检查 Python 环境"),
    OSError: ("系统操作失败", "检查文件/路径状态,或 /debug 看 traceback"),
    MemoryError: ("内存不足", "数据量太大,考虑分批处理或增加内存"),
    KeyboardInterrupt: ("用户中断", "操作已取消"),
    NotImplementedError: ("功能未实现", "该能力正在规划中,可在 GitHub 提需求"),
}


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

    三层回退:
      1. FrCliError 子类:用其自带 emoji + hint
      2. 已知标准库异常:从 _ERROR_HINTS 自动映射友好标题 + 建议操作
      3. 完全未知异常:显示类型名 + 原始 message

    Args:
        exc: 任意异常
        debug: True 时输出 traceback,默认 False(也受 FR_CLI_DEBUG 控制)

    Returns:
        用户可读的字符串(可能多行)
    """
    if isinstance(exc, FrCliError):
        text = exc.format()
        if debug or is_debug():
            text += "\n" + traceback.format_exc()
        return text

    # 标准库 / 第三方常见异常 — 自动查 _ERROR_HINTS 映射
    name = type(exc).__name__
    msg = str(exc) or repr(exc) or "(无详细信息)"
    hint_info = _ERROR_HINTS.get(type(exc))
    if hint_info:
        title, hint = hint_info
        text = f"❌ {title}: {msg}\n   💡 {hint}"
    else:
        text = f"❌ {name}: {msg}"

    if debug or is_debug():
        text += "\n" + traceback.format_exc()
    return text


def suggest_fix(exc: Exception) -> str:
    """从异常中提取友好的可执行建议(供 REPL 自动显示 / 复制)

    Returns:
        单行简短建议(如 "用 /key <key> 配置 API Key")
    """
    if isinstance(exc, FrCliError) and exc.hint:
        return exc.hint
    info = _ERROR_HINTS.get(type(exc))
    if info:
        return info[1]
    return "用 /debug 开启 traceback 看更多细节"


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
