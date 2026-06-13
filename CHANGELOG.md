# 更新日志

## v2.4.4 (2026-06-13)

### 安全：AI `【命令：...】` 走 sec_* 确认
- 修复 v2 报告里的 prompt injection 绕过面：AI 通过 `【命令：/cmd args】` 触发的工具调用之前默认 `skip_security=True`（由 `_dispatch_cmd_parts` 硬编码），与 `【调用：...】` 行为不一致
- 现在 `process_ai_commands` 的 `【命令：...】` 分支透传 `skip_security=False`（对齐 `【调用：...】`）
- `execute()` / `_dispatch_cmd_parts()` / `dispatch_cmd()` 接受显式 `skip_security` 参数；调用方可显式 `True` 跳过（已通过 `peek_ai_commands` 提前人工确认的场景）

### 安全：`auto_confirm_forever` 拆为分级 + `/unconfirm` 撤销
- 旧版单一 `auto_confirm_forever: bool` 拆为 `auto_confirm: dict[str, bool]`，按 `sec_*` 类别独立
- 按 `[F]` 仅对**当前 sec_* 类别**永久放行，不再波及其他类别（v2 报告里的关键回归：`按 F 放过 read_file 不会顺带放过 delete_file`）
- 新增 `/unconfirm` 命令：清除所有 `auto_confirm` 设置，下次 `sec_*` 操作恢复弹窗
- 旧版 `auto_confirm_forever=True` 在 `SecurityManager.__init__` 自动迁移为新版 `auto_confirm` dict（覆盖所有已知 sec_* 类别维持旧语义），迁移后清除旧字段
- 新增 `fr_cli.security.security._migrate_fconfirm()` / `_migrate_sconfirm()` 兼容 bool 输入
- 新增 `fr_cli.security.security.clear_all_auto_confirm()` 全局撤销（`/unconfirm` 入口）
- `help_detail_security` 中英文档更新（"分级永久放行"说明 + `/unconfirm` 命令）

### 并发：取消 `_agent_ctx_stack` 栈式覆盖
- 移除 `CommandExecutor._agent_ctx_stack` 列表及 push/pop 隐性协议
- `invoke_tool` / `execute` / `process_ai_commands` 全部接受显式 `client` / `model_name` 参数
- `agent/executor.py` (`run_agent` / `delegate_to_agent`) 与 `agent/workflow.py` (`run_workflow` 步骤执行) 改为显式透传 `client` / `model_name`
- 根除 cron Timer / Agent HTTP 服务 / 主循环并发 `push/pop` 错位导致的 LLM 上下文错乱
- 兼容：保留 `push_agent_context` / `pop_agent_context` 接口但实现改为 no-op（仅日志告警），旧代码不会崩溃

### 测试增强
- `tests/test_security.py` 重写为 v2.4.4 新契约：4 个旧测试按 dict 行为更新 + 5 个新测试覆盖 `fconfirm` / `sconfirm` 迁移、`clear_all_auto_confirm`、`按 F 不波及其他类别` 关键回归
- `tests/test_integration_real.py`：`test_real_executor_agent_context` / `test_real_executor_agent_context_in_run_agent` 重写为验证显式传参契约
- `tests/test_model_config.py::TestEdgeCases::test_command_executor_agent_context_override` 重写

## v2.4.3 (2026-06-13)

### Microsoft 365 邮件现代认证
- 新增 `fr_cli/weapon/m365.py`，通过 Microsoft Graph API 收发邮件
- 支持 OAuth2 设备代码流 / 授权码流，完整兼容 MFA
- token 缓存于 `~/.fr_cli/m365.json`，文件权限 `0o600`
- 新增命令：`/m365_config`、`/m365_inbox`、`/m365_read`、`/m365_send`、`/m365_status`、`/m365_logout`
- 新增 `/help m365` 主题帮助与中英文文档
- 依赖：`msal`（已包含在 `fr-cli[cloud]` / `fr-cli[all]` 可选依赖中）

### 架构评审与债务清理
- 删除 `fr_cli/command/handlers/` 整个 dead code 目录（与 `command/registered/` 重复）
- 删除 `fr_cli/agent/coding_helper.py`、`gateway.py`、`acp.py`、`plugin_system.py`、`context_files.py`
- 删除 `fr_cli/agent/builtins/powerful_agent_template.py` 及对应测试
- 删除 `fr_cli/agent/workflow_system/` 整个 dead code 目录及对应测试
- 删除 `fr_cli/agent/image_and_parallel.py` 中的 `ParallelExecutor` / `AsyncParallelExecutor` / `BatchImageGenerator` 及对应测试
- 删除 `fr_cli/main.py:288-368` 重复入口死代码

### RAG 链路简化
- 移除 `cross-encoder` Rerank 阶段与 LLM 最佳片段判定，降低延迟与依赖
- `RAGManager.query` 直接返回 embedding 检索的 top-8 片段，由大模型综合生成并标注来源
- 更新 `AGENTS.md`、`fr_cli/WEAPON.MD` 中 @RAG 说明

### Agent HTTP 服务超时与错误处理
- `POST /agents/<name>/run` 支持请求体 `timeout` 字段，默认 120 秒，最大 600 秒
- `POST /agents/<name>/workflow` 支持请求体 `timeout` 字段，默认 180 秒，最大 600 秒
- 执行超时返回 HTTP 504；执行异常返回 HTTP 500 并附带错误信息
- 超时后尝试取消尚未开始的任务
- 新增 `tests/test_agent_server.py` 覆盖成功、超时、异常、Agent 不存在、未认证场景

### Agent 工作流循环检测与单步超时
- `fr_cli/agent/workflow.py` 新增 `_build_dependency_graph` / `_detect_cycle`，执行前检测 `{{stepN.result}}` / `{{stepN.error}}` 循环依赖
- 步骤 `params` 中的 `timeout` 字段现在真正生效：单步执行超过指定秒数即抛 `WorkflowTimeoutError`
- 重试逻辑修复：每次重试使用参数副本，避免 `pop` 破坏后续重试
- 新增 `tests/test_workflow.py` 覆盖解析、循环检测、单步超时、成功执行

### Token 用量统计与 `/usage` 命令
- 新增 `fr_cli/core/usage.py:UsageTracker`，持久化 LLM 调用到 `~/.fr_cli/usage.json`（权限 0o600）
- `core/chat.py` 在每次 `stream_cnt` 后将 prompt/completion/total tokens 记录到用量统计
- 新增 `/usage [days]` 命令，汇总最近 N 天调用次数、tokens 与预估费用
- 支持在 `config.json` 中配置 `usage_prices` 实现精确费用估算

### 统一 JSON 持久化抽象 JsonStore
- 新增 `fr_cli/core/store.py:JsonStore`，提供原子写、默认回退、文件权限控制、线程安全
- 已迁移：`UsageTracker`（`usage.json`）、`CronManager`（`cron.json`）、`M365MailClient`（`m365.json`）、Agent `config.json`/`progress.json`、`GatekeeperManager`（`daemon/config.json`）
- 新增 `tests/test_json_store.py`、`tests/test_agent_manager_store.py`、`tests/test_gatekeeper_store.py` 覆盖迁移后的读写场景

### Dead Code 清理
- 删除 `fr_cli/agent/a2a.py` 整个 A2A 协议实现（A2AClient / AgentRegistry / A2AServer 等已无外部引用）
- 删除 `tests/test_a2a_and_providers.py` 中所有 A2A 相关测试，保留 StepFun provider 测试
- 更新 `AGENTS.md`、`fr_cli/WEAPON.MD` 移除 A2A 相关内容
- 删除 `fr_cli/agent/image_and_parallel.py` 整文件（ImageModelConfig / ImageGenerator / TerminalImageDisplay 等已无外部引用）
- 删除 `tests/test_new_features.py` 及 `test_no_color_prompt_toolkit.py` 中对应的 dead code 测试
- 更新 `AGENTS.md` 项目结构图

### 统一错误返回风格（试点）
- 新增 `fr_cli/core/result.py:Result` 容器，提供 `ok()` / `fail()` / `unwrap()` / `to_tuple()` / `from_tuple()`
- `weapon/launcher.py` 的 `open_file` / `launch_app` / `list_apps` 改为 `(result, error)` 风格
- 更新 `repl/commands/system.py`、`command/registered/session_config.py` 中对应调用点
- 新增 `tests/test_result.py` 覆盖 Result 基本行为

### 安全加固
- 修复 `disk_up` 参数顺序 bug（local/remote 参数颠倒）
- 修复 `@local` Windows 路径 `shell=True` 回退，彻底禁止 shell 执行
- 修复 `read_excel` / `read_csv` 未走 VFS 沙盒的问题
- 移除 MasterAgent 自动污染 skills / personality 的逻辑与硬编码 token 统计
- 注册表补充 `security` 声明：`set_key`、`set_model`、`set_limit`、`set_lang`、`set_alias`、`mcp_call`、`mail_read`、`m365_read`、`m365_config`、`open_file`、`launch_app`、`agent_create`、`update_run`、`local_llm`
- 更新 `TEST_REPORT.md`、`AGENTS.md`、README 系列文档

## 更新日志 v2.2.8

## 🆕 新增功能

### 1. 文心一言 (ERNIE Bot) 支持
- `ernie`: 文心一言基础版 (ernie-bot-4)
- `ernie-4`: 文心一言 4.0 (ERNIE Bot 4)
- `ernie-turbo`: 文心一言 Turbo 高速版 (ernie-bot-turbo)
- `ernie-8k`: 文心一言 8K 上下文版 (ernie-bot-8k)

**配置方式**：
```bash
# 使用 API Key 和 Secret Key
/providers add ernie <your-api-key> <your-secret-key>

# 切换模型
/model ernie
/model ernie-turbo
```

### 2. Agent2Agent Protocol (A2A)
- Agent 注册与发现机制
- 任务委托和结果返回
- HTTP 服务器支持
- 支持本地和远程 Agent 互操作

### 3. 图片模型和并行执行
- 图片生成：智谱 CogView / MiniMax / 通义万相 / StepFun
- 终端图片显示：ASCII / Braille / Unicode
- 批量图片生成
- 并行任务执行（多线程/异步）
- 多 Agent 并发执行

### 4. Agent 工作流系统
- 工作流引擎（顺序/并行/分支/循环）
- 工作流监控和可视化
- 预置工作流模板：代码审查、数据分析、多 Agent 协作

### 5. 强大 Agent 模板
- 自主思考和规划（Direct/CoT/ToT/ReAct）
- 完整工具系统（10+ 内置工具）
- 记忆管理（短期+长期）
- 自我学习与进化

### 6. MiniMax Token Plan 支持
- `minimax-m27`: M2.7 标准版
- `minimax-m27-fast`: M2.7 高速版
- `minimax-token-plan`: 全模态订阅

### 7. Kimi Code 平台支持
- `kimi-k2`: Kimi K2 代码优化版
- `kimi-code`: Kimi Code 代码平台
- `kimi-code-anthropic`: Anthropic 兼容接口

### 8. StepFun 系列更新
- `step-1`, `step-2`, `step-3`: Step-1/2/3 模型
- `step-audio`: Step-Audio 实时语音

## 🔧 修复

### MasterPrompt JSON 格式化问题
- 修复 JSON 花括号未转义导致的 KeyError: '"tool"'
- 所有 JSON 代码块中的 `{` 和 `}` 已正确转义为 `{{` 和 `}}`

## 📦 支持的模型（30+）

| 提供商 | Provider ID | 默认模型 |
|--------|-------------|---------|
| 智谱 | zhipu | glm-4-flash |
| 智谱 Coding | zhipu-coding | GLM-4.7 |
| 文心一言 | ernie | ernie-bot-4 |
| 文心 Turbo | ernie-turbo | ernie-bot-turbo |
| DeepSeek | deepseek | deepseek-chat |
| Kimi | kimi | moonshot-v1-8k |
| Kimi K2 | kimi-k2 | kimi-k2-0905-preview |
| Kimi Code | kimi-code | kimi-for-coding |
| 通义千问 | qwen | qwen-turbo |
| 阶跃星辰 | stepfun | step-1-8k |
| Step-3 | step-3 | step-3-auto |
| MiniMax | minimax | MiniMax-Text-01 |
| MiniMax M2.7 | minimax-m27 | MiniMax-M2.7 |
| 讯飞星火 | spark | generalv3.5 |
| 豆包 | doubao | doubao-1-5-pro-32k |
| 小米 | mimo | mimo-v2-flash |
| LongCat | longcat | LongCat-Flash-Chat |

## 🧪 测试

- 100+ 测试用例全部通过
- 新增测试文件：
  - `test_a2a_and_providers.py`
  - `test_new_features.py`

## 📚 文档

- README.md 更新（30+ 模型支持）
- WEAPON.MD 更新（A2A 协议、模型提供商）
- i18n.py 更新（中英文帮助信息）
- NEW_PROVIDERS_GUIDE.md（模型使用指南）
- A2A_AND_PROVIDERS_GUIDE.md（A2A 协议文档）

---

**版本**: v2.2.8  
**日期**: 2025-04-28
