"""
动态工具沙箱 —— 回归测试（P0-1）

覆盖：
  - 静态校验（禁导入 / 禁内置 / 禁 dunder / run 入口签名）
  - 子进程隔离执行（参数传递 / 返回契约 / 异常隔离 / 超时终止）
  - 受限 builtins 与 import 守卫（运行时）
  - 能力 RPC 代理（web_c 等回父进程执行并走 sec_* 确认）
  - 凭证脱敏（cfg 不出主进程）
  - VFS 路径沙盒
  - 注册表接入（拒绝不安全代码 / sec_exec 确认 / 端到端 dispatch）
"""
import os
import subprocess
import sys
import time
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.core.result import Result
from fr_cli.dynamic_builder.sandbox import (
    DEFAULT_TIMEOUT,
    from_wire,
    run_in_sandbox,
    to_wire,
    validate_dynamic_code,
)
from fr_cli.weapon.fs import VFS


# ------------------------------------------------------------------
# 夹具
# ------------------------------------------------------------------

class _FakeSecurity:
    """记录确认调用的假 SecurityManager。"""

    def __init__(self, allow=True):
        self.allow = allow
        self.calls = []

    def check(self, key, target, tool_name="", args=None):
        self.calls.append((key, target))
        return self.allow


class _FakeWeb:
    """假 web_c —— 只在父进程里被调用。"""

    def __init__(self):
        self.calls = []

    def search(self, q, lang):
        self.calls.append(("search", q))
        return Result.ok([{"title": q}])

    def fetch(self, url, lang):
        self.calls.append(("fetch", url))
        return Result.ok(f"content:{url}")


@pytest.fixture
def sandbox_deps(tmp_path):
    """最小 deps 命名空间 —— 真实 VFS + 假 web_c/security。"""
    web = _FakeWeb()
    security = _FakeSecurity()
    deps = types.SimpleNamespace(
        vfs=VFS([str(tmp_path)]),
        mail_c=None,
        web_c=web,
        disk_c=None,
        plugins={},
        lang="zh",
        security=security,
        cfg={"api_key": "sk-should-never-leak", "model": "glm-4-flash"},
        client=None,
        model_name="glm-4-flash",
        mcp=None,
    )
    deps._fake_web = web
    deps._fake_security = security
    return deps


def _run(code, deps, kwargs=None, timeout=25, name="t_tool"):
    return run_in_sandbox(name, code, kwargs or {}, deps, timeout=timeout)


# ==================================================================
# 静态校验
# ==================================================================

class TestValidateDynamicCode:

    def test_valid_code_passes(self):
        code = "def run(deps, **kwargs):\n    return 'ok', None\n"
        result = validate_dynamic_code(code)
        assert result.is_ok(), result.error

    def test_empty_code_rejected(self):
        assert validate_dynamic_code("").is_fail()
        assert validate_dynamic_code("   \n ").is_fail()

    def test_syntax_error_rejected(self):
        result = validate_dynamic_code("def run(deps, **kwargs)\n    return 1")
        assert result.is_fail()
        assert "语法错误" in result.error

    def test_missing_run_entry_rejected(self):
        result = validate_dynamic_code("def helper():\n    return 1\n")
        assert result.is_fail()
        assert "run(deps" in result.error

    def test_run_without_deps_rejected(self):
        result = validate_dynamic_code("def run():\n    return 1, None\n")
        assert result.is_fail()
        assert "run(deps" in result.error

    @pytest.mark.parametrize("module", [
        "os", "sys", "subprocess", "socket", "requests", "urllib",
        "pathlib", "importlib", "pickle", "threading", "multiprocessing",
        "fr_cli",
    ])
    def test_blocked_modules_rejected(self, module):
        code = f"import {module}\n\ndef run(deps, **kwargs):\n    return 1, None\n"
        result = validate_dynamic_code(code)
        assert result.is_fail(), f"{module} 应被拦截"
        assert "禁止导入" in result.error

    def test_blocked_from_import_rejected(self):
        code = "from os import path\n\ndef run(deps, **kwargs):\n    return 1, None\n"
        result = validate_dynamic_code(code)
        assert result.is_fail()
        assert "禁止导入" in result.error

    @pytest.mark.parametrize("builtin_name", ["open", "eval", "exec", "compile", "input"])
    def test_blocked_builtins_rejected(self, builtin_name):
        code = f"def run(deps, **kwargs):\n    {builtin_name}('x')\n    return 1, None\n"
        result = validate_dynamic_code(code)
        assert result.is_fail(), f"{builtin_name} 应被拦截"
        assert "禁止调用内置函数" in result.error

    def test_blocked_dunder_rejected(self):
        code = "def run(deps, **kwargs):\n    return deps.__class__, None\n"
        result = validate_dynamic_code(code)
        assert result.is_fail()
        assert "禁止访问属性" in result.error

    def test_safe_dunder_allowed(self):
        code = "def run(deps, **kwargs):\n    return __name__, None\n"
        assert validate_dynamic_code(code).is_ok()

    def test_safe_modules_allowed(self):
        code = (
            "import json\nimport re\nimport math\n"
            "def run(deps, **kwargs):\n    return json.dumps({'a': 1}), None\n"
        )
        assert validate_dynamic_code(code).is_ok()

    def test_hint_points_to_deps(self):
        """拒绝原因里应告诉模型改用 deps.vfs / deps.web_c"""
        code = "def run(deps, **kwargs):\n    open('x')\n    return 1, None\n"
        assert "deps.vfs" in validate_dynamic_code(code).error


# ==================================================================
# 线上协议编解码
# ==================================================================

class TestWireCodec:

    @pytest.mark.parametrize("value", [
        None, True, False, 0, 3, 3.5, "文本", [], [1, "a"], {},
        {"k": "v", "n": {"deep": [1, 2]}},
    ])
    def test_roundtrip_primitives(self, value):
        assert from_wire(to_wire(value)) == value

    def test_tuple_preserved(self):
        assert from_wire(to_wire(("a", 1))) == ("a", 1)

    def test_result_preserved(self):
        result = Result.ok({"x": 1})
        restored = from_wire(to_wire(result))
        assert isinstance(restored, Result)
        assert restored.is_ok()
        assert restored.data == {"x": 1}

    def test_result_error_preserved(self):
        restored = from_wire(to_wire(Result.fail("炸了")))
        assert isinstance(restored, Result)
        assert restored.is_fail()
        assert restored.error == "炸了"

    def test_generator_materialized(self):
        restored = from_wire(to_wire(x for x in range(3)))
        assert restored == [0, 1, 2]


# ==================================================================
# 沙箱执行
# ==================================================================

class TestSandboxExecution:

    def test_simple_run(self, sandbox_deps):
        code = "def run(deps, **kwargs):\n    return 'hello', None\n"
        result = _run(code, sandbox_deps)
        assert result.is_ok(), result.error
        assert result.data == "hello"

    def test_kwargs_passed_through(self, sandbox_deps):
        code = (
            "def run(deps, **kwargs):\n"
            "    return {'a': kwargs.get('a'), 'b': kwargs.get('b')}, None\n"
        )
        result = _run(code, sandbox_deps, {"a": 1, "b": "二"})
        assert result.is_ok(), result.error
        assert result.data == {"a": 1, "b": "二"}

    def test_legacy_signature_without_kwargs(self, sandbox_deps):
        """历史签名 run(deps, name='') —— 只传它接受的参数。"""
        code = "def run(deps, name=''):\n    return f'hello {name}', None\n"
        result = _run(code, sandbox_deps, {"name": "world", "extra": "丢弃"})
        assert result.is_ok(), result.error
        assert result.data == "hello world"

    def test_tuple_contract_success(self, sandbox_deps):
        code = "def run(deps, **kwargs):\n    return {'k': 'v'}, None\n"
        result = _run(code, sandbox_deps)
        assert result.is_ok()
        assert result.data == {"k": "v"}
        assert result.error is None

    def test_tuple_contract_error(self, sandbox_deps):
        code = "def run(deps, **kwargs):\n    return None, '业务错误'\n"
        result = _run(code, sandbox_deps)
        assert result.is_fail()
        assert result.error == "业务错误"

    def test_exception_isolated(self, sandbox_deps):
        code = "def run(deps, **kwargs):\n    raise ValueError('boom')\n"
        result = _run(code, sandbox_deps)
        assert result.is_fail()
        assert "boom" in result.error

    def test_parent_survives_tool_exception(self, sandbox_deps):
        """子进程炸掉不影响父进程 —— 父进程继续可用。"""
        code = "def run(deps, **kwargs):\n    raise SystemExit(3)\n"
        result = _run(code, sandbox_deps)
        assert result.is_fail()
        # 父进程还能继续跑下一个工具
        ok = _run("def run(deps, **kwargs):\n    return 'alive', None\n", sandbox_deps)
        assert ok.is_ok(), ok.error

    def test_timeout_terminates_child(self, sandbox_deps):
        code = "def run(deps, **kwargs):\n    while True:\n        pass\n"
        started = time.time()
        result = _run(code, sandbox_deps, timeout=3)
        elapsed = time.time() - started
        assert result.is_fail()
        assert "超时" in result.error
        assert elapsed < 20, "超时后应立即终止"

    def test_timeout_does_not_hang_parent(self, sandbox_deps):
        code = "def run(deps, **kwargs):\n    while True:\n        pass\n"
        result = _run(code, sandbox_deps, timeout=2)
        assert result.is_fail()
        # 父进程未被拖死
        again = _run("def run(deps, **kwargs):\n    return 1, None\n", sandbox_deps)
        assert again.is_ok()

    def test_static_check_applied_before_exec(self, sandbox_deps):
        """静态校验在执行前拦截 —— 不启动子进程。"""
        code = "def run(deps, **kwargs):\n    import os\n    return 1, None\n"
        result = _run(code, sandbox_deps)
        assert result.is_fail()
        assert "沙箱拒绝执行" in result.error
        assert "禁止导入" in result.error

    def test_stdout_does_not_corrupt_protocol(self, sandbox_deps):
        """用户代码的 print 不污染 stdout 协议。"""
        code = (
            "def run(deps, **kwargs):\n"
            "    print('HELLO-STDOUT')\n"
            "    return 'done', None\n"
        )
        result = _run(code, sandbox_deps)
        assert result.is_ok(), result.error
        assert result.data == "done"

    def test_error_message_contains_exception_detail(self, sandbox_deps):
        code = (
            "def run(deps, **kwargs):\n"
            "    raise RuntimeError('带诊断的异常')\n"
        )
        result = _run(code, sandbox_deps)
        assert result.is_fail()
        assert "带诊断的异常" in result.error


# ==================================================================
# 运行时限制（受限 builtins / import 守卫）
# ==================================================================

class TestRuntimeGuards:

    def test_restricted_builtins_drop_dangerous_names(self):
        from fr_cli.dynamic_builder.sandbox_worker import _restricted_builtins
        restricted = _restricted_builtins()
        for name in ("open", "eval", "exec", "compile", "input", "__import__"):
            if name == "__import__":
                continue  # 被替换成守卫，不是删除
            assert name not in restricted, f"{name} 应从 builtins 中移除"

    def test_import_guard_blocks_dangerous_modules(self):
        from fr_cli.dynamic_builder.sandbox_worker import _restricted_builtins
        guarded = _restricted_builtins()["__import__"]
        with pytest.raises(ImportError):
            guarded("os")
        with pytest.raises(ImportError):
            guarded("subprocess")

    def test_import_guard_allows_safe_modules(self):
        from fr_cli.dynamic_builder.sandbox_worker import _restricted_builtins
        guarded = _restricted_builtins()["__import__"]
        mod = guarded("json")
        assert hasattr(mod, "dumps")

    def test_open_is_unavailable_at_runtime(self, sandbox_deps):
        """open() 在运行时也不可用 —— 不只是静态校验。"""
        from fr_cli.dynamic_builder.sandbox_worker import _restricted_builtins
        restricted = _restricted_builtins()
        with pytest.raises(NameError):
            exec("open('/etc/passwd')", {"__builtins__": restricted})

    def test_escape_via_module_attribute_blocked(self, sandbox_deps):
        """被放行模块夹带的黑名单模块属性（如 logging.os）被清洗掉。"""
        code = (
            "def run(deps, **kwargs):\n"
            "    import logging\n"
            "    return str(logging.os.getpid()), None\n"
        )
        result = _run(code, sandbox_deps)
        assert result.is_fail()
        assert "AttributeError" in result.error

    def test_security_stub_denies_everything(self, sandbox_deps):
        """子进程里的 security 是一律拒绝的桩。"""
        code = (
            "def run(deps, **kwargs):\n"
            "    return deps.security.check('sec_write', 'x'), None\n"
        )
        result = _run(code, sandbox_deps)
        assert result.is_ok(), result.error
        assert result.data is False

    def test_security_stub_denies_permission_decision(self, sandbox_deps):
        code = (
            "def run(deps, **kwargs):\n"
            "    return deps.security.permission_decision('x'), None\n"
        )
        result = _run(code, sandbox_deps)
        assert result.is_ok(), result.error
        assert result.data == "deny"


# ==================================================================
# 凭证与文件隔离
# ==================================================================

class TestCredentialAndFileIsolation:

    def test_cfg_credentials_scrubbed(self, sandbox_deps):
        code = "def run(deps, **kwargs):\n    return deps.cfg, None\n"
        result = _run(code, sandbox_deps)
        assert result.is_ok(), result.error
        assert result.data["api_key"] == "***"
        assert "sk-should-never-leak" not in str(result.data)

    def test_nested_credentials_scrubbed(self, sandbox_deps):
        sandbox_deps.cfg = {"outer": {"access_token": "abc123", "keep": 1}}
        code = "def run(deps, **kwargs):\n    return deps.cfg, None\n"
        result = _run(code, sandbox_deps)
        assert result.is_ok(), result.error
        assert result.data["outer"]["access_token"] == "***"
        assert result.data["outer"]["keep"] == 1

    def test_vfs_path_escape_blocked(self, sandbox_deps):
        code = (
            "def run(deps, **kwargs):\n"
            "    res = deps.vfs.read('../../../../etc/passwd', deps.lang)\n"
            "    return {'ok': res.is_ok(), 'err': res.error}, None\n"
        )
        result = _run(code, sandbox_deps)
        assert result.is_ok(), result.error
        assert result.data["ok"] is False

    def test_vfs_write_then_read_inside_sandbox(self, sandbox_deps):
        code = (
            "def run(deps, **kwargs):\n"
            "    w = deps.vfs.write('note.txt', '你好', deps.lang)\n"
            "    r = deps.vfs.read('note.txt', deps.lang)\n"
            "    return {'w': w.is_ok(), 'text': r.data}, None\n"
        )
        result = _run(code, sandbox_deps)
        assert result.is_ok(), result.error
        assert result.data["w"] is True
        assert result.data["text"] == "你好"


# ==================================================================
# 能力 RPC 代理
# ==================================================================

class TestRpcProxy:

    def test_web_c_called_in_parent(self, sandbox_deps):
        code = (
            "def run(deps, **kwargs):\n"
            "    res = deps.web_c.search('关键词', deps.lang)\n"
            "    return {'ok': res.is_ok(), 'data': res.data}, None\n"
        )
        result = _run(code, sandbox_deps)
        assert result.is_ok(), result.error
        assert result.data["ok"] is True
        assert result.data["data"] == [{"title": "关键词"}]
        assert ("search", "关键词") in sandbox_deps._fake_web.calls

    def test_rpc_goes_through_security_check(self, sandbox_deps):
        code = (
            "def run(deps, **kwargs):\n"
            "    res = deps.web_c.fetch('http://example.com', deps.lang)\n"
            "    return res.data, None\n"
        )
        result = _run(code, sandbox_deps)
        assert result.is_ok(), result.error
        assert ("sec_fetch_web", "web_c.fetch") in sandbox_deps._fake_security.calls

    def test_rpc_denied_surfaces_error_to_child(self, sandbox_deps):
        sandbox_deps._fake_security.allow = False
        code = (
            "def run(deps, **kwargs):\n"
            "    try:\n"
            "        deps.web_c.search('x', deps.lang)\n"
            "        return 'unexpected', None\n"
            "    except Exception as e:\n"
            "        return str(e), None\n"
        )
        result = _run(code, sandbox_deps)
        assert result.is_ok(), result.error
        assert "拒绝" in result.data

    def test_unavailable_capability_reports_error(self, sandbox_deps):
        sandbox_deps.mail_c = None
        code = (
            "def run(deps, **kwargs):\n"
            "    try:\n"
            "        deps.mail_c.inbox(deps.lang)\n"
            "        return 'unexpected', None\n"
            "    except Exception as e:\n"
            "        return str(e), None\n"
        )
        result = _run(code, sandbox_deps)
        assert result.is_ok(), result.error
        assert "不可用" in result.data

    def test_generator_result_materialized(self, sandbox_deps):
        """client.stream_chat 的生成器在沙箱里变成列表。"""
        class _FakeClient:
            def stream_chat(self, model, messages, **kw):
                for i in range(3):
                    yield {"content": f"c{i}", "usage": None}

        sandbox_deps.client = _FakeClient()
        code = (
            "def run(deps, **kwargs):\n"
            "    chunks = deps.client.stream_chat('m', [])\n"
            "    return {'type': type(chunks).__name__,"
            " 'text': ''.join(c['content'] for c in chunks)}, None\n"
        )
        result = _run(code, sandbox_deps)
        assert result.is_ok(), result.error
        assert result.data["type"] == "list"
        assert result.data["text"] == "c0c1c2"


# ==================================================================
# 注册表接入
# ==================================================================

class TestRegistryIntegration:

    def test_register_rejects_unsafe_code(self):
        from fr_cli.dynamic_builder.registry_manager import register_dynamic_tool
        code = "def run(deps, **kwargs):\n    import subprocess\n    return 1, None\n"
        result = register_dynamic_tool("unsafe_tool_x", code)
        assert result.is_fail()
        assert "未通过安全校验" in result.error

    def test_register_rejects_missing_entry(self):
        from fr_cli.dynamic_builder.registry_manager import register_dynamic_tool
        result = register_dynamic_tool("noentry_tool_x", "x = 1\n")
        assert result.is_fail()
        assert "run(deps" in result.error

    def test_registered_tool_has_sec_exec(self):
        from fr_cli.dynamic_builder.registry_manager import register_dynamic_tool
        from fr_cli.command.registry import get_registry
        code = "def run(deps, **kwargs):\n    return 'ok', None\n"
        result = register_dynamic_tool("sec_tool_x", code)
        assert result.is_ok(), result.error
        tool = get_registry()._tools["sec_tool_x"]
        assert tool["security"] == "sec_exec"

    def test_dispatch_runs_tool_in_sandbox(self, sandbox_deps):
        """注册后 dispatch —— 代码在子进程执行，参数正确传递。"""
        from fr_cli.dynamic_builder.registry_manager import register_dynamic_tool
        from fr_cli.command.registry import get_registry
        code = (
            "def run(deps, **kwargs):\n"
            "    return {'echo': kwargs.get('msg')}, None\n"
        )
        result = register_dynamic_tool("echo_tool_x", code)
        assert result.is_ok(), result.error
        dispatched = get_registry().dispatch(
            sandbox_deps, "echo_tool_x", skip_security=True, msg="你好"
        )
        assert dispatched.is_ok(), dispatched.error
        assert dispatched.data == {"echo": "你好"}

    def test_dispatch_tool_error_is_reported(self, sandbox_deps):
        from fr_cli.dynamic_builder.registry_manager import register_dynamic_tool
        from fr_cli.command.registry import get_registry
        code = "def run(deps, **kwargs):\n    raise RuntimeError('内部炸了')\n"
        assert register_dynamic_tool("boom_tool_x", code).is_ok()
        dispatched = get_registry().dispatch(
            sandbox_deps, "boom_tool_x", skip_security=True
        )
        assert dispatched.is_fail()
        assert "内部炸了" in dispatched.error

    def test_load_all_rejects_unsafe_persisted_tool(self, tmp_path, monkeypatch):
        """磁盘上的不安全工具不会被注册。"""
        from fr_cli.dynamic_builder import registry_manager
        tools_dir = tmp_path / "dynamic_tools"
        tools_dir.mkdir(parents=True, exist_ok=True)
        (tools_dir / "bad_tool_x.py").write_text(
            "def run(deps, **kwargs):\n    import os\n    return 1, None\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(registry_manager, "DYNAMIC_TOOLS_DIR", tools_dir)
        monkeypatch.setattr(registry_manager, "REGISTRY_FILE", tools_dir / "registry.json")
        registry_manager._save_registry({
            "bad_tool_x": {"name": "bad_tool_x", "params": {}},
        })
        count, errors = registry_manager.load_and_register_all_dynamic_tools()
        assert count == 0
        assert errors and "安全校验" in errors[0]


# ==================================================================
# 进程回收
# ==================================================================

class TestProcessCleanup:

    def test_kill_process_kills_own_process_group(self):
        """独立进程组的子进程 —— 连同它自己 fork 的子孙一起回收。"""
        from fr_cli.dynamic_builder.sandbox import _kill_process
        grandchild_code = "import time; time.sleep(300)"
        proc = subprocess.Popen(
            [sys.executable, "-c",
             "import subprocess, sys, time;"
             "subprocess.Popen([sys.executable, '-c', %r]);"
             "time.sleep(300)" % grandchild_code],
            start_new_session=(os.name == "posix"),
        )
        assert os.getpgid(proc.pid) == proc.pid
        _kill_process(proc)
        assert proc.poll() is not None, "子进程应被终止"

    def test_kill_process_never_kills_parent_group(self):
        """子进程与父进程同组时 —— 绝不能 killpg（否则会把调用方一起杀掉）。

        用独立子进程跑这个场景，避免实现有 bug 时把 pytest 一起带走。
        """
        helper = (
            "import os, sys, subprocess;"
            "sys.path.insert(0, %r);"
            "from fr_cli.dynamic_builder.sandbox import _kill_process;"
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)']);"
            "assert os.getpgid(p.pid) == os.getpgid(0), '前提不成立';\n"
            "_kill_process(p);\n"
            "print('SURVIVED')" % os.getcwd()
        )
        res = subprocess.run(
            [sys.executable, "-c", helper], capture_output=True, text=True, timeout=60
        )
        assert "SURVIVED" in res.stdout, (
            f"调用方被误杀（stdout={res.stdout!r} stderr={res.stderr!r}）"
        )

    def test_child_rlimits_applied(self):
        """子进程内确实设上了资源限额。"""
        code = (
            "import resource, sys;"
            "sys.path.insert(0, %r);"
            "from fr_cli.dynamic_builder.sandbox import apply_child_limits;"
            "apply_child_limits({'cpu_seconds': 7});"
            "print(resource.getrlimit(resource.RLIMIT_CPU)[0])" % os.getcwd()
        )
        res = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
        )
        assert res.returncode == 0, res.stderr
        assert res.stdout.strip() == "7", res.stdout


# ==================================================================
# 边界
# ==================================================================

class TestSandboxEdgeCases:

    def test_default_timeout_value(self):
        assert DEFAULT_TIMEOUT >= 5

    def test_empty_code_fails_fast(self, sandbox_deps):
        result = _run("", sandbox_deps)
        assert result.is_fail()
        assert "代码为空" in result.error

    def test_missing_run_entry_fails(self, sandbox_deps):
        result = _run("def helper():\n    return 1\n", sandbox_deps)
        assert result.is_fail()

    def test_tool_returning_none(self, sandbox_deps):
        code = "def run(deps, **kwargs):\n    return None\n"
        result = _run(code, sandbox_deps)
        assert result.is_ok(), result.error
        assert result.data is None

    def test_large_payload_roundtrip(self, sandbox_deps):
        code = (
            "def run(deps, **kwargs):\n"
            "    return [i * 2 for i in range(2000)], None\n"
        )
        result = _run(code, sandbox_deps)
        assert result.is_ok(), result.error
        assert result.data == [i * 2 for i in range(2000)]
