"""
命令行 spinner —— 进度反馈工具,纯标准库实现

设计目标:
- 无第三方依赖(不引 rich/halo)
- 自动适配 TTY / 非 TTY 环境(测试 / CI / 重定向)
- 简单 context manager 接口
- 支持运行中更新消息(extract 场景下"第 N/M 批" 进度)

用法:
    with Spinner("加载数据中..."):
        do_something()
    # 输出: ⠋ 加载数据中...

    sp = Spinner("提炼中...")
    with sp:
        for i, batch in enumerate(batches):
            sp.update(f"第 {i+1}/{len(batches)} 批")
            process(batch)

非 TTY 环境(测试 / CI / 重定向)自动降级为 print:
    ... 加载数据中...
"""
import sys
import threading
import time


class Spinner:
    """单行旋转的 spinner,显示一行动态字符 + 消息"""

    # Braille 字符,Unicode 标准动画点
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    # 兼容 fallback:ASCII 字符(终端不支持 Unicode 时)
    ASCII_FRAMES = "|/-\\"

    def __init__(self, message: str = "处理中...", enabled: bool = None):
        """初始化 spinner

        Args:
            message: 起始显示消息
            enabled: None 自动检测 TTY,True/False 强制启用/禁用
        """
        self.message = message
        if enabled is None:
            # 自动检测:有 stdout TTY 且 stderr 不是(避免被重定向污染)
            enabled = sys.stdout.isatty()
        self.enabled = enabled
        self._thread = None
        self._running = False
        self._lock = threading.Lock()
        self._last_printed = ""  # 非 TTY 模式下,避免重复打印同一消息
        # 优先用 Unicode 字符,fallback 到 ASCII
        self._frames = self.FRAMES if _can_encode_unicode() else self.ASCII_FRAMES

    def update(self, new_message: str):
        """线程安全地更新显示消息(运行中可调)"""
        with self._lock:
            self.message = new_message
            should_print = self._last_printed != new_message
            self._last_printed = new_message
        # 非 TTY 模式:每次 update 换行打印,让用户看到进度
        if should_print and not self.enabled:
            print(f"... {new_message}", flush=True)

    def __enter__(self):
        if not self.enabled:
            # 非 TTY 模式:只打印一行,不做动画
            print(f"... {self.message}", flush=True)
            with self._lock:
                self._last_printed = self.message
            return self
        self._running = True
        self._thread = threading.Thread(
            target=self._spin, daemon=True, name="fr-cli-spinner"
        )
        self._thread.start()
        return self

    def __exit__(self, *args):
        if not self.enabled:
            return
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
        # 清除 spinner 行(用空格覆盖)
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()

    def _spin(self):
        i = 0
        while self._running:
            with self._lock:
                msg = self.message
            frame = self._frames[i % len(self._frames)]
            line = f"\r{frame} {msg}"
            # 截断到终端宽度,避免 wrap 影响
            try:
                width = max(1, shutil_get_terminal_width())
            except Exception:
                width = 80
            if len(line) > width:
                line = line[:width - 1] + "…"
            sys.stdout.write(line)
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1


def _can_encode_unicode() -> bool:
    """检查 stdout 编码是否能输出 Braille 字符"""
    enc = sys.stdout.encoding or "utf-8"
    try:
        "⠋".encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def _shutil_get_terminal_width():
    """安全获取终端宽度"""
    try:
        import shutil
        return shutil.get_terminal_size((80, 20)).columns
    except Exception:
        return 80


# 避免每次调用 import shutil(微优化)
shutil_get_terminal_width = _shutil_get_terminal_width


__all__ = ["Spinner"]
