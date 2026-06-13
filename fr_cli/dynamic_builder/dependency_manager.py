"""
动态构建 —— 依赖管理

负责检查、提示并安装 Python 第三方依赖。
所有安装操作默认需要用户确认（四阶安全确认或简单 Y/n）。
"""
import importlib
import subprocess
import sys
from typing import List, Tuple

from fr_cli.core.result import Result
from fr_cli.ui.ui import CYAN, GREEN, RED, RESET, YELLOW


def is_installed(package: str) -> bool:
    """检查包是否已安装（支持包名和 import 名不同的情况）"""
    package = package.strip().lower()
    # 常见映射：pip 包名 -> import 名
    mapping = {
        "pillow": "PIL",
        "pymupdf": "fitz",
        "opencv-python": "cv2",
        "opencv-python-headless": "cv2",
        "scikit-learn": "sklearn",
        "beautifulsoup4": "bs4",
        "paddleocr": "paddleocr",
        "paddlepaddle": "paddle",
    }
    import_name = mapping.get(package, package.replace("-", "_"))
    try:
        importlib.import_module(import_name)
        return True
    except ImportError:
        return False


def check_dependencies(packages: List[str]) -> Tuple[List[str], List[str]]:
    """
    检查依赖列表。

    Returns:
        (installed, missing)
    """
    installed = []
    missing = []
    for pkg in packages:
        if is_installed(pkg):
            installed.append(pkg)
        else:
            missing.append(pkg)
    return installed, missing


def install_dependency(package: str, lang: str = "zh", confirm: bool = True) -> Result:
    """
    安装单个 pip 依赖，返回 Result。

    Args:
        package: pip 包名
        lang: 界面语言
        confirm: 是否需要用户确认
    """
    if is_installed(package):
        return Result.ok(f"{package} 已安装")

    msg = f"需要安装依赖: {package}" if lang == "zh" else f"Dependency required: {package}"
    print(f"{YELLOW}📦 {msg}{RESET}")

    if confirm:
        try:
            ans = input("确认安装? [Y/n]: " if lang == "zh" else "Install? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return Result.fail("用户取消安装")
        if ans and ans not in ("y", "yes"):
            return Result.fail("用户拒绝安装")

    try:
        print(f"{CYAN}🔄 正在安装 {package}...{RESET}")
        res = subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if res.returncode == 0:
            print(f"{GREEN}✅ {package} 安装成功{RESET}")
            return Result.ok(f"{package} 安装成功")
        else:
            err = res.stderr.strip()[-500:] if res.stderr else "未知错误"
            print(f"{RED}❌ {package} 安装失败: {err}{RESET}")
            return Result.fail(f"安装失败: {err}")
    except subprocess.TimeoutExpired:
        return Result.fail("安装超时（300秒）")
    except Exception as e:
        return Result.fail(f"安装异常: {e}")


def ensure_dependencies(packages: List[str], lang: str = "zh", confirm: bool = True) -> Result:
    """
    确保所有依赖已安装，缺失时尝试安装。

    Returns:
        Result，成功时 data 为 []，失败时 data 为失败的包列表
    """
    installed, missing = check_dependencies(packages)
    if not missing:
        return Result.ok([])

    failed = []
    for pkg in missing:
        result = install_dependency(pkg, lang=lang, confirm=confirm)
        if result.is_fail():
            failed.append(pkg)

    if failed:
        return Result.fail(f"依赖安装失败: {', '.join(failed)}")
    return Result.ok([])
