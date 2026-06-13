"""
启动封面 —— 在终端以图片形式输出 splash.jpeg

设计目标
========
- **跨平台统一**:在所有支持 24 位真彩色的终端都能看到图片,不需要任何
  图像协议扩展(Kitty / iTerm2 / Sixel)。
- **主路径:像素艺术 + ANSI 24位真彩色背景**:把图片缩到 30~50 字符宽,
  每个像素用 `██` (2 字符宽 × 1 行高) + 背景色绘制。复古像素游戏风格,
  主体清晰可辨,所有终端 100% 支持。
- **可选增强:图像协议**(Kitty / iTerm2 / Sixel):在支持的终端上输出**完整原图**
  代替像素艺术版,效果更好。

协议优先级
==========
1. **Kitty 图形协议** —— Kitty / WezTerm
2. **iTerm2 inline image** —— macOS iTerm2
3. **像素艺术 + ANSI 24-bit**(默认,所有终端)

可换图
======
直接替换 `fr_cli/assets/splash.jpeg`,`pip install -e .` 即生效。
"""
from __future__ import annotations

import base64
import io
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from PIL import Image
except ImportError as e:  # pragma: no cover
    raise RuntimeError(
        "fr-cli 启动封面依赖 Pillow,请先 `pip install pillow`"
    ) from e


# ===================== 资源读取 =====================

def _load_splash_bytes() -> bytes:
    """读取封面图片字节。优先 importlib.resources,回退 __file__ 相对路径。"""
    try:
        from importlib.resources import files
        resource = files("fr_cli.assets").joinpath("splash.jpeg")
        if resource.is_file():
            return resource.read_bytes()
    except (ImportError, ModuleNotFoundError, FileNotFoundError, AttributeError):
        pass

    fallback = Path(__file__).parent.parent / "assets" / "splash.jpeg"
    if fallback.is_file():
        return fallback.read_bytes()

    raise FileNotFoundError(
        "未找到启动封面 fr_cli/assets/splash.jpeg,"
        "请确认图片文件存在或重新安装 fr-cli"
    )


# ===================== 协议探测 =====================

@dataclass(frozen=True)
class TerminalCapability:
    """终端能力"""
    protocol: Optional[str]  # "kitty" | "iterm2" | "sixel" | None
    width: int
    height: int


def detect_terminal() -> TerminalCapability:
    """探测当前终端支持的图像协议与窗口尺寸。

    返回 None 时表示不支持完整图片协议,调用方应使用像素艺术 fallback。
    """
    try:
        ts = shutil.get_terminal_size()
        w, h = ts.columns, ts.lines
    except Exception:
        w, h = 100, 30

    term = os.environ.get("TERM", "")
    term_program = os.environ.get("TERM_PROGRAM", "")

    # 1. Kitty 协议(Kitty、WezTerm)
    if term_program == "WezTerm":
        return TerminalCapability("kitty", w, h)
    if "kitty" in term.lower() and "xterm" not in term.lower():
        return TerminalCapability("kitty", w, h)

    # 2. iTerm2 协议(macOS iTerm2)
    if term_program == "iTerm.app":
        return TerminalCapability("iterm2", w, h)

    # 3. 其他一律走像素艺术(ANSI 24-bit)
    #    过去曾支持 Sixel,但 Sixel 输出在主流终端都不稳定,
    #    砍掉以保证显示质量。
    return TerminalCapability(None, w, h)


# ===================== 图片预处理 =====================

def _load_image() -> Image.Image:
    """读取并转 RGB。"""
    return Image.open(io.BytesIO(_load_splash_bytes())).convert("RGB")


def _strip_background(img: Image.Image, threshold: int = 30) -> Image.Image:
    """把暗背景像素设为(0,0,0)黑色,稍后在 _emit_pixels 中按亮度阈值跳过。

    threshold 越大,越多像素被当背景(适合纯色暗背景的图)。
    原图大部分背景是深色,主体是浅色 → 用亮度 < threshold 判定。
    """
    w, h = img.size
    pixels = img.load()
    out = img.copy()
    out_px = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y]
            # 用 ITU-R BT.601 亮度公式
            brightness = int(0.299 * r + 0.587 * g + 0.114 * b)
            if brightness < threshold:
                # 标记为纯黑(之后 _emit_pixels 会跳过亮度 < skip_threshold 的像素)
                out_px[x, y] = (0, 0, 0)
    return out


def _to_grayscale(img: Image.Image) -> Image.Image:
    """转 8 级灰度(降色阶让效果更分明)。"""
    gray = img.convert("L")  # 灰度
    # 量化到 8 级(0/32/64/96/128/160/192/224)
    return gray.point(lambda v: (v // 32) * 32)


def _resize_for_pixels(img: Image.Image, max_cols: int) -> Image.Image:
    """缩放到适合"半块字符"渲染的尺寸。

    终端字符高宽比约 1:2(高是宽的 2 倍)。
    每个字符(▀)能装 2 个像素(上前景 + 下背景),
    所以 "宽 = max_cols 像素",高度按比例 / 2 缩放(等比显示)。
    """
    w, h = img.size
    if w > max_cols:
        ratio = max_cols / w
        new_w = max_cols
        new_h = int(h * ratio / 2)  # /2 因为每个字符装 2 行像素
        return img.resize((new_w, new_h), Image.LANCZOS)
    return img


def _resize_for_protocol(img: Image.Image, max_cols: int) -> Image.Image:
    """缩放到适合完整图片协议渲染的尺寸。"""
    w, h = img.size
    if w > max_cols:
        ratio = max_cols / w
        return img.resize((max_cols, int(h * ratio)), Image.LANCZOS)
    return img


# ===================== 半块字符 + ANSI 24-bit(主路径) =====================

def _emit_pixels(img: Image.Image, skip_brightness: int = 5) -> None:
    """用 ANSI 24-bit 灰度颜色 + `▀` 半块字符绘制像素艺术(无背景)。

    原理:
        - `▀` 占 1 字符宽 × 1 行高,前景色填上半,背景色填下半
        - 1 个字符 = 2 个像素(等比显示)
        - **背景像素(亮度 < skip_brightness)直接画空格,不留黑色块**
        - 输出统一灰度(R=G=B),看起来像黑白图

    适用于所有支持 24-bit 颜色和 Unicode 的现代终端。
    """
    w, h = img.size
    pixels = img.load()

    out = sys.stdout
    out.write("\x1b[0m")

    for y in range(0, h, 2):
        for x in range(w):
            # 上半像素
            v1 = pixels[x, y]
            if isinstance(v1, int):  # 灰度图(L mode)返回 int
                gray1 = v1
            else:
                r, g, b = v1
                gray1 = int(0.299 * r + 0.587 * g + 0.114 * b)

            # 下半像素
            if y + 1 < h:
                v2 = pixels[x, y + 1]
                if isinstance(v2, int):
                    gray2 = v2
                else:
                    r, g, b = v2
                    gray2 = int(0.299 * r + 0.587 * g + 0.114 * b)
            else:
                gray2 = -1  # 标记为"无下半像素"= 背景

            # 跳过纯背景(全黑)
            top_bg = gray1 < skip_brightness
            bot_bg = gray2 < 0 or gray2 < skip_brightness

            if top_bg and bot_bg:
                # 上下都是背景 → 输出空格,什么也不画
                out.write(" ")
            elif top_bg and not bot_bg:
                # 上背景,下主体 → 用 ▀ 配背景 = 主体色填下半
                out.write(f"\x1b[38;2;{gray2};{gray2};{gray2}m\u2580")
            elif not top_bg and bot_bg:
                # 上主体,下背景 → 用 ▀ 配前景 = 主体色填上半
                out.write(f"\x1b[38;2;{gray1};{gray1};{gray1}m\u2580")
            else:
                # 上下都是主体 → 完整 ▀
                out.write(
                    f"\x1b[38;2;{gray1};{gray1};{gray1}m"
                    f"\x1b[48;2;{gray2};{gray2};{gray2}m"
                    f"\u2580"
                )
        out.write("\x1b[0m\n")  # 行末:重置 + 换行

    out.flush()


# ===================== Kitty 协议 =====================

def _emit_kitty(img: Image.Image, cols: int) -> None:
    """Kitty 图形协议:APC 转义序列,支持分块传输大图。"""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    CHUNK = 4096
    out = sys.stdout
    out.write(f"\x1b_Gf=100,a=T,c={cols},q=2,m=0;")
    out.write(b64[:CHUNK])
    out.write("\x1b\\")
    remaining = b64[CHUNK:]
    while remaining:
        chunk = remaining[:CHUNK]
        remaining = remaining[CHUNK:]
        more = 0 if remaining else 1
        out.write(f"\x1b_Gm={more};{chunk}\x1b\\")
    out.flush()


# ===================== iTerm2 协议 =====================

def _emit_iterm2(img: Image.Image, cols: int) -> None:
    """iTerm2 inline image:OSC 1337。"""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    sys.stdout.write(
        f"\x1b]1337;File=inline=1;preserveAspectRatio=1;"
        f"width={cols};size={len(b64)}:{b64}\x07"
    )
    sys.stdout.flush()


# ===================== Sixel 协议(已移除) =====================
# Sixel 协议在不同终端(mlterm / xterm / Windows Terminal)上的颜色
# 调色板行为差异很大,纯 Python 实现难以保证输出质量。
# 当前只支持 Kitty + iTerm2 两个稳定的图像协议;
# 其他终端走下方的"像素艺术 + ANSI 24-bit"主路径,
# 100% 终端都支持,效果也清晰可辨。


# ===================== 对外主接口 =====================

# 默认启动封面宽度(字符数,对应半块字符的"宽像素数")
DEFAULT_SPLASH_COLS = 50


def print_splash(
    max_cols: Optional[int] = None,
    force_protocol: Optional[str] = None,
    bg_threshold: int = 30,
) -> str:
    """在终端打印启动封面(默认黑白、无背景、50 字符宽)。

    Args:
        max_cols: 图片宽度(字符数),默认 50。
        force_protocol: 强制协议 ("kitty" / "iterm2" / "pixels")。
        bg_threshold: 亮度低于该值的像素视为背景(留空不画)。

    Returns:
        实际使用的渲染方式: "kitty" | "iterm2" | "pixels"
    """
    cap = detect_terminal()
    proto = force_protocol or cap.protocol
    cols = max_cols or min(cap.width, DEFAULT_SPLASH_COLS)

    img_full = _load_image()

    if proto == "kitty":
        img = _resize_for_protocol(img_full, cols)
        _emit_kitty(img, cols)
        return "kitty"

    if proto == "iterm2":
        img = _resize_for_protocol(img_full, cols)
        _emit_iterm2(img, cols)
        return "iterm2"

    # 主路径:黑白半块字符(默认)
    # 1) 先去背景(把暗像素染成纯黑,稍后 _emit_pixels 跳过)
    img_no_bg = _strip_background(img_full, threshold=bg_threshold)
    # 2) 转灰度 + 8 级量化
    img_gray = _to_grayscale(img_no_bg)
    # 3) 缩放到目标列宽
    img = _resize_for_pixels(img_gray, cols)
    # 4) 输出半块字符
    _emit_pixels(img)
    return "pixels"


# Iterm2 inline image 协议在某些情况下需要明确提示
HINT_FOR_PIXELS = (
    "如看不到图片,说明当前终端不完全支持 24-bit 颜色。"
    "推荐使用 iTerm2(macOS)或 Windows Terminal(Windows)。"
)


def get_splash_path() -> Path:
    """返回 splash 图片的绝对路径(用于 /splash 调试命令)。"""
    try:
        from importlib.resources import files
        resource = files("fr_cli.assets").joinpath("splash.jpeg")
        if resource.is_file():
            return Path(str(resource))
    except Exception:
        pass
    return Path(__file__).parent.parent / "assets" / "splash.jpeg"
