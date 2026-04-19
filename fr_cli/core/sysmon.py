"""
系统状态监控器
提供 CPU、内存、网络带宽的实时采样
优先使用 psutil，无依赖时优雅降级
"""
import time

# 全局采样状态（单例）
_last_sample = {
    "time": 0.0,
    "bytes_sent": 0,
    "bytes_recv": 0,
}


def _has_psutil():
    try:
        import psutil
        return True
    except ImportError:
        return False


def get_cpu_percent():
    """获取 CPU 使用百分比，无 psutil 时返回 None"""
    if not _has_psutil():
        return None
    import psutil
    return psutil.cpu_percent(interval=0.1)


def get_memory_info():
    """
    获取内存使用情况
    :return: (used_mb, total_mb, percent) 或 None
    """
    if not _has_psutil():
        return None
    import psutil
    mem = psutil.virtual_memory()
    used_mb = mem.used / (1024 * 1024)
    total_mb = mem.total / (1024 * 1024)
    return used_mb, total_mb, mem.percent


def get_network_speed():
    """
    获取网络带宽（MB/s）
    :return: (upload_mb_s, download_mb_s) 或 None
    """
    if not _has_psutil():
        return None
    import psutil
    global _last_sample

    net = psutil.net_io_counters()
    now = time.time()

    # 首次采样，只记录不返回速率
    if _last_sample["time"] == 0:
        _last_sample = {
            "time": now,
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
        }
        return 0.0, 0.0

    elapsed = now - _last_sample["time"]
    if elapsed <= 0:
        return 0.0, 0.0

    sent_diff = net.bytes_sent - _last_sample["bytes_sent"]
    recv_diff = net.bytes_recv - _last_sample["bytes_recv"]

    upload_mb_s = (sent_diff / (1024 * 1024)) / elapsed
    download_mb_s = (recv_diff / (1024 * 1024)) / elapsed

    _last_sample = {
        "time": now,
        "bytes_sent": net.bytes_sent,
        "bytes_recv": net.bytes_recv,
    }

    return upload_mb_s, download_mb_s


def get_sys_stats(lang="zh"):
    """
    获取完整的系统状态字符串（用于直接拼接显示）
    :param lang: 语言代码 "zh" 或 "en"
    :return: 形如 "CPU: 12% | 内存: 4.2/16.0GB(26%) | 网络: ↑0.5 ↓1.2 MB/s" 的字符串
             或空字符串（无 psutil 时）
    """
    if not _has_psutil():
        return ""

    cpu = get_cpu_percent()
    mem = get_memory_info()
    net = get_network_speed()

    L_CPU = "CPU" if lang == "en" else "CPU"
    L_MEM = "Mem" if lang == "en" else "内存"
    L_NET = "Net" if lang == "en" else "网络"

    parts = []
    if cpu is not None:
        parts.append(f"{L_CPU}:{cpu:.0f}%")

    if mem is not None:
        used_gb = mem[0] / 1024
        total_gb = mem[1] / 1024
        parts.append(f"{L_MEM}:{used_gb:.1f}/{total_gb:.1f}GB({mem[2]:.0f}%)")

    if net is not None:
        parts.append(f"{L_NET}:↑{net[0]:.1f}↓{net[1]:.1f}MB/s")

    return " | ".join(parts) if parts else ""
