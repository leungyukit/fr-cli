"""
spider 模块依赖管理 —— 延迟加载 requests / selenium / undetected-chromedriver / bs4

按需 import，缺失时返回 None，让上层逻辑走"无依赖"分支或给出安装提示。
"""
import threading

_requests = None
_selenium = None
_bs4 = None
_requests_sessions: dict = {}
_sessions_lock = threading.Lock()


# ---------- 用户代理池 ----------
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# 常见真实窗口分辨率（避免只用 1920x1080）
_WINDOW_SIZES = [
    (1920, 1080), (1366, 768), (1440, 900), (1536, 864),
    (1280, 720), (1600, 900), (1680, 1050), (2560, 1440),
]


def _get_requests():
    global _requests
    if _requests is None:
        try:
            import requests as r
            _requests = r
        except ImportError:
            pass
    return _requests


def _get_selenium():
    global _selenium
    if _selenium is None:
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.action_chains import ActionChains
            _selenium = {"webdriver": webdriver, "By": By, "ActionChains": ActionChains}
        except ImportError:
            pass
    return _selenium


def _get_undetected_chromedriver():
    """尝试导入 undetected-chromedriver（更强的反检测能力）"""
    try:
        import undetected_chromedriver as uc
        return uc
    except ImportError:
        return None


def _get_bs4():
    global _bs4
    if _bs4 is None:
        try:
            from bs4 import BeautifulSoup
            _bs4 = BeautifulSoup
        except ImportError:
            pass
    return _bs4


def _get_requests_session(domain: str):
    """获取带 Cookie 持久化的 Session，每个域名独立"""
    requests = _get_requests()
    if not requests:
        return None
    with _sessions_lock:
        if domain not in _requests_sessions:
            _requests_sessions[domain] = requests.Session()
        return _requests_sessions[domain]
