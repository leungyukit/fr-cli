# 凡人打字机 (fr-cli) —— 架构设计文档

> 本文档面向二次开发者。回答"这个项目怎么组织的、为什么这样组织、新功能往哪加"。

## 1. 设计原则

1. **单一真相源 (Single Source of Truth)**
   - 配置路径 → `fr_cli.conf.paths`（所有路径常量）
   - 命令注册 → `fr_cli.command.registry`（统一注册表）
   - 运行时状态 → `fr_cli.core.core.AppState`（DI 容器）

2. **向后兼容是必须的**
   - 旧路径首次启动自动迁移到新位置
   - 旧命令/旧模块保留为 deprecated alias
   - 测试基线 357 passed 不变

3. **TUI 优先于 CLI**
   - 终端支持时用 prompt_toolkit 完整 TUI
   - 不支持时（CI / HTTP）自动降级到 `input()`

4. **安全默认 + 显式 override**
   - 默认走 sec_* 安全检查
   - 仅在调用方明确说"用户已确认"时传 `skip_security=True`

## 2. 目录结构

```
fr_cli/
├── main.py                    # 主入口（TUI 主循环）
├── conf/
│   ├── paths.py               # 所有路径常量 + 旧路径迁移
│   ├── config.py              # 主配置读写
│   └── wizard.py              # 邮件/云盘/M365 配置向导
├── core/                      # 编排层（无业务逻辑）
│   ├── core.py                # AppState —— DI 容器
│   ├── chat.py                # 传统流式对话
│   ├── intent.py              # 意图判定
│   ├── thinking.py            # 思维模式
│   ├── stream.py              # 流式输出
│   ├── llm.py                 # 多模型客户端
│   ├── model_factory.py       # 模型工厂
│   ├── result.py              # Result 统一返回风格
│   ├── store.py               # JsonStore 持久化抽象
│   ├── usage.py               # LLM 用量统计
│   ├── recommender.py         # 功能推荐
│   └── sysmon.py              # 系统状态监控
├── ui/                        # 终端 UI
│   ├── ui.py                  # 颜色/宽度/动画
│   ├── prompt.py              # prompt_toolkit TUI
│   ├── banner.py              # 启动 banner
│   ├── splash.py              # 终端图片协议探测
│   └── ...
├── command/                   # 命令调度层
│   ├── registry.py            # 统一工具注册表（@register 装饰器）
│   ├── executor.py            # AI 回复解析 + 调度
│   ├── security.py            # 安全确认封装
│   └── registered/*.py        # 按类目拆分的工具实现
├── memory/                    # 记忆与历史
│   ├── history.py             # 手动保存的会话
│   ├── session.py             # 按日期自动存档
│   └── context.py             # 短期摘要
├── security/
│   └── security.py            # 四阶安全确认
├── lang/
│   ├── i18n.py                # T() 国际化
│   └── translations/          # 中文/英文翻译字典
├── weapon/                    # 武器库
│   ├── fs.py                  # VFS 沙盒
│   ├── mail.py / m365.py      # 邮件 / Microsoft 365
│   ├── web.py                 # 搜索 + 抓取
│   ├── cron.py                # 定时任务
│   ├── disk.py                # 云盘
│   ├── vision.py              # 多模态看图/画图
│   ├── launcher.py            # 本机应用启动
│   ├── dataframe.py           # Excel/CSV 读取
│   ├── mcp.py                 # MCP 外部神通
│   ├── network.py / remote.py # 网络探测 / 远程 SSH
│   ├── ocr.py / charts.py     # OCR / 图表
│   └── loader.py              # 工具描述加载
├── agent/                     # Agent 分身系统
│   ├── manager.py             # CRUD
│   ├── executor.py            # 执行
│   ├── client.py              # 本地/远程/内置 Agent 调用
│   ├── remote.py              # 远程 Agent 注册表
│   ├── server.py              # Agent HTTP REST API
│   ├── workflow.py            # 工作流引擎
│   ├── dispatch.py            # @name 前缀调度
│   ├── swarm.py / swarm_resolver.py  # 蜂群多 Agent 协作
│   ├── master.py              # MasterAgent 自我进化
│   ├── generator.py           # AI 自动生成 Agent
│   ├── shell_mode.py          # Shell 模式
│   ├── hermes.py / hermes_daemon.py  # Hermes 守护
│   ├── personality.py / skills.py    # 人设/技能
│   └── builtins/              # 内置 Agent
│       ├── local.py / remote.py / db.py / spider.py
│       ├── rag.py / stock.py
│       └── rag_watcher_daemon.py
├── dynamic_builder/           # 动态构建系统
├── gatekeeper/                # Gatekeeper 守护
├── repl/                      # REPL 命令与路由
│   ├── router.py              # 输入路由
│   ├── queue.py               # 对话队列
│   ├── bootstrap.py           # 启动引导
│   ├── actions.py             # e/r/u 快捷键
│   ├── commands.py            # 兼容层重导出
│   └── commands/*.py          # 各命令处理器
├── addon/
│   └── plugin.py              # 旧式 Plugin
└── breakthrough/
    └── update.py              # 远程更新
```

## 3. 数据流

### 3.1 一次普通对话

```
用户输入 (TUI prompt)
    ↓
main.py 主循环
    ↓
别名替换 / 命令路由 / @ Agent / 自然语言
    ↓
state.executor.handle_ai_chat()
    ↓
core/chat.py 组装 system prompt + 工具清单 + 上下文
    ↓
core/stream.py 流式调用 LLM
    ↓
command/executor.process_ai_commands 解析 + 执行
    ↓
registry.dispatch → handler → 返回结果
    ↓
多源信息汇总（如有）→ 再次 LLM
    ↓
回写到 state.messages
    ↓
更新 status bar / 输出到 TUI
```

### 3.2 命令调用

```
用户输入 "/cat foo.txt"
    ↓
main.py 路由到 _COMMAND_ROUTES
    ↓
_cmd_cat(state, parts)
    ↓
return state.executor.execute(cmd_str) 或 直接调用
    ↓
registry.dispatch → handler
    ↓
安全确认 (sec_read) → handler 执行 → 返回结果
    ↓
print 到 TUI
```

### 3.3 路径读取

```
任意模块需要读 ~/.fr_cli/xxx
    ↓
from fr_cli.conf.paths import XXX
    ↓
读取 paths.XXX 常量（已迁移后的新位置）
    ↓
如果新位置为空且旧位置有数据 → 触发 migrate() 自动搬运
    ↓
返回数据
```

## 4. 关键设计决策

### 4.1 为什么用 prompt_toolkit

参考 OpenClaw / Kimi-cli / OpenCode / Aider 都在用：
- 跨平台支持（Windows / macOS / Linux）
- 多行编辑 + 快捷键 + 补全 + 历史
- 纯 Python，约 150KB
- non-TTY 自动降级

### 4.2 为什么统一 ~/.fr_cli/ 根目录

早期曾散落在 ~/.zhipu_cli_*、~/.fr_cli_* 等位置，用户找文件困难。当前已统一为 ~/.fr_cli/。
现在：
- 所有配置统一在 `~/.fr_cli/` 下
- 按用途分子目录（mcp/, daemon/, rag/, master/, sessions/, ...）
- 首次启动自动迁移旧路径 → 新路径

### 4.3 为什么 AppState 是 DI 容器

避免全局状态散落：
- 所有子系统（vfs / mail / web / disk / security / mcp / master / ...）都挂在 state 上
- main.py / chat.py / agents / commands 共享同一个 state
- reinit_client 集中处理 client 重建

### 4.4 为什么 ToolRegistry 用装饰器

新增一个内置工具只需 1 行装饰器：

```python
@register(
    name="my_tool",
    description="...",
    params={"path": str},
    security="sec_read",
)
def _my_tool(deps, **kwargs):
    return Result.ok(result)
```

兼容旧写法 `(data, error)`，注册表会自动归一化为 `Result`。

注册表自动：
- 参数校验
- 安全确认
- 触发关键词
- 命令别名

## 5. 安全模型

| 防御点 | 实现 |
|--------|------|
| 路径沙盒 | `weapon/fs.py` VFS 路径 resolve + relative_to 精确判断 |
| 文件操作确认 | `command/security.py` 四阶确认（Y/A/F/N） |
| 插件沙盒 | `addon/plugin.py` 子进程 + isidentifier 校验 + 15s 超时 |
| Cron 注入 | `weapon/cron.py` shlex.split + shell=False |
| SSH 注入 | `agent/builtins/remote.py` paramiko.exec_command |
| SSRF | `weapon/web.py` _is_private_url |
| 邮件头注入 | `weapon/mail.py` 过滤 \r\n |
| 配置原子写入 | `conf/config.py` mkstemp + chmod 600 + os.replace |
| Agent HTTP | `agent/server.py` Bearer Token + 127.0.0.1 |
| Hermes 守护 | `agent/hermes_daemon.py` Bearer Token |
| ! shell 二次确认 | `main.py` peek_ai_commands + 用户确认 |
| 邮件正文 | `command/registry.py` <email_message> 标签 |
| Workflow 循环检测 | `agent/workflow.py` 依赖图 DFS（无 eval） |

## 6. 测试策略

- 基线 357 passed（持续维护，所有迁移需保持此基线）
- 集成测试：tests/test_integration_real.py 覆盖 AppState 初始化、命令执行、Agent 上下文
- Agent HTTP 服务：tests/test_agent_server.py
- 内置 Agent：tests/test_builtins.py
- 工具调用：tests/test_structured_tools.py

## 7. 性能与资源

- 启动 < 1s（无 provider 时）
- 启动时只加载必要的 client（其余按需创建）
- 缓存：state._client_cache 避免重复创建 LLM 客户端
- daemon 进程独立于主进程（fr-cli 退出后继续）

## 8. 扩展指南

### 8.1 新增一个内置工具

在 `command/registry.py` 末尾加：

```python
@register(
    name="my_tool",
    description="我的工具",
    params={"input": str},
    security="sec_read",
    aliases=["/mytool"],
)
def _my_tool(deps, **kwargs):
    return Result.ok(f"收到: {kwargs['input']}")
```

### 8.2 新增一个内置 Agent（@ 前缀）

在 `agent/builtins/` 下创建 `my_agent.py`：

```python
def handle_my_agent(user_input: str, state):
    # 你的逻辑
    pass
```

在 `agent/dispatch.py` 的 `BUILTIN_AGENTS` 字典中注册，并在 `repl/router.py` 中确保 `@` 前缀路由正确分发。

### 8.3 新增一个用户 Agent

让 AI 自动生成：
```
>>> /agent_create my_agent 你的需求描述
```

或者手动在 `~/.fr_cli/agents/my_agent/` 下放 agent.py：

```python
def run(context, **kwargs):
    # 你的逻辑
    return Result.ok(result)
```

### 8.4 新增配置文件路径

在 `conf/paths.py` 加：
```python
MY_NEW_FILE = ROOT / "my_new_file.json"
```

在 `conf/__init__.py` 同步 export。**所有模块都用 `from fr_cli.conf.paths import MY_NEW_FILE`**。
