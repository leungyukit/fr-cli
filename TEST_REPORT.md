# fr-cli v2.4.3 测试报告

## 测试时间
2026-06-13

## 测试结果汇总

### ✅ 所有测试通过

```bash
.venv/bin/python -m pytest tests/ -q
# 357 passed in ~15s
```

| 模块 | 状态 | 说明 |
|------|------|------|
| core.llm | ✅ | 模型加载、Provider 配置 |
| core.model_factory | ✅ | 模型工厂、配置文件 |
| core.plan | ✅ | 计划模式生成与执行 |
| agent.shell_mode | ✅ | Shell 模式切换 |
| agent.workflow | ✅ | 工作流引擎 |
| agent.swarm | ✅ | 蜂群统一调度 |
| agent.builtins.local | ✅ | 本地系统操作 Agent |
| agent.builtins.remote | ✅ | 远程 SSH Agent |
| agent.builtins.rag | ✅ | 本地知识库问答 |
| agent.builtins.spider | ✅ | 网页爬虫 |
| agent.builtins.db | ✅ | 数据库助手 |
| weapon.fs | ✅ | 虚拟文件系统沙盒 |
| weapon.mail | ✅ | IMAP/SMTP 邮件 |
| weapon.m365 | ✅ | Microsoft 365 OAuth2 邮件 |
| weapon.cron | ✅ | 定时任务 |
| weapon.web | ✅ | 联网搜索与抓取 |
| weapon.vision | ✅ | 图片生成与识别 |
| weapon.ocr | ✅ | OCR 文字识别 |
| weapon.dataframe | ✅ | Excel / CSV 读取 |
| command.registry | ✅ | 统一工具注册表 |
| command.security | ✅ | 四阶安全确认中间件 |
| memory.history | ✅ | 会话历史 |
| memory.session | ✅ | 按日期自动存档 |
| dynamic_builder | ✅ | 动态构建新工具 |

## 模块导入测试

### 核心模块
- `fr_cli.core.llm.list_providers()` ✅
- `fr_cli.core.model_factory.get_model_factory()` ✅
- `fr_cli.core.plan.generate_plan()` ✅

### Agent 模块
- `fr_cli.agent.shell_mode.get_shell_manager()` ✅
- `fr_cli.agent.workflow.parse_workflow()` ✅
- `fr_cli.agent.swarm.SwarmEngine` ✅
- `fr_cli.agent.builtins.local.run_local_agent()` ✅
- `fr_cli.agent.builtins.remote.run_remote_agent()` ✅

### 武器库模块
- `fr_cli.weapon.mail.MailClient` ✅
- `fr_cli.weapon.m365.M365MailClient` ✅
- `fr_cli.weapon.fs.VFS` ✅
- `fr_cli.weapon.cron.CronManager` ✅
- `fr_cli.weapon.web.WebRaider` ✅
- `fr_cli.weapon.vision.VisionClient` ✅
- `fr_cli.weapon.ocr.ocr_recognize_file()` ✅
- `fr_cli.weapon.dataframe.read_excel()` ✅
- `fr_cli.weapon.dataframe.read_csv()` ✅

## 功能测试

### Shell 模式
```bash
> /shell
(shell) $ ls -la
(shell) $ exit
```

### 模型支持
15+ 模型提供商：zhipu, zhipu-coding, openai, deepseek, kimi, kimi-code, qwen, doubao, mimo, minimax, minimax-token-plan, ernie, stepfun, stepfun-step-plan, spark

### Microsoft 365 邮件
- `/m365_config setup` 配置向导 ✅
- `/m365_inbox` 收件箱列表 ✅
- `/m365_read <id>` 读取邮件 ✅
- `/m365_send <to> <sub> <body>` 发送邮件 ✅

## 已清理的 dead code

本次评审后已删除/清理：
- `fr_cli/command/handlers/` — 与 `command/registered/` 重复
- `fr_cli/agent/coding_helper.py` — 零调用
- `fr_cli/agent/gateway.py` — 零调用
- `fr_cli/agent/acp.py` — 零调用
- `fr_cli/agent/plugin_system.py` — 零调用
- `fr_cli/agent/context_files.py` — 零调用
- `fr_cli/agent/builtins/powerful_agent_template.py` — 仅在测试引用
- `fr_cli/agent/workflow_system/` — 生产零调用
- `fr_cli/agent/image_and_parallel.py` 中的 `ParallelExecutor` / `AsyncParallelExecutor` / `BatchImageGenerator` / `ImageModelConfig` / `ImageGenerator` / `TerminalImageDisplay`
- `fr_cli/main.py:288-368` 重复死代码

## 安全加固

- 注册表为高敏操作补充 `security` 声明：`set_key`, `set_model`, `set_limit`, `set_lang`, `set_alias`, `mcp_call`, `mail_read`, `m365_read`, `m365_config`, `open_file`, `launch_app`, `agent_create`, `update_run`, `local_llm`
- `@local` Windows 路径移除 `shell=True` 回退
- `read_excel` / `read_csv` 命令强制走 `VFS` 沙盒校验

## 命令路由

### /shell 命令
- 文件：`fr_cli/repl/commands/shell.py`
- 行为：切换为交互式 shell 模式，所有输入直接交给 Shell 执行

### /help 命令
- 文件：`fr_cli/repl/commands/_common.py`
- 行为：打印分组命令列表或指定主题详细帮助
