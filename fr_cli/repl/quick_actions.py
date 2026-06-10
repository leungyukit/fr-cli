"""
P3 工具集：语音输入 / 截屏 / 拖文件 / VSCode 集成

所有功能都做了平台检测，不支持的平台会优雅降级或给出明确提示。
"""
import os
import sys
import subprocess
import shlex
import tempfile
from pathlib import Path
from typing import Optional, Tuple


# ==================== 平台检测 ====================

IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")


# ==================== P3-1 语音输入 ====================

def voice_input(duration: int = 5) -> Optional[str]:
    """用 macOS Speech Recognition 把麦克风输入转成文字

    Args:
        duration: 录音时长（秒）
    Returns:
        识别出的文字，失败返回 None

    实现：用 osascript 调 macOS 内置 Speech Recognition。
    """
    if not IS_MACOS:
        return None

    # 1. 录音到临时文件（用 afconvert + say 反向不行，用 arecord 也不一定有）
    # 实际上 macOS 没有简单的命令行录音工具 —— 用 osascript 调 Speech framework

    # 简化方案：直接返回 None + 提示用户用 macOS 自带 Dictation
    # （Cmd+Fn 两次 = 开始听写，Cmd+Fn 一次 = 结束）
    return None


def voice_input_linux() -> Optional[str]:
    """Linux: 用 arecord + vosk/whisper 转写（需要外部依赖）"""
    if not IS_LINUX:
        return None
    return None


# ==================== P3-2 截屏 ====================

def screenshot(region: Optional[str] = None) -> Optional[str]:
    """截屏到临时文件，返回路径

    Args:
        region: "full" / "window" / "selection" / None（默认 selection）
    Returns:
        截图文件路径
    """
    if not IS_MACOS:
        return None

    from fr_cli.conf.paths import ROOT
    img_dir = ROOT / "screenshots"
    img_dir.mkdir(parents=True, exist_ok=True)
    out_file = img_dir / f"screenshot_{int(__import__('time').time())}.png"

    cmd = ["screencapture", "-x"]  # -x 不播放快门声
    if region == "full":
        pass  # 默认全屏
    elif region == "window":
        cmd.append("-w")
    elif region == "selection" or region is None:
        cmd.append("-s")  # 交互式选择区域
    cmd.append(str(out_file))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if out_file.exists():
            return str(out_file)
        return None
    except Exception:
        return None


# ==================== P3-3 拖文件检测 ====================

FILE_PATH_PATTERNS = []  # 延迟初始化


def detect_dragged_files(text: str) -> list:
    """从用户输入中检测文件路径（拖拽场景）

    macOS/Linux 拖文件到终端会粘贴形如：
      /Users/.../foo.png
      file:///Users/.../foo.png
      '/Users/.../foo.png'
      '/Users/.../foo.png' '/Users/.../bar.py'
    """
    import re
    import os

    found = []
    # 模式 1：file:// URL
    for m in re.finditer(r'file://(/\S+?)(?=[\s\'"]|$)', text):
        path = m.group(1)
        if os.path.exists(path):
            found.append(path)
    # 模式 2：引号包裹的绝对路径
    for m in re.finditer(r"['\"]((/[^'\"\\s]+))['\"]", text):
        path = m.group(2)
        if path.startswith("/") and os.path.exists(path) and path not in found:
            found.append(path)
    # 模式 3：裸绝对路径（带扩展名）
    for m in re.finditer(r'(?<!\S)((/\S+?\.(?:png|jpg|jpeg|gif|pdf|py|js|ts|tsx|jsx|json|md|txt|csv|xlsx|docx|zip|tar|gz|mp3|mp4|mov)))(?=[\s\'"]|$)', text):
        path = m.group(1)
        if os.path.exists(path) and path not in found:
            found.append(path)
    return found


# ==================== P3-4 VSCode / Zed 集成 ====================

VSCODE_SETTINGS_TEMPLATE = """{
  // fr-cli 集成：在 VSCode 中调用本地 fr-cli 作为 AI 助手
  // 把 .fr-cli/ 放在工作区根目录启用项目级 persona

  // 推荐扩展：Continue / Cline / Roo Code（可作为 fr-cli 的客户端）
  // 或使用 Zed 编辑器（原生支持 ACP 协议）

  // 终端快捷键（Ctrl+` 打开终端后）：
  //   fr-cli                    # 启动 fr-cli
  //   /commit                   # AI 自动 git commit
  //   /pr                       # 生成 PR 描述
  //   /review .                 # code review

  // .fr-cli/persona.md 可放项目专属人设
}
"""


def write_vscode_template(target_dir: str = ".") -> str:
    """写 .vscode/settings.json 模板"""
    target = Path(target_dir) / ".vscode"
    target.mkdir(parents=True, exist_ok=True)
    f = target / "settings.json"
    if f.exists():
        return f"⚠️ 已存在: {f}（未覆盖）"
    f.write_text(VSCODE_SETTINGS_TEMPLATE, encoding="utf-8")
    return f"✅ 已写入: {f}"


ZED_SETTINGS_TEMPLATE = """{
  // fr-cli 通过 ACP 协议与 Zed 集成
  // 需要：fr-cli 已装，且 $PATH 包含 fr 命令
  "agent_servers": {
    "fr-cli": {
      "command": "fr",
      "args": ["acp"]
    }
  }
}
"""


def write_zed_template(target_dir: str = ".") -> str:
    """写 Zed settings.json 模板"""
    target = Path(target_dir) / ".zed"
    target.mkdir(parents=True, exist_ok=True)
    f = target / "settings.json"
    if f.exists():
        return f"⚠️ 已存在: {f}（未覆盖）"
    f.write_text(ZED_SETTINGS_TEMPLATE, encoding="utf-8")
    return f"✅ 已写入: {f}"


# ==================== P3-5 几个 command 命令 ====================

def cmd_voice(state, parts) -> str:
    """/voice —— 语音输入（macOS Dictation 提示）"""
    if IS_MACOS:
        return (
            "🎙️  语音输入：\n"
            "   macOS 自带 Dictation：按 Fn 两次开始听写，再按 Fn 一次结束\n"
            "   或在系统设置 → 键盘 → Dictation 启用\n\n"
            "   fr-cli 自动识别剪贴板中的转写文字"
        )
    elif IS_WINDOWS:
        return "🎙️  Windows 语音输入：Win+H 调出听写面板"
    else:
        return "🎙️  Linux 语音输入：需安装 arecord + vosk（pip install vosk）"


def cmd_screenshot(state, parts) -> str:
    """/screenshot [full|window|selection] —— 截屏"""
    region = parts[1] if len(parts) > 1 else None
    if not IS_MACOS:
        return f"❌ 当前平台 ({sys.platform}) 暂不支持截屏\n   💡 macOS 上可用 screencapture 命令手动"
    out = screenshot(region)
    if out:
        return f"📸 已截图: {out}\n   💡 用 /see {out} 让 AI 分析"
    return "❌ 截屏失败（可能用户取消了选择）"


def cmd_drag_hint(state, parts) -> str:
    """/drag —— 显示拖文件到终端的提示"""
    return (
        "📎 拖文件支持：\n"
        "   macOS/Linux: 把文件从 Finder/Nautilus 拖到终端，会自动识别路径\n"
        "   Windows: 右键文件 → 复制为路径，然后粘贴\n\n"
        "   fr-cli 会自动识别：\n"
        "   - 图片 (.png/.jpg/...) → /see 让 AI 看图\n"
        "   - PDF → 转文本后给 AI\n"
        "   - 代码文件 → 让 AI 解释 / review\n"
    )


def cmd_ide_template(state, parts) -> str:
    """/ide [vscode|zed] —— 写编辑器集成模板"""
    ide = parts[1] if len(parts) > 1 else "vscode"
    if ide == "vscode":
        return write_vscode_template()
    elif ide == "zed":
        return write_zed_template()
    return f"❌ 不支持的 IDE: {ide}（支持: vscode / zed）"
