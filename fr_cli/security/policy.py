"""
安全策略常量 —— 自治模式分级

定义哪些 sec_* 类别属于"沙盒内安全"（可在 sandbox_auto 模式下自动放行），
哪些属于"系统级操作"（即使自治模式仍需要显式确认或在非交互环境下默认拒绝）。

单一真相源：所有自治模式的权限判断都应引用这里的常量，而不是散落硬编码。
"""

# 沙盒安全：操作被限制在 VFS allowed_dirs 内，或是只读/有界的网络调用
# 在 autonomous_mode="sandbox_auto" 下会自动放行
SANDBOX_SECURITY_KEYS = frozenset({
    "sec_read",          # 读文件、列表、grep、OCR、读 Excel/CSV 等
    "sec_write",         # 写/删/改 VFS 内的文件（已受路径沙盒约束）
    "sec_fetch_web",     # 网页搜索/抓取（只读网络访问）
    "sec_gen_img",       # 图片生成（ bounded API 调用，输出写入 VFS）
})

# 系统安全：跨沙盒边界或具有不可控副作用
# 即使在 sandbox_auto 模式下也不会自动放行，仍走 Y/A/F/N 确认流程
SYSTEM_SECURITY_KEYS = frozenset({
    "sec_shell",         # 任意系统 shell 命令
    "sec_exec",          # 执行法宝/Agent/动态构建/安装包/远程命令等
    "sec_send_mail",     # 发送邮件
    "sec_read_mail",     # 读取邮件
    "sec_upload_disk",   # 上传到云盘
    "sec_download_disk", # 从云盘下载
    "sec_mcp_call",      # MCP 外部神通（能力未知）
    "sec_open_file",     # 用系统默认程序打开文件
    "sec_launch_app",    # 启动本地应用
    "sec_create_agent",  # 创建 Agent 分身
    "sec_update",        # 程序自更新
    "sec_mount",         # 添加 allowed_dirs，扩大沙盒边界
    "sec_set_key",       # 修改 API Key
    "sec_set_model",     # 修改模型配置
    "sec_set_limit",     # 修改 token 上限
    "sec_set_lang",      # 修改语言
    "sec_set_alias",     # 修改命令别名
})

# 允许的自治模式取值
VALID_AUTONOMOUS_MODES = frozenset({"manual", "sandbox_auto", "full_auto"})


def is_sandbox_key(key: str) -> bool:
    """判断某个 sec_* 类别是否属于沙盒安全级别"""
    return key in SANDBOX_SECURITY_KEYS


def is_system_key(key: str) -> bool:
    """判断某个 sec_* 类别是否属于系统安全级别"""
    return key in SYSTEM_SECURITY_KEYS


def normalize_autonomous_mode(mode: str) -> str:
    """规范化自治模式字符串，非法值回退到 manual"""
    mode = (mode or "manual").strip().lower()
    if mode == "off":
        return "manual"
    return mode if mode in VALID_AUTONOMOUS_MODES else "manual"
