# 凡人打字机 (fr-cli)

支持多模型（智谱/DeepSeek/Kimi/Qwen/StepFun/MiniMax/讯飞星火）的终极全能终端工具。

**🇨🇳 中文简介**

支持：多模型 AI 对话（智谱/DeepSeek/Kimi/Qwen/StepFun/MiniMax/讯飞星火）、MasterAgent 自我进化主控、思维模式切换（direct/CoT/ToT/ReAct）、文件沙盒操作、联网搜索（SSRF 防护）、图片生成与识别、邮件收发、定时任务（shlex 安全解析）、云盘集成、会话记忆、按日期自动存档、插件进化（子进程隔离）、四阶安全拦截、Shell 管道直通 AI。

**🇺🇸 English Intro**

The ultimate all-knowing terminal tool supporting multiple LLM providers (Zhipu/DeepSeek/Kimi/Qwen/StepFun/MiniMax/Spark). Supports AI chat, MasterAgent self-evolving controller, thinking modes (direct/CoT/ToT/ReAct), virtual filesystem, web search (SSRF-protected), image generation & vision, email, cron jobs (shlex-safe), cloud drive, session memory, auto date-based archiving, self-evolving plugins (subprocess-isolated), and powerful Shell piping.

---

## 🚀 快速开始

```bash
pip install fr-cli
fr-cli
```

首次运行会引导输入当前道统的 API Key。

## 🎮 使用方式

### 用户直接命令

在 `>>>` 提示符下输入 `/` 命令：

```
/ls                列出当前目录文件
/cat <file>        查看文件内容
/write <file>      写入文件（多行输入，Ctrl+D 结束）
/cd <dir>          切换工作目录
/delete <file>     删除文件
/search <query>    联网搜索
/save <name>       保存会话
/load              加载历史会话
/export            导出会话为 Markdown
/session_list      列出按日期存档的会话
/session_load <idx>  加载存档会话
/mode direct|cot|tot|react  切换思维模式
/master on|off|status        MasterAgent 主控
/model <模型名>              切换当前道统模型
/model <道统>:<模型名>       同时切换道统和模型
/key <key>                   修改当前道统 API Key
/key <道统> <key>            为指定道统设置 Key
/providers                   查看所有道统配置
/providers add <p> <k> [m]   添加/更新道统配置
/providers use <p>           切换到指定道统
/mcp_list          列出 MCP 服务器及工具
/mcp_add <名> <命令> [参数]  添加 MCP 服务器
/mcp_del <名>      删除 MCP 服务器
/help              查看全部命令
/exit              退出
```

### AI 自动工具调用

当请求涉及文件、搜索、画图等操作时，AI 会自动调用内置工具：

```
【调用：write_file({"path": "hello.md", "content": "# Hello\n\nWorld"})】
【调用：search_web({"query": "Python 教程"})】
【调用：generate_image({"prompt": "一只猫在月球上"})】
```

### 插件（Skills）

自定义插件通过命令方式调用：

```
【命令：/my_plugin 参数】
```

---

## 📂 项目结构

```
fr_cli/
├── main.py              # 核心入口：REPL 循环、AI 交互编排（~600行）
├── repl/
│   └── commands.py      # 40个命令处理器（从 main.py 提取）
├── WEAPON.MD            # 法宝图谱（工具清单，人类可读，不再参与程序逻辑）
├── agent/               # Agent 分身系统 + MasterAgent 主控
│   ├── master.py        # 自我进化主控 Agent（ReAct 循环）
│   ├── master_prompt.py # MasterAgent 系统提示词模板
│   ├── manager.py       # Agent 生命周期管理
│   ├── executor.py      # Agent 执行器（run/delegate/multi-agent）
│   ├── workflow.py      # 工作流引擎（workflow.md 解析与执行）
│   └── server.py        # HTTP 服务（默认 127.0.0.1 + Bearer Token）
├── command/
│   ├── executor.py      # 命令执行引擎（动态构建依赖，消除 _deps 快照）
│   ├── registry.py      # 统一工具注册表
│   └── security.py      # 四阶安全确认管理器
├── weapon/              # 武器库/扩展子系统
│   ├── fs.py            # 虚拟文件系统 VFS
│   ├── web.py           # 网络搜索与网页抓取（SSRF 防护）
│   ├── vision.py        # 图片生成 (CogView) / 多模态 (GLM-4V)
│   ├── mail.py          # 邮件客户端（防头注入）
│   ├── disk.py          # 云盘适配器
│   ├── cron.py          # 定时任务（shlex + shell=False）
│   ├── launcher.py      # 本地应用启动器（跨平台）
│   ├── dataframe.py     # Excel / CSV 读取与分析
│   └── loader.py        # 从注册表动态生成工具描述
├── memory/
│   ├── history.py       # 会话历史保存/加载/导出
│   ├── context.py       # 上下文记忆（最近 5 轮摘要）
│   └── session.py       # 按日期自动存档会话引擎
├── core/
│   ├── core.py          # AppState 全局状态容器（DI 容器）
│   ├── stream.py        # 流式输出与代码块高亮
│   ├── recommender.py   # 功能推荐引擎
│   ├── sysmon.py        # 系统状态监控
│   └── thinking.py      # 思维模式引擎（CoT/ToT/ReAct）
├── addon/
│   └── plugin.py        # 插件加载与执行（runpy + json.dumps）
├── conf/
│   └── config.py        # 配置读写（mkstemp + 0o600 原子写入）
├── lang/
│   └── i18n.py          # 国际化 (zh/en)
├── security/
│   └── security.py      # 安全确认引擎
└── ui/
    └── ui.py            # 终端 UI、颜色、动画
```

---

## 📦 可选依赖

```bash
pip install fr-cli[all]          # 全功能（含网盘）
pip install fr-cli[baidu]        # 百度网盘
pip install fr-cli[aliyun]       # 阿里云盘
pip install fr-cli[onedrive]     # OneDrive
```

---

## 🔧 开发

```bash
git clone https://github.com/yourname/fr-cli.git
cd fr-cli
pip install -e ".[all]"
python -m pytest tests/ -v
```

---

## 📄 License

MIT
