# 凡人打字机 (fr-cli) 使用与配置说明书

> 版本: v2.1.0  
> 作者: 修仙者联盟  
> 包名: `fr-cli` (PyPI)  
> 命令入口: `fr-cli`

---

## 目录

1. [简介](#简介)
2. [安装](#安装)
3. [快速开始](#快速开始)
4. [配置说明](#配置说明)
5. [命令参考](#命令参考)
6. [AI 工具调用](#ai-工具调用)
7. [插件系统](#插件系统)
8. [安全机制](#安全机制)
9. [常见问题](#常见问题)

---

## 简介

「凡人打字机」是一个基于智谱 AI (ZhipuAI/GLM) 的终极全能终端工具。它将大语言模型与本地环境深度集成，让你可以在终端中通过自然语言与 AI 对话，并让 AI 自动调用各类工具完成实际任务。

**核心特性：**
- 🤖 **AI 智能对话** — 基于 GLM-4 系列模型，流式实时响应
- 📁 **安全文件沙盒** — 虚拟文件系统，防止目录穿越攻击
- 🔍 **联网搜索** — 百度搜索 + 网页内容提取
- 🖼️ **视觉能力** — 图片生成 (CogView) + 图片分析 (GLM-4V)
- 📧 **邮件收发** — IMAP/SMTP 真实邮件客户端
- ⏰ **定时任务** — 后台线程定时执行命令
- ☁️ **云盘集成** — 阿里云 OSS 上传/下载/列出
- 🔌 **插件系统** — AI 自动生成插件，动态扩展功能
- 🧠 **会话记忆** — 自动保留最近对话摘要，持久化上下文
- 🛡️ **四阶安全确认** — 精细控制危险操作权限
- 👤 **Agent 分身系统** — 创建独立 Agent（角色/记忆/技能/工作流），AI 自动生成
- 🌐 **Agent HTTP API** — 将 Agent 发布为 REST API 供外部调用
- 🖥️ **本机应用启动** — 一键调用浏览器、微信、Word、WPS 等本地程序
- 🧑‍💻 **内置 Agent** — `@local` 本地系统操作、`@remote` 远程 SSH、`@spider` 智能爬虫、`@db` 数据库助手、`@RAG` 知识库问答
- 📊 **数据卷轴** — Excel / CSV 读取与智能分析
- 🗄️ **数据库助手** — MySQL / PostgreSQL / SQL Server / Oracle 智能 SQL 生成
- 📚 **本地 RAG** — ChromaDB 向量库 + 自动文件监控与向量化

---

## 安装

### 方式一：pip 安装（推荐）

```bash
pip install fr-cli
fr-cli
```

### 方式二：源码安装

```bash
git clone https://github.com/yourname/fr-cli.git
cd fr-cli
pip install -e ".[all]"
```

### 依赖说明

从 v2.1.0 起，所有功能依赖默认随主包一起安装，无需单独安装可选依赖：

```bash
pip install fr-cli
```

默认包含的依赖：
- `zhipuai` — 智谱 AI SDK
- `requests` — HTTP 请求
- `pandas` + `openpyxl` — Excel/CSV 数据处理
- `pymysql` + `psycopg2-binary` + `pyodbc` + `oracledb` — 数据库驱动
- `chromadb` + `sentence-transformers` — RAG 向量库
- `paramiko` — SSH 远程操作
- `selenium` — 浏览器自动化
- `watchdog` — 文件监控
- `bypy` + `aligo` + `msal` — 云盘支持

### 首次运行

运行 `fr-cli` 后，如果没有配置 API Key，会提示输入：

```
⚠️ API Key Required
👉 Enter Zhipu API Key: sk-xxxxxxxxxxxxxxxx
```

API Key 可在 [智谱开放平台](https://open.bigmodel.cn/) 获取。

---

## 快速开始

```bash
$ fr-cli
 凡 人 打 字 机
──────────────────────────────────
 【 修 仙 者 的 编 码 引 擎 】

🔮 模型: glm-4-flash | 🛡️ 上限: 20000 | 📂 洞府: /Users/... | ⏳ 轮回: 全新轮回

>>> 你好！
🧑 凡人: 你好！
🧙 仙人: 你好！我是你的修仙助手，有什么可以帮你的吗？

>>> /help
📜 修仙指南:
  【配置】 /model /key /limit /alias /export /update
  【洞府】 /ls /cat /cd /write /append /delete
  【轮回】 /save /load /del /undo
  【法宝】 /skills (自动进化)
  【神通】 /mail_* /cron_* /web /fetch /disk_* /see
  【分身 API】 /agent_server start [port] | stop | status
  【驭器】 /open <路径/URL> | /launch <应用> [目标] | /apps
  【破壁】 !命令 ...

>>> 帮我写一段 Python 代码，计算斐波那契数列
🧑 凡人: 帮我写一段 Python 代码，计算斐波那契数列
🧙 仙人: 以下是 Python 代码：

【调用：write_file({"path": "fib.py", "content": "def fib(n):\n    ..."})】

文件已写入 fib.py！
```

---

## 配置说明

### 配置文件

配置文件位于：`~/.zhipu_cli_config.json`

### 默认配置结构

```json
{
    "key": "sk-xxxxxxxxxxxxxxxx",
    "model": "glm-4-flash",
    "limit": 20000,
    "allowed_dirs": [],
    "lang": "zh",
    "aliases": {},
    "auto_confirm_forever": false,
    "session_name": "",
    "mail": {
        "imap_server": "imap.qq.com",
        "smtp_server": "smtp.qq.com",
        "email": "your@qq.com",
        "password": "授权码"
    },
    "disk": {
        "type": "oss",
        "ak": "AccessKey",
        "sk": "SecretKey",
        "endpoint": "oss-cn-hangzhou.aliyuncs.com",
        "bucket": "my-bucket",
        "prefix": "fr-cli/"
    }
}
```

### 配置项详解

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `key` | str | `""` | 智谱 AI API Key |
| `model` | str | `glm-4-flash` | AI 模型名称 |
| `limit` | int | `20000` | 单次请求 Token 上限（最小 1000） |
| `allowed_dirs` | list | `[]` | 允许的目录列表（VFS 安全沙盒） |
| `lang` | str | `zh` | 界面语言：`zh`（中文）或 `en`（英文） |
| `aliases` | dict | `{}` | 命令别名映射 |
| `auto_confirm_forever` | bool | `false` | 永久自动确认危险操作 |
| `session_name` | str | `""` | 当前会话名称 |
| `mail` | dict | `{}` | 邮件账户配置（IMAP/SMTP） |
| `disk` | dict | `{}` | 云盘配置（当前支持阿里云 OSS） |

### 邮件配置

支持邮箱类型及服务器：

| 邮箱 | IMAP 服务器 | SMTP 服务器 | 说明 |
|------|------------|-------------|------|
| QQ/QQ 企业 | `imap.qq.com` | `smtp.qq.com` | 使用「授权码」而非密码 |
| 163 | `imap.163.com` | `smtp.163.com` | 需开启 IMAP/SMTP |
| Gmail | `imap.gmail.com` | `smtp.gmail.com` | 需开启「不够安全的应用访问」或使用应用密码 |
| Outlook | `outlook.office365.com` | `smtp.office365.com` | 标准密码 |
| 阿里云 | `imap.aliyun.com` | `smtp.aliyun.com` | 标准密码 |

**重要**：QQ/163 等邮箱需要使用「授权码」而非登录密码。授权码在邮箱设置中生成。

### 命令行修改配置

```
/key sk-xxxxxxxx        # 修改 API Key
/model glm-4-plus       # 切换模型
/limit 4096             # 修改 Token 上限
/lang zh                # 切换语言
/alias ll 你好          # 设置别名
/dir /path/to/project   # 添加允许访问的目录
```

---

## 命令参考

### 一、配置命令

| 命令 | 参数 | 说明 |
|------|------|------|
| `/model <name>` | 模型名 | 切换 AI 模型（如 `glm-4-flash`、`glm-4-plus`、`glm-4v-plus`） |
| `/key <key>` | API Key | 修改智谱 AI API Key |
| `/limit <n>` | 数字 | 设置 Token 上限（最小 1000） |
| `/alias <k> [v]` | 键 [值] | 查看/设置命令别名 |
| `/lang <zh/en>` | 语言代码 | 切换界面语言 |
| `/dir <path>` | 目录路径 | 添加允许访问的目录到沙盒 |
| `/export` | - | 导出当前会话为 Markdown 文件 |
| `/update check` | - | 检查更新 |
| `/update run` | - | 执行更新并重启 |

### 二、文件操作命令（洞府）

| 命令 | 参数 | 说明 |
|------|------|------|
| `/ls` | - | 列出当前目录文件 |
| `/cat <file>` | 文件名 | 查看文件内容（支持 UTF-8/GBK/Latin-1） |
| `/cd <dir>` | 目录名 | 切换工作目录 |
| `/write <file> <content>` | 文件名 内容 | 写入/覆盖文件 |
| `/append <file> <content>` | 文件名 内容 | 追加内容到文件 |
| `/delete <file>` | 文件名 | 删除文件 |

**安全机制**：
- 所有文件操作限制在 `allowed_dirs` 目录内
- 禁止 `../` 目录穿越攻击
- `/write` 会自动创建父目录
- 危险操作触发四阶安全确认

### 三、会话命令（轮回）

| 命令 | 参数 | 说明 |
|------|------|------|
| `/save <name>` | 会话名 | 保存当前对话历史 |
| `/load` | - | 加载历史会话（交互式选择） |
| `/del` | - | 删除历史会话（交互式选择） |
| `/undo` | - | 撤销最近一轮对话（用户 + AI） |

**上下文记忆**：
- 自动保留最近 5 轮对话摘要
- 按 `session_name` 持久化到 `~/.zhipu_cli_context.json`
- 加载会话时自动恢复上下文摘要

### 四、邮件命令（邮差）

> 需先在配置中设置 `mail` 字段

| 命令 | 参数 | 说明 |
|------|------|------|
| `/mail_inbox` | - | 列出收件箱最近 10 封邮件 |
| `/mail_read <id>` | 邮件 ID | 读取指定邮件完整内容 |
| `/mail_send <to> <sub> <body>` | 收件人 主题 正文 | 发送邮件 |

**示例**：
```
/mail_inbox
/mail_read 123
/mail_send friend@qq.com 你好 这是一封测试邮件
```

### 五、定时任务命令（结界）

| 命令 | 参数 | 说明 |
|------|------|------|
| `/cron_add <秒> <命令>` | 间隔秒数 Shell命令 | 添加循环定时任务 |
| `/cron_list` | - | 列出所有运行中的定时任务 |
| `/cron_del <id>` | 任务 ID | 删除指定定时任务 |

**示例**：
```
/cron_add 60 echo hello          # 每 60 秒执行一次 echo
/cron_list
/cron_del 1
```

**注意**：
- 基于 `threading.Timer`，程序退出后任务消失
- 任务输出截断为 100 字符
- Shell 命令执行 30 秒超时

### 六、网络命令（游侠）

> 依赖 `requests`（`pip install requests`）

| 命令 | 参数 | 说明 |
|------|------|------|
| `/web <query>` | 搜索词 | 百度搜索 |
| `/fetch <url>` | 网址 | 抓取网页并提取纯文本 |

**示例**：
```
/web Python asyncio 教程
/fetch https://example.com/article
```

### 七、云盘命令（腾云）

> 需先在配置中设置 `disk` 字段，依赖 `oss2`（阿里云）

| 命令 | 参数 | 说明 |
|------|------|------|
| `/disk_ls` | - | 列出云盘文件 |
| `/disk_up <local> <remote>` | 本地路径 云端路径 | 上传文件 |
| `/disk_down <remote> [local]` | 云端路径 [本地路径] | 下载文件 |

### 八、图像命令

| 命令 | 参数 | 说明 |
|------|------|------|
| `/see <图片路径> [问题]` | 图片 问题 | 用 GLM-4V 分析图片内容 |

**注意**：分析图片需切换模型至 `glm-4v-plus`。

### 九、本机应用启动（驭器）

一键调用本机安装的应用程序，支持跨平台（macOS / Windows / Linux）。

| 命令 | 参数 | 说明 |
|------|------|------|
| `/open <路径/URL>` | 文件路径或网址 | 用系统默认程序打开 |
| `/launch <应用> [目标]` | 应用别名 [文件/URL] | 启动指定应用，可带目标参数 |
| `/apps` | - | 列出本机可用的应用别名 |

**常用应用别名**：
| 类别 | 可用别名 |
|------|----------|
| 浏览器 | `chrome`, `safari`, `firefox`, `edge`, `浏览器` |
| 办公 | `word`, `excel`, `powerpoint`, `ppt`, `wps` |
| 通讯 | `wechat`, `微信`, `qq`, `钉钉`, `飞书` |
| 编辑器 | `vscode`, `terminal`, `终端`, `记事本` |
| 媒体 | `music`, `播放器`, `spotify`, `vlc` |
| 系统 | `finder`, `计算器`, `appstore` |

**示例**：
```
/open https://example.com
/open /Users/me/report.pdf
/launch chrome https://github.com
/launch 微信
/launch word /Users/me/doc.docx
/launch vscode /Users/me/project
/apps
```

**跨平台说明**：
- **macOS**：使用 `open` / `open -a` 命令
- **Windows**：使用 `start` 命令
- **Linux**：使用 `xdg-open` 命令

### 十、Agent 分身系统

> Agent 分身存储在 `~/.fr_cli_agents/<name>/` 下

#### Agent CLI 命令

| 命令 | 参数 | 说明 |
|------|------|------|
| `/agent_create <名称> <描述>` | 名称 需求描述 | AI 自动生成完整 Agent（人设/技能/代码） |
| `/agent_list` | - | 列出所有 Agent 分身 |
| `/agent_show <名称>` | Agent 名称 | 查看 Agent 详情（人设/记忆/技能/代码/工作流） |
| `/agent_edit <名称> <类型>` | 名称 persona/memory/skills/agent/workflow | 编辑 Agent 设定 |
| `/agent_run <名称> [参数]` | 名称 [传入参数] | 运行指定 Agent |
| `/agent_delete <名称>` | Agent 名称 | 删除 Agent |

#### 内置 Agent 前缀

在对话中直接使用 `@` 前缀触发内置 Agent：

| 前缀 | 说明 | 示例 |
|------|------|------|
| `@local <需求>` | 本地系统操作助手，AI 生成系统命令并执行 | `@local 查看当前目录下最大的10个文件` |
| `@remote [IP] <需求>` | 远程 SSH 操作助手，通过 SSH 在远程主机执行命令 | `@remote 192.168.1.1 查看磁盘空间` |
| `@spider <URL> [深度]` | 智能网页爬虫，模拟真人行为获取网页内容 | `@spider https://example.com 2` |
| `@db [别名] <需求>` | 数据库智能助手，自动分析 Schema 并生成 SQL | `@db mydb 查询最近7天注册用户` |
| `@RAG <问题>` | 本地知识库问答，向量检索 + 大模型生成 | `@RAG 什么是向量数据库` |

**@remote 配置**：
- 首次使用会自动启动配置向导
- 配置文件：`~/.fr_cli_remotes.json`
- 支持多台主机，只配一台时无需指定 IP
- 配置命令：`/remote_setup`

**@db 数据库支持**：
- MySQL / PostgreSQL / SQL Server / Oracle
- 首次使用自动启动配置向导
- 配置文件：`~/.fr_cli_databases.json`
- 自动分析表结构、列信息、生成 SQL
- 危险操作（DELETE/DROP）会触发警告
- 配置命令：`/db_setup`

**@RAG 知识库**：
- 向量库：ChromaDB（本地持久化 `~/.fr_cli_rag_db`）
- 嵌入模型：sentence-transformers (all-MiniLM-L6-v2)
- 后台自动监控知识库目录（每30秒扫描）
- 新文件自动分块、向量化、入库
- 支持格式：txt, md, py, js, json, html, csv, xlsx 等
- 配置命令：`/rag_dir <目录路径>`

**@spider 依赖**：
```bash
pip install requests selenium
```
- 先尝试无头请求，触发反爬时自动降级到 selenium 模拟真人浏览
- 内容保存到工作区 `web_YYYYMMDD/` 目录下
- 支持深度爬取（1~3层），默认只爬当前页面

#### Agent 目录结构

每个 Agent 是一个独立目录，包含：

| 文件 | 说明 |
|------|------|
| `persona.md` | 角色设定 / 系统提示词 |
| `memory.md` | 长期记忆（可被工作流读写） |
| `skills.md` | 技能描述（供 AI 参考） |
| `agent.py` | 可选自定义执行逻辑（需实现 `run(context, **kwargs)`） |
| `workflow.md` | 可选工作流定义（多步骤编排） |

#### Agent HTTP 服务命令

| 命令 | 参数 | 说明 |
|------|------|------|
| `/agent_server start [port]` | 端口号（默认 17890） | 启动 Agent HTTP API 服务 |
| `/agent_server stop` | - | 停止 HTTP 服务 |
| `/agent_server status` | - | 查看服务运行状态 |

**示例**：
```
>>> /agent_server start 8080
Agent HTTP 服务已启动: http://0.0.0.0:8080

>>> /agent_server status
运行中: http://0.0.0.0:8080

>>> /agent_server stop
Agent HTTP 服务已停止
```

#### Agent HTTP API 参考

服务启动后，外部系统可通过以下 REST API 调用 Agent：

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| `GET` | `/health` | - | 健康检查 |
| `GET` | `/agents` | - | 列出所有 Agent |
| `GET` | `/agents/<name>` | - | 获取 Agent 详情（persona/memory/skills/has_workflow） |
| `POST` | `/agents/<name>/run` | `{"input": "...", "kwargs": {}}` | 执行 Agent |
| `POST` | `/agents/<name>/workflow` | `{"input": "...", "kwargs": {}}` | 执行 Agent 工作流 |

**curl 示例**：
```bash
# 列出所有 Agent
curl http://localhost:8080/agents

# 执行 Agent
curl -X POST http://localhost:8080/agents/my_agent/run \
  -H "Content-Type: application/json" \
  -d '{"input": "请分析这个需求"}'

# 执行工作流
curl -X POST http://localhost:8080/agents/researcher/workflow \
  -H "Content-Type: application/json" \
  -d '{"input": "Python 最新特性"}'
```

#### Agent 工作流格式

在 Agent 目录下创建 `workflow.md`，使用 Markdown 格式定义步骤：

```markdown
# 工作流：数据分析

## 步骤1：搜索信息
- **action**: search_web
- **params**:
  - query: "{{user_input}}"

## 步骤2：AI 整理
- **action**: ai_generate
- **params**:
  - prompt: "整理以下搜索结果：{{step1.result}}"

## 步骤3：保存文件
- **action**: invoke_tool
- **params**:
  - tool: write_file
  - path: report.md
  - content: "{{step2.result}}"
```

**支持的动作（action）**：
| action | 说明 |
|--------|------|
| `invoke_tool` / `tool` | 调用内置工具（如 write_file, search_web） |
| `execute_cmd` / `cmd` | 执行命令字符串 |
| `agent_call` / `agent` | 调用另一个 Agent |
| `ai_generate` / `ai` | 调用 AI 生成内容 |
| `save_memory` / `memory_append` | 追加内容到 Agent memory |

**支持的模板变量**：
| 变量 | 说明 |
|------|------|
| `{{user_input}}` | 用户传入的输入 |
| `{{step1.result}}` | 步骤 1 的执行结果 |
| `{{step1.error}}` | 步骤 1 的错误信息 |
| `{{agent.persona}}` | Agent 的角色设定 |
| `{{agent.memory}}` | Agent 的长期记忆 |
| `{{agent.skills}}` | Agent 的技能描述 |

### 十一、数据卷轴（Excel / CSV）

| 命令 | 参数 | 说明 |
|------|------|------|
| `/read_excel <文件>` | Excel 文件路径 | 读取 Excel 并输出数据摘要 |
| `/read_csv <文件>` | CSV 文件路径 | 读取 CSV 并输出数据摘要 |

**说明**：
- 支持 `.xlsx`, `.xls`, `.csv` 格式
- 自动输出列名、数据类型、非空统计、数值统计、前10行预览
- 数据摘要可提交给 AI 进行深度分析

### 十三、破壁命令（系统 Shell）

| 命令 | 参数 | 说明 |
|------|------|------|
| `!<shell_cmd>` | Shell 命令 | 执行本地系统命令 |
| `!<cmd> \| <prompt>` | 命令 + AI提示 | 将命令输出管道给 AI 分析 |

**示例**：
```
!ls -la /Users
!ps aux | 找出占用 CPU 最高的进程
!cat log.txt | 分析这段日志有什么问题
```

### 十四、其他命令

| 命令 | 说明 |
|------|------|
| `/skills` | 查看已安装插件列表 |
| `/apps` | 列出本机可用应用别名 |
| `/remote_setup` | 远程主机配置向导 |
| `/db_setup` | 数据库配置向导 |
| `/rag_dir <路径>` | 设置 RAG 知识库目录 |
| `/exit` 或 `/quit` | 退出程序 |
| `/help [topic]` | 查看帮助（可指定主题，见下方） |

---

## AI 工具调用

### 结构化调用（推荐）

AI 会自动识别需求并输出工具调用标记：

```
【调用：tool_name({"参数": "值"})】
```

### 内置工具列表

| 工具名 | 参数 | 功能 |
|--------|------|------|
| `write_file` | `path`, `content` | 写入文件 |
| `read_file` | `path` | 读取文件 |
| `list_files` | - | 列出文件 |
| `change_dir` | `path` | 切换目录 |
| `append_file` | `path`, `content` | 追加文件 |
| `delete_file` | `path` | 删除文件 |
| `search_web` | `query` | 百度搜索 |
| `fetch_web` | `url` | 抓取网页 |
| `generate_image` | `prompt` | 生成图片 |
| `analyze_image` | `path`, `text` | 分析图片 |
| `mail_inbox` | - | 查看收件箱 |
| `mail_read` | `id` | 读取邮件 |
| `mail_send` | `to`, `subject`, `body` | 发送邮件 |
| `cron_add` | `command`, `interval` | 添加定时任务 |
| `cron_list` | - | 列出定时任务 |
| `cron_del` | `id` | 删除定时任务 |
| `disk_ls` | - | 列出云盘文件 |
| `disk_up` | `local`, `remote` | 上传文件 |
| `disk_down` | `remote`, `local` | 下载文件 |
| `save_session` | `name` | 保存会话 |
| `list_sessions` | - | 列出会话 |
| `export_session` | - | 导出会话 |
| `set_model` | `name` | 设置模型 |
| `set_key` | `key` | 设置 API Key |
| `set_limit` | `limit` | 设置 Token 上限 |
| `set_lang` | `code` | 设置语言 |
| `open_file` | `path` | 打开文件/URL |
| `launch_app` | `name`, `target` | 启动本地应用 |
| `read_excel` | `path` | 读取 Excel 文件 |
| `read_csv` | `path` | 读取 CSV 文件 |
| `agent_create` | `name`, `description` | 自动生成 Agent |
| `agent_run` | `name` | 运行指定 Agent |

### 插件调用（命令方式）

自定义插件通过命令方式调用：

```
【命令：/插件名 参数】
```

### 旧格式兼容

兼容早期模型的 `file_operations` 换行分隔格式：

```
file_operations
/write file.md "内容"
```

---

## 插件系统

### 自动进化

当 AI 回复中包含完整的插件结构时（同时包含 `def run(args='')` 和 ````python` 代码块），程序会提示是否保存为插件：

```
⚡ 检测到法宝结构，赐名 (回车放弃): my_tool
✅ 法宝铸造: /my_tool
```

### 插件目录

插件保存在：`~/.zhipu_cli_plugins/`

### 插件调用

```
/my_tool 参数
```

### 插件约定

```python
def run(args=''):
    """args 为传入的参数字符串"""
    return "处理结果"
```

### 插件安全

- 在独立子进程中执行（15 秒超时）
- 受安全确认系统保护

---

## 安全机制

### 四阶安全确认

对危险操作（文件写入、命令执行、邮件发送、Shell 等），系统会提示：

```
⚠️ 检测到高危神通，请选择因果:
[Y]仅此  [A]本轮  [F]永世  [N]拒绝
```

| 选项 | 说明 |
|------|------|
| `Y` | 仅允许本次操作 |
| `A` | 本次会话内允许同类操作 |
| `F` | 永久允许同类操作（写入配置） |
| `N` | 拒绝本次操作 |

### 受保护的操作类型

| 操作键 | 说明 |
|--------|------|
| `sec_read` | 读取卷轴（文件） |
| `sec_write` | 写入法宝（文件写入/删除） |
| `sec_exec` | 执行法宝（插件/定时任务） |
| `sec_mount` | 开辟洞府（添加目录） |
| `sec_gen_img` | 祭炼画卷（生成图片） |
| `sec_send_mail` | 发送邮件 |
| `sec_fetch_web` | 抓取互联网 |
| `sec_upload_disk` | 上传至云端 |
| `sec_download_disk` | 下载自云端 |
| `sec_shell` | 执行系统命令 |

### 目录穿越防护

VFS 虚拟文件系统通过 `Path.resolve()` 检查目标路径是否仍在 `allowed_dirs` 列表内，防止 `../` 攻击。

---

## 常见问题

### Q1: 如何获取智谱 AI API Key？

访问 [智谱开放平台](https://open.bigmodel.cn/)，注册账号后在「API Keys」页面创建。

### Q2: 邮件发送失败？

- QQ/163 邮箱需使用「授权码」而非登录密码
- 授权码在邮箱设置 → 账户 → 开启 IMAP/SMTP 服务后生成
- 确认 IMAP/SMTP 服务器地址正确

### Q3: 搜索功能无法使用？

```bash
pip install requests
```

### Q4: 云盘功能无法使用？

```bash
pip install fr-cli[aliyun]   # 阿里云 OSS
pip install fr-cli[baidu]    # 百度网盘
pip install fr-cli[onedrive] # OneDrive
```

### Q5: 如何查看某功能的详细帮助？

```
/help config      # 配置相关
/help fs          # 文件操作
/help session     # 会话管理
/help mail        # 邮件功能
/help cron        # 定时任务
/help web         # 网络搜索
/help disk        # 云盘
/help vision      # 图像功能
/help shell       # 系统命令
/help tools       # AI 工具调用
/help security    # 安全机制
```

### Q6: 程序文件和数据保存在哪里？

| 路径 | 说明 |
|------|------|
| `~/.zhipu_cli_config.json` | 主配置文件 |
| `~/.zhipu_cli_history/` | 会话历史记录 |
| `~/.zhipu_cli_plugins/` | 用户插件目录 |
| `~/.zhipu_cli_context.json` | 上下文记忆 |
| `~/.fr_cli_agents/` | Agent 分身目录 |
| `~/.fr_cli_remotes.json` | 远程主机配置 |
| `~/.fr_cli_databases.json` | 数据库连接配置 |
| `~/.fr_cli_rag_db/` | RAG 向量库（ChromaDB）|

---

*本文档由 凡人打字机 自动生成，如有更新请以最新版本为准。*
