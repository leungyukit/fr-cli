"""
配置文件读写与初始化引擎
支持原子写入与自动备份，防止写入中断导致配置丢失

新架构：所有路径都来自 fr_cli.conf.paths（单一真相源）。
旧路径在首次启动时由 paths.migrate() 自动迁移到新位置。
"""
import json
import os
import shutil
from pathlib import Path
from fr_cli.ui.ui import YELLOW, RED, GREEN, CYAN, RESET, DIM
from fr_cli.conf.paths import (
    CONFIG_FILE, CONFIG_BACKUP, ROOT,
    migrate as paths_migrate,
)

DEFAULT_WORKSPACE = Path.home() / "fr-cli-workspaces"
DEFAULT_LIMIT = 20000


def _default_config():
    """返回默认配置字典 —— provider/model 不再硬编码，由用户显式配置"""
    return {
        "version": 2,
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
        "splash_cols": 50,
        "splash_bg_threshold": 30,
        "context_compress_threshold": 4000,
        "context_compress_keep_recent": 5,
    }


def _upgrade_schema(cfg):
    """把旧版配置升级到当前 schema（幂等执行）"""
    version = cfg.get("version", 1)
    if version >= 2:
        return cfg

    # v1 -> v2: 将顶层 model 同步到当前 provider 的专属配置中
    provider = cfg.get("provider")
    if provider and cfg.get("model"):
        providers = cfg.setdefault("providers", {})
        pcfg = providers.setdefault(provider, {})
        if not pcfg.get("model"):
            pcfg["model"] = cfg["model"]

    cfg["version"] = 2
    return cfg


def load_config():
    """加载配置，如果缺失或损坏则返回带默认值的安全字典

    优先从新路径（CONFIG_FILE）读取；如不存在则尝试从旧路径（~/.zhipu_cli_config.json）读取。
    加载后会自动执行向后兼容迁移：将顶层 model 同步到当前 provider 的专属配置中，
    确保 provider-model 强绑定。
    """
    d = _default_config()

    # 1. 尝试加载主配置文件（新路径）
    c = None
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                c = json.load(f)
        except Exception as e:
            print(f"{YELLOW}⚠️ 配置文件损坏: {e}{RESET}")

    # 2. 尝试从备份恢复
    if c is None and CONFIG_BACKUP.exists():
        try:
            with open(CONFIG_BACKUP, "r", encoding="utf-8") as f:
                c = json.load(f)
            print(f"{GREEN}✅ 已从备份恢复配置{RESET}")
            shutil.copy2(CONFIG_BACKUP, CONFIG_FILE)
        except Exception as e:
            print(f"{YELLOW}⚠️ 备份文件也损坏: {e}{RESET}")

    if c is None:
        print(f"{YELLOW}⚠️ 使用默认配置，请重新设置{RESET}")
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
        # 确保新根目录存在
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # 1. 备份现有配置
        if CONFIG_FILE.exists():
            shutil.copy2(CONFIG_FILE, CONFIG_BACKUP)

        # 2. 使用安全临时文件（随机名称 + 600 权限）
        import tempfile
        fd, tmp_path = tempfile.mkstemp(dir=CONFIG_FILE.parent, suffix=".json.tmp")
        try:
            os.chmod(tmp_path, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(c, f, indent=4, ensure_ascii=False)
            Path(tmp_path).replace(CONFIG_FILE)
        except Exception:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            raise
        return True
    except Exception as e:
        print(f"{RED}❌ 保存配置失败: {e}{RESET}")
        return False


class ConfigError(Exception):
    """配置初始化异常（替代 exit，避免作为库导入时终止进程）"""
    pass


def load_namespace(key, default=None, old_path=None):
    """从主配置 config.json 的命名空间中读取数据。

    若 old_path 指定的旧独立配置文件存在且主配置中该命名空间为空，
    则一次性迁移旧文件内容到主配置并保存。
    """
    if default is None:
        default = {}
    cfg = load_config()
    data = cfg.get(key)
    if data is not None:
        return data

    # 尝试迁移旧文件
    if old_path is not None:
        old_path = Path(old_path)
        if old_path.exists():
            try:
                old_data = json.loads(old_path.read_text(encoding="utf-8"))
                if old_data:
                    cfg[key] = old_data
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
    """把数据写入主配置 config.json 的命名空间并持久化。"""
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)


def init_config():
    """首次运行引导：迁移旧配置 → 检查并要求输入 API Key → 自动创建默认工作空间"""
    # 1. 自动迁移旧路径 → 新路径（一次性，幂等）
    moved = paths_migrate()
    if moved:
        print(f"{GREEN}✅ 已迁移 {moved} 个旧配置/数据到 {ROOT}{RESET}")

    c = load_config()

    # 自动创建默认工作空间
    if not c.get("allowed_dirs"):
        DEFAULT_WORKSPACE.mkdir(parents=True, exist_ok=True)
        c["allowed_dirs"] = [str(DEFAULT_WORKSPACE)]
        save_config(c)
        print(f"{GREEN}✅ 默认目录已添加: {DEFAULT_WORKSPACE}{RESET}")

    provider = c.get("provider")
    providers_cfg = c.get("providers", {})

    # ── 配置引导：无 provider 或未配置 Key 时提示 ──
    from fr_cli.ui.ui import get_display_width

    def _box_line(content: str, box_width: int = 50) -> str:
        """按实际显示宽度填充，确保框线对齐"""
        inner = box_width - 2
        import re
        plain = re.sub(r'\033\[[0-9;]*m', '', content)
        w = get_display_width(plain)
        pad = max(inner - w, 0)
        return f"{YELLOW}║{RESET}{content}{' ' * pad}{YELLOW}║{RESET}"

    if not provider:
        # 尚未选择 provider
        from fr_cli.core.llm import list_providers
        providers = list_providers()
        print()
        print(f"{YELLOW}╔{'═' * 50}╗{RESET}")
        print(f"{YELLOW}║{'🚨  尚未配置 LLM 提供商':^48}║{RESET}")
        print(f"{YELLOW}╠{'═' * 50}╣{RESET}")
        ids = [p['id'] for p in providers]
        ids_text = ', '.join(ids[:3])
        if len(ids) > 3:
            ids_text += f" ... 等 {len(ids)} 家"
        print(_box_line(f"  支持厂商: {DIM}{ids_text}{RESET}"))
        print(f"{YELLOW}╠{'═' * 50}╣{RESET}")
        print(_box_line("  配置方式:"))
        print(_box_line(f"  1. 启动后执行 {CYAN}/model config{RESET} 交互式配置"))
        print(_box_line(f"  2. 启动后执行 {CYAN}/providers setup{RESET} 交互式配置"))
        print(f"{YELLOW}╚{'═' * 50}╝{RESET}")
        print()
        print(f"{YELLOW}→ 进入 Mock 模式 🧪（可用 /model config 配置真实模型）{RESET}")
        return c

    pcfg = providers_cfg.get(provider, {})

    # 检查当前提供商是否已配置 key（兼容旧版顶层 key 字段）
    has_key = bool(pcfg.get("key") or c.get("key", ""))

    if not has_key:
        from fr_cli.core.llm import list_providers, get_provider_info
        providers = list_providers()
        info = get_provider_info(provider)
        default_model = info.get("default_model", "未知") if info else "未知"

        print()
        print(f"{YELLOW}╔{'═' * 50}╗{RESET}")
        print(f"{YELLOW}║{'🚨  尚未配置 API Key':^48}║{RESET}")
        print(f"{YELLOW}╠{'═' * 50}╣{RESET}")
        print(_box_line(f"  当前厂商: {CYAN}{provider}{RESET}"))
        print(_box_line(f"  默认模型: {DIM}{default_model}{RESET}"))
        print(f"{YELLOW}╠{'═' * 50}╣{RESET}")
        print(_box_line("  配置方式:"))
        print(_box_line("  1. 直接输入 API Key（下方）"))
        print(_box_line(f"  2. 启动后执行 {CYAN}/providers setup{RESET} 交互式配置"))
        print(_box_line(f"  3. 启动后执行 {CYAN}/model config{RESET} 交互式配置"))
        print(f"{YELLOW}╚{'═' * 50}╝{RESET}")
        print()

        try:
            k = input(f"👉 输入 [{CYAN}{provider}{RESET}] 的 API Key（回车进 Mock 试用）: ").strip()
        except (EOFError, KeyboardInterrupt):
            k = ""
        if k:
            c["key"] = k
            pcfg = providers_cfg.setdefault(provider, {})
            pcfg["key"] = k
            # 不再自动注入默认模型；model 由用户通过 /model 显式配置
            c["providers"] = providers_cfg
            ok = save_config(c)
            if ok:
                print(f"{GREEN}✅ API Key 已保存，下次启动自动生效{RESET}")
            else:
                print(f"{RED}❌ 配置保存失败，下次启动可能需要重新输入。{RESET}")
        else:
            print()
            print(f"{YELLOW}→ 进入 Mock 模式 🧪{RESET}")
            print(f"{DIM}  AI 回答为本地回声，命令功能（/ls /cat /web 等）仍可正常使用。{RESET}")
            print(f"{DIM}  随时可用 /key <your-key> 或 /model config 配置真实模型。{RESET}")
            print()
    return c
