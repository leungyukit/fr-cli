# 凡人打字机 (fr-cli) 功能使用手册

## 目录

1. [快速开始](#快速开始)
2. [基础命令](#基础命令)
3. [模型管理](#模型管理)
4. [Hermes 核心功能](#hermes-核心功能)
5. [Shell 模式](#shell-模式)
6. [MCP 支持](#mcp-支持)
7. [ACP 协议](#acp-协议)
8. [Agent 系统](#agent-系统)
9. [工具使用](#工具使用)
10. [安全设置](#安全设置)

---

## 快速开始

### 安装

```bash
pip install fr-cli
```

### 启动

```bash
fr-cli
# 或
python3 main.py
```

首次运行会引导配置 API Key。

---

## 基础命令

### 交互命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `/ls` | 列出文件 | `/ls` |
| `/cat <file>` | 查看文件 | `/cat main.py` |
| `/cd <dir>` | 切换目录 | `/cd src` |
| `/write <file>` | 写入文件 | `/write test.py` |
| `/delete <file>` | 删除文件 | `/delete temp.txt` |
| `/search <query>` | 联网搜索 | `/search python教程` |
| `/help` | 显示帮助 | `/help` |
| `/exit` | 退出程序 | `/exit` |

### 文件操作

```bash
# 查看文件
/cat README.md

# 写入多行文件
/write new_module.py
# 输入内容...
# Ctrl+D 结束

# 切换目录
/cd /path/to/project

# 删除文件
/delete temp.log
```

---

## 模型管理

### 切换模型

```bash
# 切换到 Kimi K2
/model kimi-k2

# 切换到 DeepSeek
/model deepseek

# 切换到 Kimi Code
/model kimi-code

# 同时指定道统和模型
/model kimi:moonshot-v1-8k
```

### 配置 API Key

```bash
# 修改当前道统 Key
/key your-new-api-key

# 为指定道统设置 Key
/key kimi your-api-key

# 查看所有道统
/providers

# 添加新道统
/providers add minimax <your-key>

# 使用指定道统
/providers use deepseek
```

### 支持的模型

| 道统 | 模型 | 用途 |
|------|------|------|
| zhipu | glm-4-flash | 通用对话 |
| kimi | moonshot-v1-8k | 通用对话 |
| kimi-k2 | kimi-k2-0905-preview | 代码优化 |
| kimi-code | kimi-for-coding | Kimi 代码平台 |
| deepseek | deepseek-chat | 编程辅助 |
| qwen | qwen-turbo | 通用对话 |
| step-3 | step-3-auto | 高级推理 |
| minimax-m27 | MiniMax-M2.7 | Token Plan |

---

## Hermes 核心功能

Hermes 是自我进化的 AI 助手核心模块。

### 任务管理

```python
from fr_cli.agent.hermes import get_task_manager

# 创建任务
tm = get_task_manager()
task = tm.create_task("完成代码审查")

# 获取任务
task = tm.get_task("task-1")

# 完成任务
tm.complete_task("task-1", "审查完成，未发现问题")

# 列出所有任务
tasks = tm.list_tasks()

# 查看历史
history = tm.list_history(limit=50)
```

### 分析统计

```python
from fr_cli.agent.hermes import get_analytics

an = get_analytics()

# 记录请求
an.record_request("glm-4-flash", 1000, 0.01)

# 记录任务
an.record_task(success=True)

# 获取统计
stats = an.get_stats()
print(stats)

# 格式化报告
print(an.format_report())
```

### 目标追踪

```python
from fr_cli.agent.hermes import GoalTracker

gt = GoalTracker()

# 设置目标
gt.set_goal("完成项目开发", ["需求分析", "编码", "测试", "部署"])

# 更新进度
gt.update_progress("已完成需求分析", 0.25)

# 完成目标
gt.complete_goal()
```

### 配置管理

```python
from fr_cli.agent.hermes import get_config_manager

cm = get_config_manager()

# 设置配置
cm.set("model.default", "glm-4-flash")
cm.set("theme.color", "blue")

# 获取配置
model = cm.get("model.default")
theme = cm.get("theme.color")

# 保存配置
cm.save()
```

### 🎯 Skills 技能系统

AI 从经验中学习，自动创建可重用的技能。你只需要告诉 Agent：

```
学习这个功能
把这个技能记下来
下次遇到这种问题用这个方法
```

Agent 会自动调用 Skills 系统保存知识。

### 👤 个性系统

通过对话切换 AI 个性：

```
切换到编程模式
我想让你当老师
用创意助手的风格

### 定时任务

```python
from fr_cli.agent.hermes import get_cron_scheduler

cron = get_cron_scheduler()

# 添加定时任务
cron.add_job("daily-report", "0 9 * * *", "生成日报")

# 列出任务
jobs = cron.list_jobs()

# 移除任务
cron.remove_job("daily-report")

# 手动运行任务
cron.run_job("daily-report")
```

---

## Shell 模式

按 `Ctrl-X` 切换 Agent/Shell 模式。

### Agent 模式

- 输入消息与 AI 对话
- AI 自动调用工具完成任务

### Shell 模式

- 直接执行 shell 命令
- 无需离开 AI 对话界面

```
(shell) $ ls -la
(shell) $ git status
(shell) $ exit  # 退出 shell 模式
```

---

## MCP 支持

MCP (Model Context Protocol) 扩展工具支持。

### 管理 MCP 服务器

```bash
# 列出所有 MCP 服务器
/mcp_list

# 添加 stdio 服务器
/mcp_add fs npx -y @modelcontextprotocol/server-filesystem /tmp

# 添加 HTTP 服务器
/mcp_add context7 --transport http https://mcp.context7.com/mcp

# 删除服务器
/mcp_del fs

# 刷新工具列表
/mcp_refresh
```

### MCP 配置文件

创建 `~/.fr_cli/mcp.json`:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    },
    "context7": {
      "url": "https://mcp.context7.com/mcp",
      "headers": {
        "CONTEXT7_API_KEY": "your-key"
      }
    }
  }
}
```

---

## ACP 协议

ACP (Agent Client Protocol) 集成到 IDE。

### 启动 ACP 服务

```bash
fr acp
```

### Zed 配置

编辑 `~/.config/zed/settings.json`:

```json
{
  "agent_servers": {
    "fr-cli": {
      "type": "custom",
      "command": "fr",
      "args": ["acp"],
      "env": {}
    }
  }
}
```

### VS Code 配置

安装 Kimi Code VS Code Extension，然后在设置中添加:

```json
{
  "agent_servers": {
    "fr-cli": {
      "command": "fr",
      "args": ["acp"]
    }
  }
}
```

---

## 🌐 Gateway 消息网关

通过 Telegram、Discord 等 IM 工具与 AI 对话！

### 配置 Telegram

```python
from fr_cli.agent.gateway import GatewayManager

gm = GatewayManager()
gm.configure_telegram("your-telegram-bot-token")
```

### 配置 Discord

```python
from fr_cli.agent.gateway import GatewayManager

gm = GatewayManager()
gm.configure_discord("your-discord-bot-token")
```

### 启动网关

```bash
# 启动 Telegram Bot
fr gateway start telegram

# 启动 Discord Bot
fr gateway start discord

# 启动所有平台
fr gateway start
```

### 查看已配置平台

```bash
fr gateway setup
```

### Gateway 工作原理

```
用户 (Telegram/Discord)
    ↓ 发送消息
fr-cli Gateway
    ↓
AI 处理 (fr-cli core)
    ↓
回复用户
```

### 支持的平台

| 平台 | 状态 | 说明 |
|------|------|------|
| Telegram | ✅ | Bot 模式 |
| Discord | ✅ | Bot 模式 |
| Slack | 🔜 | 计划中 |
| WhatsApp | 🔜 | 计划中 |

---

## Agent 系统

### 创建 Agent

```bash
/agent_create coder "Python 代码助手，擅长编写高质量 Python 代码"
/agent_create reviewer "代码审查助手，发现潜在问题和优化点"
```

### 管理 Agent

```bash
# 列出所有 Agent
/agent_list

# 查看 Agent 详情
/agent_show myagent

# 编辑 Agent 人设
/agent_edit myagent persona

# 设置 Agent 专属模型
/agent_model myagent kimi-k2:moonshot-v1-8k

# 运行 Agent
/agent_run myagent "帮我写个排序算法"

# 删除 Agent
/agent_delete oldagent
```

### 内置 Agent

```bash
@local 查看目录结构          # 本地系统操作
@spider https://example.com 2  # 智能爬虫
@db mydb 查询SQL             # 数据库助手
@RAG 什么是向量数据库         # 本地知识库
```

### Agent HTTP API

```bash
# 启动 API 服务
/agent_server start 8080

# API 端点
POST http://localhost:8080/chat
{
  "message": "你好",
  "agent": "coder"
}
```

---

## 工具使用

### Web 搜索

```bash
/search Python 教程
/search 最新 AI 新闻
```

### 数据库

```bash
@db mydb SELECT * FROM users LIMIT 10
@db mydb 显示表结构
```

### 文件读写

```bash
/cat config.json
/write data.json
{"key": "value"}
# Ctrl+D 结束
```

### Excel/CSV

```bash
/read_excel report.xlsx
/read_csv data.csv
```

---

## 安全设置

### 目录限制

```bash
/dir /workspace/project
/dir /home/user/docs
/dirs  # 列出已挂载目录
/rmdir 1  # 删除第1个挂载目录
```

### Token 限制

```bash
/limit 2000  # 设置最大 Token 数
/security  # 查看安全设置
```

---

## Zsh 集成

安装 Zsh 插件:

```bash
git clone https://github.com/yourname/zsh-fr-cli.git \
  ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/fr-cli
```

编辑 `~/.zshrc`:

```bash
plugins=(... fr-cli)
```

功能:
- `Ctrl-X` 切换 Agent/Shell 模式
- `fr-start` 启动 fr-cli

---

## 配置目录

| 路径 | 说明 |
|------|------|
| `~/.fr_cli/` | 配置根目录 |
| `~/.fr_cli/config.json` | 主配置文件 |
| `~/.fr_cli/models.yaml` | 模型配置 |
| `~/.fr_cli/mcp.json` | MCP 服务器配置 |
| `~/.fr_cli/memory/` | 记忆数据 |
| `~/.fr_cli/sessions/` | 会话存档 |

---

## 常见问题

### Q: 如何切换思维模式?
```bash
/mode direct   # 直接回复
/mode cot      # 思维链
/mode tot      # 思维树
/mode react    # ReAct
```

### Q: 如何保存会话?
```bash
/save my-session
/load
/export
```

### Q: 如何查看历史记录?
```bash
/history
/history 2024-01-15
```

---

**版本**: 2.2.9
**更新**: 2025-04-29