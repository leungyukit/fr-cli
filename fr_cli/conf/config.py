"""
配置文件读写与初始化引擎
支持原子写入与自动备份，防止写入中断损坏配置

新架构：所有路径都来自 fr_cli.conf.paths（单一真相源）。
旧路径在首次启动时由 paths.migrate() 自动迁移到新位置。
"""
import json
import os
import shutil
from pathlib import Path
from fr_cli.ui.ui import YELLOW, RED, GREEN, CYAN, RESET, DIM
from fr_cli.conf import paths as _paths
# 重新导出路径常量，方便测试 monkeypatch（生产代码用 _paths.XXX 访问）
# ruff: noqa: F401  -- 这些是测试兼容性的 re-export
from fr_cli.conf.paths import (
    CONFIG_FILE,        # noqa: F401  -- 测试通过 monkeypatch 覆盖
    CONFIG_BACKUP,      # noqa: F401  -- 测试通过 monkeypatch 覆盖
    ROOT,               # noqa: F401  -- 测试通过 monkeypatch 覆盖
    migrate as paths_migrate,
)

DEFAULT_WORKSPACE = Path.home() / "fr-cli-workspaces"
DEFAULT_LIMIT = 20000


def _default_config():
    """返回默认配置字典 —— provider/model 不再硬编码，由用户显式配置"""
    return {
        "version": 3,
        "key": "",
        # 注意：默认不设置 provider 和 model，由用户通过 /model config 显式配置
        # 未配置时状态栏显示'未配置'
        "limit": DEFAULT_LIMIT,
        "allowed_dirs": [],
        "lang": "zh",
        "aliases": {},
        "auto_confirm_forever": False,
        "autonomous_mode": "manual",
        "mail": {},
        "disk": {},
        "thinking_mode": "direct",
        "mcp": {"servers": []},
        "providers": {},
        # v2.8.7(P1-6)：MasterAgent ReAct 循环的运行时预算
        "master": {
            "max_steps": 8,          # 单次任务最大工具调用步数
            "max_repeat_calls": 3,  # 同一 tool+params 累计成功几次即判定死循环
            "step_retries": 1,      # 单步工具失败后的重试次数
        },
        # v3 新增：默认/备用模型（启动时优先用 default，default 不可用则降级到 backup）
        # 为空字符串表示"未设置"，启动时会进入向导引导配置
        "default_provider": "",
        "backup_provider": "",
        "ocr": {
            "provider": "",
            "model": "",
            "key": "",
            "base_url": "",
            "prompt": "",
        },
        "stock": {
            "default_source": "akshare",
            "akshare": {"enabled": True},
            "mairui": {"enabled": False, "key": "", "base_url": "https://api.mairui.club"},
            "tushare": {"enabled": False, "token": ""},
            "trade": {"enabled": False, "api": "", "key": "", "secret": "", "base_url": ""},
            "portfolio": {},
        },
        "banner_enabled": True,
        "splash_enabled": True,
        # v2.8.7(UX):首次启动的"快速上手"卡片是否已展示过
        "onboarding_card_shown": False,
        "splash_cols": 50,
        "splash_bg_threshold": 30,
        "context_compress_threshold": 4000,
        "context_compress_keep_recent": 5,
        # v2.8.7(P1-5):早期对话分层摘要的段数(1 = 退回单段合并的旧行为)
        "context_compress_tiers": 3,
        # v2.8.7(P0-2):LLM 单次请求超时秒数（0/None → 用客户端默认 60）
        # 瞬时错误（网络抖动/限流/5xx）会自动指数退避重试，重试次数由
        # fr_cli.core.llm.resilience.DEFAULT_RETRY 控制
        "llm_timeout": 0,
        # v3.1 新增：蜂群（swarm）整体超时秒数（0/None → 用默认 60）
        # 到达 deadline 后立即返回，未完成任务以超时条目返回（部分失败语义）
        "swarm_timeout": 60,
        # v2.8.9 新增：Agent Team 协作模式开关（/agent_team on|off）
        # 开启后普通对话自动走「拆解 → 多成员并行 → 聚合」流程
        "agent_team_enabled": False,
        # v2.8.12 新增：Agent Team 整体超时秒数（0/None → 用默认 180）
        # 与蜂群的 swarm_timeout 解耦：团队的每个子任务都是一次完整 LLM 生成，
        # reasoning 模型写中等长度内容常要 60~120 秒，用 60 秒必然整轮超时
        "agent_team_timeout": 180,
        # v3 新增：是否跳过首次启动向导（手动配置后置位）
        "model_wizard_skipped": False,
        # v3.1 新增:/start 5 步向导完成标志(避免重复弹)
        "start_wizard_done": False,
        # v3 新增：后台服务自启动偏好
        "autostart_on_launch": True,
    }


def _upgrade_schema(cfg):
    """把旧版配置升级到当前 schema（幂等执行）"""
    version = cfg.get("version", 1)
    if version >= 3:
        return cfg

    # v1 / v2 -> v3: 引入 default_provider / backup_provider 概念
    # 规则：若配置中已存在 provider，则把 provider 视为 default_provider；
    # backup_provider 默认空，由用户后续配置。
    if not cfg.get("default_provider") and cfg.get("provider"):
        cfg["default_provider"] = cfg["provider"]
    # 确保 backup_provider 字段存在
    cfg.setdefault("backup_provider", "")



    # 兼容老版本:确保 version 字段已升级
    if version < 2:
        # v1 -> v2: 将顶层 model 同步到当前 provider 的专属配置中
        provider = cfg.get("provider")
        if provider and cfg.get("model"):
            providers = cfg.setdefault("providers", {})
            pcfg = providers.setdefault(provider, {})
            if not pcfg.get("model"):
                pcfg["model"] = cfg["model"]

    cfg["version"] = 3
    return cfg


def load_config():
    """加载配置，如果缺失或损坏则返回带默认值的安全字典

    优先从新路径（CONFIG_FILE）读取；如不存在则尝试从旧路径（~/.zhipu_cli_config.json）读取。
    加载后会自动执行向后兼容迁移：将顶层 model 同步到当前 provider 的专属配置中，
    确保 provider-model 强绑定。
    """
    d = _default_config()

    # 每次动态计算路径，方便测试 monkeypatch ROOT
    config_file = _paths.CONFIG_FILE
    config_backup = _paths.CONFIG_BACKUP

    # 1. 尝试加载主配置文件（新路径）
    c = None
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                c = json.load(f)
        except Exception as e:
            print(f"{YELLOW}[!] 配置文件损坏: {e}{RESET}")

    # 2. 尝试从备份恢复
    if c is None and config_backup.exists():
        try:
            with open(config_backup, "r", encoding="utf-8") as f:
                c = json.load(f)
            print(f"{GREEN}[OK] 已从备份恢复配置{RESET}")
            shutil.copy2(config_backup, config_file)
        except Exception as e:
            print(f"{YELLOW}[!] 备份文件也损坏: {e}{RESET}")

    if c is None:
        print(f"{YELLOW}[!] 使用默认配置，请重新设置{RESET}")
        return d

    # schema 升级与向后兼容迁移（必须在补齐默认字段之前执行，
    # 否则默认值中的 version 会提前写入，导致升级逻辑被跳过）
    c = _upgrade_schema(c)

    # 补齐缺失字段（跳过 provider 和 model，由用户显式配置）
    for k, v in d.items():
        if k not in c and k not in ("provider", "model"):
            c[k] = v

    return c


def save_config(c):
    """将配置字典原子写入本地（先写临时文件再重命名，避免写入中断损坏配置）"""
    try:
        # 每次动态计算路径
        config_file = _paths.CONFIG_FILE
        config_backup = _paths.CONFIG_BACKUP

        # 确保新根目录存在
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # 1. 备份现有配置
        if config_file.exists():
            shutil.copy2(config_file, config_backup)

        # 2. 使用安全临时文件（随机名称 + 600 权限）
        import tempfile
        fd, tmp_path = tempfile.mkstemp(dir=config_file.parent, suffix=".json.tmp")
        try:
            os.chmod(tmp_path, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(c, f, indent=4, ensure_ascii=False)
            Path(tmp_path).replace(config_file)
        except Exception:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            raise
        return True
    except Exception as e:
        print(f"{RED}[x] 保存配置失败: {e}{RESET}")
        return False


class ConfigError(Exception):
    """配置初始化异常（替代 exit，避免作为库导入时终止进程）"""
    pass


def save_config_merge(c):
    """合并式保存：读磁盘上的完整配置，用 ``c`` 的键覆盖后整份写回。

    与 :func:`save_config` 的区别在于语义：

    - ``save_config(c)`` 是**整文件替换** —— ``c`` 里没有的键，磁盘上那些键就没了。
      传一个局部字典进去，等于把用户其余配置全部抹掉。
    - ``save_config_merge(c)`` 先读磁盘上的现有配置，再逐键覆盖，
      因此"只改一个字段"的场景不会误删其他字段。

    典型用法：设置一次性标记（如 ``onboarding_card_shown``）。

    Args:
        c: 要合并进磁盘配置的字典，只需包含要改的字段

    Returns:
        bool: 是否保存成功
    """
    try:
        # 文件不存在时不做"使用默认配置"的提示，直接以传入字典为准
        disk = load_config() if _paths.CONFIG_FILE.exists() else {}
        disk.update(c or {})
        return save_config(disk)
    except Exception as e:
        print(f"{RED}[x] 合并保存配置失败: {e}{RESET}")
        return False


def load_namespace(key, default=None, old_path=None):
    """从主配置 config.json 的命名空间中读取数据。

    key 支持点分路径，如 "hermes.daemon" 对应 cfg["hermes"]["daemon"]。

    default 接受类型（dict / list）或实例；传类型时会自动实例化，
    避免调用方误把 dict 类当 dict 实例使用。

    若 old_path 指定的旧独立配置文件存在且主配置中该命名空间为空，
    则一次性迁移旧文件内容到主配置并保存。
    """
    if default is None:
        default = {}
    # 兼容传类型的情况
    if default is dict:
        default = {}
    elif default is list:
        default = []
    cfg = load_config()
    data = _get_nested(cfg, key)
    if data is not None:
        return data

    # 尝试迁移旧文件
    if old_path is not None:
        old_path = Path(old_path)
        if old_path.exists():
            try:
                old_data = json.loads(old_path.read_text(encoding="utf-8"))
                if old_data:
                    _set_nested(cfg, key, old_data)
                    save_config(cfg)
                    try:
                        old_path.rename(str(old_path) + ".migrated")
                    except Exception:
                        pass
                    return old_data
            except Exception:
                pass

    return default


def save_namespace(key, value):
    """把数据写入主配置 config.json 的命名空间并持久化。

    key 支持点分路径。
    """
    cfg = load_config()
    _set_nested(cfg, key, value)
    save_config(cfg)


def _get_nested(cfg, key):
    """支持点分路径的取值"""
    parts = key.split(".")
    cur = cfg
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def _set_nested(cfg, key, value):
    """支持点分路径的赋值"""
    parts = key.split(".")
    cur = cfg
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def init_config(*, force_wizard: bool = False, interactive: bool = None):
    """首次运行引导：迁移旧配置 → 检查并引导模型配置 → 自动创建默认工作空间

    Args:
        force_wizard: 强制进入向导(例如 /model setup 调用)
        interactive: 是否允许交互式输入。None 时根据 stdin 是否 tty 自动判断。
    """
    # 1. 自动迁移旧路径 → 新路径（一次性，幂等）
    moved = paths_migrate()
    if moved:
        print(f"{GREEN}[OK] 已迁移 {moved} 个旧配置/数据到 {ROOT}{RESET}")

    c = load_config()

    # 自动创建默认工作空间
    if not c.get("allowed_dirs"):
        DEFAULT_WORKSPACE.mkdir(parents=True, exist_ok=True)
        c["allowed_dirs"] = [str(DEFAULT_WORKSPACE)]
        save_config(c)
        print(f"{GREEN}[OK] 默认目录已添加: {DEFAULT_WORKSPACE}{RESET}")

    # 检测是否需要进入模型配置向导
    has_default = bool(c.get("default_provider"))
    has_providers = bool(c.get("providers"))
    needs_wizard = force_wizard or not (has_default and has_providers)

    # 非交互环境判断
    if interactive is None:
        import sys as _sys
        interactive = _sys.stdin.isatty() if _sys.stdin else False

    # 批处理模式直接跳过向导
    import os as _os
    batch_mode = _os.environ.get("FR_CLI_NON_INTERACTIVE") == "1"

    if needs_wizard and interactive and not batch_mode and not c.get("model_wizard_skipped"):
        # ── 引导进入 6 步模型配置向导 ──
        from fr_cli.ui.ui import center_display, get_display_width
        from fr_cli.conf.model_wizard import run_model_wizard

        # 框规格统一:总宽 = _BW + 2(左右框线各 1),边框/标题/正文都按此对齐
        _BW = 56

        def _box_line(content: str, inner: int = _BW) -> str:
            import re
            plain = re.sub(r'\033\[[0-9;]*m', '', content)
            w = get_display_width(plain)
            pad = max(inner - w, 0)
            return f"{YELLOW}║{RESET}{content}{' ' * pad}{YELLOW}║{RESET}"

        print()
        print(f"{YELLOW}╔{'═' * _BW}╗{RESET}")
        # 标题按显示宽度居中(str.center 按代码点,emoji/中文会顶破右框线)
        print(f"{YELLOW}║{center_display('尚未配置默认模型', _BW)}║{RESET}")
        print(f"{YELLOW}╠{'═' * _BW}╣{RESET}")
        print(_box_line("  fr-cli 需要至少一个 LLM 模型才能正常工作。"))
        print(_box_line("  接下来会引导你完成 6 步配置。"))
        print(_box_line(""))
        print(_box_line(f"  {DIM}也可以稍后执行 {CYAN}/providers setup{RESET}{DIM} 启动向导{RESET}"))
        print(f"{YELLOW}╚{'═' * _BW}╝{RESET}")
        print()

        try:
            enter = input(f"{CYAN}现在进入配置向导? [Y/n]: {RESET}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            enter = "n"
        if enter in ("", "y", "yes", "是"):
            print()
            try:
                c = run_model_wizard(c, mode="setup")
            except (KeyboardInterrupt, EOFError):
                print(f"\n{DIM}已取消配置。{RESET}")
        else:
            print(f"{DIM}→ 跳过向导,进入 Mock 模式{RESET}")
            print(f"{DIM}  命令功能可用,AI 回答为本地回声。随时 /providers setup 启动向导。{RESET}")

    # 兼容旧版字段(provider/model 顶层),用于运行时 active model
    # 如果 default_provider 已配置但顶层 provider 为空,同步过来
    if c.get("default_provider") and not c.get("provider"):
        c["provider"] = c["default_provider"]
        providers_cfg = c.setdefault("providers", {})
        pcfg = providers_cfg.setdefault(c["default_provider"], {})
        if not c.get("model") and pcfg.get("model"):
            c["model"] = pcfg["model"]
        save_config(c)

    return c

