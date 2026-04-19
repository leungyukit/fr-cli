# 凡人打字机 (fr-cli)

基于智谱 AI (ZhipuAI / GLM) 的终极全能终端工具。

**🇨🇳 中文简介**

支持：AI 智能对话、文件沙盒操作、联网搜索、图片生成与识别、邮件收发、定时任务、云盘集成、会话记忆、插件进化、四阶安全拦截、Shell 管道直通 AI。

**🇺🇸 English Intro**

The ultimate all-knowing terminal tool based on Zhipu AI. Supports AI chat, virtual filesystem, web search, image generation & vision, email, cron jobs, cloud drive, session memory, self-evolving plugins, and powerful Shell piping.

---

## 🚀 快速开始

```bash
pip install fr-cli
fr-cli
```

首次运行会引导输入智谱 API Key。

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
├── main.py              # 核心入口：REPL 循环、AI 交互
├── WEAPON.MD            # 法宝图谱（工具清单，外置可编辑）
├── agent/               # Agent 分身系统
│   ├── manager.py       # Agent 生命周期管理
│   ├── executor.py      # Agent 执行器（run/delegate/multi-agent）
│   ├── workflow.py      # 工作流引擎（workflow.md 解析与执行）
│   └── server.py        # HTTP 服务（将 Agent 发布为 REST API）
├── command/
│   ├── executor.py      # 命令执行引擎（结构化工具调用 + 命令解析）
│   ├── registry.py      # 统一工具注册表
│   └── security.py      # 四阶安全确认管理器
├── weapon/
│   ├── fs.py            # 虚拟文件系统 VFS
│   ├── web.py           # 网络搜索与网页抓取
│   ├── vision.py        # 图片生成 (CogView) / 多模态 (GLM-4V)
│   ├── mail.py          # 邮件客户端 (IMAP/SMTP)
│   ├── disk.py          # 云盘适配器
│   ├── cron.py          # 定时任务守护线程
│   ├── launcher.py      # 本地应用启动器（跨平台）
│   └── loader.py        # WEAPON.MD 解析与工具注入判定
├── memory/
│   ├── history.py       # 会话历史保存/加载/导出
│   └── context.py       # 上下文记忆（最近 5 轮摘要）
├── core/
│   ├── core.py          # AppState 全局状态容器（DI 容器）
│   ├── stream.py        # 流式输出与代码高亮
│   └── recommender.py   # 功能推荐引擎
├── addon/
│   └── plugin.py        # 插件加载与执行
├── conf/
│   └── config.py        # 配置读写
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
