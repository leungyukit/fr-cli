"""
Hooks 系统 —— 类似 Claude Code 的可扩展点

支持的事件:
  - PreToolUse:  工具调用前,可阻止/修改参数
  - PostToolUse: 工具调用后,可修改返回结果
  - UserPromptSubmit: 用户输入后,AI 处理前
  - SessionStart: 会话开始时
  - SessionEnd:   会话结束时
  - Notification: 通知事件(权限询问、错误等)

配置:
  用户级: ~/.fr_cli/hooks.json
  项目级: <cwd>/.fr_cli/hooks.json

配置格式:
{
  "PreToolUse": [
    {
      "matcher": "write_file|delete_file",  # 工具名匹配正则,留空匹配所有
      "type": "command",  # command / internal
      "command": "echo blocked",  # shell 命令
      "description": "禁止写入到 /etc"
    }
  ],
  "PostToolUse": [...]
}

行为:
  - PreToolUse 返回 exit code 2 → 阻止工具执行
  - PreToolUse 修改 stdout → 注入到工具的 args
  - PostToolUse 修改 stdout → 替换工具返回值
"""
import json
import re
import subprocess
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any


# Hook 事件类型 —— 向后兼容:HOOK_EVENTS 也从 fr_cli.core.events 导出
from fr_cli.core.events import HOOK_EVENTS  # noqa: E402,F401

# 阻止工具执行的特殊退出码(Claude Code 风格)
EXIT_CODE_BLOCK = 2


class Hook:
    """单个 hook 定义"""

    def __init__(self, event: str, matcher: str = "", type_: str = "command",
                 command: str = "", description: str = ""):
        self.event = event
        self.matcher = matcher
        self.type = type_
        self.command = command
        self.description = description

    def matches(self, tool_name: Optional[str] = None, user_input: Optional[str] = None) -> bool:
        """判断 hook 是否匹配当前事件"""
        if not self.matcher:
            return True
        if tool_name and re.search(self.matcher, tool_name):
            return True
        if user_input and re.search(self.matcher, user_input):
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event,
            "matcher": self.matcher,
            "type": self.type,
            "command": self.command,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Hook":
        return cls(
            event=data.get("event", ""),
            matcher=data.get("matcher", ""),
            type_=data.get("type", "command"),
            command=data.get("command", ""),
            description=data.get("description", ""),
        )


class HookManager:
    """Hook 调度器"""

    def __init__(self, cfg: Optional[Dict[str, Any]] = None, cwd: Optional[Path] = None):
        self.cfg = cfg or {}
        self.cwd = cwd or Path.cwd()
        self.hooks: Dict[str, List[Hook]] = {}  # event -> list of Hook
        self._load()

    def _load(self):
        """加载 hooks 配置:用户级 + 项目级(项目级优先)"""
        # 1. 用户级
        user_hooks_file = Path.home() / ".fr_cli" / "hooks.json"
        if user_hooks_file.exists():
            self._load_file(user_hooks_file)

        # 2. 项目级(覆盖用户级)
        project_hooks_file = self.cwd / ".fr_cli" / "hooks.json"
        if project_hooks_file.exists():
            self._load_file(project_hooks_file)

        # 3. cfg["hooks"](最高优先级,运行时覆盖)
        cfg_hooks = self.cfg.get("hooks", {})
        for event, hooks_data in cfg_hooks.items():
            if event not in HOOK_EVENTS:
                continue
            if event not in self.hooks:
                self.hooks[event] = []
            for h in hooks_data:
                if isinstance(h, dict):
                    h["event"] = event
                    self.hooks[event].append(Hook.from_dict(h))

    def _load_file(self, path: Path):
        """从 JSON 文件加载 hooks"""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for event, hooks_data in data.items():
                if event not in HOOK_EVENTS:
                    continue
                if event not in self.hooks:
                    self.hooks[event] = []
                for h in hooks_data:
                    if isinstance(h, dict):
                        h["event"] = event
                        self.hooks[event].append(Hook.from_dict(h))
        except Exception:
            pass

    def get_hooks(self, event: str) -> List[Hook]:
        """获取某事件的所有 hooks"""
        return self.hooks.get(event, [])

    def run_pre_tool_use(self, tool_name: str, tool_args: Dict[str, Any],
                         timeout: int = 5) -> "HookResult":
        """执行 PreToolUse hooks

        Returns:
            HookResult(blocked, modified_args, messages)

        Side effects:
            - 匹配到 hook 时,通过 v3 EventBus 发布 "PreToolUse" 事件(供解耦的观察者监听)
            - 若 v3 EventBus 返回 stop_propagation,仍以本地结果为准(向后兼容)
        """
        hooks = [h for h in self.get_hooks("PreToolUse") if h.matches(tool_name=tool_name)]
        if not hooks:
            return HookResult(blocked=False)

        result = HookResult(blocked=False)
        for hook in hooks:
            hook_result = self._run_command_hook(hook, {
                "tool_name": tool_name,
                "tool_args": tool_args,
            }, timeout=timeout)
            result.messages.extend(hook_result.messages)
            if hook_result.blocked:
                result.blocked = True
                result.reason = hook_result.reason
                # 阻止后立即停止
                break
            # 修改参数(如果 hook 有 stdout)
            if hook_result.modified_args:
                result.modified_args.update(hook_result.modified_args)

        # v3 bus 通知(解耦的观察者用,不参与控制流)
        try:
            from fr_cli.core.events import dispatch_event, V2HookEvents
            dispatch_event(
                V2HookEvents.PRE_TOOL_USE,
                data={
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "blocked": result.blocked,
                    "reason": result.reason,
                    "modified_args": result.modified_args,
                    "matched_count": len(hooks),
                },
                source="hook_manager",
            )
        except Exception:
            pass

        return result

    def run_post_tool_use(self, tool_name: str, tool_args: Dict[str, Any],
                          tool_result: Any, timeout: int = 5) -> "HookResult":
        """执行 PostToolUse hooks

        Returns:
            HookResult(modified_args={"tool_result": tool_result | modified})
            没 hook 时 modified_args["tool_result"] = 原始 tool_result
        """
        # 默认保留原结果
        result = HookResult(blocked=False, modified_args={"tool_result": tool_result})

        hooks = [h for h in self.get_hooks("PostToolUse") if h.matches(tool_name=tool_name)]
        if not hooks:
            return result

        for hook in hooks:
            hook_result = self._run_command_hook(hook, {
                "tool_name": tool_name,
                "tool_args": tool_args,
                "tool_result": str(tool_result),
            }, timeout=timeout)
            result.messages.extend(hook_result.messages)
            # 如果 hook 输出了 JSON 包含 tool_result,替换之
            if hook_result.modified_args.get("tool_result"):
                result.modified_args["tool_result"] = hook_result.modified_args["tool_result"]

        # v3 bus 通知
        try:
            from fr_cli.core.events import dispatch_event, V2HookEvents
            dispatch_event(
                V2HookEvents.POST_TOOL_USE,
                data={
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "tool_result_modified": result.modified_args.get("tool_result"),
                    "matched_count": len(hooks),
                },
                source="hook_manager",
            )
        except Exception:
            pass

        return result

    def run_user_prompt_submit(self, user_input: str, timeout: int = 5) -> "HookResult":
        """UserPromptSubmit hook"""
        hooks = [h for h in self.get_hooks("UserPromptSubmit") if h.matches(user_input=user_input)]
        if not hooks:
            return HookResult(blocked=False)

        result = HookResult(blocked=False)
        for hook in hooks:
            hook_result = self._run_command_hook(hook, {
                "user_input": user_input,
            }, timeout=timeout)
            result.messages.extend(hook_result.messages)
            if hook_result.blocked:
                result.blocked = True
                result.reason = hook_result.reason
                break

        # v3 bus 通知
        try:
            from fr_cli.core.events import dispatch_event, V2HookEvents
            dispatch_event(
                V2HookEvents.USER_PROMPT_SUBMIT,
                data={
                    "user_input": user_input,
                    "blocked": result.blocked,
                    "reason": result.reason,
                    "matched_count": len(hooks),
                },
                source="hook_manager",
            )
        except Exception:
            pass

        return result

    def _run_command_hook(self, hook: Hook, payload: Dict[str, Any],
                          timeout: int = 5) -> "HookResult":
        """执行一个 command 类型 hook"""
        if hook.type != "command" or not hook.command:
            return HookResult(blocked=False)

        # payload 作为 JSON 通过 stdin 传给 hook
        try:
            proc = subprocess.run(
                hook.command,
                shell=True,
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return HookResult(blocked=False, messages=[f"hook 超时: {hook.description}"])
        except Exception as e:
            return HookResult(blocked=False, messages=[f"hook 执行失败: {e}"])

        result = HookResult(blocked=False)
        result.messages.append(f"hook [{hook.description or hook.command[:30]}] stdout: {proc.stdout[:200]}")

        # 退出码 2 → 阻止(Claude Code 风格)
        if proc.returncode == EXIT_CODE_BLOCK:
            result.blocked = True
            result.reason = proc.stderr.strip() or "hook 阻止了工具调用"
            return result

        # 解析 stdout:支持纯文本替换 / JSON 格式
        stdout = proc.stdout.strip()
        if stdout:
            # 尝试 JSON
            try:
                parsed = json.loads(stdout)
                if isinstance(parsed, dict):
                    if parsed.get("block"):
                        result.blocked = True
                        result.reason = parsed.get("reason", "blocked by hook")
                    # 修改参数
                    if "modified_args" in parsed:
                        result.modified_args.update(parsed["modified_args"])
                    if "tool_result" in parsed:
                        result.modified_args["tool_result"] = parsed["tool_result"]
                return result
            except (json.JSONDecodeError, ValueError):
                pass
            # 纯文本 → 作为 modified tool_result(用于 PostToolUse)
            result.modified_args["tool_result"] = stdout

        return result

    def add_hook(self, hook: Hook):
        """注册一个新 hook"""
        if hook.event not in self.hooks:
            self.hooks[hook.event] = []
        # 去重
        self.hooks[hook.event] = [h for h in self.hooks[hook.event]
                                  if not (h.matcher == hook.matcher and h.command == hook.command)]
        self.hooks[hook.event].append(hook)

    def save_to_user_config(self):
        """保存当前 hooks 到用户配置文件"""
        output = {}
        for event, hooks in self.hooks.items():
            output[event] = [h.to_dict() for h in hooks]
        target = Path.home() / ".fr_cli" / "hooks.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        return target


class HookResult:
    """Hook 执行结果"""

    def __init__(self, blocked: bool = False, reason: str = "",
                 modified_args: Optional[Dict[str, Any]] = None,
                 messages: Optional[List[str]] = None):
        self.blocked = blocked
        self.reason = reason
        self.modified_args = modified_args or {}
        self.messages = messages or []

    def __repr__(self):
        return f"HookResult(blocked={self.blocked}, reason={self.reason!r}, msgs={len(self.messages)})"


# 全局实例
_hook_manager: Optional[HookManager] = None
_hook_lock = threading.Lock()


def get_hook_manager(cfg: Optional[Dict[str, Any]] = None,
                     cwd: Optional[Path] = None) -> HookManager:
    """获取全局 HookManager"""
    global _hook_manager
    if _hook_manager is None:
        with _hook_lock:
            if _hook_manager is None:
                _hook_manager = HookManager(cfg=cfg, cwd=cwd)
    return _hook_manager


def reset_hook_manager():
    """重置全局实例(测试用)"""
    global _hook_manager
    with _hook_lock:
        _hook_manager = None
