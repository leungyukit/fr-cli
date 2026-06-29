"""Mock LLM 客户端 —— 零配置试用 / API 不可用时的降级方案"""
import time as _time
from typing import Iterator

from fr_cli.core.llm.base import BaseLLMClient


class MockLLMClient(BaseLLMClient):
    """Mock LLM:不调任何远程 API,本地回声式响应

    适用场景:
    1. 用户首次启动还没配 API Key(init_config 检测到无 key 时切换)
    2. 远程 API 调用失败(网络/限流/key 错)的临时降级
    3. 演示 / 测试场景
    """

    def __init__(self, api_key: str = "mock", **kwargs):
        super().__init__(api_key, **kwargs)
        self.model = kwargs.get("model", "mock-echo")
        self.is_mock = True

    def stream_chat(self, model: str, messages: list,
                    max_tokens: int = 4096, timeout: int = None) -> Iterator[dict]:
        """回声响应:把最后一条 user message 包装一下吐出来"""
        # 提取最后一条 user 消息
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break

        # 简单响应模板
        if not last_user:
            response = ("【Mock 模式】我是本地 mock 客户端,没收到你的输入。"
                        "配置 API Key 后可启用真实 LLM(/key <your-key>)。")
        elif last_user.startswith("/"):
            response = (f"【Mock 模式】你输入了命令 {last_user[:60]}。"
                        "当前在 mock 模式,命令执行仍可工作(不依赖 LLM),"
                        "只是 AI 回答部分是模拟的。")
        else:
            short = last_user[:200]
            response = (
                f"【Mock 模式 🧪】当前未配置 API Key 或 LLM 不可用。\n"
                f"你刚才说的是:{short}\n\n"
                f"**配置真实 LLM 的方式:**\n"
                f"- `/key sk-xxx` 设置当前提供商的 key\n"
                f"- `/providers use <厂商>` 切换到其他提供商\n"
                f"- `/providers setup` 交互式配置\n\n"
                f"**Mock 模式仍能用的功能:**\n"
                f"- `/help` / `/cat` / `/ls` / `/web` 等命令\n"
                f"- `/shell` 执行系统命令\n"
                f"- `@local` / `@RAG` 等不依赖 LLM 的 Agent\n"
            )

        # 模拟流式输出:按词切分
        for word in response.split(" "):
            yield {"content": word + " ", "usage": None}
            _time.sleep(0.02)  # 让用户看到流式效果

        # 最后给个 usage
        yield {
            "content": "",
            "usage": {
                "prompt_tokens": sum(len(m.get("content", "")) for m in messages) // 4,
                "completion_tokens": len(response) // 4,
                "total_tokens": (sum(len(m.get("content", "")) for m in messages) + len(response)) // 4,
            },
        }
