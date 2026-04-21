"""
国际化文本引擎
"""

I18N = {
    "zh": {
        "sys_prompt": """你是一个智能AI助手，可以帮助用户解答问题、编写代码、分析文件等。\n直接回答用户的问题。只有当系统提示中提供了可用工具时，才按以下规则调用：\n\n1. 内置工具（文件/搜索/画图/邮件/定时任务/云盘/会话/配置）使用【调用：tool_name({\"参数\": \"值\"})】格式，参数为标准 JSON。常用示例：\n   - 写文件: 【调用：write_file({\"path\": \"file.md\", \"content\": \"# 标题\\n\\n正文\"})】\n   - 读文件: 【调用：read_file({\"path\": \"file.md\"})】\n   - 列出文件: 【调用：list_files({})】\n   - 搜索: 【调用：search_web({\"query\": \"搜索词\"})】\n   - 画图: 【调用：generate_image({\"prompt\": \"描述\"})】\n   - 保存会话: 【调用：save_session({'name': '会话名'})】

   特别说明：当用户询问本程序的功能说明、使用帮助，或要求发送/分享本程序的说明文档时，请优先使用 read_file 读取当前工作空间中的 MANUAL.md 文件获取完整说明，而不是进行网络搜索。

2. 自定义插件（skills）使用【命令：/插件名 参数】格式。\n\n如果系统提示中没有提供工具列表，直接回答即可，不要包含任何【调用：...】或【命令：...】标记。\n\n当用户明确要求创建插件/工具时，请生成包含 def run(args='') 的 Python 代码，并放在 ```python 代码块中。""",
        "prompt_user": "🧑 凡人", "prompt_ai": "🧙 仙人", "prompt_skill": "⚔️",

        "banner_title": [" 凡 人 打 字 机 ", "──────────────────────────────────", " 【 修 仙 者 的 编 码 引 擎 】 "],
        "bye_title": ["欢 迎 下 次", "继 续 修 仙"], "bye_msg": "道友，保重。👋",
        "status_model": "🔮 模型", "status_limit": "🛡️ 上限", "status_dir": "📂 洞府", "status_sess": "⏳ 轮回",
        "no_dir": "未开放洞府", "new_sess": "全新轮回", "cur_dir": "当前",
        "conn_ok": "✅ 天道连通。", "conn_fail": "❌ 天道拒绝:", "err_posix": "❌ 走火入魔:",
        "err_bound": "⚠️ 禁止穿越结界", "err_no_file": "⚠️ 卷轴不存在",
        "ok_dir_add": "✅ 洞府 [{}] 已开辟", "err_dir_no": "❌ 目录不存在", "ok_cd": "✅ 穿梭至: {}",
        "ok_dir_remove": "✅ 洞府 [{}] 已关闭", "err_dir_idx": "❌ 索引无效", "err_dir_not_mounted": "❌ 未挂载的洞府: {}",
        "ok_write": "✅ 卷轴已刻录: {}", "err_write_perm": "❌ 权限不足，无法刻录", "ok_delete": "✅ 卷轴已销毁: {}",
        "ok_model": "✅ 法器更替: {}", "err_model": "❌ 碎裂:", "ok_key": "✅ 重铸。",
        "ok_limit": "✅ 上限: {}", "err_limit": "❌ 最小1000", "ok_forged": "✅ 法宝铸造: /{}",
        "ok_sess_save": "✅ 刻录: [{}]", "ok_sess_load": "✅ 穿梭至: [{}]", "ok_sess_del": "✅ 斩断",
        "ok_undo": "✅ 时光倒流。", "err_undo": "❌ 无法倒流。", "ok_export": "✅ 导出: {}",
        "ok_alias_set": "✅ 烙印: {} = {}", "no_alias": "无烙印。",
        "sec_title": "⚠️ 检测到高危神通，请选择因果:", "sec_opt_y": "[Y]仅此", "sec_opt_a": "[A]本轮", "sec_opt_f": "[F]永世", "sec_opt_n": "[N]拒绝", "sec_denied": "🛑 终止。",
        "sec_read": "读取卷轴", "sec_write": "写入法宝", "sec_exec": "执行法宝", "sec_mount": "开辟洞府", "sec_gen_img": "祭炼画卷", "sec_send_mail": "发送邮件", "sec_fetch_web": "抓取互联网", "sec_upload_disk": "上传至云端", "sec_download_disk": "下载自云端", "sec_shell": "执行系统命令",
        "gen_ing": "🎨 祭炼…", "gen_ok": "✅ 画卷成: {}", "gen_fail": "❌ 破碎: ", "see_warn": "⚠️ 需法器 glm-4v-plus", "see_ing": "👁️ 天眼…",
        "help_title": "📜 修仙指南:", "help_cfg": "【配置】", "help_fs": "【洞府】", "help_sess": "【轮回】", "help_plugin": "【法宝】", "help_extra": "【神通】", "help_shell": "【破壁】",
        "help_usage": "💡 用法: /help [主题]  可用主题: config, fs, session, plugin, mail, cron, web, disk, vision, shell, tools, security, app, agent, builtin, dataframe, gatekeeper, all",
        "help_not_found": "❌ 未知主题: {}  可用: config, fs, session, plugin, mail, cron, web, disk, vision, shell, tools, security, app, agent, builtin, dataframe, gatekeeper, all",
        "empty": "空空如也…", "none": "无", "no_sess": "无记忆。", "no_plugins": "无技能。",
        "ctx_dir": "\n[系统：凡人在 {}。]",
        "menu_mail": "【邮差】", "menu_cron": "【结界】", "menu_web": "【游侠】", "menu_disk": "【腾云】",
        "mail_setup": "/mail_setup", "mail_inbox": "/mail_inbox", "mail_read": "/mail_read <ID>", "mail_send": "/mail_send <To> <Sub> <Body>",
        "mail_ok": "✅ 已发送", "mail_err": "❌ 邮件:", "mail_no_cfg": "❌ 未配邮", "mail_sub": "主题: {}", "mail_from": "来自: {}", "mail_date": "时间: {}",
        "cron_add": "/cron_add <秒> <命>", "cron_list": "/cron_list", "cron_del": "/cron_del <ID>",
        "cron_ok": "✅ 布阵 (ID:{}, {}秒)", "cron_killed": "✅ 破阵: {}", "cron_running": "🏃 运行",
        "web_search": "/web <词> 搜索", "web_fetch": "/fetch <URL> 抓取",
        "web_err": "❌ 迷路:", "web_no_res": "无果。", "web_title": "📜 搜魂:",
        "disk_setup": "/disk_setup", "disk_ls": "/disk_ls <盘>", "disk_up": "/disk_up <盘> <路>", "disk_down": "/disk_down <盘> <云> [本]",
        "disk_ok_up": "✅ 飞升: {}", "disk_ok_down": "✅ 降落: {}", "disk_err": "❌ 御剑: ", "disk_no_cfg": "❌ 未配盘", "disk_miss_dep": "❌ 缺库: {} (pip install {})",
        "shell_tip": "!命令 执行本地Shell(如 !ls)",
        "pipe_tip": "!命令 | 提示 管道喂给AI(如 !ps aux | 找出占用CPU最高的进程)",
        "pipe_prefix": "[系统管道数据]:\n",
        "artifact_detect": "⚡ 检测到法宝结构，赐名 (回车放弃): ",
        "recommend_title": "💡 推荐功能:",
        "rec_ls": "列出当前目录文件",
        "rec_cat": "查看文件内容",
        "rec_cd": "切换目录",
        "rec_see": "查看并分析图片",
        "rec_mail_inbox": "查看收件箱",
        "rec_mail_send": "发送邮件",
        "rec_web": "网络搜索",
        "rec_fetch": "获取网页内容",
        "rec_cron_add": "添加定时任务",
        "rec_cron_list": "列出定时任务",
        "rec_disk_ls": "列出云盘文件",
        "rec_disk_up": "上传到云盘",
        "rec_disk_down": "从云盘下载",
        "rec_save": "保存当前会话",
        "rec_load": "加载历史会话",
        "rec_model": "切换AI模型",
        "rec_key": "设置API密钥",
        "rec_lang": "切换语言",
        "rec_skills": "查看可用插件",
        "rec_export": "导出会话为Markdown",
        "rec_exec": "执行系统命令",
        "rec_pipe": "命令输出管道到AI",
        # ---- 详细帮助文本 ----
        "help_detail_config": """📜 【配置】

/model <name>     切换AI模型 (glm-4-flash, glm-4-plus, glm-4v-plus)
/key <key>        修改智谱AI API Key
/limit <n>        设置Token上限 (最小1000)
/lang <zh/en>     切换界面语言
/mode <direct|cot|tot|react>  切换AI思维模式（直接/思维链/思维树/ReAct）
/alias <k> [v]    查看/设置命令别名
/dir <path>       添加允许访问的目录到沙盒
/dirs             列出所有已挂载的工作目录
/rmdir <索引/路径> 删除指定的工作目录
/export           导出当前会话为Markdown文件
/update check     检查更新
/update run       执行更新并重启

配置文件: ~/.zhipu_cli_config.json
""",
        "help_detail_fs": """📜 【洞府 - 文件操作】

/ls               列出当前目录文件
/cat <file>       查看文件内容 (支持UTF-8/GBK/Latin-1)
/cd <dir>         切换工作目录
/dirs             列出所有已挂载的工作目录
/rmdir <idx/path> 删除指定的工作目录
/write <f> <c>    写入/覆盖文件
/append <f> <c>   追加内容到文件
/delete <f>       删除文件

使用示例:
  /cd data           切换至 data 目录
  /ls                列出文件
  /cat README.md     查看文件内容
  /write a.md 内容   写入文件
  /append a.md 追加  追加内容
  /delete a.md       删除文件（需安全确认）

安全机制:
  • 限制在 allowed_dirs 目录内, 禁止 ../ 穿越
  • /write 自动创建父目录
  • 危险操作触发四阶安全确认
""",
        "help_detail_session": """📜 【轮回 - 会话管理】

/save <name>      保存当前对话历史
/load             加载历史会话 (交互式选择)
/del              删除历史会话 (交互式选择)
/undo             撤销最近一轮对话
/export           导出当前会话为Markdown

自动按日期存档:
  /session_list     列出所有按日期自动保存的会话
  /session_load <N> 加载指定编号的会话并继续对话
  /session_del <N>  删除指定编号的自动会话

使用示例:
  /save 项目讨论     保存当前会话
  /load              交互式选择并加载
  /del               交互式选择并删除
  /undo              撤销最近一轮
  /export            导出为 Markdown
  /session_list      查看自动存档列表
  /session_load 1    加载今天的第一个会话继续聊

上下文记忆:
  • 自动保留最近5轮对话摘要
  • 按 session_name 持久化到 ~/.zhipu_cli_context.json
  • 加载会话时自动恢复上下文摘要
  • 每次启动自动创建日期编号会话文件（~/.fr_cli_sessions/）
""",
        "help_detail_plugin": """📜 【法宝 - 插件系统】

/skills           查看已安装插件列表
/<plugin> [args]  运行指定插件

自动进化:
  • AI回复中包含 def run(args='') 和 ```python 代码块时
  • 程序提示"检测到法宝结构", 输入名称即可保存

插件目录: ~/.zhipu_cli_plugins/
插件约定: def run(args='') 返回字符串结果
安全: 独立子进程执行, 15秒超时
""",
        "help_detail_mail": """📜 【邮差 - 邮件功能】

配置方式:
  1. 获取邮箱授权码（QQ邮箱: 设置→账户→开启IMAP/SMTP）
  2. /mail_setup 启动配置向导

/mail_setup       邮件配置向导
/mail_inbox       列出收件箱最近10封邮件
/mail_read <id>   读取指定邮件完整内容
/mail_send <to> <sub> <body>  发送邮件

使用示例:
  /mail_setup
  /mail_inbox
  /mail_read 1
  /mail_send friend@qq.com 主题 正文

支持邮箱: QQ/163/Gmail/Outlook/阿里云
注意: QQ/163 需使用「授权码」而非登录密码
""",
        "help_detail_cron": """📜 【结界 - 定时任务】

/cron_add <秒> <命令>   添加循环定时任务 (Shell命令)
/cron_list              列出运行中的定时任务
/cron_del <id>          删除指定任务

使用示例:
  /cron_add 300 ls -la /project   每5分钟列出项目目录
  /cron_add 60 df -h              每分钟检查磁盘
  /cron_list
  /cron_del 1

注意:
  • 基于 threading.Timer, 程序退出后任务消失
  • 如需持久化, 使用 /gatekeeper start 启动守护进程
  • Shell命令执行30秒超时, 输出截断100字符
  • 危险操作触发安全确认
""",
        "help_detail_web": """📜 【游侠 - 网络搜索】

/web <query>      百度搜索 (返回最多5条结果)
/fetch <url>      抓取网页并提取纯文本 (截断3000字符)

使用示例:
  /web Python asyncio 教程
  /fetch https://docs.python.org/3/library/asyncio.html

AI自动调用:
  【调用：search_web({"query": "搜索词"})】
  【调用：fetch_web({"url": "https://..."})】
""",
        "help_detail_disk": """📜 【腾云 - 云盘功能】

当前支持阿里云盘（个人网盘）。
首次使用需运行 /disk_setup 完成扫码登录。

/disk_setup       启动云盘配置向导（扫码登录）
/disk_ls          列出当前云盘目录的文件和文件夹
/disk_cd <目录名>  切换云盘目录（支持 .. 返回上级）
/disk_up <本地路径> <云端名称>   上传文件到当前目录
/disk_down <云端名称> [本地路径] 从当前目录下载文件

使用示例:
  /disk_setup                     首次扫码登录
  /disk_ls                        列出云盘文件
  /disk_cd 文档                   进入文档目录
  /disk_up /local/report.pdf report.pdf
  /disk_down report.pdf /local/

依赖: pip install aligo
""",
        "help_detail_vision": """📜 【天眼 - 图像功能】

/see <图片路径> [问题]    用GLM-4V分析图片内容

使用步骤:
  1. /model glm-4v-plus            切换至视觉模型
  2. /see photo.jpg 描述这张图片  分析图片

AI自动调用:
  【调用：generate_image({"prompt": "描述"})】
  图片生成使用 CogView-3-plus, 保存到当前目录
""",
        "help_detail_shell": """📜 【破壁 - 系统命令】

!<cmd>            执行本地Shell命令 (如 !ls -la)
!<cmd> | <prompt> 将命令输出管道给AI分析

使用示例:
  !ls -la /Users/me/project
  !ps aux | 找出占用CPU最高的进程
  !cat log.txt | 分析这段日志有什么问题

注意:
  • 命令执行15秒超时
  • 触发安全确认 sec_shell
  • 管道模式下AI基于命令输出生成分析
""",
        "help_detail_tools": """📜 【AI工具调用 - 结构化调用】

AI自动输出调用标记, 程序解析并执行:
  【调用：tool_name({"参数": "值"})】

常用工具:
  write_file    {"path", "content"}
  read_file     {"path"}
  list_files    {}
  search_web    {"query"}
  fetch_web     {"url"}
  generate_image {"prompt"}
  mail_inbox    {}
  mail_send     {"to", "subject", "body"}
  cron_add      {"command", "interval"}
  save_session  {"name"}
  set_model     {"name"}

插件调用 (命令方式):
  【命令：/插件名 参数】

旧格式兼容:
  file_operations\n/write file.md "内容"
""",
        "help_detail_app": """📜 【驭器 - 本机应用启动】

/open <路径/URL>           用系统默认程序打开文件或网址
/launch <应用> [目标]      启动指定应用，可带文件或URL参数
/apps                      列出本机可用的应用别名

使用示例:
  /open https://example.com
  /open /Users/me/doc.pdf
  /launch chrome https://github.com
  /launch 微信
  /launch word /Users/me/report.docx

常用应用别名:
  浏览器: chrome, safari, firefox, edge, 浏览器
  办公:   word, excel, powerpoint, ppt, wps
  通讯:   wechat, 微信, qq, 钉钉, 飞书
  工具:   vscode, terminal, 终端, 计算器, 记事本
  媒体:   music, 播放器, spotify, vlc
""",
        "help_detail_agent": """📜 【分身 - Agent 系统】

/master on|off|status          主控 Agent — 自我进化型全能助手（接管所有对话）

/agent_create <名称> <描述>   AI 自动生成完整 Agent（人设/技能/代码）
/agent_forge <名称>            从最近一次 AI 回复中提取代码，铸造为 Agent
/agent_list                    列出所有 Agent 分身
/agent_show <名称>             查看 Agent 详情（人设/记忆/技能/代码/工作流）
/agent_edit <名称> <类型>      编辑 Agent 设定（persona/memory/skills/agent/workflow）
/agent_run <名称> [参数]       运行指定 Agent
/agent_delete <名称>           删除 Agent

Agent 目录: ~/.fr_cli_agents/<名称>/
  • persona.md  — 角色设定
  • memory.md   — 长期记忆
  • skills.md   — 技能说明
  • agent.py    — 可选自定义执行逻辑（必须包含 run(context, **kwargs)）
  • workflow.md — 可选工作流定义

将已有代码转为 Agent 的方法：
  1. 在对话中让 AI 生成包含 def run(context, **kwargs) 的代码
  2. 程序会自动检测到 Agent 结构并提示保存
  3. 或手动执行 /agent_forge <名称> 从最近回复中提取代码
""",
        "help_detail_builtin": """📜 【神通 - 内置 Agent 前缀】

在对话中直接使用 @ 前缀触发内置 Agent：

@local <需求>              本地系统操作助手，AI 生成系统命令并执行
@remote [别名] <需求>      远程 SSH 操作助手，通过 SSH 在远程主机执行命令
@spider <URL> [深度]       智能网页爬虫，模拟真人行为获取网页内容
@db [别名] <需求>          数据库智能助手，自动分析 Schema 并生成 SQL
@RAG <问题>                本地知识库问答，向量检索 + 大模型生成

RAG 知识库管理:
  /rag_dir <路径>   — 设置知识库目录并首次同步
  /rag_sync [路径]  — 手动同步知识库（向量化新文件）
  /rag_watch start [目录] [--interval N] — 启动独立守护进程（持久化后台监控）
  /rag_watch stop   — 停止独立守护进程
  /rag_watch status — 查看守护进程状态
  /rag_watch log [--lines N] — 查看守护进程日志

说明:
  • ChromaDB 以嵌入式 PersistentClient 自动启动，无需单独服务
  • 内置模式（/rag_dir 后自动启动）为 daemon 线程，退出 fr-cli 后终止
  • 独立模式（/rag_watch start）为系统级进程，退出终端后仍继续运行
  • 守护进程通过 PID 文件管理，日志写入 ~/.fr_cli_rag_watcher.log

配置向导:
  /remote_setup  — 远程主机配置向导（配置文件: ~/.fr_cli_remotes.json）
  /db_setup      — 数据库配置向导（配置文件: ~/.fr_cli_databases.json）
""",
        "help_detail_dataframe": """📜 【数据卷轴 - Excel / CSV】

/read_excel <文件>   读取 Excel 文件并输出数据摘要
/read_csv <文件>     读取 CSV 文件并输出数据摘要

说明:
  • 支持 .xlsx, .xls, .csv 格式
  • 自动输出列名、数据类型、非空统计、数值统计、前10行预览
  • 数据摘要可提交给 AI 进行深度分析
""",
        "help_detail_gatekeeper": """📜 【结界守护 - Gatekeeper 守护进程】

/gatekeeper start    启动守护进程（持久化 Agent HTTP 服务、全局定时任务、Agent 定时任务）
/gatekeeper stop     停止守护进程
/gatekeeper status   查看守护进程状态

Agent 分身定时任务:
  /agent_cron_add <agent名称> <间隔秒> [输入]  为 Agent 添加定时执行计划
  /agent_cron_list                              列出所有 Agent 定时任务
  /agent_cron_del <ID>                          删除 Agent 定时任务

说明:
  • 守护进程独立于 fr-cli 主程序运行，退出终端后仍继续工作
  • 启动时自动保存当前的 Agent HTTP 服务端口和定时任务配置
  • 程序退出后守护进程仍可维持 Agent API、全局定时任务、Agent 定时任务
  • 守护进程每30秒热重载配置，主进程新增/删除任务后自动同步
  • 全局定时任务（/cron_add）修改后自动同步到守护进程配置
  • 守护进程配置存储在 ~/.fr_cli_gatekeeper.json 中
""",
        "help_detail_security": """📜 【安全机制】

四阶安全确认 (Y/A/F/N):
  [Y]仅此    仅允许本次操作
  [A]本轮    本次会话内允许同类操作
  [F]永世    永久允许同类操作 (写入配置)
  [N]拒绝    拒绝本次操作

受保护操作:
  sec_read(读文件) sec_write(写文件) sec_exec(执行)
  sec_mount(加目录) sec_gen_img(画图) sec_send_mail(发邮件)
  sec_fetch_web(抓取) sec_upload_disk(上传) sec_download_disk(下载)
  sec_shell(Shell命令)

目录穿越防护:
  VFS通过Path.resolve()检查路径, 禁止 ../ 逃逸出 allowed_dirs

非交互环境:
  • 设置 FR_CLI_NON_INTERACTIVE=1 时，安全确认默认拒绝（用于脚本/CI环境）
""",
    },
    "en": {
        "sys_prompt": "You are an AI assistant. Answer questions directly. Use tools only when they are explicitly provided in the system prompt. If no tools are provided, respond normally without any 【命令：...】 markers.\n\nSpecial note: When the user asks about this program's features, usage help, or requests to send/share the program's documentation, please prioritize using read_file to read the MANUAL.md file in the current workspace, rather than performing a web search.\n\nWhen the user explicitly asks to create a plugin/tool, generate Python code containing def run(args='') inside a ```python block.",
        "prompt_user": "🧑 You", "prompt_ai": "🤖 AI", "prompt_skill": "⚡",
        "banner_title": [" F A N R E N C L I T O O L ", "──────────────────────────────────", " [ Advanced Code Engine v1.0 ] "],
        "bye_title": ["S E E Y O U", "N E X T T I M E"], "bye_msg": "Happy chatting. 👋",
        "status_model": "🔮 Model", "status_limit": "🛡️ Limit", "status_dir": "📂 Dir", "status_sess": "⏳ Sess",
        "no_dir": "No dir", "new_sess": "New", "cur_dir": "Active",
        "conn_ok": "✅ Connected.", "conn_fail": "❌ Failed:", "err_posix": "❌ Error:",
        "err_bound": "⚠️ Denied", "err_no_file": "⚠️ Not found",
        "ok_dir_add": "✅ Dir [{}] added", "err_dir_no": "❌ Not exists", "ok_cd": "✅ Dir: {}",
        "ok_dir_remove": "✅ Dir [{}] removed", "err_dir_idx": "❌ Invalid index", "err_dir_not_mounted": "❌ Not mounted: {}",
        "ok_model": "✅ Model: {}", "err_model": "❌ Fail:", "ok_key": "✅ Updated.",
        "ok_limit": "✅ Limit: {}", "err_limit": "❌ Min 1000", "ok_forged": "✅ Skill: /{}",
        "ok_sess_save": "✅ Saved: [{}]", "ok_sess_load": "✅ Loaded: [{}]", "ok_sess_del": "✅ Deleted",
        "ok_undo": "✅ Undone.", "err_undo": "❌ None.", "ok_export": "✅ Export: {}",
        "ok_alias_set": "✅ Alias: {} = {}", "no_alias": "None.",
        "sec_title": "⚠️ Security Check:", "sec_opt_y": "[Y]Once", "sec_opt_a": "[A]Session", "sec_opt_f": "[F]Forever", "sec_opt_n": "[N]Deny", "sec_denied": "🛑 Abort.",
        "sec_read": "Read file", "sec_write": "Write plugin", "sec_exec": "Run plugin", "sec_mount": "Mount dir", "sec_gen_img": "GenImg", "sec_send_mail": "Mail", "sec_fetch_web": "Fetch", "sec_upload_disk": "Upload", "sec_download_disk": "Download", "sec_shell": "Shell Exec",
        "gen_ing": "🎨 Gen…", "gen_ok": "✅ Saved: {}", "gen_fail": "❌ Fail: ", "see_warn": "⚠️ Need glm-4v-plus", "see_ing": "👁️ See…",
        "help_title": "📜 Help:", "help_cfg": "[Config]", "help_fs": "[FS]", "help_sess": "[Sess]", "help_plugin": "[Plugins]", "help_extra": "[Adv]", "help_shell": "[Matrix]",
        "help_usage": "💡 Usage: /help [topic]  Topics: config, fs, session, plugin, mail, cron, web, disk, vision, shell, tools, security, app, agent, builtin, dataframe, gatekeeper, all",
        "help_not_found": "❌ Unknown topic: {}  Available: config, fs, session, plugin, mail, cron, web, disk, vision, shell, tools, security, app, agent, builtin, dataframe, gatekeeper, all",
        "empty": "(Empty)", "none": "None", "no_sess": "No sess.", "no_plugins": "No plug.",
        "ctx_dir": "\n[System: User in {}.]",
        "menu_mail": "[Mail]", "menu_cron": "[Cron]", "menu_web": "[Web]", "menu_disk": "[Disk]",
        "mail_setup": "/mail_setup", "mail_inbox": "/mail_inbox", "mail_read": "/mail_read <ID>", "mail_send": "/mail_send <To> <Sub> <Body>",
        "mail_ok": "✅ Sent", "mail_err": "❌ Err:", "mail_no_cfg": "❌ No Mail", "mail_sub": "Sub: {}", "mail_from": "From: {}", "mail_date": "Date: {}",
        "cron_add": "/cron_add <S> <C>", "cron_list": "/cron_list", "cron_del": "/cron_del <ID>",
        "cron_ok": "✅ Added (ID:{}, {}s)", "cron_killed": "✅ Killed: {}", "cron_running": "🏃 Run",
        "web_search": "/web <Q> Search", "web_fetch": "/fetch <URL>",
        "web_err": "❌ Err:", "web_no_res": "None.", "web_title": "📜 Search:",
        "disk_setup": "/disk_setup", "disk_ls": "/disk_ls <N>", "disk_up": "/disk_up <N> <L>", "disk_down": "/disk_down <N> <R> [L]",
        "disk_ok_up": "✅ Up: {}", "disk_ok_down": "✅ Down: {}", "disk_err": "❌ Err: ", "disk_no_cfg": "❌ No Disk", "disk_miss_dep": "❌ Miss: {} (pip install {})",
        "shell_tip": "!cmd Run shell (e.g. !ls)",
        "pipe_tip": "!cmd | msg Pipe to AI (e.g. !ps aux | find high CPU)",
        "pipe_prefix": "[Piped Data]:\n",
        "artifact_detect": "⚡ Artifact detected, name (Enter to skip): ",
        "recommend_title": "💡 Recommended Features:",
        "rec_ls": "List files in current directory",
        "rec_cat": "View file content",
        "rec_cd": "Change directory",
        "rec_see": "View and analyze image",
        "rec_mail_inbox": "View inbox",
        "rec_mail_send": "Send email",
        "rec_web": "Web search",
        "rec_fetch": "Fetch web content",
        "rec_cron_add": "Add scheduled task",
        "rec_cron_list": "List scheduled tasks",
        "rec_disk_ls": "List cloud files",
        "rec_disk_up": "Upload to cloud",
        "rec_disk_down": "Download from cloud",
        "rec_save": "Save current session",
        "rec_load": "Load historical session",
        "rec_model": "Switch AI model",
        "rec_key": "Set API key",
        "rec_lang": "Switch language",
        "rec_skills": "View available plugins",
        "rec_export": "Export session as Markdown",
        "rec_exec": "Execute system command",
        "rec_pipe": "Pipe command output to AI",
        "help_detail_config": """📜 [Config]

/model <name>     Switch AI model (glm-4-flash, glm-4-plus, glm-4v-plus)
/key <key>        Change ZhipuAI API Key
/limit <n>        Set token limit (min 1000)
/lang <zh/en>     Switch UI language
/mode <direct|cot|tot|react>  Switch AI thinking mode (direct/CoT/ToT/ReAct)
/alias <k> [v]    View/set command alias
/dir <path>       Add allowed directory to sandbox
/dirs             List all mounted directories
/rmdir <idx/path> Remove specified directory
/export           Export current session to Markdown
/update check     Check for updates
/update run       Apply update and restart

Config file: ~/.zhipu_cli_config.json
""",
        "help_detail_fs": """📜 [FS - File Operations]

/ls               List files in current directory
/cat <file>       View file content (UTF-8/GBK/Latin-1)
/cd <dir>         Change working directory
/dirs             List all mounted directories
/rmdir <idx/path> Remove specified directory
/write <f> <c>    Write/overwrite file
/append <f> <c>   Append content to file
/delete <f>       Delete file

Examples:
  /cd data           Change to data directory
  /ls                List files
  /cat README.md     View file content
  /write a.md text   Write file
  /append a.md more  Append content
  /delete a.md       Delete file (needs confirmation)

Security:
  • Restricted to allowed_dirs, ../ traversal blocked
  • /write auto-creates parent directories
  • Dangerous ops trigger 4-level security confirmation
""",
        "help_detail_session": """📜 [Session]

/save <name>      Save current conversation
/load             Load historical session (interactive)
/del              Delete historical session (interactive)
/undo             Undo last conversation turn
/export           Export session as Markdown

Auto-save by date:
  /session_list     List all auto-saved sessions
  /session_load <N> Load session by index and continue
  /session_del <N>  Delete auto-saved session by index

Examples:
  /save project      Save current session
  /load              Interactive load
  /del               Interactive delete
  /undo              Undo last turn
  /export            Export to Markdown
  /session_list      View auto-saved sessions
  /session_load 1    Load today's first session

Context Memory:
  • Auto-summarize last 5 turns
  • Persisted to ~/.zhipu_cli_context.json by session_name
  • Context restored when loading session
  • Auto-created date-indexed session file on each launch (~/.fr_cli_sessions/)
""",
        "help_detail_plugin": """📜 [Plugins]

/skills           List installed plugins
/<plugin> [args]  Run specified plugin

Auto-evolution:
  • When AI reply contains def run(args='') and ```python block
  • Prompts to save as plugin, enter name to forge

Plugin dir: ~/.zhipu_cli_plugins/
Convention: def run(args='') returning a string
Safety: Runs in isolated subprocess with 15s timeout
""",
        "help_detail_mail": """📜 [Mail]

Setup:
  1. Get auth code (QQ Mail: Settings→Account→Enable IMAP/SMTP)
  2. /mail_setup to run config wizard

/mail_setup       Mail config wizard
/mail_inbox       List last 10 emails
/mail_read <id>   Read full content of specified email
/mail_send <to> <sub> <body>  Send email

Examples:
  /mail_setup
  /mail_inbox
  /mail_read 1
  /mail_send friend@qq.com Subject Body

Supported: QQ/163/Gmail/Outlook/Aliyun
Note: QQ/163 require "auth code" instead of login password
""",
        "help_detail_cron": """📜 [Cron - Scheduled Tasks]

/cron_add <sec> <cmd>   Add recurring task (shell command)
/cron_list              List running scheduled tasks
/cron_del <id>          Delete specified task

Examples:
  /cron_add 300 ls -la /project   Every 5 minutes
  /cron_add 60 df -h              Every minute
  /cron_list
  /cron_del 1

Notes:
  • Based on threading.Timer, tasks vanish on program exit
  • Use /gatekeeper start for persistence
  • Shell commands timeout at 30s, output truncated to 100 chars
  • Dangerous operations trigger security confirmation
""",
        "help_detail_web": """📜 [Web]

/web <query>      Baidu search (returns up to 5 results)
/fetch <url>      Fetch webpage and extract plain text (truncated to 3000 chars)

Examples:
  /web Python asyncio tutorial
  /fetch https://docs.python.org/3/library/asyncio.html

AI auto-invoke:
  【调用：search_web({"query": "..."})】
  【调用：fetch_web({"url": "https://..."})】
""",
        "help_detail_disk": """📜 [Cloud Disk]

Currently supports Aliyun Drive (personal cloud).
Run /disk_setup for first-time QR code login.

/disk_setup       Launch cloud disk setup wizard
/disk_ls          List files and folders in current cloud dir
/disk_cd <dir>     Change cloud directory (supports ..)
/disk_up <local> <remote>    Upload file to current dir
/disk_down <remote> [local]  Download file from current dir

Examples:
  /disk_setup                     First-time QR login
  /disk_ls                        List cloud files
  /disk_cd docs                   Enter docs folder
  /disk_up /local/report.pdf report.pdf
  /disk_down report.pdf /local/

Deps: pip install aligo
""",
        "help_detail_vision": """📜 [Vision]

/see <img_path> [question]   Analyze image with GLM-4V

Steps:
  1. /model glm-4v-plus            Switch to vision model
  2. /see photo.jpg Describe this  Analyze image

AI auto-invoke:
  【调用：generate_image({"prompt": "..."})】
  Image generation uses CogView-3-plus, saved to current dir
""",
        "help_detail_shell": """📜 [Matrix - Shell Commands]

!<cmd>            Run local shell command (e.g. !ls -la)
!<cmd> | <prompt> Pipe command output to AI for analysis

Examples:
  !ls -la /Users/me/project
  !ps aux | find the highest CPU process
  !cat log.txt | analyze this log for issues

Notes:
  • 15s timeout for commands
  • Triggers sec_shell security confirmation
  • In pipe mode AI generates analysis based on output
""",
        "help_detail_tools": """📜 [AI Tool Calls]

AI outputs invocation markers, program parses and executes:
  【调用：tool_name({"param": "value"})】

Common tools:
  write_file    {"path", "content"}
  read_file     {"path"}
  list_files    {}
  search_web    {"query"}
  fetch_web     {"url"}
  generate_image {"prompt"}
  mail_inbox    {}
  mail_send     {"to", "subject", "body"}
  cron_add      {"command", "interval"}
  save_session  {"name"}
  set_model     {"name"}

Plugin calls (command style):
  【命令：/plugin_name args】

Legacy format compatible:
  file_operations\n/write file.md "content"
""",
        "help_detail_app": """📜 [Launcher - Local Apps]

/open <path/URL>           Open file or URL with default app
/launch <app> [target]     Launch specific app, optionally with file/URL
/apps                      List available app aliases on this machine

Examples:
  /open https://example.com
  /open /Users/me/doc.pdf
  /launch chrome https://github.com
  /launch wechat
  /launch word /Users/me/report.docx

Common app aliases:
  Browser: chrome, safari, firefox, edge, browser
  Office:  word, excel, powerpoint, ppt, wps
  Chat:    wechat, qq, dingtalk, lark
  Tools:   vscode, terminal, calculator, notepad
  Media:   music, spotify, vlc
""",
        "help_detail_agent": """📜 [Agent System]

/master on|off|status         Master Agent — self-evolving universal assistant (takes over all chat)

/agent_create <name> <desc>   Auto-generate a complete Agent (persona/skills/code)
/agent_forge <name>           Extract code from the latest AI reply and forge as Agent
/agent_list                   List all Agent instances
/agent_show <name>            View Agent details (persona/memory/skills/code/workflow)
/agent_edit <name> <type>     Edit Agent settings (persona/memory/skills/agent/workflow)
/agent_run <name> [args]      Run specified Agent
/agent_delete <name>          Delete Agent

Agent directory: ~/.fr_cli_agents/<name>/
  • persona.md  — Character setting
  • memory.md   — Long-term memory
  • skills.md   — Skill descriptions
  • agent.py    — Optional custom execution logic (must contain run(context, **kwargs))
  • workflow.md — Optional workflow definition

How to turn existing code into an Agent:
  1. Ask AI to generate code containing def run(context, **kwargs)
  2. The program auto-detects Agent structure and prompts to save
  3. Or manually run /agent_forge <name> to extract code from the latest reply
""",
        "help_detail_builtin": """📜 [Built-in Agents — @ Prefix]

Use @ prefix in chat to trigger built-in Agents:

@local <requirement>         Local system assistant, AI generates and executes shell commands
@remote [alias] <requirement> Remote SSH assistant, executes commands on remote hosts
@spider <URL> [depth]        Smart web crawler with anti-bot adaptation
@db [alias] <requirement>    Database assistant, auto-analyzes schema and generates SQL
@RAG <question>              Local knowledge base Q&A with vector search

RAG Knowledge Base Management:
  /rag_dir <path>   — Set KB directory and sync for the first time
  /rag_sync [path]  — Manually sync KB (vectorize new files)
  /rag_watch start [dir] [--interval N] — Start standalone daemon (persistent background watcher)
  /rag_watch stop   — Stop the standalone daemon
  /rag_watch status — Show daemon status
  /rag_watch log [--lines N] — View daemon log

Notes:
  • ChromaDB runs in embedded mode (PersistentClient), no separate service needed
  • Built-in mode (auto-started after /rag_dir) uses a daemon thread, stops when fr-cli exits
  • Standalone mode (/rag_watch start) is a system-level process, survives terminal exit
  • Daemon managed via PID file, logs written to ~/.fr_cli_rag_watcher.log

Setup wizards:
  /remote_setup  — Remote host configuration wizard
  /db_setup      — Database configuration wizard
""",
        "help_detail_dataframe": """📜 [Data Scroll — Excel / CSV]

/read_excel <file>   Read Excel file and output data summary
/read_csv <file>     Read CSV file and output data summary

Notes:
  • Supports .xlsx, .xls, .csv formats
  • Auto-outputs columns, dtypes, null stats, numeric stats, top-10 preview
  • Summary can be fed to AI for deep analysis
""",
        "help_detail_gatekeeper": """📜 [Gatekeeper Daemon]

/gatekeeper start    Start the daemon (persists Agent HTTP server, global cron, agent cron)
/gatekeeper stop     Stop the daemon
/gatekeeper status   Show daemon status

Agent Cron Jobs:
  /agent_cron_add <agent> <seconds> [input]  Add a scheduled execution for an Agent
  /agent_cron_list                           List all Agent cron jobs
  /agent_cron_del <ID>                       Delete an Agent cron job

Notes:
  • Daemon runs independently of the main fr-cli process, survives terminal exit
  • On start, auto-saves current Agent HTTP port and cron job configs
  • Agent API, global cron jobs, and agent cron jobs survive after fr-cli exits
  • Daemon reloads config every 30 seconds; changes from main process auto-sync
  • Global cron jobs (/cron_add) are auto-synced to daemon config after change
  • Daemon config stored in ~/.fr_cli_gatekeeper.json
""",
        "help_detail_security": """📜 [Security]

4-level confirmation (Y/A/F/N):
  [Y]Once     Allow this operation only
  [A]Session  Allow this session
  [F]Forever  Allow forever (saved to config)
  [N]Deny     Deny this operation

Protected operations:
  sec_read sec_write sec_exec sec_mount sec_gen_img
  sec_send_mail sec_fetch_web sec_upload_disk sec_download_disk
  sec_shell

Path traversal protection:
  VFS checks via Path.resolve(), blocks ../ escaping allowed_dirs

Non-interactive mode:
  • Set FR_CLI_NON_INTERACTIVE=1 to default-deny (for scripts/CI)
""",
    }
}

def T(k, l="zh", *a):
    """根据键名和语言获取国际化文本，支持格式化参数"""
    t = I18N.get(l, I18N["zh"]).get(k, "")
    return t.format(*a) if a else t
