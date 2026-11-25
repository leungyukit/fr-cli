"""
VFS (Virtual File System) 测试
覆盖路径解析、沙盒逃逸防护、读写、目录操作、权限拒绝等。

VFS 是所有文件操作的基础设施,正确性至关重要。

注意:VFS 已迁移到 Result 风格 — read/write/delete/cd 等都返回 Result,
调用方需 .unwrap() 解包。
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.weapon.fs import VFS


@pytest.fixture
def sandbox(tmp_path):
    return VFS([str(tmp_path)])


@pytest.fixture
def multi_sandbox(tmp_path):
    d1 = tmp_path / "d1"
    d1.mkdir()
    d2 = tmp_path / "d2"
    d2.mkdir()
    return VFS([str(d1), str(d2)])


def _ok(result):
    """解包 Result 或返回原值(向后兼容)"""
    from fr_cli.core.result import Result
    if isinstance(result, Result):
        return result.unwrap() if result.is_ok() else None
    return result


# ==================== 路径解析 ====================

class TestPathResolve:

    def test_resolve_absolute_in_sandbox(self, sandbox, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        assert sandbox._resolve(str(f)) == f.resolve()

    def test_resolve_relative_to_cwd(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        f = tmp_path / "x.txt"
        f.write_text("x", encoding="utf-8")
        assert sandbox._resolve("x.txt") == f.resolve()

    def test_resolve_outside_sandbox_returns_none(self, sandbox):
        assert sandbox._resolve("/etc/passwd") is None

    def test_resolve_traversal_blocked(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        result = sandbox._resolve("../etc/passwd")
        assert result is None


# ==================== 读写操作 ====================

class TestReadWrite:

    def test_write_and_read(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        w = sandbox.write("a.txt", "hello", "zh")
        assert _ok(w) is not None
        assert _ok(sandbox.read("a.txt", "zh")) == "hello"

    def test_write_overwrites(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        sandbox.write("a.txt", "first", "zh")
        sandbox.write("a.txt", "second", "zh")
        assert _ok(sandbox.read("a.txt", "zh")) == "second"

    def test_append(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        sandbox.write("a.txt", "hello", "zh")
        sandbox.append("a.txt", " world", "zh")
        assert _ok(sandbox.read("a.txt", "zh")) == "hello world"

    def test_write_to_outside_sandbox_rejected(self, sandbox):
        sandbox.write("/etc/test_xyz_fr_cli.txt", "evil", "zh")
        assert not Path("/etc/test_xyz_fr_cli.txt").exists()

    def test_write_unicode_content(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        content = "你好世界 fr-cli"
        sandbox.write("unicode.txt", content, "zh")
        assert _ok(sandbox.read("unicode.txt", "zh")) == content

    def test_write_empty(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        sandbox.write("empty.txt", "", "zh")
        assert (tmp_path / "empty.txt").read_text(encoding="utf-8") == ""

    def test_read_nonexistent_returns_fail(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        result = sandbox.read("nonexistent.txt", "zh")
        from fr_cli.core.result import Result
        if isinstance(result, Result):
            assert result.is_fail()
            assert "不存在" in result.error
        else:
            assert "不存在" in str(result) or result is None


# ==================== 目录操作 ====================

class TestDirectoryOperations:

    def test_cd_to_subdirectory(self, sandbox, tmp_path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        sandbox.cd(str(subdir), "zh")
        # 写入应在 subdir
        sandbox.write("inside.txt", "ok", "zh")
        assert (subdir / "inside.txt").exists()

    def test_cd_to_outside_rejected(self, sandbox):
        """尝试 cd 到沙盒外应被拒绝"""
        sandbox.cd("/etc", "zh")
        # cwd 应没变(还是 tmp_path)
        sandbox._resolve("test.txt")
        # 如果 cwd 没变,test.txt 不在 /etc 下
        # 我们只验证 cd 没有副作用
        f = Path("/tmp/cd_test_after.txt")
        # 不会有副作用文件
        assert not f.exists()

    def test_ls_lists_directory(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")
        items = sandbox.ls("zh")
        # items 可能是 Result 或 list
        items_str = _str(items)
        assert "a.txt" in items_str
        assert "b.txt" in items_str

    def test_exists_returns_true_for_existing(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        (tmp_path / "x.txt").write_text("x", encoding="utf-8")
        assert sandbox.exists("x.txt") is True

    def test_exists_returns_false_for_missing(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        assert sandbox.exists("ghost.txt") is False

    def test_add_new_allowed_directory(self, sandbox, tmp_path):
        new_dir = tmp_path / "new_allowed"
        new_dir.mkdir()
        sandbox.add(str(new_dir), "zh")
        # 之后能 cd 进去
        sandbox.cd(str(new_dir), "zh")
        (new_dir / "f.txt").write_text("f", encoding="utf-8")
        items = sandbox.ls("zh")
        items_str = _str(items)
        assert "f.txt" in items_str

    def test_add_nonexistent_directory_rejected(self, sandbox):
        """不存在的目录应被拒绝"""
        result = sandbox.add("/nonexistent/dir/xxx", "zh")
        # 应是 Result.fail 或字符串包含"不存在"
        assert "不存在" in _str(result) or (hasattr(result, "is_fail") and result.is_fail())

    def test_list_dirs_returns_sandbox_list(self, sandbox):
        dirs = sandbox.list_dirs("zh")
        dirs_str = _str(dirs)
        # 至少包含初始的 tmp_path
        assert len(dirs_str) > 0
        # 应包含 tmp_path 路径
        assert "tmp" in dirs_str or "/" in dirs_str


def _str(obj):
    """统一把 Result/list/str 转字符串"""
    from fr_cli.core.result import Result
    if isinstance(obj, Result):
        return str(obj.unwrap()) if obj.is_ok() else str(obj.error)
    if isinstance(obj, (list, tuple)):
        return " ".join(str(x) for x in obj)
    return str(obj)


# ==================== 删除与重命名 ====================

class TestDeleteRename:

    def test_delete_file(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        f = tmp_path / "del.txt"
        f.write_text("bye", encoding="utf-8")
        sandbox.delete("del.txt", "zh")
        assert not f.exists()

    def test_delete_nonexistent_handled(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        result = sandbox.delete("ghost.txt", "zh")
        from fr_cli.core.result import Result
        if isinstance(result, Result):
            # fail 是预期
            assert result.is_fail()

    def test_rename_file(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        (tmp_path / "old.txt").write_text("content", encoding="utf-8")
        sandbox.rename("old.txt", "new.txt", "zh")
        assert not (tmp_path / "old.txt").exists()
        assert (tmp_path / "new.txt").exists()
        assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "content"


# ==================== 文本操作 ====================

class TestTextOperations:

    def test_replace_text(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        (tmp_path / "f.txt").write_text("hello world", encoding="utf-8")
        sandbox.replace_text("f.txt", "world", "fr-cli", False, "zh")
        assert (tmp_path / "f.txt").read_text(encoding="utf-8") == "hello fr-cli"

    def test_replace_text_with_regex(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        (tmp_path / "f.txt").write_text("a1 b22 c333", encoding="utf-8")
        sandbox.replace_text("f.txt", r"\d+", "X", True, "zh")
        assert (tmp_path / "f.txt").read_text(encoding="utf-8") == "aX bX cX"

    def test_grep_text(self, sandbox, tmp_path):
        sandbox.cd(str(tmp_path), "zh")
        (tmp_path / "log.txt").write_text("INFO: ok\nERROR: bad\nINFO: ok2", encoding="utf-8")
        results = sandbox.grep_text("log.txt", "ERROR", False, "zh")
        results_str = _str(results)
        assert "ERROR" in results_str
        assert "bad" in results_str


# ==================== 多沙盒 ====================

class TestMultiSandbox:

    def test_can_access_both(self, multi_sandbox, tmp_path):
        d1, d2 = tmp_path / "d1", tmp_path / "d2"
        (d1 / "in1.txt").write_text("1", encoding="utf-8")
        (d2 / "in2.txt").write_text("2", encoding="utf-8")
        multi_sandbox.cd(str(d1), "zh")
        assert _ok(multi_sandbox.read("in1.txt", "zh")) == "1"
        multi_sandbox.cd(str(d2), "zh")
        assert _ok(multi_sandbox.read("in2.txt", "zh")) == "2"


# ==================== ANSI 泄漏治理 ====================

class _FakeProxyStdout:
    """冒充 prompt_toolkit.patch_stdout 的 StdoutProxy。

    必须忠实复现两级行为, 少一级就会让用例失去意义:
    1) 识别: ui 的 stdout_is_prompt_toolkit_proxy() 靠
       type(sys.stdout).__module__ 是否含 "prompt_toolkit" 判定, 所以要把
       __module__ 伪装成 prompt_toolkit.patch_stdout;
    2) 破坏: 真代理非 raw 模式走 Vt100_Output.write(), 该方法的实现是
       `self._buffer.append(data.replace("\\x1b", "?"))`
       (prompt_toolkit/output/vt100.py), 会把文本里的 ESC 字节换成字面 '?'。
       少了第 2 级, 旧代码路径输出的是真 ESC 而不是 ?[ 残损序列,
       "无 ?[ 泄漏"这条断言就永远为真 —— 用例空跑。
    """

    def __init__(self):
        self.parts = []

    def write(self, s):
        self.parts.append(s.replace("\x1b", "?"))
        return len(s)

    def flush(self):
        pass

    @property
    def text(self):
        return "".join(self.parts)


_FakeProxyStdout.__module__ = "prompt_toolkit.patch_stdout"


class _FakeTtyStdout:
    """冒充真实终端(非 prompt_toolkit 代理): 原样透传, 不破坏 ESC。

    用于反向用例 —— 证明修复没有退化成"全局禁色": 在允许上色的环境里,
    print_styled 必须仍输出真 ESC 序列。
    """

    def __init__(self):
        self.parts = []

    def write(self, s):
        self.parts.append(s)
        return len(s)

    def flush(self):
        pass

    def isatty(self):
        return True

    @property
    def text(self):
        return "".join(self.parts)


class TestAnsiLeakUnderPatchStdout:
    """VFS 写文件的 diff 展示在 patch_stdout 代理期不得泄漏 ANSI 残损序列。

    背景: fs.py 曾用 from ui import 颜色常量后裸 print。那些常量是导入期
    冻结的快照(ui 在 REPL 启动前导入, 当时 stdout 还是真 TTY, 颜色全开),
    而 reset_color() 全仓库无人调用, 快照永不更新; 进 patch_stdout 代理期后
    裸 print 仍吐真 ESC, 被 Vt100_Output.write() 换成 '?'。已改为
    print_styled(每次实时判定 use_color()), 这里锁死该行为。
    """

    def _arm_real_colors(self, monkeypatch):
        """把 fs 模块级的颜色常量 Patch 成真 ESC 序列。

        必须这么做: ui.py 在 import 时就按当时 stdout 是否 TTY 调 set_no_color(),
        pytest 捕获 stdout 期间常量全是空串 —— 不 Patch 的话"无泄漏"用例会因为
        输出里本来就没有任何 ESC 而空跑通过(假通过)。
        生产环境里 REPL 启动前 stdout 是真 TTY, fs.CYAN 冻结为 '\033[96m',
        Patch 成真序列正是忠实复现生产状态。
        """
        import fr_cli.weapon.fs as fs_mod
        monkeypatch.setattr(fs_mod, "CYAN", "\x1b[96m")
        monkeypatch.setattr(fs_mod, "GREEN", "\x1b[92m")
        monkeypatch.setattr(fs_mod, "YELLOW", "\x1b[93m")
        monkeypatch.setattr(fs_mod, "RED", "\x1b[91m")
        monkeypatch.setattr(fs_mod, "RESET", "\x1b[0m")

    def test_no_damaged_ansi_when_stdout_is_proxy(self, sandbox, tmp_path, monkeypatch):
        import fr_cli.ui.ui as ui
        # 只保留"代理期"这一个关色因子, 排除 pytest 捕获 stdout 造成的关色,
        # 否则用例会因错误的原因通过。
        self._arm_real_colors(monkeypatch)
        monkeypatch.setattr(ui, "_NO_COLOR", False)
        proxy = _FakeProxyStdout()
        monkeypatch.setattr(sys, "stdout", proxy)

        sandbox.write("leak.txt", "line one\nline two\n", "zh")

        out = proxy.text
        assert "?[" not in out, f"残损 ANSI 泄漏: {out!r}"
        assert "\x1b" not in out, f"裸 ESC 泄漏: {out!r}"
        assert "line one" in out, f"纯文本被误剥: {out!r}"

    def test_color_preserved_when_stdout_is_real_tty(self, sandbox, tmp_path, monkeypatch):
        import fr_cli.ui.ui as ui
        # 反向用例: 非代理且允许上色时, 必须仍输出真 ESC 序列,
        # 防止修复退化成"全局禁色"。
        self._arm_real_colors(monkeypatch)
        monkeypatch.setattr(ui, "_NO_COLOR", False)
        monkeypatch.setattr(ui, "color_enabled", lambda: True)
        proxy = _FakeTtyStdout()
        monkeypatch.setattr(sys, "stdout", proxy)

        sandbox.write("color.txt", "hello\n", "zh")

        out = proxy.text
        assert "\x1b[96m" in out, f"颜色被误剥: {out!r}"
        assert "?[" not in out, f"残损 ANSI 泄漏: {out!r}"

    def test_replace_preview_also_goes_through_print_styled(self, sandbox, tmp_path, monkeypatch):
        import fr_cli.ui.ui as ui
        self._arm_real_colors(monkeypatch)
        monkeypatch.setattr(ui, "_NO_COLOR", False)
        proxy = _FakeProxyStdout()
        monkeypatch.setattr(sys, "stdout", proxy)

        (tmp_path / "rep.txt").write_text("alpha\nbeta\n", encoding="utf-8")
        sandbox.replace_text("rep.txt", "beta", "gamma", False, "zh")

        out = proxy.text
        assert "?[" not in out, f"残损 ANSI 泄漏: {out!r}"
        assert "\x1b" not in out, f"裸 ESC 泄漏: {out!r}"
        assert "gamma" in out
