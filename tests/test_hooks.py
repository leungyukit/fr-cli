"""
Hooks 系统测试
覆盖 HookManager 的 PreToolUse / PostToolUse / UserPromptSubmit / 阻止 / 修改参数等。
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.agent.hooks import (
    Hook, HookManager, HookResult, get_hook_manager, reset_hook_manager,
)


@pytest.fixture(autouse=True)
def reset_global():
    """每个测试重置全局 hook manager"""
    reset_hook_manager()
    yield
    reset_hook_manager()


# ==================== Hook 数据类 ====================

class TestHookDataclass:

    def test_basic_construction(self):
        h = Hook(event="PreToolUse", matcher="write_file", command="echo blocked")
        assert h.event == "PreToolUse"
        assert h.matcher == "write_file"
        assert h.command == "echo blocked"
        assert h.type == "command"  # default

    def test_matches_tool_name(self):
        h = Hook(event="PreToolUse", matcher="write.*", command="x")
        assert h.matches(tool_name="write_file") is True
        assert h.matches(tool_name="delete_file") is False

    def test_matches_user_input(self):
        h = Hook(event="UserPromptSubmit", matcher="deploy", command="x")
        assert h.matches(user_input="please deploy the app") is True
        assert h.matches(user_input="hello world") is False

    def test_empty_matcher_matches_all(self):
        h = Hook(event="PreToolUse", command="x")
        assert h.matches(tool_name="any") is True

    def test_to_dict_from_dict(self):
        original = Hook(event="PostToolUse", matcher="read_file",
                       type_="command", command="cat",
                       description="log reads")
        d = original.to_dict()
        restored = Hook.from_dict(d)
        assert restored.event == original.event
        assert restored.matcher == original.matcher
        assert restored.command == original.command


# ==================== HookManager 加载 ====================

class TestHookManagerLoad:

    def test_empty_manager(self):
        mgr = HookManager()
        assert mgr.get_hooks("PreToolUse") == []
        assert mgr.get_hooks("PostToolUse") == []

    def test_load_from_cfg(self):
        cfg = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "write_file", "command": "echo ok"}
                ]
            }
        }
        mgr = HookManager(cfg=cfg)
        hooks = mgr.get_hooks("PreToolUse")
        assert len(hooks) == 1
        assert hooks[0].matcher == "write_file"

    def test_load_from_user_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        hooks_file = tmp_path / ".fr_cli" / "hooks.json"
        hooks_file.parent.mkdir(parents=True)
        hooks_file.write_text(json.dumps({
            "PreToolUse": [{"matcher": "delete_file", "command": "echo danger"}]
        }))
        mgr = HookManager()
        assert len(mgr.get_hooks("PreToolUse")) == 1

    def test_load_from_project_file(self, tmp_path):
        project_hooks = tmp_path / ".fr_cli" / "hooks.json"
        project_hooks.parent.mkdir(parents=True)
        project_hooks.write_text(json.dumps({
            "PostToolUse": [{"matcher": ".*", "command": "logger.sh"}]
        }))
        mgr = HookManager(cwd=tmp_path)
        assert len(mgr.get_hooks("PostToolUse")) == 1

    def test_invalid_event_skipped(self):
        cfg = {
            "hooks": {
                "InvalidEvent": [{"command": "x"}],
                "PreToolUse": [{"command": "y"}],
            }
        }
        mgr = HookManager(cfg=cfg)
        # InvalidEvent 被忽略,PreToolUse 保留
        assert len(mgr.get_hooks("InvalidEvent")) == 0
        assert len(mgr.get_hooks("PreToolUse")) == 1


# ==================== PreToolUse ====================

class TestPreToolUse:

    def test_no_hooks_no_block(self):
        mgr = HookManager()
        result = mgr.run_pre_tool_use("write_file", {"path": "/x"})
        assert result.blocked is False

    def test_exit_code_2_blocks(self):
        mgr = HookManager(cfg={
            "hooks": {
                "PreToolUse": [
                    {"matcher": "delete_file", "command": "exit 2"}
                ]
            }
        })
        result = mgr.run_pre_tool_use("delete_file", {"path": "/important"})
        assert result.blocked is True

    def test_exit_code_0_does_not_block(self):
        mgr = HookManager(cfg={
            "hooks": {
                "PreToolUse": [
                    {"matcher": ".*", "command": "exit 0"}
                ]
            }
        })
        result = mgr.run_pre_tool_use("any_tool", {})
        assert result.blocked is False

    def test_matcher_filters_tools(self):
        mgr = HookManager(cfg={
            "hooks": {
                "PreToolUse": [
                    {"matcher": "write_file", "command": "exit 2"}
                ]
            }
        })
        # write_file 匹配,被阻止
        r1 = mgr.run_pre_tool_use("write_file", {})
        assert r1.blocked is True
        # read_file 不匹配,不被阻止
        r2 = mgr.run_pre_tool_use("read_file", {})
        assert r2.blocked is False

    def test_json_block(self):
        mgr = HookManager(cfg={
            "hooks": {
                "PreToolUse": [
                    {"matcher": ".*", "command": 'echo \'{"block": true, "reason": "test block"}\''}
                ]
            }
        })
        result = mgr.run_pre_tool_use("any_tool", {})
        assert result.blocked is True
        assert "test block" in result.reason

    def test_modified_args_applied(self):
        mgr = HookManager(cfg={
            "hooks": {
                "PreToolUse": [
                    {"matcher": ".*", "command": 'echo \'{"modified_args": {"path": "/redirected"}}\''}
                ]
            }
        })
        result = mgr.run_pre_tool_use("any_tool", {"path": "/original"})
        assert result.modified_args.get("path") == "/redirected"

    def test_first_blocking_hook_stops_chain(self):
        """多个 hooks,第一个 block 后后续不再执行"""
        mgr = HookManager(cfg={
            "hooks": {
                "PreToolUse": [
                    {"matcher": ".*", "command": "exit 2"},
                    {"matcher": ".*", "command": "echo should_not_run"},
                ]
            }
        })
        result = mgr.run_pre_tool_use("any_tool", {})
        assert result.blocked is True
        # 第二个 hook 没执行(没有 message)
        assert all("should_not_run" not in m for m in result.messages)

    def test_timeout_handled(self):
        """hook 超时不崩"""
        mgr = HookManager(cfg={
            "hooks": {
                "PreToolUse": [
                    {"matcher": ".*", "command": "sleep 10"}
                ]
            }
        })
        result = mgr.run_pre_tool_use("any_tool", {}, timeout=1)
        # 超时不应崩
        assert result.blocked is False


# ==================== PostToolUse ====================

class TestPostToolUse:

    def test_no_hooks_returns_input(self):
        mgr = HookManager()
        result = mgr.run_post_tool_use("any", {}, "original result")
        # 没 hook 时 tool_result 保留
        assert result.modified_args.get("tool_result") == "original result"

    def test_json_modified_result(self):
        mgr = HookManager(cfg={
            "hooks": {
                "PostToolUse": [
                    {"matcher": ".*", "command": 'echo \'{"tool_result": "modified"}\''}
                ]
            }
        })
        result = mgr.run_post_tool_use("any", {}, "original")
        assert result.modified_args.get("tool_result") == "modified"

    def test_plain_text_replaces_result(self):
        """纯文本 stdout 也会被当作 tool_result 替换"""
        mgr = HookManager(cfg={
            "hooks": {
                "PostToolUse": [
                    {"matcher": ".*", "command": 'echo plain text output'}
                ]
            }
        })
        result = mgr.run_post_tool_use("any", {}, "original")
        # stdout 是 plain text,也会替换
        assert result.modified_args.get("tool_result") == "plain text output"


# ==================== UserPromptSubmit ====================

class TestUserPromptSubmit:

    def test_block_user_input(self):
        mgr = HookManager(cfg={
            "hooks": {
                "UserPromptSubmit": [
                    {"matcher": ".*rm\\s+-rf.*", "command": "exit 2"}
                ]
            }
        })
        result = mgr.run_user_prompt_submit("please rm -rf /")
        assert result.blocked is True

    def test_allow_input(self):
        mgr = HookManager(cfg={
            "hooks": {
                "UserPromptSubmit": [
                    {"matcher": ".*dangerous.*", "command": "exit 2"}
                ]
            }
        })
        result = mgr.run_user_prompt_submit("hello world")
        assert result.blocked is False


# ==================== Hook 管理 ====================

class TestHookManagement:

    def test_add_hook(self):
        mgr = HookManager()
        h = Hook(event="PreToolUse", matcher="x", command="echo y")
        mgr.add_hook(h)
        assert len(mgr.get_hooks("PreToolUse")) == 1

    def test_add_dedup(self):
        mgr = HookManager()
        h = Hook(event="PreToolUse", matcher="x", command="echo y")
        mgr.add_hook(h)
        mgr.add_hook(h)  # 重复添加
        assert len(mgr.get_hooks("PreToolUse")) == 1

    def test_save_to_user_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        mgr = HookManager()
        mgr.add_hook(Hook(event="PreToolUse", matcher="write_file", command="echo x"))
        target = mgr.save_to_user_config()
        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert "PreToolUse" in data


# ==================== HookResult ====================

class TestHookResult:

    def test_default(self):
        r = HookResult()
        assert r.blocked is False
        assert r.modified_args == {}
        assert r.messages == []

    def test_repr(self):
        r = HookResult(blocked=True, reason="test")
        assert "blocked=True" in repr(r)
        assert "test" in repr(r)


# ==================== 全局实例 ====================

class TestGlobalHookManager:

    def test_get_returns_singleton(self):
        m1 = get_hook_manager()
        m2 = get_hook_manager()
        assert m1 is m2

    def test_reset_creates_new(self):
        m1 = get_hook_manager()
        reset_hook_manager()
        m2 = get_hook_manager()
        assert m1 is not m2
