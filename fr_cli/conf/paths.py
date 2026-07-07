"""
fr-cli 配置文件路径集中管理 —— 单一真相源

所有 ~/.fr_cli/ 下的路径都在这里定义。
旧路径（~/.zhipu_cli_* 和散落的 ~/.fr_cli_*）会在首次启动时自动迁移到新位置。

设计目标：
1. 单一根目录 ~/.fr_cli/，不再有散落根目录的 ~/.zhipu_cli_*/.fr_cli_* 文件
2. 旧路径自动迁移 → 新路径（用户无感切换）
3. 旧路径兼容层：read 仍能从旧路径读（迁移没完成时不丢数据）
4. 一次迁移后置位标志，避免重复 IO
5. 所有路径都通过 __getattr__ 动态计算，方便测试 monkeypatch ROOT
"""
import shutil
from pathlib import Path

# =================================================================
# 单一根目录（可被 monkeypatch 改写）
# =================================================================
class _RootHolder:
    """轻量级 ROOT 容器，方便测试 monkeypatch.setattr 修改 value"""
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value


_root_holder = _RootHolder(Path.home() / ".fr_cli")


def __getattr__(name):
    """所有路径都通过 __getattr__ 动态计算 ROOT / xxx。

    这样测试可以 monkeypatch _root_holder 后立即看到新路径，
    而不必逐个 patch 几十个路径常量。
    """
    if name == "ROOT":
        return _root_holder.value
    if name == "USAGE_FILE":
        return _root_holder.value / "usage.json"

    # 配置
    if name == "CONFIG_FILE":
        return _root_holder.value / "config.json"
    if name == "CONFIG_BACKUP":
        return _root_holder.value / "config.json.bak"
    if name == "CONTEXT_FILE":
        return _root_holder.value / "context.json"
    if name == "MODELS_YAML":
        return _root_holder.value / "models.yaml"

    # 会话
    if name == "SESSIONS_DIR":
        return _root_holder.value / "sessions"
    if name == "SESSIONS_MANUAL_DIR":
        return _root_holder.value / "sessions" / "manual"
    if name == "SESSIONS_AUTO_DIR":
        return _root_holder.value / "sessions" / "auto"

    # 扩展
    if name == "PLUGIN_DIR":
        return _root_holder.value / "plugins"
    if name == "AGENTS_DIR":
        return _root_holder.value / "agents"
    if name == "MASTER_DIR":
        return _root_holder.value / "master"

    # 远程
    if name == "REMOTE_DIR":
        return _root_holder.value / "remote"
    if name == "REMOTE_AGENTS_FILE":
        return _root_holder.value / "remote" / "agents.json"
    if name == "REMOTE_HOSTS_FILE":
        return _root_holder.value / "remote" / "hosts.json"

    # 业务配置
    if name == "DATABASE_FILE":
        return _root_holder.value / "database.json"
    if name == "M365_FILE":
        return _root_holder.value / "m365.json"
    if name == "GATEWAY_FILE":
        return _root_holder.value / "gateway.json"
    if name == "PERSONALITIES_FILE":
        return _root_holder.value / "personalities.json"
    if name == "SKILLS_DIR":
        return _root_holder.value / "skills"
    if name == "IMAGE_CONFIG_FILE":
        return _root_holder.value / "image_config.json"
    if name == "REGISTRY_FILE":
        return _root_holder.value / "registry.json"
    if name == "CONTEXT_FILES_FILE":
        return _root_holder.value / "context_files.json"

    # MCP
    if name == "MCP_DIR":
        return _root_holder.value / "mcp"
    if name == "MCP_SERVERS_FILE":
        return _root_holder.value / "mcp" / "servers.json"

    # 守护进程
    if name == "DAEMON_DIR":
        return _root_holder.value / "daemon"
    if name == "DAEMON_CONFIG_FILE":
        return _root_holder.value / "daemon" / "config.json"
    if name == "DAEMON_PID_FILE":
        return _root_holder.value / "daemon" / "daemon.pid"
    if name == "DAEMON_STOP_FILE":
        return _root_holder.value / "daemon" / "daemon.stop"
    if name == "DAEMON_TOKEN_FILE":
        return _root_holder.value / "daemon" / "token"
    if name == "DAEMON_HERMES_CONFIG_FILE":
        return _root_holder.value / "daemon" / "hermes_config.json"

    # Hermes
    if name == "HERMES_DIR":
        return _root_holder.value / "hermes"
    if name == "HERMES_TASKS_FILE":
        return _root_holder.value / "hermes" / "tasks.json"
    if name == "HERMES_GOALS_FILE":
        return _root_holder.value / "hermes" / "goals.json"
    if name == "HERMES_ANALYTICS_FILE":
        return _root_holder.value / "hermes" / "analytics.json"
    if name == "HERMES_LOG_FILE":
        return _root_holder.value / "hermes" / "hermes.log"
    if name == "HERMES_REVIEW_QUEUE_FILE":
        return _root_holder.value / "hermes" / "review_queue.json"
    if name == "HERMES_MEMORY_FILE":
        return _root_holder.value / "hermes" / "memory.json"
    if name == "ERROR_LEDGER_FILE":
        return _root_holder.value / "error_ledger.json"
    if name == "HERMES_DAEMON_CONFIG_FILE":
        return _root_holder.value / "hermes" / "daemon.json"
    if name == "HERMES_DAEMON_PID_FILE":
        return _root_holder.value / "hermes" / "daemon.pid"
    if name == "HERMES_DAEMON_STOP_FILE":
        return _root_holder.value / "hermes" / "daemon.stop"

    # RAG
    if name == "RAG_DIR":
        return _root_holder.value / "rag"
    if name == "RAG_DB_DIR":
        return _root_holder.value / "rag" / "db"
    if name == "RAG_WATCHER_PID_FILE":
        return _root_holder.value / "rag" / "watcher.pid"
    if name == "RAG_WATCHER_STOP_FILE":
        return _root_holder.value / "rag" / "watcher.stop"
    if name == "RAG_WATCHER_LOG_FILE":
        return _root_holder.value / "rag" / "watcher.log"

    raise AttributeError(f"module 'fr_cli.conf.paths' has no attribute {name!r}")


# =================================================================
# 旧路径 → 新路径 迁移映射
# =================================================================
def _migration_map():
    """动态计算迁移映射（基于当前 ROOT）"""
    root = _root_holder.value
    return {
        # 主配置
        Path.home() / ".zhipu_cli_config.json": root / "config.json",
        Path.home() / ".zhipu_cli_config.json.bak": root / "config.json.bak",
        # 短期摘要
        Path.home() / ".zhipu_cli_context.json": root / "context.json",
        # 会话存档
        Path.home() / ".zhipu_cli_history": root / "sessions" / "manual",
        Path.home() / ".fr_cli_sessions": root / "sessions" / "auto",
        # 插件
        Path.home() / ".zhipu_cli_plugins": root / "plugins",
        # Agent 分身
        Path.home() / ".fr_cli_agents": root / "agents",
        # MasterAgent
        Path.home() / ".fr_cli_master": root / "master",
        # 远程
        Path.home() / ".fr_cli_remote_agents.json": root / "remote" / "agents.json",
        Path.home() / ".fr_cli_remotes.json": root / "remote" / "hosts.json",
        # 数据库
        Path.home() / ".fr_cli_databases.json": root / "database.json",
        # MCP（之前有两套，合并）
        Path.home() / ".fr_cli" / "mcp_servers.json": root / "mcp" / "servers.json",
        # Gatekeeper
        Path.home() / ".fr_cli_gatekeeper.json": root / "daemon" / "config.json",
        Path.home() / ".fr_cli_gatekeeper.pid": root / "daemon" / "daemon.pid",
        Path.home() / ".fr_cli_gatekeeper.stop": root / "daemon" / "daemon.stop",
        # Hermes
        Path.home() / ".fr_cli_hermes.token": root / "daemon" / "token",
        Path.home() / ".fr_cli" / "config.json": root / "daemon" / "hermes_config.json",
        # RAG
        Path.home() / ".fr_cli_rag_db": root / "rag" / "db",
        Path.home() / ".fr_cli_rag_watcher.pid": root / "rag" / "watcher.pid",
        Path.home() / ".fr_cli_rag_watcher.stop": root / "rag" / "watcher.stop",
        Path.home() / ".fr_cli_rag_watcher.log": root / "rag" / "watcher.log",
        # 其他
        Path.home() / ".fr_cli_image_config.json": root / "image_config.json",
        Path.home() / ".fr_cli_agent_registry.json": root / "registry.json",
        Path.home() / ".fr_cli" / "gateway.json": root / "gateway.json",
        Path.home() / ".fr_cli" / "personalities.json": root / "personalities.json",
        Path.home() / ".fr_cli" / "skills": root / "skills",
        Path.home() / ".fr_cli" / "models.yaml": root / "models.yaml",
        Path.home() / ".fr_cli" / "context_files.json": root / "context_files.json",
    }


# 保留向后兼容（一些代码可能直接 import 这个变量名）
_MIGRATION_MAP = _migration_map()


# =================================================================
# 迁移（一次性）
# =================================================================
_migrated = False


def migrate(verbose: bool = False):
    """把所有旧路径的文件/目录迁移到新位置（一次性，运行后置位）"""
    global _migrated
    if _migrated:
        return 0
    _migrated = True

    root = _root_holder.value
    root.mkdir(parents=True, exist_ok=True)
    moved = 0
    for old, new in _migration_map().items():
        if not old.exists() or new.exists():
            continue
        try:
            new.parent.mkdir(parents=True, exist_ok=True)
            if old.is_dir():
                shutil.copytree(str(old), str(new))
            else:
                shutil.copy2(str(old), str(new))
            moved += 1
            if verbose:
                print(f"  迁移: {old.name} → {new}")
        except Exception as e:
            if verbose:
                print(f"  跳过: {old.name} ({e})")
    return moved


def reset_migration_flag():
    """仅供测试：重置迁移标志"""
    global _migrated
    _migrated = False


# =================================================================
# 兼容层：read-with-fallback（仅用于关键配置文件）
# =================================================================
def read_with_fallback(primary: Path, fallbacks: list, binary: bool = False) -> bytes | str | None:
    """按优先级读取：先 primary，再 fallbacks。

    用于主配置等需要向后兼容的关键文件。读取不会触发迁移，
    迁移在启动时统一做。
    """
    if primary.exists():
        return primary.read_bytes() if binary else primary.read_text(encoding="utf-8")
    for fb in fallbacks:
        if fb.exists():
            return fb.read_bytes() if binary else fb.read_text(encoding="utf-8")
    return None


def ensure_dir(p: Path) -> Path:
    """确保目录存在，返回 Path"""
    p.mkdir(parents=True, exist_ok=True)
    return p
