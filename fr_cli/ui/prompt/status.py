"""
fr-cli TUI 状态条 —— 底部实时显示模型/路径/Token/工具状态

生成 prompt_toolkit FormattedText 列表，由 FanRenPrompt / FallbackPrompt 共享。

v2.8.7(UX) 重排
--------------
此前所有信息（模型 / 目录 / 时间 / 耗时 / token / 模式 / 队列 / 转向 /
工具 / spinner）用 ``│`` 平铺成一行，窄终端直接折行 —— 折行后的状态栏会把
输入框顶变形，看着像"终端炸了"。

现在改成**左右分栏 + 优先级裁剪**：
* 左区 = 身份与位置（模型、工作目录）
* 右区 = 状态与计量（忙碌/工具、队列、转向、上下文占用、token、耗时、时间、模式）
* 宽度不够时按优先级从低到高丢弃右区项（模型与忙碌状态永远保留）

新增
----
* **上下文占用 %**：接近压缩阈值时变色预警（黄 80% / 红 100%）。
* **工具执行参数**：此前 ``tool_name`` 字段从未被赋值，工具执行分支是死代码；
  现在由 ``command/executor_dispatch.py`` 上报真实工具名与参数摘要。
* **工具来源与失败原因**：状态栏显示调用来源（``[master]`` / ``[local]`` /
  ``[workflow]`` / ``[plan]``），工具失败时以红色显示失败原因 ——
  工具结果本身不回显给用户，状态栏是失败现场唯一可见的地方。
"""
from datetime import datetime
from typing import List, Optional, Tuple

#: 状态项：(优先级, 样式, 文本, 侧别)
#: 优先级数字越小越重要 —— 宽度不足时从大到小丢弃。
_Item = Tuple[int, str, str, str]

#: 侧别
_LEFT = "L"
_RIGHT = "R"

#: 分隔符
_SEP = " │ "


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
        self.tool_args = ""        # 工具参数摘要（当前工具调用的关键参数）
        self.tool_source = ""      # 工具调用来源（master / @local / workflow / plan ...）
        self.tool_error = ""       # 工具失败原因（成功时为空；失败后保留到本轮结束）
        # v2.8.7(UX)：流式期间可交互 —— 队列深度 + 待生效转向指令
        self.queue_depth = 0       # 待处理队列条数（对话队列）
        self.steer_pending = 0     # 已提交但尚未注入本轮的转向指令条数
        # v2.8.7(UX)：上下文占用（接近压缩阈值时预警）
        self.context_tokens = 0    # 当前上下文估算 token 数
        self.context_limit = 0     # 上下文压缩阈值（分母）
        # 上次 AI 回答统计
        self.last_response_time = 0.0
        self.last_input_tokens = 0
        self.last_output_tokens = 0
        self.last_total_tokens = 0

    # ------------------------------------------------------------------
    # 采集
    # ------------------------------------------------------------------

    def _model_item(self) -> _Item:
        """模型 / 提供商 —— 永远保留（优先级最高）"""
        if self.provider == "未配置" or self.model == "未配置":
            return (0, "class:status-red", "未配置", _LEFT)
        if self.is_mock:
            return (0, "class:status-yellow", f"mock/{self.model}", _LEFT)
        return (0, "class:status-cyan", f"{self.provider}/{self.model}", _LEFT)

    def _busy_item(self) -> Optional[_Item]:
        """忙碌状态 / 当前工具 —— 永远保留"""
        if self.tool_name:
            import time
            elapsed = time.time() - self.tool_started if self.tool_started else 0
            # 来源 agent 前缀 —— 让人知道这次调用是谁发起的
            head = f"[{self.tool_source}] {self.tool_name}" if self.tool_source else self.tool_name
            text = f"{head} ({elapsed:.1f}s)"
            if self.tool_args:
                text += f" {self.tool_args}"
            if self.tool_error:
                # 失败原因：状态栏是失败现场唯一可见的地方（工具结果本身不回显给用户）
                text += f" ✗ {self.tool_error}"
                return (0, "class:status-red", text, _RIGHT)
            return (0, "class:status-yellow", text, _RIGHT)
        if self.is_busy:
            frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            spinner = frames[self.spinner_frame % len(frames)]
            # 等待状态用**黄**（红色留给失败）—— v2.8.7 第四阶段语义色分层
            return (0, "class:status-yellow", f"{spinner} 思考中", _RIGHT)
        return (0, "class:status-green", "就绪", _RIGHT)

    def _context_item(self) -> Optional[_Item]:
        """上下文占用 —— 接近压缩阈值时预警"""
        if not self.context_limit or self.context_tokens <= 0:
            return None
        pct = self.context_tokens * 100.0 / self.context_limit
        if pct >= 100:
            style = "class:status-red"
        elif pct >= 80:
            style = "class:status-yellow"
        else:
            style = "class:status-gray"
        return (3, style, f"上下文 {pct:.0f}%", _RIGHT)

    def _collect(self) -> List[_Item]:
        """收集全部状态项（按展示顺序）"""
        items: List[_Item] = [self._model_item()]

        # 左区：工作目录（低优先级，窄屏先丢）
        if self.directory:
            short_dir = self.directory
            if len(short_dir) > 20:
                short_dir = "..." + short_dir[-17:]
            items.append((8, "class:status-green", short_dir, _LEFT))

        busy = self._busy_item()
        if busy:
            items.append(busy)

        # 队列 / 转向：交互语义强，优先级高
        if self.queue_depth:
            items.append((1, "class:status-yellow", f"队列 {self.queue_depth}", _RIGHT))
        if self.steer_pending:
            items.append((2, "class:status-magenta", f"↯ 转向 {self.steer_pending}", _RIGHT))

        ctx = self._context_item()
        if ctx:
            items.append(ctx)

        # Token 统计（口径统一见 core/usage.py::format_token_usage）
        if self.last_total_tokens > 0:
            from fr_cli.core.usage import format_token_usage
            items.append((4, "class:status-yellow",
                          format_token_usage(self.last_input_tokens,
                                             self.last_output_tokens,
                                             self.last_total_tokens),
                          _RIGHT))

        # 上次耗时
        if self.last_response_time > 0:
            items.append((5, "class:status-yellow", f"{self.last_response_time:.1f}s", _RIGHT))

        # 当前时间
        items.append((6, "class:status-gray", datetime.now().strftime("%H:%M:%S"), _RIGHT))

        # 思维模式
        if self.mode and self.mode != "direct":
            items.append((7, "class:status-magenta", self.mode, _RIGHT))

        return items

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------

    @staticmethod
    def _measure(items: List[_Item]) -> int:
        """估算一组状态项占用的显示宽度（含分隔符）"""
        if not items:
            return 0
        total = 0
        for item in items:
            total += len(item[2])
        total += len(_SEP) * (len(items) - 1)
        return total

    def render(self, width: int = 0) -> List[Tuple[str, str]]:
        """生成状态条文本（prompt_toolkit FormattedText 列表）

        Args:
            width: 可用终端宽度；<= 0 表示不限制（全部显示）。
                给定时按**全局优先级**裁剪（低优先级的先丢 —— 目录、
                时间、模式），模型与忙碌/工具状态永远保留。
        """
        items = self._collect()

        if width and width > 24:
            # 全局按优先级丢弃：优先级数字越小越重要
            order = sorted(range(len(items)), key=lambda i: items[i][0])
            keep = set()
            used = 0
            for idx in order:
                need = self._measure([items[idx]]) + (len(_SEP) if keep else 0)
                if used + need > width - 1 and items[idx][0] > 0:
                    # 放不下就跳过这一项（继续试后面更短的项）
                    continue
                keep.add(idx)
                used += need
            items = [it for i, it in enumerate(items) if i in keep]

        left = [it for it in items if it[3] == _LEFT]
        right = [it for it in items if it[3] == _RIGHT]

        result: List[Tuple[str, str]] = []

        def _emit(group: List[_Item]):
            for i, (_, style, text, _) in enumerate(group):
                if i > 0:
                    result.append(("class:status-sep", _SEP))
                result.append((style, text))

        _emit(left)

        if left and right:
            lw = self._measure(left)
            rw = self._measure(right)
            pad = max(1, (width - lw - rw - 2 * len(_SEP)) if width else 1)
            result.append(("class:status-sep", _SEP))
            result.append(("class:status-sep", " " * pad))
            result.append(("class:status-sep", _SEP))
        _emit(right)

        return result
