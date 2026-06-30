"""英文翻译字典"""

EN_DICT = {
  "sys_prompt": "You are an AI assistant. Answer questions directly. Use tools only when they are explicitly provided in the system prompt. If no tools are provided, respond normally without any 【命令：...】 markers.\n\nSpecial note: When the user asks about this program's features, usage help, or requests to send/share the program's documentation, please prioritize using read_file to read the MANUAL.md file in the current workspace, rather than performing a web search.\n\nWhen the user explicitly asks to create a plugin/tool, generate Python code containing def run(args='') inside a ```python block.",
  "prompt_user": "🧑 You",
  "prompt_ai": "🤖 AI",
  "prompt_skill": "⚡",
  "banner_title": [
    " F A N R E N C L I T O O L ",
    "──────────────────────────────────",
    " [ Advanced Code Engine v1.0 ] "
  ],
  "bye_title": [
    "S E E Y O U",
    "N E X T T I M E"
  ],
  "bye_msg": "Happy chatting. 👋",
  "status_model": "🔮 Model",
  "status_limit": "🛡️ Limit",
  "status_dir": "📂 Dir",
  "status_sess": "⏳ Sess",
  "no_dir": "No dir",
  "new_sess": "New",
  "cur_dir": "Active",
  "conn_ok": "✅ Connected.",
  "conn_fail": "❌ Failed:",
  "err_posix": "❌ Error:",
  "err_bound": "⚠️ Denied",
  "err_no_file": "⚠️ Not found",
  "grep_no_match": "No match for '{}' in file: {}",
  "ok_dir_add": "✅ Dir [{}] added",
  "err_dir_no": "❌ Not exists",
  "ok_cd": "✅ Dir: {}",
  "ok_dir_remove": "✅ Dir [{}] removed",
  "err_dir_idx": "❌ Invalid index",
  "err_dir_not_mounted": "❌ Not mounted: {}",
  "ok_write": "✅ Written: {}",
  "err_write_perm": "❌ Permission denied",
  "ok_delete": "✅ Deleted: {}",
  "ok_model": "✅ Model: {}",
  "err_model": "❌ Fail:",
  "diff_new_file": "🆕 New file: {}",
  "diff_overwrite": "📝 Overwrite: {}",
  "diff_append": "➕ Append to: {}",
  "diff_preview_truncated": "(content truncated, showing first {} lines; use /cat for full content)",
  "diff_truncated": "(diff truncated; use system diff for full output)",
  "diff_no_binary": "(binary file, diff not shown)",
  "ok_key": "✅ Updated.",
  "ok_limit": "✅ Limit: {}",
  "err_limit": "❌ Min 1000",
  "ok_forged": "✅ Skill: /{}",
  "ok_sess_save": "✅ Saved: [{}]",
  "ok_sess_load": "✅ Loaded: [{}]",
  "ok_sess_del": "✅ Deleted",
  "ok_undo": "✅ Undone.",
  "err_undo": "❌ None.",
  "ok_export": "✅ Export: {}",
  "ok_alias_set": "✅ Alias: {} = {}",
  "no_alias": "None.",
  "sec_title": "⚠️ Security Check:",
  "sec_opt_y": "[Y]Once",
  "sec_opt_a": "[A]Session",
  "sec_opt_f": "[F]Forever",
  "sec_opt_n": "[N]Deny",
  "sec_denied": "🛑 Abort.",
  "sec_read": "Read file",
  "sec_write": "Write plugin",
  "sec_exec": "Run plugin",
  "sec_mount": "Mount dir",
  "sec_gen_img": "GenImg",
  "sec_send_mail": "Mail",
  "sec_fetch_web": "Fetch",
  "sec_upload_disk": "Upload",
  "sec_download_disk": "Download",
  "sec_shell": "Shell Exec",
  "gen_ing": "🎨 Gen…",
  "gen_ok": "✅ Saved: {}",
  "gen_fail": "❌ Fail: ",
  "see_warn": "⚠️ Need vision model",
  "see_ing": "👁️ See…",
  "help_title": "📜 Help:",
  "help_cfg": "[Config]",
  "help_fs": "[FS]",
  "help_sess": "[Sess]",
  "help_plugin": "[Plugins]",
  "help_extra": "[Adv]",
  "help_shell": "[Matrix]",
  "help_usage": "💡 Usage: /help [topic]  Topics: config, fs, session, plugin, mail, cron, web, disk, vision, shell, tools, security, app, agent, builtin, dataframe, gatekeeper, mcp, all",
  "help_detail_mcp": "📜 [MCP External Tools]\n\nMCP (Model Context Protocol) connects external servers and makes their tools available to AI.\n\nManagement:\n  /mcp_list                List all servers and their tools\n  /mcp_add <name> <cmd> [args...]  Add a stdio server\n  /mcp_del <name>          Remove server\n  /mcp_enable <name>       Enable server\n  /mcp_disable <name>      Disable server\n  /mcp_refresh             Refresh tool list\n\nAI call format:\n  【调用：mcp_call({\"server\": \"server_name\", \"tool\": \"tool_name\", \"arguments\": {...}})】\n\nExample:\n  /mcp_add fs npx -y @modelcontextprotocol/server-filesystem /tmp\n  /mcp_refresh\n",
  "help_not_found": "❌ Unknown topic: {}  Available: config, fs, session, plugin, mail, m365, cron, web, disk, vision, shell, tools, security, app, agent, builtin, dataframe, gatekeeper, mcp, hermes, build, context, status, stock, all",
  "empty": "(Empty)",
  "none": "None",
  "no_sess": "No sess.",
  "no_plugins": "No plug.",
  "ctx_dir": "\n[System: User in {}.]",
  "menu_mail": "[Mail]",
  "menu_cron": "[Cron]",
  "menu_web": "[Web]",
  "menu_disk": "[Disk]",
  "mail_setup": "/mail_setup",
  "mail_inbox": "/mail_inbox",
  "mail_read": "/mail_read <ID>",
  "mail_send": "/mail_send <To> <Sub> <Body>",
  "mail_ok": "✅ Sent",
  "mail_err": "❌ Err:",
  "mail_no_cfg": "❌ No Mail",
  "mail_sub": "Sub: {}",
  "mail_from": "From: {}",
  "mail_date": "Date: {}",
  "cron_add": "/cron_add <S> <C>",
  "cron_list": "/cron_list",
  "cron_del": "/cron_del <ID>",
  "cron_ok": "✅ Added (ID:{}, {}s)",
  "cron_killed": "✅ Killed: {}",
  "cron_running": "🏃 Run",
  "web_search": "/web <Q> Search",
  "web_fetch": "/fetch <URL>",
  "web_err": "❌ Err:",
  "web_no_res": "None.",
  "web_title": "📜 Search:",
  "disk_setup": "/disk_setup",
  "disk_ls": "/disk_ls <N>",
  "disk_up": "/disk_up <N> <L>",
  "disk_down": "/disk_down <N> <R> [L]",
  "disk_ok_up": "✅ Up: {}",
  "disk_ok_down": "✅ Down: {}",
  "disk_err": "❌ Err: ",
  "disk_no_cfg": "❌ No Disk",
  "disk_miss_dep": "❌ Miss: {} (pip install {})",
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
  "help_detail_config": "📜 [Config & Model]\n\n/model                    Interactive model selection\n/model config             Interactive model config wizard (provider + model + key)\n/model list               List all available models/providers\n/model current            Show current model\n/model default            Reset to provider default model\n/model <arg>              Switch model directly (e.g. /model deepseek:deepseek-chat)\n/providers                View/manage all provider configs\n/providers use <provider> Switch to specified provider\n/providers setup          Interactive provider config wizard\n/key <key>                Set API Key for current provider\n/key <provider> <key>     Set API Key for specified provider\n/limit <n>                Set token limit (min 1000)\n/lang <zh/en>             Switch UI language\n/autonomous [manual|sandbox_auto|full_auto|off]  Set autonomous mode\n/mode <direct|cot|tot|react|plan>  Switch AI thinking mode\n/dir <path>               Add allowed directory to sandbox\n/dirs                     List all mounted directories\n/rmdir <idx>              Remove specified directory\n/export                   Export current session to Markdown\n/update check             Check for updates\n/update run               Apply update and restart\n\nConfig file: ~/.fr_cli/config.json\n",
  "help_detail_fs": "📜 [FS - File Operations]\n\n/dir              List files in current directory\n/open <file>      View file content (UTF-8/GBK/Latin-1)\n/dirs             List all mounted directories\n/rmdir <idx>      Remove specified directory\n/write <f> <c>    Write/overwrite file\n/append <f> <c>   Append content to file\n/delete <f>       Delete file\n\nExamples:\n  /dir               List files\n  /open README.md    View file content\n  /dirs              List mounted directories\n  /write a.md text   Write file\n  /append a.md more  Append content\n  /delete a.md       Delete file (needs confirmation)\n\nSecurity:\n  • Restricted to allowed_dirs, ../ traversal blocked\n  • /write auto-creates parent directories\n  • Dangerous ops trigger 4-level security confirmation\n",
  "help_detail_session": "📜 [Session]\n\n/save <name>      Save current conversation\n/load             Load historical session (interactive)\n/del              Delete historical session (interactive)\n/export           Export session as Markdown\n\nAuto-save by date:\n  /session_list     List all auto-saved sessions\n  /session_load <N> Load session by index and continue\n  /session_del <N>  Delete auto-saved session by index\n\nExamples:\n  /save project      Save current session\n  /load              Interactive load\n  /del               Interactive delete\n  /export            Export to Markdown\n  /session_list      View auto-saved sessions\n  /session_load 1    Load today's first session\n\nContext Memory & Compression:\n  • Auto-summarize last 5 turns\n  • Auto-compress early conversation when threshold exceeded (/context)\n  • Persisted to config.json context namespace by session_name\n  • Context restored when loading session\n  • Auto-created date-indexed session file on each launch (~/.fr_cli/sessions/auto/)\n",
  "help_detail_plugin": "📜 [Plugins]\n\n/skills           List installed plugins\n/<plugin> [args]  Run specified plugin\n\nAuto-evolution:\n  • When AI reply contains def run(args='') and ```python block\n  • Prompts to save as plugin, enter name to forge\n\nPlugin dir: ~/.fr_cli/plugins/\nConvention: def run(args='') returning a string\nSafety: Runs in isolated subprocess with 15s timeout\n",
  "help_detail_mail": "📜 [Mail]\n\nSetup:\n  1. Get auth code (QQ Mail: Settings→Account→Enable IMAP/SMTP)\n  2. /mail setup to run config wizard\n\n/mail setup       Mail config wizard\n/mail inbox       List last 10 emails\n/mail read <id>   Read full content of specified email\n/mail send <to> <sub> <body>  Send email\n\nExamples:\n  /mail setup\n  /mail inbox\n  /mail read 1\n  /mail send friend@qq.com Subject Body\n\nSupported: QQ/163/Gmail/Outlook/Aliyun\nNote: QQ/163 require \"auth code\" instead of login password\n",
  "help_detail_cron": "📜 [Cron - Scheduled Tasks]\n\n/cron_add <sec> <cmd>   Add recurring task (shell command)\n/cron_list              List running scheduled tasks\n/cron_del <id>          Delete specified task\n\nExamples:\n  /cron_add 300 ls -la /project   Every 5 minutes\n  /cron_add 60 df -h              Every minute\n  /cron_list\n  /cron_del 1\n\nNotes:\n  • Based on threading.Timer, tasks vanish on program exit\n  • Use /gatekeeper start for persistence\n  • Shell commands timeout at 30s, output truncated to 100 chars\n  • Dangerous operations trigger security confirmation\n",
  "help_detail_web": "📜 [Web]\n\n/web <query>      Baidu search (returns up to 5 results)\n/fetch <url>      Fetch webpage and extract plain text (truncated to 3000 chars)\n\nExamples:\n  /web Python asyncio tutorial\n  /fetch https://docs.python.org/3/library/asyncio.html\n\nAI auto-invoke:\n  【调用：search_web({\"query\": \"...\"})】\n  【调用：fetch_web({\"url\": \"https://...\"})】\n",
  "help_detail_disk": "📜 [Cloud Disk]\n\nCurrently supports Aliyun Drive (personal cloud).\nRun /disk_setup for first-time QR code login.\n\n/disk_setup       Launch cloud disk setup wizard\n/disk_ls          List files and folders in current cloud dir\n/disk_cd <dir>     Change cloud directory (supports ..)\n/disk_up <local> <remote>    Upload file to current dir\n/disk_down <remote> [local]  Download file from current dir\n\nExamples:\n  /disk_setup                     First-time QR login\n  /disk_ls                        List cloud files\n  /disk_cd docs                   Enter docs folder\n  /disk_up /local/report.pdf report.pdf\n  /disk_down report.pdf /local/\n\nDeps: pip install aligo\n",
  "help_detail_vision": "📜 [Vision]\n\n/see <img_path> [question]   Analyze image with GLM-4V\n\nSteps:\n  1. /model <vision-model>         Switch to vision model\n  2. /see photo.jpg Describe this  Analyze image\n\nAI auto-invoke:\n  【调用：generate_image({\"prompt\": \"...\"})】\n  Image generation uses the image model configured for the current provider, saved to current dir\n",
  "help_detail_shell": "📜 [Matrix - Shell Commands]\n\n!<cmd>            Run local shell command (e.g. !ls -la)\n!<cmd> | <prompt> Pipe command output to AI for analysis\n\nExamples:\n  !ls -la /Users/me/project\n  !ps aux | find the highest CPU process\n  !cat log.txt | analyze this log for issues\n\nNotes:\n  • 15s timeout for commands\n  • Triggers sec_shell security confirmation\n  • In pipe mode AI generates analysis based on output\n",
  "help_detail_tools": "📜 [AI Tool Calls]\n\nAI outputs invocation markers, program parses and executes:\n  【调用：tool_name({\"param\": \"value\"})】\n\nCommon tools:\n  write_file     {\"path\", \"content\"}\n  read_file      {\"path\"}\n  list_files     {}\n  search_web     {\"query\"}\n  fetch_web      {\"url\"}\n  generate_image {\"prompt\"}\n  mail_inbox     {}\n  mail_send      {\"to\", \"subject\", \"body\"}\n  cron_add       {\"command\", \"interval\"}\n  save_session   {\"name\"}\n  set_model      {\"name\"}\n  agent_call     {\"name\", \"user_input\"}\n  swarm_run      {\"mode\", \"names\", \"user_input\"}\n  mcp_call       {\"server\", \"tool\", \"arguments\"}\n\nDynamic Builder:\n  /build <requirement>  Auto-generate tool, install deps, self-test and register\n  /build list           List built tools\n  /build check <name>   Re-test and fix a tool\n  /build del <name>     Delete a built tool\n\nPlugin calls (command style):\n  【命令：/plugin_name args】\n\nLegacy format compatible:\n  file_operations\n/write file.md \"content\"\n",
  "help_detail_app": "📜 [Launcher - Local Apps]\n\n/open <path/URL>           Open file or URL with default app\n/launch <app> [target]     Launch specific app, optionally with file/URL\n/apps                      List available app aliases on this machine\n\nExamples:\n  /open https://example.com\n  /open /Users/me/doc.pdf\n  /launch chrome https://github.com\n  /launch wechat\n  /launch word /Users/me/report.docx\n\nCommon app aliases:\n  Browser: chrome, safari, firefox, edge, browser\n  Office:  word, excel, powerpoint, ppt, wps\n  Chat:    wechat, qq, dingtalk, lark\n  Tools:   vscode, terminal, calculator, notepad\n  Media:   music, spotify, vlc\n",
  "help_detail_agent": "📜 [Agent System]\n\n/master on|off|status         Master Agent — self-evolving universal assistant (takes over all chat)\n\n/agent_create <name> <desc>   Auto-generate a complete Agent (persona/skills/code)\n/agent_forge <name>           Extract code from the latest AI reply and forge as Agent\n/agent_list                   List all Agent instances\n/agent_show <name>            View Agent details (persona/memory/skills/code/workflow)\n/agent_edit <name> <type>     Edit Agent settings (persona/memory/skills/agent/workflow)\n/agent_run <name> [args]      Run specified Agent\n/agent_delete <name>          Delete Agent\n/agent_model <name> [provider:model|clear|--key <key>]\n                              View/set Agent-specific model (persisted in config.json)\n\nAgent directory: ~/.fr_cli/agents/<name>/\n  • persona.md  — Character setting\n  • memory.md   — Long-term memory\n  • skills.md   — Skill descriptions\n  • agent.py    — Optional custom execution logic (must contain run(context, **kwargs))\n  • workflow.md — Optional workflow definition\n  • config.json — Model binding config (provider / model / key, optional)\n\nModel binding examples:\n  /agent_model my_agent deepseek:deepseek-chat  — Bind exclusive model\n  /agent_model my_agent --key sk-own-key        — Set independent API Key\n  /agent_model my_agent clear                   — Clear config, fallback to global default\n\nHow to turn existing code into an Agent:\n  1. Ask AI to generate code containing def run(context, **kwargs)\n  2. The program auto-detects Agent structure and prompts to save\n  3. Or manually run /agent_forge <name> to extract code from the latest reply\n",
  "help_detail_builtin": "📜 [Built-in Agents — @ Prefix]\n\nUse @ prefix in chat to trigger built-in Agents:\n\n@local <requirement>         Local system assistant, AI generates and executes shell commands\n@remote [alias] <requirement> Remote SSH assistant, executes commands on remote hosts\n@spider <URL> [depth]        Smart web crawler with anti-bot adaptation\n@db [alias] <requirement>    Database assistant, auto-analyzes schema and generates SQL\n@RAG <question>              Local knowledge base Q&A with vector search\n@stock <requirement>         Stock/quant assistant, quote and simulated trading\n\nRAG Knowledge Base Management:\n  /rag_dir <path>   — Set KB directory and sync for the first time\n  /rag_sync [path]  — Manually sync KB (vectorize new files)\n  /rag_watch start [dir] [--interval N] — Start standalone daemon (persistent background watcher)\n  /rag_watch stop   — Stop the standalone daemon\n  /rag_watch status — Show daemon status\n  /rag_watch log [--lines N] — View daemon log\n\nNotes:\n  • ChromaDB runs in embedded mode (PersistentClient), no separate service needed\n  • Built-in mode (auto-started after /rag_dir) uses a daemon thread, stops when fr-cli exits\n  • Standalone mode (/rag_watch start) is a system-level process, survives terminal exit\n  • Daemon managed via PID file, logs written to ~/.fr_cli/rag/watcher.log\n\nSetup wizards:\n  /remote_setup  — Remote host configuration wizard (config: ~/.fr_cli/remote/hosts.json)\n  /db_setup      — Database configuration wizard (config: ~/.fr_cli/database.json)\n  /stock_config setup — Stock data source config wizard (config: ~/.fr_cli/stock.json)\n",
  "help_detail_dataframe": "📜 [Data Scroll — Excel / CSV]\n\n/read_excel <file>   Read Excel file and output data summary\n/read_csv <file>     Read CSV file and output data summary\n\nNotes:\n  • Supports .xlsx, .xls, .csv formats\n  • Auto-outputs columns, dtypes, null stats, numeric stats, top-10 preview\n  • Summary can be fed to AI for deep analysis\n",
  "help_detail_gatekeeper": "📜 [Gatekeeper Daemon]\n\n/gatekeeper start    Start the daemon (persists Agent HTTP server, global cron, agent cron)\n/gatekeeper stop     Stop the daemon\n/gatekeeper status   Show daemon status\n\nAgent Cron Jobs:\n  /agent_cron_add <agent> <seconds> [input]  Add a scheduled execution for an Agent\n  /agent_cron_list                           List all Agent cron jobs\n  /agent_cron_del <ID>                       Delete an Agent cron job\n\nNotes:\n  • Daemon runs independently of the main fr-cli process, survives terminal exit\n  • On start, auto-saves current Agent HTTP port and cron job configs\n  • Agent API, global cron jobs, and agent cron jobs survive after fr-cli exits\n  • Daemon reloads config every 30 seconds; changes from main process auto-sync\n  • Global cron jobs (/cron_add) are auto-synced to daemon config after change\n  • Daemon config stored in ~/.fr_cli/daemon/config.json\n",
  "help_detail_hermes": "📜 [Hermes Autonomous Engine]\n\n/hermes status              Show engine status\n/hermes goal <goal>         Create a goal and auto-decompose into subtasks\n/hermes task <desc>         Create a delayed task (default 5 minutes)\n/hermes task \"send daily\" --due 60 --depends <task_id>\n/hermes list [status]       List tasks\n/hermes run                 Run one polling cycle immediately\n/hermes stop                Stop daemon thread\n/hermes http [port]         Start HTTP task interface\n/hermes log <id>            View task result/log\n/hermes cancel <id>         Pause a task\n/hermes review <id>         Review a pending task\n/hermes confirm <id>        Confirm and execute a task\n\nNotes:\n  • Tasks and goals persisted to ~/.fr_cli/hermes.json\n  • Supports subtask dependency chains, retry, cross-task memory and failure-driven learning\n  • Use /status errors to view Hermes errors and failure patterns\n",
  "help_detail_build": "📜 [Dynamic Builder]\n\n/build <requirement>    Auto-generate a tool and register it\n/build list             List built tools\n/build check <name>     Re-test and auto-fix a tool\n/build del <name>       Delete a built tool\n\nExamples:\n  /build generate a QR code recognizer\n  /build turn image into ASCII art\n  /build list\n  /build check qr_tool\n\nNotes:\n  • Generated code saved to ~/.fr_cli/dynamic_tools/<name>.py\n  • Metadata saved to ~/.fr_cli/dynamic_tools/registry.json\n  • After generation, dependencies are installed and self-tests run; failures roll back\n  • Use /status errors to view build failures\n",
  "help_detail_context": "📜 [Context Compression]\n\n/context status                 Show current estimated tokens and config\n/context compress               Compress early conversation now\n/context threshold [N]          View/set auto-compress threshold (0 to disable)\n/context keep [N]               View/set recent turns to keep\n\nConfig (~/.fr_cli/config.json memory namespace):\n  memory.compress_threshold     default 4000\n  memory.compress_keep_recent   default 5\n\nNotes:\n  • When session tokens exceed threshold, early conversation is summarized\n  • Keeps last N turns intact to preserve current context\n  • Reduces prompt cost and context window pressure for long sessions\n",
  "help_detail_status": "📜 [System Status & Error Report]\n\n/status           Human-readable system status panel\n/status json      Output JSON status\n/status errors    Output centralized error report\n\nError report aggregates:\n  • Hermes task failures and failure patterns\n  • Dynamic builder self-test failures\n  • Security review denied operations\n  • MasterAgent failure patterns\n",
  "help_detail_stock": "📜 [Stock Assistant]\n\nConfig:\n  /stock_config setup               Interactive data source config\n  /stock_config source akshare|mairui|tushare|trade\n  /stock_config key mairui <key>\n  /stock_config token tushare <token>\n\nUsage:\n  @stock query Kweichow Moutai price\n  @stock buy 600519 1500.00 100    # simulated trading\n\nNotes:\n  • Data sources: akshare (no key), mairui API (key required), tushare (token required)\n  • Trading is currently simulated; real trading API needs custom extension\n",
  "help_detail_security": "📜 [Security]\n\n4-level confirmation (Y/A/F/N):\n  [Y]Once     Allow this operation only\n  [A]Session  Allow this session\n  [F]Forever  Allow forever (saved to config)\n  [N]Deny     Deny this operation\n\nProtected operations:\n  sec_read sec_write sec_exec sec_mount sec_gen_img\n  sec_send_mail sec_fetch_web sec_upload_disk sec_download_disk\n  sec_shell\n\nPath traversal protection:\n  VFS checks via Path.resolve(), blocks ../ escaping allowed_dirs\n\nNon-interactive mode:\n  • Set FR_CLI_NON_INTERACTIVE=1 to default-deny (for scripts/CI)\n\nAutonomous mode (v2.5.1):\n  /autonomous manual       — Default: ask for every sec_* operation\n  /autonomous sandbox_auto — Auto-allow sandbox read/write/web; system ops still ask\n  /autonomous full_auto    — Auto-allow all operations (dangerous)\n  /autonomous off          — Same as manual\n\nPer-category Forever (v2.4.4):\n  Pressing [F] only whitelists the current sec_* category. It no longer\n  bleeds into other categories (e.g. confirming read_file does NOT silently\n  allow delete_file).\n  Revoke all permanent allowances: /unconfirm\n",

  # ---------- Tutorial ----------
  "tutorial_title": "🎓 fr-cli Interactive Tutorial",
  "tutorial_prompt_next": "Press Enter for next step...",
  "tutorial_skipped": "Tutorial skipped.",
  "tutorial_complete": "🎉 Tutorial complete! Type /help for more commands.",
  "tutorial_hint": "Tip: First run /dir <your_workspace> to set working directory.",

  "tutorial_step1_title": "🎯 Step 1: Chat with AI",
  "tutorial_step1_content":
    "Type any text to chat with AI.\n"
    "Example: \"Explain what recursion is\"\n"
    "Press Enter to send, Shift+Enter or Ctrl+J for newline.\n"
    "AI auto-detects intent and invokes tools (search, file IO, etc).",

  "tutorial_step2_title": "⚙️ Step 2: Configure Model & API Key",
  "tutorial_step2_content":
    "fr-cli supports Zhipu, DeepSeek, Kimi, Qwen, StepFun, MiniMax and 25+ providers:\n"
    "  /model                    Show current model and available providers\n"
    "  /model config             Interactive config wizard (recommended)\n"
    "  /model <model_name>       Switch by name (e.g. /model deepseek-chat)\n"
    "  /model <provider>:<model> Switch with provider (e.g. /model deepseek:deepseek-chat)\n"
    "  /providers use <provider> Switch provider\n"
    "  /key <your-key>           Set API key for current provider\n"
    "Without a configured model, chat is blocked and prompts for setup.",

  "tutorial_step3_title": "📁 Step 3: Working Directories & File Operations",
  "tutorial_step3_content":
    "Use / commands for file operations (protected by VFS sandbox):\n"
    "  /dir <path>     Add and list working directory\n"
    "  /open <file>    View file contents\n"
    "  /dirs           List mounted directories\n"
    "  /write <f>      Write file (multi-line, Ctrl+D to finish)\n"
    "  /delete <f>     Delete file\n"
    "AI can also auto read/write files. Risky ops trigger security confirm.",

  "tutorial_step4_title": "💾 Step 4: Session Management",
  "tutorial_step4_content":
    "Each session has a unique UUID, auto-archived to ~/.fr_cli/sessions/auto/:\n"
    "  /new              New session, reset context\n"
    "  /save <name>      Manual save\n"
    "  /load             Load history\n"
    "  /export           Export current session to Markdown\n"
    "  /session_list     List auto archives\n"
    "  /session_load <n> Load specific auto archive",

  "tutorial_step5_title": "🌐 Step 5: Web & Multimodal",
  "tutorial_step5_content":
    "  /web <query>         Web search\n"
    "  /see <img>           Image analysis\n"
    "  /read_excel <f>      Read Excel\n"
    "  /read_csv <f>        Read CSV\n"
    "  /ocr <img/pdf>       OCR text recognition\n"
    "  !<cmd>               Run system command (e.g. !ls -la)\n"
    "  !<cmd> | <prompt>    Pipe command output to AI",

  "tutorial_step6_title": "🤖 Step 6: Agent Avatars",
  "tutorial_step6_content":
    "Create independent agents with own persona, memory, and skills:\n"
    "  /agent_create <name> <desc>   Auto-generate agent\n"
    "  /agent_list                   List agents\n"
    "  /agent_show <name>            Show agent details\n"
    "  /agent_run <name>             Run agent\n"
    "  /agent_model <name> <cfg>     Bind dedicated model\n"
    "Built-in: @local @remote @db @RAG @spider @stock",

  "tutorial_step7_title": "📚 Step 7: RAG Local Knowledge Base",
  "tutorial_step7_content":
    "Vectorize local docs, let AI answer based on knowledge base:\n"
    "  /rag_dir <dir>       Set knowledge base dir and initial sync\n"
    "  /rag_sync [dir]      Manual sync\n"
    "  /rag_watch start     Start background file monitor\n"
    "  @RAG <question>      Q&A based on knowledge base",

  "tutorial_step8_title": "🔌 Step 8: MCP External Tools",
  "tutorial_step8_content":
    "Connect external tool servers via MCP protocol:\n"
    "  /mcp_list            List MCP servers\n"
    "  /mcp_add <n> <cmd>   Add server\n"
    "  /mcp_enable <name>   Enable server\n"
    "  /mcp_refresh         Refresh tool list",

  "tutorial_step9_title": "🧠 Step 9: Thinking Mode, Master & Hermes",
  "tutorial_step9_content":
    "  /mode <direct|cot|tot|react|plan>   Switch thinking mode\n"
    "  /master on|off                      Enable/disable MasterAgent\n"
    "  /hermes goal <goal>                 Create goal and decompose\n"
    "  /hermes task <desc>                 Create background autonomous task\n"
    "  /mode react will show AI reasoning.",

  "tutorial_step10_title": "🚀 Step 10: More Exploration",
  "tutorial_step10_content":
    "  /build <req>         Dynamic tool builder\n"
    "  /context             Manage context compression\n"
    "  /status errors       View centralized error report\n"
    "  /usage [days]        View LLM usage\n"
    "  /stock_config setup  Configure stock data source\n"
    "  /cron_add <s> <cmd>  Add cron task\n"
    "  /gatekeeper start    Start daemon\n"
    "  /autostart           One-click start all background services\n"
    "  /tutorial            Re-show this tutorial\n"
    "  /help <topic>        View topic help\n"
    "  /queue               View dialog queue\n"
    "  /exit                Exit"
}
