"""
fr-cli 配置文件路径集中管理 —— 单一真相源

所有 ~/.fr_cli/ 下的路径都在这里定义。
旧路径（~/.zhipu_cli_* 和散落的 ~/.fr_cli_*）会在首次启动时自动迁移到新位置。

设计目标：
1. 单一根目录 ~/.fr_cli/，不再有散落根目录的 ~/.zhipu_cli_*/.fr_cli_* 文件
2. 旧路径自动迁移 → 新路径（用户无感切换）
3. 旧路径兼容层：read 仍能从旧路径读（迁移没完成时不丢数据）
4. 一次迁移后置位标志，避免重复 IO
"""
import os
import shutil
from pathlib import Path

# =================================================================
# 单一根目录
# =================================================================
ROOT = Path.home() / ".fr_cli"


# =================================================================
# 旧路径 → 新路径 迁移映射
# =================================================================
_MIGRATION_MAP = {
    # 主配置
    Path.home() / ".zhipu_cli_config.json": ROOT / "config.json",
    Path.home() / ".zhipu_cli_config.json.bak": ROOT / "config.json.bak",
    # 短期摘要
    Path.home() / ".zhipu_cli_context.json": ROOT / "context.json",
    # 会话存档
    Path.home() / ".zhipu_cli_history": ROOT / "sessions" / "manual",
    Path.home() / ".fr_cli_sessions": ROOT / "sessions" / "auto",
    # 插件
    Path.home() / ".zhipu_cli_plugins": ROOT / "plugins",
    # Agent 分身
    Path.home() / ".fr_cli_agents": ROOT / "agents",
    # MasterAgent
    Path.home() / ".fr_cli_master": ROOT / "master",
    # 远程
    Path.home() / ".fr_cli_remote_agents.json": ROOT / "remote" / "agents.json",
    Path.home() / ".fr_cli_remotes.json": ROOT / "remote" / "hosts.json",
    # 数据库
    Path.home() / ".fr_cli_databases.json": ROOT / "database.json",
    # MCP（之前有两套，合并）
    Path.home() / ".fr_cli" / "mcp_servers.json": ROOT / "mcp" / "servers.json",
    # Gatekeeper
    Path.home() / ".fr_cli_gatekeeper.json": ROOT / "daemon" / "config.json",
    Path.home() / ".fr_cli_gatekeeper.pid": ROOT / "daemon" / "daemon.pid",
    Path.home() / ".fr_cli_gatekeeper.stop": ROOT / "daemon" / "daemon.stop",
    # Hermes
    Path.home() / ".fr_cli_hermes.token": ROOT / "daemon" / "token",
    Path.home() / ".fr_cli" / "config.json": ROOT / "daemon" / "hermes_config.json",
    # RAG
    Path.home() / ".fr_cli_rag_db": ROOT / "rag" / "db",
    Path.home() / ".fr_cli_rag_watcher.pid": ROOT / "rag" / "watcher.pid",
    Path.home() / ".fr_cli_rag_watcher.stop": ROOT / "rag" / "watcher.stop",
    Path.home() / ".fr_cli_rag_watcher.log": ROOT / "rag" / "watcher.log",
    # 其他
    Path.home() / ".fr_cli_image_config.json": ROOT / "image_config.json",
    Path.home() / ".fr_cli_agent_registry.json": ROOT / "registry.json",
    Path.home() / ".fr_cli" / "gateway.json": ROOT / "gateway.json",
    Path.home() / ".fr_cli" / "personalities.json": ROOT / "personalities.json",
    Path.home() / ".fr_cli" / "skills": ROOT / "skills",
    Path.home() / ".fr_cli" / "models.yaml": ROOT / "models.yaml",
    Path.home() / ".fr_cli" / "context_files.json": ROOT / "context_files.json",
}


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

    ROOT.mkdir(parents=True, exist_ok=True)
    moved = 0
    for old, new in _MIGRATION_MAP.items():
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
# 新路径常量（唯一权威）
# =================================================================
# 配置
CONFIG_FILE = ROOT / "config.json"
CONFIG_BACKUP = ROOT / "config.json.bak"
CONTEXT_FILE = ROOT / "context.json"
MODELS_YAML = ROOT / "models.yaml"

# 会话
SESSIONS_DIR = ROOT / "sessions"
SESSIONS_MANUAL_DIR = SESSIONS_DIR / "manual"
SESSIONS_AUTO_DIR = SESSIONS_DIR / "auto"

# 扩展
PLUGIN_DIR = ROOT / "plugins"
AGENTS_DIR = ROOT / "agents"
MASTER_DIR = ROOT / "master"

# 远程
REMOTE_DIR = ROOT / "remote"
REMOTE_AGENTS_FILE = REMOTE_DIR / "agents.json"
REMOTE_HOSTS_FILE = REMOTE_DIR / "hosts.json"

# 业务配置
DATABASE_FILE = ROOT / "database.json"
GATEWAY_FILE = ROOT / "gateway.json"
PERSONALITIES_FILE = ROOT / "personalities.json"
SKILLS_DIR = ROOT / "skills"
IMAGE_CONFIG_FILE = ROOT / "image_config.json"
REGISTRY_FILE = ROOT / "registry.json"
CONTEXT_FILES_FILE = ROOT / "context_files.json"

# MCP
MCP_DIR = ROOT / "mcp"
MCP_SERVERS_FILE = MCP_DIR / "servers.json"

# 守护进程
DAEMON_DIR = ROOT / "daemon"
DAEMON_CONFIG_FILE = DAEMON_DIR / "config.json"
DAEMON_PID_FILE = DAEMON_DIR / "daemon.pid"
DAEMON_STOP_FILE = DAEMON_DIR / "daemon.stop"
DAEMON_TOKEN_FILE = DAEMON_DIR / "token"
DAEMON_HERMES_CONFIG_FILE = DAEMON_DIR / "hermes_config.json"

# RAG
RAG_DIR = ROOT / "rag"
RAG_DB_DIR = RAG_DIR / "db"
RAG_WATCHER_PID_FILE = RAG_DIR / "watcher.pid"
RAG_WATCHER_STOP_FILE = RAG_DIR / "watcher.stop"
RAG_WATCHER_LOG_FILE = RAG_DIR / "watcher.log"


# =================================================================
# 兼容层：read-with-fallback（仅用于关键配置文件）
# =================================================================
def read_with_fallback(primary: Path, fallbacks: list, binary: bool = False) -> bytes | str | None:
    """按优先级读取：先 primary，再 fallbacks。

    用于主配置等需要向后兼容的关键文件。读取不会触发迁移，
    迁移在启动时统一做。
    """
    if primary.exists():
        mode = "rb" if binary else "r"
        return primary.read_bytes() if binary else primary.read_text(encoding="utf-8")
    for fb in fallbacks:
        if fb.exists():
            mode = "rb" if binary else "r"
            return fb.read_bytes() if binary else fb.read_text(encoding="utf-8")
    return None


def ensure_dir(p: Path) -> Path:
    """确保目录存在，返回 Path"""
    p.mkdir(parents=True, exist_ok=True)
    return p
