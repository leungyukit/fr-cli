# 凡人打字机 (fr-cli) — Agent 指南

> 本文档面向 AI 编码助手。假设读者对该项目一无所知，所有信息均基于实际代码与文件内容，不做臆测。

---

## 项目概览

**凡人打字机 (fr-cli)** 是一个基于智谱 AI（Zhipu AI / GLM）的交互式终端工具。它以 Python 3 编写，提供 REPL 式的命令行界面，让用户在终端中与 GLM 大模型对话，并集成了文件系统沙盒、网页搜索、邮件、网盘、定时任务、图片生成与视觉识别等扩展能力。

项目大量使用中文修仙/玄幻术语作为内部命名与注释风格（如“洞府”指目录、“法宝”指插件、“轮回”指会话、“结界”指定时任务）。

- **仓库路径**：`/Users/liangyj/workspace/fr-cli`
- **主包目录**：`fr_cli/`
- **PyPI 包名**：`fr-cli`
- **主要语言**：Python 3.13（兼容 Python 3.8+）
- **文档与注释主要语言**：中文

---

## 技术栈

| 层级 | 技术/依赖 |
|---|---|
| 运行时 | Python 3.13（虚拟环境 `.venv/` 已创建） |
| AI SDK | `zhipuai>=2.0.0`（智谱）, `openai>=1.0.0`（兼容 DeepSeek/Kimi/Qwen/StepFun/MiniMax/讯飞/豆包/小米MiMo） |
| 默认模型 | `glm-4-flash`（智谱）、`deepseek-chat`（DeepSeek）、`moonshot-v1-8k`（Kimi）等，支持 9 大道统 |
| 多模型支持 | zhipu / zhipu-coding / openai / deepseek / kimi / qwen / stepfun / stepfun-step-plan / minimax / minimax-token-plan / spark / doubao / mimo / mimo-token-plan |
| HTTP / 网页 | `requests` |
| 数据 / Excel | `pandas`、`openpyxl` |
| 数据库 | `pymysql`、`psycopg2-binary`、`pyodbc`、`oracledb` |
| 远程 SSH | `paramiko` |
| 爬虫 | `requests`、`selenium` |
| RAG 向量库 | `chromadb` |
| RAG 嵌入模型 | `sentence-transformers` (all-MiniLM-L6-v2) |
| 文件监控 | `watchdog` |
| 云存储 | `bypy`、`aligo`、`msal` |
| 邮件 | 标准库 `imaplib`、`smtplib`、`email` |
| 并发 | `threading.Timer`（定时任务）、后台守护线程（RAG 文件监控） |
| 配置持久化 | JSON 文件（用户主目录下） |
| 插件执行 | `subprocess.run`（子进程隔离，15 秒超时） |
| UI | ANSI 转义码、终端动画、颜色常量 |
| 打包 | `pyproject.toml` + `setuptools`（现代 Python 标准） |
| 测试 | `pytest`，473 个测试全部通过 |

---

## 项目结构

```
fr-cli/
├── pyproject.toml              # 现代 Python 打包配置
├── README.md                   # PyPI 展示用 README
├── MANIFEST.in                 # 打包数据文件清单
├── AGENTS.md                   # 本文档：Agent 指南
├── fr_cli/                     # 主应用包
│   ├── main.py                 # 核心入口：REPL 循环、AI 交互编排
│   ├── __init__.py             # 包初始化，含 __version__
│   ├── WEAPON.MD               # 法宝图谱：人类可读工具清单（不再参与程序逻辑）
│   ├── requirements.txt        # 依赖清单
│   ├── README.md               # 项目内部说明
│   ├── agent/                  # Agent 分身系统
│   │   ├── __init__.py         # Agent 目录常量
│   │   ├── manager.py          # Agent 生命周期管理（创建/删除/列出/读写 MD 设定）
│   │   ├── executor.py         # Agent 执行器（加载 persona/memory/skills 并调用 run）
│   │   ├── client.py           # 本地/远程/内置 Agent 统一调用入口
│   │   ├── remote.py           # 远程 Agent 注册表
│   │   ├── dispatch.py         # @name 前缀调度器
│   │   ├── workflow.py         # 工作流引擎（解析 workflow.md，步骤调度，模板变量）
│   │   ├── server.py           # HTTP 服务（将 Agent 发布为 REST API）
│   │   ├── master.py           # MasterAgent 主类骨架（mixin 组装 + 状态管理 toggle/is_enabled/status）
│   │   ├── master_storage.py   # MasterAgent 存储层（配置路径、默认值、文件 I/O、错误分类）
│   │   ├── master_prompt.py    # MasterAgent 默认 system prompt 模板（中文/英文/规划/反思）
│   │   ├── master_loop.py      # MasterAgent ReAct 主循环 mixin（handle/_extract_tool_calls/_execute_tool）
│   │   ├── master_prompt_builder.py  # MasterAgent Prompt 组装 mixin（_build_tools_desc/_build_system_prompt/_detect_artifacts）
│   │   ├── master_reflect.py   # MasterAgent 反思进化 mixin（_record_interaction/_reflect_and_evolve 等）
│   │   ├── generator.py        # AI 自动生成 Agent
│   │   ├── shell_mode.py       # Shell 模式
│   │   ├── hermes/             # Hermes 后台自治任务引擎（拆包）
│   │   │   ├── engine.py       #   HermesEngine 统一入口
│   │   │   ├── managers.py     #   PersistentTaskManager / PersistentGoalTracker / PersistentReviewQueue
│   │   │   ├── models.py       #   数据模型
│   │   │   └── scheduler.py    #   后台轮询调度器
│   │   ├── hermes_daemon.py         # Hermes 调度守护（449 行）
│   │   ├── hermes_manager.py        # Hermes 独立子进程管理
│   │   ├── hermes_daemon_process.py # Hermes 独立守护进程入口
│   │   ├── review_queue.py     # 后台产物审核队列（独立模块，被 Hermes 调用）
│   │   ├── artifact_detector.py # AI 回复产物检测器（插件/Agent 自动检测，支持交互/审核队列）
│   │   ├── swarm.py            # 蜂群统一调度引擎
│   │   ├── swarm_resolver.py   # 蜂群任务解析器
│   │   └── builtins/           # 内置 Agent（local/remote/db/spider/rag/stock）
│   │       └── spider/         #   @spider 智能爬虫（拆包：deps/analyzer/fetcher/crawler/evasion/memory）
│   ├── repl/
│   │   ├── router.py           # 输入路由与分发
│   │   ├── queue.py            # 对话队列与连续输入
│   │   ├── bootstrap.py        # 启动引导
│   │   ├── actions.py          # e/r/u 快捷键处理
│   │   └── commands/           # REPL 命令处理器（从 main.py 拆分，架构解耦）
│   │       ├── _common.py      #   公共工具与基类
│   │       ├── base.py / agent.py / cron.py / fs.py ...  # 各分类命令处理器
│   │       ├── config/         #   配置类（/model, /key, /lang, /autonomous 等，按职责拆为 key/model/misc 三个子模块）
│   │       └── system/         #   系统级（/status, /hermes, /agent_server, /autostart 等 7 个子模块）
│   ├── addon/
│   │   └── plugin.py           # 插件进化引擎：扫描、落盘、子进程隔离执行（runpy+json.dumps）
│   ├── breakthrough/
│   │   └── update.py           # 自动更新：查询远程版本、下载 ZIP、备份替换、重启
│   ├── dynamic_builder/        # 动态构建系统（按需安装依赖并生成工具）
│   └── gatekeeper/             # Gatekeeper 守护
│   ├── command/
│   │   ├── executor.py         # 命令执行引擎：解析 AI 调用标记并调度到注册表
│   │   ├── registry.py         # 统一工具注册表：装饰器注册、参数校验、安全中间件
│   │   ├── security.py         # 四阶安全确认管理器（封装 sconfirm/fconfirm）
│   │   ├── registered/         # 按类目拆分的工具注册文件
│   │   └── __init__.py
│   ├── conf/
│   │   ├── paths.py            # 路径常量 + 旧路径迁移
│   │   ├── config.py           # 配置读写与首次运行引导
│   │   └── wizard.py           # 邮件/云盘/M365 配置向导
│   ├── core/
│   │   ├── core.py             # AppState 全局状态容器（DI 容器）
│   │   ├── chat.py             # 传统流式对话编排
│   │   ├── intent.py           # 用户意图判定
│   │   ├── thinking.py         # 思维模式引擎（CoT/ToT/ReAct/Plan）
│   │   ├── plan.py             # 计划模式
│   │   ├── stream.py           # 流式输出与代码块高亮
│   │   ├── llm.py              # 多模型客户端抽象
│   │   ├── model_factory.py    # 模型工厂
│   │   ├── result.py           # 统一返回风格容器
│   │   ├── store.py            # JsonStore 持久化抽象
│   │   ├── usage.py            # LLM 用量统计
│   │   ├── recommender.py      # 功能推荐引擎
│   │   └── sysmon.py           # 系统状态监控
│   ├── lang/
│   │   ├── i18n.py             # 国际化核心（T() 函数）
│   │   └── translations/       # 翻译数据（已模块化拆分）
│   │       ├── zh.py           # 中文翻译字典
│   │       └── en.py           # 英文翻译字典
│   ├── memory/
│   │   ├── history.py          # 会话历史保存、加载、删除、导出 Markdown
│   │   ├── session.py          # 按日期自动存档会话
│   │   └── context.py          # 上下文记忆：最近 5 轮摘要注入 system prompt
│   ├── security/
│   │   └── security.py         # 四阶安全确认引擎（Y/A/F/N）
│   ├── ui/
│   │   ├── ui.py               # 终端颜色常量、清屏、显示宽度计算、启动动画
│   │   ├── prompt/             # prompt_toolkit TUI 输入（拆包：status/completer/tui/fallback）
│   │   ├── banner.py           # 启动 banner
│   │   ├── buddha.py           # ASCII 佛像启动画面（禅定印，25 行纯字符构图）
│   │   └── markdown.py         # 轻量级 Markdown → ANSI 终端渲染器
│   └── weapon/                 # 武器库/扩展子系统
│       ├── cron.py             # 定时任务（CronManager 类，threading.Timer）
│       ├── disk.py             # 云盘适配器
│       ├── fs.py               # 虚拟文件系统 VFS（路径沙盒、防 ../ 逃逸）
│       ├── loader.py           # 工具加载器（从注册表动态生成，兼容旧 WEAPON.MD 格式）
│       ├── mail.py / m365.py   # IMAP/SMTP 邮件 / Microsoft 365
│       ├── vision.py           # 图片生成（CogView）与多模态消息构造（GLM-4V）
│       ├── web.py              # 百度搜索抓取与网页正文抽取
│       ├── network.py          # 网络探测
│       ├── remote.py           # 远程 SSH 客户端
│       ├── launcher.py         # 本地应用启动器（跨平台调用浏览器/办公/通讯等）
│       ├── dataframe.py        # 数据卷轴读取器（Excel / CSV 读取与分析）
│       ├── ocr.py              # OCR 文字识别
│       ├── charts.py           # 图表生成
│       └── mcp.py              # MCP 外部神通客户端（stdio/SSE 连接、工具发现与调用）
├── release/                    # 可分发包目录
│   ├── fr-cli-installer        # macOS 可执行安装程序
│   ├── fr-cli-install          # 跨平台 Python 安装脚本
│   ├── fr-cli-install.sh       # macOS/Linux 安装脚本
│   ├── fr-cli-install.bat      # Windows 安装脚本
│   ├── fr_cli-2.0.0-py3-none-any.whl
│   └── fr-cli-README.md
├── tests/
│   ├── test_a2a_and_providers.py   # StepFun 提供商测试（A2A 协议已移除）
│   ├── test_integration_real.py    # 集成测试（配置/LLM/Agent/工作流）
│   ├── test_master_prompt_fix.py   # MasterAgent Prompt 格式修复测试
│   ├── test_model_config.py        # 模型配置与 LLM 客户端测试
│   ├── test_new_features.py        # 新特性测试（图片/并行/工作流）
│   ├── test_new_providers.py       # 新提供商测试（MiniMax/Kimi）
│   └── run_live_demo.py
├── structure.py                # 打包脚本（旧版，与当前源码不同步）
└── .venv/                      # Python 3.13 虚拟环境
```

---

## 如何运行

### 开发模式

```bash
pip install -e .
fr-cli
```

### 批处理 / 非交互模式

```bash
# 执行单条 slash 命令后退出
fr-cli -c "/model current"
fr-cli -c "/ls"

# 单次 AI 对话后退出
fr-cli "请总结 README.md"
fr-cli -p "Python 如何读取 JSON？"

# 从文件或标准输入读取提示词
cat article.txt | fr-cli -s
fr-cli -f prompt.txt

# 静默模式（跳过启动 banner）
fr-cli -q -c "/model current"
```

### 测试

```bash
python -m pytest tests/ -v
```

### 独立运行更新模块

```bash
python fr_cli/breakthrough/update.py check
python fr_cli/breakthrough/update.py run
```

### Docker 部署

项目已内置 `Dockerfile` 与 `docker-compose.yml`，支持在容器环境中运行。

```bash
# 构建镜像
docker build -t fr-cli .

# 运行（交互式终端，需挂载配置卷以持久化数据）
docker run -it \
  -v ~/.fr_cli:/root/.fr_cli \
  -v $(pwd):/app/workspace \
  fr-cli

# 或使用 Docker Compose（推荐）
docker compose up fr-cli
```

> 注意：首次运行需在交互中输入 Zhipu API Key，配置会自动写入挂载的配置文件。

---

## 代码组织与模块划分

### 架构模式：分层架构 + 统一注册表 + 依赖注入

```
┌─────────────────────────────────────────────┐
│  UI / REPL 层    (main.py)                   │  输入输出、启动动画、状态展示
├─────────────────────────────────────────────┤
│  编排 / 状态层   (core/core.py → AppState)   │  DI 容器、消息组装、AI 调用编排
├─────────────────────────────────────────────┤
│  命令调度层      (command/registry.py)       │  统一工具注册表、参数校验、安全中间件
├─────────────────────────────────────────────┤
│  解析与执行层    (command/executor.py)       │  AI 回复解析、调用标记提取、调度注册表
├─────────────────────────────────────────────┤
│  能力实现层      (weapon/ + addon/)          │  纯净业务逻辑，返回 Result（兼容 (result, error) 解包）
├─────────────────────────────────────────────┤
│  基础设施层      (conf/ + memory/ + security/ + core/store.py)│ 配置、持久化、安全、国际化
└─────────────────────────────────────────────┘
```

#### 核心模块职责

- **`command/registry.py`**：统一工具注册表 —— 单一真相源
  - `@register(name, description, params, security, aliases, triggers)` 装饰器注册工具
  - `dispatch()`：结构化调用（AI 生成的 `【调用：...】`）
  - `dispatch_cmd()`：命令字符串调用（用户输入的 `/cmd args`）
  - 自动参数校验、安全确认中间件、触发关键词管理
  - **新增一个内置工具只需在此文件注册一个 handler**

- **`command/executor.py`**：轻量解析与调度器（~150 行）
  - `invoke_tool(tool_name, kwargs)` → 调用 `registry.dispatch()`
  - `execute(cmd_str)` → 调用 `registry.dispatch_cmd()`
  - `process_ai_commands(ai_response)`：解析三种格式并执行

- **`core/core.py`**：`AppState` —— 本命元神 / DI 容器
  - 统一管理配置、子系统实例（ZhipuAI、VFS、MailClient、WebRaider、CloudDisk、SecurityManager）
  - 持有命令执行引擎 `executor` 与用量统计 `usage`
  - 提供状态变更方法（`update_model()`、`update_key()`、`save_cfg()` 等）
  - `main.py` 通过 `AppState` 访问所有运行时状态，不再使用局部变量

- **`core/store.py`**：`JsonStore` —— 统一 JSON 持久化抽象
  - 原子写、默认回退、文件权限控制、线程安全
  - 已用于 `usage.json`、`context.json`、Agent `progress.json`、`memory/history`、`memory/session`、`dynamic_builder/registry.json`（这些是运行时状态/数据，不是配置）
  - **配置类**数据已统一收敛到 `config.json` 的命名空间（见配置系统章节），用 `conf/config.py:load_namespace/save_namespace` 访问

- **`core/usage.py`**：`UsageTracker` —— LLM 调用用量统计

- **`core/result.py`**：`Result` —— 统一错误返回风格容器
  - 替代 `(result, error)` / `(success, message)` / 抛异常 / 静默返回 等多种风格
  - 新增代码优先使用 `Result.ok(data)` / `Result.fail(error)`，旧接口可用 `to_tuple()` / `from_tuple()` 兼容
  - `command/registry.py`、`command/executor.py`、VFS、网络/邮件/云盘/远程、Agent 执行链路（client/executor/workflow/dispatch）、更新模块（breakthrough/update.py）、Agent HTTP 服务（agent/server.py）等已迁移为 `Result` 风格
  - 自动记录 provider/model/tokens/cost
  - 持久化到 `~/.fr_cli/usage.json`，支持 `/usage [days]` 汇总查询

- **`weapon/loader.py`**：工具信息加载器
  - 从注册表动态生成 AI 可用的工具列表
  - 保持与旧 `WEAPON.MD` 格式的兼容性（`load_weapon_md()` 返回旧结构）
  - `WEAPON.MD` 本身仍保留为人类可读文档，但不再被程序解析

### 模块交互简图

```
main.py
├── core.core           → AppState（DI 容器，聚合所有子系统）
├── core.usage          → ~/.fr_cli/usage.json（LLM 用量统计）
├── core.store          → JsonStore 统一 JSON 持久化
├── core.result         → Result 统一错误返回风格
├── core.stream         → 流式调用 ZhipuAI，代码高亮输出
├── core.recommender    → 功能推荐
├── core.thinking       → 思维模式引擎（CoT/ToT/ReAct）
├── command.executor    → 解析 AI 回复，调度注册表（动态构建依赖）
├── repl.commands       → 40 个命令处理器
├── memory.history      → ~/.fr_cli/sessions/manual/ (JSON)
├── memory.context      → ~/.fr_cli/context.json（会话摘要）
├── memory.session      → ~/.fr_cli/sessions/auto/ (按日期自动存档)
├── addon.plugin        → ~/.fr_cli/plugins/ (*.py)
├── weapon.loader       → 从注册表生成工具描述
├── weapon.cron         → CronManager（threading.Timer）
├── agent.master        → ~/.fr_cli_master/ (记忆与进化)
└── breakthrough.update → 远程更新
```

### 关键数据流（一次普通对话）

1. `main.py` 通过 `AppState` 获取所有运行时状态。
2. 检查 `state.master_agent.enabled`：
   - 若启用 → 由 `MasterAgent.run()` 接管，进入 ReAct 循环
   - 若禁用 → 继续传统流式对话流程
3. 组装 `messages`（system prompt + 工具清单 + 上下文摘要 + 历史）。
4. 通过 `should_inject_tools()` 判定是否需要注入工具信息。
5. 调用 `stream_cnt()` → 逐 token 输出到 stdout。
6. 收到完整回复后，`executor.process_ai_commands()` 解析调用标记：
   - `【调用：tool_name({"参数": "值"})】` → `registry.dispatch()` → 执行 handler
   - `【命令：/command args】` → `registry.dispatch_cmd()` → 执行同一 handler
7. 自动执行提取的命令，打印结果，并将结果回写到 `messages`。
8. 再次调用 AI 生成最终回复（命令标记从显示文本中清除）。
9. 显示 token 统计，并将用量（provider/model/tokens/cost）持久化到 `~/.fr_cli/usage.json`；显示功能推荐；若检测到代码块则提示"是否祭炼为法宝"。
10. 提取最近 5 轮对话，生成摘要，持久化到 `~/.fr_cli/context.json`。
11. 自动存档：若首次输入则创建 `~/.fr_cli/sessions/auto/YYYY-MM-DD_NN.json`，否则增量更新。

---

## Agent 分身系统

### 设计目标

Agent 分身系统允许用户创建独立的 AI Agent（分身），每个 Agent 拥有独立的：
- **persona.md** —— 角色设定 / 系统提示词
- **memory.md** —— 长期记忆（可读写）
- **skills.md** —— 技能说明（供 AI 参考）
- **agent.py** —— 可选的自定义 Python 执行逻辑（必须实现 `run(context, **kwargs)`）
- **workflow.md** —— 可选的工作流定义（多步骤编排）
- **config.json** —— 可选的专属模型配置（provider / model / key），Agent 执行时自动切换为该模型

Agent 存储在 `~/.fr_cli/agents/<name>/` 目录下。

### 创建 Agent 的四种方式

1. **AI 自动生成**：`/agent_create <name> <description>` —— 调用大模型生成完整 Agent（persona + skills + code + workflow），创建完成后可通过 `/agent_run`、`@name` 或让大模型调用 `agent_call` 使用
2. **从已有代码铸造**：`/agent_forge <name>` —— 从历史消息中提取最近一段包含 `def run(context, **kwargs)` 的 Python 代码，直接保存为 Agent
3. **自动检测提示**：当 AI 回复中包含 `def run(context, **kwargs)` 和 `\`\`\`python` 代码块时，程序自动弹出提示，输入名称即可保存
4. **手动创建**：直接在 `~/.fr_cli/agents/<name>/` 目录下创建 `agent.py`（必须包含 `run(context, **kwargs)` 入口），可选补充 `persona.md`、`skills.md`、`workflow.md`

> **插件 vs Agent 分身的区分**：包含 `def run(args='')` 的代码会被识别为**插件**（保存到 `~/.fr_cli/plugins/`），包含 `def run(context, **kwargs)` 的代码会被识别为 **Agent 分身**（保存到 `~/.fr_cli/agents/`）。

### 模块职责

- **`agent/manager.py`** —— 分身掌管者
  - `create_agent_dir(name)`：开辟 Agent 洞府
  - `list_agents()`：列出所有分身
  - `delete_agent(name)`：抹除分身
  - `load_persona/memory/skills(name)`：读取设定
  - `save_persona/memory/skills(name, content)`：写入设定
  - `load_agent_config(name)` / `save_agent_config(name, data)`：读取/写入专属模型配置 `config.json`
  - `load_agent_module(name)`：动态加载 `agent.py`

- **`agent/executor.py`** —— 分身执行器
  - `run_agent(name, state, **kwargs)`：执行单个 Agent
  - `delegate_to_agent(name, state, pipeline_input, **kwargs)`：管道化委托（前一 Agent 输出作为后一输入）
  - `run_multi_agent(names, state, initial_input, **kwargs)`：多 Agent 流水线协作

- **`agent/dispatch.py`** —— `@agent_name` 调度器
  - `dispatch_agent_call(state, text)`：解析 `@name 任务` 并调用 `run_agent()` 执行
  - 在 REPL 主循环中拦截以 `@` 开头的输入，实现“@name 任务”一键召唤

- **`agent/workflow.py`** —— 工作流引擎
  - `load_workflow(name)` / `save_workflow(name, content)`：读写 workflow.md
  - `parse_workflow(text)`：解析 Markdown 格式工作流为步骤列表
  - `run_workflow(name, state, user_input, **kwargs)`：按步骤执行工作流
  - 支持模板变量：`{{step1.result}}`、`{{user_input}}`、`{{agent.persona}}` 等

- **`agent/server.py`** —— HTTP 服务（分身对外接口）
  - `AgentHTTPServer(state, host, port)`：HTTP 守护线程
  - 提供 REST API：`GET /agents`、`GET /agents/<name>`、`POST /agents/<name>/run`、`POST /agents/<name>/workflow`
  - 零额外依赖（标准库 `http.server`）

### Agent 模型绑定

每个独立 Agent 可配置专属大模型，执行时自动切换，不影响全局默认模型。配置持久化在 `~/.fr_cli/agents/<name>/config.json` 中。

**命令：**
```
>>> /agent_model my_agent                    # 查看当前配置
>>> /agent_model my_agent deepseek:deepseek-chat   # 设置专属模型
>>> /agent_model my_agent --key sk-own-key   # 设置独立 API Key（可选）
>>> /agent_model my_agent clear              # 清除配置，恢复全局默认
```

**config.json 格式：**
```json
{
    "provider": "deepseek",
    "model": "deepseek-chat",
    "key": ""
}
```

- `provider` + `model`：指定道统和模型（两者均非空时生效）
- `key`：可选的独立 API Key；若为空，回退到全局 `providers` 中对应道统的 Key
- Agent 代码中通过 `context["provider"]` 和 `context["model"]` 可感知当前绑定的道统

### 调用 Agent 分身的方式

创建 Agent 后，有三种调用方式：

1. **命令行调用**
   ```
   >>> /agent_run my_agent 请帮我总结 README.md
   ```

2. **@ 前缀快捷调用（REPL）**
   ```
   >>> @my_agent 请帮我总结 README.md
   🧙 正在召唤 Agent [my_agent]...
   ...
   ```
   主循环会拦截以 `@` 开头的输入，解析 Agent 名称和任务后直接进入 Agent 执行器，不会当作普通对话发送给大模型。

3. **让大模型作为工具调用**
   当用户请求适合交由某个 Agent 处理时，大模型会在 system prompt 的工具列表中看到可用的 Agent 列表，并输出：
   ```
   【调用：agent_call({"name": "my_agent", "user_input": "请帮我总结 README.md"})】
   ```
   系统自动执行该调用，并将结果回写给大模型生成最终回答。

### 蜂群协作（Swarm）

蜂群功能允许同时调用多个**任务单元**协作处理任务，支持三种模式。每个任务单元可以是：
- 自定义 Agent 分身
- 内置 Agent（`@local` / `@remote` / `@db` / `@spider` / `@RAG` / `@stock`）
- 注册表工具（`search_web` / `read_file` / `ocr_recognize` 等）
- 任意 `/` 命令
- MCP 外部工具
- 自定义插件

**任务名称格式：**
```
agent:myagent              # 自定义/远程 Agent
@local 或 builtin:local    # 内置 Agent
tool:search_web            # 注册表工具
cmd:/web 搜索词            # 命令字符串（/ 开头也可自动识别）
mcp:fs/read_file {"path": "/tmp/a.txt"}  # MCP 工具
plugin:myplugin            # 自定义插件
```

无显式前缀时自动推断优先级：Agent > 内置 Agent > 插件 > 工具 > 命令。

1. **并行模式（parallel）**
   多个任务同时独立处理同一任务，互不干扰。
   ```
   >>> /swarm parallel coder,reviewer 帮我检查这段代码
   >>> /swarm parallel @local,tool:search_web 分析项目并搜索相关资料
   ```

2. **议会模式（council）**
   多个任务分别给出结果，再由大模型综合汇总成最终结论。
   ```
   >>> /swarm council planner,coder,reviewer 设计一个用户登录模块
   >>> /swarm council @stock,@db 综合分析某只股票和相关财务数据
   ```

3. **流水线模式（pipeline）**
   多个任务串联执行，前一个任务的输出作为后一个任务的输入。
   ```
   >>> /swarm pipeline planner,coder 设计并实现一个快速排序
   >>> /swarm pipeline tool:search_web,cmd:/write report.md 搜索并保存报告
   ```

大模型调用方式：
```
【调用：swarm_run({"mode": "council", "names": ["planner", "coder"], "user_input": "设计登录模块"})】
```

### 动态构建（Dynamic Builder）

fr-cli 支持根据用户需求**自主安装依赖并动态生成工具**，生成后的工具立即注册到命令注册表，可供用户和 AI 调用。

**触发方式：**

```bash
# 手动触发
>>> /build 生成一个二维码识别工具
>>> /build 把图片转换成 ASCII 艺术
>>> /build 查询 Hacker News 热榜

# AI 自动触发
>>> 帮我生成一个二维码
【调用：dynamic_build({"requirement": "生成一个二维码识别工具"})】
```

**管理已构建工具：**

```bash
>>> /build list
>>> /build del qr_tool
```

**工作流程：**

1. **需求规划**：LLM 判断需求是否已被现有能力覆盖；若未覆盖，输出构建计划（工具名、依赖、参数、别名、触发词）。
2. **依赖安装**：自动检查并提示安装所需的 `pip` 包，默认需要用户确认。
3. **代码生成**：LLM 生成包含 `run(deps, **kwargs)` 入口的 Python 代码。
4. **持久化与注册**：代码保存到 `~/.fr_cli/dynamic_tools/<name>.py`，元数据写入 `registry.json`，并立即注册到 `ToolRegistry`。
5. **自动加载**：fr-cli 启动时自动加载所有已构建的工具。

**代码约定：**

- 动态工具必须包含 `def run(deps, **kwargs)` 函数
- `deps` 包含：`vfs`, `mail_c`, `web_c`, `disk_c`, `plugins`, `lang`, `security`, `cfg`, `client`, `model_name`, `mcp`
- 返回 `Result`，其中 `Result.error` 为 `None` 或错误字符串（仍兼容 `(result, error)` 解包）
- `breakthrough/update.py` 与 `agent/server.py` 已加入 Result 化，HTTP 接口统一返回 `{"result": ..., "error": ...}`
- 第三方依赖缺失时，应在函数内部捕获 `ImportError` 并返回安装提示

**相关文件：**

- `fr_cli/dynamic_builder/planner.py` — 需求规划
- `fr_cli/dynamic_builder/dependency_manager.py` — 依赖检查/安装
- `fr_cli/dynamic_builder/code_generator.py` — 代码生成
- `fr_cli/dynamic_builder/registry_manager.py` — 持久化与注册
- `fr_cli/dynamic_builder/runner.py` — 主流程编排
- `fr_cli/repl/commands/build.py` — `/build` 命令
- `fr_cli/command/registered/dynamic_build.py` — `dynamic_build` AI 工具

### 内置 Agent 使用指南

**@local — 本地系统操作**
```
>>> @local 查看当前目录下最大的10个文件
🧙 正在分析本地操作...
建议命令: find . -type f -exec ls -lh {} + | sort -k5 -rh | head -10
是否执行? [Y/n]: Y
```

**@remote — 远程 SSH 操作**
```
>>> @remote myserver 查看磁盘空间
🧙 正在为 [myserver](Linux) 生成远程命令...
建议命令 (myserver): df -h
是否执行? [Y/n]: Y
```
- 首次使用自动启动配置向导，配置文件：`~/.fr_cli/remote/hosts.json`

**@spider — 智能网页爬虫**
```
>>> @spider https://example.com 2
🕷️ 开始爬取: https://example.com | 深度: 2
爬取完成 | 成功: 15 个页面 | 保存目录: web_20240115/
```
- 依赖: `pip install requests selenium`

**@db — 数据库智能助手**
```
>>> @db mydb 查询最近7天注册用户
📊 正在分析 Schema...
生成 SQL: SELECT COUNT(*) FROM users WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY);
是否执行? [Y/n]: Y
返回 1 行: {'COUNT(*)': 342}
```
- 支持：MySQL / PostgreSQL / SQL Server / Oracle
- 配置文件：`~/.fr_cli/database.json`

**@RAG — 本地知识库问答**
```
>>> @RAG 项目的部署流程是什么
📚 正在同步知识库...
🔍 正在检索知识库并生成回答...
```
- 向量库：ChromaDB（嵌入式 `PersistentClient`，自动启动，无需单独服务）

**@stock — 股票/量化交易助手**
```
>>> @stock 查询茅台股价
🧙 正在分析股票数据...
贵州茅台 当前价格 ...

>>> @stock 买入 600519 1500.00 100
模拟交易确认: 动作=BUY 代码=600519.SH 数量=100 价格=1500.00
是否执行? [y/N]: y
✅ 模拟交易已记录
```
- 数据源：akshare（免 key）、麦蕊 API（需 token）、tushare（需 token）
- 交易能力：当前仅提供模拟交易记录，真实交易 API 需自行扩展
- 配置命令：
  - `/stock_config setup` — 交互式配置向导
  - `/stock_config source akshare|mairui|tushare|trade`
  - `/stock_config key mairui <key>` / `/stock_config token tushare <token>`
- 嵌入模型：all-MiniLM-L6-v2（向量检索，取 top-8 片段）
- 综合生成：将检索到的片段一次性交给大模型，由其综合回答并标注来源
- 配置命令：`/rag_dir <目录路径>` — 设置目录并首次同步
- 手动同步：`/rag_sync [路径]` — 立即向量化新文件/更新文件
- 独立守护进程：`/rag_watch start [目录] [--interval N]` — 启动持久化后台监控进程
  - `/rag_watch stop` — 停止守护进程
  - `/rag_watch status` — 查看守护进程状态
  - `/rag_watch log [--lines N]` — 查看守护进程日志
- 监控模式说明：
  - 内置模式（`/rag_dir` 后自动启动）：daemon 线程，fr-cli 退出后终止
  - 独立模式（`/rag_watch start`）：系统级子进程，脱离终端，日志写入 `~/.fr_cli/rag/watcher.log`

### MasterAgent 自我进化主控

**设计目标**：一个类似 OpenClaw 的中央控制器。启用后接管所有普通对话（`/` 命令、`!` shell、`@` 前缀仍保持原有逻辑），通过 ReAct 循环自主调用工具，每 10 次交互自动反思并进化 prompt。

**存储位置**：`~/.fr_cli/master/`

**配置文件体系（有漏即补）**：

| 文件 | 类型 | 说明 | 默认内容 |
|------|------|------|----------|
| `persona.md` | 文本 | 人设文件，用户可自定义系统人设，覆盖默认 prompt | 核心职责 + 执行原则 |
| `skills.md` | 文本 | 技能装备文件，描述特殊能力与高级用法 | 高级规划 + 自我进化 + 状态感知 |
| `memory.json` | JSON | 交互记忆，记录每次工具调用的成功/失败 | `{"interactions": []}` |
| `evolution.json` | JSON | 进化记录，prompt 追加 + 成功/失败模式统计 | `{"success": [], "failure": [], "prompt_addon": ""}` |
| `session.json` | JSON | 会话状态，当前任务 + 任务历史 + 上下文笔记 | `{"current_task": null, "task_history": [], "context_notes": ""}` |
| `status.json` | JSON | 状态文件，启用状态 + 统计 + 时间戳 | `{"enabled": false, "total_interactions": 0, "evolution_count": 0}` |

首次初始化时，`_ensure_all_master_files()` 会自动检查并补全缺失的默认配置文件。

**核心类**：`agent/master.py` 中的 `MasterAgent`（通过 mixin 组装，行为方法分布在三个独立 mixin 模块中）

**文件分布**：

| 文件 | 职责 |
|------|------|
| `master.py` | 主类骨架：`__init__`、状态管理 `toggle` / `is_enabled` / `status`、mixin 组装 |
| `master_storage.py` | 存储层：配置文件路径、默认值、文件 I/O、错误分类 `_classify_error`、`_ensure_all_master_files` |
| `master_prompt.py` | 默认 system prompt 模板（中文/英文/规划/反思） |
| `master_loop.py` | ReAct 主循环 mixin：`handle` / `_extract_tool_calls` / `_execute_tool` |
| `master_prompt_builder.py` | Prompt 组装 mixin：`_build_tools_desc` / `_build_system_prompt` / `_detect_artifacts` |
| `master_reflect.py` | 反思进化 mixin：`_record_interaction` / `_get_recent_memory` / `_get_failure_hint` / `_maybe_compress_messages` / `_reflect_and_evolve` |

| 方法（按 mixin 分布） | 说明 |
|------|------|
| `__init__` / `toggle` / `is_enabled` / `status` | 主类骨架（master.py） |
| `_ensure_all_master_files` / `_classify_error` | 存储层辅助（master_storage.py） |
| `handle(user_input, context_messages=None, background=False)` | ReAct 主循环（master_loop.py） |
| `_extract_tool_calls(text)` | 从 AI 回复中提取 ```tool 代码块 / 【调用：...】格式（master_loop.py） |
| `_execute_tool(tool_name, params)` | 通过注册表执行工具（master_loop.py） |
| `_build_tools_desc` / `_build_system_prompt(lang)` | Prompt 组装（master_prompt_builder.py） |
| `_detect_artifacts(txt, lang, background)` | 插件/Agent 自动产物检测（master_prompt_builder.py） |
| `_record_interaction` / `_get_recent_memory` / `_get_failure_hint` / `_maybe_compress_messages` | 记忆与压缩（master_reflect.py） |
| `_reflect_and_evolve(...)` | 每 10 次交互触发反思与 prompt 进化（master_reflect.py） |

**ReAct 循环伪代码**：
```python
for step in range(8):
    txt = call_llm(history)
    if "【最终答案】" in txt:
        return extract_final_answer(txt)
    actions = extract_tool_calls(txt)
    for action in actions:
        obs = execute_tool(action["tool"], action.get("params", {}))
        history.append({"role": "system", "content": f"Observation: {obs}"})
        record_interaction(action, obs)
```

**后台隔离执行**：`MasterAgent.handle(user_input, context_messages=None, background=False)` 支持传入独立的 `context_messages` 并标记 `background=True`。Hermes 后台任务使用该参数，避免后台执行污染用户主会话的 `state.messages`、上下文摘要和自动存档；同时禁用交互式产物检测，改为进入 `PersistentReviewQueue`。

---

### Hermes 后台自治任务引擎

**设计目标**：把 Hermes 从独立的 HTTP stub 升级为真正的后台自治任务引擎，拥有持久化任务队列、调度器、与 MasterAgent 联动的执行能力。

**存储位置**：`~/.fr_cli/hermes/`

| 文件 | 说明 |
|------|------|
| `tasks.json` | 持久化任务队列（状态、优先级、重试、结果） |
| `goals.json` | 持久化目标与里程碑 |
| `analytics.json` | 任务统计 |
| `hermes.log` | 运行日志 |
| `review_queue.json` | 后台产物审核队列（插件/Agent 代码） |
| `daemon.json` / `daemon.pid` / `daemon.stop` | 独立守护进程配置与生命周期标记 |

**核心类**：`agent/hermes.py`

| 类/方法 | 说明 |
|---|---|
| `PersistentTaskManager` | 基于 `JsonStore` 的持久化任务队列，支持优先级、重试、状态过滤 |
| `PersistentGoalTracker` | 持久化目标追踪 |
| `HermesScheduler` | 后台轮询调度器（daemon thread），每 5 秒执行 pending 任务 |
| `HermesEngine` | 统一入口，负责任务创建、调度、执行、HTTP daemon 管理 |
| `HermesEngine.create_task(...)` | 创建后台任务，默认 `execution_mode="sandbox"`；`autonomous` 任务默认 PAUSED |
| `HermesEngine.confirm_task(id)` | 显式确认 autonomous 任务，使其以 `full_auto` 执行 |
| `HermesEngine._execute_task(task)` | 设置环境变量 → 隔离 state.messages → 调用 MasterAgent → 记录结果 |
| `PersistentReviewQueue` | `agent/review_queue.py`，后台非交互产物审核队列 |
| `HermesManager` | `agent/hermes_manager.py`，管理独立 Hermes 子进程 |
| `hermes_daemon_process.py` | 独立守护进程入口，脱离 REPL 运行 HermesEngine + HTTP 服务 |

**安全执行模式**：

| 模式 | 说明 | 沙盒操作（读/写/搜索） | 系统操作（shell/exec/邮件/MCP） |
|---|---|---|---|
| `sandbox`（默认） | 后台任务默认模式 | 自动放行 | 非交互时默认拒绝 |
| `autonomous` | 完全信任该任务 | 自动放行 | 自动放行 |
| `interactive` | 不走后台，仅占位 | 按当前模式 | 按当前模式 |

**REPL 命令**：

```
/hermes start [port]                  # 启动独立 HTTP 守护进程（子进程）
/hermes stop                          # 停止守护进程
/hermes status                        # 查看守护进程与任务统计
/hermes task [--autonomous|-a] <描述>  # 创建后台任务（默认 sandbox 模式）
/hermes confirm <id>                  # 确认 autonomous 任务
/hermes list [status]                  # 列任务
/hermes log <id>                      # 查看任务结果/日志
/hermes cancel <id>                   # 暂停任务
/hermes review                        # 查看后台产物审核队列
/hermes review approve <id> [name]    # 批准并安装队列中的产物
/hermes review reject <id>            # 拒绝队列中的产物
```

**HTTP API**（默认 `127.0.0.1:8765`，写端点需 Bearer Token）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/info` | 引擎状态 |
| GET | `/tasks` | 任务列表 |
| GET | `/tasks/<id>` | 单个任务 |
| POST | `/tasks/<id>/confirm` | 确认 autonomous 任务 |
| POST | `/task` | 创建任务；`execution_mode=autonomous` 返回 `needs_confirmation` |
| POST | `/execute` | 提交命令任务（不再直接 subprocess） |
| POST | `/chat` | 提交对话任务给 MasterAgent |
| POST | `/goal` | 创建目标 |
| GET | `/goals` | 目标列表 |
| GET | `/analytics` | 统计 |
| GET | `/review` | 审核队列列表 |
| POST | `/review/<id>/approve?name=xxx` | 批准并安装产物 |
| POST | `/review/<id>/reject` | 拒绝产物 |

**任务执行超时**：
- 单个 Hermes 任务默认最大执行时间为 300 秒。
- 可通过环境变量覆盖：`export FR_CLI_HERMES_TASK_TIMEOUT=600`。
- 超时后任务会按重试策略重试，达到最大重试次数后标记为 `FAILED`，错误信息包含“执行超时”。

---

### 全局控制命令

为方便用户，fr-cli 提供一键启停与全局状态查看命令。

#### `/autostart` — 一键启动所有后台服务

```text
/autostart                              # 使用默认端口启动所有服务
/autostart --agent-server 17890         # 指定 Agent HTTP 端口
/autostart --hermes 8765                # 指定 Hermes 端口
/autostart --agent-server 17890 --hermes 8765
```

启动项包括：
- 启用 MasterAgent（若未启用）
- Agent HTTP 服务（默认端口 17890）
- Hermes 独立 HTTP 守护进程（默认端口 8765）
- Gatekeeper 独立守护进程
- 同步 Cron 定时任务配置

每项服务的启动结果会单独显示；已运行的服务会显示“已在运行”而不重复启动。

#### `/status` — 查看 fr-cli 全局状态

```text
/status         # 人类可读面板
/status json    # 输出 JSON
```

展示内容包括：
- 当前 provider / model / API Key 是否已配置
- 自主模式（`manual` / `sandbox_auto` / `full_auto`）
- MasterAgent 是否启用及交互次数
- Agent HTTP 服务、Hermes 守护进程、Gatekeeper 运行状态
- Hermes 任务统计（pending / running / completed / failed / paused）
- 审核队列 pending 数量
- Cron 定时任务数量
- 已加载插件数量、Agent 分身数量
- RAG 监控状态（若配置了知识库）

---

### 按日期自动存档会话

**存储位置**：`~/.fr_cli/sessions/auto/YYYY-MM-DD_NN.json`

**核心模块**：`memory/session.py`

| 函数 | 说明 |
|------|------|
| `create_session(msgs)` | 生成 `YYYY-MM-DD_NN.json`，NN 自动递增 |
| `update_session(path, msgs)` | 增量写入完整对话 |
| `list_sessions()` / `load_session(idx)` / `delete_session(idx)` | 管理接口 |

**命令**：`/session_list`, `/session_load <idx>`, `/session_del <idx>`

---

### 工作流格式示例

```markdown
# 工作流：数据分析助手

## 步骤1：收集数据
- **action**: search_web
- **params**:
  - query: "{{user_input}}"

## 步骤2：整理内容
- **action**: ai_generate
- **params**:
  - prompt: "整理以下搜索结果：{{step1.result}}"

## 步骤3：保存报告
- **action**: invoke_tool
- **params**:
  - tool: write_file
  - path: report.md
  - content: "{{step2.result}}"
```

- 支持的步骤 action：`ai_generate`、`invoke_tool` / `tool`、`execute_cmd` / `cmd`、`agent_call`、`save_memory`
- `params` 中可指定 `timeout`（秒）为单步设置执行超时，如 `timeout: 30`
- `params` 中可指定 `retry_count` 为重试次数
- 执行前会自动检测 `{{stepN.result}}` / `{{stepN.error}}` 之间的循环依赖，发现环则直接返回错误

### HTTP API 示例

```bash
# 在 fr-cli 中启动服务
>>> /agent_server start 8080
Agent HTTP 服务已启动: http://0.0.0.0:8080

# 外部系统调用
curl http://localhost:8080/agents
curl http://localhost:8080/agents/my_agent
curl -X POST http://localhost:8080/agents/my_agent/run \
  -H "Content-Type: application/json" \
  -d '{"input": "请分析这个需求", "timeout": 120}'
curl -X POST http://localhost:8080/agents/my_agent/workflow \
  -H "Content-Type: application/json" \
  -d '{"input": "Python 最新特性", "timeout": 180}'
```

- `/run` 默认超时 120 秒，`/workflow` 默认 180 秒，可通过请求体 `timeout` 字段覆盖（最大 600 秒）
- 超时返回 HTTP 504，响应体包含 `{"result": null, "error": "...超时..."}`

### 蜂群协作（Swarm）

多个**任务单元**可组成**蜂群**，以并行、议会或流水线模式协同完成复杂任务。蜂群由 `fr_cli/agent/swarm.py` 中的 `SwarmEngine` 驱动，任务解析与执行统一收敛到 `fr_cli/agent/swarm_resolver.py` 的 `SwarmTaskResolver`。

任务单元支持：自定义 Agent、内置 Agent（`@local` / `@remote` / `@db` / `@spider` / `@RAG` / `@stock`）、注册表工具、`/` 命令、MCP 工具、自定义插件。

**协作模式**

| 模式 | 说明 | 适用场景 |
|---|---|---|
| `parallel` | 并发独立调用每个任务，返回各自结果 | 多角度并行分析、批量处理 |
| `council` | 先并行执行，再由大模型汇总为一致结论 | 评审、投票、共识生成 |
| `pipeline` | 串联执行，前一任务输出作为后一任务输入 | 分阶段加工（搜索→整理→保存） |

**任务名称格式**

```
agent:myagent              # 自定义/远程 Agent
@local 或 builtin:local    # 内置 Agent
tool:search_web            # 注册表工具
cmd:/web 搜索词            # 命令字符串（/ 开头也可自动识别）
mcp:fs/read_file {"path": "/tmp/a.txt"}  # MCP 工具
plugin:myplugin            # 自定义插件
```

**命令示例**

```
>>> /swarm parallel coder,reviewer 帮我review这段代码
>>> /swarm council researcher,writer 调研并总结 Python 3.13 新特性
>>> /swarm pipeline extractor,summarizer 从报告中提取关键点并生成摘要
>>> /swarm parallel @local,tool:search_web 分析项目并搜索资料
>>> /swarm pipeline tool:search_web,cmd:/write report.md 搜索并保存报告
```

**AI 调用示例**

```
【调用：swarm_run({"mode": "council", "names": ["coder", "reviewer"], "user_input": "帮我review这段代码"})】
```

- `names`：任务名称列表，逗号分隔
- `max_workers`：最大并发数，默认 5，上限 10
- 某个任务失败时仅记录 `error` 字段，不影响蜂群整体执行

---

## AI 调用格式

### 内置工具（结构化调用）

AI 使用 `【调用：tool_name({"参数": "值"})】` 格式，参数为标准 JSON。

| 工具名 | 参数示例 | 说明 |
|--------|----------|------|
| `write_file` | `{"path": "a.md", "content": "..."}` | 写入文件 |
| `read_file` | `{"path": "a.md"}` | 读取文件 |
| `list_files` | `{}` | 列出目录 |
| `change_dir` | `{"path": "dir"}` | 切换目录 |
| `append_file` | `{"path": "a.md", "content": "..."}` | 追加内容 |
| `delete_file` | `{"path": "a.md"}` | 删除文件 |
| `rename_file` | `{"old_path": "a.md", "new_path": "b.md"}` | 重命名文件 |
| `replace_text` | `{"path": "a.md", "old_text": "foo", "new_text": "bar", "use_regex": false}` | 文本替换（支持正则） |
| `grep_text` | `{"path": "a.md", "pattern": "regex", "use_regex": true}` | 正则/文本匹配 |
| `search_web` | `{"query": "搜索词"}` | 联网搜索 |
| `fetch_web` | `{"url": "https://..."}` | 抓取网页 |
| `ping_host` | `{"host": "example.com"}` | ping 探测 |
| `port_scan` | `{"host": "192.168.1.1", "ports": "22,80,443"}` | 端口扫描 |
| `ip_scan` | `{"network": "192.168.1.0/24"}` | IP 存活扫描 |
| `network_devices` | `{"network": "192.168.1.0/24"}` | 网络设备发现 |
| `ssh_command` | `{"host": "srv", "user": "root", "command": "uptime"}` | SSH 执行远程命令 |
| `scp_transfer` | `{"host": "srv", "user": "root", "local_path": "a.txt", "remote_path": "/tmp/a.txt", "direction": "up"}` | SCP/SFTP 文件传输 |
| `generate_image` | `{"prompt": "描述"}` | 生成图片 |
| `analyze_image` | `{"path": "img.jpg", "text": "问题"}` | 图片分析 |
| `mail_inbox` | `{}` | 查看收件箱 |
| `mail_read` | `{"id": "1"}` | 读取邮件 |
| `mail_send` | `{"to": "a@b.com", "subject": "主题", "body": "正文"}` | 发送邮件 |
| `cron_add` | `{"command": "/ls", "interval": 60}` | 添加定时任务 |
| `cron_list` | `{}` | 列出定时任务 |
| `cron_del` | `{"id": "1"}` | 删除定时任务 |
| `disk_ls` | `{}` | 列出云盘文件 |
| `disk_up` | `{"local": "a.txt", "remote": "/b.txt"}` | 上传文件 |
| `disk_down` | `{"remote": "/b.txt", "local": "a.txt"}` | 下载文件 |
| `save_session` | `{"name": "session1"}` | 保存会话 |
| `list_sessions` | `{}` | 列出会话 |
| `export_session` | `{}` | 导出为 Markdown |
| `set_model` | `{"name": "glm-4-flash"}` | 切换模型 |
| `set_key` | `{"key": "xxx"}` | 设置 API Key |
| `set_limit` | `{"limit": 4096}` | 设置 token 上限 |
| `set_lang` | `{"code": "zh"}` | 切换语言 |
| `generate_chart` | `{"type": "bar", "labels": ["A", "B", "C"], "values": [10, 20, 30], "title": "销售"}` | 生成控制台图表（bar/pie/line） |
| `swarm_run` | `{"mode": "council", "names": ["coder", "reviewer"], "user_input": "帮我review这段代码"}` | 蜂群协作：并行/议会/流水线多 Agent 协作 |
| `ocr_recognize` | `{"path": "invoice.pdf"}` | OCR 识别图片或 PDF 中的文字 |
| `mcp_call` | `{"server": "fs", "tool": "read_file", "arguments": {"path": "/tmp/a.txt"}}` | 调用 MCP 外部神通 |
| `mcp_list` | `{}` | 列出 MCP 服务器及工具 |

### MCP 外部神通

MCP (Model Context Protocol) 允许连接外部服务器，将其工具纳入 AI 调用范围。

**配置格式**（`~/.fr_cli/config.json`）：
```json
{
    "mcp": {
        "servers": [
            {
                "name": "fs",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                "env": {},
                "enabled": true
            }
        ]
    }
}
```

**管理命令**：`/mcp_list`, `/mcp_add`, `/mcp_del`, `/mcp_enable`, `/mcp_disable`, `/mcp_refresh`

### 多源信息融合框架

当用户请求涉及信息获取时，系统采用**双源回答与汇总**模式：

1. **第一轮（并行收集）**：
   - AI 先基于自身知识给出初步回答（直接输出在回复文本中）
   - 同时调用相应的外部工具（search_web、mcp_call、agent_call 等）获取补充信息

2. **第二轮（融合整理）**：
   - 系统将所有信息源结构化合并后再次提交给大模型
   - 大模型基于多源信息整理成完整、准确、结构清晰的最终答案
   - 若不同来源存在冲突，以最新/最权威来源为准，或明确标注不确定性

3. **保存意图检测**：
   - 若用户原始请求中包含"保存"关键词，第二轮会追加提示，强制 AI 调用 `write_file` 保存最终内容

### 自定义插件（命令方式）

插件保持传统命令格式：`【命令：/plugin_name 参数】`

---

## 配置系统

配置文件路径：`~/.fr_cli/config.json`

默认配置字典（由 `conf/config.py` 定义）：

```python
{
    "key": "",                  # Zhipu API Key
    "provider": "zhipu",         # 当前道统
    "model": "glm-4-flash",     # 默认模型
    "providers": {               # 各道统独立配置
        "deepseek": {"key": "", "model": "deepseek-chat"},
        "kimi": {"key": "", "model": "moonshot-v1-8k"}
        # 每个 provider 还可选配置：
        #   "base_url": "...",            # 自定义通用 API Base URL
        #   "token_plan_base_url": "...", # Token Plan / 订阅套餐专用 Base URL
        #   "is_token_plan": true         # 标记为 Token Plan 变体，将自动使用 token_plan_base_url
    },
    "limit": 20000,             # 最大 token 上限
    "allowed_dirs": [],         # VFS 允许的目录列表
    "lang": "zh",               # 界面语言 (zh / en)
    "aliases": {},              # 命令别名
    "auto_confirm_forever": False,  # 安全：永久放行
    "mail": {},                 # 邮件配置
    "disk": {},                 # 网盘配置
    "mcp": {"servers": []},     # MCP 外部神通服务器列表
    "ocr": {                    # OCR 文字识别配置
        "provider": "",         # 复用全局 providers 中的厂商（如 zhipu / deepseek / kimi）
        "model": "",            # OCR Vision 模型名（如 glm-4v）
        "key": "",              # 专属 API Key（可选，为空则使用全局厂商 key）
        "base_url": "",         # 自定义接口地址（provider 为空时使用）
        "prompt": ""            # 默认 OCR 提示词
    },
    "stock": {                  # 股票/量化交易配置
        "default_source": "akshare",
        "akshare": {"enabled": true},
        "mairui": {"enabled": false, "key": "", "base_url": "https://api.mairui.club"},
        "tushare": {"enabled": false, "token": ""},
        "trade": {"enabled": false, "api": "", "key": "", "secret": "", "base_url": ""},
        "portfolio": {}         # 模拟持仓
    },
    "usage_prices": {           # Token 费用估算表（单位：元/千 tokens）
        "deepseek": {
            "deepseek-chat": {"prompt": 1.5, "completion": 6.0}
        }
    }
}
```

其他运行时数据目录：
- `~/.fr_cli/sessions/manual/` — 会话历史 JSON 文件
- `~/.fr_cli/plugins/` — 用户插件 `.py` 文件
- `~/.fr_cli/context.json` — 上下文记忆摘要
- `~/.fr_cli/usage.json` — LLM 调用用量统计（文件权限 0o600）
- `~/.fr_cli/agents/<name>/config.json` — Agent 专属模型配置
- `~/.fr_cli/agents/<name>/progress.json` — Agent 定时任务执行进度

> **配置统一收敛**：所有用户配置（cron / m365 / database / remote.hosts / gatekeeper / hermes.daemon）都已合并到 `~/.fr_cli/config.json` 的对应命名空间下（cron / m365 / databases / remote / gatekeeper / hermes.daemon）。`fr_cli/conf/config.py` 提供 `load_namespace(key, default, old_path)` / `save_namespace(key, value)` 工具函数，**支持点分路径**（如 `hermes.daemon`）和**老文件自动迁移**。
> 
> 旧独立文件（cron.json / m365.json / database.json / remote/hosts.json / daemon/config.json / hermes/daemon.json）在首次加载时会**自动迁移到主配置**，迁移成功后旧文件会被重命名为 `*.migrated`，作为一次性备份。
> 
> 仅 `~/.fr_cli/agents/<name>/config.json` 保留为独立文件 —— 因为每个 Agent 的配置是独立的、动态增删的，放在主配置会污染根命名空间。
> 
> **统一持久化抽象**：`fr_cli/core/store.py:JsonStore` 提供原子写、默认回退、权限控制与线程安全。目前用于 `usage.json`、`context.json`、Agent `progress.json`、Gatekeeper 进程 PID/Stop 文件等"运行时数据"类文件（这些不是配置而是状态）。

---

### OCR 文字识别配置

OCR 功能支持两种识别引擎：
- **vision**（默认）：通过 OpenAI 兼容的多模态 Vision API 识别，需配置模型与 Key。
- **paddle**：本地 PaddleOCR 引擎，离线识别，无需 API Key。

**配置方式：**

```bash
# 交互式配置向导
>>> /ocr_config setup

# 切换识别引擎
>>> /ocr_config engine paddle
>>> /ocr_config engine vision

# 直接设置字段（vision 引擎）
>>> /ocr_config provider zhipu
>>> /ocr_config model glm-4v
>>> /ocr_config key sk-xxx          # 可选，覆盖全局 key
>>> /ocr_config base_url https://... # 自定义接口时使用
>>> /ocr_config prompt "请提取所有发票字段"
```

**字段说明：**

| 字段 | 说明 |
|---|---|
| `engine` | 识别引擎：`vision`（默认）或 `paddle` |
| `provider` | 复用全局 `providers` 中的厂商；留空则使用 `base_url` + `key` 自定义接口 |
| `model` | Vision 模型名，如 `glm-4v`、`moonshot-v1-8k`、`deepseek-vl` 等 |
| `key` | 专属 API Key；为空且 `provider` 非空时，自动回退到该厂商全局 key |
| `base_url` | 自定义 OpenAI 兼容接口地址，仅在 `provider` 为空或未知时生效 |
| `prompt` | 默认 OCR 提示词，可引导模型输出表格、字段、翻译等 |

**使用示例：**

```bash
>>> /ocr screenshot.png
>>> /ocr invoice.pdf
>>> /ocr /path/to/scan.jpg
```

**依赖安装：**

PDF 识别依赖 `pymupdf`：

```bash
pip install pymupdf
```

PaddleOCR 引擎依赖 `paddleocr` 与 `paddlepaddle`：

```bash
pip install paddleocr paddlepaddle
```

---

## 代码风格指南

### 注释与命名

- **注释使用中文**，且大量使用修仙/玄幻隐喻。修改代码时应保持这一风格一致性。
- 示例术语映射：
  - 洞府 = 目录/工作区
  - 法宝 = 插件
  - 轮回 = 会话
  - 结界 = 定时任务
  - 神通 = 命令/能力
  - 本命元神 = 核心状态 (AppState)
  - 祭炼 = 保存/编译
  - 腾云驾雾 = 云盘
  - 卷轴 = 文件

### 导入风格

- 标准库导入放最前，常合并为一行：`import sys, os, re, subprocess`
- 第三方库次之：`from zhipuai import ZhipuAI`, `from openai import OpenAI`
- 多模型抽象层：`from fr_cli.core.llm import BaseLLMClient, ZhipuLLMClient, OpenAICompatibleClient`
- 内部模块使用绝对导入：
  ```python
  from fr_cli.conf.config import load_config, save_config, init_config
  from fr_cli.lang.i18n import T
  ```

### 静态检查

- 项目已配置 `ruff`，启用 `F` + `E` + `W`。
- 因历史风格保留部分忽略项：`E401`（多导入一行）、`E701/E702`（单行 if/return）、`E402`（可选依赖延迟导入）、`E501`（行长度）、`E741`（单字母变量）、`E731`（lambda 赋值）、`F403/F405`（star import）。
- 提交前运行：
  ```bash
  ruff check fr_cli tests
  .venv/bin/python -m pytest tests/ -q
  ```

---

## 测试说明

项目已有完整测试套件：

- `tests/test_a2a_and_providers.py` — 多提供商测试
- `tests/test_integration_real.py` — 集成测试（配置/LLM/Agent/工作流）
- `tests/test_master_prompt_fix.py` — MasterAgent Prompt 格式修复测试
- `tests/test_model_config.py` — 模型配置与 LLM 客户端测试
- `tests/test_workflow.py` — Agent 工作流引擎测试
- `tests/test_new_providers.py` — 新提供商测试（MiniMax/Kimi）
- `tests/test_ocr.py` — OCR 文字识别测试
- `tests/test_stock.py` — StockShareAgent 股票/量化助手测试
- `tests/test_swarm.py` — 蜂群多 Agent 协作测试
- `tests/test_plan.py` — 计划模式测试
- `tests/test_dynamic_builder.py` — 动态构建系统测试
- 总计 **473 个测试全部通过**

测试覆盖：VFS、Security、Config、History、Plugin、Cron、Web、WeaponLoader、Recommender、CommandExecutor、ContextMemory、AIToolCallingIntegration、StructuredToolInvocation、MasterAgent、AutoSession、ThinkingModes、PlanMode、Gatekeeper

---

## 安全考量

### 1. 四阶安全确认与自治模式（security/security.py、security/policy.py）

对危险操作（文件读写、命令执行、插件安装等），系统默认会提示用户并等待输入：

- `Y` — 仅允许一次（Once）
- `A` — 本次会话允许（Session）
- `F` — 永久允许（Forever），会写入 `~/.fr_cli/config.json` 的 `auto_confirm` 字典
- `N` / 回车 — 拒绝（Deny）

**自治模式（v2.5.1）**：

通过 `/autonomous [manual|sandbox_auto|full_auto|off]` 或环境变量 `FR_CLI_AUTONOMOUS_MODE` 设置：

- `manual`（默认）：每个 `sec_*` 都询问。
- `sandbox_auto`：`sec_read`、`sec_write`、`sec_fetch_web`、`sec_gen_img` 自动放行；`sec_shell`、`sec_exec`、`sec_send_mail` 等系统级操作仍询问或在非交互时默认拒绝。
- `full_auto`：所有 `sec_*` 自动放行（危险）。

Hermes 后台任务默认使用 `execution_mode="sandbox"`，等价于在任务执行期间设置 `FR_CLI_AUTONOMOUS_MODE=sandbox_auto`。

### 2. 虚拟文件系统沙盒（weapon/fs.py）

- `VFS._resolve()` 使用 `Path.resolve()` 解析后，检查路径前缀是否落在 `allowed_dirs` 内。
- 禁止 `../` 逃逸到允许目录之外。
- 路径检查使用 `== base_path or startswith(base_path + os.sep)`，防止 `/foo` 错误匹配 `/foo-bar`。

### 3. AI 自动工具执行

- 内置工具通过注册表统一调度，参数走结构化 `kwargs`，避免字符串 split 导致的问题。
- `registry.dispatch()` 自动进行参数校验和安全确认。
- `registry.dispatch_cmd()` 用于用户命令，跳过安全确认（由 `main.py` 在调用前确认）。
- 插件通过 `execute()` 解析命令字符串执行。

### 4. 插件子进程隔离（安全加固后）

- 插件名称通过 `name.isidentifier()` 校验，只允许合法 Python 标识符
- 参数使用 `json.dumps()` 序列化传递，消除字符串拼接注入
- 使用 `runpy.run_path(path, run_name="__plugin__", init_globals={"ARGS": json.dumps(args)})` 执行，替代 `subprocess.run([sys.executable, "-c", runner_code], shell=True)` 的字符串拼接方式
- 超时 15 秒，输出捕获后打印

### 5. 定时任务安全

- `CronManager._job_runner()` 使用 `shlex.split(cmd) + shell=False` 替代 `shell=True`
- `add_job` 强制 `interval >= 5`，防止高频执行

### 6. SSH 远程安全

- `agent/builtins/remote.py` 全面改用 `paramiko.SSHClient().connect() + exec_command()`
- 彻底消除 `subprocess.run(ssh_cmd, shell=True)` 的远程命令注入风险

### 7. 网页抓取 SSRF 防护

- `weapon/web.py` 中 `_is_private_url(url)` 拦截：
  - 非 http/https 协议（file://、ftp:// 等）
  - localhost / 127.0.0.1 / 0.0.0.0
  - 私有 IP 段：10/8、172.16/12、192.168/16、169.254/16

### 8. 邮件头注入防护

- `weapon/mail.py` 中邮件头字段过滤换行符（`\r`、`\n`），防止 SMTP 头注入攻击

### 9. 配置文件原子写入

- `conf/config.py` 中 `save_config()` 使用：
  - `tempfile.mkstemp(dir=CONFIG_FILE.parent)` 创建临时文件
  - `os.chmod(fd, 0o600)` 设置仅所有者可读写
  - `os.replace(tmp, CONFIG_FILE)` 原子替换，防竞态条件和截断写入

### 10. Agent HTTP 安全

- 默认绑定 `host="127.0.0.1"`（原为 `0.0.0.0`）
- 启动时生成随机 Bearer Token：`secrets.token_hex(16)`
- 所有端点需携带 `Authorization: Bearer <token>`
- CORS 改为按需而非全局 `*`

### 11. 架构解耦带来的安全收益

- `CommandExecutor` 从快照同步改为**动态构建依赖**（`_build_deps(state)`），消除状态不同步导致的安全边界漂移
- `main.py` 已瘦身，命令处理器拆分为 `repl/commands/` 包并由 `repl/router.py` 统一路由，降低单文件复杂度带来的安全风险

---

## 给 AI 助手的快速参考

| 任务 | 建议操作 |
|---|---|
| **添加新 weapon 工具** | **只需在 `command/registry.py` 中用 `@register(...)` 注册一个 handler**，可选在 `WEAPON.MD` 中添加人类可读描述 |
| 添加新 Agent | 在 `~/.fr_cli/agents/<name>/` 下创建 `persona.md` + `memory.md` + `skills.md` + `agent.py`（可选） |
| 添加本机应用启动 | 修改 `weapon/launcher.py` 的 `_APP_ALIASES` 映射表，按平台添加别名 |
| 添加数据库支持 | 修改 `agent/builtins/db.py` 的 `_connect()` 添加新数据库驱动 |
| 添加 RAG 文件类型 | 修改 `agent/builtins/rag.py` 的 `_read_file()` 添加新文件格式解析 |
| 修改 RAG 检索流程 | 修改 `agent/builtins/rag.py` 的 `query()` — 调整嵌入模型、候选池大小、生成 prompt |
| 添加 Excel/CSV 支持 | 修改 `weapon/dataframe.py` 添加新的数据读取/分析方法 |
| 添加 MCP 传输方式 | 修改 `weapon/mcp.py` 添加新传输协议（如 SSE） |
| 添加 Agent 工作流 | 在 Agent 目录下创建 `workflow.md`，使用 `## 步骤N` 格式定义步骤 |
| 启动 Agent HTTP 服务 | 在 CLI 中输入 `/agent_server start [port]`，或直接用 `AgentHTTPServer(state, port=8080).start()` |
| 添加 Agent HTTP 端点 | 修改 `agent/server.py` 的 `_AgentHTTPHandler`，新增路由和处理逻辑 |
| 启动 Gatekeeper 守护进程 | 在 CLI 中输入 `/gatekeeper start`，持久化 Agent HTTP 服务 + 定时任务 + Agent 定时任务 |
| 添加 Agent 定时任务 | 在 CLI 中输入 `/agent_cron_add <agent名称> <秒> [输入]`，Gatekeeper 后台自动执行 |
| 修改定时任务执行逻辑 | 修改 `weapon/cron.py` 的 `CronManager._job_runner()`，支持 shell/agent 两种类型 |
| 使用蜂群调度任意任务 | `/swarm parallel agent:a,@local,tool:search_web,cmd:/ls,mcp:fs/read_file,plugin:myplugin 任务描述` |
| 动态构建新工具 | `/build <需求描述>` 或 AI 调用 `dynamic_build({"requirement": "..."})` |
| 上下文 Token 压缩 | `/context compress` 手动压缩；自动阈值 `/context threshold 8000`；保留轮数 `/context keep 5` |
| 使用 Microsoft 365 邮件 | 配置 Azure AD 应用后执行 `/m365_config setup`，支持 OAuth2 设备码/授权码流 + MFA |
| 添加新配置项 | 修改 `conf/config.py` 的默认字典 `d`，在 `AppState` 中读取并使用 |
| 修改安全策略 | 修改 `security/security.py` 的 `ask()`，确保返回值在 `command/security.py` 的 `SecurityManager.check()` 中正确处理 |
| 切换思维模式 | 在 CLI 中输入 `/mode cot|tot|react|plan`，启用 CoT/ToT/ReAct/Plan 深度推理 |
| 修改思维引擎 | 修改 `core/thinking.py` 的 prompt 模板或 `ThinkingEngine.analyze()` 逻辑；计划模式逻辑在 `core/plan.py` |
| 修改插件机制 | 修改 `addon/plugin.py`，保持 `def run(args='')` 的约定和子进程超时 15 秒的限制 |
| 修改流式输出 | 修改 `core/stream.py` 的 `stream_cnt()`，注意代码块高亮状态机 |
| 修改国际化文本 | 修改 `lang/i18n.py` 的 `I18N` 字典，确保 `zh` 与 `en` 键同时存在 |
| 添加测试 | 在 `tests/` 目录中新增或修改，运行 `python -m pytest tests/ -v` 验证 |
| 发布新版本 | 修改 `pyproject.toml` 的 `version`，运行 `python -m build && twine upload dist/*` |
| Docker 部署 | 使用 `docker build -t fr-cli .` 构建，`docker compose up fr-cli` 运行；配置通过卷挂载持久化 |

---

## 自主增强收尾（OpenClaw/HermesAgent 对齐）

以下能力在 v2.5+ 中加入，用于提升 autonomous 任务的自我管理与进化能力：

| 能力 | 用法 / 入口 | 关键文件 |
|---|---|---|
| 自动目标分解 | `/hermes goal [--autonomous] [--tags a,b] <目标描述>` 或 HTTP `POST /goal`（带 `decompose=true`） | `agent/hermes/engine.py`, `agent/hermes/managers.py` |
| 子任务依赖 / 链式执行 | 任务 `dependencies` / `chain_next` 字段；调度器自动检测循环依赖 | `agent/hermes/engine.py`, `agent/hermes/scheduler.py` |
| 自动生成物验证 | 动态构建的工具注册后会立即自测；失败自动回滚 | `dynamic_builder/runner.py`, `dynamic_builder/registry_manager.py` |
| 失败驱动自我学习 | MasterAgent 按 `(tool, error_type)` 统计失败，生成 `failure_hints` 并注入 system prompt | `agent/master_reflect.py`, `agent/master_prompt_builder.py` |
| 能力缺口发现 | `/build check <需求>`、AI 工具 `analyze_gap` / `build_missing_tool` | `dynamic_builder/gap_analyzer.py`, `command/registered/dynamic_build.py` |
| 跨任务记忆 | Hermes 任务携带 `context_tags`，执行前注入相关历史任务摘要 | `agent/hermes/managers.py` 的 `HermesMemoryStore` |
| 集中式错误报告 | `/status errors` 聚合 Hermes 失败、自测回滚、审核拒绝、MasterAgent 失败模式 | `core/error_ledger.py`, `core/core.py`, `repl/commands/system/status.py` |

## 消息平台推送（v2.8+）

通过 webhook 单向推送通知到主流协作平台（零依赖，仅 requests）：

| 平台 | 命令 | 关键文件 |
|---|---|---|
| 飞书 / Lark | `/notify_add lark <webhook> [secret]` | `weapon/notifier.py` `_send_lark` |
| 钉钉 | `/notify_add dingtalk <webhook> [secret]` | `weapon/notifier.py` `_send_dingtalk` |
| 企业微信 | `/notify_add wecom <webhook>` | `weapon/notifier.py` `_send_wecom` |
| Slack | `/notify_add slack <webhook>` | `weapon/notifier.py` `_send_slack` |
| Discord | `/notify_add discord <webhook>` | `weapon/notifier.py` `_send_discord` |
| Telegram | `/notify_add telegram <webhook>` | `weapon/notifier.py` `_send_telegram` |

典型用法：定时任务执行结果通知
```bash
/cron_add "0 9 * * *" "/notify lark '早安,今日数据已就绪'"
/notify lark '手动推送测试'
/notify all '重要告警'  # 群发所有通道
```

## Dream 梦境机制（v2.8+）

参考 OpenClaw/HermesAgent 的「Dream」概念：用户空闲时主动整理长期记忆。

| 入口 | 行为 | 关键文件 |
|---|---|---|
| `/dream` | 立即执行一次梦境整理（LLM 提炼经验/偏好/最佳实践） | `agent/dream.py` `DreamEngine.dream_now` |
| `/dream status` | 显示梦境统计 | `agent/dream.py` `get_dream_summary` |
| 自动 | MasterAgent 空闲 30 分钟无新交互时触发 | `agent/dream.py` `DreamEngine.start_idle_watcher` |

输出归档：
- 长期索引：`~/.fr_cli/master/dream_index.json`（按主题、含频次）
- 人类可读：`~/.fr_cli/master/dream_log.md`（Markdown 章节）

## Cron 表达式（v2.8+）

定时任务支持三种调度模式（向 OpenClaw / HermesAgent 看齐）：

```bash
# 旧式 interval（兼容）：每秒/分钟间隔
/cron_add echo hello 60

# 标准 cron 表达式：每天 9 点
/cron_add echo morning "0 9 * * *"

# 每 5 分钟一次
/cron_add "*/5 * * * *" "/notify lark 心跳检测"

# 一次性任务：指定时间
/cron_add echo "2026 新年快乐" "2027-01-01 00:00:00"
```

底层用 `croniter` 库，支持标准 5/6 字段 cron 表达式。

## 选品洞察提炼器（v2.9+ / Unreleased）

让 MasterAgent 从选品历史中提炼爆款规律，自动注入到 system prompt。属于"业务经验学习"维度。

**数据源**（可插拔，`fr_cli/agent/insight_source.py`）：
- `MockSelectionSource` — 默认，~80 条合成数据，零配置跑通
- `JSONSelectionSource` / `CSVSelectionSource` — 真实数据接入
- `register_source(name, cls)` — 动态扩展（如接 ERP / 选品平台 API）

**提炼引擎**（`fr_cli/agent/insight_extractor.py`）：
- 分批-聚合模式，应对 100-1000 条规模
- 输出结构化洞察：强势品类 / 价格带规律 / 生命周期 / 季节性 / 关键信号
- `format_for_prompt(insights, max_chars=2000)` 输出可注入 prompt 的 Markdown

**档案存储**（`fr_cli/agent/insight_storage.py`）：
- `~/.fr_cli/master/insights/latest.json` — 最新洞察，供 prompt 注入
- `~/.fr_cli/master/insights/history/YYYY-MM-DD_HHMMSS.json` — 历史快照

**REPL 命令**（`fr_cli/repl/commands/insight.py`）：
- `/insight` 或 `/insight show` — 查看最新洞察
- `/insight extract [--source mock|json|csv] [--path <file>] [--since YYYY-MM-DD] [--batch N]` — 立即跑一次提炼
- `/insight history [N]` — 查看最近 N 条历史
- `/insight sources` — 列出可用数据源
- `/insight_extract` — 等价于 `/insight extract`

**Prompt 注入**（`fr_cli/agent/master_prompt_builder.py`）：
- 在 `[高频失败与恢复提示]` 段后追加 `[选品经验]` 段落
- 来源元信息（数据源 + 提炼时间）一并注入，便于 LLM 评估时效

**Dream 集成**（`fr_cli/agent/dream.py`）：
- `DreamEngine(client, model_name, lang, selection_source=None)` 可选传 `selection_source`
- 每次 Dream 末尾会顺带跑一次 `insight_extract`，失败不影响 Dream 主流程

**典型使用**：
```bash
# 第一次:跑一次提炼(用 mock 数据看效果)
/insight extract

# 接真实数据:
/insight extract --source json --path ~/Downloads/selection_history.json

# 之后 MasterAgent 每次启动,会自动读取 latest.json 注入
```

*文档更新时间：2026-08-13（v2.9 Unreleased：选品洞察提炼器 Insight Extractor + 业务经验自动注入 MasterAgent）。*
