# 凡人打字机 (fr-cli)

**支持 27+ 种 AI 模型（智谱/智谱Coding/DeepSeek/Kimi/Kimi K2/Kimi Code/StepFun/Step-3/MiniMax/M2.7/讯飞星火/豆包/MiMo/LongCat）的终极全能终端工具。**

**集成 Hermes Agent 核心功能：自我进化的 AI 助手。**

## ✨ 功能特性

### 🤖 多模型支持
支持以下 AI 模型提供商：
- **智谱 AI**: GLM-4-Flash 等
- **智谱 Coding Plan**: GLM-4.7 等 (https://docs.bigmodel.cn/cn/coding-plan/quick-start)
- **OpenAI**: GPT-4o / GPT-4o-mini / o1-mini / o3-mini 等（标准 OpenAI 接口）
- **DeepSeek**: DeepSeek-Chat 等
- **Kimi (Moonshot)**: moonshot-v1-8k 等
- **Kimi K2**: 代码优化版 kimi-k2-0905-preview
- **Kimi Code**: 代码平台 kimi-for-coding (Kimi 会员)
- **通义千问 (Qwen)**: qwen-turbo 等
- **阶跃星辰 (StepFun)**: step-1-8k, step-2-16k, step-3-auto 等
- **Step-Audio**: 实时语音交互
- **MiniMax**: MiniMax-Text-01 等
- **MiniMax M2.7**: Token Plan 订阅模型
- **讯飞星火 (Spark)**: generalv3.5 等
- **豆包 (Doubao)**: doubao-1-5-pro-32k 等
- **小米 MiMo**: mimo-v2-flash 等
- **LongCat (龙猫)**: LongCat-Flash-Chat 等 (https://longcat.chat/platform/docs/zh/)

### 🧠 核心功能
- **MasterAgent 主控**：自我进化的 ReAct 主控 Agent，自动规划、调用工具、反思进化
- **Agent2Agent Protocol (A2A)**：Agent 互操作协议，支持 Agent 发现、注册、任务委托
- **思维模式**：direct / CoT / ToT / ReAct 四种推理模式切换
- **文件沙盒**：安全的虚拟文件系统，支持读写/目录操作
- **联网搜索**：内置 Web 搜索与网页内容提取（SSRF 防护）

### 🎯 特色功能
- **视觉能力**：图片生成 (CogView) 与多模态识别 (GLM-4V)
- **邮件收发**：支持 IMAP/SMTP 与 Microsoft 365 现代认证（OAuth2 + MFA，防头注入）
- **定时任务**：后台定时执行命令（shlex 安全解析）
- **云盘集成**：百度/阿里/OneDrive 网盘
- **插件系统**：AI 生成代码自动保存为插件（子进程隔离）
- **会话记忆**：自动保留最近 5 轮对话摘要 + 按日期自动存档
- **Agent 分身系统**：AI 自动生成 Agent，支持工作流编排
- **Agent HTTP API**：将 Agent 发布为 REST API 供外部调用
- **本机应用启动**：一键调用浏览器、微信、Word、WPS 等本地程序
- **内置 Agent**：`@local` `@remote` `@spider` `@db` `@RAG`
- **数据卷轴**：Excel / CSV 读取与智能分析
- **数据库助手**：MySQL / PostgreSQL / SQL Server / Oracle 智能 SQL 生成
- **本地 RAG**：ChromaDB 向量库 + 自动文件监控与向量化
- **MCP 外部神通**：支持 Model Context Protocol
- **多源信息融合**：大模型 + 工具结果统一汇总
- **中英文切换**：完整国际化支持
- **NO_COLOR 支持**：`NO_COLOR=1` 禁用所有 ANSI 颜色，适合 CI/管道环境

## 🚀 快速开始

```bash
# 安装
pip install fr-cli

# 启动
fr-cli

# 或从源码运行
cd fr-cli
pip install -e .
fr-cli
```

首次运行会引导输入当前道统的 API Key。直接回车可进入 Mock 模式试用。

## 📝 使用方法

### 📋 常用命令

```
/ls                 列出当前目录文件
/cat <file>         查看文件内容
/cd <dir>           切换工作目录
/write <file>       写入文件（多行输入，Ctrl+D 结束）
/delete <file>     删除文件
/search <query>     联网搜索
/save <name>        保存会话
/load               加载历史会话
/export             导出会话为 Markdown

/model <模型名>              切换AI模型（仅当前会话生效）
/model <道统>:<模型名>       同时切换道统和模型
/model config               🆕 交互式模型配置向导
/model list                 列出所有可用模型
/model current              显示当前模型
/model default              恢复 factory 默认模型
/key <key>                   修改当前道统 API Key
/key <道统> <key>            为指定道统设置 Key
/providers                   查看所有道统配置
/providers setup            交互式配置向导
/providers add <p> <k> [m]   添加/更新道统配置
/providers use <p>           切换到指定道统

/mode direct|cot|tot|react   切换思维模式
/master on|off|status       MasterAgent 主控
/mcp_list                   列出 MCP 服务器及工具
/mcp_add <名> <命令> [参数]  添加 MCP 服务器
/mcp_del <名>               删除 MCP 服务器

/mail setup        配置 IMAP/SMTP 邮箱
/mail inbox        查看收件箱
/mail read <id>    读取邮件
/mail send <to> <sub> <body>   发送邮件
/m365_config setup 配置 Microsoft 365 邮箱（OAuth2 + MFA）
/m365_inbox        查看 Microsoft 365 收件箱
/m365_read <id>    读取 Microsoft 365 邮件
/m365_send <to> <sub> <body>   发送 Microsoft 365 邮件

/help              查看帮助
/exit              退出
```

### 🖥️ 非交互 / 批处理模式

fr-cli 支持在不进入 REPL 的情况下执行单次命令或单次 AI 对话，适用于脚本、cron、管道等场景：

```bash
# 执行一条 slash 命令后退出
fr-cli -c "/model current"
fr-cli -c "/ls"

# 向 AI 提问后退出
fr-cli "请总结 README.md"
fr-cli -p "Python 如何读取 JSON？"

# 从文件或标准输入读取提示词
cat article.txt | fr-cli -s
fr-cli -f prompt.txt

# 静默模式（跳过启动 banner，只输出核心结果）
fr-cli -q -c "/model current"
fr-cli -q -p "1+1等于几"
```

### 🤖 AI 模型配置

```bash
# 交互式配置向导（推荐）
>>> /model config

# 直接切换（仅当前会话生效，重启后恢复 factory 默认）
>>> /model deepseek-chat
>>> /model deepseek:deepseek-reasoner

# 查看当前模型
>>> /model current

# 恢复 factory 默认模型
>>> /model default

# 配置新的 API Key
>>> /providers add step-3 <your-api-key>
```

### 🔧 Agent 管理

```
/agent_create coder "编写Python代码的助手"  # 创建 Agent
/agent_list                                    # 列出所有 Agent
/agent_show myagent                            # 查看 Agent 详情
/agent_edit myagent persona                    # 编辑 Agent 人设
/agent_run myagent "帮我写个排序算法"          # 运行 Agent
/agent_delete oldagent                          # 删除 Agent
/agent_server start 8080                        # 启动 HTTP API
```

### 🔗 MCP 外部神通

```
/mcp_list                  # 列出已配置的 MCP 服务器
/mcp_add fs npx -y @modelcontextprotocol/server-filesystem /tmp
/mcp_del fs                # 删除 MCP 服务器
/mcp_refresh               # 刷新工具列表
```

### 📊 数据处理

```
/read_excel report.xlsx    # 读取 Excel
/read_csv data.csv         # 读取 CSV
```

### 🧑‍💻 内置 Agent

```
@local 查看当前目录最大的5个文件    # 本地系统操作
@spider https://example.com 2        # 智能爬虫
@db mydb 查询最近7天注册用户         # 数据库助手
@RAG 什么是向量数据库                # 本地知识库问答
```

### 🛡️ 安全命令

```
/limit <n>        设置 Token 上限 (最小1000)
/dir <path>       添加允许访问的目录
/dirs             列出已挂载的工作目录
/rmdir <索引>     删除已挂载的目录
/security        查看安全设置
```

## 🧠 Hermes 核心功能

### 📋 任务管理
```
from fr_cli.agent.hermes import get_task_manager, get_analytics

# 创建任务
tm = get_task_manager()
task = tm.create_task("完成代码审查")

# 记录分析
an = get_analytics()
an.record_request("glm-4-flash", 1000, 0.01)
```

### 🎯 目标追踪
```
from fr_cli.agent.hermes import GoalTracker

gt = GoalTracker()
gt.set_goal("完成项目", ["阶段1", "阶段2", "阶段3"])
gt.update_progress("已完成阶段1", 0.33)
```

### ⏰ 定时任务
```
from fr_cli.agent.hermes import get_cron_scheduler

cron = get_cron_scheduler()
cron.add_job("daily-report", "0 9 * * *", "生成日报")
```

### 🔌 插件系统
```
from fr_cli.agent.plugin_system import get_plugin_registry

registry = get_plugin_registry()
plugins = registry.list_all()
```

### 🐚 Shell 模式 (Ctrl-X 切换)
```
Agent 模式: 输入消息与 AI 对话
Shell 模式: 直接执行 shell 命令

按 Ctrl-X 切换模式
```

### 🔗 ACP (Agent Client Protocol)
```bash
# 启动 ACP 服务
fr acp

# 配置到 Zed
# ~/.config/zed/settings.json
{
  "agent_servers": {
    "fr-cli": {
      "command": "fr",
      "args": ["acp"]
    }
  }
}
```

## 🤖 支持的模型提供商（25+）

| 道统 | 默认模型 | API 地址 | 常用模型 |
|------|---------|----------|---------|
| zhipu | glm-4-flash | open.bigmodel.cn/api/paas/v4 | glm-4-flash, glm-4-plus, glm-4, glm-4v-plus, glm-4-air, glm-4-long |
| zhipu-coding | GLM-4.7 | open.bigmodel.cn/api/coding/paas/v4 (Coding Plan) | GLM-4.7, GLM-5.1, GLM-4.5-air |
| zhipu-anthropic | glm-4.6 | open.bigmodel.cn/api/anthropic | glm-4.6 |
| openai | gpt-4o-mini | api.openai.com/v1 | gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo, o1-mini, o3-mini |
| deepseek | deepseek-chat | api.deepseek.com | deepseek-chat, deepseek-reasoner, deepseek-coder |
| kimi | moonshot-v1-8k | api.moonshot.cn | moonshot-v1-8k, moonshot-v1-32k, moonshot-v1-128k |
| kimi-k2 | kimi-k2-0905-preview | api.moonshot.cn | kimi-k2-0905-preview |
| kimi-code | kimi-for-coding | api.kimi.com/coding/v1 | kimi-for-coding |
| qwen | qwen-turbo | dashscope.aliyuncs.com | qwen-turbo, qwen-plus, qwen-max, qwen-coder-plus |
| stepfun | step-1-8k | api.stepfun.com (api.stepfun.com/step_plan/v1 for Step Plan) | step-1-8k, step-1-32k, step-2-16k, step-3-auto |
| step-1 | step-1-8k | api.stepfun.com | step-1-8k |
| step-2 | step-2-16k | api.stepfun.com | step-2-16k |
| step-3 | step-3-auto | api.stepfun.com | step-3-auto |
| step-audio | step-audio-2 | api.stepfun.com | step-audio-2 |
| stepfun-step-plan | step-3-auto | api.stepfun.com/step_plan/v1 (Step Plan) | step-3-auto, step-2-16k, step-1-8k |
| minimax | MiniMax-Text-01 | api.minimax.io (api.minimax.chat for Token Plan) | MiniMax-Text-01, MiniMax-M2.1, abab6.5s-chat, abab6.5t-chat |
| minimax-m27 | MiniMax-M2.7 | api.minimax.chat (Token Plan) | MiniMax-M2.7 |
| minimax-m27-fast | MiniMax-M2.7-HighSpeed | api.minimax.chat (Token Plan) | MiniMax-M2.7-HighSpeed |
| minimax-token-plan | MiniMax-M2.7 | api.minimax.chat (Token Plan) | MiniMax-M2.7 |
| spark | generalv3.5 | spark-api-open.xf-yun.com | generalv3.5 |
| doubao | doubao-1-5-pro-32k-250115 | ark.cn-beijing.volces.com | doubao-1-5-pro-32k, doubao-1-5-lite-32k |
| mimo | mimo-v2-flash | api.xiaomimimo.com | mimo-v2-flash, mimo-v2-pro |
| mimo-token-plan | mimo-v2-flash | token-plan-sgp.xiaomimimo.com (Token Plan) | mimo-v2-flash, mimo-v2-pro |
| longcat | LongCat-Flash-Chat | api.longcat.chat/openai | LongCat-Flash-Chat |
| longcat-anthropic | LongCat | api.longcat.chat/anthropic | LongCat |

## 🔧 开发

```bash
# 克隆项目
git clone https://github.com/yourname/fr-cli.git
cd fr-cli

# 安装开发依赖
pip install -e ".[all]"

# 运行测试
python3 -m pytest tests/ -v

# 运行程序
fr-cli
```

### 环境变量

| 变量 | 说明 |
|------|------|
| `NO_COLOR=1` | 禁用所有 ANSI 颜色输出，适合 CI/管道/日志重定向 |
| `FR_CLI_DEBUG=1` | 开启调试模式，显示详细 traceback |
| `FR_CLI_NON_INTERACTIVE=1` | 非交互模式，安全确认默认拒绝 |

## 📂 项目结构

```
fr_cli/
├── main.py              # 核心入口
├── agent/                # Agent 系统
│   ├── a2a.py           # Agent2Agent 协议
│   ├── master.py        # MasterAgent 主控
│   └── ...
├── core/                 # 核心模块
│   ├── llm.py           # LLM 客户端（20+ 提供商）
│   └── model_factory.py # 模型工厂配置
├── weapon/              # 武器库
├── memory/              # 记忆系统
└── lang/                # 国际化
```

## 📚 文档

- [AGENTS.md](AGENTS.md) - 面向 AI 编码助手的项目架构与开发指南

## 📂 配置目录

> 配置统一在 `~/.fr_cli/` 目录下，旧路径（如 `~/.zhipu_cli_config.json`）会在首次启动时自动迁移到新路径。

| 路径 | 说明 |
|------|------|
| `~/.fr_cli/config.json` | 主配置文件（统一配置目录） |
| `~/.fr_cli/config.json.bak` | 配置自动备份 |
| `~/.fr_cli/history/` | 会话历史记录 |
| `~/.fr_cli/context.json` | 上下文记忆 |
| `~/.fr_cli/sessions/` | 按日期自动存档的会话 |
| `~/.fr_cli/plugins/` | 用户插件目录 |
| `~/.fr_cli/agents/` | Agent 分身目录 |
| `~/.fr_cli/master/` | MasterAgent 记忆与进化记录 |
| `~/.fr_cli/remotes.json` | 远程主机配置 |
| `~/.fr_cli/databases.json` | 数据库连接配置 |
| `~/.fr_cli/rag_db/` | RAG 向量库（ChromaDB）|

## ❓ 常见问题

**Q: 如何切换思维模式?**
```bash
/mode direct   # 直接回复
/mode cot      # 思维链
/mode tot      # 思维树
/mode react    # ReAct
```

**Q: 模型切换后重启又变回去了？**
这是预期行为。fr-cli 每次启动从 `model_factory.py` 的工厂配置读取默认模型，`/model` 切换仅当前会话生效。如需持久化切换默认模型，可修改 `fr_cli/core/model_factory.py` 中的默认模型，或使用 `/providers setup` 交互式配置向导。

**Q: 如何配置模型？**
```bash
# 推荐：交互式向导
/model config

# 或
/providers setup
```

**Q: 如何保存会话?**
```bash
/save my-session
/load
/export
```

**Q: 如何查看历史记录?**
```bash
/history
/session_list
```

**Q: 邮件发送失败?**
- QQ/163 邮箱需使用「授权码」而非登录密码
- 授权码在邮箱设置 → 账户 → 开启 IMAP/SMTP 服务后生成

**Q: Microsoft 365 / Outlook 邮箱如何使用?**
Microsoft 365 已禁用基本认证，需使用 OAuth2 现代认证：
1. 在 Azure AD 注册应用，添加 `Mail.Read`、`Mail.Send`、`User.Read` 委派权限
2. 复制 Application (client) ID 和 Directory (tenant) ID
3. 执行 `/m365_config setup`，按向导完成设备码或授权码登录（支持 MFA）
4. 之后使用 `/m365_inbox`、`/m365_read <id>`、`/m365_send <to> <sub> <body>`

Token 缓存于 `~/.fr_cli/m365.json`，文件权限 `0o600`。

**Q: 搜索功能无法使用?**
```bash
pip install requests
```

**Q: 云盘功能无法使用?**
```bash
pip install aligo   # 阿里云盘
```
首次使用需运行 `/disk_setup` 完成扫码登录。

## 📄 License

MIT
