"""
图片模型和并行任务执行模块
==========================

功能：
1. 图片生成模型配置和使用
2. 图片自动下载到工作目录
3. 终端图片显示（ASCII/Unicode）
4. 并行任务执行（多线程/异步）
5. 多 Agent 并发执行
"""

import os
import re
import time
import base64
import shutil
import tempfile
import threading
import asyncio
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, Future
from enum import Enum
from pathlib import Path


# ============ 图片模型配置 ============

@dataclass
class ImageProvider:
    """图片生成提供商配置"""
    name: str
    provider_id: str  # 对应 LLM provider
    model: str
    api_key: str
    base_url: Optional[str] = None
    size: str = "1024x1024"
    quality: str = "standard"
    style: str = "vivid"  # vivid / natural
    enabled: bool = True


class ImageModelConfig:
    """
    图片模型配置管理器
    支持配置多个图片生成提供商
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._providers = {}
            cls._instance._default_provider = None
            cls._instance._config_file = Path.home() / ".fr_cli_image_config.json"
            cls._instance._load_config()
        return cls._instance

    def __init__(self):
        self._register_builtin_providers()

    def _register_builtin_providers(self):
        """注册内置图片提供商"""

        # 智谱 CogView
        self.register_provider(ImageProvider(
            name="智谱 CogView-4",
            provider_id="zhipu",
            model="cogview-4",
            api_key="",
            size="1024x1024"
        ))

        # MiniMax 图片
        self.register_provider(ImageProvider(
            name="MiniMax 图片",
            provider_id="minimax",
            model="image-01",
            api_key="",
            base_url="https://api.minimax.chat/v1",
            size="1024x1024"
        ))

        # 通义万相
        self.register_provider(ImageProvider(
            name="通义万相",
            provider_id="qwen",
            model="wanx2.1-t2i-turbo",
            api_key="",
            base_url="https://dashscope.aliyuncs.com/api/v2",
            size="1024x1024"
        ))

        # StepFun 图片
        self.register_provider(ImageProvider(
            name="StepFun 图片",
            provider_id="stepfun",
            model="step-1-image",
            api_key="",
            base_url="https://api.stepfun.com/v1",
            size="1024x1024"
        ))

    def register_provider(self, provider: ImageProvider):
        """注册图片提供商"""
        self._providers[provider.name] = provider
        if self._default_provider is None:
            self._default_provider = provider.name

    def get_provider(self, name: str = None) -> Optional[ImageProvider]:
        """获取图片提供商"""
        if name is None:
            name = self._default_provider
        return self._providers.get(name)

    def list_providers(self) -> List[Dict]:
        """列出所有图片提供商"""
        return [
            {
                "name": p.name,
                "model": p.model,
                "provider_id": p.provider_id,
                "enabled": p.enabled,
                "is_default": p.name == self._default_provider
            }
            for p in self._providers.values()
        ]

    def set_default(self, name: str):
        """设置默认提供商"""
        if name in self._providers:
            self._default_provider = name

    def update_provider(self, name: str, api_key: str = None, **kwargs):
        """更新提供商配置"""
        if name in self._providers:
            p = self._providers[name]
            if api_key:
                p.api_key = api_key
            for k, v in kwargs.items():
                if hasattr(p, k):
                    setattr(p, k, v)
            self._save_config()

    def _load_config(self):
        """加载配置文件"""
        if self._config_file.exists():
            try:
                import json
                data = json.loads(self._config_file.read_text(encoding="utf-8"))
                for name, pdata in data.get("providers", {}).items():
                    if name in self._providers:
                        p = self._providers[name]
                        p.api_key = pdata.get("api_key", "")
                        p.enabled = pdata.get("enabled", True)
                        p.size = pdata.get("size", "1024x1024")
            except Exception:
                pass

    def _save_config(self):
        """保存配置文件"""
        try:
            import json
            data = {
                "default": self._default_provider,
                "providers": {
                    name: {
                        "api_key": p.api_key,
                        "enabled": p.enabled,
                        "size": p.size
                    }
                    for name, p in self._providers.items()
                }
            }
            self._config_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


# ============ 图片生成器 ============

class ImageGenerator:
    """
    图片生成器
    支持调用多个图片生成 API
    """

    def __init__(self, provider: ImageProvider = None):
        self.config = ImageModelConfig()
        self.provider = provider or self.config.get_provider()

    def generate(self, prompt: str, save_dir: str = None, filename: str = None, **kwargs) -> Dict:
        """
        生成图片

        参数:
            prompt: 图片描述
            save_dir: 保存目录（默认当前工作目录）
            filename: 文件名（默认时间戳）
            **kwargs: 额外参数 (size, quality, style)

        返回:
            Dict: {
                "success": bool,
                "path": str,  # 本地文件路径
                "url": str,    # 原始 URL
                "error": str
            }
        """
        if not self.provider:
            return {"success": False, "error": "未配置图片生成器"}

        provider = self.provider
        size = kwargs.get("size") or provider.size
        quality = kwargs.get("quality") or provider.quality
        style = kwargs.get("style") or provider.style

        try:
            # 根据不同的 provider 调用不同的 API
            if provider.provider_id == "zhipu":
                result = self._generate_zhipu(prompt, size, quality)
            elif provider.provider_id == "minimax":
                result = self._generate_minimax(prompt, size)
            elif provider.provider_id == "qwen":
                result = self._generate_qwen(prompt, size)
            else:
                result = self._generate_generic(prompt, provider)

            if result.get("success") and result.get("image_data"):
                # 下载并保存图片
                save_path = self._download_image(
                    result["image_data"],
                    save_dir or os.getcwd(),
                    filename
                )
                result["path"] = save_path
                del result["image_data"]  # 清理内存

            return result

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _generate_zhipu(self, prompt: str, size: str, quality: str) -> Dict:
        """智谱 CogView 生成"""
        try:
            from zhipuai import ZhipuAI

            client = ZhipuAI(api_key=self.provider.api_key or os.getenv("ZHIPU_API_KEY"))

            response = client.images.generation(
                model="cogview-4",
                prompt=prompt,
                size=size,
                quality=quality
            )

            return {
                "success": True,
                "url": response.data[0].url,
                "image_data": self._fetch_image_data(response.data[0].url)
            }
        except Exception as e:
            return {"success": False, "error": f"智谱 CogView 生成失败: {str(e)}"}

    def _generate_minimax(self, prompt: str, size: str) -> Dict:
        """MiniMax 图片生成"""
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.provider.api_key or os.getenv("MINIMAX_API_KEY"),
                base_url=self.provider.base_url or "https://api.minimax.chat/v1"
            )

            response = client.images.generate(
                model="image-01",
                prompt=prompt,
                size=size
            )

            return {
                "success": True,
                "url": response.data[0].url,
                "image_data": self._fetch_image_data(response.data[0].url)
            }
        except Exception as e:
            return {"success": False, "error": f"MiniMax 图片生成失败: {str(e)}"}

    def _generate_qwen(self, prompt: str, size: str) -> Dict:
        """通义万相生成"""
        try:
            import requests

            response = requests.post(
                url=f"{self.provider.base_url}/services/aigc/text-to-image/imageCreation",
                headers={"Authorization": f"Bearer {self.provider.api_key or os.getenv('DASHSCOPE_API_KEY')}"},
                json={
                    "model": "wanx2.1-t2i-turbo",
                    "input": {"prompt": prompt},
                    "parameters": {"size": size}
                },
                timeout=60
            )

            data = response.json()
            task_id = data.get("output", {}).get("task_id")

            # 轮询结果
            result_url = self._wait_qwen_result(task_id)

            return {
                "success": True,
                "url": result_url,
                "image_data": self._fetch_image_data(result_url)
            }
        except Exception as e:
            return {"success": False, "error": f"通义万相生成失败: {str(e)}"}

    def _generate_generic(self, prompt: str, provider: ImageProvider) -> Dict:
        """通用 OpenAI 兼容接口生成"""
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=provider.api_key or os.getenv("OPENAI_API_KEY"),
                base_url=provider.base_url
            )

            response = client.images.generate(
                model=provider.model,
                prompt=prompt,
                size=provider.size
            )

            return {
                "success": True,
                "url": response.data[0].url,
                "image_data": self._fetch_image_data(response.data[0].url)
            }
        except Exception as e:
            return {"success": False, "error": f"图片生成失败: {str(e)}"}

    def _fetch_image_data(self, url: str) -> bytes:
        """获取图片数据"""
        import requests
        response = requests.get(url, timeout=30)
        return response.content

    def _wait_qwen_result(self, task_id: str, max_wait: int = 60) -> str:
        """等待通义万相任务完成"""
        import time
        import requests

        for _ in range(max_wait):
            response = requests.get(
                url=f"{self.provider.base_url}/services/aigc/text-to-image/imageCreation",
                headers={"Authorization": f"Bearer {self.provider.api_key}"},
                params={"task_id": task_id}
            )
            data = response.json()
            if data.get("output", {}).get("image_url"):
                return data["output"]["image_url"]
            time.sleep(1)

        raise Exception("通义万相任务超时")

    def _download_image(self, image_data: bytes, save_dir: str, filename: str = None) -> str:
        """下载并保存图片"""
        os.makedirs(save_dir, exist_ok=True)

        if filename is None:
            filename = f"image_{int(time.time())}.png"

        filepath = os.path.join(save_dir, filename)

        with open(filepath, "wb") as f:
            f.write(image_data)

        return filepath


# ============ 终端图片显示 ============

class TerminalImageDisplay:
    """
    终端图片显示
    支持 ASCII 艺术、Unicode 字符、原始图片显示
    """

    @staticmethod
    def display_image(image_path: str, method: str = "auto") -> bool:
        """
        在终端显示图片

        参数:
            image_path: 图片路径
            method: 显示方法 (auto/kitty/iterm2/braille/ascii)

        返回:
            bool: 是否成功
        """
        if not os.path.exists(image_path):
            print(f"图片不存在: {image_path}")
            return False

        if method == "auto":
            method = TerminalImageDisplay._detect_method()

        if method == "kitty":
            return TerminalImageDisplay._display_kitty(image_path)
        elif method == "iterm2":
            return TerminalImageDisplay._display_iterm2(image_path)
        elif method == "braille":
            return TerminalImageDisplay._display_braille(image_path)
        elif method == "ascii":
            return TerminalImageDisplay._display_ascii(image_path)
        else:
            print(f"不支持的显示方法: {method}")
            return False

    @staticmethod
    def _detect_method() -> str:
        """检测终端支持的显示方法"""
        term = os.environ.get("TERM_PROGRAM", "")

        if term == "iTerm.app":
            return "iterm2"
        elif os.environ.get("KITTY_WINDOW_ID"):
            return "kitty"
        elif os.environ.get("TERM") in ("xterm-256color", "screen-256color"):
            return "braille"

        return "ascii"  # 默认使用 ASCII

    @staticmethod
    def _display_kitty(image_path: str) -> bool:
        """Kitty 终端图片显示"""
        try:
            import base64
            with open(image_path, "rb") as f:
                data = base64.b64encode(f.read()).decode()

            print(f"\033[1337;File={image_path};inline=1:{data}\033\\")
            return True
        except Exception as e:
            print(f"Kitty 显示失败: {e}")
            return False

    @staticmethod
    def _display_iterm2(image_path: str) -> bool:
        """iTerm2 图片显示"""
        try:
            import base64
            with open(image_path, "rb") as f:
                data = base64.b64encode(f.read()).decode()

            print(f"\033]1337;File=name={os.path.basename(image_path)};size={os.path.getsize(image_path)};inline=1:{data}\a")
            return True
        except Exception as e:
            print(f"iTerm2 显示失败: {e}")
            return False

    @staticmethod
    def _display_braille(image_path: str, max_width: int = 120) -> bool:
        """Unicode Braille 字符显示"""
        try:
            from PIL import Image

            img = Image.open(image_path)
            img = img.convert("L")  # 转灰度

            # 计算缩放比例
            width, height = img.size
            aspect = height / width
            new_width = min(max_width, width)
            new_height = int(new_width * aspect * 0.5)  # 高度减半因为字符高度

            img = img.resize((new_width, new_height))

            # 转换为 Braille 字符
            chars = " .:-=+*#%@"
            result = []

            for y in range(new_height):
                row = ""
                for x in range(new_width):
                    pixel = img.getpixel((x, y))
                    char_idx = int(pixel / 256 * len(chars))
                    row += chars[char_idx]
                result.append(row)

            print("\n" + "\n".join(result))
            return True

        except ImportError:
            print("需要安装 Pillow: pip install pillow")
            return TerminalImageDisplay._display_ascii(image_path)
        except Exception as e:
            print(f"Braille 显示失败: {e}")
            return False

    @staticmethod
    def _display_ascii(image_path: str, max_width: int = 100) -> bool:
        """ASCII 字符显示"""
        try:
            from PIL import Image

            img = Image.open(image_path)
            img = img.convert("L")

            width, height = img.size
            aspect = height / width
            new_width = min(max_width, width)
            new_height = int(new_width * aspect * 0.5)

            img = img.resize((new_width, new_height))

            chars = " .:-=+*#%@"
            result = []

            for y in range(new_height):
                row = ""
                for x in range(new_width):
                    pixel = img.getpixel((x, y))
                    char_idx = int(pixel / 256 * len(chars))
                    row += chars[char_idx]
                result.append(row)

            print("\n" + "\n".join(result))
            return True

        except ImportError:
            print("需要安装 Pillow: pip install pillow")
            return False
        except Exception as e:
            print(f"ASCII 显示失败: {e}")
            return False


# ============ 并行任务执行 ============

@dataclass
class TaskResult:
    """任务结果"""
    task_id: str
    task_name: str
    status: str  # pending/running/completed/failed
    result: Any = None
    error: str = ""
    execution_time: float = 0.0
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0


class ParallelExecutor:
    """
    并行任务执行器
    支持多线程/异步执行多个 Agent 或任务
    """

    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.tasks: Dict[str, Future] = {}
        self.results: Dict[str, TaskResult] = {}

    def submit(self, task_id: str, task_name: str, func: Callable, *args, **kwargs) -> str:
        """
        提交任务

        参数:
            task_id: 任务 ID
            task_name: 任务名称（用于显示）
            func: 执行函数
            *args, **kwargs: 函数参数

        返回:
            str: 任务 ID
        """
        result = TaskResult(
            task_id=task_id,
            task_name=task_name,
            status="running"
        )
        self.results[task_id] = result

        def wrapper():
            try:
                result_obj = func(*args, **kwargs)
                result.result = result_obj
                result.status = "completed"
            except Exception as e:
                result.error = str(e)
                result.status = "failed"
            finally:
                result.end_time = time.time()
                result.execution_time = result.end_time - result.start_time

        future = self.executor.submit(wrapper)
        self.tasks[task_id] = future

        return task_id

    def submit_agent(self, task_id: str, agent_name: str, state, input_data: str, **kwargs) -> str:
        """
        提交 Agent 执行任务

        参数:
            task_id: 任务 ID
            agent_name: Agent 名称
            state: AppState 实例
            input_data: 输入数据
            **kwargs: 额外参数

        返回:
            str: 任务 ID
        """
        from fr_cli.agent.executor import delegate_to_agent

        def agent_task():
            result, error = delegate_to_agent(
                agent_name,
                state,
                pipeline_input=input_data,
                **kwargs
            )
            return {"result": result, "error": error}

        return self.submit(task_id, f"Agent:{agent_name}", agent_task)

    def wait(self, task_ids: List[str] = None, timeout: float = None) -> Dict[str, TaskResult]:
        """
        等待任务完成

        参数:
            task_ids: 要等待的任务 ID（None 表示等待所有）
            timeout: 超时时间

        返回:
            Dict[str, TaskResult]: 任务结果
        """
        if task_ids is None:
            task_ids = list(self.tasks.keys())

        for task_id in task_ids:
            if task_id in self.tasks:
                try:
                    self.tasks[task_id].result(timeout=timeout)
                except TimeoutError:
                    pass

        return {tid: self.results[tid] for tid in task_ids if tid in self.results}

    def get_result(self, task_id: str) -> Optional[TaskResult]:
        """获取任务结果"""
        return self.results.get(task_id)

    def get_status(self) -> Dict:
        """获取执行器状态"""
        running = sum(1 for r in self.results.values() if r.status == "running")
        completed = sum(1 for r in self.results.values() if r.status == "completed")
        failed = sum(1 for r in self.results.values() if r.status == "failed")

        return {
            "max_workers": self.max_workers,
            "running": running,
            "completed": completed,
            "failed": failed,
            "total": len(self.results)
        }

    def shutdown(self, wait: bool = True):
        """关闭执行器"""
        self.executor.shutdown(wait=wait)


class AsyncParallelExecutor:
    """
    异步并行执行器
    使用 asyncio 实现异步任务执行
    """

    def __init__(self):
        self.tasks: Dict[str, asyncio.Task] = {}
        self.results: Dict[str, TaskResult] = {}
        self._loop = None

    async def submit(self, task_id: str, task_name: str, coro) -> str:
        """提交异步任务"""
        result = TaskResult(
            task_id=task_id,
            task_name=task_name,
            status="running"
        )
        self.results[task_id] = result

        async def wrapper():
            try:
                result_obj = await coro
                result.result = result_obj
                result.status = "completed"
            except Exception as e:
                result.error = str(e)
                result.status = "failed"
            finally:
                result.end_time = time.time()
                result.execution_time = result.end_time - result.start_time

        task = asyncio.create_task(wrapper())
        self.tasks[task_id] = task

        return task_id

    async def submit_agent(self, task_id: str, agent_name: str, state, input_data: str, **kwargs) -> str:
        """提交异步 Agent 任务"""
        from fr_cli.agent.executor import delegate_to_agent

        async def agent_coro():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: delegate_to_agent(agent_name, state, pipeline_input=input_data, **kwargs)
            )

        return await self.submit(task_id, f"Agent:{agent_name}", agent_coro())

    async def wait_all(self) -> Dict[str, TaskResult]:
        """等待所有任务完成"""
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        return self.results

    async def wait(self, task_ids: List[str]) -> Dict[str, TaskResult]:
        """等待指定任务完成"""
        tasks = [self.tasks[tid] for tid in task_ids if tid in self.tasks]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return {tid: self.results[tid] for tid in task_ids if tid in self.results}

    def get_result(self, task_id: str) -> Optional[TaskResult]:
        """获取任务结果"""
        return self.results.get(task_id)

    def get_status(self) -> Dict:
        """获取执行器状态"""
        running = sum(1 for r in self.results.values() if r.status == "running")
        completed = sum(1 for r in self.results.values() if r.status == "completed")
        failed = sum(1 for r in self.results.values() if r.status == "failed")

        return {
            "running": running,
            "completed": completed,
            "failed": failed,
            "total": len(self.results)
        }


# ============ 批量图片生成 ============

class BatchImageGenerator:
    """
    批量图片生成器
    支持并行生成多张图片
    """

    def __init__(self, max_workers: int = 3):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.generator = ImageGenerator()

    def generate_batch(self, prompts: List[str], save_dir: str = None, **kwargs) -> List[Dict]:
        """
        批量生成图片

        参数:
            prompts: 图片描述列表
            save_dir: 保存目录
            **kwargs: 额外参数

        返回:
            List[Dict]: 生成结果列表
        """
        futures = []

        for i, prompt in enumerate(prompts):
            filename = f"batch_image_{i+1}_{int(time.time())}.png"
            future = self.executor.submit(
                self.generator.generate,
                prompt,
                save_dir,
                filename,
                **kwargs
            )
            futures.append(future)

        results = []
        for future in futures:
            try:
                results.append(future.result(timeout=120))
            except Exception as e:
                results.append({"success": False, "error": str(e)})

        return results

    def shutdown(self):
        """关闭执行器"""
        self.executor.shutdown(wait=True)


# ============ 工具函数 ============

def generate_and_display(prompt: str, provider_name: str = None, display_method: str = "auto") -> Dict:
    """
    一站式图片生成和显示

    参数:
        prompt: 图片描述
        provider_name: 提供商名称
        display_method: 显示方法

    返回:
        Dict: 生成结果
    """
    config = ImageModelConfig()
    if provider_name:
        provider = config.get_provider(provider_name)
    else:
        provider = config.get_provider()

    generator = ImageGenerator(provider)
    result = generator.generate(prompt)

    if result.get("success") and result.get("path"):
        print(f"✅ 图片已保存到: {result['path']}")
        TerminalImageDisplay.display_image(result["path"], display_method)

    return result


def parallel_agent_execution(agent_configs: List[Dict], state) -> Dict[str, TaskResult]:
    """
    并行执行多个 Agent

    参数:
        agent_configs: Agent 配置列表
            [{"name": "agent1", "input": "task1"}, {"name": "agent2", "input": "task2"}]
        state: AppState 实例

    返回:
        Dict[str, TaskResult]: 任务结果
    """
    executor = ParallelExecutor(max_workers=len(agent_configs))

    task_ids = []
    for config in agent_configs:
        task_id = executor.submit_agent(
            task_id=f"task_{len(task_ids)}",
            agent_name=config["name"],
            state=state,
            input_data=config["input"]
        )
        task_ids.append(task_id)

    results = executor.wait()
    executor.shutdown()

    return results


# ============ 导出 ============

def run(context: Dict, **kwargs) -> str:
    """
    工具模块入口（可被 Agent 调用）

    使用示例：
    【调用：generate_image({"prompt": "一只猫", "provider": "minimax"})】
    【调用：batch_generate({"prompts": ["猫", "狗", "鸟"], "save_dir": "./images"})】
    【调用：parallel_execute({"agents": [{"name": "code-agent", "input": "生成代码"}]})】
    """
    action = kwargs.get("action", "")

    if action == "generate":
        return _handle_generate(kwargs)

    elif action == "batch_generate":
        return _handle_batch_generate(kwargs)

    elif action == "parallel_execute":
        return _handle_parallel_execute(kwargs)

    elif action == "display_image":
        return _handle_display_image(kwargs)

    elif action == "configure_provider":
        return _handle_configure_provider(kwargs)

    else:
        return "未知操作。可用操作: generate, batch_generate, parallel_execute, display_image, configure_provider"


def _handle_generate(kwargs) -> str:
    """处理图片生成"""
    prompt = kwargs.get("prompt", "")
    provider_name = kwargs.get("provider")
    display = kwargs.get("display", True)

    result = generate_and_display(prompt, provider_name, "auto" if display else None)

    if result.get("success"):
        return f"✅ 图片生成成功！\n路径: {result.get('path')}\nURL: {result.get('url')}"
    else:
        return f"❌ 图片生成失败: {result.get('error')}"


def _handle_batch_generate(kwargs) -> str:
    """处理批量生成"""
    prompts = kwargs.get("prompts", [])
    save_dir = kwargs.get("save_dir")

    if not prompts:
        return "❌ 未提供 prompts 参数"

    generator = BatchImageGenerator()
    results = generator.generate_batch(prompts, save_dir)
    generator.shutdown()

    success_count = sum(1 for r in results if r.get("success"))
    return f"✅ 批量生成完成: {success_count}/{len(prompts)} 张成功"


def _handle_parallel_execute(kwargs) -> str:
    """处理并行执行"""
    agents = kwargs.get("agents", [])
    state = kwargs.get("state")

    if not agents:
        return "❌ 未提供 agents 参数"

    results = parallel_agent_execution(agents, state)

    success_count = sum(1 for r in results.values() if r.status == "completed")
    return f"✅ 并行执行完成: {success_count}/{len(agents)} 个任务成功"


def _handle_display_image(kwargs) -> str:
    """处理图片显示"""
    path = kwargs.get("path", "")
    method = kwargs.get("method", "auto")

    if not path:
        return "❌ 未提供 path 参数"

    success = TerminalImageDisplay.display_image(path, method)
    return "✅ 图片已显示" if success else "❌ 显示失败"


def _handle_configure_provider(kwargs) -> str:
    """处理提供商配置"""
    name = kwargs.get("name")
    api_key = kwargs.get("api_key")
    enabled = kwargs.get("enabled", True)

    if not name:
        return "❌ 未提供 name 参数"

    config = ImageModelConfig()

    if api_key:
        config.update_provider(name, api_key)

    provider = config.get_provider(name)
    if provider:
        provider.enabled = enabled
        config._save_config()
        return f"✅ 提供商 {name} 配置已更新"

    return f"❌ 未找到提供商: {name}"


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    图片模型和并行任务执行模块                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

功能：
  🖼️  图片生成: 支持多个图片生成提供商
  📥  自动下载: 图片生成后自动保存到工作目录
  🖥️  终端显示: ASCII/Braille/Unicode 多种显示方式
  ⚡ 并行执行: 多线程/异步执行多个任务
  🤖 Agent协作: 多 Agent 并发执行

支持的图片提供商：
  • 智谱 CogView-4
  • MiniMax 图片
  • 通义万相
  • StepFun 图片

使用示例：

  # 生成图片
  result = generate_and_display("一只可爱的猫")

  # 批量生成
  results = batch_generate(["猫", "狗", "鸟"], save_dir="./images")

  # 并行执行 Agent
  results = parallel_agent_execution([
      {"name": "code-agent", "input": "生成代码"},
      {"name": "doc-agent", "input": "生成文档"}
  ], state)

工具调用格式：
  【调用：generate_image({"prompt": "...", "provider": "minimax"})】
  【调用：batch_generate({"prompts": [...], "save_dir": "..."})】
  【调用：parallel_execute({"agents": [...]})】
""")