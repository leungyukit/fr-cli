"""
配置文件读写与初始化引擎
支持原子写入与自动备份，防止写入中断导致配置丢失
"""
import json
import shutil
from pathlib import Path
from fr_cli.ui.ui import YELLOW, RED, GREEN, RESET

CONFIG_FILE = Path.home() / ".zhipu_cli_config.json"
CONFIG_BACKUP = Path.home() / ".zhipu_cli_config.json.bak"
DEFAULT_WORKSPACE = Path.home() / "fr-cli-workspaces"
DEFAULT_LIMIT = 20000


def _default_config():
    """返回默认配置字典"""
    return {
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
    }


def load_config():
    """加载配置，如果缺失或损坏则返回带默认值的安全字典"""
    d = _default_config()

    # 尝试加载主配置文件
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                c = json.load(f)
            for k, v in d.items():
                if k not in c:
                    c[k] = v
            return c
        except Exception as e:
            print(
                f"{YELLOW}⚠️ 配置文件损坏: {e}{RESET}"
            )

    # 尝试从备份恢复
    if CONFIG_BACKUP.exists():
        try:
            with open(CONFIG_BACKUP, "r", encoding="utf-8") as f:
                c = json.load(f)
            for k, v in d.items():
                if k not in c:
                    c[k] = v
            print(f"{GREEN}✅ 已从备份恢复配置{RESET}")
            # 恢复主配置文件
            shutil.copy2(CONFIG_BACKUP, CONFIG_FILE)
            return c
        except Exception as e:
            print(f"{YELLOW}⚠️ 备份文件也损坏: {e}{RESET}")

    print(f"{YELLOW}⚠️ 使用默认配置，请重新设置{RESET}")
    return d


def save_config(c):
    """将配置字典原子写入本地（先写临时文件再重命名，避免写入中断损坏配置）"""
    try:
        # 1. 备份现有配置
        if CONFIG_FILE.exists():
            shutil.copy2(CONFIG_FILE, CONFIG_BACKUP)

        # 2. 写入临时文件
        tmp = CONFIG_FILE.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(c, f, indent=4, ensure_ascii=False)

        # 3. 原子替换
        tmp.replace(CONFIG_FILE)
        return True
    except Exception as e:
        print(f"{RED}❌ 保存配置失败: {e}{RESET}")
        return False


class ConfigError(Exception):
    """配置初始化异常（替代 exit，避免作为库导入时终止进程）"""
    pass


def init_config():
    """首次运行引导：检查并要求输入 API Key，自动创建默认工作空间"""
    c = load_config()

    # 自动创建默认工作空间
    if not c.get("allowed_dirs"):
        DEFAULT_WORKSPACE.mkdir(parents=True, exist_ok=True)
        c["allowed_dirs"] = [str(DEFAULT_WORKSPACE)]
        save_config(c)
        print(f"{GREEN}✅ 默认洞府已开辟: {DEFAULT_WORKSPACE}{RESET}")

    if not c.get("key"):
        print(f"\n{YELLOW}⚠️ API Key Required{RESET}")
        k = input(f"👉 Enter Zhipu API Key: ").strip()
        if k:
            c["key"] = k
            ok = save_config(c)
            if ok:
                print(f"{GREEN}✅ API Key 已保存至: {CONFIG_FILE}{RESET}")
            else:
                print(f"{RED}❌ 配置保存失败，下次启动可能需要重新输入。{RESET}")
        else:
            raise ConfigError("API Key is required")
    return c
