"""
配置向导引擎
当用户首次使用需配置的功能时，通过交互式向导引导配置并保存。
"""
from fr_cli.conf.config import save_config
from fr_cli.ui.ui import CYAN, GREEN, YELLOW, RED, DIM, RESET


def _prompt(text, default=""):
    """带默认值的输入提示"""
    if default:
        val = input(f"{CYAN}👉 {text} [{default}]: {RESET}").strip()
        return val if val else default
    return input(f"{CYAN}👉 {text}: {RESET}").strip()


def _confirm(text):
    """Y/N 确认，默认 Y"""
    r = input(f"{YELLOW}{text} (Y/n): {RESET}").strip().lower()
    return r in ("", "y", "yes", "是")


# ── 邮件服务商预设 ──
MAIL_PRESETS = {
    "1": {"name": "QQ邮箱 / Foxmail", "imap": "imap.qq.com", "smtp": "smtp.qq.com"},
    "2": {"name": "163邮箱", "imap": "imap.163.com", "smtp": "smtp.163.com"},
    "3": {"name": "Gmail", "imap": "imap.gmail.com", "smtp": "smtp.gmail.com"},
    "4": {"name": "Outlook", "imap": "outlook.office365.com", "smtp": "smtp.office365.com"},
    "5": {"name": "阿里云邮箱", "imap": "imap.aliyun.com", "smtp": "smtp.aliyun.com"},
}


def mail_wizard(cfg, lang="zh"):
    """
    邮件配置交互向导
    :param cfg: 当前配置字典（会被修改）
    :param lang: 语言
    :return: (success: bool, updated_cfg: dict)
    """
    uf = lang == "zh"
    print(f"\n{YELLOW}{'⚠️ 邮件功能尚未配置' if uf else '⚠️ Mail not configured'}{RESET}")
    if not _confirm("启动配置向导?" if uf else "Launch setup wizard?"):
        return False, cfg

    print(f"\n{CYAN}{'📧 选择邮箱服务商:' if uf else '📧 Select mail provider:'}{RESET}")
    for k, v in MAIL_PRESETS.items():
        print(f"  [{k}] {v['name']}")
    print(f"  [6] {'自定义' if uf else 'Custom'}")

    choice = _prompt("选择" if uf else "Choice", "1")
    if choice in MAIL_PRESETS:
        preset = MAIL_PRESETS[choice]
        imap_server = preset["imap"]
        smtp_server = preset["smtp"]
        print(f"{DIM}  IMAP: {imap_server} | SMTP: {smtp_server}{RESET}")
    elif choice == "6":
        imap_server = _prompt("IMAP 服务器" if uf else "IMAP server")
        smtp_server = _prompt("SMTP 服务器" if uf else "SMTP server")
    else:
        print(f"{RED}{'❌ 无效选择' if uf else '❌ Invalid choice'}{RESET}")
        return False, cfg

    import getpass
    email = _prompt("邮箱地址" if uf else "Email address")
    password = getpass.getpass(f"{CYAN}👉 {'授权码/密码' if uf else 'Auth code / password'}: {RESET}")

    if not email or not password:
        print(f"{RED}{'❌ 邮箱和密码不能为空' if uf else '❌ Email and password required'}{RESET}")
        return False, cfg

    # 保存配置
    cfg["mail"] = {
        "imap_server": imap_server,
        "smtp_server": smtp_server,
        "email": email,
        "password": password,
    }
    save_config(cfg)

    # 尝试验证连接
    print(f"\n{CYAN}{'🔄 正在测试连接...' if uf else '🔄 Testing connection...'}{RESET}")
    try:
        from fr_cli.weapon.mail import MailClient
        client = MailClient(cfg["mail"])
        if client.connected:
            print(f"{GREEN}{'✅ 配置已保存并验证通过！' if uf else '✅ Config saved and verified!'}{RESET}")
        else:
            print(f"{YELLOW}{'⚠️ 配置已保存，但模块加载失败' if uf else '⚠️ Config saved but module load failed'}{RESET}")
    except Exception as e:
        print(f"{YELLOW}{'⚠️ 配置已保存，验证出错:' if uf else '⚠️ Config saved, verify error:'} {e}{RESET}")

    return True, cfg


# ── 云盘类型预设 ──
DISK_PRESETS = {
    "1": {"name": "阿里云盘", "type": "aliyundrive"},
    "2": {"name": "百度网盘", "type": "baidu"},
    "3": {"name": "OneDrive", "type": "onedrive"},
}


def disk_wizard(cfg, lang="zh"):
    """
    云盘配置交互向导
    :param cfg: 当前配置字典（会被修改）
    :param lang: 语言
    :return: (success: bool, updated_cfg: dict)
    """
    uf = lang == "zh"
    print(f"\n{YELLOW}{'⚠️ 云盘功能尚未配置' if uf else '⚠️ Cloud disk not configured'}{RESET}")
    if not _confirm("启动配置向导?" if uf else "Launch setup wizard?"):
        return False, cfg

    print(f"\n{CYAN}{'☁️ 选择云盘类型:' if uf else '☁️ Select cloud type:'}{RESET}")
    for k, v in DISK_PRESETS.items():
        print(f"  [{k}] {v['name']}")

    choice = _prompt("选择" if uf else "Choice", "1")
    if choice in DISK_PRESETS:
        disk_type = DISK_PRESETS[choice]["type"]
    else:
        print(f"{RED}{'❌ 无效选择' if uf else '❌ Invalid choice'}{RESET}")
        return False, cfg

    # 阿里云盘配置（扫码登录）
    if disk_type == "aliyundrive":
        try:
            from aligo import Aligo
        except ImportError:
            print(f"{RED}{'❌ 请先安装 aligo: pip install aligo' if uf else '❌ Please install aligo: pip install aligo'}{RESET}")
            return False, cfg

        print(f"\n{DIM}{'正在初始化阿里云盘登录...' if uf else 'Initializing Aliyun Drive login...'}{RESET}")
        try:
            # 尝试使用已有 refresh_token 登录
            old_disk = cfg.get("disk", {})
            refresh_token = old_disk.get("refresh_token") if old_disk.get("type") == "aliyundrive" else None
            name = old_disk.get("name", "fr-cli")

            if refresh_token:
                ali = Aligo(name=name, refresh_token=refresh_token)
                print(f"{GREEN}{'✅ 已使用缓存令牌登录成功' if uf else '✅ Logged in with cached token'}{RESET}")
            else:
                print(f"{YELLOW}{'请使用阿里云盘 App 扫描二维码完成登录' if uf else 'Please scan QR code with Aliyun Drive App'}{RESET}")
                ali = Aligo(name=name)
                print(f"{GREEN}{'✅ 登录成功' if uf else '✅ Login successful'}{RESET}")

            # 保存配置
            disk_cfg = {
                "type": "aliyundrive",
                "name": name,
            }
            # 尝试提取 refresh_token 以便后续免扫码登录
            try:
                disk_cfg["refresh_token"] = ali.refresh_token
            except AttributeError:
                pass

            cfg["disk"] = disk_cfg
        except Exception as e:
            print(f"{RED}{'❌ 登录失败:' if uf else '❌ Login failed:'} {e}{RESET}")
            return False, cfg
    else:
        print(f"{YELLOW}{'⚠️ 当前仅支持阿里云盘，其他类型敬请期待' if uf else '⚠️ Only Aliyun Drive is currently supported'}{RESET}")
        return False, cfg

    save_config(cfg)
    print(f"{GREEN}{'✅ 云盘配置已保存！' if uf else '✅ Cloud disk config saved!'}{RESET}")
    return True, cfg


