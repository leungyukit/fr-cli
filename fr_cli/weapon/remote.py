"""
远程访问工具 —— SSH 命令执行与 SCP/SFTP 文件传输
供大模型通过注册表工具调用
"""
from pathlib import Path

from fr_cli.core.result import Result


def _is_safe_key_path(key_path: str, allowed_dirs: list) -> bool:
    """校验私钥路径是否位于允许的目录或用户 ~/.ssh/ 下"""
    if not key_path:
        return True
    try:
        p = Path(key_path).expanduser().resolve()
    except Exception:
        return False

    # 允许 ~/.ssh/ 下的密钥
    home_ssh = Path.home() / ".ssh"
    try:
        p.relative_to(home_ssh)
        return True
    except ValueError:
        pass

    # 允许 VFS 沙盒内的密钥
    for d in allowed_dirs or []:
        try:
            p.relative_to(Path(d).resolve())
            return True
        except ValueError:
            continue

    return False


def _get_connect_kwargs(host, port, user, password, key_path, timeout, allowed_dirs):
    """构建 paramiko SSHClient.connect 参数"""
    kwargs = {
        "hostname": host,
        "port": int(port) if port else 22,
        "username": user,
        "timeout": timeout,
        "look_for_keys": True,
        "allow_agent": True,
    }
    if password:
        kwargs["password"] = password
    if key_path:
        if not _is_safe_key_path(key_path, allowed_dirs):
            raise ValueError(f"私钥路径不在允许范围内: {key_path}")
        kwargs["key_filename"] = str(Path(key_path).expanduser().resolve())
    return kwargs


def ssh_command(host: str, user: str, command: str, password: str = None,
                key_path: str = None, port: int = 22, timeout: int = 30,
                allowed_dirs: list = None):
    """通过 SSH 在远程主机执行命令，返回 Result[dict]。"""
    try:
        import paramiko
    except ImportError:
        return Result.fail("缺少依赖 paramiko，请安装: pip install paramiko>=3.0.0")

    if not host or not user or not command:
        return Result.fail("host/user/command 不能为空")

    client = None
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = _get_connect_kwargs(host, port, user, password, key_path, timeout, allowed_dirs)
        client.connect(**kwargs)

        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="ignore")
        err = stderr.read().decode("utf-8", errors="ignore")
        rc = stdout.channel.recv_exit_status()

        return Result.ok({
            "host": host,
            "command": command,
            "stdout": out,
            "stderr": err,
            "returncode": rc,
        })
    except Exception as e:
        return Result.fail(f"SSH 执行失败: {e}")
    finally:
        if client:
            client.close()


def scp_transfer(host: str, user: str, local_path: str, remote_path: str,
                 direction: str = "up", password: str = None, key_path: str = None,
                 port: int = 22, timeout: int = 30, allowed_dirs: list = None):
    """通过 SFTP 上传或下载文件，返回 Result[str]。"""
    try:
        import paramiko
    except ImportError:
        return Result.fail("缺少依赖 paramiko，请安装: pip install paramiko>=3.0.0")

    if not host or not user or not local_path or not remote_path:
        return Result.fail("host/user/local_path/remote_path 不能为空")

    direction = direction.lower()
    if direction not in ("up", "down"):
        return Result.fail("direction 必须是 up 或 down")

    client = None
    sftp = None
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = _get_connect_kwargs(host, port, user, password, key_path, timeout, allowed_dirs)
        client.connect(**kwargs)
        sftp = client.open_sftp()

        if direction == "up":
            sftp.put(local_path, remote_path)
            return Result.ok(f"上传完成: {local_path} -> {host}:{remote_path}")
        else:
            sftp.get(remote_path, local_path)
            return Result.ok(f"下载完成: {host}:{remote_path} -> {local_path}")
    except Exception as e:
        return Result.fail(f"SCP 传输失败: {e}")
    finally:
        if sftp:
            sftp.close()
        if client:
            client.close()
