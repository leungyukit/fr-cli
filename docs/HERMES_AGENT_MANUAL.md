# HermesAgent 详细使用手册

> **版本**：v3.0+  
> **项目**：凡人打字机 (fr-cli)  
> **文档日期**：2026-06-21  

---

## 目录

1. [概述](#1-概述)
2. [核心概念](#2-核心概念)
3. [快速开始](#3-快速开始)
4. [REPL 命令详解](#4-repl-命令详解)
5. [HTTP API 完整参考](#5-http-api-完整参考)
6. [执行模式详解](#6-执行模式详解)
7. [目标分解与任务链](#7-目标分解与任务链)
8. [审核队列](#8-审核队列)
9. [配置与持久化](#9-配置与持久化)
10. [Python API 使用](#10-python-api-使用)
11. [架构设计](#11-架构设计)
12. [安全机制](#12-安全机制)
13. [故障排查](#13-故障排查)
14. [最佳实践](#14-最佳实践)

---

## 1. 概述

### 1.1 什么是 HermesAgent

HermesAgent（赫尔墨斯后台自治引擎）是 **fr-cli** 内置的后台任务调度与自治执行引擎。它的设计灵感来源于希腊神话中的信使神 Hermes——负责在后台默默传递信息、执行任务。

**核心能力**：
- 🔄 **持久化任务队列**：任务不随进程退出而丢失，重启后自动恢复
- 🤖 **AI 驱动执行**：每个任务通过 MasterAgent（ReAct 循环）自主调用工具完成
- 🎯 **目标自动分解**：用 LLM 将高层目标拆分为可执行的步骤链
- 🔗 **依赖与链式调度**：支持任务间的前置依赖和线性链式执行
- 🔁 **自动重试**：失败后指数退避重试，最多 3 次（可配置）
- 🧠 **跨任务记忆**：相似任务自动继承历史上下文
- 📊 **使用统计**：任务成功率、Token 消耗、模型使用分布
- 🌐 **HTTP 接口**：独立的 RESTful API，支持外部系统集成
- 🔍 **产物审核队列**：AI 自动生成的插件/Agent 代码需人工审核后方可安装

### 1.2 系统定位

```
┌─────────────────────────────────────────────────┐
│              fr-cli REPL 主界面                   │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
│  │   普通对话    │  │  / 命令交互  │  │ @Agent   │ │
│  └──────┬──────┘  └──────┬──────┘  └────┬─────┘ │
│         │                │              │        │
│         ▼                ▼              ▼        │
│  ┌─────────────────────────────────────────────┐ │
│  │              MasterAgent (主控)               │ │
│  │   ReAct 循环 → 解析工具调用 → 执行 → 反思    │ │
│  └─────────────────────┬───────────────────────┘ │
└────────────────────────┼─────────────────────────┘
                         │ 委托后台任务
                         ▼
┌─────────────────────────────────────────────────┐
│              HermesAgent 引擎                    │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
│  │ TaskManager │  │GoalTracker  │  │Analytics │ │
│  │ (任务队列)   │  │ (目标追踪)   │  │ (统计)   │ │
│  └──────┬──────┘  └──────┬──────┘  └────┬─────┘ │
│         │                │              │        │
│  ┌──────▼────────────────▼──────────────▼─────┐ │
│  │           HermesScheduler                    │ │
│  │  后台线程每 5 秒扫描 → 执行就绪任务           │ │
│  └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   ┌─────────────┐ ┌───────────┐ ┌─────────────┐
   │ 独立子进程   │ │ HTTP API  │ │ 审核队列     │
   │ hermes_daemon│ │ :8765     │ │ review_queue │
   │ _process.py  │ │ (REST)    │ │ (插件/Agent) │
   └─────────────┘ └───────────┘ └─────────────┘
```

### 1.3 存储位置

HermesAgent 的所有数据持久化在以下目录（通过 `JsonStore` 原子写入）：

```
~/.fr_cli/hermes/
├── tasks.json          # 持久化任务队列（状态、优先级、重试、结果）
├── goals.json          # 持久化目标与里程碑
├── analytics.json      # 任务执行统计
├── hermes.log          # 运行日志（追加写入）
├── memory.json         # 跨任务记忆（最近 200 条）
└── review_queue.json   # 后台产物审核队列

~/.fr_cli/daemon/
├── config.json         # 守护进程启动配置（port/host/lang）
├── pid                 # 守护进程 PID
└── stop                # 停止标记文件（存在即退出）
└── token               # HTTP Bearer Token（权限 600）
```

---

## 2. 核心概念

### 2.1 任务（Task）

任务是 Hermes 的最小执行单元。每个任务具有以下属性：

| 属性 | 类型 | 说明 |
|------|------|------|
| `id` | string | 唯一标识，格式 `hms-<8位>-<时间戳>` |
| `description` | string | 任务描述（AI 会据此执行） |
| `status` | enum | PENDING / RUNNING / COMPLETED / FAILED / PAUSED |
| `priority` | enum | LOW(1) / NORMAL(2) / HIGH(3) / CRITICAL(4) |
| `task_type` | string | adhoc / cron / goal_step / command / chat |
| `source` | string | repl / http / cron / master |
| `execution_mode` | string | sandbox / autonomous / interactive |
| `created_at` | float | Unix 时间戳 |
| `started_at` | float | 开始执行时间 |
| `completed_at` | float | 完成时间 |
| `result` | string | 执行结果（截断至 4000 字符） |
| `error` | string | 错误信息（失败时记录） |
| `retries` | int | 已重试次数 |
| `max_retries` | int | 最大重试次数（默认 3） |
| `parent_id` | string | 父任务 ID（子任务时设置） |
| `dependencies` | list | 依赖的任务 ID 列表 |
| `children_ids` | list | 子任务 ID 列表 |
| `chain_next` | string | 链式下一个任务 ID |
| `context_tags` | list | 上下文标签（用于跨任务记忆匹配） |
| `user_confirmed_at` | float | autonomous 任务用户确认时间 |

### 2.2 目标（Goal）

目标是任务的逻辑分组，可分解为多个步骤子任务：

| 属性 | 类型 | 说明 |
|------|------|------|
| `id` | string | 唯��标识，格式 `goal-<8位>-<时间戳>` |
| `description` | string | 目标描述 |
| `status` | enum | PENDING / COMPLETED / FAILED |
| `milestones` | list | 里程碑列表 |
| `progress` | float | 进度百分比（0.0 ~ 1.0） |
| `task_ids` | list | 关联的子任务 ID 列表 |

### 2.3 执行模式

Hermes 有三种执行模式，控制任务在执行时的权限和安全边界：

| 模式 | 描述 | 适用场景 | 安全级别 |
|------|------|----------|----------|
| `sandbox`（默认） | 沙盒模式，文件操作自动放行，系统操作在非交互时拒绝 | 后台常规任务 | ⭐⭐⭐ 中等 |
| `autonomous` | 完全自治模式，所有操作自动放行，但需用户显式授权 | 完全可信的自动化流程 | ⭐ 最低（需谨慎） |
| `interactive` | 交互模式，不进入后台，仅占位执行 | 临时任务，不走后台队列 | ⭐⭐⭐⭐ 高 |

### 2.4 任务优先级

| 优先级 | 值 | 说明 |
|--------|-----|------|
| LOW | 1 | 低优先级，资源空闲时执行 |
| NORMAL | 2 | 默认优先级 |
| HIGH | 3 | 高优先级，尽快执行 |
| CRITICAL | 4 | 最高优先级，立即执行 |

> **调度策略**：同一时刻，调度器优先执行高优先级任务；同优先级按创建时间升序（FIFO）。

### 2.5 审核队列（Review Queue）

当 Hermes 后台任务由 AI 自动生成了 **插件代码**（包含 `def run(args='')`）或 **Agent 代码**（包含 `def run(context, **kwargs)`）时，这些产物不会直接安装，而是进入审核队列：

- 用户可通过 `/hermes review` 查看待审核产物
- 批准后自动安装到 `~/.fr_cli/plugins/` 或 `~/.fr_cli/agents/`
- 拒绝则丢弃

---

## 3. 快速开始

### 3.1 启动 Hermes 守护进程

在 fr-cli REPL 中执行：

```
/hermes start                # 启动，默认端口 8765
/hermes start 9999           # 指定端口
/hermes status               # 查看运行状态
/hermes stop                 # 停止守护进程
```

启动成功后的输出示例：
```
🧚 Hermes 守护进程已启动: http://127.0.0.1:8765
🔑 Bearer Token: abc123xyz456...
   (已保存到 ~/.fr_cli/daemon/token，权限 600)
📡 监听命令中...
```

### 3.2 创建第一个任务

```
/hermes task 总结当前目录下的所有 Python 文件
```

输出：
```
✅ 任务已创建: hms-a1b2c3d4-1718900000 [pending]
```

查看任务状态：
```
/hermes list
```

查看任务结果（任务完成后）：
```
/hermes log hms-a1b2c3d4-1718900000
```

### 3.3 一键启动所有服务

```
/autostart
```

该命令会同时启动：
- MasterAgent（若未启用）
- Agent HTTP 服务（默认端口 17890）
- Hermes 独立 HTTP 守护进程（默认端口 8765）
- Gatekeeper 守护进程
- 同步 Cron 定时任务配置

---

## 4. REPL 命令详解

### 4.1 `/hermes start [port]`

启动独立的 Hermes 后台守护进程。

**参数**：
- `port`：可选，HTTP 监听端口，默认 `8765`

**行为**：
1. 检查是否已有守护进程在运行（通过 PID 文件检测）
2. 清理残留的 PID/停止标记文件
3. 持久化启动配置到 `~/.fr_cli/daemon/config.json`
4. 以子进程方式启动 `hermes_daemon_process.py`
5. 等待最多 3 秒确认子进程存活

**示例**：
```
/hermes start           # 默认端口 8765
/hermes start 9090      # 自定义端口
```

---

### 4.2 `/hermes stop`

停止 Hermes 守护进程。

**行为**：
1. 写入停止标记文件 `~/.fr_cli/hermes/daemon.stop`
2. 守护进程检测到标记后优雅关闭
3. 等待最多 7.5 秒，超时后发送 SIGTERM
4. 清理 PID 和停止标记文件

---

### 4.3 `/hermes status`

查看 Hermes 引擎状态报告。

**输出内容**：
```
📊 Hermes 状态
  任务: pending=2 running=0 completed=15 failed=1 paused=0
  调度器: 运行中
  成功率: 93.8%
  运行时长: 3600 秒
```

---

### 4.4 `/hermes task [--autonomous|-a] <描述>`

创建一个后台任务。

**参数**：
- `--autonomous` / `-a`：可选，以 autonomous 模式创建（需确认授权）
- `<描述>`：任务描述文本

**行为**：

1. **普通模式**（默认）：
   ```
   /hermes task 读取 README.md 并提取关键信息保存到 summary.md
   ```
   输出：
   ```
   ✅ 任务已创建: hms-xxxx-1718900000 [pending]
   ```

2. **Autonomous 模式**：
   ```
   /hermes task --autonomous 自动备份所有 .py 文件到 backup 目录
   ```
   输出：
   ```
   ⚠️  即将创建 autonomous 任务：
      描述: 自动备份所有 .py 文件到 backup 目录
      🔴 该任务将自动执行系统级操作(shell/exec/邮件/MCP 等)，不再逐条询问。
   是否确认授权? [y/N]: y
   ✅ 已授权，任务将在后台以 autonomous 模式执行。
   ✅ autonomous 任务已创建并授权: hms-xxxx-1718900001 [pending]
   ```

   若拒绝授权：
   ```
   ⏸️  任务已暂停，可稍后执行 /hermes confirm hms-xxxx-1718900001 授权。
   ```

---

### 4.5 `/hermes goal [--autonomous|-a] [--tags tag1,tag2] <描述>`

创建目标并自动分解为步骤任务。

**参数**：
- `--autonomous` / `-a`：可选，以 autonomous 模式创建子任务
- `--tags tag1,tag2`：可选，为任务添加上下文标签（用于跨任务记忆匹配）
- `<描述>`：目标描述

**行为**：
1. 调用 LLM 将目标描述分解为最多 8 个可执行步骤
2. 创建父任务（task_type="goal"）和线性链式子任务
3. 子任务之间通过 `chain_next` 链接，按顺序执行

**示例**：
```
/hermes goal --tags python,learning 学习 Python 异步编程并写一篇博客
```

输出：
```
✅ 目标已创建: goal-xxxx-1718900000
步骤:
  1. 搜索 Python asyncio 最新教程和最佳实践
  2. 整理异步编程的核心概念（event loop、coroutine、await）
  3. 编写示例代码演示 asyncio 常用模式
  4. 将博客内容保存到 blog_python_async.md
```

---

### 4.6 `/hermes confirm <id>`

确认并授权一个处于 PAUSED 状态的 autonomous 任务。

**示例**：
```
/hermes confirm hms-xxxx-1718900001
```
输出：
```
✅ 任务已授权: hms-xxxx-1718900001
```

---

### 4.7 `/hermes list [status]`

列出任务，支持按状态过滤。

**参数**：
- `status`：可选，过滤条件。可选值：`pending` / `running` / `completed` / `failed` / `paused`

**示例**：
```
/hermes list              # 列出所有任务
/hermes list pending      # 列出待执行任务
/hermes list failed       # 列出失败任务
```

输出格式：
```
任务列表 (5 个):
  ⏳ 🤖✓ hms-xxxx-1 [HIGH] [pending] 自动备份文件
  🏃 hms-xxxx-2 [NORMAL] [running]  读取README
  ✅ hms-xxxx-3 [NORMAL] [completed] 总结文档
  ❌ hms-xxxx-4 [LOW] [failed] 搜索资料（错误：网络超时）
  ⏸️  hms-xxxx-5 [NORMAL] [paused] 待授权任务
```

> **图标说明**：⏳ 等待 🏃 运行中 ✅ 完成 ❌ 失败 ⏸️ 暂停 🤖 autonomous ✓ 已授权

---

### 4.8 `/hermes log <id>`

查看任务的详细信息，包括结果和错误。

**示例**：
```
/hermes log hms-xxxx-1718900000
```

输出：
```
任务: hms-xxxx-1718900000
  状态: completed
  优先级: NORMAL
  模式: sandbox
  描述: 总结当前目录下的所有 Python 文件
  结果:
    已分析 12 个 Python 文件，核心功能包括：
    1. tello.py - Tello 无人机控制接口
    2. main.py - 主程序入口
    3. pose.py - 姿态识别模块
    ...
```

---

### 4.9 `/hermes cancel <id>`

暂停（取消）一个任务。

**说明**：这不会删除任务，而是将其状态改为 PAUSED，可通过重新授权或修改状态恢复。

**示例**：
```
/hermes cancel hms-xxxx-1718900002
```
输出：
```
✅ 任务已暂停: hms-xxxx-1718900002
```

---

### 4.10 `/hermes review`

查看后台产物审核队列。

**无参数**：列出所有待审核的产物。

```
审核队列 (2 pending / 2 total):
  review-xxxx-1 [plugin]
    建议名: auto_backup
  review-xxxx-2 [agent]
    建议名: code_reviewer
```

### 4.11 `/hermes review approve <id> [name]`

批准并安装审核队列中的产物。

**参数**：
- `id`：审核项 ID
- `name`：可选，指定安装后的名称（默认使用建议名称）

**示例**：
```
/hermes review approve review-xxxx-1 backup_tool
```

### 4.12 `/hermes review reject <id>`

拒绝审核队列中的产物。

**示例**：
```
/hermes review reject review-xxxx-2
```

---

## 5. HTTP API 完整参考

Hermes 守护进程暴露了一套完整的 RESTful API，默认监听 `http://127.0.0.1:8765`。

### 5.1 认证

所有写操作端点（POST/PUT/DELETE/PATCH）需要 Bearer Token 认证：

```http
Authorization: Bearer <token>
```

Token 存储在 `~/.fr_cli/daemon/token`，文件权限为 `0o600`（仅所有者可读写）。  
首次启动时自动生成随机 Token（`secrets.token_urlsafe(24)`）。

> ⚠️ **安全提示**：不要泄露 Token，任何持有 Token 的客户端都可以创建和管理任务。

### 5.2 健康检查

```http
GET /health
```

**响应**：
```json
{
  "status": "ok",
  "daemon": "hermes",
  "version": "2.5.1",
  "engine_ready": true
}
```

### 5.3 引擎信息

```http
GET /info
```

**响应**：
```json
{
  "daemon": "hermes",
  "version": "2.5.1",
  "tasks": {
    "pending": 2,
    "running": 0,
    "completed": 15,
    "failed": 1,
    "paused": 0
  },
  "goals": 3,
  "analytics": {
    "total_requests": 18,
    "total_tokens": 45230,
    "total_cost": 0.023,
    "successful_tasks": 15,
    "failed_tasks": 1,
    "models_used": {
      "glm-4-flash": {"requests": 10, "tokens": 23000},
      "deepseek-chat": {"requests": 8, "tokens": 22230}
    },
    "uptime_seconds": 3600,
    "success_rate": 0.938
  }
}
```

### 5.4 任务列表

```http
GET /tasks
GET /tasks?status=pending           # 按状态过滤
GET /tasks?limit=10                 # 限制返回数量
```

**响应**：
```json
{
  "tasks": [
    {
      "id": "hms-xxxx-1718900000",
      "description": "总结 README.md",
      "status": "completed",
      "priority": "NORMAL",
      "created_at": 1718900000.0,
      "result": "README 主要介绍了...",
      "error": null,
      "retries": 0,
      "execution_mode": "sandbox",
      "context_tags": []
    }
  ]
}
```

### 5.5 单个任务

```http
GET /tasks/{task_id}
```

**响应**：同上（单个任务对象），404 表示任务不存在。

### 5.6 创建任务

```http
POST /task
Content-Type: application/json
Authorization: Bearer <token>

{
  "task": "任务描述文本",
  "priority": "normal",
  "execution_mode": "sandbox"
}
```

**参数**：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `task` | string | ✅ | - | 任务描述 |
| `priority` | string | ❌ | `"normal"` | 优先级：low/normal/high/critical |
| `execution_mode` | string | ❌ | `"sandbox"` | 执行模式：sandbox/autonomous/interactive |

**响应**（202 Accepted）：
```json
{
  "id": "hms-xxxx-1718900000",
  "status": "pending",
  "needs_confirmation": false
}
```

> **注意**：若 `execution_mode` 为 `"autonomous"`，则 `needs_confirmation` 为 `true`，需调用确认接口后方可执行。

### 5.7 确认任务

```http
POST /tasks/{task_id}/confirm
Authorization: Bearer <token>
```

**响应**：
```json
{
  "confirmed": true
}
```

### 5.8 目标管理

#### 创建目标

```http
POST /goal
Content-Type: application/json
Authorization: Bearer <token>

{
  "description": "学习 Python 并写博客",
  "milestones": ["入门", "进阶", "实战"],
  "decompose": true,
  "execution_mode": "sandbox",
  "tags": ["python", "learning"]
}
```

**参数**：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `description` | string | ✅ | - | 目标描述 |
| `milestones` | array | ❌ | `[]` | 里程碑列表 |
| `decompose` | bool | ❌ | `false` | 是否调用 LLM 自动分解 |
| `execution_mode` | string | ❌ | `"sandbox"` | 子任务执行模式 |
| `tags` | array | ❌ | `[]` | 上下文标签 |

**响应**（`decompose=true` 时）：
```json
{
  "goal_id": "goal-xxxx-1718900000",
  "status": "pending",
  "steps": [
    "搜索 Python 最新特性",
    "整理核心概念",
    "编写示例代码",
    "撰写博客文章"
  ]
}
```

#### 查看目标列表

```http
GET /goals
```

**响应**：
```json
{
  "goals": [
    {
      "id": "goal-xxxx-1718900000",
      "description": "学习 Python 并写博客",
      "status": "pending",
      "milestones": ["入门", "进阶", "实战"],
      "progress": 0.0,
      "task_ids": ["hms-xxx-1", "hms-xxx-2"]
    }
  ]
}
```

### 5.9 执行命令

```http
POST /execute
Content-Type: application/json
Authorization: Bearer <token>

{
  "command": "ls -la /tmp",
  "execution_mode": "sandbox"
}
```

**说明**：命令不作为子进程直接执行，而是作为 `command` 类型任务提交到 Hermes 引擎，由 MasterAgent 决定如何执行。

**响应**：
```json
{
  "id": "hms-xxxx-1718900000",
  "status": "pending",
  "needs_confirmation": false,
  "note": "queued as Hermes task"
}
```

### 5.10 AI 对话

```http
POST /chat
Content-Type: application/json
Authorization: Bearer <token>

{
  "message": "请解释什么是异步编程",
  "execution_mode": "sandbox"
}
```

**响应**：
```json
{
  "id": "hms-xxxx-1718900000",
  "status": "pending"
}
```

### 5.11 统计信息

```http
GET /analytics
```

**响应**：
```json
{
  "total_requests": 18,
  "total_tokens": 45230,
  "total_cost": 0.023,
  "successful_tasks": 15,
  "failed_tasks": 1,
  "models_used": {
    "glm-4-flash": {"requests": 10, "tokens": 23000}
  },
  "start_time": 1718900000.0,
  "uptime_seconds": 3600,
  "success_rate": 0.938
}
```

### 5.12 外部上报统计

```http
POST /analytics
Content-Type: application/json
Authorization: Bearer <token>

{
  "requests": 1,
  "tokens": 1500,
  "cost": 0.001
}
```

### 5.13 审核队列

```http
GET /review
GET /review?status=pending          # 按状态过滤
```

**响应**：
```json
{
  "items": [
    {
      "id": "review-xxxx-1",
      "artifact_type": "plugin",
      "suggested_name": "auto_backup",
      "status": "pending",
      "task_id": "hms-xxxx-1",
      "created_at": 1718900000.0
    }
  ],
  "counts": {
    "pending": 2,
    "approved": 0,
    "rejected": 0,
    "total": 2
  }
}
```

#### 批准产物

```http
POST /review/{item_id}/approve?name=final_name
Authorization: Bearer <token>
```

**响应**：
```json
{
  "approved": true,
  "installed": true,
  "name": "backup_tool",
  "error": null
}
```

#### 拒绝产物

```http
POST /review/{item_id}/reject
Authorization: Bearer <token>
```

**响应**：
```json
{
  "rejected": true
}
```

### 5.14 查看能力列表

```http
GET /capabilities
```

返回所有可用端点的说明列表。

---

## 6. 执行模式详解

### 6.1 Sandbox 模式（默认）

Sandbox 模式在安全性和自动化之间取得平衡。

**环境变量设置**（任务执行期间自动设置，执行后恢复）：
- `FR_CLI_AUTONOMOUS_MODE=sandbox_auto`：文件读写、网页搜索、图片生成自动放行
- `FR_CLI_NON_INTERACTIVE=1`：标记为非交互环境

**权限矩阵**：

| 操作类型 | Sandbox 模式 |
|----------|-------------|
| 文件读取 | ✅ 自动放行 |
| 文件写入 | ✅ 自动放行 |
| 网页搜索 | ✅ 自动放行 |
| 图片生成 | ✅ 自动放行 |
| Shell 命令 | ❌ 非交互时默认拒绝 |
| 执行代码 | ❌ 非交互时默认拒绝 |
| 发送邮件 | ❌ 非交互时默认拒绝 |
| MCP 调用 | ❌ 非交互时默认拒绝 |

### 6.2 Autonomous 模式

Autonomous 模式授予任务完全权限，所有操作自动放行。

**前置条件**：
1. 创建任务时必须指定 `--autonomous` 标志
2. 用户在 REPL 中确认授权（交互式来源）
3. 或通过 HTTP API 显式调用 `/tasks/{id}/confirm`（非交互式来源）

**环境变量设置**：
- `FR_CLI_AUTONOMOUS_MODE=full_auto`
- `FR_CLI_NON_INTERACTIVE=1`

**权限矩阵**：

| 操作类型 | Autonomous 模式 |
|----------|----------------|
| 所有操作 | ✅ 自动放行 |

> ⚠️ **安全警告**：Autonomous 模式等效于授予任务完全的 shell 和系统访问权限。仅对完全可信的任务使用此模式。

### 6.3 Interactive 模式

Interactive 模式不进入后台队列，直接在当前会话中执行。

**适用场景**：
- 临时性任务，不需要持久化
- 调试和开发阶段

**特点**：
- 不修改环境变量
- 不隔离会话消息
- 产物检测使用交互式审核（弹出提示）

---

## 7. 目标分解与任务链

### 7.1 目标分解

当使用 `/hermes goal` 或 `POST /goal?decompose=true` 时，系统会调用 LLM 将高层目标自动分解为具体步骤。

**分解提示词模板**：
```
请把以下目标拆分为最多 {max_steps} 个具体可执行的步骤。
目标：{description}
请只输出 JSON，格式为：{"steps": ["步骤1", "步骤2", ...]}
```

**示例**：
```
输入：学习 Python 异步编程并写一篇博客
输出：
{
  "steps": [
    "搜索 Python asyncio 最新教程和最佳实践",
    "整理异步编程的核心概念（event loop、coroutine、await）",
    "编写示例代码演示 asyncio 常用模式",
    "将博客内容保存到 blog_python_async.md"
  ]
}
```

### 7.2 任务链

分解后的子任务自动形成线性链：

```
父任务 (goal-xxxx)
├── 子任务 1 (hms-aaa) → chain_next → hms-bbb
├── 子任务 2 (hms-bbb) → chain_next → hms-ccc
├── 子任务 3 (hms-ccc) → chain_next → hms-ddd
└── 子任务 4 (hms-ddd)
```

**调度逻辑**：
1. 调度器检查任务的 `chain_next` 字段
2. 当前任务完成后，将 `chain_next` 指向的任务的 `scheduled_at` 设为当前时间
3. 下一个调度周期会自动拾取并执行

### 7.3 任务依赖

任务间可以设置 `dependencies`，形成 DAG（有向无环图）：

```
任务 A (hms-aaa)
  └── 依赖：任务 B (hms-bbb) ✅
        └── 依赖：任务 C (hms-ccc)
```

**依赖检查逻辑**：
- 调度前检查 `dependencies` 中的所有任务状态
- 只有所有依赖都处于 COMPLETED 状态时，任务才可执行
- 自动检测循环依赖（DFS），发现环则标记为 FAILED

---

## 8. 审核队列

### 8.1 触发条件

当 Hermes 后台任务由 AI 自动生成以下类型的代码时，自动进入审核队列：

- **插件**：包含 `def run(args='')` 的 Python 代码块
- **Agent**：包含 `def run(context, **kwargs)` 的 Python 代码块

### 8.2 审核流程

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  AI 生成代码  │────▶│ 进入审核队列  │────▶│  用户审核    │
│ (后台任务中)  │     │ (pending)    │     │             │
└─────────────┘     └─────────────┘     ├── approve ──▶ 安装
                                           └── reject ──▶ 丢弃
```

### 8.3 命令行操作

```bash
# 查看待审核产物
/hermes review

# 批准并安装（可指定名称）
/hermes review approve review-xxxx-1 my_custom_name

# 拒绝
/hermes review reject review-xxxx-1
```

### 8.4 HTTP API 操作

```bash
# 查看待审核
curl -H "Authorization: Bearer $TOKEN" http://localhost:8765/review

# 批准
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8765/review/review-xxxx-1/approve?name=my_name"

# 拒绝
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8765/review/review-xxxx-1/reject"
```

### 8.5 安装逻辑

批准后，系统根据产物类型自动安装：

| 产物类型 | 安装位置 | 安装方法 |
|----------|----------|----------|
| plugin | `~/.fr_cli/plugins/<name>.py` | `install_plugin()` |
| agent | `~/.fr_cli/agents/<name>/agent.py` | `install_agent()` |

---

## 9. 配置与持久化

### 9.1 守护进程配置

文件：`~/.fr_cli/daemon/config.json`

```json
{
  "port": 8765,
  "host": "127.0.0.1",
  "lang": "zh"
}
```

### 9.2 任务持久化

文件：`~/.fr_cli/hermes/tasks.json`

整个任务列表以 JSON 数组形式持久化，每次任务状态变更时原子写入。

### 9.3 跨任务记忆

文件：`~/.fr_cli/hermes/memory.json`

结构：
```json
[
  {
    "task_id": "hms-xxxx-1",
    "description": "搜索 Python asyncio 教程",
    "result_summary": "找到 5 篇高质量教程...",
    "tags": ["python", "async"],
    "created_at": 1718900000.0
  }
]
```

> **限制**：最多保留 200 条记录，超出后自动删除最旧的记录。

**记忆匹配**：当新任务带有 `context_tags` 时，系统自动查找标签重叠的历史记录，将摘要注入到任务执行的 system prompt 中。

### 9.4 超时配置

单个 Hermes 后台任务的默认最大执行时间为 **300 秒**（5 分钟）。

**覆盖方式**（环境变量）：
```bash
export FR_CLI_HERMES_TASK_TIMEOUT=600    # 改为 10 分钟
```

超时后行为：
1. 重试次数 +1
2. 未达到最大重试次数 → 状态回 PENDING，指数退避后重新调度
3. 达到最大重试次数 → 标记为 FAILED，记录到错误台账

### 9.5 指数退避

任务失败后的重试延迟：

```
重试 1: 2^1 = 2 秒
重试 2: 2^2 = 4 秒
重试 3: 2^3 = 8 秒
...
上限: 600 秒（10 分钟）
```

---

## 10. Python API 使用

### 10.1 基本用法

```python
from fr_cli.conf.config import load_config
from fr_cli.core.core import AppState
from fr_cli.agent.hermes.engine import HermesEngine

# 1. 初始化配置和状态
cfg = load_config()
state = AppState(cfg)

# 2. 创建 Hermes 引擎
engine = HermesEngine(state_provider=lambda: state)

# 3. 创建任务
task = engine.create_task(
    description="总结 README.md 的核心内容",
    priority="normal",        # low / normal / high / critical
    source="python",
    execution_mode="sandbox", # sandbox / autonomous / interactive
)

print(f"任务已创建: {task.id} [{task.status.value}]")

# 4. 查询任务
task = engine.get_task("hms-xxxx-1718900000")
print(f"状态: {task.status.value}")
print(f"结果: {task.result}")

# 5. 列出所有任务
tasks = engine.list_tasks(status="completed")
for t in tasks:
    print(f"{t.id}: {t.description[:50]}")

# 6. 状态报告
print(engine.status_report())
```

### 10.2 目标分解

```python
# 创建目标并自动分解
parent = engine.decompose_goal(
    description="构建一个个人博客系统",
    execution_mode="sandbox",
    context_tags=["web", "python"],
    max_steps=8,
)

print(f"目标 ID: {parent.id}")
for i, child_id in enumerate(parent.children_ids, 1):
    child = engine.get_task(child_id)
    print(f"  步骤 {i}: {child.description}")
```

### 10.3 子任务与链式执行

```python
# 创建子任务
parent_id = "hms-xxxx-1"
child = engine.create_subtask(
    parent_id=parent_id,
    description="子任务描述",
    priority="high",
    execution_mode="sandbox",
    context_tags=["tag1", "tag2"],
)

# 创建链式任务
prev = engine.get_task("hms-step-1")
engine.task_manager.update(
    type('Task', (), {'id': 'hms-step-2', 'chain_next': 'hms-step-3'})()
)
```

### 10.4 审核队列操作

```python
from fr_cli.agent.review_queue import PersistentReviewQueue

queue = PersistentReviewQueue()

# 列出待审核
items = queue.list(status="pending")
for item in items:
    print(f"{item.id}: {item.artifact_type} - {item.suggested_name}")

# 批准
item = queue.approve("review-xxxx-1", final_name="my_plugin")

# 拒绝
queue.reject("review-xxxx-1")
```

### 10.5 独立守护进程

```python
from fr_cli.agent.hermes_manager import HermesManager

manager = HermesManager()

# 启动
result = manager.start(port=8765, host="127.0.0.1", lang="zh")
print(result.unwrap_or(result.error))

# 停止
result = manager.stop()

# 状态
print(manager.status())

# 检查是否运行中
print(manager.is_running())
```

### 10.6 跨任务记忆查询

```python
# 记录记忆
engine.memory_store.record(
    task_id="hms-xxxx-1",
    description="搜索 Python asyncio 教程",
    result_summary="找到 5 篇高质量教程，重点介绍了 event loop",
    tags=["python", "async", "tutorial"],
)

# 查询相关记忆
relevant = engine.memory_store.find_relevant(
    tags=["python", "async"],
    limit=3,
)
for rec in relevant:
    print(f"- {rec['description']}: {rec['result_summary']}")
```

---

## 11. 架构设计

### 11.1 类图

```
HermesEngine (mixin 组合)
├── HermesEngineCoreMixin      # 初始化 / 日志 / 关闭
│   ├── _init_engine()         #   初始化引擎实例
│   ├── _log()                 #   统一日志入��
│   ├── _log_error()           #   错误日志
│   └── shutdown()             #   关闭引擎
│
├── HermesEngineTaskMixin      # 任务/目标 CRUD + 状态查询
│   ├── create_task()          #   创建任务（含 autonomous 确认逻辑）
│   ├── confirm_task()         #   确认 autonomous 任务
│   ├── cancel_task()          #   暂停任务
│   ├── create_goal()          #   创建目标
│   ├── decompose_goal()       #   LLM 分解目标
│   ├── create_subtask()       #   创建子任务
│   ├── get_task() / list_tasks()  # 查询
│   └── status_report()        #   状态报告
│
├── HermesEngineExecutionMixin # 任务执行内部逻辑
│   ├── _execute_task()        #   执行单个任务
│   ├── _fail_task()           #   失败处理
│   ├── _dependencies_satisfied()  # 依赖检查
│   ├── _has_cycle()           #   循环依赖检测（DFS）
│   ├── _on_child_completed()  #   子任务完成回调
│   └── _schedule_chain_next() #   链式调度
│
└── HermesEngineDaemonMixin    # HTTP daemon 生命周期
    ├── start_daemon()         #   启动 HTTP 服务
    └── stop_daemon()          #   停止 HTTP 服务

组合的管理器：
├── PersistentTaskManager      # 任务队列（JsonStore 持久化）
├── PersistentGoalTracker      # 目标追踪
├── HermesMemoryStore          # 跨任务记忆
├── HermesAnalytics            # 统计
└── HermesScheduler            # 后台轮询调度器（daemon thread）
```

### 11.2 任务执行流程

```
1. 调度器每 5 秒扫描一次任务队列
   │
   ▼
2. 检查任务是否就绪（状态为 PENDING，scheduled_at <= 当前时间）
   │
   ▼
3. 检查依赖是否满足（所有 dependency 任务均为 COMPLETED）
   │
   ▼
4. 检查循环依赖（DFS 检测）
   │
   ▼
5. 设置环境变量（FR_CLI_AUTONOMOUS_MODE / FR_CLI_NON_INTERACTIVE）
   │
   ▼
6. 隔离用户主会话（保存 state.messages）
   │
   ▼
7. 注入跨任务记忆（匹配 context_tags）
   │
   ▼
8. 调用 MasterAgent.handle()（ReAct 循环，最多 8 步）
   │
   ▼
9. 记录结果 / 错误
   │
   ▼
10. 触发链式下一个任务
   │
   ▼
11. 恢复环境变量和会话状态
   │
   ��
12. 持久化任务状态
```

### 11.3 独立守护进程流程

```
hermes_daemon_process.py
│
├── 初始化
│   ├── 加载配置（daemon/config.json）
│   ├── 初始化 AppState
│   ├── 初始化 HermesEngine
│   ├── 写入 PID 文件
│   ├── 注册信号处理器（SIGTERM / SIGINT）
│   └── 注册退出清理（atexit）
│
├── 启动 HTTP 服务
│   └── HermesDaemon → HTTPServer + HermesHandler
│       ├── GET /health
│       ├── GET /info
│       ├── GET /tasks
│       ├── POST /task
│       ├── POST /goal
│       ├── POST /execute
│       ├── POST /chat
│       └── ...
│
└── 主循环
    ├── 每 2 秒检查 daemon.stop 文件
    ├── 如果存在 → 退出循环
    └── 否则继续
```

---

## 12. 安全机制

### 12.1 任务授权

**Autonomous 任务**必须经过用户显式授权才能执行：

| 来源 | 授权方式 |
|------|----------|
| REPL（交互式） | 弹出 `[y/N]` 提示，用户输入 `y` 确认 |
| HTTP API | 调用 `POST /tasks/{id}/confirm` |
| 其他 | 默认 PAUSED，需后续确认 |

### 12.2 环境变量隔离

任务执行期间，Hermes 通过修改环境变量来控制权限：

```python
# 备份原始值
env_backup = {
    "FR_CLI_AUTONOMOUS_MODE": os.environ.get("FR_CLI_AUTONOMOUS_MODE"),
    "FR_CLI_NON_INTERACTIVE": os.environ.get("FR_CLI_NON_INTERACTIVE"),
}

# 设置任务权限
os.environ["FR_CLI_AUTONOMOUS_MODE"] = "sandbox_auto"  # 或 "full_auto"
os.environ["FR_CLI_NON_INTERACTIVE"] = "1"

# ... 执行任务 ...

# 恢复原始值
for k, v in env_backup.items():
    if v is None:
        os.environ.pop(k, None)
    else:
        os.environ[k] = v
```

### 12.3 会话隔离

后台任务执行时，用户的主会话 `state.messages` 会被保存并隔离：

```python
saved_messages = state.messages
context_messages = []  # 后台任务使用独立的消息上下文

# 执行任务（使用 context_messages）
result = state.master_agent.handle(
    task.description,
    context_messages=context_messages,
    background=True,
)

# 恢复用户会话
state.messages = saved_messages
```

### 12.4 HTTP 认证

- 写操作端点必须携带 Bearer Token
- Token 使用 `secrets.compare_digest()` 进行恒定时间比较（防止时序攻击）
- Token 文件权限为 `0o600`

### 12.5 错误台账

任务失败时自动记录到集中式错误台账：

```python
from fr_cli.core.error_ledger import get_error_ledger

get_error_ledger().record(
    "hermes_task",           # 来源分类
    task.id,                 # 任务 ID
    task.description,        # 任务描述
    task.error,              # 错误信息
    metadata={
        "execution_mode": task.execution_mode,
        "task_type": task.task_type,
        "cause": "timeout"   # 或 "exception"
    }
)
```

---

## 13. 故障排查

### 13.1 守护进程无法启动

**检查步骤**：

1. 确认端口未被占用：
   ```bash
   lsof -i :8765
   ```

2. 检查 PID 文件：
   ```bash
   cat ~/.fr_cli/hermes/daemon.pid
   kill -0 $(cat ~/.fr_cli/hermes/daemon.pid)  # 检查进程是否存活
   ```

3. 清理残留状态：
   ```bash
   rm -f ~/.fr_cli/hermes/daemon.pid ~/.fr_cli/hermes/daemon.stop
   ```

4. 重新启动：
   ```bash
   /hermes start
   ```

### 13.2 任务卡在 PENDING 状态

可能原因：
1. **调度器未启动**：检查 `state.hermes.scheduler.running` 是否为 `True`
2. **scheduled_at 在未来**：检查 `task.scheduled_at` 是否已过期
3. **依赖未满足**：检查 `task.dependencies` 中的任务是否全部 COMPLETED
4. **chain_next 未设置**：链式任务需要前一个任务完成后才能调度下一个

### 13.3 任务执行超时

默认超时为 300 秒。如果任务需要更长时间：

```bash
export FR_CLI_HERMES_TASK_TIMEOUT=600
```

或检查任务是否卡在某个工具调用上（如等待用户输入）。

### 13.4 任务失败

查看错误信息：
```bash
/hermes log <task_id>
```

查看错误台账：
```bash
/status errors
```

### 13.5 日志查看

Hermes 日志文件：`~/.fr_cli/hermes/hermes.log`

```bash
tail -f ~/.fr_cli/hermes/hermes.log
```

日志格式：`[YYYY-MM-DD HH:MM:SS] 日志内容`

---

## 14. 最佳实践

### 14.1 任务设计建议

1. **描述要具体**：任务描述越具体，MasterAgent 的执行效果越好
   - ❌ `做点什么`
   - ✅ `读取 README.md，提取项目核心功能列表，保存到 features.md`

2. **合理使用优先级**：不要将所有任务设为 CRITICAL
   - 常规任务：NORMAL
   - 重要但不紧急：HIGH
   - 阻塞其他任务：CRITICAL

3. **善用 context_tags**：为相关任务添加相同标签，系统会自动匹配历史记忆

4. **Autonomous 模式谨慎使用**：仅在完全可信的场景下使用，并确保已进行充分测试

### 14.2 目标分解建议

1. **目标要清晰**：`构建个人博客系统` 比 `做个网站` 更容易分解
2. **指定 tags**：添加相关标签可提高跨任务记忆的匹配度
3. **控制步骤数**：`max_steps` 默认 8，复杂目标可适当增加

### 14.3 审核队列管理

1. **定期清理**：定期查看并处理审核队列，避免堆积
2. **命名规范**：批准时指定清晰、有意义的名称
3. **代码审查**：即使产物来自 AI，批准前也应快速浏览代码

### 14.4 监控与维护

1. **定期查看统计**：`/hermes status` 或 `GET /analytics`
2. **关注失败率**：如果失败率突然升高，检查 LLM 配置或网络连接
3. **清理旧任务**：定期清理已完成的旧任务，保持任务列表整洁

### 14.5 与其他功能配合

| 功能 | 配合方式 |
|------|----------|
| `/autostart` | 一键启动所有服务（MasterAgent + Hermes + Gatekeeper） |
| `/status` | 全局状态面板，包含 Hermes 统计 |
| `/swarm` | 蜂群模式可并行调用多个 Hermes 任务 |
| `/build` | 动态构建的工具可被 Hermes 任务调用 |
| Cron 定时任务 | Cron 触发时自动创建 Hermes 任务 |
| Gatekeeper | 管理 Agent HTTP 服务 + 定时任务 + Hermes |

---

## 附录 A：常见问题 FAQ

**Q: Hermes 和 MasterAgent 是什么关系？**  
A: MasterAgent 是单次对话的 ReAct 执行器，Hermes 是后台任务调度器。Hermes 执行任务时委托 MasterAgent 完成实际的 AI 推理和工具调用。

**Q: 任务执行失败会重试吗？**  
A: 会。默认重试 3 次，使用指数退避（2s → 4s → 8s，上限 600s）。重试次数耗尽后标记为 FAILED。

**Q: 可以同时运行多少个任务？**  
A: HermesScheduler 使用单线程轮询，同一时刻只执行一个任务。但 HermesEngine 内部使用 ThreadPoolExecutor，可扩展为并发执行。

**Q: 守护进程崩溃后任务会丢失吗？**  
A: 不会。所有任务持久化在 `tasks.json` 中，重启后自动恢复。但正在执行的任务会中断（可配置重试）。

**Q: 如何限制后台任务的资源消耗？**  
A: 通过 `FR_CLI_HERMES_TASK_TIMEOUT` 环境变量控制单个任务的最大执行时间。

**Q: 审核队列中的产物会自动安装吗？**  
A: 不会。必须人工批准后才会安装。这是为了防止 AI 生成的恶意代码自动运行。

---

## 附录 B：术语表

| 术语 | 说明 |
|------|------|
| Hermes | 后台自治任务引擎 |
| Task | 任务，最小执行单元 |
| Goal | 目标，可分解为多个 Task |
| Goal Step | 目标分解后的子任务 |
| Chain Next | 链式调度中当前任务的下一个任务 |
| Dependency | 任务依赖，必须前置完成 |
| Context Tags | 上下文标签，用于跨任务记忆匹配 |
| Execution Mode | 执行模式（sandbox/autonomous/interactive） |
| Review Queue | 审核队列，存放待审核的 AI 生成产物 |
| Daemon | 独立守护进程，脱离 REPL 运行 |
| Scheduler | 后台调度器，轮询执行就绪任务 |
| MasterAgent | 主控 Agent，ReAct 循环执行器 |
| Bearer Token | HTTP 认证令牌 |

---

*文档结束。最后更新：2026-06-21*
