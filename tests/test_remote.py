"""
SSH / SCP 远程命令端到端测试
使用 paramiko.Transport 启动本地 mock SSH server(127.0.0.1:2222),
通过 fr_cli.weapon.remote.{ssh_command, scp_transfer} 连接并验证行为。

注意:本测试需要 paramiko >= 3.0,可通过 extras 安装:
    pip install -e ".[remote]"
"""
import os
import socket
import sys
import threading
import time

import paramiko
import pytest

# 把项目根加进 path,使 fr_cli 可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.weapon.remote import ssh_command, scp_transfer


# ==================== Mock SSH Server ====================

HOST_KEY = paramiko.RSAKey.generate(2048)
MOCK_PORT = 2222
MOCK_USER = "testuser"
MOCK_PASS = "testpass"


class MockServer(paramiko.ServerInterface):
    """Mock SSH 服务器,支持 echo / pwd / ls / fail / cat 命令"""

    def check_channel_request(self, kind, chanid):
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        if username == MOCK_USER and password == MOCK_PASS:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_channel_exec_request(self, channel, command):
        cmd = command.decode() if isinstance(command, bytes) else command
        if cmd.startswith("echo "):
            channel.sendall(cmd[5:].encode() + b"\n")
            channel.send_exit_status(0)
        elif cmd == "pwd":
            channel.sendall(b"/home/test\n")
            channel.send_exit_status(0)
        elif cmd == "ls":
            channel.sendall(b"file1.txt\nfile2.txt\n")
            channel.send_exit_status(0)
        elif cmd == "whoami":
            channel.sendall(b"testuser\n")
            channel.send_exit_status(0)
        elif cmd == "fail":
            channel.sendall(b"partial output\n")
            channel.sendall_stderr(b"error message\n")
            channel.send_exit_status(1)
        elif cmd.startswith("cat "):
            path = cmd[4:].strip()
            try:
                with open(path) as f:
                    channel.sendall(f.read().encode())
            except Exception as e:
                channel.sendall_stderr(f"ERROR: {e}".encode())
            channel.send_exit_status(0)
        else:
            channel.sendall(f"unknown: {cmd}\n".encode())
            channel.send_exit_status(0)
        return True


def _run_mock_server(stop_event):
    """后台线程:在 127.0.0.1:MOCK_PORT 接受连接并启动 SSH 会话"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", MOCK_PORT))
    sock.listen(5)
    sock.settimeout(0.5)
    while not stop_event.is_set():
        try:
            client, _ = sock.accept()
        except socket.timeout:
            continue
        except Exception:
            break
        try:
            transport = paramiko.Transport(client)
            transport.add_server_key(HOST_KEY)
            transport.start_server(server=MockServer())
            chan = transport.accept(20)
            if chan is not None:
                chan.settimeout(5)
                # 不立即关闭 channel,等 client 读完 stdout/stderr + recv_exit_status
                time.sleep(0.3)
                chan.close()
            transport.close()
        except Exception:
            pass
    sock.close()


# ==================== Fixtures ====================

@pytest.fixture(scope="module", autouse=True)
def mock_ssh_server():
    """模块级 fixture:为整组测试启动一次 mock SSH server"""
    stop_event = threading.Event()
    t = threading.Thread(target=_run_mock_server, args=(stop_event,), daemon=True)
    t.start()
    time.sleep(0.5)  # 等 server 就绪
    yield
    stop_event.set()
    time.sleep(0.3)


# ==================== 测试用例 ====================

class TestSSHCommand:
    """ssh_command 远程执行测试"""

    def test_01_echo_returns_correct_stdout(self):
        """echo 命令:stdout + returncode=0"""
        result = ssh_command(
            host="127.0.0.1", user=MOCK_USER, command="echo hello-fr-cli",
            password=MOCK_PASS, port=MOCK_PORT, timeout=10, allowed_dirs=[],
        )
        assert result.is_ok(), f"ssh 应成功,实际 error={result.error}"
        data = result.unwrap()
        assert data.get("stdout") == "hello-fr-cli\n"
        assert data.get("returncode") == 0
        assert data.get("stderr") == ""

    def test_02_pwd_returns_working_directory(self):
        """pwd 命令:返回 mock 的工作目录"""
        result = ssh_command(
            host="127.0.0.1", user=MOCK_USER, command="pwd",
            password=MOCK_PASS, port=MOCK_PORT, timeout=10, allowed_dirs=[],
        )
        assert result.is_ok(), result.error
        data = result.unwrap()
        assert data.get("stdout") == "/home/test\n"
        assert data.get("returncode") == 0

    def test_03_failed_command_captures_returncode_and_stderr(self):
        """失败命令:returncode=1 + stderr 包含错误信息 + stdout 仍有部分输出"""
        result = ssh_command(
            host="127.0.0.1", user=MOCK_USER, command="fail",
            password=MOCK_PASS, port=MOCK_PORT, timeout=10, allowed_dirs=[],
        )
        # ssh_command 把命令本身视为"成功执行",只是 returncode 非 0
        assert result.is_ok(), "命令执行本身应成功"
        data = result.unwrap()
        assert data.get("returncode") == 1
        assert "error message" in data.get("stderr", "")
        assert "partial output" in data.get("stdout", "")

    def test_04_wrong_password_rejected(self):
        """错误密码:认证失败"""
        result = ssh_command(
            host="127.0.0.1", user=MOCK_USER, command="ls",
            password="WRONG", port=MOCK_PORT, timeout=10, allowed_dirs=[],
        )
        assert not result.is_ok(), "认证失败应返回 fail"
        # error 信息应包含认证相关关键词
        assert any(kw in result.error.lower() for kw in ["auth", "认证", "password"])

    def test_05_empty_host_rejected(self):
        """空 host:参数校验失败"""
        result = ssh_command(host="", user="x", command="ls", password="x")
        assert not result.is_ok()
        assert "host" in result.error.lower() or "不能为空" in result.error

    def test_06_unreachable_port_returns_fail(self):
        """端口无人监听:连接失败"""
        result = ssh_command(
            host="127.0.0.1", user="x", command="ls",
            password="x", port=9999, timeout=3, allowed_dirs=[],
        )
        assert not result.is_ok()
        # 错误信息应提到连接失败
        assert any(kw in result.error.lower() for kw in ["connect", "连接", "refused", "timeout", "失败"])

    def test_07_empty_user_rejected(self):
        """空 user:参数校验失败"""
        result = ssh_command(
            host="127.0.0.1", user="", command="ls",
            password="x", port=MOCK_PORT, timeout=10, allowed_dirs=[],
        )
        assert not result.is_ok()
        assert "user" in result.error.lower() or "不能为空" in result.error

    def test_08_empty_command_rejected(self):
        """空 command:参数校验失败"""
        result = ssh_command(
            host="127.0.0.1", user=MOCK_USER, command="",
            password=MOCK_PASS, port=MOCK_PORT, timeout=10, allowed_dirs=[],
        )
        assert not result.is_ok()
        assert "command" in result.error.lower() or "不能为空" in result.error


class TestSCPTransfer:
    """scp_transfer 文件传输测试(本测试覆盖错误路径,SFTP 上传/下载需真实 sshd)"""

    def test_09_upload_nonexistent_file_returns_fail(self):
        """上传不存在的本地文件:应失败"""
        result = scp_transfer(
            host="127.0.0.1", user=MOCK_USER,
            local_path="/nonexistent/file_xxx.txt",
            remote_path="/tmp/test.txt",
            direction="up", password=MOCK_PASS,
            port=MOCK_PORT, timeout=10, allowed_dirs=[],
        )
        assert not result.is_ok()

    def test_10_invalid_direction_rejected(self):
        """错误的 direction 参数:应失败"""
        result = scp_transfer(
            host="127.0.0.1", user=MOCK_USER,
            local_path="/tmp/any.txt", remote_path="/tmp/test.txt",
            direction="invalid", password=MOCK_PASS,
            port=MOCK_PORT, timeout=10, allowed_dirs=[],
        )
        assert not result.is_ok()