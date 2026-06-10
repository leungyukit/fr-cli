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
from fr_cli.ui.ui import YELLOW, RED, GREEN, RESET, DIM
from fr_cli.conf.paths import (
    CONFIG_FILE, CONFIG_BACKUP, ROOT,
    migrate as paths_migrate,
)

DEFAULT_WORKSPACE = Path.home() / "fr-cli-workspaces"
DEFAULT_LIMIT = 20000


def _default_config():
    """返回默认配置字典"""
    return {
        "provider": "zhipu",
        "key": "",
        "model": "glm-4-flash",
        "limit": DEFAULT_LIMIT,
        "allowed_dirs": [],
        "lang": "zh",
        "aliases": {},
        "auto_confirm_forever": False,
        "mail": {},
        "disk": {},
        "thinking_mode": "direct",
        "mcp": {"servers": []},
        "providers": {},
        "banner_enabled": True,
        "splash_enabled": True,  # 启动封面(完整图片),终端不支持图像协议时降级为 banner
        "splash_cols": 50,  # 启动封面宽度(字符数)
        "splash_bg_threshold": 30,  # 背景阈值:亮度低于此值的像素视为背景(留空)
    }


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

    # 补齐缺失字段
    for k, v in d.items():
        if k not in c:
            c[k] = v

    # 向后兼容迁移：将顶层 model 同步到当前 provider 的专属配置中
    provider = c.get("provider", "zhipu")
    providers_cfg = c.setdefault("providers", {})
    pcfg = providers_cfg.setdefault(provider, {})
    if c.get("model") and not pcfg.get("model"):
        pcfg["model"] = c["model"]
        c["providers"] = providers_cfg

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

    # 向后兼容：无 provider 字段的旧配置自动补全
    if "provider" not in c:
        c["provider"] = "zhipu"
        save_config(c)

    provider = c.get("provider", "zhipu")
    providers_cfg = c.get("providers", {})
    pcfg = providers_cfg.get(provider, {})

    # 检查当前提供商是否已配置 key
    has_key = bool(pcfg.get("key"))
    if not has_key and provider == "zhipu":
        has_key = bool(c.get("key", ""))

    if not has_key:
        print(f"\n{YELLOW}⚠️ API Key Required{RESET}")
        from fr_cli.core.llm import list_providers, get_provider_info
        providers = list_providers()
        print(f"{DIM}当前提供商: {provider}{RESET}")
        print(f"{DIM}支持提供商: {', '.join([p['id'] for p in providers])}{RESET}")
        print(f"{DIM}（直接回车可进入 Mock 模式试用）{RESET}")
        try:
            k = input(f"👉 Enter API Key for [{provider}] (回车跳过): ").strip()
        except (EOFError, KeyboardInterrupt):
            # 非交互环境直接进 Mock 模式
            k = ""
        if k:
            c["key"] = k
            pcfg = providers_cfg.setdefault(provider, {})
            pcfg["key"] = k
            # 确保 provider 配置中也有 model（保持 provider-model 一致性）
            if not pcfg.get("model"):
                info = get_provider_info(provider)
                default_model = info.get("default_model", "glm-4-flash") if info else "glm-4-flash"
                pcfg["model"] = default_model
                c["model"] = default_model
            c["providers"] = providers_cfg
            ok = save_config(c)
            if ok:
                print(f"{GREEN}✅ API Key 已保存至: {CONFIG_FILE}{RESET}")
            else:
                print(f"{RED}❌ 配置保存失败，下次启动可能需要重新输入。{RESET}")
        else:
            # 用户跳过 → 进 Mock 模式（不报错）
            print(f"{YELLOW}→ 进入 Mock 模式（所有命令可用，AI 回答是 echo 风格）{RESET}")
            print(f"{DIM}   之后可用 /key <your-key> 设真 key 立即切换{RESET}")
    return c
