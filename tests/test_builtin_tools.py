"""
内置工具测试
覆盖新增的文件改名、文本替换、正则匹配、网络探测、远程访问工具
"""
import pytest
from pathlib import Path


@pytest.fixture
def vfs(tmp_path):
    """创建基于临时目录的 VFS 实例"""
    from fr_cli.weapon.fs import VFS
    return VFS([str(tmp_path)])


class TestVFSRename:
    """测试 VFS 重命名"""

    def test_rename_file(self, vfs, tmp_path):
        (tmp_path / "old.txt").write_text("content", encoding="utf-8")
        result = vfs.rename("old.txt", "new.txt", "zh")
        assert result.is_ok()
        assert not (tmp_path / "old.txt").exists()
        assert (tmp_path / "new.txt").exists()

    def test_rename_outside_sandbox_fails(self, vfs, tmp_path):
        result = vfs.rename("../escape.txt", "new.txt", "zh")
        assert result.is_fail()


class TestVFSReplaceText:
    """测试 VFS 文本替换"""

    def test_replace_plain_text(self, vfs, tmp_path):
        (tmp_path / "file.txt").write_text("hello world\nhello python", encoding="utf-8")
        result = vfs.replace_text("file.txt", "hello", "hi", False, "zh")
        assert result.is_ok()
        content = (tmp_path / "file.txt").read_text(encoding="utf-8")
        assert content == "hi world\nhi python"

    def test_replace_regex(self, vfs, tmp_path):
        (tmp_path / "file.txt").write_text("foo123 bar456", encoding="utf-8")
        result = vfs.replace_text("file.txt", r"\d+", "X", True, "zh")
        assert result.is_ok()
        content = (tmp_path / "file.txt").read_text(encoding="utf-8")
        assert content == "fooX barX"

    def test_replace_no_match(self, vfs, tmp_path):
        (tmp_path / "file.txt").write_text("content", encoding="utf-8")
        result = vfs.replace_text("file.txt", "notfound", "x", False, "zh")
        assert result.is_fail()


class TestVFSGrepText:
    """测试 VFS 文本搜索"""

    def test_grep_plain_text(self, vfs, tmp_path):
        (tmp_path / "file.txt").write_text("line1\nhello world\nline3", encoding="utf-8")
        result = vfs.grep_text("file.txt", "hello", False, "zh")
        assert result.is_ok()
        assert "hello world" in result.unwrap()

    def test_grep_regex(self, vfs, tmp_path):
        (tmp_path / "file.txt").write_text("abc123\ndef456\nghi789", encoding="utf-8")
        result = vfs.grep_text("file.txt", r"[a-z]+\d+", True, "zh")
        assert result.is_ok()
        assert "abc123" in result.unwrap()
        assert "def456" in result.unwrap()

    def test_grep_no_match(self, vfs, tmp_path):
        (tmp_path / "file.txt").write_text("content", encoding="utf-8")
        result = vfs.grep_text("file.txt", "notfound", False, "zh")
        assert result.is_ok()
        assert "未找到" in result.unwrap() or "No match" in result.unwrap()


class TestNetworkTools:
    """测试网络探测工具"""

    def test_parse_ports_string(self):
        from fr_cli.weapon.network import _parse_ports
        assert _parse_ports("22,80,443") == [22, 80, 443]
        assert _parse_ports("1-3") == [1, 2, 3]
        assert _parse_ports("22,80-82") == [22, 80, 81, 82]
        assert _parse_ports([]) == []
        assert _parse_ports(None) == []

    def test_ping_localhost(self):
        from fr_cli.weapon.network import ping_host
        result = ping_host("127.0.0.1", count=1, timeout=2)
        assert result.is_ok()
        res = result.unwrap()
        assert res["host"] == "127.0.0.1"
        assert isinstance(res["alive"], bool)

    def test_port_scan_localhost(self):
        from fr_cli.weapon.network import port_scan
        # 扫描一个常见端口，避免失败
        result = port_scan("127.0.0.1", "22", timeout=1)
        assert result.is_ok()
        assert isinstance(result.unwrap(), list)

    def test_ip_scan_loopback(self):
        from fr_cli.weapon.network import ip_scan
        # 扫描 127.0.0.0/30 仅包含 2 个主机
        result = ip_scan("127.0.0.0/30", timeout=1)
        assert result.is_ok()
        assert "127.0.0.1" in result.unwrap()


class TestRemoteTools:
    """测试远程访问工具"""

    def test_safe_key_path(self):
        from fr_cli.weapon.remote import _is_safe_key_path
        home_ssh = str(Path.home() / ".ssh" / "id_rsa")
        assert _is_safe_key_path(home_ssh, ["/tmp"])
        assert _is_safe_key_path("/tmp/key", ["/tmp"])
        assert not _is_safe_key_path("/etc/passwd", ["/tmp"])
        assert _is_safe_key_path(None, ["/tmp"])

    def test_ssh_command_missing_param(self):
        from fr_cli.weapon.remote import ssh_command
        result = ssh_command("", "user", "cmd")
        assert result.is_fail()

    def test_scp_transfer_invalid_direction(self):
        from fr_cli.weapon.remote import scp_transfer
        result = scp_transfer("host", "user", "local", "remote", direction="sideways")
        assert result.is_fail()


class TestRegistryParsing:
    """测试注册表对新命令的参数解析"""

    def test_parse_rename(self):
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        kwargs = reg._parse_cmd_args(["/rename", "a.txt", "b.txt"], {"name": "rename_file"}, None)
        assert kwargs == {"old_path": "a.txt", "new_path": "b.txt"}

    def test_parse_replace(self):
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        kwargs = reg._parse_cmd_args(["/replace", "file.txt", "old", "new", "true"], {"name": "replace_text"}, None)
        assert kwargs["path"] == "file.txt"
        assert kwargs["old_text"] == "old"
        assert kwargs["new_text"] == "new"
        assert kwargs["use_regex"] is True

    def test_parse_grep(self):
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        kwargs = reg._parse_cmd_args(["/grep", "file.txt", "pattern"], {"name": "grep_text"}, None)
        assert kwargs == {"path": "file.txt", "pattern": "pattern", "use_regex": False}

    def test_parse_ping(self):
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        kwargs = reg._parse_cmd_args(["/ping", "example.com"], {"name": "ping_host"}, None)
        assert kwargs == {"host": "example.com"}

    def test_parse_ssh(self):
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        kwargs = reg._parse_cmd_args(["/ssh", "host", "user", "uname", "-a"], {"name": "ssh_command"}, None)
        assert kwargs["host"] == "host"
        assert kwargs["user"] == "user"
        assert kwargs["command"] == "uname -a"
