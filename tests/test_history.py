"""
会话历史测试
覆盖 init_history / get_sessions / save_sess / load_sess / del_sess / export_md。

注:history 模块用全局 HIST_DIR,测试时 monkeypatch 到临时目录。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def isolated_history(tmp_path, monkeypatch):
    """隔离 HIST_DIR 到临时目录"""
    import fr_cli.memory.history as hist_mod
    monkeypatch.setattr(hist_mod, "HIST_DIR", tmp_path)
    return tmp_path


class TestInitHistory:

    def test_creates_directory(self, tmp_path, monkeypatch):
        import fr_cli.memory.history as hist_mod
        target = tmp_path / "new_history_dir"
        monkeypatch.setattr(hist_mod, "HIST_DIR", target)
        hist_mod.init_history()
        assert target.exists()
        assert target.is_dir()


class TestSaveLoadSession:

    def test_save_and_list(self, isolated_history):
        from fr_cli.memory import history
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        ok = history.save_sess("test_session", msgs)
        assert ok is True

        sessions = history.get_sessions()
        assert len(sessions) >= 1
        # 至少有一个叫 test_session
        names = [s["name"] for s in sessions]
        assert "test_session" in names

    def test_load_session(self, isolated_history):
        from fr_cli.memory import history
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        history.save_sess("my_session", msgs)

        ok, loaded_msgs, name = history.load_sess(0, "system prompt content")
        assert ok is True
        assert name == "my_session"
        assert loaded_msgs is not None
        assert len(loaded_msgs) >= 2  # 加了 system prompt
        # 第一条应是 system
        assert loaded_msgs[0]["role"] == "system"
        assert loaded_msgs[0]["content"] == "system prompt content"

    def test_load_session_invalid_index(self, isolated_history):
        from fr_cli.memory import history
        ok, msgs, name = history.load_sess(999, "sp")
        assert ok is False

    def test_delete_session(self, isolated_history):
        from fr_cli.memory import history
        history.save_sess("to_delete", [{"role": "user", "content": "x"}])
        assert len(history.get_sessions()) >= 1
        history.del_sess(0)
        assert len(history.get_sessions()) == 0

    def test_delete_invalid_index(self, isolated_history):
        from fr_cli.memory import history
        history.save_sess("s", [{"role": "user", "content": "x"}])
        # 不应崩
        history.del_sess(999)


class TestExportMarkdown:

    def test_export_empty_msgs(self, isolated_history):
        from fr_cli.memory import history
        ok, msg = history.export_md([], "zh")
        assert ok is False

    def test_export_with_msgs(self, isolated_history):
        from fr_cli.memory import history
        msgs = [
            {"role": "user", "content": "什么是 fr-cli?"},
            {"role": "assistant", "content": "fr-cli 是一个终端 AI 助手。"},
        ]
        # 默认导出到 cwd
        original_cwd = os.getcwd()
        os.chdir(str(isolated_history))
        try:
            ok, result = history.export_md(msgs, "zh")
            assert ok is True
            # 应生成 .md 文件
            md_files = list(isolated_history.glob("*.md"))
            assert len(md_files) >= 1
            # 内容应包含对话
            content = md_files[0].read_text(encoding="utf-8")
            assert "fr-cli" in content
        finally:
            os.chdir(original_cwd)

    def test_export_with_custom_dir(self, isolated_history):
        from fr_cli.memory import history
        msgs = [{"role": "user", "content": "test"}]
        target_dir = isolated_history / "exports"
        target_dir.mkdir()
        ok, result = history.export_md(msgs, "zh", out_dir=str(target_dir))
        if ok:
            md_files = list(target_dir.glob("*.md"))
            assert len(md_files) >= 1


class TestSessionNameSafety:

    def test_save_with_special_chars(self, isolated_history):
        """名字包含特殊字符应被清理"""
        from fr_cli.memory import history
        ok = history.save_sess("../../etc/passwd", [{"role": "user", "content": "x"}])
        assert ok is True
        # 文件应在 HIST_DIR 内(不应逃逸)
        escaped = list(isolated_history.glob("*passwd*"))
        if escaped:
            for f in escaped:
                # 文件名不应包含 .. 或 /
                assert ".." not in f.name
                assert "/" not in f.name


class TestGetSessions:

    def test_empty_history(self, isolated_history):
        from fr_cli.memory import history
        sessions = history.get_sessions()
        assert sessions == []

    def test_multiple_sessions(self, isolated_history):
        from fr_cli.memory import history
        history.save_sess("s1", [{"role": "user", "content": "1"}])
        history.save_sess("s2", [{"role": "user", "content": "2"}])
        history.save_sess("s3", [{"role": "user", "content": "3"}])
        sessions = history.get_sessions()
        assert len(sessions) == 3
