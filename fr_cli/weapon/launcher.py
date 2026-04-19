"""
本地应用启动器 —— 驭器神通
支持跨平台调用浏览器、办公软件、通讯工具等本机程序。
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
        "browser": "start microsoft-edge:",
        "浏览器": "start microsoft-edge:",
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


def open_file(path, lang="zh"):
    """用系统默认程序打开文件或 URL（跨平台）"""
    if not path:
        return False, "路径为空" if lang == "zh" else "Empty path"
    try:
        if SYSTEM == "Darwin":
            subprocess.Popen(["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif SYSTEM == "Windows":
            subprocess.Popen(["start", "", path], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, f"已打开: {path}" if lang == "zh" else f"Opened: {path}"
    except Exception as e:
        return False, str(e)


def launch_app(name, target=None, lang="zh"):
    """启动指定应用程序，可选传入文件/URL 作为目标"""
    if not name:
        return False, "应用名称为空" if lang == "zh" else "Empty app name"

    app = _resolve_app(name)

    try:
        if SYSTEM == "Darwin":
            cmd = ["open", "-a", app]
            if target:
                cmd.append(target)
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif SYSTEM == "Windows":
            # Windows 某些应用支持直接传目标，某些用 start
            if target:
                # 如果是 URL，直接用 start；如果是文件，用应用打开
                if target.startswith("http"):
                    subprocess.Popen(["start", "", target], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(["start", "", "", app, target], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                # 某些 Windows 命令本身就是 URI 协议或 shell 命令
                if app.endswith(":") or " " in app:
                    subprocess.Popen([app], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(["start", "", app], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        return True, msg
    except Exception as e:
        return False, str(e)


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
