"""
网络探测工具 —— 供大模型调用
包含 ping、端口扫描、IP 扫描、网络设备发现等基础能力
"""
import platform
import socket
import subprocess
import ipaddress
import concurrent.futures

from fr_cli.core.result import Result


_SYSTEM = platform.system().lower()


def ping_host(host: str, count: int = 3, timeout: int = 2):
    """对目标主机执行 ping 探测，返回 Result[dict]。"""
    if not host:
        return Result.fail("主机名不能为空")

    try:
        if _SYSTEM == "windows":
            # Windows: -n 次数, -w 毫秒超时
            cmd = ["ping", "-n", str(count), "-w", str(timeout * 1000), host]
        else:
            # macOS/Linux: -c 次数, -W 秒超时
            cmd = ["ping", "-c", str(count), "-W", str(timeout), host]

        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=count * timeout + 5,
        )
        stdout = proc.stdout.decode("utf-8", errors="ignore")
        stderr = proc.stderr.decode("utf-8", errors="ignore")

        # 通用判断：返回码 0 表示至少收到一个回复
        alive = proc.returncode == 0

        # 简单解析丢包率
        loss = None
        text = stdout + stderr
        for line in text.splitlines():
            line_lower = line.lower()
            if "loss" in line_lower or "丢失" in line:
                # Windows: "0% loss"; Linux: "0% packet loss"
                parts = line.split("%")
                if len(parts) > 1:
                    try:
                        loss = int(parts[0].split()[-1])
                    except ValueError:
                        pass

        return Result.ok({
            "host": host,
            "alive": alive,
            "loss_percent": loss if loss is not None else (0 if alive else 100),
            "raw": stdout[:500],
        })
    except subprocess.TimeoutExpired:
        return Result.ok({"host": host, "alive": False, "loss_percent": 100, "raw": "timeout"})
    except FileNotFoundError:
        return Result.fail("系统未安装 ping 命令")
    except Exception as e:
        return Result.fail(f"ping 失败: {e}")


def port_scan(host: str, ports, timeout: float = 1.0, max_workers: int = 50):
    """扫描目标主机的指定端口，返回 Result[list]。"""
    if not host:
        return Result.fail("主机名不能为空")

    port_list = _parse_ports(ports)
    if not port_list:
        return Result.fail("端口格式无效")
    if len(port_list) > 1000:
        return Result.fail("单次扫描端口数不能超过 1000")

    open_ports = []

    def _check(port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                result = s.connect_ex((host, port))
                if result == 0:
                    try:
                        service = socket.getservbyport(port, "tcp")
                    except (OSError, ValueError):
                        service = "unknown"
                    return {"port": port, "service": service}
        except Exception:
            pass
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_check, p) for p in port_list]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                open_ports.append(res)

    open_ports.sort(key=lambda x: x["port"])
    return Result.ok(open_ports)


def _parse_ports(ports):
    """解析端口参数为整数列表"""
    if isinstance(ports, list):
        return [int(p) for p in ports if isinstance(p, int) or str(p).isdigit()]

    if isinstance(ports, str):
        result = []
        for part in ports.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    start, end = part.split("-", 1)
                    result.extend(range(int(start), int(end) + 1))
                except ValueError:
                    continue
            elif part.isdigit():
                result.append(int(part))
        return result

    return []


def ip_scan(network: str, timeout: int = 1, max_workers: int = 50, max_hosts: int = 256):
    """对 CIDR 网段执行 ping 批量扫描，返回 Result[list]。"""
    try:
        net = ipaddress.ip_network(network, strict=False)
    except ValueError as e:
        return Result.fail(f"网段格式错误: {e}")

    hosts = [str(ip) for ip in net.hosts()]
    if len(hosts) > max_hosts:
        hosts = hosts[:max_hosts]

    alive = []

    def _ping_one(ip):
        result = ping_host(ip, count=1, timeout=timeout)
        if result.is_ok() and result.unwrap().get("alive"):
            return ip
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_ping_one, ip) for ip in hosts]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                alive.append(res)

    alive.sort(key=lambda x: tuple(int(p) for p in x.split(".")))
    return Result.ok(alive)


def network_devices(network: str, timeout: int = 1, max_workers: int = 50, max_hosts: int = 64):
    """扫描网段并尝试识别网络设备，返回 Result[list]。"""
    scan_result = ip_scan(network, timeout=timeout, max_workers=max_workers, max_hosts=max_hosts)
    if scan_result.is_fail():
        return Result.fail(scan_result.error)
    alive = scan_result.unwrap()

    common_ports = [22, 23, 80, 443, 445, 8080, 8443, 3306, 5432, 3389]
    devices = []

    def _probe(ip):
        device = {"ip": ip, "hostname": "", "open_ports": []}
        try:
            device["hostname"] = socket.gethostbyaddr(ip)[0]
        except Exception:
            pass

        ports_result = port_scan(ip, common_ports, timeout=timeout, max_workers=10)
        if ports_result.is_ok():
            device["open_ports"] = ports_result.unwrap()
        return device

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_probe, ip) for ip in alive]
        for future in concurrent.futures.as_completed(futures):
            devices.append(future.result())

    devices.sort(key=lambda x: tuple(int(p) for p in x["ip"].split(".")))
    return Result.ok(devices)
