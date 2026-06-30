# fr-cli 使用说明(USAGE.md)

> 凡人打字机(fr-cli)是基于智谱、DeepSeek、Kimi、Qwen、StepFun、MiniMax 等 25+ 大模型的交互式终端工具。
> 在 REPL 中与 AI 对话,自动调用文件系统、网络搜索、邮件、网盘、定时任务、图片、OCR、Excel/CSV、RAG 知识库、
> 自定义 Agent、MasterAgent 自我进化、Hermes 后台自治引擎、MCP 外部工具等能力。
>
> **本文件是面向最终用户的完整使用手册**,涵盖所有功能、配置和使用示例。
> 另见:
> - [README.md](README.md) — PyPI 简介、Quick Start、Docker 部署
> - [AGENTS.md](AGENTS.md) — AI 编码助手向的项目结构说明
> - [CHANGELOG](https://github.com/leungyukit/fr-cli/blob/master/CHANGELOG.md) — 版本变更记录
>
> **版本**:`__version__`(见 `fr_cli/__init__.py`)
> **许可证**:个人项目

---

## 目录

- [1. 安装](#1-安装)
- [2. 快速开始](#2-快速开始)
- [3. 模型与提供商配置](#3-模型与提供商配置)
- [4. REPL 基本使用](#4-repl-基本使用)
- [5. 文件操作(洞府)](#5-文件操作洞府)
- [6. 会话管理(轮回)](#6-会话管理轮回)
- [7. 多模态:图片 / Excel / CSV / OCR](#7-多模态图片--excel--csv--ocr)
- [8. Shell 与系统命令(破壁)](#8-shell-与系统命令破壁)
- [9. 内置 Agent(`@local` `@remote` `@db` `@spider` `@RAG` `@stock`)](#9-内置-agent)
- [10. 自定义 Agent 分身](#10-自定义-agent-分身)
- [11. MasterAgent 自我进化主控](#11-masteragent-自我进化主控)
- [12. 蜂群协作(Swarm)](#12-蜂群协作swarm)
- [13. 邮件(邮差 + M365)](#13-邮件邮差--m365)
- [14. 阿里云盘(腾云)](#14-阿里云盘腾云)
- [15. RAG 本地知识库](#15-rag-本地知识库)
- [16. MCP 外部神通](#16-mcp-外部神通)
- [17. 动态构建(`/build`)](#17-动态构建build)
- [18. 思维模式:`/mode` 与计划模式](#18-思维模式mode-与计划模式)
- [19. Hermes 后台自治引擎](#19-hermes-后台自治引擎)
- [20. 上下文压缩](#20-上下文压缩)
- [21. 定时任务(结界)与 Gatekeeper 守护](#21-定时任务结界-与-gatekeeper-守护)
- [22. 安全机制与自治模式](#22-安全机制与自治模式)
- [23. Web 控制台](#23-web-控制台)
- [24. 系统状态 / 用量统计 / 错误报告](#24-系统状态--用量统计--错误报告)
- [25. 插件(法宝)系统](#25-插件法宝系统)
- [26. 本机应用启动(驭器)](#26-本机应用启动驭器)
- [27. 配置参考(`~/.fr_cli/config.json`)](#27-配置参考)
- [28. 高级用法与脚本调用](#28-高级用法与脚本调用)
- [29. 故障排查](#29-故障排查)
- [30. 速查表](#30-速查表)

---

## 1. 安装

### 1.1 PyPI 安装(推荐)

```bash
pip install fr-cli
```

### 1.2 源码安装

```bash
git clone https://github.com/leungyukit/fr-cli.git
cd fr-cli
pip install -e .
```

### 1.3 一键脚本(macOS/Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/leungyukit/fr-cli/master/release/fr-cli-install.sh | bash
```

### 1.4 Docker 部署

仓库内置 `Dockerfile` + `docker-compose.yml`:

```bash
docker compose up fr-cli
```

### 1.5 核心依赖

```bash
# 必须
pip install zhipuai>=2.0.0 openai>=1.0.0 requests

# 可选(按功能)
pip install chromadb sentence-transformers   # RAG 知识库
pip install aligo                              # 阿里云盘
pip install pymysql psycopg2-binary pyodbc oracledb paramiko  # DB + SSH
pip install pandas openpyxl                    # Excel/CSV
pip install paddleocr paddlepaddle             # OCR(本地引擎)
pip install mcp                                # MCP 外部工具
pip install pillow                             # 图像
```

---

## 2. 快速开始

### 2.1 首次启动

```bash
fr-cli
```

首次启动会进入交互式配置向导,提示你选择提供商、模型、设置 API Key。

### 2.2 一行命令模式

```bash
# 一次对话后退出
fr-cli "请总结 README.md"

# 从文件读提示词
fr-cli -f prompt.txt

# 从 stdin 读
cat article.txt | fr-cli -s

# 静默模式(跳过 banner)
fr-cli -q -c "/model current"
```

### 2.3 常用快捷键

| 快捷键 | 功能 |
|--------|------|
| `Enter` | 发送 |
| `Shift+Enter` / `Ctrl+J` | 换行 |
| `Ctrl+C` | 清空当前输入 |
| `Ctrl+L` | 清屏 |
| `Ctrl+D` | 退出 |
| `e` | 编辑上一条 |
| `r` | 重试上一条 |
| `u` | 撤销 |

### 2.4 输入语法

| 形式 | 含义 |
|------|------|
| `<文字>` | 与 AI 对话 |
| `!<cmd>` | 执行系统命令 |
| `!<cmd> \| <prompt>` | 命令输出管道给 AI 分析 |
| `/<cmd> [args]` | 执行 REPL 命令 |
| `@<agent> <task>` | 调用内置/自定义 Agent |

---

## 3. 模型与提供商配置

### 3.1 支持的提供商(25+ 道统)

| 道统 | 代表模型 | 备注 |
|------|---------|------|
| `zhipu` | glm-4-flash / glm-4-plus / cogview-3 | 默认(智谱) |
| `zhipu-coding` | glm-4-coding | 智谱编程特化 |
| `deepseek` | deepseek-chat / deepseek-coder | 高性价比 |
| `kimi` | moonshot-v1-8k / 32k / 128k | 长上下文 |
| `qwen` | qwen-turbo / qwen-plus / qwen-max | 阿里通义 |
| `stepfun` | step-1v-8k / step-1v-32k | 阶跃星辰 |
| `minimax` | abab6-chat / abab5.5 | MiniMax |
| `minimax-token-plan` | — | MiniMax Token 套餐(独立 Base URL) |
| `spark` | spark-v3.5 | 讯飞星火 |
| `doubao` | doubao-pro / lite | 字节豆包 |
| `mimo` | mimo-7b | 小米 |
| `mimo-token-plan` | — | 小米 Token 套餐 |
| `openai` | gpt-4o / gpt-4-turbo / gpt-3.5 | 兼容 OpenAI |
| `wenxin` | ernie-4 / ernie-3.5 | 文心一言 |
| `ollama` | 本地任意模型 | 通过 OpenAI 兼容 API |
| 自定义 `openai-compatible` | — | 自定义 Base URL |

### 3.2 配置方式

#### 方式 A:交互式向导(推荐新手)

```bash
>>> /model config
```

依次选择提供商 → 模型 → 粘贴 Key → 完成。

#### 方式 B:命令行直接配置

```bash
>>> /model glm-4-flash                    # 切换当前提供商的某个模型
>>> /model deepseek:deepseek-chat         # 同时切换提供商和模型
>>> /key sk-your-zhipu-key-here           # 设置当前提供商的 Key
>>> /providers use kimi                   # 切换活跃提供商
>>> /providers setup                      # 配置向导(类似 /model config)
```

#### 方式 C:Token Plan(订阅套餐)

某些提供商(如 MiniMax、小米)支持 Token 套餐,需要独立的 Base URL:

```json
{
  "providers": {
    "minimax": {
      "key": "your-token-plan-key",
      "model": "abab6-chat",
      "is_token_plan": true,
      "token_plan_base_url": "https://api.minimax.chat/v1"
    }
  }
}
```

`is_token_plan: true` 时,系统自动使用 `token_plan_base_url`。

### 3.3 命令速查

| 命令 | 功能 |
|------|------|
| `/model` | 显示当前模型 |
| `/model list` | 列出所有可用模型 |
| `/model current` | 显示当前模型详情 |
| `/model <name>` | 切换到指定模型 |
| `/model config` | 启动交互式配置向导 |
| `/model default` | 恢复当前提供商的默认模型 |
| `/providers` | 管理所有提供商 |
| `/providers use <p>` | 切换活跃提供商 |
| `/providers setup` | 提供商配置向导 |
| `/key [provider] <key>` | 设置 Key |
| `/limit <n>` | 设置最大 token 上限(默认 20000) |
| `/lang <zh\|en>` | 切换界面语言 |

### 3.4 Token 用量与计费

```bash
>>> /usage           # 最近 1 天汇总
>>> /usage 7         # 最近 7 天
>>> /usage 30        # 最近 30 天
```

每个 LLM 调用的费用按 `~/.fr_cli/config.json` 的 `usage_prices` 估算。
Zhipu、DeepSeek、Kimi 等主流模型已内置价格表;自定义模型可手动配置。

---

## 4. REPL 基本使用

### 4.1 `/help` 与 `/tutorial`

```bash
>>> /help                  # 显示所有命令分组
>>> /help agent            # 查看 Agent 主题详情
>>> /help mcp              # 查看 MCP 主题详情
>>> /help hermes           # 查看 Hermes 后台任务详情
>>> /help all              # 一次性查看所有主题

>>> /tutorial              # 交互式 10 步新手教程(按 Enter 翻页)
```

### 4.2 对话主流程

1. **输入消息** → 大模型流式返回
2. **AI 自动调用工具**(读文件、写文件、搜索、命令)
3. **AI 调用结果合并**(双源汇总模式)→ 二次生成
4. **自动保存上下文摘要**(最近 5 轮)
5. **自动按日期存档会话**(`~/.fr_cli/sessions/auto/YYYY-MM-DD_NN.json`)

### 4.3 UI 模式(影响 AI 是否主动调工具)

```bash
>>> /mode ui chat          # 纯对话:AI 只回答,不主动调工具
>>> /mode ui dev           # 开发(默认):AI 可以读写文件、执行命令
>>> /mode ui agent         # Agent 模式:启用 MasterAgent 自我进化主控
```

### 4.4 自治模式(影响安全确认粒度)

```bash
>>> /autonomous manual         # 默认:每次 sec_* 都询问
>>> /autonomous sandbox_auto   # 沙盒内(读/写/网络)自动放行
>>> /autonomous full_auto      # 所有操作自动放行(危险)
>>> /autonomous off            # 等同于 manual
```

`/autonomous` 也可通过环境变量 `FR_CLI_AUTONOMOUS_MODE` 设置。

---

## 5. 文件操作(洞府)

fr-cli 内置 VFS(Virtual File System)沙盒,**所有文件操作都限制在 `/dir` 添加的工作目录内**,禁止 `../` 逃逸。

### 5.1 工作目录管理

```bash
>>> /dir                         # 列出当前工作目录
>>> /dir <path>                  # 添加并切换到工作目录
>>> /dirs                        # 列出所有已挂载目录
>>> /rmdir <idx>                 # 移除指定挂载
```

### 5.2 文件读写

```bash
>>> /open <file>                 # 读取文件(支持 UTF-8/GBK/Latin-1)
>>> /write <file>                # 写入(多行输入,Ctrl+D 结束)
>>> /append <file> <text>        # 追加文本
>>> /delete <file>               # 删除(需安全确认)
```

### 5.3 文本编辑

AI 自动调:
```
【调用：write_file({"path": "a.md", "content": "..."})】
【调用：read_file({"path": "a.md"})】
【调用：list_files({})】
【调用：append_file({"path": "a.md", "content": "..."})】
【调用：delete_file({"path": "tmp.txt"})】
【调用：rename_file({"old_path": "a.md", "new_path": "b.md"})】
【调用：replace_text({"path": "a.md", "old_text": "foo", "new_text": "bar", "use_regex": false})】
【调用：grep_text({"path": "a.md", "pattern": "regex", "use_regex": true})】
```

### 5.4 安全机制

- VFS 路径解析:`Path.resolve()` 后必须落在某个 `allowed_dirs` 下
- 危险操作(`/write`、`/delete`、`/shell`)触发四阶安全确认(Y/A/F/N)
- 写入路径前缀检查:`== base_path or startswith(base_path + os.sep)`,防止 `/foo` 错误匹配 `/foo-bar`

### 5.5 配置文件位置

工作目录列表保存在 `~/.fr_cli/config.json` 的 `allowed_dirs` 字段。

---

## 6. 会话管理(轮回)

每个会话有唯一 UUID,自动按日期存档到 `~/.fr_cli/sessions/auto/YYYY-MM-DD_NN.json`。

### 6.1 基本命令

```bash
>>> /new                    # 新会话,清空上下文,显示启动画面
>>> /save <name>            # 手动保存当前会话
>>> /load                   # 交互式选择并加载历史会话
>>> /export                 # 导出当前会话为 Markdown
>>> /del                    # 交互式删除历史会话
```

### 6.2 按日期自动存档

```bash
>>> /session_list           # 列出所有按日期自动存档
>>> /session_load <N>       # 加载指定编号(继续对话)
>>> /session_del <N>        # 删除指定自动存档
```

存档格式:`sessions/auto/2026-06-30_01.json`(`01` 是当天第几个会话)。

### 6.3 上下文记忆与压缩

每次对话自动保留最近 5 轮摘要到 `~/.fr_cli/context.json`,加载会话时自动恢复。

超过阈值时自动压缩:

```bash
>>> /context status                 # 查看当前估算 token 与压缩配置
>>> /context compress               # 立即压缩
>>> /context threshold [N]          # 查看/设置阈值(0 关闭)
>>> /context keep [N]               # 查看/设置保留最近轮数
```

### 6.4 会话可视化(导出 HTML 时间线)

```bash
# 命令方式
>>> export_session_to_html ~/.fr_cli/sessions/auto/2026-06-30_01.json /tmp/timeline.html
```

生成自包含 HTML(暗色主题,内嵌 CSS),包含时间线、消息卡片、工具调用折叠面板。

### 6.5 对话队列

```bash
>>> /queue                  # 查看当前对话队列(连续输入的消息)
```

在 AI 响应未回来前连续输入的消息会自动排队,响应回来后依次发送。

---

## 7. 多模态:图片 / Excel / CSV / OCR

### 7.1 图片分析(`/see`)

```bash
>>> /see <图片路径> [问题]
```

**前提**:当前模型必须是当前 provider 的 vision 模型(例如 glm-4v、moonshot-v1-8k、deepseek-vl)。

AI 也可自动调用:
```
【调用：analyze_image({"path": "photo.jpg", "text": "描述这张图"})】
【调用：generate_image({"prompt": "一只猫在窗台"})】
```

### 7.2 Excel 读取

```bash
>>> /read_excel <文件>      # 输出列名/类型/统计/前10行预览
>>> /read_csv <文件>        # 同 Excel
```

AI 也可自动调用:
```
【调用：read_excel({"path": "sales_2026.xlsx"})】
```

### 7.3 OCR 文字识别

OCR 支持两种引擎,**Vision**(在线 API)和 **PaddleOCR**(本地)。

#### 配置引擎

```bash
>>> /ocr_config setup                # 交互式配置向导
>>> /ocr_config engine paddle       # 切换到本地 PaddleOCR
>>> /ocr_config engine vision       # 切换到 Vision API
>>> /ocr_config provider zhipu      # 设置 Vision 提供商
>>> /ocr_config model glm-4v         # 设置 Vision 模型
>>> /ocr_config key sk-xxx           # 设置专属 Key(可选)
>>> /ocr_config prompt "提取发票字段" # 自定义 OCR 提示词
```

#### 使用

```bash
>>> /ocr invoice.pdf
>>> /ocr /path/to/scan.jpg
```

依赖:`pip install paddleocr paddlepaddle`(本地引擎)、`pip install pymupdf`(PDF 识别)。

### 7.4 数据分析

fr-cli 通过 `weapon/dataframe.py` 提供统一的数据卷轴接口,支持 Excel/CSV 读取后让 AI 进行统计分析、生成图表。

---

## 8. Shell 与系统命令(破壁)

### 8.1 直接 Shell

```bash
>>> !ls -la                  # 执行命令
>>> !ps aux                   # 查看进程
>>> !cat log.txt              # 看日志
```

### 8.2 管道给 AI

```bash
>>> !ls -la | 找出最大的 5 个文件
>>> !ps aux | 哪些进程占用 CPU 超过 80%
>>> !cat log.txt | 这段日志有什么问题?
```

AI 基于命令输出生成分析。

### 8.3 Shell 模式(交互式)

```bash
>>> /shell                   # 进入 Shell 模式(进入命令循环)
(shell) $ ls -la            # 直接执行命令
(shell) $ df -h
(shell) $ exit              # 退出 Shell 模式回到 Agent
```

### 8.4 本机应用启动(驭器)

```bash
>>> /open https://example.com         # 用默认浏览器打开
>>> /open /Users/me/doc.pdf          # 用默认程序打开文件
>>> /launch chrome github.com        # 启动指定应用
>>> /launch word /Users/me/report.docx
>>> /apps                            # 列出可用别名
```

支持别名:chrome / safari / firefox / edge / word / excel / powerpoint / ppt / wps /
wechat / 微信 / qq / 钉钉 / 飞书 / vscode / terminal / 终端 / 计算器 / 记事本 /
music / 播放器 / spotify / vlc 等。

---

## 9. 内置 Agent

fr-cli 内置 6 个 `@` 前缀 Agent,直接在对话中使用即可。

### 9.1 `@local` — 本地系统操作

```bash
>>> @local 查看当前目录下最大的 10 个文件
>>> @local 清理 ~/.cache 下大于 100MB 的旧文件
>>> @local 当前系统的内存使用情况
```

实现:让 AI 生成 shell 命令,经安全确认后执行。

### 9.2 `@remote` — 远程 SSH 操作

**首次使用**:配置向导
```bash
>>> /remote_setup
```

编辑 `~/.fr_cli/remote/hosts.json`:
```json
{
  "myserver": {
    "host": "192.168.1.10",
    "user": "root",
    "key_file": "~/.ssh/id_rsa",
    "port": 22
  }
}
```

**使用**:
```bash
>>> @remote myserver 查看磁盘空间
>>> @remote myserver 启动 docker 服务
```

实现:`paramiko.SSHClient`,**无 shell 注入风险**。

### 9.3 `@spider` — 智能网页爬虫

```bash
>>> @spider https://example.com 2      # URL + 爬取深度
```

- 依赖:`pip install requests selenium`
- 输出:爬取的页面保存到 `web_YYYYMMDD/` 目录

### 9.4 `@db` — 数据库智能助手

**首次使用**:配置
```bash
>>> /db_setup
```

支持的数据库:**MySQL / PostgreSQL / SQL Server / Oracle**

配置文件:`~/.fr_cli/database.json`
```json
{
  "mydb": {
    "type": "mysql",
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "xxx",
    "database": "shop"
  }
}
```

**使用**:
```bash
>>> @db mydb 查询最近 7 天注册用户
>>> @db mydb 销量最高的 10 个商品
```

AI 自动分析 schema → 生成 SQL → 二次确认 → 执行 → 返回结果。

### 9.5 `@RAG` — 本地知识库问答

```bash
>>> /rag_dir ./docs            # 设置知识库目录并首次同步
>>> @RAG 项目的部署流程是什么
>>> @RAG 找一下"退款"相关的文档
```

详见 [15. RAG 本地知识库](#15-rag-本地知识库)。

### 9.6 `@stock` — 股票 / 量化交易

```bash
>>> @stock 查询茅台股价
>>> @stock 买入 600519 1500.00 100    # 模拟交易
```

详见 [章节 #stock](#)。

---

## 10. 自定义 Agent 分身

每个 Agent 分身有独立的设定、记忆、技能,存储在 `~/.fr_cli/agents/<name>/`。

### 10.1 创建 Agent(4 种方式)

#### 方式 1:AI 自动生成
```bash
>>> /agent_create <name> <description>
```

示例:
```bash
>>> /agent_create coder 编写高质量 Python 代码
```

#### 方式 2:代码铸造(从最近 AI 回复提取)
```bash
>>> /agent_forge <name>
```

适用:让 AI 在普通对话中生成代码,然后保存为 Agent。

#### 方式 3:自动检测
当 AI 回复中包含:
- `def run(context, **kwargs)`
- ` ```python ` 代码块

程序会自动提示输入名称保存为 Agent。

#### 方式 4:手动创建
```bash
mkdir -p ~/.fr_cli/agents/myagent
cat > ~/.fr_cli/agents/myagent/agent.py <<'EOF'
def run(context, **kwargs):
    """你的 Agent 逻辑"""
    user_input = context.get("user_input", "")
    return f"Echo: {user_input}"
EOF

cat > ~/.fr_cli/agents/myagent/persona.md <<'EOF'
# 角色设定
你是一个专业助手。
EOF
```

### 10.2 Agent 目录结构

```
~/.fr_cli/agents/<name>/
├── persona.md      # 角色设定(覆盖默认 system prompt)
├── memory.md       # 长期记忆(可读写)
├── skills.md       # 技能说明
├── agent.py        # 自定义逻辑(必须含 run(context, **kwargs))
├── workflow.md     # 可选工作流定义
└── config.json     # 专属模型配置
```

### 10.3 命令速查

```bash
>>> /agent_list                            # 列出所有 Agent
>>> /agent_show <name>                     # 查看详情
>>> /agent_run <name> [输入]               # 运行 Agent
>>> /agent_edit <name> persona|memory|skills|agent|workflow  # 编辑
>>> /agent_delete <name>                   # 删除
>>> /agent_model <name> [cfg]              # 查看/设置专属模型
```

### 10.4 专属模型绑定

```bash
>>> /agent_model myagent                              # 查看当前绑定
>>> /agent_model my_agent deepseek:deepseek-chat      # 绑定专属模型
>>> /agent_model my_agent --key sk-own-key            # 设置独立 Key
>>> /agent_model my_agent clear                       # 清除,恢复全局默认
```

Agent 的 `config.json`:
```json
{
  "provider": "deepseek",
  "model": "deepseek-chat",
  "key": ""
}
```

Agent 代码中通过 `context["provider"]` 和 `context["model"]` 感知当前绑定的道统。

### 10.5 工作流(`workflow.md`)

支持工作流引擎,Markdown 格式:

```markdown
# 工作流: 数据分析助手

## 步骤1: 收集数据
- **action**: search_web
- **params**:
  - query: "{{user_input}}"

## 步骤2: 整理内容
- **action**: ai_generate
- **params**:
  - prompt: "整理以下搜索结果:{{step1.result}}"

## 步骤3: 保存报告
- **action**: invoke_tool
- **params**:
  - tool: write_file
  - path: report.md
  - content: "{{step2.result}}"
```

支持的 step action:
- `ai_generate`:调用 LLM
- `invoke_tool` / `tool`:调用工具
- `execute_cmd` / `cmd`:执行命令
- `agent_call`:调用其他 Agent
- `save_memory`:保存到记忆

模板变量:
- `{{user_input}}`:原始输入
- `{{stepN.result}}`:前一步的结果
- `{{stepN.error}}`:前一步的错误
- `{{agent.persona}}`:Agent persona 内容

支持单步 `timeout: <秒>` 和 `retry_count: <n>`。
执行前自动检测循环依赖,有环则直接报错。

### 10.6 调用 Agent 的 3 种方式

```bash
# 1. 命令行
>>> /agent_run my_agent 请帮我总结 README.md

# 2. @ 前缀快捷
>>> @my_agent 请帮我总结 README.md

# 3. AI 作为工具调用
>>> 让 Agent X 帮我分析一下数据
【调用：agent_call({"name": "my_agent", "user_input": "..."})】
```

---

## 11. MasterAgent 自我进化主控

MasterAgent 是一个类似 OpenClaw 的中央控制器。**启用后接管所有普通对话**,通过 ReAct 循环自主调用工具,**每 10 次交互自动反思并进化 prompt**。

### 11.1 开关

```bash
>>> /master on
>>> /master off
>>> /master status
```

### 11.2 存储位置

`~/.fr_cli/master/`:

| 文件 | 说明 |
|------|------|
| `persona.md` | 人设文件 |
| `skills.md` | 技能装备文件 |
| `memory.json` | 交互记忆 |
| `evolution.json` | 进化记录 + prompt 追加 |
| `session.json` | 当前任务 + 历史 + 上下文笔记 |
| `status.json` | 启用状态 + 统计 |

### 11.3 ReAct 循环

```python
for step in range(8):
    txt = call_llm(history)
    if "【最终答案】" in txt:
        return extract_final_answer(txt)
    actions = extract_tool_calls(txt)
    for action in actions:
        obs = execute_tool(action)
        history.append({"role": "system", "content": f"Observation: {obs}"})
        record_interaction(action, obs)
```

### 11.4 后台隔离执行

MasterAgent 支持 `background=True` 模式:Hermes 后台任务使用该参数,避免后台执行污染用户主会话的 `state.messages`、上下文摘要和自动存档;同时禁用交互式产物检测,改为进入 `PersistentReviewQueue`。

### 11.5 失败驱动学习

MasterAgent 按 `(tool, error_type)` 统计失败,生成 `failure_hints` 并注入 system prompt,让 AI 避免重复犯错。

---

## 12. 蜂群协作(Swarm)

蜂群功能允许同时调用多个任务单元协作处理任务,支持三种模式。

### 12.1 三种协作模式

| 模式 | 说明 | 适用 |
|------|------|------|
| `parallel` | 并发独立调用 | 多角度并行分析、批量处理 |
| `council` | 并行后由 LLM 汇总 | 评审、投票、共识生成 |
| `pipeline` | 串联执行,前一个输出作为后一个输入 | 分阶段加工 |

### 12.2 任务名称格式

```
agent:myagent              # 自定义/远程 Agent
@local 或 builtin:local    # 内置 Agent
tool:search_web            # 注册表工具
cmd:/web 搜索词            # 命令字符串
mcp:fs/read_file {"path": "/tmp/a.txt"}  # MCP 工具
plugin:myplugin            # 自定义插件
```

无显式前缀时自动推断优先级:Agent > 内置 Agent > 插件 > 工具 > 命令。

### 12.3 命令示例

```bash
# 并行
>>> /swarm parallel coder,reviewer 帮我 review 这段代码
>>> /swarm parallel @local,tool:search_web 分析项目并搜索资料

# 议会
>>> /swarm council planner,coder,reviewer 设计一个用户登录模块

# 流水线
>>> /swarm pipeline extractor,summarizer 从报告中提取关键点并生成摘要
>>> /swarm pipeline tool:search_web,cmd:/write report.md 搜索并保存报告
```

### 12.4 AI 调用

```
【调用：swarm_run({"mode": "council", "names": ["coder", "reviewer"], "user_input": "..."})】
```

参数:
- `mode`:parallel / council / pipeline
- `names`:任务名称列表(逗号分隔)
- `user_input`:任务描述
- `max_workers`:最大并发数(默认 5,上限 10)

某个任务失败时仅记录 `error` 字段,不影响蜂群整体执行。

---

## 13. 邮件(邮差 + M365)

### 13.1 普通邮件(IMAP/SMTP)

**首次使用**:
```bash
>>> /mail setup
```

依次输入邮箱地址、SMTP/IMAP 服务器地址、端口、授权码(QQ/163 邮箱需使用授权码,而非登录密码)。

支持邮箱:QQ / 163 / Gmail / Outlook / 阿里云。

**命令**:
```bash
>>> /mail inbox             # 查看最近 10 封
>>> /mail read <id>         # 读取完整内容
>>> /mail send a@b.com 主题 正文
```

AI 也可自动调用:
```
【调用：mail_inbox({})】
【调用：mail_read({"id": "1"})】
【调用：mail_send({"to": "a@b.com", "subject": "主题", "body": "正文"})】
```

### 13.2 Microsoft 365(现代认证)

**首次使用**:
```bash
>>> /m365_config setup
```

支持 OAuth2 设备码 / 授权码流 + MFA。

```bash
>>> /m365_inbox            # 收件箱
>>> /m365_read <id>        # 读邮件
>>> /m365_send a@b.com 主题 正文
```

Token 缓存:`~/.fr_cli/m365.json`(文件权限 0o600)。

### 13.3 安全

- 邮件头注入防护:过滤 `\r`、`\n`
- 发送邮件前触发 `sec_send_mail` 安全确认

---

## 14. 阿里云盘(腾云)

```bash
>>> /disk_setup             # 扫码登录(首次)
>>> /disk_ls                # 列出当前目录
>>> /disk_cd 文档           # 进入子目录
>>> /disk_cd ..             # 返回上级
>>> /disk_up /local/a.pdf a.pdf      # 上传
>>> /disk_down a.pdf /local/         # 下载
```

依赖:`pip install aligo`。

上传/下载触发 `sec_upload_disk` / `sec_download_disk` 安全确认。

---

## 15. RAG 本地知识库

把本地文档向量化,让 AI 基于知识库回答。

### 15.1 快速使用

```bash
>>> /rag_dir <目录路径>     # 设置知识库目录并首次同步
>>> @RAG <问题>             # 基于知识库问答
```

### 15.2 手动同步与监控

```bash
>>> /rag_sync [路径]        # 立即向量化新文件/更新文件
>>> /rag_watch start [目录] [--interval N]   # 启动持久化后台监控
>>> /rag_watch stop         # 停止守护进程
>>> /rag_watch status       # 查看守护进程状态
>>> /rag_watch log [--lines N]   # 查看守护进程日志
```

### 15.3 监控模式说明

| 模式 | 说明 |
|------|------|
| 内置模式(`/rag_dir` 后自动启动) | daemon 线程,fr-cli 退出后终止 |
| 独立模式(`/rag_watch start`) | 系统级子进程,脱离终端,日志写入 `~/.fr_cli/rag/watcher.log` |

### 15.4 技术栈

- **向量库**:ChromaDB(嵌入式 `PersistentClient`,无需单独服务)
- **嵌入模型**:all-MiniLM-L6-v2
- **检索**:top-8 片段,然后一次性交给大模型综合生成,标注来源

### 15.5 依赖安装

```bash
pip install chromadb sentence-transformers
```

### 15.6 数据存储

- 向量库:`~/.fr_cli/rag/chroma/`
- 文件索引:`~/.fr_cli/rag/index.json`
- 守护进程日志:`~/.fr_cli/rag/watcher.log`

---

## 16. MCP 外部神通

MCP(Model Context Protocol)允许连接外部服务器,将其工具纳入 AI 调用范围。

### 16.1 管理命令

```bash
>>> /mcp_list               # 列出所有服务器及其可用工具
>>> /mcp_add <名> <命令> [参数...]   # 添加 stdio 服务器
>>> /mcp_del <名>           # 删除服务器
>>> /mcp_enable <名>        # 启用
>>> /mcp_disable <名>       # 禁用
>>> /mcp_refresh            # 刷新工具列表
```

### 16.2 配置文件

`~/.fr_cli/config.json` 的 `mcp.servers`:
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
      },
      {
        "name": "remote",
        "transport": "http",
        "url": "https://example.com/mcp",
        "headers": {"Authorization": "Bearer xxx"},
        "enabled": true
      }
    ]
  }
}
```

支持的 transport:`stdio`、`streamable_http`、`sse`。

### 16.3 AI 调用

```
【调用：mcp_call({"server": "服务器名", "tool": "工具名", "arguments": {...}})】
【调用：mcp_list({})】
```

### 16.4 Resources / Prompts

MCP 还支持 Resources 和 Prompts 协议:
- `list_resources(server)` / `list_all_resources()` / `read_resource_sync(server, uri)`
- `list_prompts(server)` / `list_all_prompts()` / `get_prompt_sync(server, name, args)`

### 16.5 示例:接入官方 filesystem MCP

```bash
>>> /mcp_add fs npx -y @modelcontextprotocol/server-filesystem /tmp
>>> /mcp_refresh
>>> /mcp_list
```

### 16.6 依赖

```bash
pip install mcp
```

### 16.7 SSRF 防护

`_is_private_url()` 拦截:
- 非 http/https 协议
- localhost / 127.0.0.1 / 0.0.0.0
- 私有 IP 段:10/8、172.16/12、192.168/16、169.254/16

---

## 17. 动态构建(`/build`)

fr-cli 支持根据用户需求**自主安装依赖并动态生成工具**,生成后立即注册到命令注册表。

### 17.1 触发方式

```bash
# 手动
>>> /build 生成一个二维码识别工具
>>> /build 把图片转换成 ASCII 艺术

# AI 自动
>>> 帮我生成一个二维码
【调用：dynamic_build({"requirement": "..."})】
```

### 17.2 管理已构建工具

```bash
>>> /build list             # 列出已构建工具
>>> /build check <name>     # 重新测试并修复
>>> /build del <name>       # 删除
```

### 17.3 工作流程

1. **需求规划**:LLM 判断需求是否已被现有能力覆盖
2. **依赖安装**:自动检查并提示安装所需的 pip 包
3. **代码生成**:LLM 生成包含 `run(deps, **kwargs)` 入口的 Python 代码
4. **自测**:自动运行 + 失败回滚
5. **持久化 + 注册**:保存到 `~/.fr_cli/dynamic_tools/<name>.py`,元数据写入 `registry.json`

### 17.4 代码约定

动态工具必须包含:
```python
def run(deps, **kwargs):
    """工具入口"""
    # deps 包含: vfs, mail_c, web_c, disk_c, plugins, lang, security, cfg, client, model_name, mcp
    # 返回: Result.ok(data) 或 Result.fail(error)
    ...
```

`Result` 的 `error` 为 `None` 或错误字符串(同时兼容 `(result, error)` 解包)。

第三方依赖缺失时,在函数内部捕获 `ImportError` 并返回安装提示。

### 17.5 工具覆盖检查

新增:能力缺口发现 — `/build check <需求>` 或 AI 工具 `analyze_gap` / `build_missing_tool` 可检测缺口并自动生成。

---

## 18. 思维模式(`/mode`)与计划模式

### 18.1 5 种思维模式

```bash
>>> /mode direct            # 直接回答(默认)
>>> /mode cot               # 思维链 — 先拆解、自我验证
>>> /mode tot               # 思维树 — 多分支策略、评估选最优
>>> /mode react             # ReAct — 思考→行动→观察,循环
>>> /mode plan              # 计划模式 — 制定结构化计划、用户确认、逐步执行、汇总
```

### 18.2 思维模式引擎

位置:`fr_cli/core/thinking.py`

- CoT / ToT 需要额外一次流式调用,思维过程展示给用户
- ReAct 模式的 reasoning 注入 system prompt(用户看不到推理过程)
- plan 模式先生成计划、用户确认、按步骤执行、汇总

### 18.3 计划模式示例

```bash
>>> /mode plan
>>> 帮我调研 Python 3.13 的新特性,生成一份报告
```

AI 输出:
```
## 计划:调研 Python 3.13 新特性
1. 联网搜索"Python 3.13 release notes"
2. AI 整理搜索结果
3. 保存为 report.md

是否执行? [Y/n]: Y
执行步骤 1/3... ✓
执行步骤 2/3... ✓
执行步骤 3/3... ✓

总结:
Python 3.13 主要新特性包括...
```

---

## 19. Hermes 后台自治引擎

Hermes 是持久化的后台任务引擎,负责任务创建、调度、执行、与 MasterAgent 联动。

### 19.1 存储位置

`~/.fr_cli/hermes/`:
- `tasks.json` — 任务队列(状态/优先级/重试/结果)
- `goals.json` — 目标与里程碑
- `analytics.json` — 任务统计
- `hermes.log` — 运行日志
- `review_queue.json` — 后台产物审核队列

### 19.2 安全执行模式

| 模式 | 说明 |
|------|------|
| `sandbox`(默认) | 后台任务默认模式;沙盒自动放行,系统级非交互默认拒绝 |
| `autonomous` | 完全信任该任务;所有操作自动放行 |
| `interactive` | 占位;不走后台 |

### 19.3 REPL 命令

```bash
>>> /hermes start [port]                  # 启动独立 HTTP 守护进程(默认 8765)
>>> /hermes stop
>>> /hermes status                        # 引擎状态
>>> /hermes task [--autonomous|-a] <描述> # 创建任务(默认 sandbox)
>>> /hermes confirm <id>                  # 确认 autonomous 任务
>>> /hermes list [status]                  # 列任务
>>> /hermes log <id>                      # 查看任务结果
>>> /hermes cancel <id>                   # 暂停任务
>>> /hermes review                        # 查看后台产物审核队列
>>> /hermes review approve <id> [name]    # 批准并安装
>>> /hermes review reject <id>            # 拒绝
```

### 19.4 HTTP API(默认 `127.0.0.1:8765`,写端点需 Bearer Token)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/info` | 引擎状态 |
| GET | `/tasks` | 任务列表 |
| POST | `/task` | 创建任务 |
| POST | `/chat` | 提交对话任务 |
| POST | `/goal` | 创建目标 |
| GET | `/review` | 审核队列 |

### 19.5 目标自动分解

```bash
>>> /hermes goal [--autonomous] [--tags a,b] <目标描述>
>>> HTTP POST /goal with {"description": "...", "decompose": true}
```

自动分解为子任务(LLM 决策),通过 `chain_next` 串联。

### 19.6 子任务依赖 / 链式执行

任务字段:
- `dependencies`:依赖的任务 ID 列表
- `chain_next`:完成后自动启动的任务 ID

调度器自动检测循环依赖。

### 19.7 失败重试与超时

- 单个任务默认 300 秒超时(`FR_CLI_HERMES_TASK_TIMEOUT` 可覆盖)
- 失败后按重试策略重试,达到最大次数标记 FAILED

### 19.8 一键启动所有服务

```bash
>>> /autostart                              # 默认端口
>>> /autostart --agent-server 17890 --hermes 8765
```

启动项:
- 启用 MasterAgent(若未启用)
- Agent HTTP 服务(默认 17890)
- Hermes HTTP 守护进程(默认 8765)
- Gatekeeper 守护进程
- 同步 Cron 定时任务配置

---

## 20. 上下文压缩

长会话累积过多 token 时,自动压缩早期对话,保留最近 N 轮完整对话。

### 20.1 命令

```bash
>>> /context status                 # 当前估算 token 与配置
>>> /context compress               # 立即压缩当前会话
>>> /context threshold [N]          # 查看/设置自动压缩阈值(0 关闭)
>>> /context keep [N]               # 查看/设置保留最近轮数
```

### 20.2 配置项(`~/.fr_cli/config.json`)

```json
{
  "memory": {
    "compress_threshold": 4000,
    "compress_keep_recent": 5
  }
}
```

自适应阈值:不超过模型 token 上限的 60%,避免小上限模型未触发压缩。

### 20.3 工作原理

```python
def auto_compress_messages(state, messages):
    threshold = state.context_compress_threshold      # 默认 4000
    keep_recent = state.context_compress_keep_recent  # 默认 5
    if threshold <= 0 or len(messages) <= keep_recent * 2 + 1:
        return
    limit = state.limit or 0
    effective_threshold = min(threshold, int(limit * 0.6)) if limit > 0 else threshold
    compressed, did_compress, before, after = maybe_compress(...)
    if did_compress:
        messages[:] = compressed
```

---

## 21. 定时任务(结界)与 Gatekeeper 守护

### 21.1 内存级定时任务(`/cron`)

```bash
>>> /cron_add <秒> <命令>       # 添加循环任务(基于 threading.Timer)
>>> /cron_list                  # 列出运行中任务
>>> /cron_del <id>              # 删除
```

示例:
```bash
>>> /cron_add 300 ls -la /project       # 每 5 分钟
>>> /cron_add 60 df -h                  # 每分钟
```

注意:
- 强制 `interval >= 5` 秒
- 命令执行 30 秒超时,输出截断 100 字符
- Shell 命令通过 `shlex.split + shell=False` 执行,无注入风险
- **程序退出后任务消失**

### 21.2 Gatekeeper 守护进程(持久化)

```bash
>>> /gatekeeper start
>>> /gatekeeper stop
>>> /gatekeeper status
```

守护进程独立运行,持久化以下服务:
- Agent HTTP 服务
- 全局定时任务
- Agent 定时任务

### 21.3 Agent 定时任务

```bash
>>> /agent_cron_add <agent名称> <秒> [输入]   # 为 Agent 添加定时执行
>>> /agent_cron_list
>>> /agent_cron_del <ID>
```

### 21.4 配置同步

守护进程每 30 秒热重载配置,主进程新增/删除任务后自动同步。

守护进程配置存储在 `~/.fr_cli/daemon/config.json`。

---

## 22. 安全机制与自治模式

### 22.1 四阶安全确认(Y/A/F/N)

```
⚠️ 写入文件 /tmp/test.txt
   内容: Hello World
[Y]仅此    [A]本轮    [F]永世    [N]拒绝    选:
```

- `Y` — 仅允许本次(Once)
- `A` — 本次会话内允许同类(Session)
- `F` — 永久允许同类(Forever),写入 `~/.fr_cli/config.json`
- `N` / 回车 — 拒绝(Deny)

### 22.2 受保护操作(sec_*)

| 类别 | 含义 |
|------|------|
| `sec_read` | 读文件 |
| `sec_write` | 写文件 |
| `sec_exec` | 执行命令/插件/Agent |
| `sec_mount` | 添加工作目录 |
| `sec_gen_img` | 生成图片 |
| `sec_send_mail` | 发邮件 |
| `sec_fetch_web` | 抓取网页 |
| `sec_upload_disk` | 上传云盘 |
| `sec_download_disk` | 下载云盘 |
| `sec_shell` | Shell 命令 |

### 22.3 自治模式(`/autonomous`)

```bash
>>> /autonomous manual         # 默认:每次 sec_* 都询问
>>> /autonomous sandbox_auto   # 沙盒(读/写/网络)自动放行,系统级仍询问
>>> /autonomous full_auto      # 所有自动放行(危险)
>>> /autonomous off            # 等同于 manual
```

也可通过环境变量 `FR_CLI_AUTONOMOUS_MODE=manual|sandbox_auto|full_auto` 设置。

### 22.4 撤销永久放行

```bash
>>> /unconfirm                 # 清除所有 F 永久放行
```

### 22.5 路径穿越防护

VFS `_resolve()` 使用 `Path.resolve()`,解析后检查路径前缀:
- `== base_path` 或 `startswith(base_path + os.sep)`
- 禁止 `../` 逃逸到允许目录之外
- 防止 `/foo` 错误匹配 `/foo-bar`

### 22.6 邮件头注入防护

`mail.py` 中邮件头字段过滤 `\r`、`\n`,防止 SMTP 头注入。

### 22.7 SSH 注入防护

`agent/builtins/remote.py` 用 `paramiko.SSHClient().connect() + exec_command()`,**彻底消除** `subprocess.run(ssh_cmd, shell=True)` 的远程命令注入风险。

### 22.8 配置写入安全

`save_config()` 使用:
- `tempfile.mkstemp(dir=CONFIG_FILE.parent)` 创建临时文件
- `os.chmod(fd, 0o600)` 设置仅所有者可读写
- `os.replace(tmp, CONFIG_FILE)` 原子替换

### 22.9 Agent HTTP 安全

- 默认绑定 `host="127.0.0.1"`
- 启动时生成随机 Bearer Token:`secrets.token_hex(16)`
- 所有端点需携带 `Authorization: Bearer <token>`

### 22.10 非交互模式

```bash
export FR_CLI_NON_INTERACTIVE=1
```

非交互场景下,安全确认默认拒绝(用于脚本/CI)。

---

## 23. Web 控制台

Web 控制台提供实时事件流、指标仪表盘、远程管理界面。

### 23.1 启动

```bash
>>> /agent_server start [port]      # 默认 17890,绑定 127.0.0.1
```

或自动启动所有服务:
```bash
>>> /autostart
```

### 23.2 REST API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/info` | 引擎状态 |
| GET | `/agents` | 列出 Agent |
| GET | `/agents/<name>` | Agent 详情 |
| POST | `/agents/<name>/run` | 运行 Agent |
| POST | `/agents/<name>/workflow` | 运行工作流 |
| GET | `/api/events` | SSE 长连接 |
| POST | `/api/event` | 推送客户端事件 |
| GET | `/api/metrics?format=json\|prom\|summary` | 指标 |

`/run` 默认超时 120 秒,`/workflow` 默认 180 秒,可通过请求体 `timeout` 字段覆盖(最大 600 秒)。超时返回 HTTP 504。

### 23.3 SSE 实时事件流

```bash
curl -N "http://127.0.0.1:17890/api/events?token=YOUR_TOKEN"
```

事件类型:
- `status` — 系统状态
- `task` — Hermes 任务进度
- `log` — 日志消息
- `tool` — 工具调用
- `llm` — LLM 调用
- `agent` — Agent 事件
- `custom` — 自定义事件

### 23.4 鉴权

所有端点需携带 `Authorization: Bearer <token>`,Token 启动时随机生成,首次启动打印到 stdout 并写入 `~/.fr_cli/console_token`。

### 23.5 示例:外部系统调用

```bash
TOKEN=$(cat ~/.fr_cli/console_token)

# 列出 Agent
curl http://127.0.0.1:17890/agents -H "Authorization: Bearer $TOKEN"

# 运行 Agent
curl -X POST http://127.0.0.1:17890/agents/myagent/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input": "请分析这个需求", "timeout": 120}'

# 实时事件流
curl -N http://127.0.0.1:17890/api/events?token=$TOKEN
```

---

## 24. 系统状态 / 用量统计 / 错误报告

### 24.1 `/status` 全局状态面板

```bash
>>> /status                       # 人类可读面板
>>> /status json                  # JSON 格式
```

展示内容:
- 当前 provider / model / API Key 是否配置
- 自治模式(manual / sandbox_auto / full_auto)
- MasterAgent 是否启用及交互次数
- Agent HTTP 服务、Hermes 守护进程、Gatekeeper 运行状态
- Hermes 任务统计(pending / running / completed / failed / paused)
- 审核队列 pending 数量
- Cron 定时任务数量
- 已加载插件数量、Agent 分身数量
- RAG 监控状态

### 24.2 `/usage` LLM 用量统计

```bash
>>> /usage                        # 最近 1 天
>>> /usage 7                      # 最近 7 天
>>> /usage 30                     # 最近 30 天
```

按 provider/model 聚合,显示 token 数 + 估算费用(基于 `usage_prices` 表)。

用量持久化到 `~/.fr_cli/usage.json`(文件权限 0o600)。

### 24.3 `/status errors` 集中式错误报告

```bash
>>> /status errors
```

聚合:
- Hermes 任务失败与失败模式
- 动态构建自测失败记录
- 安全审核被拒绝的操作
- MasterAgent 失败模式

通过 EventBus 自动订阅各模块的 `*.failed` 事件。

### 24.4 Prometheus 指标导出

`/api/metrics?format=prom` 返回 Prometheus 文本格式:

```
# HELP fr_cli_requests_total Total requests
# TYPE fr_cli_requests_total counter
fr_cli_requests_total{tool="write_file"} 42
```

支持的指标类型:
- counter:累计计数(如 `requests_total`)
- histogram:分布统计(如 `latency_seconds`)
- timer:延迟统计
- gauge:当前值(如活跃连接数)

可通过 `MetricsPlugin` 自定义钩子。

---

## 25. 插件(法宝)系统

fr-cli 支持自定义插件,放在 `~/.fr_cli/plugins/<name>.py`。

### 25.1 插件约定

```python
def run(args: str = "") -> str:
    """插件入口,返回字符串结果"""
    return f"Echo: {args}"
```

### 25.2 调用方式

```bash
>>> /<plugin_name> <args>          # 直接调用
```

AI 也可调:
```
【命令：/my_plugin arg1 arg2】
```

### 25.3 安全性

- 插件名通过 `name.isidentifier()` 校验
- 参数用 `json.dumps()` 序列化
- `runpy.run_path()` 隔离执行,15 秒超时
- 子进程隔离,主进程不受影响

### 25.4 插件 vs Agent 分身

| 形式 | 类型 | 保存位置 |
|------|------|----------|
| `def run(args='')` | 插件 | `~/.fr_cli/plugins/` |
| `def run(context, **kwargs)` | Agent 分身 | `~/.fr_cli/agents/` |

---

## 26. 本机应用启动(驭器)

```bash
>>> /open <路径/URL>              # 用系统默认程序打开
>>> /launch <应用> [目标]         # 启动应用
>>> /apps                         # 列出可用别名
```

### 26.1 别名表(部分)

| 类别 | 别名 |
|------|------|
| 浏览器 | chrome, safari, firefox, edge, 浏览器 |
| 办公 | word, excel, powerpoint, ppt, wps |
| 通讯 | wechat, 微信, qq, 钉钉, 飞书 |
| 工具 | vscode, terminal, 终端, 计算器, 记事本 |
| 媒体 | music, 播放器, spotify, vlc |

新增应用别名,修改 `weapon/launcher.py` 的 `_APP_ALIASES`。

---

## 27. 配置参考

完整配置文件:`~/.fr_cli/config.json`(部分字段):

```json
{
  "key": "your-zhipu-key",
  "provider": "zhipu",
  "model": "glm-4-flash",
  "providers": {
    "zhipu":     {"key": "", "model": "glm-4-flash"},
    "deepseek":  {"key": "sk-ds-xxx", "model": "deepseek-chat"},
    "kimi":      {"key": "", "model": "moonshot-v1-8k"},
    "minimax":   {"key": "", "model": "abab6-chat", "is_token_plan": true,
                  "token_plan_base_url": "https://api.minimax.chat/v1"}
  },
  "limit": 20000,
  "allowed_dirs": ["/Users/me/projects"],
  "lang": "zh",
  "aliases": {},
  "auto_confirm_forever": false,
  "mail": {},
  "disk": {},
  "mcp": {"servers": []},
  "ocr": {
    "engine": "vision",
    "provider": "zhipu",
    "model": "glm-4v",
    "key": "",
    "base_url": "",
    "prompt": ""
  },
  "stock": {
    "default_source": "akshare",
    "akshare": {"enabled": true},
    "mairui":  {"enabled": false, "key": "", "base_url": "https://api.mairui.club"},
    "tushare": {"enabled": false, "token": ""},
    "trade":   {"enabled": false, "api": "", "key": "", "secret": "", "base_url": ""},
    "portfolio": {}
  },
  "usage_prices": {
    "deepseek": {
      "deepseek-chat": {"prompt": 1.5, "completion": 6.0}
    }
  },
  "memory": {
    "compress_threshold": 4000,
    "compress_keep_recent": 5
  }
}
```

### 27.1 数据目录结构

```
~/.fr_cli/
├── config.json                       # 主配置
├── usage.json                        # LLM 用量(0o600)
├── cron.json                         # 定时任务
├── context.json                      # 上下文摘要
├── m365.json                         # M365 OAuth token(0o600)
├── console_token                     # Web 控制台 Bearer Token
├── sessions/
│   ├── manual/                       # 手动保存的会话
│   └── auto/YYYY-MM-DD_NN.json       # 自动按日期存档
├── plugins/<name>.py                 # 用户插件
├── dynamic_tools/<name>.py           # /build 生成的工具
├── agents/<name>/                    # Agent 分身
├── master/                           # MasterAgent 状态
├── hermes/                           # Hermes 后台引擎
├── rag/                              # RAG 知识库
│   ├── chroma/                       # ChromaDB 向量库
│   ├── index.json                    # 文件索引
│   └── watcher.log                   # 守护进程日志
├── remote/hosts.json                 # SSH 主机配置
├── database.json                     # 数据库配置
├── stock.json                        # 股票数据源配置
├── exports/session_*.html            # 会话 HTML 时间线导出
└── daemon/config.json                # Gatekeeper 配置
```

### 27.2 配置安全

- `config.json` 写入用 `tempfile.mkstemp` + `os.chmod(0o600)` + 原子替换
- `usage.json`、`m365.json` 文件权限 0o600

---

## 28. 高级用法与脚本调用

### 28.1 命令行参数

```bash
fr-cli [选项] [prompt]
fr-cli -c "/command" [args]           # 执行单条 / 命令后退出
fr-cli -p "问题"                       # 单次 AI 对话后退出
fr-cli -s                              # 从 stdin 读提示词
fr-cli -f <file>                       # 从文件读提示词
fr-cli -q                              # 静默模式(跳过 banner)
```

### 28.2 在脚本中调用 fr-cli

```bash
# 输出 JSON(待规划)
fr-cli -q -c "/status json"
```

### 28.3 环境变量

| 变量 | 用途 |
|------|------|
| `FR_CLI_AUTONOMOUS_MODE` | 自治模式(manual / sandbox_auto / full_auto) |
| `FR_CLI_NON_INTERACTIVE` | 非交互模式(1 启用,所有确认默认拒绝) |
| `FR_CLI_HERMES_TASK_TIMEOUT` | 单个 Hermes 任务超时(秒,默认 300) |
| `FR_CLI_FLAKY_SSE` | 跳过 SSE 偶发测试 |

### 28.4 与 Mavis Agent 集成

fr-cli 提供的工具、Agent、Hermes 任务可以被外部系统通过 REST API 调用。详见 [23. Web 控制台](#23-web-控制台)。

### 28.5 Dockerfile 部署

仓库内置 `Dockerfile` + `docker-compose.yml`:

```yaml
services:
  fr-cli:
    build: .
    stdin_open: true
    tty: true
    volumes:
      - ~/.fr_cli:/root/.fr_cli
      - $(pwd):/app/workspace
```

---

## 29. 故障排查

### 29.1 模型未配置

```
⚠️ 模型未配置,请使用 /model <模型名> 或 /model config 选择模型。
```

**解决**:`/model config` 走向导,或手动 `/key + /model`。

### 29.2 API Key 无效

```
401 Unauthorized
```

**解决**:
- 检查 `/model current` 显示的 Key 是否正确
- `/key <provider> <key>` 重新设置
- 智谱/DeepSeek 控制台查看 Key 是否过期

### 29.3 路径不在允许目录

```
不允许的路径:/etc/passwd
```

**解决**:`/dir <path>` 添加工作目录,或使用 `/dirs` 检查已挂载目录。

### 29.4 Agent HTTP 启动失败

```
无法绑定 127.0.0.1:17890: [Errno 48] Address already in use
```

**解决**:
- 找到占用进程:`lsof -i :17890`
- 或换端口:`/agent_server start 17891`

### 29.5 MCP 服务器无法连接

```
[Errno 2] No such file or directory: 'npx'
```

**解决**:
- 安装 Node.js + npm
- 或换用 Python MCP server:`/mcp_add myserver python my_server.py`

### 29.6 OCR 引擎不可用

```
PaddleOCR not installed
```

**解决**:`pip install paddleocr paddlepaddle`,或切换 Vision 引擎:`/ocr_config engine vision`。

### 29.7 测试时偶发失败

部分 SSE / MCP 测试在并发场景下偶发失败(网络时序问题),可通过环境变量跳过:

```bash
FR_CLI_FLAKY_SSE=1 pytest tests/
```

### 29.8 日志位置

- 主程序日志:stderr
- Hermes 日志:`~/.fr_cli/hermes/hermes.log`
- RAG 守护日志:`~/.fr_cli/rag/watcher.log`
- Agent 错误:`~/.fr_cli/master/memory.json` + `/status errors`

---

## 30. 速查表

### 30.1 模型 & 提供商

| 命令 | 功能 |
|------|------|
| `/model` | 显示当前 |
| `/model config` | 配置向导 |
| `/model list` | 列出模型 |
| `/model <n>` | 切换 |
| `/model <p>:<m>` | 同时切提供商 |
| `/providers use <p>` | 切提供商 |
| `/key <k>` | 设 Key |
| `/limit <n>` | token 上限 |
| `/lang zh\|en` | 切语言 |
| `/usage [days]` | 用量 |
| `/autonomous <mode>` | 自治 |

### 30.2 文件 & 会话

| 命令 | 功能 |
|------|------|
| `/dir <p>` | 加工作目录 |
| `/dirs` | 列已挂载 |
| `/open <f>` | 读文件 |
| `/write <f>` | 写 |
| `/append <f>` | 追加 |
| `/delete <f>` | 删 |
| `/new` | 新会话 |
| `/save <n>` | 保存 |
| `/load` | 加载 |
| `/export` | 导出 MD |
| `/session_list` | 自动存档 |
| `/session_load <n>` | 加载自动 |
| `/context compress` | 压缩上下文 |

### 30.3 多模态

| 命令 | 功能 |
|------|------|
| `/see <img>` | 看图 |
| `/read_excel <f>` | Excel |
| `/read_csv <f>` | CSV |
| `/ocr <f>` | OCR |
| `/ocr_config setup` | OCR 配置 |

### 30.4 网络 & Agent

| 命令 | 功能 |
|------|------|
| `/web <query>` | 搜索 |
| `/shell` | Shell 模式 |
| `!<cmd>` | 执行命令 |
| `!<cmd> \| <prompt>` | 管道 |
| `@local <q>` | 本地操作 |
| `@remote <s> <q>` | 远程 SSH |
| `@spider <url>` | 爬虫 |
| `@db <a> <q>` | 数据库 |
| `@RAG <q>` | 知识库 |
| `@stock <q>` | 股票 |
| `/agent_create <n> <d>` | 创建 Agent |
| `/agent_list` | 列 Agent |
| `/agent_run <n>` | 运行 Agent |
| `/agent_model <n> [cfg]` | 绑模型 |
| `/swarm <mode> <names> <q>` | 蜂群 |

### 30.5 邮件 & 网盘 & MCP

| 命令 | 功能 |
|------|------|
| `/mail setup` | 邮件配置 |
| `/mail inbox` | 收件箱 |
| `/mail send` | 发送 |
| `/m365_config setup` | M365 配置 |
| `/disk_setup` | 云盘登录 |
| `/disk_ls` | 云盘列表 |
| `/mcp_list` | MCP 列表 |
| `/mcp_add <n> <cmd>` | 加 MCP |
| `/mcp_refresh` | 刷新 |

### 30.6 高级

| 命令 | 功能 |
|------|------|
| `/mode direct\|cot\|tot\|react\|plan` | 思维模式 |
| `/master on\|off` | 主控 |
| `/hermes ...` | 后台任务 |
| `/build <req>` | 动态构建 |
| `/context ...` | 上下文 |
| `/cron_add` | 定时任务 |
| `/gatekeeper ...` | 守护 |
| `/autostart` | 启动所有 |
| `/status` | 系统状态 |
| `/status errors` | 错误报告 |
| `/agent_server start` | Web 控制台 |
| `/tutorial` | 教程 |
| `/help <topic>` | 帮助 |
| `/queue` | 对话队列 |
| `/exit` | 退出 |

### 30.7 AI 自动调用格式

```
【调用：tool_name({"参数": "值"})】       # 结构化调用
【命令：/plugin_name args】              # 插件调用
【并行调用：[{"name": "t1", "args": {...}}, ...]】  # 并行执行
【最终答案】...                          # MasterAgent 最终答案标记
```

### 30.8 文件路径速查

| 路径 | 内容 |
|------|------|
| `~/.fr_cli/config.json` | 主配置 |
| `~/.fr_cli/usage.json` | 用量统计 |
| `~/.fr_cli/sessions/` | 会话存档 |
| `~/.fr_cli/plugins/` | 插件 |
| `~/.fr_cli/agents/<n>/` | Agent 分身 |
| `~/.fr_cli/dynamic_tools/` | /build 工具 |
| `~/.fr_cli/master/` | MasterAgent 状态 |
| `~/.fr_cli/hermes/` | Hermes 后台 |
| `~/.fr_cli/rag/` | RAG 知识库 |
| `~/.fr_cli/exports/` | HTML 导出 |

---

## 附录 A:支持的所有命令(注册表)

通过 `@register` 装饰器注册,**所有内置工具** 在启动时自动加载,总数 144+:

| 类别 | 数量 | 示例 |
|------|------|------|
| 文件 | 9 | write_file / read_file / list_files / append_file / delete_file / rename_file / replace_text / grep_text / change_dir |
| 网络 | 4 | search_web / fetch_web / ping_host / port_scan / ip_scan / network_devices |
| SSH | 2 | ssh_command / scp_transfer |
| 图像 | 3 | generate_image / analyze_image / ocr_recognize |
| 邮件 | 4 | mail_inbox / mail_read / mail_send / m365_* |
| Cron | 3 | cron_add / cron_list / cron_del |
| 云盘 | 3 | disk_ls / disk_up / disk_down |
| 会话 | 4 | save_session / list_sessions / export_session / set_session_name |
| 模型 | 4 | set_model / set_key / set_limit / set_lang |
| Agent | 5 | agent_create / agent_run / agent_call / agent_list / swarm_run |
| MCP | 2 | mcp_call / mcp_list |
| 业务 | 多 | stock / excel / csv / chart / defi / 等等 |

调用方式:
```bash
# 用户命令行
>>> /<tool_name> <args>

# AI 自动
【调用：<tool_name>({"参数": "值"})】
```

新增内置工具:在 `command/registry.py` 用 `@register(...)` 注册一个 handler,即可。

---

## 附录 B:快捷键

| 按键 | 功能 |
|------|------|
| `Enter` | 发送消息 |
| `Shift+Enter` / `Ctrl+J` | 换行 |
| `Ctrl+C` | 清空当前输入 |
| `Ctrl+L` | 清屏 |
| `Ctrl+D` | 退出 |
| `e` | 编辑上一条消息 |
| `r` | 重试上一条 |
| `u` | 撤销 |

---

**版本**:fr-cli `__version__`
**许可**:个人项目
**反馈**:GitHub Issues https://github.com/leungyukit/fr-cli/issues