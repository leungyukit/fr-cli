"""
@remote 内置 Agent —— 远程 SSH 操作助手
支持多机配置、配置向导、AI 生成远程命令。
"""
import json
import os
import subprocess
from pathlib import Path

REMOTE_CFG_PATH = Path.home() / ".fr_cli_remotes.json"

REMOTE_SYS_PROMPT = """你是一个远程系统命令专家。请根据目标主机的操作系统类型和用户需求，生成最合适的远程命令。

规则：
1. 只输出命令本身，不要任何解释、不要 markdown 代码块、不要多余文字
2. 如果需求涉及危险操作，输出 COMMENT: 开头的注释警告
3. 优先使用标准 Linux/Unix 命令（目标多为服务器）
4. 如果需要多条命令，用 && 或 ; 连接成一行
5. 避免交互式命令（如 vim、top），使用非交互式替代

目标主机 OS: {os_name}
"""


def _load_hosts():
    if not REMOTE_CFG_PATH.exists():
        return {}
    try:
        return json.loads(REMOTE_CFG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_hosts(hosts):
    REMOTE_CFG_PATH.write_text(json.dumps(hosts, ensure_ascii=False, indent=2), encoding="utf-8")


def list_hosts():
    return _load_hosts()


def save_host(alias, ip, port, user, auth_type, auth_value):
    hosts = _load_hosts()
    hosts[alias] = {
        "ip": ip,
        "port": int(port) if port else 22,
        "user": user,
        "auth_type": auth_type,  # "password" or "key"
        "auth_value": auth_value,
    }
    _save_hosts(hosts)


def delete_host(alias):
    hosts = _load_hosts()
    if alias in hosts:
        del hosts[alias]
        _save_hosts(hosts)
        return True
    return False


def _exec_ssh(host_cfg, command):
    """通过 ssh 命令执行远程操作"""
    ip = host_cfg["ip"]
    port = host_cfg.get("port", 22)
    user = host_cfg["user"]
    auth_type = host_cfg.get("auth_type", "password")
    auth_value = host_cfg.get("auth_value", "")

    ssh_opts = f"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p {port}"

    if auth_type == "key":
        if not Path(auth_value).exists():
            return None, f"密钥文件不存在: {auth_value}"
        ssh_cmd = f"ssh {ssh_opts} -i {auth_value} {user}@{ip} '{command}'"
    else:
        # 使用 sshpass 或 expect 传密码
        # 先尝试 sshpass，如果没有则尝试 ssh 的 BatchMode
        import shutil
        if shutil.which("sshpass"):
            ssh_cmd = f"sshpass -p '{auth_value}' ssh {ssh_opts} {user}@{ip} '{command}'"
        else:
            # 没有 sshpass，使用 ssh 的 ControlMaster 或提示用户
            return None, "未安装 sshpass，无法自动传密码。建议配置密钥认证，或安装 sshpass: brew install sshpass / apt install sshpass"

    try:
        res = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True, timeout=30)
        out = res.stdout + res.stderr
        return out, None
    except subprocess.TimeoutExpired:
        return None, "SSH 命令执行超时（30秒）"
    except Exception as e:
        return None, str(e)


def _detect_os(host_cfg):
    """探测远程主机操作系统"""
    out, err = _exec_ssh(host_cfg, "uname -s")
    if err:
        return "Unknown", err
    return out.strip() or "Linux", None


def handle_remote(user_input, state):
    """处理 @remote 前缀的请求"""
    from fr_cli.core.stream import stream_cnt
    from fr_cli.ui.ui import CYAN, GREEN, RED, YELLOW, DIM, RESET

    hosts = list_hosts()
    if not hosts:
        print(f"{YELLOW}未配置远程主机。正在启动配置向导...{RESET}")
        _setup_wizard(state.lang)
        hosts = list_hosts()
        if not hosts:
            print(f"{RED}配置取消，无法执行远程操作。{RESET}")
            return

    # 解析输入: @remote [ip/alias] 需求
    text = user_input[len("@remote"):].strip()
    parts = text.split(None, 1)

    # 如果只配置了一台，默认使用它
    if len(hosts) == 1:
        alias = list(hosts.keys())[0]
        requirement = text
    else:
        if len(parts) < 2:
            print(f"{YELLOW}用法: @remote <别名/IP> <需求描述>{RESET}")
            print(f"{DIM}已配置主机: {', '.join(hosts.keys())}{RESET}")
            return
        alias = parts[0]
        requirement = parts[1]

    # 查找主机配置
    host_cfg = hosts.get(alias)
    if not host_cfg:
        # 尝试用 alias 模糊匹配
        for k, v in hosts.items():
            if k.lower() == alias.lower() or v.get("ip") == alias:
                host_cfg = v
                alias = k
                break
    if not host_cfg:
        print(f"{RED}未找到主机 [{alias}]。已配置: {', '.join(hosts.keys())}{RESET}")
        return

    # 探测 OS
    os_name, err = _detect_os(host_cfg)
    if err:
        print(f"{RED}无法连接主机 [{alias}]: {err}{RESET}")
        return

    prompt = REMOTE_SYS_PROMPT.format(os_name=os_name)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": requirement},
    ]

    print(f"{CYAN}🧙 正在为 [{alias}]({os_name}) 生成远程命令...{RESET}")
    cmd_text, _, _ = stream_cnt(state.client, state.model_name, messages, state.lang, custom_prefix="", max_tokens=1024)
    cmd_text = cmd_text.strip()

    if cmd_text.startswith("```"):
        cmd_text = cmd_text.split("\n", 1)[1] if "\n" in cmd_text else ""
        if cmd_text.endswith("```"):
            cmd_text = cmd_text.rsplit("\n", 1)[0]
        cmd_text = cmd_text.strip()

    if not cmd_text:
        print(f"{RED}未能生成有效命令。{RESET}")
        return

    if cmd_text.startswith("COMMENT:"):
        print(f"{YELLOW}{cmd_text}{RESET}")
        return

    print(f"\n{DIM}建议命令 ({alias}):{RESET}\n{CYAN}{cmd_text}{RESET}")
    confirm = input(f"{DIM}是否执行? [Y/n]: {RESET}").strip().lower()
    if confirm and confirm not in ("y", "yes", "Y"):
        print(f"{DIM}已取消。{RESET}")
        return

    out, err = _exec_ssh(host_cfg, cmd_text)
    if err:
        print(f"{RED}❌ 执行失败: {err}{RESET}")
    else:
        if out.strip():
            print(f"\n{GREEN}{out.strip()[:3000]}{RESET}")
        else:
            print(f"{GREEN}✅ 命令执行完成（无输出）{RESET}")


def _setup_wizard(lang="zh"):
    """远程主机配置向导"""
    from fr_cli.ui.ui import CYAN, GREEN, YELLOW, DIM, RESET

    print(f"{CYAN}═══ 远程主机配置向导 ═══{RESET}")
    alias = input(f"{DIM}别名 (如: myserver): {RESET}").strip()
    if not alias:
        print(f"{YELLOW}别名不能为空。{RESET}")
        return
    ip = input(f"{DIM}IP 地址: {RESET}").strip()
    if not ip:
        print(f"{YELLOW}IP 不能为空。{RESET}")
        return
    port = input(f"{DIM}端口 [22]: {RESET}").strip() or "22"
    user = input(f"{DIM}用户名: {RESET}").strip()
    if not user:
        print(f"{YELLOW}用户名不能为空。{RESET}")
        return
    auth = input(f"{DIM}认证方式 (password/key) [password]: {RESET}").strip() or "password"
    if auth == "key":
        auth_value = input(f"{DIM}私钥文件路径 (如: ~/.ssh/id_rsa): {RESET}").strip()
    else:
        auth_value = input(f"{DIM}密码: {RESET}").strip()

    save_host(alias, ip, port, user, auth, auth_value)
    print(f"{GREEN}✅ 主机 [{alias}] ({ip}) 已保存。{RESET}")
