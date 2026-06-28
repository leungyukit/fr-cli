# 凡人打字机 (fr-cli)

**支持 25 种 AI 模型(智谱/Anthropic/OpenAI/DeepSeek/Kimi/StepFun/MiniMax/豆包/MiMo/Qwen 等)的终端全能 AI 工具。**

**集成 MasterAgent 主控 + Hermes 后台自治任务引擎:自我进化、目标分解、定时执行。**

## ✨ 功能特性

### 🤖 多模型支持(25 个厂商)
支持以下 AI 模型提供商,默认 `zhipu / glm-4-flash`,启动时按 `default_provider → backup_provider` 自动降级:

| 厂商 | 默认模型 | 协议 |
|------|---------|------|
| **zhipu** 智谱 | glm-4-flash | 原生 SDK |
| **zhipu-coding** 智谱 Coding Plan | glm-4.7 | OpenAI 兼容 |
| **anthropic** Anthropic Claude | claude-sonnet-4-5 | Anthropic 协议 |
| **openai** | gpt-4o-mini | OpenAI 兼容 |
| **deepseek** | deepseek-chat | OpenAI 兼容 |
| **kimi** 月之暗面 | moonshot-v1-8k | OpenAI 兼容 |
| **kimi-k2** | kimi-k2-0905-preview | OpenAI 兼容 |
| **kimi-code** 代码平台 | kimi-for-coding | OpenAI 兼容 |
| **kimi-code-anthropic** | kimi-for-coding | Anthropic 协议 |
| **qwen** 通义千问 | qwen-turbo | OpenAI 兼容 |
| **doubao** 豆包 | doubao-1-5-pro-32k | OpenAI 兼容 |
| **mimo** 小米 MiMo | mimo-v2-flash | OpenAI 兼容 |
| **mimo-token-plan** | mimo-v2-flash | OpenAI 兼容(Token Plan) |
| **minimax** MiniMax | MiniMax-Text-01 | OpenAI 兼容 |
| **minimax-chat** | abab6.5s-chat | OpenAI 兼容 |
| **minimax-m27** Token Plan | MiniMax-M2.7 | OpenAI 兼容(Token Plan) |
| **minimax-m27-fast** | MiniMax-M2.7-HighSpeed | OpenAI 兼容(Token Plan) |
| **minimax-token-plan** | MiniMax-M2.7 | OpenAI 兼容(Token Plan) |
| **stepfun** 阶跃星辰 | step-1-8k | OpenAI 兼容 |
| **step-1 / step-2 / step-3** | step-X-8k/16k/auto | OpenAI 兼容 |
| **step-audio** | step-audio-2 | OpenAI 兼容 |
| **stepfun-step-plan** | step-3-auto | OpenAI 兼容(Token Plan) |
| **ernie** 文心一言 | ernie-bot-4 | Wenxin SDK |

### 🧠 核心功能
- **MasterAgent 主控**(默认启用):自我进化的 ReAct 主控 Agent,自动规划、调用工具、反思进化、失败驱动学习
- **Hermes 后台自治任务**:持久化任务队列、目标自动分解、子任务依赖链、跨任务记忆、定时执行、审核队列
- **启动流程 v2.6+**:首次启动自动引导配置 → 6 步模型向导 → default/backup 自动降级 → 后台服务自动拉起
- **项目记忆自动加载 (v2.7+)**:自动发现 `.frcli.md` / `AGENTS.md` / `CLAUDE.md` / `.github/AGENTS.md`,注入到 system prompt(类似 Claude Code 的 CLAUDE.md 机制)
- **完整 Plan mode (v2.7+)**:AI 主动 `enter_plan_mode` → 生成执行计划 → 用户审批 → `exit_plan_mode` 自动执行(类似 Claude Code 的 EnterPlanMode/ExitPlanMode)
- **多文件原子编辑 (v2.7+)**:`multi_edit` 工具一次性编辑多个文件,任一失败整体回滚
- **Git 集成 (v2.7+)**:7 个 AI 工具(`git_status` / `git_diff` / `git_log` / `git_add` / `git_commit` / `git_branch` / `git_show`),让 AI 像 Claude Code 一样感知版本控制
- **Sub-agent 委派 (v2.7+)**:MasterAgent 通过 `spawn_agent` 工具启动子 Agent 处理子任务,`task_output` 查询后台任务状态(类似 Claude Code 的 Task/TaskOutput)
- **Skill 系统 (v2.7+)**:用户可定义 `.md` skill(frontmatter + steps),通过触发词或 `/skill` 命令加载,AI 自动按步骤执行
- **Hooks 系统 (v2.7+)**:PreToolUse / PostToolUse / UserPromptSubmit / SessionStart 等可扩展点,支持 shell 命令钩子(`exit 2` 阻止 / JSON 输出修改参数)
- **Per-tool 权限 (v2.7+)**:在 `sec_*` 类别基础上加 tool 级控制(always_allow / always_deny / ask_each_time + path_rules)
- **Voice / TTS (v2.7+)**:复用 matrix MCP 的 TTS 工具,支持 AI 回复自动朗读
- **STT 语音输入 (v2.8+)**:通过 matrix MCP `transcribe_audio` 工具转写音频文件(mp3/wav/m4a/flac 等),可选本地 `faster-whisper` fallback;macOS 支持 `/voice_record` 录音 + 转写
- **Git Worktree 环境隔离 (v2.8+)**:4 个 AI 工具(`worktree_create` / `worktree_list` / `worktree_remove` / `worktree_switch`),主仓库里并行开多个独立 worktree,互不干扰地开发多个 feature
- **Plan mode UI 增强 (v2.8+)**:彩色 ANSI 渲染 + 进度条 `████░░░░ 60%` + 步骤状态图标 `✅❌🏃⏳⏭️` + 步骤耗时估算 + 依赖箭头可视化
- **RAG 检索结果缓存 (v2.8+)**:基于 query+top_k+lang 的 SHA256 hash,10 分钟 TTL,128 条 LRU 自动清理,避免重复 embedding + LLM 调用
- **会话自动恢复 (v2.8+)**:启动时检测 24h 内的最近会话,询问是否继续(加载最后 5 轮到 messages),支持 y/n/s 三个选项
- **消息分块持久化 (v2.8+)**:增量写 + 周期 full snapshot(默认 20 条触发一次),减少大 messages 列表的 IO 开销
- **并行工具调用 (v2.8+)**:AI 用 `【并行调用：tool1({...}),tool2({...})】` 显式并发执行,ThreadPoolExecutor 后台跑,失败隔离
- **Plan mode 撤销栈 (v2.8+)**:保存 20 步历史 plan,`undo_plan` / `redo_plan` 回退/重做,持久化到 `~/.fr_cli/plan_history/`
- **Worktree 自动清理 (v2.8+)**:空闲 7 天的 worktree 自动加入清理列表,`clean_idle_worktrees` 支持 `--dry-run` / `--force`
- **RAG 跨会话缓存 (v2.8+)**:可选持久化模式,缓存写到 `~/.fr_cli/rag_cache.json`,重启后还能命中
- **Diff 可视化 (v2.8+)**:彩色 unified diff + 行号对齐 + 上下文折叠 + 双栏并排,集成到 `git_diff` 工具
- **Streaming Markdown (v2.8+)**:边输出边渲染,状态机跟踪 heading/code/list/quote/table,逐 chunk 渲染不重写
- **会话导出 PPT (v2.8+)**:`/export_ppt <会话索引或路径>` 导出为 PPTX(python-pptx)或 Markdown 大纲(fallback),每对 user/assistant 转为一张幻灯片
- **思维模式**:`direct / CoT / ToT / ReAct / Plan` 五种推理模式切换
- **文件沙盒**:安全的虚拟文件系统(VFS),支持读写/目录操作、`../` 防逃逸
- **联网搜索**:内置 Web 搜索与网页内容提取(SSRF 防护)
- **Token 上下文压缩**:长会话自动摘要早期对话,降低 prompt token 消耗
- **4 阶安全确认**:`Y / A / F / N` 四级授权,支持 `sandbox_auto` / `full_auto` 自治模式

### 🎯 特色功能
- **视觉能力**:图片生成(CogView)与多模态识别(GLM-4V / Claude Vision)
- **OCR 文字识别**:`/ocr <文件>` 识别图片或 PDF 中的文字,支持 Vision API + PaddleOCR 本地引擎
- **邮件收发**:IMAP/SMTP 标准邮箱 + Microsoft 365 现代认证(OAuth2 + MFA)
- **定时任务**:后台定时执行命令(Cron)与 Agent 定时任务(Agent Cron)
- **云盘集成**:百度/阿里/OneDrive 网盘
- **插件系统**:AI 生成代码自动保存为插件(子进程隔离,15s 超时)
- **会话记忆**:最近 5 轮对话摘要注入 + 按日期自动存档 + 手动保存
- **Agent 分身系统**:AI 自动生成 Agent,支持工作流编排、专属模型绑定、远程 Agent 注册
- **Agent HTTP API**:将 Agent / 蜂群 / MasterAgent 发布为 REST API
- **蜂群协作 (Swarm)**:`parallel / council / pipeline` 三种多 Agent/工具/MCP/插件协作模式
- **动态构建系统**:按需自动安装依赖、生成工具、自测回滚、能力缺口发现
- **本机应用启动**:一键调用浏览器、微信、Word、WPS 等本地程序
- **内置 Agent**:`@local` `@remote` `@spider` `@db` `@RAG` `@stock`
- **数据卷轴**:Excel / CSV 读取与智能分析
- **数据库助手**:MySQL / PostgreSQL / SQL Server / Oracle 智能 SQL 生成
- **本地 RAG**:ChromaDB 向量库 + 自动文件监控与向量化(支持独立守护进程)
- **股票助手**:akshare / 麦蕊 / tushare 数据源,模拟交易
- **MCP 外部神通**:支持 Model Context Protocol(stdio / SSE)
- **多源信息融合**:大模型 + 工具结果统一汇总,双源回答
- **集中式错误报告**:`/status errors` 聚合 Hermes / 动态构建 / 审核拒绝 / MasterAgent 失败模式
- **中英文切换**:完整国际化支持
- **NO_COLOR 支持**:`NO_COLOR=1` 禁用所有 ANSI 颜色,适合 CI/管道环境

## 🚀 快速开始

```bash
# 安装
pip install fr-cli

# 启动
fr-cli

# 或从源码运行
git clone https://github.com/yourname/fr-cli.git
cd fr-cli
pip install -e ".[all]"
fr-cli
```

**首次运行**(v2.6+):
1. 检测到未配置 → 提示是否进入 6 步配置向导
2. 选 N → 进入 Mock 模式试用
3. 选 Y → 6 步流程:`选厂商 → 选 compat → 选模型 → 设 baseUrl → 设 API Key → 设 default/backup`

启动后自动:
- 启用 MasterAgent(默认开,可 `/master off` 关掉)
- 拉起 Hermes 后台守护进程(可 `autostart_on_launch: false` 关掉)
- 拉起 Gatekeeper 守护进程(Agent HTTP + 定时任务持久化)

## 📝 使用方法

### 📋 常用命令

#### 💬 对话 / 模型
```
/model <模型名>                切换 AI 模型(仅当前会话)
/model <道统>:<模型名>         同时切换道统和模型
/model current                 显示当前模型
/model default                 恢复 factory 默认模型
/model list                    列出所有可用模型
/model config                  🆕 6 步模型配置向导(等价 /providers setup)
/key <key>                     修改当前道统 API Key
/key <道统> <key>              为指定道统设置 Key
/providers                     查看所有道统配置(含 default/backup)
/providers setup               🆕 6 步模型配置向导
/providers add <p> <k> [m]     添加/更新道统配置
/providers use <p>             切换到指定道统
```

#### 🧠 主控 / 思维
```
/master on|off|status          MasterAgent 主控(默认开)
/mode direct|cot|tot|react|plan  切换思维模式
/autonomous [mode]             切换自治模式(manual/sandbox_auto/full_auto/off)

# v2.7+:完整 Plan mode(类似 Claude Code 的 EnterPlanMode/ExitPlanMode)
# AI 工具:
enter_plan_mode      AI 主动进入计划模式,生成详细执行计划
exit_plan_mode       用户审批/拒绝后,自动按步骤执行或放弃
```

#### 📂 文件 / 上下文
```
/dir [路径]                    列出目录文件 / 添加允许访问的目录
/dirs                          列出已挂载的工作目录
/rmdir <索引>                  删除已挂载的目录
/open <file>                   查看文件内容
/write <file>                  写入文件(多行,Ctrl+D 结束)
/delete <file>                 删除文件
/context [status|compress|threshold N|keep N]  管理上下文压缩
/limit <n>                     设置 Token 上限(最小 1000)
```

#### 🧬 项目记忆 + 多文件编辑 + Git
```
# v2.7+:自动加载 .frcli.md / AGENTS.md / CLAUDE.md 作为项目记忆
# 放在项目根目录(或 .github/AGENTS.md)即可被 AI 自动感知

# AI 工具:
multi_edit          原子性多文件编辑(任一失败整体回滚,适合批量重构)
git_status          git working tree 状态
git_diff [path]     查看变更内容
git_log [limit]     查看提交历史
git_add [paths]     暂存文件
git_commit          提交变更
git_branch          列出/创建/切换/删除分支
git_show            查看某次提交详情
```

#### 💾 会话 / 用量
```
/save <name>                   保存当前会话
/load [name]                   加载历史会话
/export [path]                 导出会话为 Markdown
/session_list                  列出按日期自动存档的会话
/session_load <idx>            加载自动存档的会话
/session_del <idx>             删除自动存档
/usage [days]                  查看 LLM 用量统计(provider/model/tokens/cost)
/status [json|errors]          查看全局状态 / 集中错误报告
```

#### 🔌 MCP / 插件 / 动态构建
```
/mcp_list                      列出 MCP 服务器及工具
/mcp_add <名> <命令> [参数]    添加 MCP 服务器
/mcp_del <名>                  删除 MCP 服务器
/mcp_enable / mcp_disable <名> 启用/禁用 MCP
/mcp_refresh                   刷新 MCP 工具列表
/build <需求>                  AI 自动生成工具并注册
/build list                    列出已构建工具
/build check <name>            重新测试已构建工具
/build del <name>              删除已构建工具
```

#### 🤖 Agent 管理
```
/agent_create <名> <描述>      AI 自动生成 Agent
/agent_forge <名>              从历史代码铸造 Agent
/agent_list                    列出所有 Agent
/agent_show <名>               查看 Agent 详情
/agent_edit <名> persona|memory|skills  编辑 Agent 文件
/agent_run <名> <任务>         运行 Agent
/agent_model <名> [<provider>:<model>]  配置 Agent 专属模型
/agent_delete <名>             删除 Agent
/agent_server start|stop|status [port]   启动 Agent HTTP API
```

#### 🛰️ 远程 Agent / 内置 Agent
```
@local <任务>                  本地系统操作(安全确认后执行)
/remote <host> <任务>          远程 SSH 操作(支持 sftp/scp)
/spider <url> [depth]          智能网页爬虫
/db <conn> <任务>              数据库智能助手
@RAG <问题>                    本地知识库问答
@stock <任务>                  股票/量化助手

/remote_setup                  配置 SSH 远程主机
/db_setup                      配置数据库连接
/remote_agent_add <名> <url>   注册远程 Agent
/remote_agent_list             列出远程 Agent
/remote_agent_publish <名>    将本地 Agent 发布为 HTTP API
```

#### 🔧 后台服务 / 系统
```
/autostart [--agent-server port] [--hermes port]  一键启动所有后台服务
/hermes status|start|stop|list|task|goal|confirm|review   Hermes 后台自治(统一入口,start 即启动独立 HTTP 守护进程)
/gatekeeper start|stop|status             Gatekeeper 守护进程(Agent HTTP + Cron)
/hermes_review approve|reject <id>        审核队列(动态构建 / Agent 自动产物)

# v2.7+:AI 工具(类似 Claude Code 的 TaskOutput)
task_output            查询 Hermes 后台任务的状态/输出
list_background_tasks  列出所有后台任务
spawn_agent            启动子 Agent 处理子任务,返回 task_id(可并发)
```

#### 🎯 Skill 系统 (v2.7+)
```
# 用户可定义 .md skill,放在 ~/.fr_cli/skills/ 或项目 .fr_cli/skills/

# skill 文件格式(Markdown frontmatter):
---
name: my-skill
description: 描述
triggers:
  - 触发词1
  - 触发词2
steps: |
  1. 第一步
  2. 第二步
---

# 触发方式:/skill <name> 或自然语言包含触发词
# AI 会自动加载 skill 并按步骤执行
```

#### 🎣 Hooks 系统 (v2.7+)
```
# ~/.fr_cli/hooks.json 或项目级 .fr_cli/hooks.json
{
  "PreToolUse": [
    {"matcher": "delete_file", "command": "exit 2", "description": "禁止删除"}
  ],
  "PostToolUse": [
    {"matcher": ".*", "command": "logger.sh"}
  ],
  "UserPromptSubmit": [
    {"matcher": ".*rm\\s+-rf.*", "command": "exit 2"}
  ]
}

# PreToolUse hook:
#   - exit 0: 放行
#   - exit 2: 阻止(类似 Claude Code)
#   - stdout 输出 JSON {block: true} → 阻止
#   - stdout 输出 JSON {modified_args: {...}} → 修改参数
#   - 纯文本 stdout → 替换 tool_result(用于 PostToolUse)
```

#### 🔐 Per-tool 权限 (v2.7+)
```json
// ~/.fr_cli/config.json
{
  "permissions": {
    "always_allow": ["search_web", "read_file"],
    "always_deny":  ["delete_file"],
    "ask_each_time": ["git_commit"],
    "path_rules": {
      "write_file": {
        "always_allow_paths": ["/tmp/*"],
        "always_deny_paths": ["/etc/*", "/usr/*", "re:.*\\.env$"]
      }
    }
  }
}
```
优先级:`deny` > `path_allow` > `always_allow` > `ask` > `fallthrough(sec_*)`

#### 🔊 Voice / TTS (v2.7+)
```
# 需要配置 matrix MCP server(内置 TTS 工具)
# 配置后:
voice_speak          朗读文本(同步,生成音频文件)
voice_list           列出可用声音
voice_toggle         切换自动朗读(AI 回复自动朗读)
# AI 工具:
【调用：voice_speak({"text": "你好世界"})】
```

#### 🎙️ STT 语音输入 (v2.8+)
```
# 需要配置 matrix MCP server(内置 transcribe_audio 工具)
# 用法:
/voice_input /path/to/audio.mp3          # 文件转写
/voice_input /path/to/audio.wav --lang en  # 英文转写
/voice_input /path/to/audio.mp3 --local    # 优先用本地 whisper
/voice_record 30                          # macOS 录音 30 秒 + 自动转写
# AI 工具:
【调用：voice_input({"path": "/tmp/audio.mp3", "language": "zh"})】
```
支持的音频格式:mp3 / wav / m4a / flac / ogg / opus / webm / aac
引擎优先级:MCP matrix → 本地 faster-whisper(fallback)

#### 🌳 Git Worktree 环境隔离 (v2.8+)
```
# 在当前 git 仓库下创建隔离 working copy,适合并行开发多个 feature
/worktree_create feat-x                # 创建 feat-x 分支 + worktree
/worktree_create feat-y /path/to/wt    # 自定义路径
/worktree_list                         # 列出所有 worktree
/worktree_switch /path/to/wt           # 切换 cwd 到 worktree
/worktree_remove /path/to/wt --force   # 删除 worktree(保留分支)
# AI 工具:
【调用：worktree_create({"branch": "feat-x", "base": "master"})】
【调用：worktree_list({})】
```
默认路径: `<repo>/.worktrees/<branch>/`,可自定义。删除分支用普通 git 命令。

#### 📋 Plan mode UI 增强 (v2.8+)
```
# Plan mode 的可视化增强:
- ANSI 彩色(标题/成功/失败/警告)
- 进度条 ████░░░░ 60%
- 步骤状态 ✅ ❌ 🏃 ⏳ ⏭️
- 步骤耗时估算(基于工具类型)
- 依赖箭头 │ ▼ 连接步骤
- 审批选项:y/n/e/s/d(原版只有 y/n/e/s)
  + d = 步骤详情(查看每个步骤的参数)
```

#### 💾 RAG 缓存 + 会话自动恢复 (v2.8+)
```
# RAG 检索缓存:
- 10 分钟 TTL,基于 query + top_k + lang 的 SHA256 hash
- 最多缓存 128 条,LRU 自动清理
- 避免重复 embedding + LLM 调用

# 会话自动恢复:
- 启动时检测 24h 内的最近会话
- 提示:y / n / s
  - y / 回车 = 继续上次(加载最后 5 轮)
  - n         = 开始新会话
  - s         = 选择其他会话
```

#### ⏰ 定时任务
```
/agent_cron_add <名> <秒> [输入]  Agent 定时任务
/agent_cron_list               列出 Agent 定时任务
/agent_cron_del <id>           删除 Agent 定时任务
```

#### 📧 邮件
```
/mail setup                    配置 IMAP/SMTP 邮箱
/mail inbox                    查看收件箱
/mail read <id>                读取邮件
/mail send <to> <sub> <body>   发送邮件
/m365_config setup             配置 Microsoft 365 邮箱(OAuth2 + MFA)
/m365_inbox / m365_read / m365_send
```

#### 🌐 RAG / 股票 / OCR
```
/rag_dir <目录>                设置并同步本地知识库
/rag_sync [路径]               手动同步文件到向量库
/rag_watch start|stop|status|log  RAG 独立文件监控守护进程
/stock_config setup            交互式配置股票数据源
/ocr <文件>                    OCR 识别图片或 PDF
/ocr_config setup|engine|provider|model|key|base_url|prompt  配置 OCR
```

#### 🛠️ 其它
```
/search <query>                联网搜索
/read_excel <xlsx>             读取 Excel
/read_csv <csv>                读取 CSV
/security                      查看安全设置
/lang <zh|en>                  切换语言
/update check|run              检查 / 执行更新
/tutorial                      显示交互式教程
/banner on|off                 控制启动动画
/exit                          退出
```

### 🖥️ 非交互 / 批处理模式

适合脚本、cron、管道场景:

```bash
# 执行一条 slash 命令后退出
fr-cli -c "/model current"
fr-cli -c "/dir"

# 向 AI 提问后退出
fr-cli "请总结 README.md"
fr-cli -p "Python 如何读取 JSON？"

# 从文件或标准输入读取提示词
cat article.txt | fr-cli -s
fr-cli -f prompt.txt

# 静默模式(跳过启动 banner,只输出核心结果)
fr-cli -q -c "/model current"
fr-cli -q -p "1+1等于几"
```

### 🤖 模型配置详解(v2.6+)

**首次启动自动引导**,或手动 `/model config` / `/providers setup` 启动 6 步向导:

| 步骤 | 内容 |
|------|------|
| a | 选择供应商(25 个,显示已配置标记 + compat 类型) |
| b | 选择 compat 模式(Anthropic / OpenAI,zhipu 自动跳过) |
| c | 选择模型(支持 `c` 自定义) |
| d | 设置 baseUrl(`none` 清空,可读环境变量) |
| e | 设置 API Key(getpass 隐藏,可读环境变量) |
| f | 设置 default / backup / 仅保存 |

**default / backup 自动降级**:
```json
{
  "default_provider": "zhipu",
  "backup_provider": "deepseek",
  "providers": {
    "zhipu": {"key": "sk-xxx", "model": "glm-4-flash"},
    "deepseek": {"key": "sk-yyy", "model": "deepseek-chat"}
  }
}
```
启动时若 `default_provider` 不可用(无 key / 接口挂),自动降级到 `backup_provider`,可通过 `/status json` 查看 `active_model_source`。

**Agent 专属模型**(不影响全局默认):
```bash
>>> /agent_model my_agent
>>> /agent_model my_agent deepseek:deepseek-chat
>>> /agent_model my_agent --key sk-own-key
>>> /agent_model my_agent clear
```
配置存储于 `~/.fr_cli/agents/<name>/config.json`。

### 🐝 蜂群协作 (Swarm)

通过 AI 工具调用实现多 Agent / 工具协作:

```
【调用：swarm_run({"mode": "parallel", "names": ["@local", "tool:search_web"], "user_input": "分析项目并搜索相关资料"})】
【调用：swarm_run({"mode": "council", "names": ["planner", "coder", "reviewer"], "user_input": "设计用户登录模块"})】
【调用：swarm_run({"mode": "pipeline", "names": ["extractor", "summarizer"], "user_input": "从报告中提取关键点"})】
```

支持任务单元:Agent / 内置 Agent / 注册表工具 / `/` 命令 / MCP 工具 / 自定义插件。
也可用 `/swarm parallel coder,reviewer ...` 直接执行。

### 🤖 AI 调用格式

```
【调用：search_web({"query": "搜索词"})】
【调用：write_file({"path": "a.md", "content": "..."})】
【命令：/build 生成二维码工具】
```

## 🧠 Hermes 后台自治任务

Hermes 是 fr-cli 的后台自治引擎,负责目标分解、任务队列、定时执行、跨任务记忆、审核队列。

### REPL 命令
```
/hermes status                 查看引擎状态(任务/目标/统计/守护进程)
/hermes start [port]           启动独立 HTTP 守护进程(默认 8765)
/hermes stop                   停止守护进程
/hermes goal [--autonomous] <目标> [--tags a,b]  创建目标并自动分解
/hermes task [--autonomous|-a] <描述>  创建后台任务
/hermes confirm <id>           显式确认 autonomous 任务(以 full_auto 执行)
/hermes list [status]          列任务(pending/running/completed/failed/paused)
/hermes log <id>               查看任务结果/日志
/hermes cancel <id>            暂停任务
/hermes review [approve|reject <id>]  审核队列(动态构建 / Agent 自动产物)
```

### HTTP API(默认 127.0.0.1:8765,写端点需 Bearer Token)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/health` | 健康检查 |
| GET  | `/tasks` / `/tasks/<id>` | 任务列表 / 详情 |
| POST | `/task` | 创建任务(`execution_mode=autonomous` 返回 needs_confirmation) |
| POST | `/tasks/<id>/confirm` | 确认 autonomous 任务 |
| POST | `/chat` | 提交对话任务给 MasterAgent |
| POST | `/goal` | 创建目标(带 `decompose=true` 自动分解) |
| GET  | `/goals` | 目标列表 |
| GET  | `/analytics` | 统计 |
| GET  | `/review` | 审核队列列表 |
| POST | `/review/<id>/approve?name=xxx` | 批准并安装产物 |
| POST | `/review/<id>/reject` | 拒绝产物 |

### 安全执行模式

| 模式 | 说明 | 适用 |
|------|------|------|
| `sandbox`(默认) | 后台任务默认,沙盒操作自动放行,系统操作非交互时拒绝 | 普通后台任务 |
| `autonomous` | 完全信任,所有操作自动放行 | `/hermes task -a` 创建后需 `/hermes confirm` |
| `interactive` | 占位,走当前 REPL 模式 | 实时对话 |

### 🐚 Shell 模式(Ctrl-X 切换)
```
Agent 模式: 输入消息与 AI 对话
Shell 模式: 直接执行 shell 命令
按 Ctrl-X 切换模式
```

## 🔧 开发

```bash
# 克隆项目
git clone https://github.com/yourname/fr-cli.git
cd fr-cli

# 安装开发依赖
pip install -e ".[all]"

# 运行测试
python3 -m pytest tests/ -v

# Lint
ruff check fr_cli tests
```

### 测试覆盖

项目共有 **745+ 个测试用例**,覆盖核心模块:

| 测试文件 | 数量 | 覆盖范围 |
|---------|------|---------|
| `test_remote.py` | 10 | SSH / SCP(本地 mock server) |
| `test_rag.py` | 37 | RAG 知识库(文件读取/分块/入库/同步/query/守护) |
| `test_spider.py` | 28 | @spider 智能爬虫(链接提取/反爬检测/自适应) |
| `test_ocr.py` | 22 | OCR 文字识别(Vision/PDF/格式检测) |
| `test_fs.py` | 26 | VFS 文件沙盒(路径解析/读写/../ 逃逸防护) |
| `test_security.py` | 17 | 4 阶安全确认(manual/sandbox_auto/full_auto) |
| `test_cron.py` | 15 | CronManager(添加/删除/列表/shlex 安全) |
| `test_charts.py` | 17 | 控制台图表(bar/pie/line) |
| `test_network.py` | 13 | 网络探测(ping/port_scan/ip_scan) |
| `test_web.py` | 16 | WebRaider 搜索 + SSRF 防护 |
| `test_history.py` | 12 | 会话历史(保存/加载/导出 Markdown) |
| `test_context.py` | 13 | 上下文记忆(摘要/最近轮) |
| `test_result.py` | 19 | Result 统一返回风格 |
| `test_store.py` | 19 | JsonStore 原子持久化 |
| `test_dataframe.py` | 9 | Excel/CSV 读取 |
| `test_project_memory.py` | 18 | 项目记忆加载(.frcli.md/AGENTS.md/CLAUDE.md) |
| `test_multi_edit.py` | 13 | 原子多文件编辑 |
| `test_git_tools.py` | 31 | Git 集成(7 个工具,真实 git 仓库) |
| `test_skills.py` | 21 | Skill 系统(解析/发现/触发词) |
| `test_hooks.py` | 28 | Hooks 系统(Pre/Post/UserPromptSubmit) |
| `test_permissions.py` | 26 | Per-tool 权限 + path rules |
| `test_plan_mode.py` | 15 | Plan mode(EnterPlanMode/edit/show) |
| `test_voice.py` | 18 | Voice / TTS(matrix MCP 集成) |
| 其他 | ~450 | 既有测试(MasterAgent/Hermes/Swarm/MCP 等) |

测试可在任何环境运行(RAG/OCR/SSH/SPIDER 等都用 mock 隔离外部依赖)。

**累计:43+ 个测试文件,1234+ 个测试用例**

v2.8+ 新增测试:

| 测试文件 | 数量 | 覆盖范围 |
|---------|------|---------|
| `test_worktree.py` | 18 | Git worktree(create/list/remove/prune/format) |
| `test_voice_input.py` | 7 | STT 音频转写(格式校验 / fallback) |
| `test_plan_ui.py` | 16 | Plan mode 彩色 UI(渲染 / 进度 / 摘要 / 估算) |
| `test_rag_cache.py` | 10 | RAG 检索结果缓存(SHA256 / TTL / LRU) |
| `test_resume.py` | 18 | 会话自动恢复(找最新 / 时间窗 / 加载 / 询问) |
| `test_incremental.py` | 12 | 消息增量持久化(snapshot / delta / 触发 / 兼容) |
| `test_parallel.py` | 13 | 并行工具调用(提取 / 拆分 / 并发执行 / 失败隔离) |
| `test_plan_undo.py` | 13 | Plan 撤销栈(push / undo / redo / 清空 / 深度限制) |
| `test_worktree_cleanup.py` | 14 | Worktree 自动清理(注册 / touch / 找空闲 / dry-run / 实际清理) |
| `test_rag_persistent.py` | 7 | RAG 跨会话持久化(写盘 / 读盘 / 过期跳过 / 删除) |
| `test_diff_view.py` | 16 | Diff 可视化(解析 / unified / 双栏 / 统计) |
| `test_markdown_stream.py` | 19 | Streaming Markdown 渲染(状态机 / code block / 列表) |
| `test_session_ppt.py` | 15 | 会话导出 PPT(配对提取 / 大纲 / Markdown fallback) |

### 环境变量

| 变量 | 说明 |
|------|------|
| `NO_COLOR=1` | 禁用所有 ANSI 颜色输出,适合 CI/管道/日志重定向 |
| `FR_CLI_DEBUG=1` | 开启调试模式,显示详细 traceback |
| `FR_CLI_NON_INTERACTIVE=1` | 非交互模式,安全确认默认拒绝 |
| `FR_CLI_BATCH_CONFIRM=1` | 批量确认模式:跳过所有安全询问(脚本/自动化场景) |
| `FR_CLI_AUTONOMOUS_MODE` | 自治模式:`manual` / `sandbox_auto` / `full_auto` |
| `FR_CLI_HERMES_TASK_TIMEOUT` | 单个 Hermes 任务超时秒数(默认 300) |

## 📂 项目结构

```
fr_cli/
├── main.py                    # 核心入口:REPL 循环与 AI 交互编排
├── agent/                     # Agent 分身 / Master / Hermes / 蜂群系统
│   ├── master.py              # MasterAgent 主类骨架(mixin 组装)
│   ├── master_storage.py      # 配置文件路径 / 默认值 / 错误分类
│   ├── master_prompt.py       # 默认 system prompt 模板
│   ├── master_prompt_builder.py  # Prompt 组装
│   ├── master_loop.py         # ReAct 主循环
│   ├── master_reflect.py      # 反思进化
│   ├── hermes/                # Hermes 后台自治(engines/managers/models/scheduler)
│   ├── swarm.py / swarm_resolver.py  # 蜂群协作
│   ├── review_queue.py        # 后台产物审核队列
│   └── builtins/              # 内置 Agent(local/remote/db/spider/rag/stock)
├── command/                   # 统一工具注册表与命令执行引擎
│   ├── registry.py            # 工具注册表(单一真相源)
│   ├── executor.py            # AI 回复解析与调度
│   ├── security.py            # 安全确认中间件
│   └── registered/            # 按类目拆分的工具实现
├── core/                      # 核心模块
│   ├── llm.py                 # LLM 客户端(25 个厂商 + Anthropic 兼容)
│   ├── core.py                # AppState 全局状态(DI 容器)
│   ├── result.py              # 统一 Result 返回风格
│   ├── store.py               # 统一 JSON 持久化抽象
│   ├── usage.py               # Token 用量统计
│   ├── thinking.py            # 思维模式引擎(CoT/ToT/ReAct)
│   ├── plan/                  # Plan 模式独立模块
│   └── ...
├── conf/                      # 配置与路径管理
│   ├── config.py              # 配置读写 / 首次启动引导
│   ├── model_wizard.py        # 6 步模型配置向导
│   └── default_models.yaml    # 25 个厂商的元数据
├── dynamic_builder/           # 动态构建系统(按需生成工具)
├── repl/                      # REPL 命令路由
│   ├── router.py              # 命令路由表
│   └── commands/              # 40+ 命令处理器
│       ├── config/            # 配置类(model/key/providers/limit/lang)
│       └── system/            # 系统类(autostart/status/hermes/setup)
├── weapon/                    # 武器库(文件/网络/邮件/云盘/RAG/视觉/OCR/图表)
├── memory/                    # 记忆系统(历史/会话/上下文/压缩)
├── addon/                     # 插件机制
├── breakthrough/              # 自动更新
├── gatekeeper/                # Gatekeeper 守护
├── lang/                      # 国际化(zh/en)
└── security/                  # 4 阶安全确认引擎
```

## 📚 文档

- [AGENTS.md](AGENTS.md) - 面向 AI 编码助手的项目架构与开发指南
- [fr_cli/README.md](fr_cli/README.md) - 项目内部说明

## 📂 配置目录

> 配置统一在 `~/.fr_cli/` 目录下,旧路径(如 `~/.zhipu_cli_config.json`)会在首次启动时自动迁移。

| 路径 | 说明 |
|------|------|
| `~/.fr_cli/config.json` | 主配置文件(scheme v3,含 default_provider / backup_provider / autostart_on_launch) |
| `~/.fr_cli/config.json.bak` | 配置自动备份 |
| `~/.fr_cli/history/` | 会话历史记录 |
| `~/.fr_cli/sessions/manual/` | 手动保存的会话 |
| `~/.fr_cli/sessions/auto/` | 按日期自动存档的会话 |
| `~/.fr_cli/context.json` | 上下文记忆摘要 |
| `~/.fr_cli/usage.json` | LLM 用量统计(文件权限 0o600) |
| `~/.fr_cli/plugins/` | 用户插件目录 |
| `~/.fr_cli/agents/<name>/` | Agent 分身目录 |
| `~/.fr_cli/master/` | MasterAgent 记忆与进化记录 |
| `~/.fr_cli/dynamic_tools/` | 动态构建生成的工具目录 |
| `~/.fr_cli/hermes/` | Hermes 任务 / 目标 / 审核队列 / 日志 |
| `~/.fr_cli/daemon/` | Gatekeeper 守护进程配置 |
| `~/.fr_cli/cron.json` | 定时任务配置 |
| `~/.fr_cli/remotes.json` | 远程主机配置 |
| `~/.fr_cli/databases.json` | 数据库连接配置 |
| `~/.fr_cli/rag_db/` | RAG 向量库(ChromaDB) |
| `~/.fr_cli/rag/` | RAG 监控日志 |
| `~/.fr_cli/m365.json` | Microsoft 365 OAuth Token 缓存(0o600) |
| `~/.fr_cli/stock.json` | 股票数据源与模拟交易记录 |

## ❓ 常见问题

**Q: 如何切换思维模式?**
```bash
/mode direct   # 直接回复
/mode cot      # 思维链
/mode tot      # 思维树
/mode react    # ReAct
/mode plan     # 计划模式(独立模块)
```

**Q: 如何配置模型?**
```bash
# 推荐:6 步配置向导
/model config
# 或
/providers setup

# 启动时按 default → backup 自动降级,可通过 /status json 查看当前激活来源
```

**Q: 切换的模型重启后失效?**
使用 `/model config` 配置后会持久化到 `~/.fr_cli/config.json`(写入 `default_provider` / `providers.*`)。重启仍然生效。仅 `/model xxx` 临时切换会随会话结束失效。

**Q: 如何保存/加载会话?**
```bash
/save my-session               # 手动保存到 sessions/manual/
/load                          # 列出并选择手动保存的会话
/session_list                  # 列出按日期自动存档的会话
/export                        # 导出当前会话为 Markdown
```

**Q: Token 上下文压缩?**
会话历史累积超过阈值(默认 4000 token)时自动压缩为摘要,保留最近 N 轮完整对话。压缩摘要注入 system prompt,降低 token 成本。
```bash
/context status                # 查看当前状态
/context compress              # 手动触发压缩
/context threshold 8000        # 调整阈值
/context keep 10               # 调整保留轮数
```
配置位于 `~/.fr_cli/config.json` 的 `memory` 命名空间。

**Q: MasterAgent 默认开启吗?需要关掉?**
v2.6+ 默认启用。普通对话自动进入 ReAct 循环(自主调用工具 / 反思)。如想恢复传统流式对话:
```bash
/master off
```
所有原有 `/`、`!`、`@` 前缀行为不变。

**Q: 邮件发送失败?**
QQ/163 邮箱需使用「授权码」而非登录密码。授权码在邮箱设置 → 账户 → 开启 IMAP/SMTP 服务后生成。

**Q: Microsoft 365 / Outlook 邮箱如何使用?**
Microsoft 365 已禁用基本认证,需使用 OAuth2 现代认证:
1. 在 Azure AD 注册应用,添加 `Mail.Read`、`Mail.Send`、`User.Read` 委派权限
2. 复制 Application (client) ID 和 Directory (tenant) ID
3. 执行 `/m365_config setup`,按向导完成设备码或授权码登录(支持 MFA)
4. 使用 `/m365_inbox`、`/m365_read <id>`、`/m365_send`

Token 缓存于 `~/.fr_cli/m365.json`,文件权限 `0o600`。

**Q: OCR 使用?**
```bash
/ocr_config setup              # 交互式配置(选 vision / paddle 引擎)
/ocr screenshot.png            # 识别图片
/ocr invoice.pdf               # 识别 PDF(需 pip install pymupdf)
```
Vision 引擎复用全局 provider 配置(如 `zhipu / glm-4v`);PaddleOCR 为本地引擎,需 `pip install paddleocr paddlepaddle`。

**Q: 股票数据源?**
```bash
/stock_config setup            # 交互式配置向导
/stock_config source akshare   # 切换数据源(akshare / 麦蕊 / tushare)
/stock_config key mairui <key> # 配置麦蕊 API Key
/stock 查询茅台股价
/stock 买入 600519 1500.00 100 # 模拟交易(需先 /stock_config trade)
```

**Q: 搜索功能无法使用?**
```bash
pip install requests
```

**Q: 云盘功能无法使用?**
```bash
pip install aligo   # 阿里云盘
pip install bypy    # 百度网盘
```
首次使用需运行 `/disk_setup` 完成扫码登录。

**Q: 启动时自动拉起了后台服务,怎么关?**
```json
// ~/.fr_cli/config.json
{
  "autostart_on_launch": false
}
```
或单独控制:
```bash
/hermes stop                  # 停止 Hermes 守护进程
/gatekeeper stop              # 停止 Gatekeeper 守护进程
/master off                   # 关闭 MasterAgent 主控
```

## 📄 License

MIT