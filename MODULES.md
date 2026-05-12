# fr-cli 功能使用指南

## 目录

1. [Shell 模式](#1-shell-模式)
2. [模型切换](#2-模型切换)
3. [AI 自我学习](#3-ai-自我学习)
4. [AI 个性切换](#4-ai-个性切换)
5. [MCP 扩展工具](#5-mcp-扩展工具)
6. [IDE 集成](#6-ide-集成)
7. [消息网关](#7-消息网关)
8. [文件操作](#8-文件操作)
9. [网络搜索](#9-网络搜索)
10. [Agent 分身](#10-agent-分身)
11. [技能系统](#11-技能系统)

---

## 1. Shell 模式

### 功能
在 AI 对话中直接执行命令行，无需离开。

### 使用方法

```
> /shell
🆗 进入 Shell 模式

(shell) $ ls -la
(shell) $ git status
(shell) $ python3 main.py
(shell) $ exit
```

### 常用命令

```bash
(shell) $ pwd                    # 当前目录
(shell) $ cd project            # 切换目录
(shell) $ git status            # Git 状态
(shell) $ pip install xxx       # 安装包
(shell) $ npm run dev           # 运行项目
```

### 退出
输入 `exit` 或 `quit` 返回 AI 对话模式。

---

## 2. 模型切换

### 功能
在多个 AI 模型之间切换，获得不同能力。

### 使用方法

```bash
> /model kimi-k2
✅ 已切换: [kimi-k2] moonshot-v1-8k

> /model deepseek
✅ 已切换: [deepseek] deepseek-chat

> /model kimi-code
✅ 已切换: [kimi-code] kimi-for-coding
```

### 支持的模型

| 模型 | 用途 | 特点 |
|------|------|------|
| zhipu | 通用对话 | 免费额度 |
| kimi | 通用对话 | 长上下文 |
| kimi-k2 | 代码优化 | Kimi 代码版 |
| kimi-code | Kimi 代码平台 | Kimi 会员 |
| deepseek | 编程辅助 | 性价比高 |
| qwen | 通用对话 | 阿里云 |
| minimax | 长文本 | Token Plan |

---

## 3. AI 自我学习

### 功能
AI 会自动记住你的偏好和知识，下次遇到类似问题会更快解决。

### 使用方法

```
> 记住 Python 虚拟环境创建方法
✅ 已学习：python-venv 使用方法

> 这个排序算法很好，记住它
✅ 已保存到技能库

> 下次遇到这种问题用这个方法
✅ 已记住，下次优先使用
```

### AI 自动学习
- 当你认可 AI 的回答时，AI 会自动记住
- 当你重复问类似问题时，AI 会使用之前学到的知识

---

## 4. AI 个性切换

### 功能
让 AI 以不同的风格回答问题。

### 使用方法

```
> 切换到编程模式
✅ 已切换到 coder 个性

> 用老师的语气解释这个概念
✅ 已切换到 teacher 个性

> 用创意助手的风格写一首诗
✅ 已切换到 creative 个性
```

### 个性类型

| 个性 | 特点 | 适用场景 |
|------|------|----------|
| coder | 编程专家 | 代码、调试、技术问题 |
| teacher | 耐心的教师 | 学习新知识、解释概念 |
| reviewer | 严格的审查员 | 代码审查、安全检查 |
| expert | 领域专家 | 架构设计、技术选型 |
| creative | 创意助手 | 头脑风暴、写作 |

---

## 5. MCP 扩展工具

### 功能
连接外部工具，扩展 AI 能力。

### 使用方法

```bash
> /mcp_list
当前 MCP 服务器：无

> /mcp_add fs npx -y @modelcontextprotocol/server-filesystem /tmp
✅ 已添加 MCP 服务器: fs

> /mcp_add context7 https://mcp.context7.com/mcp
✅ 已添加 MCP 服务器: context7
```

### 常用 MCP 服务器

| 服务器 | 命令 | 用途 |
|--------|------|------|
| filesystem | npx -y @modelcontextprotocol/server-filesystem | 读写本地文件 |
| context7 | https://mcp.context7.com/mcp | 搜索最新文档 |

---

## 6. 服务器对比

### 三种服务器的区别

| 命令 | 功能 | 端口 | 用途 |
|------|------|------|------|
| `/hermes start` | Hermes 守护进程 | 8765 | 任务/技能/目标/统计管理 |
| `/agent_server start` | Agent HTTP | 17890 | 将 AI 能力发布为 API |
| `/gateway start` | 消息网关 | - | Telegram/Discord 集成 |

---

## 7. Hermes 守护进程

### 功能
将 Agent 能力发布为 Web API，供外部调用。

### 启动服务器

```
> /agent_server start
✅ Agent HTTP 服务已启动: http://localhost:17890

> /agent_server status
📡 服务运行中
   端口: 17890
   Token: xxxxxxxx
```

### 停止服务器

```
> /agent_server stop
✅ Agent HTTP 服务已停止
```

### API 调用

```bash
# 健康检查
curl http://localhost:17890/health

# 执行任务
curl -X POST http://localhost:17890/agent \
  -H "Authorization: Bearer TOKEN" \
  -d '{"message": "帮我写个快速排序"}'

# 查看状态
curl http://localhost:17890/status
```

### Zed 配置

```json
// ~/.config/zed/settings.json
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

## 7. Hermes 守护进程

### 功能
通过 Telegram、Discord 控制 AI，随时随地使用。

### Telegram 配置

```bash
> /gateway setup
📱 已配置的消息平台：
   - telegram: ✅ 启用
```

### 配置 Bot Token

```python
from fr_cli.agent.gateway import GatewayManager
gm = GatewayManager()
gm.configure_telegram("your-bot-token")
```

### 启动

```bash
> /gateway start telegram
🤖 Telegram Bot 已启动
```

---

## 8. 文件操作

### 功能
直接查看、编辑项目文件。

### 使用方法

```bash
> /ls                    # 列出文件
> /cat main.py           # 查看文件
> /cd src               # 切换目录
> /write test.py        # 创建文件
> /delete temp.txt       # 删除文件
> /search "排序"         # 搜索内容
```

### 示例

```
> /cat README.md
[显示文件内容]

> /write hello.py
[进入编辑模式，输入内容后 Ctrl+D 保存]
```

---

## 9. 网络搜索

### 功能
让 AI 搜索最新信息。

### 使用方法

```
> /search 最新 Python 特性
[AI 搜索并总结最新信息]

> 帮我查一下这个库的文档
[AI 获取最新文档]
```

---

## 10. Agent 分身

### 功能
创建专门的 AI 助手处理特定任务。

### 创建分身

```
> /agent_create coder "Python 代码助手"
✅ 分身创建成功

> /agent_create reviewer "代码审查助手"
✅ 分身创建成功
```

### 使用分身

```
> /agent_run coder "写个 Web 服务器"
[分身开始工作]

> /agent_list
📋 分身列表：
   - coder: Python 代码助手
   - reviewer: 代码审查助手
```

### 内置分身

| 分身 | 用法 | 功能 |
|------|------|------|
| @local | @local "查看目录结构" | 本地文件操作 |
| @spider | @spider https://xxx.com 2 | 爬取网页 |
| @db | @db mydb "SELECT * FROM users" | 数据库查询 |
| @RAG | @RAG "什么是向量数据库" | 本地知识库问答 |

---

## 11. 技能系统

### 功能
AI 从对话中自动学习的技能库。

### 工作原理
- 当你觉得 AI 回答很好时，说"记住这个"
- AI 会保存解决方案到技能库
- 下次遇到类似问题时自动使用

### 查看技能

```
> /skills
📚 技能列表：
   - python-venv: Python 虚拟环境
   - fastapi-crud: FastAPI CRUD 模式
   - git-rebase: Git 变基操作
```

### 自动使用
AI 遇到相关问题时自动调用已学习的技能。

---

## 12. Hermes 守护进程

### 功能
后台服务，管理任务、技能、目标和使用统计。

### 启动

```
> /hermes start
🧚 Hermes 守护进程已启动: http://127.0.0.1:8765
```

### 可用功能

| 功能 | 说明 |
|------|------|
| 任务管理 | 创建、追踪、完成任务 |
| 技能库 | AI 学习的技能存储 |
| 目标追踪 | 设置里程碑式目标 |
| 使用统计 | Token 和费用统计 |
| 命令执行 | 远程执行 shell 命令 |
| AI 对话 | 发送消息给 AI |

### API 端点

```bash
# 健康检查
curl http://127.0.0.1:8765/health

# 守护进程信息
curl http://127.0.0.1:8765/info

# 查看所有功能
curl http://127.0.0.1:8765/capabilities
```

### 任务管理

```bash
# 添加任务
curl -X POST http://127.0.0.1:8765/task \
  -d '{"task": "审查代码"}'

# 查看任务
curl http://127.0.0.1:8765/tasks
```

### 技能库

```bash
# 添加技能
curl -X POST http://127.0.0.1:8765/skill \
  -d '{"name": "python-sort", "content": "快速排序算法"}'

# 查看技能
curl http://127.0.0.1:8765/skills
```

### 目标追踪

```bash
# 设置目标
curl -X POST http://127.0.0.1:8765/goal \
  -d '{"description": "完成项目", "milestones": ["设计", "编码", "测试"]}'

# 查看目标
curl http://127.0.0.1:8765/goals
```

### 命令执行

```bash
# 执行命令
curl -X POST http://127.0.0.1:8765/execute \
  -d '{"command": "ls -la"}'
```

### 使用统计

```bash
curl http://127.0.0.1:8765/analytics
```

### 从其他终端发送命令

```bash
# 终端 2: 发送任务
curl -X POST http://127.0.0.1:8765/task \
  -H "Content-Type: application/json" \
  -d '{"task": "帮我审查代码"}'

# 发送命令执行
curl -X POST http://127.0.0.1:8765/execute \
  -H "Content-Type: application/json" \
  -d '{"command": "ls -la"}'

# 查询任务状态
curl http://127.0.0.1:8765/tasks

# 查询技能
curl http://127.0.0.1:8765/skills"

### API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/task` | POST | 添加任务 |
| `/tasks` | GET | 查看任务列表 |
| `/skill` | POST | 添加技能 |
| `/skills` | GET | 查看技能列表 |
| `/execute` | POST | 执行命令 |

### Python 调用

```python
import requests

# 添加任务
requests.post("http://127.0.0.1:8765/task", json={"task": "审查代码"})

# 执行命令
requests.post("http://127.0.0.1:8765/execute", json={"command": "ls"})

# 查看结果
requests.get("http://127.0.0.1:8765/tasks")
```

### 定时任务 (Cron)

```python
from fr_cli.agent.hermes import get_cron_scheduler

cron = get_cron_scheduler()
cron.add_job("daily-report", "0 9 * * *", "生成日报")

# 启动定时调度
# (需要配合守护进程或后台任务运行)
```

---

## 常用命令速查

| 命令 | 功能 |
|------|------|
| `/shell` | 进入命令行模式 |
| `/model <名称>` | 切换 AI 模型 |
| `/key <密钥>` | 设置 API Key |
| `/providers` | 查看所有模型 |
| `/ls` | 列出文件 |
| `/cat <文件>` | 查看文件 |
| `/cd <目录>` | 切换目录 |
| `/write <文件>` | 创建/编辑文件 |
| `/search <关键词>` | 网络搜索 |
| `/mcp_list` | 列出 MCP 服务器 |
| `/mcp_add <名> <命令>` | 添加 MCP |
| `/agent_create <名> <描述>` | 创建分身 |
| `/agent_run <名> <任务>` | 运行分身 |
| `/help` | 显示帮助 |

---

**版本**: 2.3.2
**更新**: 2025-05-08
