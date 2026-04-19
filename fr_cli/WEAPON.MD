# 法宝图谱 (WEAPON.MD)

> 本文档描述凡人打字机所有可用工具（武器/法宝）。
> 程序运行时会从此文件读取工具信息，动态注入大模型上下文。
> 修改本文件后重启程序即可生效，无需改动源码。
> **调用格式**：所有内置工具使用 `【调用：tool_name({"参数": "值"})】` 格式，参数为标准 JSON。

---

## file_operations
- **名称**: 文件操作工具
- **功能**: 列出文件、查看文件内容、切换目录、写入文件、追加内容、删除文件等
- **程序路径**: fr_cli/weapon/fs.py
- **调用方式**: write_file, read_file, list_files, change_dir, append_file, delete_file
- **触发关键词**: 文件, 目录, folder, 读取, read, 保存到, save to, 写入文件, 创建文件, 生成文件, ls , cat , cd , write , append , delete

## image_analysis
- **名称**: 图片分析工具
- **功能**: 查看和分析图片内容、生成图片
- **程序路径**: fr_cli/weapon/vision.py
- **调用方式**: analyze_image, generate_image
- **触发关键词**: 分析图片, 识图, 看图, describe image, 图片内容, 识别图片, 生成图片, 画图, 画一张

## email_management
- **名称**: 邮件管理工具
- **功能**: 查看收件箱、读取邮件、发送邮件
- **程序路径**: fr_cli/weapon/mail.py
- **调用方式**: mail_inbox, mail_read, mail_send
- **触发关键词**: 邮件, mail, email, 发邮件, 收件箱, inbox, 发送邮件, 查看邮件

## web_search
- **名称**: 网络搜索工具
- **功能**: 搜索网络内容和获取网页
- **程序路径**: fr_cli/weapon/web.py
- **调用方式**: search_web, fetch_web
- **触发关键词**: 搜索, search, 查一下, 查询, look up, 最新新闻, 今天天气, 股价, 汇率, 查百度, 查谷歌

## scheduled_tasks
- **名称**: 定时任务工具
- **功能**: 添加、列出和删除定时任务
- **程序路径**: fr_cli/weapon/cron.py
- **调用方式**: cron_add, cron_list, cron_del
- **触发关键词**: 定时任务, 定时执行, 周期性执行, cron job, scheduled task, 定时器

## cloud_storage
- **名称**: 云盘管理工具
- **功能**: 上传、下载和列出云盘文件
- **程序路径**: fr_cli/weapon/disk.py
- **调用方式**: disk_ls, disk_up, disk_down
- **触发关键词**: 云盘, 上传文件, 下载文件, cloud disk, upload file, download file, 云端

## session_management
- **名称**: 会话管理工具
- **功能**: 保存、加载和导出会话
- **程序路径**: fr_cli/memory/history.py
- **调用方式**: save_session, list_sessions, export_session
- **触发关键词**: 保存会话, 加载会话, 导出会话, save session, load session, export session

## configuration
- **名称**: 配置管理工具
- **功能**: 设置模型、API密钥、语言等
- **程序路径**: fr_cli/conf/config.py
- **调用方式**: set_model, set_key, set_limit, set_lang
- **触发关键词**: 切换模型, 换模型, 改模型, set model, api key, api密钥, 切换语言, 设置上限

## plugin_system
- **名称**: 插件系统工具
- **功能**: 查看和执行自定义插件（skills）
- **程序路径**: fr_cli/addon/plugin.py
- **调用方式**: 【命令：/skills】, 【命令：/<plugin_name>】
- **触发关键词**: 插件, plugin, 技能, skill, 法宝, 自定义工具

## system_commands
- **名称**: 系统命令工具
- **功能**: 执行shell命令和管道操作
- **程序路径**: 内置 (main.py)
- **调用方式**: !<command>, !<cmd> | <prompt>
- **触发关键词**: 执行命令, shell, bash, 系统命令, 运行命令, terminal

## launcher_system
- **名称**: 本机应用启动器
- **功能**: 跨平台调用浏览器、办公软件、通讯工具、媒体播放器等本地程序
- **程序路径**: fr_cli/weapon/launcher.py
- **调用方式**: /open <路径/URL>, /launch <应用> [目标], /apps
- **触发关键词**: 打开, open, 启动, launch, 浏览, 播放, 查看, 打开微信, 打开浏览器, 打开 Word

## agent_system
- **名称**: Agent 分身系统
- **功能**: 创建独立 Agent（角色设定/记忆/技能/工作流），支持 HTTP API 调用
- **程序路径**: fr_cli/agent/
- **调用方式**: /agent_server start [port], /agent_server stop, /agent_server status, /agent_create, /agent_list, /agent_run
- **触发关键词**: agent, 分身, 工作流, workflow, API, HTTP 服务

## builtin_local
- **名称**: @local 本机助手
- **功能**: 拦截 `@local <需求>`，AI 自动生成并执行本机系统命令，结果保存到 Agent 记忆
- **程序路径**: fr_cli/agent/builtins/local.py
- **调用方式**: `@local <需求描述>`
- **触发关键词**: 本地操作, 本机, 系统命令, 终端, shell

## builtin_remote
- **名称**: @remote 远程运维助手
- **功能**: 管理多机 SSH 连接，`@remote [IP/别名] <需求>` 自动探测远程 OS 并生成命令
- **程序路径**: fr_cli/agent/builtins/remote.py
- **调用方式**: `@remote <需求>` 或 `@remote [别名] <需求>`
- **触发关键词**: 远程, 服务器, SSH, 运维, Linux, 主机管理

## builtin_spider
- **名称**: @spider 爬虫助手
- **功能**: requests → selenium 降级策略，模拟真人行为，深度爬取，保存到 `web_YYYYMMDD/`
- **程序路径**: fr_cli/agent/builtins/spider.py
- **调用方式**: `@spider <需求>`
- **触发关键词**: 爬取, 爬虫, 抓取, spider, 采集, 网页下载, 批量下载

## builtin_db
- **名称**: @db 数据库助手
- **功能**: MySQL/PostgreSQL/SQL Server/Oracle 通用交互，自动分析 Schema 生成 SQL，危险操作警告
- **程序路径**: fr_cli/agent/builtins/db.py
- **调用方式**: `@db <需求>` 或 `@db [别名] <需求>`
- **触发关键词**: 数据库, SQL, MySQL, PostgreSQL, 查询, 表结构, DB

## builtin_rag
- **名称**: @RAG 本地知识库助手
- **功能**: ChromaDB 向量检索，后台自动向量化监控目录，`@RAG <问题>` 检索回答
- **程序路径**: fr_cli/agent/builtins/rag.py
- **调用方式**: `@RAG <问题>`
- **触发关键词**: 知识库, RAG, 检索, 向量搜索, 文档问答, 本地文档

## data_scroll
- **名称**: 数据卷轴
- **功能**: 读取 Excel/CSV，输出列名、类型、统计信息和数据预览
- **程序路径**: fr_cli/weapon/dataframe.py
- **调用方式**: `/read_excel <文件>`, `/read_csv <文件>`
- **触发关键词**: Excel, CSV, 表格, 数据分析, 数据预览, 统计
