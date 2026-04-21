# 凡人打字机 (fr-cli) 使用与配置说明书

> 版本: v2.1.0  
> 作者: 修仙者联盟  
> 包名: `fr-cli` (PyPI)  
> 命令入口: `fr-cli`

---

## 目录

1. [简介](#简介)
2. [安装](#安装)
3. [快速开始](#快速开始)
4. [配置说明](#配置说明)
5. [命令参考](#命令参考)
6. [MasterAgent 主控](#masteragent-主控)
7. [思维模式](#思维模式)
8. [按日期自动存档会话](#按日期自动存档会话)
9. [AI 工具调用](#ai-工具调用)
10. [插件系统](#插件系统)
11. [安全机制](#安全机制)
12. [常见问题](#常见问题)

---

## 简介

「凡人打字机」是一个基于智谱 AI (ZhipuAI/GLM) 的终极全能终端工具。它将大语言模型与本地环境深度集成，让你可以在终端中通过自然语言与 AI 对话，并让 AI 自动调用各类工具完成实际任务。

**核心特性：**
- 🤖 **AI 智能对话** — 基于 GLM-4 系列模型，流式实时响应
- 🧠 **MasterAgent 主控** — 自我进化的 ReAct 主控 Agent，自动规划、调用工具、反思进化
- 🧩 **思维模式** — direct / CoT / ToT / ReAct 四种推理模式切换
- 📁 **安全文件沙盒** — 虚拟文件系统，防止目录穿越攻击
- 🔍 **联网搜索** — 百度搜索 + 网页内容提取（SSRF 防护）
- 🖼️ **视觉能力** — 图片生成 (CogView) + 图片分析 (GLM-4V)
- 📧 **邮件收发** — IMAP/SMTP 真实邮件客户端（防头注入）
- ⏰ **定时任务** — 后台线程定时执行命令（shlex 安全解析）
- ☁️ **云盘集成** — 阿里云盘上传/下载/列出
- 🔌 **插件系统** — AI 自动生成插件，动态扩展功能（子进程隔离，无代码注入）
- 🧠 **会话记忆** — 自动保留最近对话摘要 + 按日期自动存档
- 🛡️ **四阶安全确认** — 精细控制危险操作权限
- 👤 **Agent 分身系统** — 创建独立 Agent（角色/记忆/技能/工作流），AI 自动生成
- 🌐 **Agent HTTP API** — 将 Agent 发布为 REST API 供外部调用（默认 127.0.0.1 + Bearer Token）
- 🖥️ **本机应用启动** — 一键调用浏览器、微信、Word、WPS 等本地程序
- 🧑‍💻 **内置 Agent** — `@local` 本地系统操作、`@remote` 远程 SSH、`@spider` 智能爬虫、`@db` 数据库助手、`@RAG` 知识库问答
- 📊 **数据卷轴** — Excel / CSV 读取与智能分析
- 🗄️ **数据库助手** — MySQL / PostgreSQL / SQL Server / Oracle 智能 SQL 生成
- 📚 **本地 RAG** — ChromaDB 向量库 + 自动文件监控与向量化

---

## 安装

### 方式一：pip 安装（推荐）

```bash
pip install fr-cli
fr-cli
```

### 方式二：源码安装

```bash
git clone https://github.com/yourname/fr-cli.git
cd fr-cli
pip install -e ".[all]"
```

### 依赖说明

从 v2.1.0 起，所有功能依赖默认随主包一起安装，无需单独安装可选依赖：

```bash
pip install fr-cli
```

默认包含的依赖：
- `zhipuai` — 智谱 AI SDK
- `requests` — HTTP 请求
- `pandas` + `openpyxl` — Excel/CSV 数据处理
- `pymysql` + `psycopg2-binary` + `pyodbc` + `oracledb` — 数据库驱动
- `chromadb` + `sentence-transformers` — RAG 向量库
- `paramiko` — SSH 远程操作
- `selenium` — 浏览器自动化
- `watchdog` — 文件监控
- `bypy` + `aligo` + `msal` — 云盘支持

### 首次运行

运行 `fr-cli` 后，如果没有配置 API Key，会提示输入：

```
⚠️ API Key Required
👉 Enter Zhipu API Key: sk-xxxxxxxxxxxxxxxx
```

API Key 可在 [智谱开放平台](https://open.bigmodel.cn/) 获取。

---

## 快速开始

```bash
$ fr-cli
 凡 人 打 字 机
──────────────────────────────────
 【 修 仙 者 的 编 码 引 擎 】

🔮 模型: glm-4-flash | 🛡️ 上限: 20000 | 📂 洞府: /Users/... | ⏳ 轮回: 全新轮回

>>> 你好！
🧑 凡人: 你好！
🧙 仙人: 你好！我是你的修仙助手，有什么可以帮你的吗？

>>> /help
📜 修仙指南:
  【配置】 /model /key /limit /alias /export /update /mode
  【洞府】 /ls /cat /cd /write /append /delete
  【轮回】 /save /load /del /undo /session_list /session_load /session_del
  【法宝】 /skills (自动进化)
  【神通】 /mail_* /cron_* /web /fetch /disk_* /see
  【主控】 /master on | off | status
  【分身 API】 /agent_server start [port] | stop | status
  【驭器】 /open <路径/URL> | /launch <应用> [目标] | /apps
  【破壁】 !命令 ...

>>> 帮我写一段 Python 代码，计算斐波那契数列
🧑 凡人: 帮我写一段 Python 代码，计算斐波那契数列
🧙 仙人: 以下是 Python 代码：

【调用：write_file({"path": "fib.py", "content": "def fib(n):\n    ..."})】

文件已写入 fib.py！
```

---

## 配置说明

### 配置文件

配置文件位于：`~/.zhipu_cli_config.json`

### 默认配置结构

```json
{
    "key": "sk-xxxxxxxxxxxxxxxx",
    "model": "glm-4-flash",
    "limit": 20000,
    "allowed_dirs": [],
    "lang": "zh",
    "aliases": {},
    "auto_confirm_forever": false,
    "session_name": "",
    "mail": {
        "imap_server": "imap.qq.com",
        "smtp_server": "smtp.qq.com",
        "email": "your@qq.com",
        "password": "授权码"
    },
    "disk": {
        "type": "oss",
        "ak": "AccessKey",
        "sk": "SecretKey",
        "endpoint": "oss-cn-hangzhou.aliyuncs.com",
        "bucket": "my-bucket",
        "prefix": "fr-cli/"
    }
}
```

### 配置项详解

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `key` | str | `""` | 智谱 AI API Key |
| `model` | str | `glm-4-flash` | AI 模型名称 |
| `limit` | int | `20000` | 单次请求 Token 上限（最小 1000） |
| `allowed_dirs` | list | `[]` | 允许的目录列表（VFS 安全沙盒） |
| `lang` | str | `zh` | 界面语言：`zh`（中文）或 `en`（英文） |
| `aliases` | dict | `{}` | 命令别名映射 |
| `auto_confirm_forever` | bool | `false` | 永久自动确认危险操作 |
| `session_name` | str | `""` | 当前会话名称 |
| `thinking_mode` | str | `"direct"` | 思维模式：`direct` / `cot` / `tot` / `react` |
| `mail` | dict | `{}` | 邮件账户配置（IMAP/SMTP） |
| `disk` | dict | `{}` | 云盘配置（当前支持阿里云盘） |

### 邮件配置

支持邮箱类型及服务器：

| 邮箱 | IMAP 服务器 | SMTP 服务器 | 说明 |
|------|------------|-------------|------|
| QQ/QQ 企业 | `imap.qq.com` | `smtp.qq.com` | 使用「授权码」而非密码 |
| 163 | `imap.163.com` | `smtp.163.com` | 需开启 IMAP/SMTP |
| Gmail | `imap.gmail.com` | `smtp.gmail.com` | 需开启「不够安全的应用访问」或使用应用密码 |
| Outlook | `outlook.office365.com` | `smtp.office365.com` | 标准密码 |
| 阿里云 | `imap.aliyun.com` | `smtp.aliyun.com` | 标准密码 |

**重要**：QQ/163 等邮箱需要使用「授权码」而非登录密码。授权码在邮箱设置中生成。

### 命令行修改配置

```
/key sk-xxxxxxxx        # 修改 API Key
/model glm-4-plus       # 切换模型
/limit 4096             # 修改 Token 上限
/lang zh                # 切换语言
/alias ll 你好          # 设置别名
/dir /path/to/project   # 添加允许访问的目录
```

---

## 命令参考

### 一、配置命令

| 命令 | 参数 | 说明 |
|------|------|------|
| `/model <name>` | 模型名 | 切换 AI 模型（如 `glm-4-flash`、`glm-4-plus`、`glm-4v-plus`） |
| `/key <key>` | API Key | 修改智谱 AI API Key |
| `/limit <n>` | 数字 | 设置 Token 上限（最小 1000） |
| `/alias <k> [v]` | 键 [值] | 查看/设置命令别名 |
| `/lang <zh/en>` | 语言代码 | 切换界面语言 |
| `/dir <path>` | 目录路径 | 添加允许访问的目录到沙盒 |
| `/dirs` | - | 列出所有已挂载的工作目录 |
| `/rmdir <索引/路径>` | 索引或路径 | 删除指定的工作目录 |
| `/export` | - | 导出当前会话为 Markdown 文件 |
| `/update check` | - | 检查更新 |
| `/update run` | - | 执行更新并重启 |

**使用步骤示例**：

```
>>> /model glm-4-plus
✅ 法器更替: glm-4-plus

>>> /key sk-xxxxxxxxxxxxxxxx
✅ 重铸。

>>> /limit 4096
✅ 上限: 4096

>>> /lang en
语言已切换为: English

>>> /alias ll 你好
✅ 烙印: ll = 你好

>>> /alias ll        # 查看别名值
你好

>>> /dir /Users/me/project
✅ 洞府 [/Users/me/project] 已开辟

>>> /dirs
📂 已挂载的洞府:
  [0] /Users/me/project
  [1] /Users/me/docs

>>> /rmdir 1         # 按索引删除
✅ 洞府 [/Users/me/docs] 已关闭
```

**配置别名后使用**：
```
>>> ll               # 输入别名，自动替换为"你好"
🧑 凡人: 你好
🧙 仙人: 你好！有什么可以帮你的吗？
```

### 二、文件操作命令（洞府）

| 命令 | 参数 | 说明 |
|------|------|------|
| `/ls` | - | 列出当前目录文件 |
| `/cat <file>` | 文件名 | 查看文件内容（支持 UTF-8/GBK/Latin-1） |
| `/cd <dir>` | 目录名 | 切换工作目录 |
| `/write <file> <content>` | 文件名 内容 | 写入/覆盖文件 |
| `/append <file> <content>` | 文件名 内容 | 追加内容到文件 |
| `/delete <file>` | 文件名 | 删除文件 |

**使用步骤示例**：

```
>>> /ls
📂 当前目录文件:
  README.md
  data/
  config.json

>>> /cd data
✅ 穿梭至: /Users/me/project/data

>>> /ls
📂 当前目录文件:
  input.csv
  output.xlsx

>>> /cat input.csv
id,name,age
1,张三,25
2,李四,30

>>> /write hello.txt 你好，凡人打字机！
✅ 卷轴已刻录: hello.txt

>>> /append hello.txt \n这是追加的内容。
✅ 卷轴已刻录: hello.txt

>>> /cat hello.txt
你好，凡人打字机！
这是追加的内容。

>>> /delete hello.txt
⚠️ 检测到高危神通，请选择因果:
[Y]仅此  [A]本轮  [F]永世  [N]拒绝
Y
✅ 卷轴已销毁: hello.txt

>>> /cd ..             # 返回上级目录
✅ 穿梭至: /Users/me/project
```

**安全机制**：
- 所有文件操作限制在 `allowed_dirs` 目录内
- 禁止 `../` 目录穿越攻击（已解析的真实路径必须在 allowed_dirs 内）
- `/write` 会自动创建父目录
- 危险操作（写入、删除）触发四阶安全确认（Y/A/F/N）

### 三、会话命令（轮回）

| 命令 | 参数 | 说明 |
|------|------|------|
| `/save <name>` | 会话名 | 保存当前对话历史 |
| `/load` | - | 加载历史会话（交互式选择） |
| `/del` | - | 删除历史会话（交互式选择） |
| `/undo` | - | 撤销最近一轮对话（用户 + AI） |

**使用步骤示例**：

```
>>> /save 项目需求讨论
✅ 刻录: [项目需求讨论]

>>> /load
  [0] 项目需求讨论
  [1] 代码审查
ID: 0                  # 输入要加载的会话索引
✅ 穿梭至: [项目需求讨论]

>>> /del
  [0] 项目需求讨论
  [1] 代码审查
ID: 1                  # 输入要删除的会话索引
✅ 斩断

>>> /undo              # 撤销最近一轮（删除 assistant 的回复）
✅ 时光倒流。
```

**上下文记忆**：
- 自动保留最近 5 轮对话摘要
- 按 `session_name` 持久化到 `~/.zhipu_cli_context.json`
- 加载会话时自动恢复上下文摘要
- 导出会话：`/export` 将当前会话导出为 Markdown 文件到当前工作目录

#### 自动存档会话（新增）

每次与 AI 对话后，系统会自动将完整对话按日期存档到 `~/.fr_cli_sessions/YYYY-MM-DD_NN.json`。

| 命令 | 参数 | 说明 |
|------|------|------|
| `/session_list` | - | 列出所有按日期存档的会话 |
| `/session_load <idx>` | 索引 | 加载指定索引的存档会话 |
| `/session_del <idx>` | 索引 | 删除指定索引的存档会话 |

**使用示例**：
```
>>> /session_list
📜 存档列表:
  [0] 2026-04-20_01 (5 轮对话)
  [1] 2026-04-19_03 (12 轮对话)
  [2] 2026-04-19_02 (8 轮对话)

>>> /session_load 0
✅ 已加载存档: 2026-04-20_01

>>> /session_del 2
✅ 已删除存档: 2026-04-19_02
```

**说明**：
- 首次输入时自动创建 `~/.fr_cli_sessions/YYYY-MM-DD_NN.json`
- 每次 AI 响应后增量保存
- 文件名按日期自动编号，不重复
- 传统手动 `/save` `/load` 仍然可用

### 四、邮件命令（邮差）

> 首次使用需配置邮件账户。可直接编辑 `~/.zhipu_cli_config.json`，或在对话中让 AI 帮你配置。

| 命令 | 参数 | 说明 |
|------|------|------|
| `/mail_setup` | - | 启动邮件配置向导 |
| `/mail_inbox` | - | 列出收件箱最近 10 封邮件 |
| `/mail_read <id>` | 邮件 ID | 读取指定邮件完整内容 |
| `/mail_send <to> <sub> <body>` | 收件人 主题 正文 | 发送邮件 |

**配置步骤**：

1. 获取邮箱授权码（以 QQ 邮箱为例）：
   - 登录 QQ 邮箱 → 设置 → 账户 → 开启 IMAP/SMTP 服务
   - 生成「授权码」（不是登录密码）

2. 运行配置向导或手动编辑配置：
```
>>> /mail_setup
👉 邮箱地址: your@qq.com
👉 授权码/密码: xxxxxxxxxxxxxx
👉 IMAP 服务器 [imap.qq.com]: 
👉 SMTP 服务器 [smtp.qq.com]: 
✅ 邮件配置已保存。
```

**使用示例**：
```
>>> /mail_inbox
  1 项目进度汇报 (boss@company.com)
  2 会议邀请 (hr@company.com)

>>> /mail_read 1
主题: 项目进度汇报
来自: boss@company.com | 2024-01-15 09:30

正文内容...

>>> /mail_send team@company.com 周报 本周完成了xxx功能，详见附件。
✅ 已发送
```

**支持的邮箱**：QQ/163/Gmail/Outlook/阿里云，具体服务器地址见「配置说明」章节。

### 五、定时任务命令（结界）

| 命令 | 参数 | 说明 |
|------|------|------|
| `/cron_add <秒> <命令>` | 间隔秒数 Shell命令 | 添加循环定时任务 |
| `/cron_list` | - | 列出所有运行中的定时任务 |
| `/cron_del <id>` | 任务 ID | 删除指定定时任务 |

**使用步骤示例**：

```
>>> /cron_add 300 ls -la /Users/me/project
✅ 布阵 (ID:1, 300秒)

>>> /cron_list
  [1] ls -la /Users/me/project (每300秒) 🏃 运行

>>> /cron_del 1
✅ 破阵: 1
```

**使用场景**：
- 定时备份：`/cron_add 3600 cp -r /project /backup`
- 定时监控：`/cron_add 60 df -h`
- 定时提醒：`/cron_add 1800 echo "该休息了"`

**注意**：
- 基于 `threading.Timer`，程序退出后任务消失
- 如需持久化，使用 Gatekeeper 守护进程：`/gatekeeper start`
- Shell 命令执行 30 秒超时，输出截断为 100 字符
- 危险命令触发安全确认

### 六、网络命令（游侠）

| 命令 | 参数 | 说明 |
|------|------|------|
| `/web <query>` | 搜索词 | 百度搜索 |
| `/fetch <url>` | 网址 | 抓取网页并提取纯文本 |

**使用步骤示例**：

```
>>> /web Python asyncio 教程
📜 搜魂:
  - Python asyncio 官方文档
    https://docs.python.org/3/library/asyncio.html
    asyncio 是用于编写并发代码的库...

>>> /fetch https://docs.python.org/3/library/asyncio.html
--- Fetch ---
asyncio — Asynchronous I/O...

 asyncio 是用于使用 async/await 语法编写并发代码的库。
 ...
--- EOF ---
```

**AI 自动调用**：
当用户提问涉及搜索时，AI 会自动输出调用标记：
```
【调用：search_web({"query": "Python asyncio 教程"})】
【调用：fetch_web({"url": "https://docs.python.org/..."})】
```
程序会自动执行并返回结果给 AI。

### 七、云盘命令（腾云）

> 当前支持阿里云盘（个人网盘）。

| 命令 | 参数 | 说明 |
|------|------|------|
| `/disk_setup` | - | 启动云盘配置向导（扫码登录） |
| `/disk_ls` | - | 列出当前云盘目录的文件和文件夹 |
| `/disk_cd <目录名>` | 目录名 | 切换云盘目录（支持 `..` 返回上级） |
| `/disk_up <本地路径> <云端名称>` | 本地路径 云端名称 | 上传文件到当前目录 |
| `/disk_down <云端名称> [本地路径]` | 云端名称 [本地路径] | 从当前目录下载文件 |

依赖: `pip install aligo`

**使用步骤示例**：

```
>>> /disk_setup
📱 请使用手机阿里云盘 App 扫描下方二维码...
✅ 登录成功！

>>> /disk_ls
📂 根目录:
  文档/
  图片/
  备份.zip

>>> /disk_cd 文档
✅ 已进入: 文档

>>> /disk_ls
📂 文档:
  项目资料/
  会议纪要.md

>>> /disk_up /Users/me/report.pdf report.pdf
✅ 飞升: report.pdf

>>> /disk_down 会议纪要.md /Users/me/download/
✅ 降落: 会议纪要.md
```

**说明**：
- 首次使用必须运行 `/disk_setup` 完成扫码登录
- 登录信息自动缓存，后续无需重复扫码
- 切换目录仅影响云盘操作上下文，不影响本地工作目录

### 八、图像命令

| 命令 | 参数 | 说明 |
|------|------|------|
| `/see <图片路径> [问题]` | 图片 问题 | 用 GLM-4V 分析图片内容 |

**使用步骤**：

1. 切换至视觉模型：
```
>>> /model glm-4v-plus
✅ 法器更替: glm-4v-plus
```

2. 分析本地图片：
```
>>> /see /Users/me/photo.jpg 这张图片里有什么
⚠️ 需法器 glm-4v-plus
👁️ 天眼…
📊 模型: glm-4v-plus | 耗时: 2.35秒

这张图片展示了一座山峰，山顶有积雪...
```

3. 分析网络图片：
```
>>> /see https://example.com/image.png 描述这张图片
```

**AI 自动调用**：
```
【调用：generate_image({"prompt": "一只在云上睡觉的猫"})】
```
图片生成使用 CogView-3-plus，保存到当前工作目录。

### 九、本机应用启动（驭器）

一键调用本机安装的应用程序，支持跨平台（macOS / Windows / Linux）。

| 命令 | 参数 | 说明 |
|------|------|------|
| `/open <路径/URL>` | 文件路径或网址 | 用系统默认程序打开 |
| `/launch <应用> [目标]` | 应用别名 [文件/URL] | 启动指定应用，可带目标参数 |
| `/apps` | - | 列出本机可用的应用别名 |

**常用应用别名**：
| 类别 | 可用别名 |
|------|----------|
| 浏览器 | `chrome`, `safari`, `firefox`, `edge`, `浏览器` |
| 办公 | `word`, `excel`, `powerpoint`, `ppt`, `wps` |
| 通讯 | `wechat`, `微信`, `qq`, `钉钉`, `飞书` |
| 编辑器 | `vscode`, `terminal`, `终端`, `记事本` |
| 媒体 | `music`, `播放器`, `spotify`, `vlc` |
| 系统 | `finder`, `计算器`, `appstore` |

**示例**：
```
/open https://example.com
/open /Users/me/report.pdf
/launch chrome https://github.com
/launch 微信
/launch word /Users/me/doc.docx
/launch vscode /Users/me/project
/apps
```

**跨平台说明**：
- **macOS**：使用 `open` / `open -a` 命令
- **Windows**：使用 `start` 命令
- **Linux**：使用 `xdg-open` 命令

### 十、Agent 分身系统

> Agent 分身存储在 `~/.fr_cli_agents/<name>/` 下

#### Agent CLI 命令

| 命令 | 参数 | 说明 |
|------|------|------|
| `/agent_create <名称> <描述>` | 名称 需求描述 | AI 自动生成完整 Agent（人设/技能/代码） |
| `/agent_forge <名称>` | 名称 | 从最近一次 AI 回复中提取代码，铸造为 Agent |
| `/agent_list` | - | 列出所有 Agent 分身 |
| `/agent_show <名称>` | Agent 名称 | 查看 Agent 详情（人设/记忆/技能/代码/工作流） |
| `/agent_edit <名称> <类型>` | 名称 persona/memory/skills/agent/workflow | 编辑 Agent 设定 |
| `/agent_run <名称> [参数]` | 名称 [传入参数] | 运行指定 Agent |
| `/agent_delete <名称>` | Agent 名称 | 删除 Agent |

#### 创建 Agent 的三种方法

**方法一：AI 自动生成（/agent_create）**

让 AI 根据你的需求描述，自动生成完整的 Agent（人设 + 技能 + 代码）：

```
>>> /agent_create 文件搜索助手 根据关键词搜索本地文件并返回匹配结果
✅ Agent [文件搜索助手] 铸造完成！
```

**方法二：从已有代码铸造（/agent_forge）**

当你在对话中让 AI 写了一段功能代码后，可以直接将其转为 Agent：

```
>>> 请帮我写一段代码，功能是根据关键词搜索本地文件
🧙 仙人: （输出包含 def run(context, **kwargs) 的 Python 代码）

>>> /agent_forge file_searcher
✅ Agent [file_searcher] 铸造完成！
  路径: ~/.fr_cli_agents/file_searcher/
  运行: /agent_run file_searcher keyword=TODO
```

**方法三：自动检测提示**

当 AI 回复中包含 `def run(context, **kwargs)` 和 `\`\`\`python` 代码块时，程序会自动检测到 Agent 分身结构并提示保存：

```
⚡ 检测到 Agent 分身结构，赐名 (回车放弃): file_searcher
✅ Agent [file_searcher] 铸造完成！
  路径: ~/.fr_cli_agents/file_searcher/
  运行: /agent_run file_searcher [参数]
```

> **注意**：包含 `def run(args='')` 的代码会被识别为**插件**（保存到 `~/.zhipu_cli_plugins/`），而包含 `def run(context, **kwargs)` 的代码会被识别为 **Agent 分身**（保存到 `~/.fr_cli_agents/`）。两者互不干扰。

**方法四：手动创建（直接操作文件）**

如果你已有本地代码文件，可直接在文件系统中创建 Agent：

```bash
# 创建 Agent 目录
mkdir -p ~/.fr_cli_agents/my_agent

# 写入 agent.py（必须包含 run(context, **kwargs) 入口）
cat > ~/.fr_cli_agents/my_agent/agent.py << 'EOF'
def run(context, **kwargs):
    """
    context 包含: persona, memory, skills, client, model, lang, executor, state
    kwargs  包含用户调用时传入的参数，如 user_input
    """
    user_input = kwargs.get("user_input", "")
    # ... 你的功能逻辑 ...
    return "执行结果"
EOF

# 可选：写入人设和技能
echo "# my_agent" > ~/.fr_cli_agents/my_agent/persona.md
echo "## 技能" > ~/.fr_cli_agents/my_agent/skills.md
```

然后执行 `/agent_run my_agent` 即可运行。

#### Agent 代码约定

Agent 分身的核心文件是 `agent.py`，其入口函数签名如下：

```python
def run(context, **kwargs):
    """
    context 字典包含以下键：
      - persona: str      — 人设文本（来自 persona.md）
      - memory: str       — 记忆文本（来自 memory.md）
      - skills: str       — 技能文本（来自 skills.md）
      - client: ZhipuAI   — AI 客户端实例，可直接调用大模型
      - model: str        — 当前模型名称
      - lang: str         — 语言代码（'zh' 或 'en'）
      - executor: CommandExecutor — 可调用 invoke_tool()/execute() 执行工具
      - state: AppState   — 可访问 vfs、cfg、plugins 等子系统
      - agent_name: str   — 当前 Agent 名称
    
    kwargs 包含用户调用时传入的参数，如:
      - user_input: str   — 用户输入文本
    
    返回值: str — 执行结果字符串
    """
    user_input = kwargs.get("user_input", "")
    # ... 功能逻辑 ...
    return "执行结果"
```

#### 内置 Agent 前缀

在对话中直接使用 `@` 前缀触发内置 Agent：

| 前缀 | 说明 | 示例 |
|------|------|------|
| `@local <需求>` | 本地系统操作助手 | `@local 查看当前目录下最大的10个文件` |
| `@remote [别名] <需求>` | 远程 SSH 操作助手 | `@remote myserver 查看磁盘空间` |
| `@spider <URL> [深度]` | 智能网页爬虫 | `@spider https://example.com 2` |
| `@db [别名] <需求>` | 数据库智能助手 | `@db mydb 查询最近7天注册用户` |
| `@RAG <问题>` | 本地知识库问答 | `@RAG 什么是向量数据库` |

**@local — 本地系统操作助手**

AI 根据你的操作系统生成最合适的系统命令，经你确认后执行：

```
>>> @local 查看当前目录下最大的10个文件
🧙 正在分析本地操作...

建议命令:
find . -type f -exec ls -lh {} + | sort -k5 -rh | head -10

是否执行? [Y/n]: Y
执行中...
-rw-r--r--  1 user  staff   50M  Jan 15 10:20 ./data/backup.zip
...
```

**@remote — 远程 SSH 操作助手**

通过 SSH 在远程主机执行命令，支持多机配置：

```
>>> @remote 192.168.1.1 查看磁盘空间
⚠️ 未配置远程主机。正在启动配置向导...
═══ 远程主机配置向导 ═══
别名 (如: myserver): myserver
IP 地址: 192.168.1.1
端口 [22]: 
用户名: root
认证方式 (password/key) [password]: 
密码: ********
✅ 主机 [myserver] (192.168.1.1) 已保存。

🧙 正在为 [myserver](Linux) 生成远程命令...

建议命令 (myserver):
df -h

是否执行? [Y/n]: Y

Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        50G   20G   28G  42% /
```

- 首次使用自动启动配置向导
- 配置文件：`~/.fr_cli_remotes.json`
- 配置命令：`/remote_setup`

**@spider — 智能网页爬虫**

模拟真人浏览行为，支持 requests → selenium 降级策略：

```
>>> @spider https://example.com 2
🕷️ 开始爬取: https://example.com | 深度: 2

爬取完成
  成功: 15 个页面
  失败: 0 个页面
  保存目录: /Users/me/project/web_20240115
```

依赖: `pip install requests selenium`
- 先尝试无头请求，触发反爬时自动降级到 selenium
- 支持深度爬取（1~3层），默认只爬当前页面
- 内容保存到工作区 `web_YYYYMMDD/` 目录

**@db — 数据库智能助手**

自动分析数据库 Schema，生成并执行 SQL：

```
>>> @db mydb 查询最近7天注册用户
📊 正在分析 MYSQL [mydb](users_db) 的 Schema...
🧙 正在生成 SQL...

生成 SQL:
SELECT COUNT(*) FROM users WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY);

是否执行? [Y/n]: Y

返回 1 行:
  {'COUNT(*)': 342}
```

支持：MySQL / PostgreSQL / SQL Server / Oracle
- 首次使用自动启动配置向导
- 配置文件：`~/.fr_cli_databases.json`
- 配置命令：`/db_setup`

**@RAG — 本地知识库问答**

向量检索 + 大模型生成，基于你的本地文档回答问题：

```
>>> @RAG 项目的部署流程是什么
📚 正在同步知识库...
✅ 所有文件已是最新状态
🔍 正在检索知识库并生成回答...

根据知识库中的 deploy.md 和 README.md，部署流程如下：
1. 安装依赖: pip install -r requirements.txt
2. 配置环境变量: cp .env.example .env
3. 运行: python main.py
```

- 向量库：ChromaDB（本地持久化 `~/.fr_cli_rag_db`）
- 支持格式：txt, md, py, js, json, html, csv, xlsx 等
- 后台自动监控知识库目录（每30秒扫描）
- 配置命令：`/rag_dir <目录路径>`

#### Agent 目录结构

每个 Agent 是一个独立目录，包含：

| 文件 | 说明 |
|------|------|
| `persona.md` | 角色设定 / 系统提示词 |
| `memory.md` | 长期记忆（可被工作流读写） |
| `skills.md` | 技能描述（供 AI 参考） |
| `agent.py` | 可选自定义执行逻辑（需实现 `run(context, **kwargs)`） |
| `workflow.md` | 可选工作流定义（多步骤编排） |

#### Agent HTTP 服务命令

| 命令 | 参数 | 说明 |
|------|------|------|
| `/agent_server start [port]` | 端口号（默认 17890） | 启动 Agent HTTP API 服务 |
| `/agent_server stop` | - | 停止 HTTP 服务 |
| `/agent_server status` | - | 查看服务运行状态 |

**示例**：
```
>>> /agent_server start 8080
Agent HTTP 服务已启动: http://0.0.0.0:8080

>>> /agent_server status
运行中: http://0.0.0.0:8080

>>> /agent_server stop
Agent HTTP 服务已停止
```

#### Agent HTTP API 参考

服务启动后，外部系统可通过以下 REST API 调用 Agent：

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| `GET` | `/health` | - | 健康检查 |
| `GET` | `/agents` | - | 列出所有 Agent |
| `GET` | `/agents/<name>` | - | 获取 Agent 详情（persona/memory/skills/has_workflow） |
| `POST` | `/agents/<name>/run` | `{"input": "...", "kwargs": {}}` | 执行 Agent |
| `POST` | `/agents/<name>/workflow` | `{"input": "...", "kwargs": {}}` | 执行 Agent 工作流 |

**curl 示例**：
```bash
# 列出所有 Agent
curl http://localhost:8080/agents

# 执行 Agent
curl -X POST http://localhost:8080/agents/my_agent/run \
  -H "Content-Type: application/json" \
  -d '{"input": "请分析这个需求"}'

# 执行工作流
curl -X POST http://localhost:8080/agents/researcher/workflow \
  -H "Content-Type: application/json" \
  -d '{"input": "Python 最新特性"}'
```

#### Agent 工作流格式

在 Agent 目录下创建 `workflow.md`，使用 Markdown 格式定义步骤：

```markdown
# 工作流：数据分析

## 步骤1：搜索信息
- **action**: search_web
- **params**:
  - query: "{{user_input}}"

## 步骤2：AI 整理
- **action**: ai_generate
- **params**:
  - prompt: "整理以下搜索结果：{{step1.result}}"

## 步骤3：保存文件
- **action**: invoke_tool
- **params**:
  - tool: write_file
  - path: report.md
  - content: "{{step2.result}}"
```

**支持的动作（action）**：
| action | 说明 |
|--------|------|
| `invoke_tool` / `tool` | 调用内置工具（如 write_file, search_web） |
| `execute_cmd` / `cmd` | 执行命令字符串 |
| `agent_call` / `agent` | 调用另一个 Agent |
| `ai_generate` / `ai` | 调用 AI 生成内容 |
| `save_memory` / `memory_append` | 追加内容到 Agent memory |

**支持的模板变量**：
| 变量 | 说明 |
|------|------|
| `{{user_input}}` | 用户传入的输入 |
| `{{step1.result}}` | 步骤 1 的执行结果 |
| `{{step1.error}}` | 步骤 1 的错误信息 |
| `{{agent.persona}}` | Agent 的角色设定 |
| `{{agent.memory}}` | Agent 的长期记忆 |
| `{{agent.skills}}` | Agent 的技能描述 |

### 十一、MasterAgent 主控

> MasterAgent 是一个自我进化的 ReAct 主控 Agent。启用后，它会接管普通对话，自主规划、调用工具、观察结果并持续进化。

| 命令 | 参数 | 说明 |
|------|------|------|
| `/master on` | - | 启用 MasterAgent 主控模式 |
| `/master off` | - | 关闭 MasterAgent，恢复传统流式对话 |
| `/master status` | - | 查看 MasterAgent 当前状态 |

**使用示例**：

```
>>> /master on
✅ MasterAgent 已觉醒

>>> 帮我搜索 Python 异步编程的最新资料并整理成文档
🧠 MasterAgent 思考: 用户需要搜索资料并整理成文档。我应该先搜索，然后写入文件。

【调用：search_web({"query": "Python 异步编程 最新"})】
...
【调用：write_file({"path": "async_guide.md", "content": "..."})】
✅ 任务完成，已保存到 async_guide.md
```

**工作原理**：
1. **ReAct 循环**：Thought → Action → Observation → Reflect，最多 8 步
2. **工具调用**：AI 输出 JSON 格式 `{"tool": "name", "params": {...}}`，系统解析并执行
3. **自动记忆**：记录每次工具调用的成功/失败模式到 `~/.fr_cli_master/memory.json`
4. **自我进化**：每 10 次交互自动反思，将成功经验沉淀为 prompt 追加到 `~/.fr_cli_master/evolution.json`
5. **状态隔离**：`/` 命令、`!` shell、`@` 前缀仍保持原有逻辑，不受 MasterAgent 影响

---

### 十二、思维模式

支持四种思维模式，影响 AI 的推理深度：

| 命令 | 说明 |
|------|------|
| `/mode direct` | 直接回答（默认，最快） |
| `/mode cot` | CoT（Chain-of-Thought）链式思考 |
| `/mode tot` | ToT（Tree-of-Thoughts）树状搜索 |
| `/mode react` | ReAct（Reasoning + Acting）推理行动 |

**使用示例**：
```
>>> /mode react
✅ 思维模式: react

>>> 帮我分析这个复杂的技术选型问题
🧠 [思考] 需要从多个维度评估...
🧠 [行动] 搜索相关资料...
...
```

**说明**：
- `direct`：常规流式对话，不注入思维 prompt
- `cot`：要求 AI 分步推理，展示思考链
- `tot`：要求 AI 生成多个候选方案并评估
- `react`：要求 AI 交替进行思考（Thought）和行动（Action）

---

### 十三、数据卷轴（Excel / CSV）

| 命令 | 参数 | 说明 |
|------|------|------|
| `/read_excel <文件>` | Excel 文件路径 | 读取 Excel 并输出数据摘要 |
| `/read_csv <文件>` | CSV 文件路径 | 读取 CSV 并输出数据摘要 |

**使用步骤示例**：

```
>>> /read_excel sales_data.xlsx
📊 数据摘要:
表格: sales_data.xlsx
行数: 1,250 | 列数: 5

列信息:
  日期        datetime64  非空: 1250/1250
  产品名称     object      非空: 1250/1250
  销量         int64       非空: 1250/1250  均值: 342.5  范围: 10~980
  单价         float64     非空: 1248/1250  均值: 128.6
  地区         object      非空: 1245/1250

前10行预览:
  ...

>>> /read_csv users.csv
📊 数据摘要:
表格: users.csv
行数: 500 | 列数: 3
...
```

**与 AI 联动分析**：
读取数据后，可将摘要提交给 AI 进行深度分析：
```
>>> 分析这份销售数据，找出销量最高的产品和增长趋势
🧙 仙人: 根据数据分析，销量最高的产品是...
```

**说明**：
- 支持 `.xlsx`, `.xls`, `.csv` 格式
- 自动输出列名、数据类型、非空统计、数值统计、前10行预览
- 数据摘要可提交给 AI 进行深度分析

### 十五、守护进程（Gatekeeper）

守护进程独立于 fr-cli 主程序运行，可在主程序退出后继续维持 Agent HTTP API 服务和定时任务。

| 命令 | 参数 | 说明 |
|------|------|------|
| `/gatekeeper start` | - | 启动守护进程 |
| `/gatekeeper stop` | - | 停止守护进程 |
| `/gatekeeper status` | - | 查看守护进程状态 |

**使用步骤示例**：

```
>>> /agent_server start 8080          # 先启动 Agent HTTP 服务
✅ Agent HTTP 服务已启动: http://0.0.0.0:8080

>>> /cron_add 300 echo "heartbeat"    # 添加定时任务
✅ 布阵 (ID:1, 300秒)

>>> /gatekeeper start                 # 启动守护进程
✅ 守护进程已启动

>>> /exit                             # 退出 fr-cli
道友，保重。👋

# （守护进程仍在后台运行，维持 Agent API 和定时任务）

$ fr-cli                              # 重新进入
>>> /gatekeeper status
运行中 | PID: 12345
```

**说明**：
- 启动时自动保存当前的 Agent HTTP 服务端口和定时任务配置
- 停止守护进程后，Agent API 和定时任务会随之停止
- 守护进程配置存储在 `~/.zhipu_cli_config.json` 中

### 十六、破壁命令（系统 Shell）

| 命令 | 参数 | 说明 |
|------|------|------|
| `!<shell_cmd>` | Shell 命令 | 执行本地系统命令 |
| `!<cmd> \| <prompt>` | 命令 + AI提示 | 将命令输出管道给 AI 分析 |

**示例**：
```
!ls -la /Users
!ps aux | 找出占用 CPU 最高的进程
!cat log.txt | 分析这段日志有什么问题
```

### 十七、其他命令

| 命令 | 说明 |
|------|------|
| `/skills` | 查看已安装插件列表 |
| `/apps` | 列出本机可用应用别名 |
| `/remote_setup` | 远程主机配置向导 |
| `/db_setup` | 数据库配置向导 |
| `/rag_dir <路径>` | 设置 RAG 知识库目录 |
| `/exit` 或 `/quit` | 退出程序 |
| `/help [topic]` | 查看帮助（可指定主题，见下方） |

---

## AI 工具调用

### 结构化调用（推荐）

AI 会自动识别需求并输出工具调用标记：

```
【调用：tool_name({"参数": "值"})】
```

### 内置工具列表

| 工具名 | 参数 | 功能 |
|--------|------|------|
| `write_file` | `path`, `content` | 写入文件 |
| `read_file` | `path` | 读取文件 |
| `list_files` | - | 列出文件 |
| `change_dir` | `path` | 切换目录 |
| `append_file` | `path`, `content` | 追加文件 |
| `delete_file` | `path` | 删除文件 |
| `search_web` | `query` | 百度搜索 |
| `fetch_web` | `url` | 抓取网页 |
| `generate_image` | `prompt` | 生成图片 |
| `analyze_image` | `path`, `text` | 分析图片 |
| `mail_inbox` | - | 查看收件箱 |
| `mail_read` | `id` | 读取邮件 |
| `mail_send` | `to`, `subject`, `body` | 发送邮件 |
| `cron_add` | `command`, `interval` | 添加定时任务 |
| `cron_list` | - | 列出定时任务 |
| `cron_del` | `id` | 删除定时任务 |
| `disk_ls` | - | 列出云盘文件 |
| `disk_up` | `local`, `remote` | 上传文件 |
| `disk_down` | `remote`, `local` | 下载文件 |
| `save_session` | `name` | 保存会话 |
| `list_sessions` | - | 列出会话 |
| `export_session` | - | 导出会话 |
| `set_model` | `name` | 设置模型 |
| `set_key` | `key` | 设置 API Key |
| `set_limit` | `limit` | 设置 Token 上限 |
| `set_lang` | `code` | 设置语言 |
| `open_file` | `path` | 打开文件/URL |
| `launch_app` | `name`, `target` | 启动本地应用 |
| `read_excel` | `path` | 读取 Excel 文件 |
| `read_csv` | `path` | 读取 CSV 文件 |
| `agent_create` | `name`, `description` | 自动生成 Agent |
| `agent_run` | `name` | 运行指定 Agent |

### 插件调用（命令方式）

自定义插件通过命令方式调用：

```
【命令：/插件名 参数】
```

### 旧格式兼容

兼容早期模型的 `file_operations` 换行分隔格式：

```
file_operations
/write file.md "内容"
```

---

## 插件系统

### 自动进化

当 AI 回复中包含完整的插件结构时（同时包含 `def run(args='')` 和 ````python` 代码块），程序会提示是否保存为插件：

```
⚡ 检测到法宝结构，赐名 (回车放弃): my_tool
✅ 法宝铸造: /my_tool
```

### 插件目录

插件保存在：`~/.zhipu_cli_plugins/`

### 插件调用

```
/my_tool 参数
```

### 插件约定

```python
def run(args=''):
    """args 为传入的参数字符串"""
    return "处理结果"
```

### 插件安全

- 在独立子进程中执行（15 秒超时）
- 受安全确认系统保护

---

## 安全机制

### 四阶安全确认

对危险操作（文件写入、命令执行、邮件发送、Shell 等），系统会提示：

```
⚠️ 检测到高危神通，请选择因果:
[Y]仅此  [A]本轮  [F]永世  [N]拒绝
```

| 选项 | 说明 |
|------|------|
| `Y` | 仅允许本次操作 |
| `A` | 本次会话内允许同类操作 |
| `F` | 永久允许同类操作（写入配置） |
| `N` | 拒绝本次操作 |

### 受保护的操作类型

| 操作键 | 说明 |
|--------|------|
| `sec_read` | 读取卷轴（文件） |
| `sec_write` | 写入法宝（文件写入/删除） |
| `sec_exec` | 执行法宝（插件/定时任务） |
| `sec_mount` | 开辟洞府（添加目录） |
| `sec_gen_img` | 祭炼画卷（生成图片） |
| `sec_send_mail` | 发送邮件 |
| `sec_fetch_web` | 抓取互联网 |
| `sec_upload_disk` | 上传至云端 |
| `sec_download_disk` | 下载自云端 |
| `sec_shell` | 执行系统命令 |

### 目录穿越防护

VFS 虚拟文件系统通过 `Path.resolve()` 检查目标路径是否仍在 `allowed_dirs` 列表内，防止 `../` 攻击。路径检查使用 `== base_path or startswith(base_path + os.sep)`，防止 `/foo` 错误匹配 `/foo-bar`。

### 安全加固（v2.2.0）

| 模块 | 加固措施 |
|------|----------|
| **插件执行** | `name.isidentifier()` 校验；参数使用 `json.dumps()` 序列化；`runpy.run_path()` 替代字符串拼接执行 |
| **定时任务** | `shlex.split(cmd) + shell=False` 替代 `shell=True`；最小间隔 ≥ 5 秒 |
| **SSH 远程** | 全面改用 `paramiko.SSHClient`，消除 `subprocess.run(ssh_cmd, shell=True)` 命令注入 |
| **网页抓取** | SSRF 防护：拦截 `file://`、`ftp://`、localhost、私有 IP 段（10/8、172.16/12、192.168/16、127/8、169.254/16） |
| **图片分析** | 网络图片 URL 经 VFS 接口校验后再下载，防止路径穿越 |
| **邮件发送** | 邮件头字段过滤换行符，防止头注入攻击 |
| **配置文件** | `tempfile.mkstemp() + os.chmod(0o600) + os.replace()` 原子写入，防竞态 |
| **Agent HTTP** | 默认绑定 `127.0.0.1`；启动时生成随机 Bearer Token；移除全局 `*` CORS |
| **AI 工具调用** | 结构化 `kwargs` 参数，避免字符串 split 导致的问题；`registry.dispatch()` 自动参数校验 |
| **架构解耦** | `CommandExecutor` 从快照同步改为动态构建依赖，消除状态不同步导致的安全边界漂移 |

---

## 常见问题

### Q1: 如何获取智谱 AI API Key？

访问 [智谱开放平台](https://open.bigmodel.cn/)，注册账号后在「API Keys」页面创建。

### Q2: 邮件发送失败？

- QQ/163 邮箱需使用「授权码」而非登录密码
- 授权码在邮箱设置 → 账户 → 开启 IMAP/SMTP 服务后生成
- 确认 IMAP/SMTP 服务器地址正确

### Q3: 搜索功能无法使用？

```bash
pip install requests
```

### Q4: 云盘功能无法使用？

```bash
pip install aligo   # 阿里云盘
```

首次使用需运行 `/disk_setup` 完成扫码登录。

### Q5: 如何查看某功能的详细帮助？

```
/help config      # 配置相关
/help fs          # 文件操作
/help session     # 会话管理
/help master      # MasterAgent 主控
/help thinking    # 思维模式
/help mail        # 邮件功能
/help cron        # 定时任务
/help web         # 网络搜索
/help disk        # 云盘
/help vision      # 图像功能
/help shell       # 系统命令
/help tools       # AI 工具调用
/help security    # 安全机制
/help agent       # Agent 分身系统
/help builtin     # 内置 Agent
/help dataframe   # 数据卷轴
/help gatekeeper  # 守护进程
```

### Q6: 程序文件和数据保存在哪里？

| 路径 | 说明 |
|------|------|
| `~/.zhipu_cli_config.json` | 主配置文件 |
| `~/.zhipu_cli_history/` | 会话历史记录 |
| `~/.zhipu_cli_plugins/` | 用户插件目录 |
| `~/.zhipu_cli_context.json` | 上下文记忆 |
| `~/.fr_cli_agents/` | Agent 分身目录 |
| `~/.fr_cli_remotes.json` | 远程主机配置 |
| `~/.fr_cli_databases.json` | 数据库连接配置 |
| `~/.fr_cli_rag_db/` | RAG 向量库（ChromaDB）|
| `~/.fr_cli_sessions/` | 按日期自动存档的会话 |
| `~/.fr_cli_master/` | MasterAgent 记忆与进化记录 |

---

*本文档由 凡人打字机 自动生成，如有更新请以最新版本为准。*
