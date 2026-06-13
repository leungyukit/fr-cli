"""
注册表分组：网络探测类工具
- ping_host / port_scan / ip_scan / network_devices
"""
from fr_cli.command.registry import register


@register(
    name="ping_host",
    triggers=["ping", "连通", "探测", "延迟"],
    description="ping 探测目标主机连通性和延迟",
    params={"host": str},
    security="sec_fetch_web",
    aliases=["/ping"],
)
def _ping_host(deps, **kwargs):
    from fr_cli.weapon.network import ping_host
    result = ping_host(kwargs["host"])
    return result


@register(
    name="port_scan",
    triggers=["端口扫描", "scan port", "开放端口"],
    description="扫描目标主机的指定端口是否开放",
    params={"host": str, "ports": str},
    security="sec_exec",
    aliases=["/port_scan"],
)
def _port_scan(deps, **kwargs):
    from fr_cli.weapon.network import port_scan
    result = port_scan(kwargs["host"], kwargs["ports"])
    return result


@register(
    name="ip_scan",
    triggers=["IP扫描", "网段扫描", "存活主机", "ip scan"],
    description="扫描 CIDR 网段内的存活主机",
    params={"network": str},
    security="sec_exec",
    aliases=["/ip_scan"],
)
def _ip_scan(deps, **kwargs):
    from fr_cli.weapon.network import ip_scan
    result = ip_scan(kwargs["network"])
    return result


@register(
    name="network_devices",
    triggers=["网络设备", "设备扫描", "network devices", "设备发现"],
    description="扫描网段并识别网络设备（存活主机+开放端口+主机名）",
    params={"network": str},
    security="sec_exec",
    aliases=["/network_devices"],
)
def _network_devices(deps, **kwargs):
    from fr_cli.weapon.network import network_devices
    result = network_devices(kwargs["network"])
    return result
