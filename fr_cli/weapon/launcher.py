"""
本地应用启动器
支持跨平台调用浏览器、办公软件、通讯工具等本机程序。

安全说明（v2.8.7 加固）：
  Windows 分支原先用 `subprocess.Popen([...], shell=True)` 拼接命令行，
  而路径 / 应用名 / 目标均来自用户输入或 AI 生成 → 命令注入面。
  现已全部改为 **shell=False**：
    - 文件 / URL / URI 协议 → `os.startfile()`（ShellExecute，不经 shell）
    - 普通可执行名           → `subprocess.Popen([app], shell=False)`
  不再存在任何 `shell=True` 回退路径。
"""
import os
import platform
import subprocess

SYSTEM = platform.system()

# 常用应用别名映射表 —— 按平台映射到可执行命令或应用包名
_APP_ALIASES = {
    "Darwin": {
        # 浏览器
        "chrome": "Google Chrome",
        "googlechrome": "Google Chrome",
        "safari": "Safari",
        "firefox": "Firefox",
        "edge": "Microsoft Edge",
        "browser": "Safari",
        "浏览器": "Safari",
        # 办公
        "word": "Microsoft Word",
        "msword": "Microsoft Word",
        "excel": "Microsoft Excel",
        "msexcel": "Microsoft Excel",
        "powerpoint": "Microsoft PowerPoint",
        "ppt": "Microsoft PowerPoint",
        "mspowerpoint": "Microsoft PowerPoint",
        "wps": "WPS Office",
        # 通讯
        "wechat": "WeChat",
        "微信": "WeChat",
        "qq": "QQ",
        "tim": "Tencent TIM",
        "dingtalk": "DingTalk",
        "钉钉": "DingTalk",
        "飞书": "Lark",
        "lark": "Lark",
        # 编辑器 / 工具
        "notepad": "TextEdit",
        "textedit": "TextEdit",
        "记事本": "TextEdit",
        "notes": "Notes",
        "备忘录": "Notes",
        "vscode": "Visual Studio Code",
        "code": "Visual Studio Code",
        "terminal": "Terminal",
        "iterm": "iTerm",
        "终端": "Terminal",
        "计算器": "Calculator",
        "calc": "Calculator",
        "calculator": "Calculator",
        # 媒体
        "music": "Music",
        "itunes": "Music",
        "播放器": "Music",
        "spotify": "Spotify",
        "vlc": "VLC",
        "quicktime": "QuickTime Player",
        "photos": "Photos",
        "相册": "Photos",
        # 系统
        "finder": "Finder",
        "访达": "Finder",
        "systempreferences": "System Preferences",
        "系统偏好设置": "System Preferences",
        "appstore": "App Store",
        "app store": "App Store",
        "地图": "Maps",
        "maps": "Maps",
    },
    "Windows": {
        # 浏览器
        "chrome": "chrome",
        "googlechrome": "chrome",
        "edge": "msedge",
        "firefox": "firefox",
        "browser": "microsoft-edge:",
        "浏览器": "microsoft-edge:",
        # 办公
        "word": "winword",
        "msword": "winword",
        "excel": "excel",
        "msexcel": "excel",
        "powerpoint": "powerpnt",
        "ppt": "powerpnt",
        "mspowerpoint": "powerpnt",
        "wps": "wps",
        # 通讯
        "wechat": "WeChat",
        "微信": "WeChat",
        "qq": "QQ",
        "tim": "TIM",
        "dingtalk": "DingTalk",
        "钉钉": "DingTalk",
        "飞书": "Lark",
        "lark": "Lark",
        # 编辑器 / 工具
        "notepad": "notepad",
        "记事本": "notepad",
        "vscode": "code",
        "code": "code",
        "terminal": "wt",
        "终端": "wt",
        "计算器": "calc",
        "calc": "calc",
        "calculator": "calc",
        # 媒体
        "music": "mswindowsmusic:",
        "itunes": "itunes",
        "播放器": "mswindowsmusic:",
        "spotify": "spotify",
        "vlc": "vlc",
        "photos": "ms-photos:",
        "相册": "ms-photos:",
        # 系统
        "explorer": "explorer",
        "文件资源管理器": "explorer",
        "settings": "ms-settings:",
        "系统设置": "ms-settings:",
        "appstore": "ms-windows-store:",
        "app store": "ms-windows-store:",
    },
    "Linux": {
        # 浏览器
        "chrome": "google-chrome",
        "googlechrome": "google-chrome",
        "chromium": "chromium-browser",
        "firefox": "firefox",
        "edge": "microsoft-edge",
        "browser": "xdg-open",
        "浏览器": "xdg-open",
        # 办公
        "word": "libreoffice --writer",
        "excel": "libreoffice --calc",
        "powerpoint": "libreoffice --impress",
        "ppt": "libreoffice --impress",
        "wps": "wps",
        # 通讯
        "wechat": "wechat",
        "微信": "wechat",
        "qq": "qq",
        "lark": "lark",
        "飞书": "lark",
        # 编辑器 / 工具
        "notepad": "gedit",
        "记事本": "gedit",
        "vscode": "code",
        "code": "code",
        "terminal": "gnome-terminal",
        "终端": "gnome-terminal",
        "计算器": "gnome-calculator",
        "calc": "gnome-calculator",
        "calculator": "gnome-calculator",
        # 媒体
        "vlc": "vlc",
        "播放器": "vlc",
        "spotify": "spotify",
        # 系统
        "files": "nautilus",
        "文件管理器": "nautilus",
        "settings": "gnome-control-center",
        "系统设置": "gnome-control-center",
    },
}


def _resolve_app(name):
    """将别名解析为平台对应的应用标识"""
    key = name.lower().strip()
    plat = SYSTEM
    aliases = _APP_ALIASES.get(plat, {})
    return aliases.get(key, name)


def _normalize_windows_app(app: str) -> str:
    """去掉 Windows 应用标识里遗留的 cmd 内建命令前缀。

    别名表里曾经写过 "start microsoft-edge:" —— `start` 是 cmd 内建命令，
    只有经过 shell 才能工作。既然 Windows 分支已不再走 shell，就在这里
    剥掉这类前缀，得到可交给 ShellExecute / CreateProcess 的纯应用标识。
    """
    cleaned = (app or "").strip()
    lowered = cleaned.lower()
    for prefix in ("start ", "cmd /c ", "cmd /k "):
        if lowered.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    return cleaned


def _startfile(path, *args):
    """Windows 专用：用 os.startfile 打开文件 / URL / 应用（全程不经 shell）。

    Args:
        path: 文件路径、URL 或 URI 协议名（如 "ms-settings:"）
        args: 可选的 ShellExecute 参数（operation / args）

    Raises:
        RuntimeError: 当前解释器没有 os.startfile（非 Windows 或过老的 Python），
            此时**明确报错**而不是回退到 shell=True（回退即等于重新打开注入面）。
    """
    startfile = getattr(os, "startfile", None)
    if startfile is None:
        raise RuntimeError(
            "当前 Python 环境不支持 os.startfile，无法安全启动应用"
            "（为避免命令注入已禁用 shell 回退）"
        )
    startfile(path, *args)


def _open_windows(path, app=None):
    """在 Windows 上打开文件 / URL。

    - 纯路径或 URL → os.startfile(path)（ShellExecute 交给系统默认程序）
    - 指定应用     → 先试 os.startfile(app, "open", path)，
                     失败则退回 shell=False 的 Popen([app, path])（等价于旧
                     `start "" app path` 的语义，但不经 shell）
    """
    if app:
        try:
            _startfile(app, "open", path)
            return
        except OSError:
            subprocess.Popen(
                [app, path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
    _startfile(path)


def _launch_windows_app(app: str) -> None:
    """在 Windows 上启动一个应用标识（全程不经 shell，无命令注入面）。

    - URI 协议（如 ms-settings:）→ os.startfile（ShellExecute 才能接管协议）
    - 带空格的显示名（如 WeChat）→ 先 os.startfile（会查 App Paths 注册表），
      失败再退回 shell=False 的 Popen
    - 普通可执行名（如 notepad）→ Popen([app], shell=False)，CreateProcess 直连
    """
    if app.endswith(":"):
        _startfile(app)
        return
    if " " in app:
        try:
            _startfile(app)
            return
        except OSError:
            pass
    subprocess.Popen([app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_file(path, lang="zh"):
    """用系统默认程序打开文件或 URL（跨平台），返回 (result, error)"""
    if not path:
        return None, "路径为空" if lang == "zh" else "Empty path"
    try:
        if SYSTEM == "Darwin":
            subprocess.Popen(["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif SYSTEM == "Windows":
            # os.startfile 走 ShellExecute：文件与 URL 都能交给系统默认程序
            _open_windows(path)
        else:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"已打开: {path}" if lang == "zh" else f"Opened: {path}", None
    except Exception as e:
        return None, str(e)


def launch_app(name, target=None, lang="zh"):
    """启动指定应用程序，可选传入文件/URL 作为目标，返回 (result, error)"""
    if not name:
        return None, "应用名称为空" if lang == "zh" else "Empty app name"

    app = _resolve_app(name)

    try:
        if SYSTEM == "Darwin":
            cmd = ["open", "-a", app]
            if target:
                cmd.append(target)
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif SYSTEM == "Windows":
            app = _normalize_windows_app(app)
            if target:
                # URL 交给系统默认浏览器；文件则用指定应用打开
                if target.startswith("http"):
                    _startfile(target)
                else:
                    _open_windows(target, app=app)
            elif app.endswith(":"):
                # URI 协议（如 ms-settings:）—— 只能由 ShellExecute 接管
                _startfile(app)
            else:
                # 普通可执行名 / 带空格显示名：不经 shell
                _launch_windows_app(app)
        else:
            # Linux
            parts = app.split()
            cmd = parts.copy()
            if target:
                cmd.append(target)
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        msg = f"已启动: {name}" if lang == "zh" else f"Launched: {name}"
        if target:
            msg += f" ({target})"
        return msg, None
    except Exception as e:
        return None, str(e)


def list_apps(lang="zh"):
    """列出当前平台支持的应用别名"""
    plat = SYSTEM
    aliases = _APP_ALIASES.get(plat, {})
    if not aliases:
        return None, "暂无预置应用列表" if lang == "zh" else "No app list available"

    items = []
    seen = set()
    for alias, real in sorted(aliases.items()):
        if real not in seen:
            seen.add(real)
            items.append(f"  {real:<30} ← {alias}")
    header = "本机可用应用映射:" if lang == "zh" else "Available app mappings:"
    return header + "\n" + "\n".join(items), None
