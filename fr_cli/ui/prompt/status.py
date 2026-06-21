"""
fr_cli TUI 状态条 —— 底部实时显示模型/路径/Token/工具状态

生成 prompt_toolkit FormattedText 列表，由 FanRenPrompt / FallbackPrompt 共享。
"""
from datetime import datetime
from typing import List, Tuple


class StatusState:
    """状态条显示用的实时状态"""

    def __init__(self):
        self.model = ""
        self.provider = ""
        self.directory = ""
        self.session = ""
        self.tokens_used = 0
        self.limit = 0
        self.mode = "direct"
        self.is_busy = False       # AI 正在生成时为 True
        self.is_mock = False       # Mock 模式
        self.spinner_frame = 0
        self.tool_name = ""        # 当前正在调用的工具
        self.tool_started = 0.0    # 工具调用开始时间戳
        # 上次 AI 回答统计
        self.last_response_time = 0.0
        self.last_input_tokens = 0
        self.last_output_tokens = 0
        self.last_total_tokens = 0

    def render(self) -> List[Tuple[str, str]]:
        """生成状态条文本（prompt_toolkit FormattedText 列表）"""
        parts = []
        # 模型 / 提供商
        if self.provider == "未配置" or self.model == "未配置":
            parts.append(("class:status-red", "未配置"))
        elif self.is_mock:
            parts.append(("class:status-yellow", f"mock/{self.model}"))
        else:
            parts.append(("class:status-cyan", f"{self.provider}/{self.model}"))
        # 工作目录
        if self.directory:
            short_dir = self.directory
            if len(short_dir) > 20:
                short_dir = "..." + short_dir[-17:]
            parts.append(("class:status-green", f"{short_dir}"))
        # 当前时间
        parts.append(("class:status-gray", f"{datetime.now().strftime('%H:%M:%S')}"))
        # 上次耗时
        if self.last_response_time > 0:
            parts.append(("class:status-yellow", f"{self.last_response_time:.1f}s"))
        # Token 统计
        if self.last_total_tokens > 0:
            parts.append(("class:status-yellow",
                          f"{self.last_input_tokens}/{self.last_output_tokens}/{self.last_total_tokens}"))
        elif self.tokens_used or self.limit:
            parts.append(("class:status-yellow", f"{self.tokens_used}/{self.limit}"))
        # 思维模式
        if self.mode and self.mode != "direct":
            parts.append(("class:status-magenta", f"{self.mode}"))
        # 工具/忙碌/就绪状态
        if self.tool_name:
            import time
            elapsed = time.time() - self.tool_started if self.tool_started else 0
            parts.append(("class:status-yellow", f"{self.tool_name} ({elapsed:.1f}s)"))
        elif self.is_busy:
            frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            spinner = frames[self.spinner_frame % len(frames)]
            parts.append(("class:status-red", f"{spinner} 思考中"))
        else:
            parts.append(("class:status-green", "就绪"))

        # 用 " │ " 连接，生成 FormattedText 列表
        result = []
        for i, (style, text) in enumerate(parts):
            if i > 0:
                result.append(("class:status-sep", " │ "))
            result.append((style, text))
        return result
