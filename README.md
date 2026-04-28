# 凡人打字机 (fr-cli)

**支持 27+ 种 AI 模型（智谱/智谱Coding/DeepSeek/Kimi/Kimi K2/Kimi Code/StepFun/Step-3/MiniMax/M2.7/讯飞星火/豆包/MiMo/LongCat）的终极全能终端工具。**

## ✨ 功能特性

### 🤖 多模型支持
支持以下 AI 模型提供商：
- **智谱 AI**: GLM-4-Flash 等
- **智谱 Coding Plan**: GLM-4.7 等 (https://docs.bigmodel.cn/cn/coding-plan/quick-start)
- **DeepSeek**: DeepSeek-Chat 等
- **Kimi (Moonshot)**: moonshot-v1-8k 等
- **Kimi K2**: 代码优化版 kimi-k2-0905-preview
- **Kimi Code**: 代码平台 kimi-cache-test (Kimi 会员)
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
- **邮件收发**：支持 IMAP/SMTP（防头注入）
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

## 🚀 快速开始

```bash
# 安装
pip install fr-cli

# 启动
fr-cli

# 或从源码运行
cd fr-cli
pip install -e .
python3 main.py
```

首次运行会引导输入当前道统的 API Key。

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

/model <模型名>              切换AI模型
/model <道统>:<模型名>       同时切换道统和模型
/key <key>                   修改当前道统 API Key
/key <道统> <key>            为指定道统设置 Key
/providers                   查看所有道统配置
/providers add <p> <k> [m]   添加/更新道统配置
/providers use <p>           切换到指定道统

/mode direct|cot|tot|react   切换思维模式
/master on|off|status       MasterAgent 主控
/mcp_list                   列出 MCP 服务器及工具
/mcp_add <名> <命令> [参数]  添加 MCP 服务器
/mcp_del <名>               删除 MCP 服务器

/help              查看帮助
/exit              退出
```

### 🤖 AI 模型切换示例

```
# 使用 Kimi K2（代码优化版）
/model kimi-k2

# 使用 MiniMax M2.7（Token Plan）
/model minimax-m27

# 使用 Step-3（阶跃星辰）
/model step-3

# 使用 Kimi Code
/model kimi-code

# 配置新的 API Key
/providers add step-3 <your-api-key>
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

## 📦 支持的模型提供商（25+）

| 道统 | 默认模型 | API 地址 |
|------|---------|----------|
| zhipu | glm-4-flash | - |
| zhipu-coding | GLM-4.7 | open.bigmodel.cn/api/coding/paas/v4 |
| zhipu-anthropic | glm-4.6 | open.bigmodel.cn/api/anthropic |
| deepseek | deepseek-chat | api.deepseek.com |
| kimi | moonshot-v1-8k | api.moonshot.cn |
| kimi-k2 | kimi-k2-0905-preview | api.moonshot.cn |
| kimi-code | kimi-cache-test | api.kimi.com/coding/v1 |
| qwen | qwen-turbo | dashscope.aliyuncs.com |
| stepfun | step-1-8k | api.stepfun.com |
| step-1 | step-1-8k | api.stepfun.com |
| step-2 | step-2-16k | api.stepfun.com |
| step-3 | step-3-auto | api.stepfun.com |
| step-audio | step-audio-2 | api.stepfun.com |
| minimax | MiniMax-Text-01 | api.minimax.chat |
| minimax-m27 | MiniMax-M2.7 | api.minimax.chat |
| minimax-m27-fast | MiniMax-M2.7-HighSpeed | api.minimax.chat |
| minimax-token-plan | MiniMax-M2.7 | api.minimax.chat |
| spark | generalv3.5 | spark-api-open.xf-yun.com |
| doubao | doubao-1-5-pro-32k-250115 | ark.cn-beijing.volces.com |
| mimo | mimo-v2-flash | api.xiaomimimo.com |
| longcat | LongCat-Flash-Chat | api.longcat.chat/openai |
| longcat-anthropic | LongCat | api.longcat.chat/anthropic |

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
python3 main.py
```

## 📂 项目结构

```
fr_cli/
├── main.py              # 核心入口
├── agent/                # Agent 系统
│   ├── a2a.py           # Agent2Agent 协议
│   ├── master.py        # MasterAgent 主控
│   └── ...
├── core/                 # 核心模块
│   └── llm.py           # LLM 客户端（20+ 提供商）
├── weapon/              # 武器库
├── memory/              # 记忆系统
└── lang/                # 国际化
```

## 📚 文档

- [NEW_PROVIDERS_GUIDE.md](NEW_PROVIDERS_GUIDE.md) - 新增模型使用指南
- [A2A_AND_PROVIDERS_GUIDE.md](A2A_AND_PROVIDERS_GUIDE.md) - A2A 协议文档

## 📄 License

MIT