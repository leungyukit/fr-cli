"""
用户面错误信息友好化测试
"""
import json
from unittest.mock import MagicMock



# ---------- friendly_print 基础 ----------

class TestFriendlyPrint:
    """friendly_print 把任意异常格式化为用户可读字符串"""

    def test_FrCliError_uses_its_own_emoji_and_hint(self):
        from fr_cli.core.errors import FrCliError, friendly_print

        e = FrCliError("自定义错误", hint="试试重启")
        text = friendly_print(e)
        assert "自定义错误" in text
        assert "试试重启" in text
        assert "❌" in text

    def test_APIKeyError_has_specialized_hint(self):
        from fr_cli.core.errors import APIKeyError, friendly_print

        e = APIKeyError()
        text = friendly_print(e)
        assert "/key" in text
        assert "🔑" in text

    def test_FileNotFoundError_maps_to_friendly_title_and_hint(self):
        from fr_cli.core.errors import friendly_print

        e = FileNotFoundError("/no/such/file.txt")
        text = friendly_print(e)
        assert "文件或目录不存在" in text
        assert "/pwd" in text or "路径" in text
        assert "/no/such/file.txt" in text  # 原始信息保留

    def test_PermissionError_has_actionable_hint(self):
        from fr_cli.core.errors import friendly_print

        e = PermissionError("/etc/shadow")
        text = friendly_print(e)
        assert "权限不足" in text
        assert "chmod" in text or "sudo" in text

    def test_json_decode_error_mentions_json(self):
        from fr_cli.core.errors import friendly_print

        e = json.JSONDecodeError("Expecting value", "{not json", 0)
        text = friendly_print(e)
        assert "JSON" in text
        assert "解析失败" in text

    def test_unknown_exception_shows_type_name(self):
        from fr_cli.core.errors import friendly_print

        class WeirdError(Exception):
            pass

        e = WeirdError("abc")
        text = friendly_print(e)
        assert "WeirdError" in text
        assert "abc" in text

    def test_empty_message_falls_back_to_repr(self):
        from fr_cli.core.errors import friendly_print

        e = ValueError()
        text = friendly_print(e)
        assert "ValueError" in text

    def test_debug_includes_traceback(self):
        from fr_cli.core.errors import friendly_print

        try:
            raise FileNotFoundError("/x")
        except FileNotFoundError as e:
            text = friendly_print(e, debug=True)
        assert "文件或目录不存在" in text
        assert "Traceback" in text


# ---------- suggest_fix ----------

class TestSuggestFix:
    """suggest_fix 从异常中提取单行建议"""

    def test_FrCliError_returns_its_hint(self):
        from fr_cli.core.errors import FrCliError, suggest_fix

        e = FrCliError("test", hint="点 /help")
        assert suggest_fix(e) == "点 /help"

    def test_FileNotFoundError_returns_how_to_fix(self):
        from fr_cli.core.errors import suggest_fix

        e = FileNotFoundError("/x")
        fix = suggest_fix(e)
        assert "路径" in fix or "/pwd" in fix

    def test_unknown_exception_returns_debug_hint(self):
        from fr_cli.core.errors import suggest_fix

        class UnknownError(Exception):
            pass

        fix = suggest_fix(UnknownError("foo"))
        assert "/debug" in fix


# ---------- debug 开关 ----------

class TestDebugFlag:
    """set_debug / is_debug / FR_CLI_DEBUG 环境变量"""

    def test_default_off(self):
        from fr_cli.core import errors
        errors.set_debug(False)
        assert errors.is_debug() is False

    def test_set_debug_true(self):
        from fr_cli.core import errors
        errors.set_debug(True)
        assert errors.is_debug() is True
        errors.set_debug(False)  # 复位

    def test_env_var_enables_debug(self, monkeypatch):
        monkeypatch.setenv("FR_CLI_DEBUG", "1")
        # 重新 import 让 __init__ 重新读 env
        import importlib
        import fr_cli.core.errors as errors
        importlib.reload(errors)
        assert errors.is_debug() is True
        importlib.reload(errors)  # 复位

    def test_env_var_off_disables_debug(self, monkeypatch):
        monkeypatch.setenv("FR_CLI_DEBUG", "0")
        import importlib
        import fr_cli.core.errors as errors
        importlib.reload(errors)
        assert errors.is_debug() is False
        importlib.reload(errors)


# ---------- 端到端:commands 里的 except 用 friendly_print ----------

class TestCompetitorGapsUsesFriendlyPrint:
    """_cmd_competitor_gaps 的 except 块统一走 friendly_print"""

    def test_scan_failure_uses_friendly_print(self, capsys, monkeypatch):
        """scanner 抛 FileNotFoundError 时,用户看到的输出含友好提示"""
        from fr_cli.repl.commands import competitor_gaps

        # 构造一个会抛 FileNotFoundError 的 CompetitorGapScanner
        class BoomScanner:
            def __init__(self, **kw):
                pass
            def scan(self, **kw):
                raise FileNotFoundError("/no/such/yaml")
        monkeypatch.setattr(
            "fr_cli.dynamic_builder.competitor_gap_scan.CompetitorGapScanner",
            BoomScanner,
        )

        result = competitor_gaps._cmd_competitor_gaps(
            MagicMock(), ["/competitor_gaps", "scan"]
        )
        assert result is False
        captured = capsys.readouterr()
        text = captured.out
        assert "文件或目录不存在" in text
        # 友好的可执行建议(走 _ERROR_HINTS)
        assert "/pwd" in text or "路径" in text
