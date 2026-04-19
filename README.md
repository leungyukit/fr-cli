# 凡人打字机 (fr-cli)

基于智谱 AI (ZhipuAI/GLM) 的终极全能终端工具。

## ✨ 功能特性

- 🤖 **AI 对话**：基于 GLM-4 系列模型的智能对话
- 📁 **文件沙盒**：安全的虚拟文件系统，支持读写/目录操作
- 🔍 **联网搜索**：内置 Web 搜索与网页内容提取
- 🖼️ **视觉能力**：图片生成 (CogView) 与多模态识别 (GLM-4V)
- 📧 **邮件收发**：支持 IMAP/SMTP
- ⏰ **定时任务**：后台定时执行命令
- ☁️ **云盘集成**：百度/阿里/OneDrive 网盘
- 🔌 **插件系统**：AI 生成代码自动保存为插件
- 🧠 **会话记忆**：自动保留最近 5 轮对话摘要
- 🛡️ **安全确认**：四阶危险操作拦截
- 👤 **Agent 分身系统**：AI 自动生成 Agent（人设/记忆/技能/代码），支持工作流编排
- 🌐 **Agent HTTP API**：将 Agent 发布为 REST API 供外部调用
- 🖥️ **本机应用启动**：一键调用浏览器、微信、Word、WPS 等本地程序
- 🧑‍💻 **内置 Agent**：`@local` `@remote` `@spider` `@db` `@RAG`
- 📊 **数据卷轴**：Excel / CSV 读取与智能分析
- 🗄️ **数据库助手**：MySQL / PostgreSQL / SQL Server / Oracle 智能 SQL 生成
- 📚 **本地 RAG**：ChromaDB 向量库 + 自动文件监控与向量化
- 🌍 **中英文切换**：完整国际化支持

## 🚀 快速安装

```bash
pip install fr-cli
fr-cli
```

首次运行会引导输入智谱 API Key。

## 📝 使用示例

### 终端命令

```bash
fr-cli

# 用户直接输入的命令
/ls                # 列出文件
/cat hello.md      # 查看文件
/cd /tmp           # 切换目录
/save mysession    # 保存会话
/export            # 导出为 Markdown
/agent_server start 8080   # 启动 Agent HTTP API
/agent_create coder "编写Python代码的助手"  # 自动生成Agent
/open /Users/me/doc.pdf    # 用默认应用打开文件
/launch chrome github.com  # 用 Chrome 打开网址
/launch 微信               # 启动微信
/apps                      # 列出可用应用
@local 查看当前目录最大的5个文件  # 本地系统操作Agent
@spider https://example.com 2  # 智能爬虫（深度2）
@db mydb 查询最近7天注册用户    # 数据库智能助手
@RAG 什么是向量数据库           # 本地知识库问答
/read_excel report.xlsx    # 读取 Excel
/read_csv data.csv         # 读取 CSV
/help              # 查看帮助
/exit              # 退出
```

### AI 自动工具调用

向 AI 描述需求，它会自动调用内置工具：

```
>>> 搜索一下 Python 最新版本
🧙 仙人 【调用：search_web({"query": "Python 最新版本"})】
...

>>> 把刚才的内容保存到文件
🧙 仙人 【调用：write_file({"path": "python_news.md", "content": "..."})】
✅ 卷轴已刻录
```

### Agent HTTP API 调用

启动服务后，外部系统可直接调用 Agent：

```bash
# 在 fr-cli 中启动服务
>>> /agent_server start 8080

# 外部系统调用
curl http://localhost:8080/agents
curl -X POST http://localhost:8080/agents/my_agent/run \
  -H "Content-Type: application/json" \
  -d '{"input": "请分析这个需求"}'
```

### 插件调用

自定义插件保持命令方式：

```
>>> 运行我的天气插件
🧙 仙人 【命令：/weather 北京】
```

## 📦 安装

```bash
# 一键安装（v2.1.0 起所有功能依赖默认包含）
pip install fr-cli
```

默认包含：智谱 AI SDK、HTTP 请求、Excel/CSV 处理、MySQL/PostgreSQL/SQL Server/Oracle 驱动、ChromaDB 向量库、sentence-transformers、SSH、Selenium、文件监控、云盘支持。

## 🔧 开发

```bash
git clone https://github.com/yourname/fr-cli.git
cd fr-cli
pip install -e .
python -m pytest tests/ -v
```

## 📄 License

MIT
