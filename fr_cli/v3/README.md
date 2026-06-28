# fr-cli v3.0 架构

> **核心原则**:渐进式重构 + 向后兼容。新基础设施加在 `fr_cli/v3/`,旧 API 完全保留。

## 1. 当前架构问题

```
main.py (REPL 大函数)
  → core.core.AppState (DI 容器,但所有状态都塞一起)
    → agent.master.MasterAgent (耦合对话+工具+反思)
      → command.executor.CommandExecutor (硬编码 hooks + 工具调度)
        → registry.ToolRegistry (静态注册)
```

**痛点**:
1. `AppState` 是"上帝对象",耦合太紧
2. `MasterAgent` 同时管对话、工具调度、反思、记忆,职责不清
3. 直接函数调用,无法插入横切关注点(audit/observability)
4. 同步阻塞,没有真正的异步管线
5. 插件(ad-hoc)与注册表(标准化)混用
6. 依赖关系不清晰,有循环引用风险

## 2. v3.0 新分层架构

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 6: Interfaces (UI)                                    │
│    fr_cli.repl/      fr_cli.web/console.py     fr_cli.main   │
│    终端 REPL        Web 控制台 + PWA          MCP Server   │
├──────────────────────────────────────────────────────────────┤
│  Layer 5: Applications                                       │
│    fr_cli.v3.app.App           全局应用门面                   │
├──────────────────────────────────────────────────────────────┤
│  Layer 4: Agents                                             │
│    fr_cli.v3.agent.MasterAgent  基于 EventBus                  │
│    fr_cli.agent.builtins/*     内置 Agent(@local/@RAG/...)   │
├──────────────────────────────────────────────────────────────┤
│  Layer 3: Services (业务服务)                                │
│    fr_cli.v3.service.Session  Memory  RAG  Plan  Permission │
│    全部注册到 Container,通过接口调用,不直接 import          │
├──────────────────────────────────────────────────────────────┤
│  Layer 2: Providers (能力提供方)                             │
│    fr_cli.v3.provider.LLMProvider / ToolProvider /           │
│                            ResourceProvider / PromptProvider│
│    统一接口,具体实现在 v3 compat 层                          │
├──────────────────────────────────────────────────────────────┤
│  Layer 1: Core (基础设施)                                    │
│    fr_cli.v3.core.EventBus        事件总线                    │
│    fr_cli.v3.core.errors          统一错误                    │
│    fr_cli.v3.core.lifecycle       App lifecycle hooks        │
│    fr_cli.v3.core.container       DI 容器                     │
│    fr_cli.v3.core.plugin          插件接口                    │
│    fr_cli.v3.core.pipeline        流式处理                    │
└──────────────────────────────────────────────────────────────┘
```

## 3. v3.0 关键设计

### 3.1 EventBus(事件驱动)

**取代**:直接函数调用,所有横切关注点(日志/监控/审计/UI 推送)订阅事件。

```python
bus = EventBus()

# 订阅
bus.on("tool.invoked", lambda e: log.info(f"tool: {e['name']}"))
bus.on("llm.responded", lambda e: update_token_stats(e["tokens"]))

# 发布
bus.emit("tool.invoked", {"name": "search_web", "args": {...}})
```

事件类型:
- `llm.requested / llm.responded / llm.failed`
- `tool.invoked / tool.succeeded / tool.failed`
- `session.created / session.message_added / session.saved`
- `plan.created / plan.approved / plan.executed`
- `app.starting / app.started / app.stopping / app.stopped`

### 3.2 Container(依赖注入)

**取代**:`AppState` 上帝对象。

```python
container = Container()
container.register("config", load_config())
container.register("vfs", VFS(container.get("config")))
container.register("executor", CommandExecutor(container))

# 获取
vfs = container.get("vfs")
```

特性:
- 单例模式(默认)
- 自动依赖解析(type hints)
- 测试时可替换(register override)

### 3.3 Lifecycle(应用生命周期)

**取代**:散落的 init 函数。

```python
app = App()

@app.on("starting")
def setup_logger():
    ...

@app.on("started")
def start_background_services():
    ...

@app.on("stopping")
def cleanup():
    ...

app.start()
```

### 3.4 Provider(统一抽象)

**取代**:LLMClient / Tool / Resource / Prompt 各一套。

```python
class Provider(Protocol):
    name: str
    async def invoke(self, request) -> Response: ...

# LLM / Tool / Resource / Prompt 都实现此接口
class LLMProvider(Provider):
    name = "zhipu"
    async def invoke(self, request: LLMRequest) -> LLMResponse: ...

class ToolProvider(Provider):
    name = "search_web"
    async def invoke(self, request: ToolRequest) -> ToolResponse: ...
```

### 3.5 Plugin(规范化的插件接口)

**取代**:ad-hoc 的 plugin / addon / skill 混用。

```python
from fr_cli.v3.core.plugin import Plugin, hook

class MyPlugin(Plugin):
    name = "my-plugin"

    @hook("tool.before_invoke")
    def log_invocation(self, event):
        log.info(event)

    @hook("tool.after_invoke")
    def record_result(self, event):
        metrics.counter(f"tool.{event['name']}").inc()

plugin_manager.register(MyPlugin())
```

### 3.6 Pipeline(流式处理)

**取代**:每处自己实现流式回调。

```python
@pipeline("llm.stream")
async def stream_llm(messages, on_chunk, on_done):
    # 自动处理 SSE / 流式响应
    async for chunk in client.stream(messages):
        on_chunk(chunk)
    on_done(final_response)
```

## 4. 兼容性保证

- ✅ 现有 1459 个测试全部通过
- ✅ 现有 API 全部保留(只是内部走新 EventBus)
- ✅ `AppState` 仍然可用(适配器)
- ✅ `MCPServerManager` 等工具仍然可用
- ✅ REPL 用户体验不变
- ✅ Web 控制台页面不变

## 5. 迁移路径(渐进)

```
v2.8.x (现状)
   ↓
v3.0: 新基础设施(E3Bus, Container, Lifecycle) — 不破坏 API
v3.1: 主循环改为 EventBus 驱动
v3.2: Agent 改为订阅事件而非调用
v3.3: Tool / LLM 改为 Provider 抽象
v3.4: 完整插件系统 + entry_points
```

## 6. 文件清单

新增:
- `fr_cli/v3/__init__.py`
- `fr_cli/v3/core/__init__.py`
- `fr_cli/v3/core/events.py` — EventBus
- `fr_cli/v3/core/errors.py` — 错误类型
- `fr_cli/v3/core/lifecycle.py` — App lifecycle
- `fr_cli/v3/core/container.py` — DI 容器
- `fr_cli/v3/core/provider.py` — Provider 协议
- `fr_cli/v3/core/plugin.py` — Plugin 接口
- `fr_cli/v3/core/pipeline.py` — 流式处理
- `fr_cli/v3/service/__init__.py` — 服务接口占位
- `fr_cli/v3/compat/__init__.py` — v2→v3 兼容层
- `fr_cli/v3/app.py` — App 门面

测试:
- `tests/test_v3_events.py`
- `tests/test_v3_container.py`
- `tests/test_v3_lifecycle.py`
- `tests/test_v3_provider.py`
- `tests/test_v3_plugin.py`

文档:
- `fr_cli/v3/README.md`(已在本目录)
- 更新 `README.md` 添加 v3.0 章节