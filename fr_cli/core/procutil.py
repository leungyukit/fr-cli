"""守护进程工具：pid 存活/身份校验、现存进程扫描与收养。

背景（守护进程累积 bug）：
Gatekeeper / Hermes 两个后台守护进程由各自 Manager spawn，历史上只用
「pid 文件 + os.kill(pid, 0)」判断存活，有两个漏洞：

1. 守护进程在写 pid 文件之前挂起（或 pid 文件丢失）→ 之后每次启动
   fr-cli 都会再 spawn 一个，旧的永不停 → 进程无限累积；
2. pid 被系统回收后 os.kill(pid, 0) 仍成功 → 误报「在运行」→
   守护进程永远无法被重启。

本模块提供：
- pid_alive：进程是否存在（不校验身份）
- pid_matches_daemon：pid 存活且命令行含守护脚本标记（防 pid 回收误报）
- scan_daemon_pids：扫描命令行含标记的现存进程（用于「收养」）

跨实例误收养 bug（已修）：
两个 fr-cli 实例跑同一仓库时，守护进程的命令行完全相同（只有脚本路径），
scan_daemon_pids 曾因此把**别的实例**（含沙盒 HOME）的守护进程收养过来，
随后被本实例 stop() 杀掉，导致那个实例失去守护进程。
现由「归属标记」修复：Manager spawn 时在命令行追加
--fr-cli-daemon-home <配置根>，收养/身份校验时比对，标记不同或缺失
（旧版 daemon）一律不认。

Windows 下 ps 不可用：身份校验退化为「仅确认存活」，扫描返回空列表。
"""

import os
import subprocess
import sys

_PS_TIMEOUT = 10

# 守护进程归属标记：Manager spawn 时追加在命令行里，
# 值 = 启动它的 fr-cli 实例的配置根（~/.fr_cli，沙盒 HOME 下是别的路径）。
# 扫描收养时比对，防止跨实例（含沙盒）误收养/误杀。
DAEMON_HOME_FLAG = "--fr-cli-daemon-home"


def pid_alive(pid) -> bool:
    """进程是否存在（不校验身份）。"""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(1, False, pid)
            if handle:
                kernel32.CloseProcess(handle)
                return True
            return False
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # 进程存在，只是不属于当前用户
        return True
    except OSError:
        return False


def _ps(args):
    """执行 ps 命令；Windows 或执行失败返回 None"""
    if sys.platform == "win32":
        return None
    try:
        return subprocess.run(
            ["ps"] + args, capture_output=True, text=True, timeout=_PS_TIMEOUT
        )
    except Exception:
        return None


def pid_cmdline(pid):
    """返回进程命令行文本；取不到返回 None"""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    out = _ps(["-o", "args=", "-p", str(pid)])
    if out is None or out.returncode != 0:
        return None
    return out.stdout


def iter_all_pids():
    """产出 (pid, cmdline)；ps 不可用时为空"""
    out = _ps(["-A", "-o", "pid=", "-o", "args="])
    if out is None or out.returncode != 0:
        return
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        yield int(parts[0]), parts[1]


def daemon_home_of_cmdline(cmdline):
    """从命令行提取守护进程自称的归属配置根；取不到返回 None。

    旧版 daemon（spawn 时没有追加 --fr-cli-daemon-home）返回 None，
    即「归属不可知」——调用方按各自策略处理（见 pid_matches_daemon /
    scan_daemon_pids 的 home 参数语义）。
    """
    if not cmdline:
        return None
    parts = cmdline.split()
    for i, tok in enumerate(parts):
        if tok == DAEMON_HOME_FLAG:
            if i + 1 < len(parts):
                return parts[i + 1]
            return None
        if tok.startswith(DAEMON_HOME_FLAG + "="):
            return tok.split("=", 1)[1]
    return None


def pid_matches_daemon(pid, marker, home=None) -> bool:
    """pid 存活且确认为守护进程。

    :param marker: 命令行须含的守护脚本标记
    :param home:   传入时做「归属校验」—— 命令行必须带
                    --fr-cli-daemon-home 且值等于 home；带但值不同
                    （别的实例的 daemon）或不带（旧版 daemon，归属不可知）
                    都算不匹配。不传则只校验脚本标记（pid 文件路径用：
                    pid 文件本身按配置根隔离，且升级遗留的旧 daemon
                    仍要能被识别和停止）。

    无法校验身份时（Windows / ps 异常）退化为「仅确认存活」，
    避免误杀健康守护进程；POSIX 下均可校验。
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if not pid_alive(pid):
        return False
    if pid == os.getpid():
        return False
    cmdline = pid_cmdline(pid)
    if cmdline is None:
        # 拿不到命令行：无法确认归属，仅在调用方不关心归属时视为匹配
        return home is None
    if marker not in cmdline:
        return False
    if home is None:
        return True
    return daemon_home_of_cmdline(cmdline) == home


def scan_daemon_pids(marker, home=None, exclude_pid=None) -> list:
    """扫描命令行含 marker 的进程 pid（升序，不含自身）。

    用于「收养」：守护进程还活着但 pid 文件缺失/失效时，
    把它的 pid 写回 pid 文件，避免重复 spawn 造成累积。

    :param home: 传入时只收养归属本实例的 daemon（命令行
                 --fr-cli-daemon-home 值相同）。别的实例（含沙盒 HOME）
                 与旧版无标记 daemon 都不收养 —— 宁可漏收养（下次多起
                 一个）也不能把别人还在用的 daemon 抢过来再杀掉。
    """
    if not marker:
        return []
    if exclude_pid is None:
        exclude_pid = os.getpid()
    found = []
    for pid, cmdline in iter_all_pids():
        if pid == exclude_pid:
            continue
        if marker not in cmdline:
            continue
        if home is not None and daemon_home_of_cmdline(cmdline) != home:
            continue
        found.append(pid)
    return sorted(found)
