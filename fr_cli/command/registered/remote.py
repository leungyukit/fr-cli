"""
注册表分组：远程访问类工具
- ssh_command / scp_transfer
"""
from fr_cli.command.registry import register


@register(
    name="ssh_command",
    triggers=["ssh", "远程命令", "远程执行"],
    description="通过 SSH 在远程主机执行命令",
    params={"host": str, "user": str, "command": str},
    security="sec_exec",
    aliases=["/ssh"],
)
def _ssh_command(deps, **kwargs):
    from fr_cli.weapon.remote import ssh_command
    allowed_dirs = getattr(deps, "vfs", None) and getattr(deps.vfs, "ds", None)
    result = ssh_command(
        host=kwargs["host"],
        user=kwargs["user"],
        command=kwargs["command"],
        password=kwargs.get("password"),
        key_path=kwargs.get("key_path"),
        port=kwargs.get("port", 22),
        timeout=kwargs.get("timeout", 30),
        allowed_dirs=allowed_dirs,
    )
    return result


@register(
    name="scp_transfer",
    triggers=["scp", "上传", "下载", "远程传输"],
    description="通过 SFTP/SCP 上传或下载文件",
    params={"host": str, "user": str, "local_path": str, "remote_path": str},
    security="sec_exec",
    aliases=["/scp"],
)
def _scp_transfer(deps, **kwargs):
    from fr_cli.weapon.remote import scp_transfer
    allowed_dirs = getattr(deps, "vfs", None) and getattr(deps.vfs, "ds", None)
    result = scp_transfer(
        host=kwargs["host"],
        user=kwargs["user"],
        local_path=kwargs["local_path"],
        remote_path=kwargs["remote_path"],
        direction=kwargs.get("direction", "up"),
        password=kwargs.get("password"),
        key_path=kwargs.get("key_path"),
        port=kwargs.get("port", 22),
        timeout=kwargs.get("timeout", 30),
        allowed_dirs=allowed_dirs,
    )
    return result
