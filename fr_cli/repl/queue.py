"""
对话队列管理器
- 让用户在 AI 回答期间继续输入新问题
- 后台线程处理队列，主线程持续监听输入
- 借鉴 OpenCode/Kimi Code 的并发交互模式
"""
import threading
import time
from fr_cli.ui.ui import RED, RESET, YELLOW, DIM, CYAN


class ChatQueueManager:
    """管理用户输入队列，当 AI 正在回答时，新问题自动排队。"""

    def __init__(self, state, prompt):
        self.state = state
        self.prompt = prompt
        self.queue = []
        self.is_processing = False
        self.lock = threading.Lock()
        self._patch_stdout_available = False
        try:
            from prompt_toolkit.patch_stdout import patch_stdout
            self._patch_stdout = patch_stdout
            self._patch_stdout_available = True
        except ImportError:
            pass

    def add(self, user_input: str) -> int:
        """添加问题到队列，返回队列位置（1-based）"""
        with self.lock:
            self.queue.append(user_input)
            pos = len(self.queue)
        return pos

    def peek(self) -> list:
        """查看队列内容（不修改）"""
        with self.lock:
            return list(self.queue)

    def clear(self):
        """清空队列"""
        with self.lock:
            self.queue.clear()

    def status_text(self) -> str:
        """返回队列状态文本"""
        with self.lock:
            if self.is_processing:
                if self.queue:
                    return f"处理中，队列中还有 {len(self.queue)} 个问题"
                return "处理中"
            if self.queue:
                return f"队列中有 {len(self.queue)} 个问题待处理"
            return "空闲"

    def _try_process_next(self):
        """尝试处理队列中的下一个问题（后台线程）"""
        with self.lock:
            if self.is_processing or not self.queue:
                return
            next_input = self.queue.pop(0)
            self.is_processing = True

        def worker():
            # 延迟导入避免循环引用（chat.py 可能 import queue）
            from fr_cli.core.chat import handle_ai_chat
            try:
                self.prompt.set_busy(True)
                if self._patch_stdout_available:
                    with self._patch_stdout():
                        stats = handle_ai_chat(self.state, next_input)
                else:
                    stats = handle_ai_chat(self.state, next_input)
                if stats:
                    self.prompt.update_last_stats(**stats)
            except Exception as e:
                import traceback
                print(f"{RED}队列处理出错: {e}{RESET}")
                traceback.print_exc()
            finally:
                self.prompt.set_busy(False)
                with self.lock:
                    self.is_processing = False
                    has_more = bool(self.queue)
                if has_more:
                    self._try_process_next()

        threading.Thread(target=worker, daemon=True).start()

    def process(self, user_input: str):
        """添加问题并尝试启动处理"""
        pos = self.add(user_input)
        if pos > 1:
            print(f"{DIM}问题已加入队列 (位置: {pos}){RESET}")
        self._try_process_next()

    def wait_for_complete(self, timeout: float = None) -> bool:
        """等待当前处理完成（不等待队列中的未处理问题）"""
        start = time.time()
        while self.is_processing:
            time.sleep(0.1)
            if timeout and (time.time() - start) > timeout:
                return False
        return True


def handle_queue_command(state, parts) -> bool:
    """/queue, /queue clear"""
    queue_mgr = getattr(state, '_queue_mgr', None)
    if not queue_mgr:
        print(f"{YELLOW}队列管理器未初始化{RESET}")
        return False

    if len(parts) > 1 and parts[1] == "clear":
        queue_mgr.clear()
        print(f"{CYAN}队列已清空{RESET}")
        return False

    status = queue_mgr.status_text()
    pending = queue_mgr.peek()
    print(f"{CYAN}队列状态: {status}{RESET}")
    if pending:
        print(f"{DIM}待处理问题 ({len(pending)} 个):{RESET}")
        for i, q in enumerate(pending, 1):
            preview = q[:60] + "..." if len(q) > 60 else q
            print(f"  {i}. {preview}")
    return False