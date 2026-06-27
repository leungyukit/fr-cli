"""
Per-tool 权限测试
覆盖 PermissionManager 的 allow/deny/ask、path rules、优先级等。
"""
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.security.permissions import (
    PermissionManager, load_permissions, save_permissions,
)


class TestPermissionManager:

    def test_empty_manager_returns_fallthrough(self):
        mgr = PermissionManager()
        assert mgr.check_tool("any_tool") == "fallthrough"

    def test_always_allow(self):
        mgr = PermissionManager({"always_allow": ["read_file"]})
        assert mgr.check_tool("read_file") == "allow"

    def test_always_deny(self):
        mgr = PermissionManager({"always_deny": ["delete_file"]})
        assert mgr.check_tool("delete_file") == "deny"

    def test_ask_each_time(self):
        mgr = PermissionManager({"ask_each_time": ["git_commit"]})
        assert mgr.check_tool("git_commit") == "ask"

    def test_always_deny_takes_precedence_over_allow(self):
        mgr = PermissionManager({
            "always_allow": ["read_file"],
            "always_deny": ["read_file"],
        })
        # deny 优先
        assert mgr.check_tool("read_file") == "deny"


class TestPathRules:

    def test_allow_path_glob(self):
        mgr = PermissionManager({
            "path_rules": {
                "write_file": {"always_allow_paths": ["/tmp/*"]}
            }
        })
        assert mgr.check_tool("write_file", {"path": "/tmp/test.txt"}) == "allow"

    def test_deny_path_glob(self):
        mgr = PermissionManager({
            "path_rules": {
                "write_file": {
                    "always_allow_paths": ["/tmp/*"],
                    "always_deny_paths": ["/etc/*", "/usr/*"]
                }
            }
        })
        assert mgr.check_tool("write_file", {"path": "/etc/passwd"}) == "deny"
        assert mgr.check_tool("write_file", {"path": "/usr/bin/x"}) == "deny"
        assert mgr.check_tool("write_file", {"path": "/tmp/safe.txt"}) == "allow"

    def test_regex_path(self):
        mgr = PermissionManager({
            "path_rules": {
                "read_file": {
                    "always_deny_paths": ["re:.*\\.env$"]
                }
            }
        })
        assert mgr.check_tool("read_file", {"path": "/app/.env"}) == "deny"
        assert mgr.check_tool("read_file", {"path": "/app/config.json"}) == "fallthrough"

    def test_path_rules_other_tool_unaffected(self):
        mgr = PermissionManager({
            "path_rules": {
                "write_file": {"always_deny_paths": ["/etc/*"]}
            }
        })
        assert mgr.check_tool("read_file", {"path": "/etc/passwd"}) == "fallthrough"

    def test_path_rules_with_other_param_names(self):
        mgr = PermissionManager({
            "path_rules": {
                "fetch_url": {"always_deny_paths": ["/admin/*"]}
            }
        })
        assert mgr.check_tool("fetch_url", {"url": "/admin/secret"}) == "deny"
        assert mgr.check_tool("fetch_url", {"file": "/admin/secret"}) == "deny"

    def test_no_path_arg_falls_through(self):
        mgr = PermissionManager({
            "path_rules": {
                "write_file": {"always_deny_paths": ["/etc/*"]}
            }
        })
        assert mgr.check_tool("write_file", {"content": "x"}) == "fallthrough"


class TestMatchPath:

    def test_glob_simple(self):
        assert PermissionManager._match_path("/tmp/x.txt", "/tmp/*") is True
        assert PermissionManager._match_path("/etc/x.txt", "/tmp/*") is False

    def test_glob_question_mark(self):
        assert PermissionManager._match_path("/tmp/a.txt", "/tmp/?.txt") is True
        assert PermissionManager._match_path("/tmp/ab.txt", "/tmp/?.txt") is False

    def test_glob_double_star(self):
        assert PermissionManager._match_path("/tmp/a/b/c.txt", "/tmp/**") is True

    def test_regex_prefix(self):
        assert PermissionManager._match_path("/foo.env", "re:.*\\.env$") is True
        assert PermissionManager._match_path("/foo.txt", "re:.*\\.env$") is False

    def test_invalid_regex_treated_as_no_match(self):
        assert PermissionManager._match_path("/foo", "re:[invalid(") is False

    def test_empty_pattern(self):
        assert PermissionManager._match_path("/foo", "") is False


class TestUpdate:

    def test_update_always_allow(self):
        mgr = PermissionManager()
        mgr.update(always_allow=["read_file", "search_web"])
        assert "read_file" in mgr.always_allow
        assert "search_web" in mgr.always_allow

    def test_update_always_deny(self):
        mgr = PermissionManager()
        mgr.update(always_deny=["rm_rf"])
        assert "rm_rf" in mgr.always_deny


class TestDescribe:

    def test_describe_empty(self):
        mgr = PermissionManager()
        out = mgr.describe()
        assert "无" in out or "默认" in out

    def test_describe_with_rules(self):
        mgr = PermissionManager({
            "always_allow": ["read_file"],
            "always_deny": ["delete_file"],
            "path_rules": {
                "write_file": {"always_deny_paths": ["/etc/*"]}
            }
        })
        out = mgr.describe()
        assert "read_file" in out
        assert "delete_file" in out
        assert "write_file" in out
        assert "/etc/*" in out


class TestLoadSave:

    def test_load_from_cfg(self):
        cfg = {
            "permissions": {
                "always_allow": ["x"],
                "always_deny": ["y"],
            }
        }
        mgr = load_permissions(cfg)
        assert "x" in mgr.always_allow
        assert "y" in mgr.always_deny

    def test_load_empty(self):
        mgr = load_permissions({})
        assert mgr.always_allow == set()

    def test_save_back_to_cfg(self):
        cfg = {}
        mgr = PermissionManager({"always_allow": ["a"]})
        save_permissions(cfg, mgr)
        assert cfg["permissions"]["always_allow"] == ["a"]


class TestPriorityOrder:

    def test_deny_overrides_all(self):
        mgr = PermissionManager({
            "always_allow": ["read_file"],
            "always_deny": ["read_file"],
            "ask_each_time": ["read_file"],
        })
        assert mgr.check_tool("read_file") == "deny"

    def test_path_allow_doesnt_override_deny(self):
        mgr = PermissionManager({
            "always_deny": ["write_file"],
            "path_rules": {"write_file": {"always_allow_paths": ["/*"]}},
        })
        assert mgr.check_tool("write_file", {"path": "/tmp/x"}) == "deny"
