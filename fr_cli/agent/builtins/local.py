"""
@local 内置 Agent —— 本地系统操作助手
将用户需求 + 当前 OS 信息提交大模型，生成并执行系统命令。
"""
import platform
import shutil
import subprocess

LOCAL_SYS_PROMPT = """你是一个系统命令专家。请根据用户的操作系统类型和需求，生成最合适、最安全的系统命令。

规则：
1. 只输出命令本身，不要任何解释、不要 markdown 代码块、不要多余文字
2. 如果需求涉及危险操作（rm -rf、格式化磁盘等），输出 COMMENT: 开头的注释警告
3. 优先使用跨平台兼容的命令，如果无法兼容则针对当前 OS 生成
4. 如果需要多条命令，用 && 或 ; 连接成一行（Windows 下用 ;）
5. 如果用户只是想查看信息，用安全的只读命令

当前操作系统: {os_name}
当前目录: {cwd}
"""

WINDOWS_PS_HINT = """
注意：当前系统为 Windows，请使用 PowerShell 命令，不要使用 Linux/bash 命令。
常用映射参考：
- ls / dir → Get-ChildItem
- cat → Get-Content
- rm / rmdir → Remove-Item -Recurse -Force
- mkdir → New-Item -ItemType Directory
- pwd → Get-Location
- cp → Copy-Item
- mv → Move-Item
- grep → Select-String
- touch → New-Item
"""


def handle_local(user_input, state):
    """处理 @local 前缀的请求"""
    from fr_cli.core.stream import stream_cnt
    from fr_cli.ui.ui import CYAN, GREEN, RED, YELLOW, DIM, RESET

    requirement = user_input[len("@local"):].strip()
    if not requirement:
        print(f"{RED}用法: @local <需求描述>{RESET}")
        return

    os_name = platform.system()
    cwd = state.vfs.cwd if state.vfs and state.vfs.cwd else "."

    prompt = LOCAL_SYS_PROMPT.format(os_name=os_name, cwd=cwd)
    if os_name == "Windows":
        prompt += WINDOWS_PS_HINT
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": requirement},
    ]

    print(f"{CYAN}🧙 正在分析本地操作...{RESET}")
    cmd_text, _, _ = stream_cnt(state.client, state.model_name, messages, state.lang, custom_prefix="", max_tokens=1024)
    cmd_text = cmd_text.strip()

    # 清理可能的代码块
    from fr_cli.agent.builtins._utils import strip_code_blocks
    cmd_text = strip_code_blocks(cmd_text)

    if not cmd_text:
        print(f"{RED}未能生成有效命令。{RESET}")
        return

    if cmd_text.startswith("COMMENT:"):
        print(f"{YELLOW}{cmd_text}{RESET}")
        return

    print(f"\n{DIM}建议命令:{RESET}\n{CYAN}{cmd_text}{RESET}")
    from fr_cli.agent.builtins._utils import confirm_execute
    if not confirm_execute():
        print(f"{DIM}已取消。{RESET}")
        return

    try:
        print(f"{DIM}执行中...{RESET}")
        if os_name == "Windows":
            # Windows 下优先使用 PowerShell 执行，避免 cmd 无法识别 PowerShell 命令
            ps_exe = shutil.which("pwsh") or shutil.which("powershell")
            if ps_exe:
                res = subprocess.run([ps_exe, "-Command", cmd_text], capture_output=True, text=True, timeout=30)
            else:
                res = subprocess.run(cmd_text, shell=True, capture_output=True, text=True, timeout=30)
        else:
            res = subprocess.run(cmd_text, shell=True, capture_output=True, text=True, timeout=30)
        out = res.stdout + res.stderr
        if out.strip():
            print(f"\n{GREEN}{out.strip()[:3000]}{RESET}")
        else:
            print(f"{GREEN}✅ 命令执行完成（无输出）{RESET}")
        # 将结果追加到记忆
        from fr_cli.agent.manager import save_memory, load_memory
        mem = load_memory("__local__")
        ts = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M")
        new_mem = f"\n[{ts}] 执行: {cmd_text}\n结果: {out.strip()[:500]}\n"
        save_memory("__local__", (mem or "") + new_mem)
    except subprocess.TimeoutExpired:
        print(f"{RED}⏱️ 命令执行超时（30秒）{RESET}")
    except Exception as e:
        print(f"{RED}❌ 执行失败: {e}{RESET}")
