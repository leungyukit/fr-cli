"""
v3 Pipeline —— 流式处理管道

v2.x:每个流式场景自己实现 SSE / chunk 回调
v3:统一 Pipeline 接口 + Chunk / Event 协议 + 装饰器

示例:
    @pipeline("llm.stream")
    async def stream_llm(request, on_chunk, on_done):
        async for chunk in client.stream(request):
            on_chunk(chunk)
        on_done(final)

    # 调用
    pipeline_manager.run("llm.stream", request, on_chunk=..., on_done=...)
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class Chunk:
    """流式输出的一块数据"""
    data: Any
    index: int = 0
    is_final: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class PipelineRequest:
    """流式请求"""
    pipeline_name: str
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    on_chunk: Optional[Callable[[Chunk], None]] = None
    on_done: Optional[Callable[[Any], None]] = None
    on_error: Optional[Callable[[Exception], None]] = None
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


class Pipeline:
    """流式处理管道定义"""

    def __init__(self, name: str, func: Callable,
                 description: str = "",
                 timeout: float = 300.0):
        self.name = name
        self.func = func
        self.description = description
        self.timeout = timeout

    async def run(self, *args, **kwargs) -> Any:
        """运行管道"""
        if asyncio.iscoroutinefunction(self.func):
            return await asyncio.wait_for(self.func(*args, **kwargs), timeout=self.timeout)
        else:
            # 同步函数,在线程池跑
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self.func(*args, **kwargs)),
                timeout=self.timeout,
            )


class PipelineManager:
    """管道管理器"""

    def __init__(self):
        self._pipelines: Dict[str, Pipeline] = {}
        self._stats: Dict[str, int] = {}

    def register(self, name: str, func: Callable,
                 description: str = "",
                 timeout: float = 300.0,
                 override: bool = True) -> Pipeline:
        """注册一个管道"""
        if name in self._pipelines and not override:
            return self._pipelines[name]
        p = Pipeline(name, func, description=description, timeout=timeout)
        self._pipelines[name] = p
        return p

    def get(self, name: str) -> Optional[Pipeline]:
        return self._pipelines.get(name)

    def list_pipelines(self) -> List[str]:
        return list(self._pipelines.keys())

    def remove(self, name: str) -> bool:
        return self._pipelines.pop(name, None) is not None

    async def run(self, name: str, *args, **kwargs) -> Any:
        """运行管道"""
        p = self._pipelines.get(name)
        if p is None:
            raise ValueError(f"pipeline not found: {name}")
        self._stats[name] = self._stats.get(name, 0) + 1
        return await p.run(*args, **kwargs)

    def stats(self) -> Dict[str, int]:
        return dict(self._stats)


# 装饰器
def pipeline(name: str, description: str = "", timeout: float = 300.0):
    """装饰器:把函数注册为 pipeline

    用法:
        @pipeline("llm.stream", "LLM 流式输出")
        async def stream_llm(messages, on_chunk, on_done):
            async for chunk in client.stream(messages):
                on_chunk(Chunk(data=chunk, index=...))
            on_done(result)
    """
    def decorator(func: Callable) -> Callable:
        # 标记 + 注册到全局 manager
        func._pipeline_metadata = {
            "name": name,
            "description": description,
            "timeout": timeout,
        }
        try:
            from fr_cli.v3.core.pipeline import global_pipeline_manager
            global_pipeline_manager().register(name, func, description=description, timeout=timeout)
        except Exception:
            pass
        return func
    return decorator


# 全局
_global_pm: Optional[PipelineManager] = None


def global_pipeline_manager() -> PipelineManager:
    global _global_pm
    if _global_pm is None:
        _global_pm = PipelineManager()
    return _global_pm


def reset_global_pipeline_manager():
    global _global_pm
    _global_pm = None


# ---------------- 流式助手 ----------------

async def stream_to_callback(source: AsyncIterator, on_chunk: Callable,
                              on_done: Optional[Callable] = None,
                              chunk_factory: Callable = lambda x, i: Chunk(data=x, index=i),
                              max_chunks: Optional[int] = None):
    """把 AsyncIterator 流转发到 on_chunk 回调

    Args:
        source: 异步迭代器
        on_chunk: 每块的回调 fn(chunk: Chunk)
        on_done: 结束回调 fn(final_chunk)
        chunk_factory: 把 (item, index) 转 Chunk 的工厂
        max_chunks: 最多接收多少块(None = 无限)
    """
    final = None
    i = 0
    async for item in source:
        if max_chunks and i >= max_chunks:
            break
        chunk = chunk_factory(item, i)
        if i == max_chunks - 1 if max_chunks else False:
            chunk.is_final = True
        try:
            on_chunk(chunk)
        except Exception as e:
            log.error(f"on_chunk error: {e}")
        final = chunk
        i += 1
    if final:
        final.is_final = True
    if on_done:
        try:
            on_done(final)
        except Exception as e:
            log.error(f"on_done error: {e}")


async def collect_stream(source: AsyncIterator, max_chunks: Optional[int] = None) -> List[Any]:
    """把流收集为列表"""
    items = []
    i = 0
    async for item in source:
        if max_chunks and i >= max_chunks:
            break
        items.append(item)
        i += 1
    return items
