"""
子 Agent 统一注册表 —— 把本地 / 远程 / 内置 / 动态 Agent 收敛成一个统一视图

背景: 子 Agent 目前分散在四处 ——
- ``fr_cli/agent/manager.py``  本地 Agent 目录（``~/.fr_cli/agents/<name>/``）
- ``fr_cli/agent/client.py``   远程 Agent（HTTP API）
- ``fr_cli/agent/dispatch.py`` 内置 Agent（``BUILTIN_AGENTS`` 路由表）
- 动态注册（动态构建 / 插件）

本模块提供**只读的统一视图 + 动态注册入口**, 供 ``/agent_list`` 等场景查询。
它**不改动** ``dispatch_agent_call`` 等既有调用路径 —— 老逻辑继续按原路径工作。

用法:
    >>> from fr_cli.agent.registry import get_agent_registry
    >>> reg = get_agent_registry()
    >>> reg.refresh()
    >>> print(reg.describe())
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

__all__ = [
    "AgentEntry",
    "AgentRegistry",
    "get_agent_registry",
    "reset_agent_registry",
]


# 内置 Agent 的中文说明（describe() 用）
_BUILTIN_DESCRIPTIONS: Dict[str, str] = {
    "local": "本地系统操作（文件/进程/磁盘）",
    "remote": "远程 SSH 操作",
    "spider": "智能网页爬虫",
    "db": "数据库智能助手（MySQL/PG/MSSQL/Oracle）",
    "RAG": "本地知识库问答（ChromaDB）",
    "stock": "股票/量化交易助手",
}

# kind → 中文标签
_KIND_LABELS: Dict[str, str] = {
    "local": "本地",
    "remote": "远程",
    "builtin": "内置",
    "dynamic": "动态",
}


@dataclass
class AgentEntry:
    """统一视图里的一条 Agent 记录。"""

    name: str
    kind: str                       # "local" | "remote" | "builtin" | "dynamic"
    description: str = ""
    persona: str = ""
    source: str = ""                # 目录路径 / 远程 host / 内置名
    callable: Optional[Callable] = None   # kind=="builtin" 时为执行函数
    enabled: bool = True
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def kind_label(self) -> str:
        """kind 的中文标签。"""
        return _KIND_LABELS.get(self.kind, self.kind)


class AgentRegistry:
    """子 Agent 统一注册表。

    线程安全: 注册/查询都走可重入锁, 动态注册与并发查询互不干扰。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: Dict[str, AgentEntry] = {}

    # ---------- 基础增删查 ----------

    def register(self, entry: AgentEntry) -> AgentEntry:
        """注册（或覆盖）一个 Agent 记录。"""
        if not isinstance(entry, AgentEntry):
            raise TypeError("register() 只接受 AgentEntry")
        with self._lock:
            self._entries[entry.name] = entry
        return entry

    def unregister(self, name: str) -> bool:
        """注销一个 Agent 记录，返回是否真的移除。"""
        with self._lock:
            return self._entries.pop(name, None) is not None

    def get(self, name: str) -> Optional[AgentEntry]:
        """按名字取记录。"""
        with self._lock:
            return self._entries.get(name)

    def list(self, kind: Optional[str] = None) -> List[AgentEntry]:
        """列出记录；给定 kind 时只列出该类。"""
        with self._lock:
            items = list(self._entries.values())
        if kind is None:
            return items
        return [e for e in items if e.kind == kind]

    def names(self, kind: Optional[str] = None) -> List[str]:
        """列出 Agent 名字。"""
        return [e.name for e in self.list(kind)]

    # ---------- 各来源加载 ----------

    def load_local(self) -> List[AgentEntry]:
        """扫描本地 Agent 目录（``fr_cli.agent.manager.list_agents``）。"""
        from fr_cli.agent.manager import list_agents, load_agent_description, load_persona

        entries: List[AgentEntry] = []
        for info in list_agents() or []:
            name = info.get("name", "")
            if not name:
                continue
            try:
                description = load_agent_description(name)
            except Exception:
                description = ""
            if not description:
                description = (
                    f"本地Agent (人设:{'有' if info.get('has_persona') else '无'}, "
                    f"记忆:{'有' if info.get('has_memory') else '无'}, "
                    f"技能:{'有' if info.get('has_skills') else '无'})"
                )
            try:
                persona = load_persona(name)
            except Exception:
                persona = ""
            entries.append(AgentEntry(
                name=name,
                kind="local",
                description=description,
                persona=persona,
                source=info.get("path", ""),
                meta={
                    "has_persona": bool(info.get("has_persona")),
                    "has_memory": bool(info.get("has_memory")),
                    "has_skills": bool(info.get("has_skills")),
                    "has_config": bool(info.get("has_config")),
                },
            ))
        return entries

    def load_builtin(self) -> List[AgentEntry]:
        """从 ``fr_cli.agent.dispatch.BUILTIN_AGENTS`` 路由表加载内置 Agent。"""
        from fr_cli.agent.dispatch import BUILTIN_AGENTS
        from fr_cli.agent.client import call_builtin_agent

        entries: List[AgentEntry] = []
        for name in BUILTIN_AGENTS:
            # call_builtin_agent(name, user_input, state) → 绑定 name 后
            # 调用约定统一为 callable(user_input, state)
            entries.append(AgentEntry(
                name=name,
                kind="builtin",
                description=_BUILTIN_DESCRIPTIONS.get(name, f"内置 Agent: {name}"),
                source=name,
                callable=lambda user_input="", state=None, _n=name: call_builtin_agent(_n, user_input, state),
                meta={"route": list(BUILTIN_AGENTS[name]) if isinstance(BUILTIN_AGENTS[name], (list, tuple)) else str(BUILTIN_AGENTS[name])},
            ))
        return entries

    def load_remote(self, registry_cfg: Optional[Dict[str, Any]] = None) -> List[AgentEntry]:
        """加载远程 Agent。

        Args:
            registry_cfg: 远程 Agent 配置映射(name -> {host, port, token, description});
                为 None 时从 ``fr_cli.agent.remote.list_remote_agents()`` 读取。
        """
        if registry_cfg is None:
            from fr_cli.agent.remote import list_remote_agents
            registry_cfg = list_remote_agents() or {}

        entries: List[AgentEntry] = []
        for name, cfg in (registry_cfg or {}).items():
            cfg = cfg or {}
            host = cfg.get("host", "")
            port = cfg.get("port", "")
            description = cfg.get("description") or (
                f"远程Agent @ {host}:{port}" if host else "远程Agent"
            )
            entries.append(AgentEntry(
                name=name,
                kind="remote",
                description=description,
                source=f"{host}:{port}" if host else "",
                meta={
                    "host": host,
                    "port": port,
                    "token": cfg.get("token", ""),
                },
            ))
        return entries

    # ---------- 汇总 ----------

    def refresh(self) -> List[AgentEntry]:
        """重新扫描全部来源（本地 / 内置 / 远程），保留动态注册项。

        Returns:
            当前全部记录（按 kind 分组顺序: local → builtin → remote → dynamic）。
        """
        local = self.load_local()
        builtin = self.load_builtin()
        remote = self.load_remote()

        with self._lock:
            dynamic = [e for e in self._entries.values() if e.kind == "dynamic"]
            self._entries.clear()
            for entry in local + builtin + remote + dynamic:
                self._entries[entry.name] = entry
            return list(self._entries.values())

    def describe(self) -> str:
        """生成人类可读摘要（给 ``/agent_list`` 用）。"""
        entries = self.list()
        if not entries:
            return "Agent 总览: 无可用 Agent"

        lines = [f"Agent 总览（共 {len(entries)} 个）:"]
        order = ("local", "builtin", "remote", "dynamic")
        for kind in order:
            group = [e for e in entries if e.kind == kind]
            if not group:
                continue
            lines.append(f"  [{_KIND_LABELS.get(kind, kind)}]")
            for entry in group:
                desc = entry.description or "（无描述）"
                flag = "" if entry.enabled else "（已禁用）"
                lines.append(f"    - {entry.name}{flag}: {desc}")
        return "\n".join(lines)


# ------------------------------------------------------------------
# 模块级单例
# ------------------------------------------------------------------
_registry_instance: Optional[AgentRegistry] = None
_registry_lock = threading.RLock()


def get_agent_registry() -> AgentRegistry:
    """获取全局 Agent 注册表单例（懒创建）。"""
    global _registry_instance
    with _registry_lock:
        if _registry_instance is None:
            _registry_instance = AgentRegistry()
        return _registry_instance


def reset_agent_registry() -> None:
    """重置全局单例（测试用）。"""
    global _registry_instance
    with _registry_lock:
        _registry_instance = None
