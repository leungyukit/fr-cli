# Agent2Agent Protocol (A2A) 和 Provider 更新文档

## 更新日期：2025-04-28

---

## 一、新增功能概览

本次更新包含以下主要功能：

### 1. Agent2Agent Protocol (A2A) - Agent 互操作协议
- Agent 发现与注册
- 能力描述与匹配
- 任务委托与执行
- 结果返回与状态同步

### 2. StepFun 模型支持
- 新增 Step-1、Step-2、Step-3 系列模型
- 新增 Step-Audio 实时语音模型
- 更新 API 配置

### 3. MiniMax 和 Kimi 更新
- MiniMax Token Plan 支持
- Kimi Code 平台支持

---

## 二、Agent2Agent Protocol (A2A)

### 2.1 协议概述

A2A 协议实现了 Agent 之间的互操作，支持：
- 本地 Agent 和远程 Agent 的统一调用
- 任务委托和结果返回
- Agent 能力发现和匹配
- HTTP 接口支持

### 2.2 核心组件

#### AgentRegistry - Agent 注册表

```python
from fr_cli.agent.a2a import AgentRegistry, AgentInfo

# 获取注册表实例（单例）
registry = AgentRegistry()

# 注册 Agent
agent = AgentInfo(
    name="code-agent",
    type="local",
    description="代码生成专家",
    capabilities=["code_generation", "code_review"]
)
registry.register(agent)

# 查找 Agent
agent = registry.get_agent("code-agent")

# 列出所有 Agent
agents = registry.list_agents()

# 查找最佳 Agent
best = registry.find_best_agent(
    task_description="Generate Python code",
    required_capabilities=["code_generation"]
)
```

#### A2AClient - A2A 客户端

```python
from fr_cli.agent.a2a import A2AClient

# 创建客户端
client = A2AClient()

# 提交任务
task_id = client.submit_task(
    agent_name="code-agent",
    user_input="生成一个快速排序算法",
    context={"language": "python"}
)

# 同步调用 Agent
result = client.call_agent_sync(
    agent_name="code-agent",
    user_input="生成快速排序代码",
    timeout=300
)
```

#### A2AServer - A2A 服务器

```python
from fr_cli.agent.a2a import A2AServer

# 创建服务器
server = A2AServer(
    agent_name="my-agent",
    agent_module=agent_module,
    host="127.0.0.1",
    port=8080
)

# 启动服务器
server.start_sync()
```

### 2.3 数据结构

#### AgentInfo - Agent 信息

```python
@dataclass
class AgentInfo:
    name: str              # Agent 名称
    type: str              # 类型 (local/remote)
    description: str        # 描述
    capabilities: List[str]  # 能力列表
    endpoint: Optional[str]   # HTTP 端点
    auth_token: Optional[str]  # 认证令牌
    version: str           # 版本
    status: str            # 状态 (online/offline)
```

#### TaskRequest - 任务请求

```python
@dataclass
class TaskRequest:
    task_id: str           # 任务 ID
    agent_name: str        # 目标 Agent
    user_input: str        # 用户输入
    context: Dict[str, Any]  # 上下文
    timeout: int = 300     # 超时时间
    priority: int = 0      # 优先级
```

#### TaskResult - 任务结果

```python
@dataclass
class TaskResult:
    task_id: str           # 任务 ID
    status: TaskStatus     # 状态 (pending/running/completed/failed)
    result: Any = None      # 结果
    error: Optional[str] = None  # 错误信息
    execution_time: float = 0.0  # 执行时间
```

### 2.4 Agent 能力类型

```python
class AgentCapability(Enum):
    CODE_GENERATION = "code_generation"      # 代码生成
    CODE_REVIEW = "code_review"              # 代码审查
    DATA_ANALYSIS = "data_analysis"          # 数据分析
    WEB_SEARCH = "web_search"                # 网络搜索
    FILE_OPERATION = "file_operation"        # 文件操作
    DATABASE = "database"                    # 数据库
    IMAGE_PROCESSING = "image_processing"     # 图像处理
    TEXT_GENERATION = "text_generation"      # 文本生成
    TRANSLATION = "translation"              # 翻译
    GENERAL = "general"                      # 通用
```

### 2.5 使用示例

#### 任务委托

```python
from fr_cli.agent.a2a import A2AClient

client = A2AClient()

# 调用本地 Agent
result = client.call_agent_sync(
    agent_name="data-analyst",
    user_input="分析销售数据并生成报告",
    context={
        "state": state,  # AppState 实例
        "pipeline_input": None
    }
)

if result.status == TaskStatus.COMPLETED:
    print(f"结果: {result.result}")
else:
    print(f"错误: {result.error}")
```

#### Agent 发现

```python
from fr_cli.agent.a2a import discover_all_agents

# 获取所有可用 Agent
agents = discover_all_agents()

for agent in agents:
    print(f"- [{agent['type']}] {agent['name']}: {agent['description']}")
    print(f"  能力: {', '.join(agent['capabilities'])}")
```

---

## 三、StepFun 模型支持

### 3.1 新增 Provider

| Provider ID | 名称 | 默认模型 | 说明 |
|------------|------|---------|------|
| `stepfun` | 阶跃星辰 (StepFun) | step-1-8k | 基础模型 |
| `step-1` | Step-1 (阶跃星辰) | step-1-8k | Step-1 模型 |
| `step-2` | Step-2 (阶跃星辰) | step-2-16k | Step-2 模型（16k 上下文）|
| `step-3` | Step-3 (阶跃星辰) | step-3-auto | Step-3 模型（自动推理）|
| `step-audio` | Step-Audio (实时语音) | step-audio-2 | 实时语音交互 |

### 3.2 使用方法

```bash
# 配置 StepFun API Key
/providers add stepfun <your-stepfun-api-key>

# 使用 Step-1 模型
/model stepfun

# 使用 Step-3 模型
/model step-3

# 使用特定模型
/model step-3:step-3-auto
```

### 3.3 Step-3 特点

根据 [StepFun 官方文档](https://platform.stepfun.com/docs/zh/guides/basic-concepts)：

- **Step-3**: 最新一代基础大模型，拥有强大视觉感知和复杂推理能力
- 支持 OpenAI/Anthropic 兼容 API
- 开源模型，可自行部署

### 3.4 Step-Audio 特点

- 实时语音交互
- 支持 WebSocket 连接
- 适合语音助手和实时对话场景

---

## 四、完整 Provider 列表

### 4.1 所有 Provider

| Provider ID | 名称 | 默认模型 |
|------------|------|---------|
| `zhipu` | 智谱AI | glm-4-flash |
| `deepseek` | DeepSeek | deepseek-chat |
| `kimi` | Kimi (Moonshot) | moonshot-v1-8k |
| `kimi-k2` | Kimi K2 (代码优化版) | kimi-k2-0905-preview |
| `kimi-code` | Kimi Code (代码平台) | kimi-cache-test |
| `kimi-code-anthropic` | Kimi Code (Anthropic兼容) | kimi-cache-test |
| `qwen` | 通义千问 (Qwen) | qwen-turbo |
| `stepfun` | 阶跃星辰 (StepFun) | step-1-8k |
| `step-1` | Step-1 (阶跃星辰) | step-1-8k |
| `step-2` | Step-2 (阶跃星辰) | step-2-16k |
| `step-3` | Step-3 (阶跃星辰) | step-3-auto |
| `step-audio` | Step-Audio (实时语音) | step-audio-2 |
| `minimax` | MiniMax | MiniMax-Text-01 |
| `minimax-chat` | MiniMax Chat | abab6.5s-chat |
| `minimax-m27` | MiniMax M2.7 (Token Plan) | MiniMax-M2.7 |
| `minimax-m27-fast` | MiniMax M2.7-HighSpeed (Token Plan) | MiniMax-M2.7-HighSpeed |
| `minimax-token-plan` | MiniMax Token Plan (全模态) | MiniMax-M2.7 |
| `spark` | 讯飞星火 (Spark) | generalv3.5 |
| `doubao` | 豆包 (Doubao) | doubao-1-5-pro-32k-250115 |
| `mimo` | 小米 MiMo | mimo-v2-flash |

---

## 五、测试验证

### 5.1 测试文件

- `tests/test_a2a_and_providers.py`: A2A 协议和 StepFun Provider 测试
- `tests/test_new_providers.py`: MiniMax 和 Kimi Provider 测试
- `tests/test_master_prompt_fix.py`: MasterPrompt 修复测试
- `tests/test_model_config.py`: 模型配置测试
- `tests/test_integration_real.py`: 集成测试

### 5.2 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行 A2A 和 Provider 测试
pytest tests/test_a2a_and_providers.py -v

# 运行特定测试类
pytest tests/test_a2a_and_providers.py::TestA2AProtocol -v
pytest tests/test_a2a_and_providers.py::TestStepFunProviders -v
```

### 5.3 测试结果

```
✅ 103 个测试通过
❌ 1 个测试失败（预先存在的环境问题）
```

---

## 六、版本信息

- **fr-cli**: v2.2.7 → v2.2.8
- **新增 Provider**: 13 个
  - StepFun 系列: 5 个
  - MiniMax 系列: 3 个
  - Kimi Code 系列: 2 个
  - Kimi K2: 1 个
  - Kimi Code Anthropic: 1 个
  - Kimi Code: 1 个
- **新增模块**: A2A 协议模块

---

## 七、参考链接

- [StepFun 开放平台](https://platform.stepfun.com/)
- [StepFun API 文档](https://platform.stepfun.com/docs/api-reference)
- [A2A 协议设计](docs/a2a-protocol.md)

---

**祝您使用愉快！** 🚀

如有问题，请访问 [GitHub Issues](https://github.com/yourname/fr-cli/issues)