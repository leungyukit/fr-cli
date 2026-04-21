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
| AI SDK | `zhipuai>=2.0.0` |
| 默认模型 | `glm-4-flash`（对话）、`glm-4v-plus`（视觉）、`cogview-3-plus`（文生图） |
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
| 测试 | `pytest`，142 个测试全部通过 |

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
│   │   ├── workflow.py         # 工作流引擎（解析 workflow.md，步骤调度，模板变量）
│   │   └── server.py           # HTTP 服务（将 Agent 发布为 REST API）
│   ├── addon/
│   │   └── plugin.py           # 插件进化引擎：扫描、落盘、子进程执行
│   ├── breakthrough/
│   │   └── update.py           # 自动更新：查询远程版本、下载 ZIP、备份替换、重启
│   ├── command/
│   │   ├── executor.py         # 命令执行引擎：解析 AI 调用标记并调度到注册表
│   │   ├── registry.py         # 统一工具注册表：装饰器注册、参数校验、安全中间件
│   │   ├── security.py         # 四阶安全确认管理器（封装 sconfirm/fconfirm）
│   │   └── __init__.py
│   ├── conf/
│   │   └── config.py           # 配置读写与首次运行引导
│   ├── core/
│   │   ├── core.py             # AppState 全局状态容器（DI 容器）
│   │   ├── stream.py           # 流式输出与代码块高亮
│   │   ├── recommender.py      # 功能推荐引擎
│   │   └── sysmon.py           # 系统状态监控
│   ├── lang/
│   │   └── i18n.py             # 国际化：硬编码 zh/en 双语字典
│   ├── memory/
│   │   ├── history.py          # 会话历史保存、加载、删除、导出 Markdown
│   │   └── context.py          # 上下文记忆：最近 5 轮摘要注入 system prompt
│   ├── security/
│   │   └── security.py         # 四阶安全确认引擎（Y/A/F/N）
│   ├── ui/
│   │   └── ui.py               # 终端颜色常量、清屏、显示宽度计算、启动动画
│   └── weapon/                 # 武器库/扩展子系统
│       ├── cron.py             # 定时任务（CronManager 类，threading.Timer）
│       ├── disk.py             # 云盘适配器
│       ├── fs.py               # 虚拟文件系统 VFS（路径沙盒、防 ../ 逃逸）
│       ├── loader.py           # 工具加载器（从注册表动态生成，兼容旧 WEAPON.MD 格式）
│       ├── mail.py             # IMAP/SMTP 邮件客户端
│       ├── vision.py           # 图片生成（CogView）与多模态消息构造（GLM-4V）
│       ├── web.py              # 百度搜索抓取与网页正文抽取
│       ├── launcher.py         # 本地应用启动器（跨平台调用浏览器/办公/通讯等）
│       └── dataframe.py        # 数据卷轴读取器（Excel / CSV 读取与分析）
├── release/                    # 可分发包目录
│   ├── fr-cli-installer        # macOS 可执行安装程序
│   ├── fr-cli-install          # 跨平台 Python 安装脚本
│   ├── fr-cli-install.sh       # macOS/Linux 安装脚本
│   ├── fr-cli-install.bat      # Windows 安装脚本
│   ├── fr_cli-2.0.0-py3-none-any.whl
│   └── fr-cli-README.md
├── tests/
│   ├── test_all.py             # 单元测试
│   ├── test_integration.py     # 集成测试
│   ├── test_structured_tools.py # 结构化工具调用测试
│   ├── test_agent_server.py    # Agent HTTP 服务测试
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

### 测试

```bash
python -m pytest tests/ -v
```

### 独立运行更新模块

```bash
python fr_cli/breakthrough/update.py check
python fr_cli/breakthrough/update.py run
```

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
│  能力实现层      (weapon/ + addon/)          │  纯净业务逻辑，返回 (result, error)
├─────────────────────────────────────────────┤
│  基础设施层      (conf/ + memory/ + security/)│ 配置、持久化、安全、国际化
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
  - 持有命令执行引擎 `executor`
  - 提供状态变更方法（`update_model()`、`update_key()`、`save_cfg()` 等）
  - `main.py` 通过 `AppState` 访问所有运行时状态，不再使用局部变量

- **`weapon/loader.py`**：工具信息加载器
  - 从注册表动态生成 AI 可用的工具列表
  - 保持与旧 `WEAPON.MD` 格式的兼容性（`load_weapon_md()` 返回旧结构）
  - `WEAPON.MD` 本身仍保留为人类可读文档，但不再被程序解析

### 模块交互简图

```
main.py
├── core.core         → AppState（DI 容器，聚合所有子系统）
├── core.stream       → 流式调用 ZhipuAI，代码高亮输出
├── core.recommender  → 功能推荐
├── command.executor  → 解析 AI 回复，调度注册表
├── memory.history    → ~/.zhipu_cli_history/ (JSON)
├── memory.context    → ~/.zhipu_cli_context.json（会话摘要）
├── addon.plugin      → ~/.zhipu_cli_plugins/ (*.py)
├── weapon.loader     → 从注册表生成工具描述
├── weapon.cron       → CronManager（threading.Timer）
└── breakthrough.update → 远程更新
```

### 关键数据流（一次普通对话）

1. `main.py` 通过 `AppState` 获取所有运行时状态。
2. 组装 `messages`（system prompt + 工具清单 + 上下文摘要 + 历史）。
3. 通过 `should_inject_tools()` 判定是否需要注入工具信息。
4. 调用 `stream_cnt()` → 逐 token 输出到 stdout。
5. 收到完整回复后，`executor.process_ai_commands()` 解析调用标记：
   - `【调用：tool_name({"参数": "值"})】` → `registry.dispatch()` → 执行 handler
   - `【命令：/command args】` → `registry.dispatch_cmd()` → 执行同一 handler
6. 自动执行提取的命令，打印结果，并将结果回写到 `messages`。
7. 再次调用 AI 生成最终回复（命令标记从显示文本中清除）。
8. 显示 token 统计、功能推荐；若检测到代码块则提示"是否祭炼为法宝"。
9. 提取最近 5 轮对话，生成摘要，持久化到 `~/.zhipu_cli_context.json`。

---

## Agent 分身系统

### 设计目标

Agent 分身系统允许用户创建独立的 AI Agent（分身），每个 Agent 拥有独立的：
- **persona.md** —— 角色设定 / 系统提示词
- **memory.md** —— 长期记忆（可读写）
- **skills.md** —— 技能说明（供 AI 参考）
- **agent.py** —— 可选的自定义 Python 执行逻辑（必须实现 `run(context, **kwargs)`）
- **workflow.md** —— 可选的工作流定义（多步骤编排）

Agent 存储在 `~/.fr_cli_agents/<name>/` 目录下。

### 创建 Agent 的四种方式

1. **AI 自动生成**：`/agent_create <name> <description>` —— 调用大模型生成完整 Agent（persona + skills + code）
2. **从已有代码铸造**：`/agent_forge <name>` —— 从历史消息中提取最近一段包含 `def run(context, **kwargs)` 的 Python 代码，直接保存为 Agent
3. **自动检测提示**：当 AI 回复中包含 `def run(context, **kwargs)` 和 `\`\`\`python` 代码块时，程序自动弹出提示，输入名称即可保存
4. **手动创建**：直接在 `~/.fr_cli_agents/<name>/` 目录下创建 `agent.py`（必须包含 `run(context, **kwargs)` 入口），可选补充 `persona.md`、`skills.md`、`workflow.md`

> **插件 vs Agent 分身的区分**：包含 `def run(args='')` 的代码会被识别为**插件**（保存到 `~/.zhipu_cli_plugins/`），包含 `def run(context, **kwargs)` 的代码会被识别为 **Agent 分身**（保存到 `~/.fr_cli_agents/`）。

### 模块职责

- **`agent/manager.py`** —— 分身掌管者
  - `create_agent_dir(name)`：开辟 Agent 洞府
  - `list_agents()`：列出所有分身
  - `delete_agent(name)`：抹除分身
  - `load_persona/memory/skills(name)`：读取设定
  - `save_persona/memory/skills(name, content)`：写入设定
  - `load_agent_module(name)`：动态加载 `agent.py`

- **`agent/executor.py`** —— 分身执行器
  - `run_agent(name, state, **kwargs)`：执行单个 Agent
  - `delegate_to_agent(name, state, pipeline_input, **kwargs)`：管道化委托（前一 Agent 输出作为后一输入）
  - `run_multi_agent(names, state, initial_input, **kwargs)`：多 Agent 流水线协作

- **`agent/workflow.py`** —— 工作流引擎
  - `load_workflow(name)` / `save_workflow(name, content)`：读写 workflow.md
  - `parse_workflow(text)`：解析 Markdown 格式工作流为步骤列表
  - `run_workflow(name, state, user_input, **kwargs)`：按步骤执行工作流
  - 支持模板变量：`{{step1.result}}`、`{{user_input}}`、`{{agent.persona}}` 等

- **`agent/server.py`** —— HTTP 服务（分身对外接口）
  - `AgentHTTPServer(state, host, port)`：HTTP 守护线程
  - 提供 REST API：`GET /agents`、`GET /agents/<name>`、`POST /agents/<name>/run`、`POST /agents/<name>/workflow`
  - 零额外依赖（标准库 `http.server`）

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
- 首次使用自动启动配置向导，配置文件：`~/.fr_cli_remotes.json`

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
- 配置文件：`~/.fr_cli_databases.json`

**@RAG — 本地知识库问答**
```
>>> @RAG 项目的部署流程是什么
📚 正在同步知识库...
🔍 正在检索知识库并生成回答...
```
- 向量库：ChromaDB（嵌入式 `PersistentClient`，自动启动，无需单独服务）
- 嵌入模型：all-MiniLM-L6-v2（向量检索）
- Rerank 模型：cross-encoder/ms-marco-MiniLM-L-6-v2（重排序，取 top-3）
- 大模型判定：LLM 从 top-3 中按相关性/完整性/准确性评估，选出 ★【最佳】片段
- 最终生成：优先基于最佳片段回答，可综合其他片段补充
- 配置命令：`/rag_dir <目录路径>` — 设置目录并首次同步
- 手动同步：`/rag_sync [路径]` — 立即向量化新文件/更新文件
- 独立守护进程：`/rag_watch start [目录] [--interval N]` — 启动持久化后台监控进程
  - `/rag_watch stop` — 停止守护进程
  - `/rag_watch status` — 查看守护进程状态
  - `/rag_watch log [--lines N]` — 查看守护进程日志
- 监控模式说明：
  - 内置模式（`/rag_dir` 后自动启动）：daemon 线程，fr-cli 退出后终止
  - 独立模式（`/rag_watch start`）：系统级子进程，脱离终端，日志写入 `~/.fr_cli_rag_watcher.log`

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
  -d '{"input": "请分析这个需求"}'
curl -X POST http://localhost:8080/agents/my_agent/workflow \
  -H "Content-Type: application/json" \
  -d '{"input": "Python 最新特性"}'
```

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
| `search_web` | `{"query": "搜索词"}` | 联网搜索 |
| `fetch_web` | `{"url": "https://..."}` | 抓取网页 |
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

### 自定义插件（命令方式）

插件保持传统命令格式：`【命令：/plugin_name 参数】`

---

## 配置系统

配置文件路径：`~/.zhipu_cli_config.json`

默认配置字典（由 `conf/config.py` 定义）：

```python
{
    "key": "",                  # Zhipu API Key
    "model": "glm-4-flash",     # 默认模型
    "limit": 20000,             # 最大 token 上限
    "allowed_dirs": [],         # VFS 允许的目录列表
    "lang": "zh",               # 界面语言 (zh / en)
    "aliases": {},              # 命令别名
    "auto_confirm_forever": False,  # 安全：永久放行
    "mail": {},                 # 邮件配置
    "disk": {}                  # 网盘配置
}
```

其他运行时数据目录：
- `~/.zhipu_cli_history/` — 会话历史 JSON 文件
- `~/.zhipu_cli_plugins/` — 用户插件 `.py` 文件
- `~/.zhipu_cli_context.json` — 上下文记忆摘要

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
- 第三方库次之：`from zhipuai import ZhipuAI`
- 内部模块使用绝对导入：
  ```python
  from fr_cli.conf.config import load_config, save_config, init_config
  from fr_cli.lang.i18n import T
  ```

---

## 测试说明

项目已有完整测试套件：

- `tests/test_all.py` — 单元测试
- `tests/test_integration.py` — 集成测试
- `tests/test_structured_tools.py` — 结构化工具调用测试
- `tests/test_agent_server.py` — Agent HTTP 服务测试（启动/停止/Agent 执行/工作流/CORS）
- `tests/test_launcher.py` — 本地应用启动器测试
- `tests/test_builtins.py` — 内置 Agent 测试（远程配置/爬虫工具）
- `tests/test_dataframe.py` — 数据卷轴测试
- 总计 **142 个测试全部通过**

测试覆盖：VFS、Security、Config、History、Plugin、Cron、Web、WeaponLoader、Recommender、CommandExecutor、ContextMemory、AIToolCallingIntegration、StructuredToolInvocation

---

## 安全考量

### 1. 四阶安全确认（security/security.py）

对危险操作（文件读写、命令执行、插件安装等），系统会提示用户并等待输入：

- `Y` — 仅允许一次（Once）
- `A` — 本次会话允许（Session）
- `F` — 永久允许（Forever），会写入 `~/.zhipu_cli_config.json` 的 `auto_confirm_forever: true`
- `N` / 回车 — 拒绝（Deny）

### 2. 虚拟文件系统沙盒（weapon/fs.py）

- `VFS._resolve()` 使用 `Path.resolve()` 解析后，检查路径前缀是否落在 `allowed_dirs` 内。
- 禁止 `../` 逃逸到允许目录之外。
- 路径检查使用 `== base_path or startswith(base_path + os.sep)`，防止 `/foo` 错误匹配 `/foo-bar`。

### 3. AI 自动工具执行

- 内置工具通过注册表统一调度，参数走结构化 `kwargs`，避免字符串 split 导致的问题。
- `registry.dispatch()` 自动进行参数校验和安全确认。
- `registry.dispatch_cmd()` 用于用户命令，跳过安全确认（由 `main.py` 在调用前确认）。
- 插件通过 `execute()` 解析命令字符串执行。

### 4. 插件子进程隔离

- 插件通过 `subprocess.run([sys.executable, "-c", runner_code], timeout=15)` 执行。
- 超时 15 秒，输出捕获后打印。

---

## 给 AI 助手的快速参考

| 任务 | 建议操作 |
|---|---|
| **添加新 weapon 工具** | **只需在 `command/registry.py` 中用 `@register(...)` 注册一个 handler**，可选在 `WEAPON.MD` 中添加人类可读描述 |
| 添加新 Agent | 在 `~/.fr_cli_agents/<name>/` 下创建 `persona.md` + `memory.md` + `skills.md` + `agent.py`（可选） |
| 添加本机应用启动 | 修改 `weapon/launcher.py` 的 `_APP_ALIASES` 映射表，按平台添加别名 |
| 添加数据库支持 | 修改 `agent/builtins/db.py` 的 `_connect()` 添加新数据库驱动 |
| 添加 RAG 文件类型 | 修改 `agent/builtins/rag.py` 的 `_read_file()` 添加新文件格式解析 |
| 修改 RAG 检索流程 | 修改 `agent/builtins/rag.py` 的 `query()` — 调整 rerank 模型、候选池大小、大模型判定 prompt |
| 添加 Excel/CSV 支持 | 修改 `weapon/dataframe.py` 添加新的数据读取/分析方法 |
| 添加新数据库支持 | 修改 `agent/builtins/db.py` 的 `_connect()` 添加新数据库驱动 |
| 添加 Agent 工作流 | 在 Agent 目录下创建 `workflow.md`，使用 `## 步骤N` 格式定义步骤 |
| 启动 Agent HTTP 服务 | 在 CLI 中输入 `/agent_server start [port]`，或直接用 `AgentHTTPServer(state, port=8080).start()` |
| 添加 Agent HTTP 端点 | 修改 `agent/server.py` 的 `_AgentHTTPHandler`，新增路由和处理逻辑 |
| 启动 Gatekeeper 守护进程 | 在 CLI 中输入 `/gatekeeper start`，持久化 Agent HTTP 服务 + 定时任务 + Agent 定时任务 |
| 添加 Agent 定时任务 | 在 CLI 中输入 `/agent_cron_add <agent名称> <秒> [输入]`，Gatekeeper 后台自动执行 |
| 修改定时任务执行逻辑 | 修改 `weapon/cron.py` 的 `CronManager._job_runner()`，支持 shell/agent 两种类型 |
| 添加新配置项 | 修改 `conf/config.py` 的默认字典 `d`，在 `AppState` 中读取并使用 |
| 修改安全策略 | 修改 `security/security.py` 的 `ask()`，确保返回值在 `command/security.py` 的 `SecurityManager.check()` 中正确处理 |
| 切换思维模式 | 在 CLI 中输入 `/mode cot|tot|react`，启用 CoT/ToT/ReAct 深度推理 |
| 修改思维引擎 | 修改 `core/thinking.py` 的 prompt 模板或 `ThinkingEngine.analyze()` 逻辑 |
| 修改插件机制 | 修改 `addon/plugin.py`，保持 `def run(args='')` 的约定和子进程超时 15 秒的限制 |
| 修改流式输出 | 修改 `core/stream.py` 的 `stream_cnt()`，注意代码块高亮状态机 |
| 修改国际化文本 | 修改 `lang/i18n.py` 的 `I18N` 字典，确保 `zh` 与 `en` 键同时存在 |
| 添加测试 | 在 `tests/` 目录中新增或修改，运行 `python -m pytest tests/ -v` 验证 |
| 发布新版本 | 修改 `pyproject.toml` 的 `version`，运行 `python -m build && twine upload dist/*` |

---

*文档更新时间：2026-04-20（已完成：统一注册表 + AppState DI 容器 + Agent 分身系统 + Agent HTTP 服务 + 内置 Agent（local/remote/spider/db/RAG）+ 数据卷轴 + 本机应用启动 + Gatekeeper 热重载与 Agent 定时任务 + CoT/ToT/ReAct 思维推演模式）。*
