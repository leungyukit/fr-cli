"""
Per-tool 权限精细化 —— 在 sec_* 类别基础上加 tool 级控制

格式(在 ~/.fr_cli/config.json 或 .fr_cli/config.json):
{
  "permissions": {
    "always_allow": ["search_web", "read_file"],      # 永远不需要确认
    "always_deny":  ["delete_file"],                   # 永远拒绝
    "ask_each_time": ["git_commit"],                   # 每次都问(覆盖 sec_* 默认)
    "path_rules": {                                    # 按参数值匹配
      "write_file": {
        "always_allow_paths": ["/tmp/*"],              # /tmp/* 写入允许
        "always_deny_paths": ["/etc/*", "/usr/*"]      # 系统路径拒绝
      }
    }
  }
}

与 sec_* 配合:
  - 先检查 tool 级 always_deny/always_allow
  - 再检查 path_rules
  - 最后走 sec_* 询问
"""
import fnmatch
import re
from typing import Dict, Optional, Any


class PermissionManager:
    """Tool 级权限管理"""

    def __init__(self, permissions: Optional[Dict[str, Any]] = None):
        self.permissions = permissions or {}
        self.always_allow = set(self.permissions.get("always_allow", []))
        self.always_deny = set(self.permissions.get("always_deny", []))
        self.ask_each_time = set(self.permissions.get("ask_each_time", []))
        self.path_rules = self.permissions.get("path_rules", {})

    def check_tool(self, tool_name: str, tool_args: Optional[Dict[str, Any]] = None) -> str:
        """检查工具权限

        Returns:
            "allow" / "deny" / "ask" / "fallthrough"
            - allow: 允许(无需询问)
            - deny: 拒绝
            - ask: 需要询问
            - fallthrough: 走 sec_* 默认行为
        """
        # 1. tool 级 always_deny
        if tool_name in self.always_deny:
            return "deny"

        # 2. tool 级 always_allow
        if tool_name in self.always_allow:
            # 但还要检查 path_rules(可能仍要 deny)
            if tool_name in self.path_rules:
                path_decision = self._check_path_rules(tool_name, tool_args or {})
                if path_decision == "deny":
                    return "deny"
                if path_decision == "allow":
                    return "allow"
            return "allow"

        # 3. path_rules(对非 always_allow 的 tool 也生效)
        if tool_name in self.path_rules:
            path_decision = self._check_path_rules(tool_name, tool_args or {})
            if path_decision == "deny":
                return "deny"
            if path_decision == "allow":
                return "allow"

        # 4. ask_each_time(强制询问)
        if tool_name in self.ask_each_time:
            return "ask"

        # 5. fallthrough 到 sec_*
        return "fallthrough"

    def _check_path_rules(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """检查路径规则

        Returns:
            "allow" / "deny" / "fallthrough"
        """
        rules = self.path_rules.get(tool_name, {})
        allow_paths = rules.get("always_allow_paths", [])
        deny_paths = rules.get("always_deny_paths", [])

        # 找到 path 参数(常见参数名)
        path_value = tool_args.get("path") or tool_args.get("file") or tool_args.get("url")
        if not path_value or not isinstance(path_value, str):
            return "fallthrough"

        # 先检查 deny
        for pattern in deny_paths:
            if self._match_path(path_value, pattern):
                return "deny"

        # 再检查 allow
        for pattern in allow_paths:
            if self._match_path(path_value, pattern):
                return "allow"

        return "fallthrough"

    @staticmethod
    def _match_path(path_value: str, pattern: str) -> bool:
        """路径匹配:支持 glob(* ?)和正则(以 re: 开头)"""
        if not pattern:
            return False
        if pattern.startswith("re:"):
            # 正则模式
            try:
                return bool(re.search(pattern[3:], path_value))
            except re.error:
                return False
        # glob 模式
        return fnmatch.fnmatch(path_value, pattern)

    def update(self, **kwargs):
        """更新权限配置"""
        for key, value in kwargs.items():
            if key == "always_allow":
                self.always_allow = set(value)
                self.permissions["always_allow"] = value
            elif key == "always_deny":
                self.always_deny = set(value)
                self.permissions["always_deny"] = value
            elif key == "ask_each_time":
                self.ask_each_time = set(value)
                self.permissions["ask_each_time"] = value
            elif key == "path_rules":
                self.path_rules = value
                self.permissions["path_rules"] = value

    def to_dict(self) -> Dict[str, Any]:
        return self.permissions

    def describe(self) -> str:
        """生成可读的权限摘要"""
        lines = ["权限规则:"]
        if self.always_allow:
            lines.append(f"  永远允许: {', '.join(sorted(self.always_allow))}")
        if self.always_deny:
            lines.append(f"  永远拒绝: {', '.join(sorted(self.always_deny))}")
        if self.ask_each_time:
            lines.append(f"  每次询问: {', '.join(sorted(self.ask_each_time))}")
        if self.path_rules:
            lines.append("  路径规则:")
            for tool, rules in self.path_rules.items():
                allow = rules.get("always_allow_paths", [])
                deny = rules.get("always_deny_paths", [])
                if allow:
                    lines.append(f"    {tool}.allow: {', '.join(allow)}")
                if deny:
                    lines.append(f"    {tool}.deny: {', '.join(deny)}")
        if len(lines) == 1:
            return "权限规则: 无(全部走 sec_* 默认)"
        return "\n".join(lines)


def load_permissions(cfg: Dict[str, Any]) -> PermissionManager:
    """从 config 加载权限"""
    return PermissionManager(cfg.get("permissions", {}))


def save_permissions(cfg: Dict[str, Any], manager: PermissionManager) -> None:
    """保存权限到 config"""
    cfg["permissions"] = manager.to_dict()
