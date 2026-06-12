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
   - 测试基线 118 passed 不变

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
│   ├── paths.py               # 【唯一】所有路径常量 + 旧路径迁移
│   ├── config.py              # 主配置读写
│   └── wizard.py              # 邮件/云盘配置向导
├── core/                      # 编排层（无业务逻辑）
│   ├── core.py                # AppState —— DI 容器
│   ├── chat.py                # handle_ai_chat：传统流式对话
│   ├── intent.py              # 意图判定
│   ├── thinking.py            # 思维模式（direct/cot/tot/react）
│   ├── stream.py              # 流式输出
│   ├── llm.py                 # 多模型客户端
│   ├── model_factory.py       # 模型工厂
│   ├── recommender.py         # 功能推荐
│   └── sysmon.py              # 系统状态监控
├── ui/
│   ├── ui.py                  # 颜色常量、清屏、宽度计算
│   ├── banner.py              # 【新】红色实心螃蟹启动画面
│   └── prompt.py              # 【新】prompt_toolkit TUI 输入面板
├── command/                   # 命令调度层
│   ├── registry.py            # 统一工具注册表（@register 装饰器）
│   ├── executor.py            # AI 回复解析 + 调度
│   └── security.py            # 安全确认封装
├── memory/                    # 记忆与历史
│   ├── history.py             # 手动保存的会话
│   ├── session.py             # 按日期自动存档
│   └── context.py             # 短期摘要
├── security/
│   └── security.py            # 四阶安全确认
├── lang/
│   └── i18n.py                # 中英文硬编码字典
├── weapon/                    # 武器库
│   ├── fs.py                  # VFS 沙盒
│   ├── mail.py                # IMAP/SMTP
│   ├── web.py                 # 搜索 + 抓取
│   ├── cron.py                # 定时任务（state_provider 化）
│   ├── disk.py                # 阿里云盘
│   ├── vision.py              # 多模态看图
│   ├── launcher.py            # 本机应用启动
│   ├── dataframe.py           # Excel/CSV 读取
│   ├── mcp.py                 # MCP 外部神通
│   └── loader.py              # 工具描述加载
├── agent/                     # Agent 分身系统
│   ├── __init__.py            # AGENTS_DIR re-export
│   ├── manager.py             # CRUD
│   ├── executor.py            # 执行
│   ├── generator.py           # AI 自动生成
│   ├── workflow.py            # 工作流引擎
│   ├── server.py              # Agent HTTP REST API
│   ├── client.py              # 远程 Agent 客户端
│   ├── remote.py              # 远程 Agent 注册表
│   ├── image.py               # 图片模型（合并自 image_and_parallel）
│   ├── parallel.py            # 并行执行
│   ├── context_files.py       # 项目上下文文件
│   ├── shell_mode.py          # Shell 模式
│   ├── master/                # MasterAgent 自我进化
│   │   ├── __init__.py
│   │   ├── core.py            # ReAct 主循环
│   │   ├── skills.py          # 技能（合并自 agent/skills.py）
│   │   ├── personality.py     # 个性（合并自 agent/personality.py）
│   │   ├── status.py          # 状态文件原子写入
│   │   └── prompts.py
│   ├── builtins/              # 内置 Agent
│   │   ├── _utils.py
│   │   ├── local.py           # @local（已 shlex 安全化）
│   │   ├── remote.py          # @remote
│   │   ├── spider.py          # @spider
│   │   ├── db.py              # @db（已 SQL 注入/多语句防护）
│   │   ├── rag.py             # @RAG
│   │   └── rag_watcher_daemon.py
│   └── _legacy/               # 旧模块（deprecated，保留兼容）
│       ├── hermes.py          # → master/skills.py
│       ├── hermes_daemon.py   # → daemon/
│       ├── personality.py     # → master/personality.py
│       ├── skills.py          # → master/skills.py
│       ├── image_and_parallel.py  # → image.py + parallel.py
│       ├── coding_helper.py   # → master/coding.py
│       ├── gateway.py         # → daemon/
│       ├── a2a.py             # 未使用，保留
│       ├── acp.py             # 未使用，保留
│       └── plugin_system.py   # 未使用，保留
├── daemon/                    # 【新】统一守护
│   ├── __init__.py
│   ├── manager.py             # 启动/停止/状态
│   ├── daemon.py              # 主循环
│   ├── cron.py                # 定时任务
│   ├── http.py                # HTTP 路由
│   └── token.py               # Bearer Token
├── repl/
│   ├── commands.py            # 主命令处理器
│   ├── slash.py               # / 命令专用
│   └── at.py                  # @ Agent 拦截
├── addon/
│   └── plugin.py              # 旧式 Plugin
├── breakthrough/
│   └── update.py              # 远程更新
└── 标记 deprecated 但保留的旧模块：
    ├── gatekeeper/ 整个目录  → 整合到 daemon/
    └── （其他迁移完成的）
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
    return result, None
```

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
| Workflow 表达式 | `agent/workflow_system.py` AST 白名单（无 eval） |

## 6. 测试策略

- 基线 118 passed / 19 failed（19 个失败是已存在的 provider 缺失，不归我修）
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
    return f"收到: {kwargs['input']}", None
```

### 8.2 新增一个内置 Agent（@ 前缀）

在 `agent/builtins/` 下创建 `my_agent.py`：

```python
def handle_my_agent(user_input: str, state):
    # 你的逻辑
    pass
```

在 `repl/commands.py` 的 main.py 路由区加 elif。

### 8.3 新增一个用户 Agent

让 AI 自动生成：
```
>>> /agent_create my_agent 你的需求描述
```

或者手动在 `~/.fr_cli/agents/my_agent/` 下放 agent.py：

```python
def run(context, **kwargs):
    # 你的逻辑
    return result, None
```

### 8.4 新增配置文件路径

在 `conf/paths.py` 加：
```python
MY_NEW_FILE = ROOT / "my_new_file.json"
```

在 `conf/__init__.py` 同步 export。**所有模块都用 `from fr_cli.conf.paths import MY_NEW_FILE`**。
