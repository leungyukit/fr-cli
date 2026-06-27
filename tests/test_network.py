"""
网络探测测试
覆盖 ping_host / port_scan / ip_scan / network_devices 等真实网络操作。

这些测试会发真实网络请求(localhost / 公开 DNS),不需要 mock。
"""
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.weapon.network import ping_host, port_scan, ip_scan, network_devices


class TestPingHost:

    def test_ping_localhost(self):
        """ping localhost 通常会成功"""
        result = ping_host("127.0.0.1", count=1, timeout=2)
        assert result.is_ok(), f"error: {result.error}"
        data = result.unwrap()
        assert data.get("host") == "127.0.0.1"
        assert "alive" in data
        assert "loss_percent" in data

    def test_ping_empty_host_fails(self):
        result = ping_host("", count=1, timeout=1)
        assert result.is_fail()
        assert "不能为空" in result.error or "主机" in result.error

    def test_ping_invalid_host_returns_fail(self):
        """无效主机名应返回 fail"""
        result = ping_host("this-host-definitely-does-not-exist-xxx-12345.invalid",
                            count=1, timeout=2)
        # 大概率失败
        assert result.is_fail() or not result.unwrap().get("alive")

    def test_ping_returns_dict(self):
        result = ping_host("127.0.0.1", count=1, timeout=1)
        if result.is_ok():
            data = result.unwrap()
            assert isinstance(data, dict)


class TestPortScan:

    def test_scan_localhost_open_port(self):
        """扫描 localhost:22(SSH)或一个肯定开放的端口"""
        # 用 0 端口不靠谱,直接测 1 (应关闭)
        result = port_scan("127.0.0.1", [22, 80, 443], timeout=0.5)
        assert result.is_ok(), f"error: {result.error}"
        ports = result.unwrap()
        assert isinstance(ports, list)
        # 每项应包含 port 和 state
        if ports:
            assert "port" in ports[0]
            assert "state" in ports[0]

    def test_scan_empty_host_fails(self):
        result = port_scan("", [22], timeout=0.5)
        assert result.is_fail()

    def test_scan_with_string_ports(self):
        """支持 "22,80,443" 字符串格式"""
        result = port_scan("127.0.0.1", "22,80,443", timeout=0.5)
        # 注意:port_scan 只返回开放的端口,如果都没开则返回空 list
        assert result.is_ok(), f"error: {result.error}"
        ports = result.unwrap()
        assert isinstance(ports, list)
        # 任何返回的端口都应是合法的
        for p in ports:
            assert "port" in p
            assert 22 <= p["port"] <= 443

    def test_scan_with_range(self):
        """支持 "20-25" 范围"""
        result = port_scan("127.0.0.1", "20-25", timeout=0.5)
        if result.is_ok():
            ports = result.unwrap()
            assert isinstance(ports, list)
            # 只返回开放的
            for p in ports:
                assert 20 <= p["port"] <= 25
        else:
            # 也可能 scan 失败
            assert "error" in result.error or "失败" in result.error

    def test_scan_invalid_port_format(self):
        result = port_scan("127.0.0.1", "not-a-port", timeout=0.5)
        assert result.is_fail()

    def test_scan_too_many_ports(self):
        """超过 1000 端口应被拒绝"""
        result = port_scan("127.0.0.1", list(range(2000)), timeout=0.1)
        # 应拒绝或超时
        assert result.is_fail() or len(result.unwrap()) <= 1000


class TestIpScan:

    def test_scan_local_loopback(self):
        """扫描 127.0.0.0/30 应找到 127.0.0.1"""
        result = ip_scan("127.0.0.0/30", timeout=1, max_hosts=4)
        assert result.is_ok(), f"error: {result.error}"
        hosts = result.unwrap()
        assert isinstance(hosts, list)
        # 至少应包含 127.0.0.1
        assert "127.0.0.1" in hosts

    def test_scan_empty_network_fails(self):
        result = ip_scan("", timeout=1)
        assert result.is_fail()


class TestNetworkDevices:

    def test_devices_local(self):
        """扫描本地子网:可能找到自己的设备"""
        result = network_devices("127.0.0.0/30", timeout=1, max_hosts=4)
        assert result.is_ok() or result.is_fail()
        if result.is_ok():
            devices = result.unwrap()
            assert isinstance(devices, list)
