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
        "help_usage": "💡 用法: /help [主题]  可用主题: config, fs, session, plugin, mail, cron, web, disk, vision, shell, tools, security, app, all",
        "help_not_found": "❌ 未知主题: {}  可用: config, fs, session, plugin, mail, cron, web, disk, vision, shell, tools, security, app, all",
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
/alias <k> [v]    查看/设置命令别名
/dir <path>       添加允许访问的目录到沙盒
/export           导出当前会话为Markdown文件
/update check     检查更新
/update run       执行更新并重启

配置文件: ~/.zhipu_cli_config.json
""",
        "help_detail_fs": """📜 【洞府 - 文件操作】

/ls               列出当前目录文件
/cat <file>       查看文件内容 (支持UTF-8/GBK/Latin-1)
/cd <dir>         切换工作目录
/write <f> <c>    写入/覆盖文件
/append <f> <c>   追加内容到文件
/delete <f>       删除文件

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

上下文记忆:
  • 自动保留最近5轮对话摘要
  • 按 session_name 持久化到 ~/.zhipu_cli_context.json
  • 加载会话时自动恢复上下文摘要
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

需先在 ~/.zhipu_cli_config.json 中配置 mail 字段:
  {
    "imap_server": "imap.qq.com",
    "smtp_server": "smtp.qq.com",
    "email": "your@qq.com",
    "password": "授权码"
  }

/mail_inbox       列出收件箱最近10封邮件
/mail_read <id>   读取指定邮件完整内容
/mail_send <to> <sub> <body>  发送邮件

支持邮箱: QQ/163/Gmail/Outlook/阿里云
注意: QQ/163 需使用「授权码」而非登录密码
""",
        "help_detail_cron": """📜 【结界 - 定时任务】

/cron_add <秒> <命令>   添加循环定时任务 (Shell命令)
/cron_list              列出运行中的定时任务
/cron_del <id>          删除指定任务

注意:
  • 基于 threading.Timer, 程序退出后任务消失
  • Shell命令执行30秒超时, 输出截断100字符
  • 危险操作触发安全确认
""",
        "help_detail_web": """📜 【游侠 - 网络搜索】

依赖: pip install requests

/web <query>      百度搜索 (返回最多5条结果)
/fetch <url>      抓取网页并提取纯文本 (截断3000字符)

AI自动调用:
  【调用：search_web({"query": "搜索词"})】
  【调用：fetch_web({"url": "https://..."})】
""",
        "help_detail_disk": """📜 【腾云 - 云盘功能】

需先在配置中设置 disk 字段:
  {
    "type": "oss",
    "ak": "AccessKey", "sk": "SecretKey",
    "endpoint": "oss-cn-hangzhou.aliyuncs.com",
    "bucket": "my-bucket", "prefix": "fr-cli/"
  }

/disk_ls          列出云端文件
/disk_up <local> <remote>   上传文件
/disk_down <remote> [local] 下载文件

依赖: pip install oss2 (阿里云)
      或 fr-cli[aliyun] / fr-cli[baidu] / fr-cli[onedrive]
""",
        "help_detail_vision": """📜 【天眼 - 图像功能】

/see <图片路径> [问题]    用GLM-4V分析图片内容

注意:
  • 需切换模型至 glm-4v-plus: /model glm-4v-plus
  • 支持本地图片路径或URL
  • AI自动调用: 【调用：generate_image({"prompt": "描述"})】
  • 图片生成使用 CogView-3-plus, 保存到当前目录
""",
        "help_detail_shell": """📜 【破壁 - 系统命令】

!<cmd>            执行本地Shell命令 (如 !ls -la)
!<cmd> | <prompt> 将命令输出管道给AI分析

示例:
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

常用应用别名:
  浏览器: chrome, safari, firefox, edge, 浏览器
  办公:   word, excel, powerpoint, ppt, wps
  通讯:   wechat, 微信, qq, 钉钉, 飞书
  工具:   vscode, terminal, 终端, 计算器, 记事本
  媒体:   music, 播放器, spotify, vlc

示例:
  /open https://example.com
  /open /Users/me/doc.pdf
  /launch chrome https://example.com
  /launch 微信
  /launch word /Users/me/report.docx
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
        "ok_model": "✅ Model: {}", "err_model": "❌ Fail:", "ok_key": "✅ Updated.",
        "ok_limit": "✅ Limit: {}", "err_limit": "❌ Min 1000", "ok_forged": "✅ Skill: /{}",
        "ok_sess_save": "✅ Saved: [{}]", "ok_sess_load": "✅ Loaded: [{}]", "ok_sess_del": "✅ Deleted",
        "ok_undo": "✅ Undone.", "err_undo": "❌ None.", "ok_export": "✅ Export: {}",
        "ok_alias_set": "✅ Alias: {} = {}", "no_alias": "None.",
        "sec_title": "⚠️ Security Check:", "sec_opt_y": "[Y]Once", "sec_opt_a": "[A]Session", "sec_opt_f": "[F]Forever", "sec_opt_n": "[N]Deny", "sec_denied": "🛑 Abort.",
        "sec_read": "Read file", "sec_write": "Write plugin", "sec_exec": "Run plugin", "sec_mount": "Mount dir", "sec_gen_img": "GenImg", "sec_send_mail": "Mail", "sec_fetch_web": "Fetch", "sec_upload_disk": "Upload", "sec_download_disk": "Download", "sec_shell": "Shell Exec",
        "gen_ing": "🎨 Gen…", "gen_ok": "✅ Saved: {}", "gen_fail": "❌ Fail: ", "see_warn": "⚠️ Need glm-4v-plus", "see_ing": "👁️ See…",
        "help_title": "📜 Help:", "help_cfg": "[Config]", "help_fs": "[FS]", "help_sess": "[Sess]", "help_plugin": "[Plugins]", "help_extra": "[Adv]", "help_shell": "[Matrix]",
        "help_usage": "💡 Usage: /help [topic]  Topics: config, fs, session, plugin, mail, cron, web, disk, vision, shell, tools, security, app, all",
        "help_not_found": "❌ Unknown topic: {}  Available: config, fs, session, plugin, mail, cron, web, disk, vision, shell, tools, security, app, all",
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
/alias <k> [v]    View/set command alias
/dir <path>       Add allowed directory to sandbox
/export           Export current session to Markdown
/update check     Check for updates
/update run       Apply update and restart

Config file: ~/.zhipu_cli_config.json
""",
        "help_detail_fs": """📜 [FS - File Operations]

/ls               List files in current directory
/cat <file>       View file content (UTF-8/GBK/Latin-1)
/cd <dir>         Change working directory
/write <f> <c>    Write/overwrite file
/append <f> <c>   Append content to file
/delete <f>       Delete file

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

Context Memory:
  • Auto-summarize last 5 turns
  • Persisted to ~/.zhipu_cli_context.json by session_name
  • Context restored when loading session
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

Requires mail config in ~/.zhipu_cli_config.json:
  {"imap_server":"imap.qq.com","smtp_server":"smtp.qq.com",
   "email":"your@qq.com","password":"auth_code"}

/mail_inbox       List last 10 emails
/mail_read <id>   Read full content of specified email
/mail_send <to> <sub> <body>  Send email

Supported: QQ/163/Gmail/Outlook/Aliyun
Note: QQ/163 require "auth code" instead of login password
""",
        "help_detail_cron": """📜 [Cron - Scheduled Tasks]

/cron_add <sec> <cmd>   Add recurring task (shell command)
/cron_list              List running scheduled tasks
/cron_del <id>          Delete specified task

Notes:
  • Based on threading.Timer, tasks vanish on program exit
  • Shell commands timeout at 30s, output truncated to 100 chars
  • Dangerous operations trigger security confirmation
""",
        "help_detail_web": """📜 [Web]

Requires: pip install requests

/web <query>      Baidu search (returns up to 5 results)
/fetch <url>      Fetch webpage and extract plain text (truncated to 3000 chars)

AI auto-invoke:
  【调用：search_web({"query": "..."})】
  【调用：fetch_web({"url": "https://..."})】
""",
        "help_detail_disk": """📜 [Cloud Disk]

Requires disk config:
  {"type":"oss","ak":"...","sk":"...",
   "endpoint":"oss-cn-hangzhou.aliyuncs.com",
   "bucket":"my-bucket","prefix":"fr-cli/"}

/disk_ls          List cloud files
/disk_up <local> <remote>    Upload file
/disk_down <remote> [local]  Download file

Deps: pip install oss2 (Aliyun)
      or fr-cli[aliyun] / fr-cli[baidu] / fr-cli[onedrive]
""",
        "help_detail_vision": """📜 [Vision]

/see <img_path> [question]   Analyze image with GLM-4V

Notes:
  • Switch model first: /model glm-4v-plus
  • Supports local path or URL
  • AI auto-invoke: 【调用：generate_image({"prompt": "..."})】
  • Image generation uses CogView-3-plus, saved to current dir
""",
        "help_detail_shell": """📜 [Matrix - Shell Commands]

!<cmd>            Run local shell command (e.g. !ls -la)
!<cmd> | <prompt> Pipe command output to AI for analysis

Examples:
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

Common app aliases:
  Browser: chrome, safari, firefox, edge, browser
  Office:  word, excel, powerpoint, ppt, wps
  Chat:    wechat, qq, dingtalk, lark
  Tools:   vscode, terminal, calculator, notepad
  Media:   music, spotify, vlc

Examples:
  /open https://example.com
  /open /Users/me/doc.pdf
  /launch chrome https://example.com
  /launch wechat
  /launch word /Users/me/report.docx
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
""",
    }
}

def T(k, l="zh", *a):
    """根据键名和语言获取国际化文本，支持格式化参数"""
    t = I18N.get(l, I18N["zh"]).get(k, "")
    return t.format(*a) if a else t
