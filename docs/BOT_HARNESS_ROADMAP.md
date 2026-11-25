# fr-cli → Bot / Agent Harness 改造路线图

> 版本：2026-11-24
> 范围：基于 fr-cli v2.8.6（47k 行 Python，303 个源文件，2044 个测试用例）代码实测盘点
> 性质：只读分析，未修改任何源码。所有结论均带 `文件:行号` 证据。

---

## 0. 实施状态（本轮已落地）

> 本节记录 **2026-11-24 已完成的实现**，下文第 1~7 节是当时的盘与计划，
> 保留作为设计依据与后续路线的对照。

### 决策

| 决策点 | 选择 |
|---|---|
| bot 形态 | **统一适配层** —— 先抽象 `Channel` 接口，再逐个接平台 |
| harness 重点 | **可扩展性** —— 工具 / 子 Agent 动态注册、MCP 全面接入 |
| 交付形态 | **完整实现**（多阶段落地） |

### 已落地清单

**阶段 0 —— 地基**

| 项 | 状态 | 落地位置 |
|---|---|---|
| 统一 tool-call 协议层 | ✅ | `fr_cli/core/tool_protocol.py`（新建）；`command/executor_parse.py`、`agent/master_loop.py` 改为委托 |
| 可注入确认策略 | ✅ | `fr_cli/security/strategy.py`（新建）；`command/security.py::SecurityManager.set_strategy()` |
| 无头模式 | ✅ | `core/headless.py`（新建）；`core/chat/pipeline*.py`、`agent/artifact_detector.py`、`repl/router.py` |
| 回复正文回传 | ✅ | `state.last_reply`（`core/app_state_core.py`） |
| 会话隔离 | ✅ | `bot/core/session_store.py`（新建），按 `session_key` 隔离，**不写全局 `context.summaries`** |
| 消息并发安全 | ✅ | `AppState.get_messages()` / `set_messages()` / `append_message()` / `message_lock()` |
| 用量计量并发安全 | ✅ | `core/usage.py` 加锁 + 批量延迟落盘（原先自称线程安全却无锁） |

**阶段 1 —— Harness 硬化 / 可扩展性**

| 项 | 状态 | 落地位置 |
|---|---|---|
| 工具 JSON Schema 导出 | ✅ | `fr_cli/command/schema.py`（新建），`export_schemas()` 实测导出 149 个工具 |
| 参数类型校验 | ✅ | `command/schema.py::validate_params`（宽容转换 + 类型校验），接入 `registry.dispatch()` |
| per-tool 权限层接入 | ✅ | `security/permissions.py::check_tool_permission` → `command/security.py::permission_decision` → `registry.dispatch()`。**复活了此前零调用点的死代码** |
| 子 Agent 统一注册表 | ✅ | `fr_cli/agent/registry.py`（新建），本地 / 远程 / 内置 / 动态统一视图；已接入 `/agent_list` |
| MCP schema 注入 | ✅ | `core/chat/helpers.py::fetch_mcp_desc` 输出完整参数 schema；**顺带修掉一处隐藏死代码**（原读 `srv.tools`，而 `MCPServer` 根本没这个字段 → 真实 manager 恒返回空） |
| MCP 调用超时 | ✅ | `weapon/mcp/manager_invocation.py`，`asyncio.wait_for` 包裹 |
| MCP 跨线程安全 | ✅ | `call_tool_sync` 在已有 running loop 的线程里改走新线程，不再抛 RuntimeError |
| MCP 工具缓存 | ✅ | `weapon/mcp/manager_tools.py`，TTL 300s + `invalidate_cache()` |
| MCP 接入统一注册表 | ✅ | `command/registered/mcp_tools.py`（新建），`mcp_<server>_<tool>` 作为普通工具注册 |
| MCP 发现不阻塞启动 | ✅ | `core/app_state_core.py` 改为后台线程预热（同步发现会拖慢启动与每轮 prompt 组装） |
| 注册表并发安全 | ✅ | `command/registry.py` 加锁 + 遍历前取快照 |

### 安全加固（P0-1，第二轮）

| 项 | 状态 | 落地位置 |
|---|---|---|
| 动态工具子进程隔离 | ✅ | `dynamic_builder/sandbox.py`（新建，父进程侧）+ `dynamic_builder/sandbox_worker.py`（新建，子进程侧）；`registry_manager.py` 移除 `exec()`，改为注册调用沙箱的 handler |
| 静态 AST 校验 | ✅ | `sandbox.py::validate_dynamic_code` —— 禁导入 `os`/`sys`/`subprocess`/`socket`/`requests`/`pathlib`/`pickle`/`fr_cli` 等；禁内置 `open`/`eval`/`exec`/`compile`/`input`；禁 `__class__`/`__globals__`/`__subclasses__` 等 dunder |
| 运行时 import 守卫 | ✅ | `sandbox_worker.py::_restricted_builtins` —— 受限 builtins 字典（`open` 直接不存在）+ `__import__` 守卫；放行模块夹带的黑名单属性被清洗（如 `logging.os`） |
| 凭证隔离 | ✅ | `sandbox.py::_scrub` —— `deps.cfg` 传脱敏副本（api key / secret / token / password → `***`） |
| 能力 RPC 回代理 | ✅ | `sandbox.py::_SandboxHost` + `sandbox_worker.py::_RpcProxy` —— `web_c`/`mail_c`/`disk_c`/`client`/`mcp` 回父进程执行，按 `sec_*` 走真实确认 |
| 超时与资源限额 | ✅ | 默认 30s（`meta["timeout"]` 可调），超时杀进程组；子进程内 `RLIMIT_CPU`/`RLIMIT_AS`/`RLIMIT_FSIZE`/`RLIMIT_NPROC` |
| 动态工具 `sec_exec` 确认 | ✅ | `registry_manager.py::register_dynamic_tool` 注册时 `security="sec_exec"` |
| 代码生成 prompt 引导 | ✅ | `code_generator.py` 增加「沙箱限制」章节 —— 引导模型用 `deps.vfs` / `deps.web_c` |

**阶段 2 —— Bot 接入**

| 项 | 状态 | 落地位置 |
|---|---|---|
| 通道抽象 | ✅ | `bot/core/channel.py`（新建）—— 新增平台只需实现 `verify` / `parse` / `send` 三个方法 |
| 统一消息模型 | ✅ | `bot/core/message.py`（新建）—— `BotMessage` / `BotReply` |
| 路由（@ 判定 / 群白名单） | ✅ | `bot/core/router.py`（新建） |
| 消息幂等去重 | ✅ | `bot/core/idempotency.py`（新建） |
| 会话隔离存储 | ✅ | `bot/core/session_store.py`（新建） |
| 聊天窗口确认 | ✅ | `bot/core/confirm.py` + `bot/core/confirm_broker.py`（新建）—— Y/A/F/N 搬到 IM，超时按拒绝 |
| 状态池 | ✅ | `bot/core/state_pool.py`（新建）—— 多会话安全共享运行时 |
| 调度器 | ✅ | `bot/core/dispatcher.py`（新建） |
| HTTP 网关 | ✅ | `bot/runtime/gateway.py`（新建）—— 统一接收平台 webhook，立即 ack + 异步处理 |
| 引擎 / 守护进程 / 进程管理 | ✅ | `bot/runtime/engine.py`、`daemon.py`、`manager.py`（新建） |
| 首批平台 | ✅ | `bot/channels/generic.py`、`lark.py`、`telegram.py`（新建） |
| REPL 命令 | ✅ | `command/registered/bot.py`（新建）—— `/bot_start` `/bot_stop` `/bot_status` `/bot_config` `/bot_channels` |

### 第四轮（2026-11-25）—— UX / 显示层欠账收口

> 这一轮把"清单上挂着、实际没做"的项清干净。逐条核实代码后发现：
> `core/optimizations.py` 里标着"未实现"的三条长线 TODO，**有两条本身是过时信息**。

| 项 | 状态 | 落地位置 / 结论 |
|---|---|---|
| P2-1 token 三处口径统一 | ✅ 本轮 | `core/usage.py::format_token_usage` 成为唯一真相源；状态栏与回答末尾同一格式、同一分母；删掉 `tokens_used/limit` 死分支（该字段全仓无人写入） |
| P2-2 多行粘贴降级 | ✅ 本轮 | 新增 `repl/paste.py` 的 `/paste`（读到 EOF 整段作为一条消息）。**诚实边界**：现代终端靠 bracketed paste 本就正常，`/paste` 是给不支持该协议的终端兜底 |
| P2-3 未知命令模糊建议 | ✅ 本轮 | `repl/router.py::_cmd_similarity` —— 编辑距离 + 子序列 + 前缀，最多 5 条（此前固定 3 条且不认子序列） |
| 长线-3 并行工具调用 | ✅ 本轮补齐 | 并发执行器早就存在，但只接在文本标记路径；**原生 function calling 多 tool_calls 仍是串行** → 已并发（结果按序回填）。另修：并行下安全确认会抢终端 → 全局确认锁 |
| 长线-4 消息分块持久化 | ✅ 本轮接线 | 增量写入器（`memory/incremental.py`）**早就写好但只有它自己的测试在用**；生产路径仍每轮全量重写 → 已接线，并补 v1→v2 迁移、链式哈希校验（原地改写/截断 → 全量重写） |
| 长线-5 RAG 检索缓存 | ⚠️ **早已实现** | `agent/builtins/rag_cache.py`（TTL 600s + 磁盘持久化）**已接线**到 `rag_query.py`；此前那条 TODO 是过时信息，已更正 |

顺带修掉的既有缺陷：`tests/test_security.py` 环境变量泄漏（`os.environ[...] =` 不会被回滚，把后续用例的确认流程变成"一律放行"）、`tests/test_dataframe.py` 未导入的 `MagicMock`（被 skipif 掩盖，装了 pandas 就崩）、测试目录 19 处 lint、USAGE.md 的 `Shift+Enter` 漂移（实际是 `Esc+Enter`）、README 的"745+ 用例"（实际 2563）。

### 测试

新增 5 个测试文件，共 **108 个用例**：

| 文件 | 覆盖 |
|---|---|
| `tests/test_tool_protocol.py` | 三级参数回退、全格式提取、去重、**两条历史路径行为一致性** |
| `tests/test_security_strategy.py` | 四种策略的契约、fail-closed 语义、SecurityManager 集成 |
| `tests/test_bot_core.py` | 消息模型 / 路由 / 去重 / 会话隔离 / 确认代理 / 状态池 / 调度器 |
| `tests/test_bot_gateway.py` | 网关端到端（入站 → 验签 → 解析 → 调度 → 回复） |
| `tests/test_bot_integration.py` | 真实 generic 通道 + 真实调度器 + 真实网关的完整闭环 |
| `tests/test_dynamic_sandbox.py` | 静态校验 / 子进程隔离 / 参数传递 / 超时终止 / 异常隔离 / import 守卫 / 凭证脱敏 / VFS 路径沙盒 / RPC 代理 / 注册表接入（81 个用例） |
| `tests/test_display_ux.py` | 显示层（颜色活引用 / 语法高亮 / 折叠 + Ctrl+O / 状态栏分栏 / @ 补全 / 上手卡片） |
| `tests/test_ux_backlog.py` | 本轮欠账（token 口径 / `/paste` / 模糊建议 / 原生 FC 并行 / 确认互斥 / 增量持久化） |

### 本轮修掉的真实缺陷

| 缺陷 | 位置 | 影响 |
|---|---|---|
| 两条 tool-call 解析路径容错不一致 | `command/executor_parse.py` vs `agent/master_loop.py` | 同一段 AI 文本在 ReAct 路径被**静默丢弃**，工具从未执行 |
| 宽松解析匹配不到无引号 key | `core/tool_protocol.py` | `{path: /a.txt}` 这类参数解析失败 |
| per-tool 权限层是死代码 | `security/permissions.py` | 用户写在 config 里的权限规则**永远不生效** |
| `fetch_mcp_desc` 读不存在的字段 | `core/chat/helpers.py` | 真实 MCP manager **恒返回空**，模型拿不到任何 MCP 工具 |
| `UsageTracker` 自称线程安全却无锁 | `core/usage.py` | 并发调用丢记录 + 每次全量重写 10 万条 JSON |
| `state.messages` 读-改-写无锁 | `core/app_state_core.py` | 4 个写点 + 后台 worker → 多用户场景消息交错 |
| 产物检测在 `_post_process` 里无条件 `input()` | `agent/artifact_detector.py` | bot 里**必然挂死**（AI 回复含 `def run(...)` 代码块即触发） |
| 状态池归还状态时自锁死 | `bot/core/state_pool.py` | Condition 底层用了非重入 Lock（本次由新测试捕获） |
| 飞书验签拿不到原始 body | `bot/runtime/gateway.py` | 平台侧签名对不上，验签必然失败 |
| `/bot_start` 在网关监听前就返回 | `bot/runtime/manager.py` | 调用方立刻发请求会连接被拒 |
| 僵尸进程被误判为"还活着" | `bot/runtime/manager.py` | 停止流程一路走到 SIGKILL，还留下僵尸 |
| `~/.ssh` 路径未 resolve | `weapon/remote.py` | macOS 上 `/var` 是符号链接 → 合法 SSH 密钥被误拒 |
| 测试污染真实 `~/.fr_cli/` | `tests/conftest.py`（新建） | 跑一次测试就写垃圾 cron、清空 providers |
| `build_tool` 规划失败返回元组 | `dynamic_builder/runner.py` | `return False, "..."` 而调用方调 `result.is_ok()` → `AttributeError` 崩溃 |
| 推理模型思考过程被当成代码 | `dynamic_builder/code_generator.py::_clean_code_markers` | `core/llm/base.py` 在 content 为空时回退 `reasoning_content` → 散文进 `exec()` → `/build` 对 stepfun/glm 等推理模型**完全不可用** |
| 代码生成 token 上限偏小 | `dynamic_builder/code_generator.py` | `max_tokens=2048` 被思考吃光，代码被截断 |

### 剩余缺口（本轮**未**实现，按风险排序）

> 这些是原路线图里仍然开着的项。**已核实当前代码状态**。
>
> **第三轮（P0-2 / P0-3 / P1-1~P1-14 / P2-1~P2-9）后**：下面三张表里的项已全部落地或明确关闭，
> 详见每行的「现状」列。

#### 🔴 P0 —— 安全 / 可靠性硬伤

| 项 | 位置 | 现状 |
|---|---|---|
| ~~**`/build` 动态工具无隔离**~~ | `dynamic_builder/` | ✅ **第二轮已修** —— 见上方「安全加固（P0-1，第二轮）」。父进程授权 + 子进程执行 + 能力 RPC 回代理 + 超时 + rlimit + 凭证脱敏 |
| ~~**LLM 调用无重试 / 无降级**~~ | `core/llm/resilience.py` + `core/stream.py` | ✅ **第三轮已修** —— 错误三分（瞬时/认证/致命）+ 指数退避重试 + 主模型挂了降级到备用 provider；`timeout` 从 `llm_timeout` 配置读。重试仅在未产出内容时进行；**降级不改变用户的 `/model` 选择**；失败原因如实带回 |
| ~~**无原生 function calling**~~ | `core/llm/function_calling.py` | ✅ **第三轮已修** —— `stream_chat` 支持 `tools` / `tool_choice`，流式分片按 index 归并，工具结果以 `role="tool"` 回填跑第二轮。provider 不支持/拒绝时自动退回文本标记路径（anthropic / 文心协议不同，暂走文本路径） |

#### 🟠 P1 —— 可运营性

| 项 | 位置 | 现状 |
|---|---|---|
| ~~**swarm timeout 是假能力**~~ | `agent/swarm.py` | ✅ **第三轮已修** —— 改用 `concurrent.futures.wait(timeout=)` 做真整体 deadline；超时条目带真实任务名，按**部分失败**语义返回 |
| ~~**10 个事件零派发**~~ | `core/events.py` | ✅ **第三轮已修** —— 建立 `ALL_V2_EVENTS` 事件名清单 + 派发自检（拼错事件名会告警），补齐 `command.executed` / `session.created` / `session.saved` / `app.stopped` / `error.occurred` 派发点；`llm.*` 事件下沉到 `stream_cnt`（唯一漏斗） |
| ~~**无 `/metrics` 命令**~~ | `repl/commands/config/metrics.py` | ✅ **第三轮已修** —— `/metrics` / `/metrics json` / `/metrics prom` |
| ~~**中文 token 估算低估 ~4 倍**~~ | `memory/compress.py` | ✅ **第三轮已修** —— CJK / 西文分别计权 + 安全系数；`estimate_tokens` 签名与语义不变 |
| ~~**无 trace / span**~~ | `core/trace.py` | ✅ **第三轮已修** —— `trace_id` / `span_id` / `parent_span_id`，工具调用自动埋点，JSONL 落盘可选 |
| ~~**`shell=True` 残留**~~ | `weapon/launcher.py` / `agent/shell_mode.py` | ✅ **第三轮已修（launcher）/ 明确关闭（shell_mode）** —— launcher 消除全部 `shell=True`；`agent/shell_mode.py` 的命令**只来自用户手输**（注册表里的 `shell` 工具只是桩，无 LLM 路径可达），且 `!ls \| grep x` 正是该功能本身 —— 保留并写明依据 |
| ~~**workflow DAG 并行未实现**~~ | `agent/workflow.py` | ✅ **第三轮已修** —— 按依赖图分层，同层并行（仅纯 LLM 补全层并行，碰 `state.executor` 的层保守串行）；失败保留部分结果 |
| ~~**MasterAgent 落盘非原子**~~ | `agent/master_storage.py` | ✅ **第三轮已修** —— tmp + fsync + `os.replace` |
| ~~**agent/server.py 单线程**~~ | `agent/server.py` | ✅ **第三轮已修** —— 换 `ThreadingHTTPServer`；同时修掉 `_run_with_timeout` 的阻塞退出（超时名不副实） |
| ~~**上下文压缩信息不可逆丢失**~~ | `memory/compress.py` | ✅ **第三轮已修** —— 早期对话切最多 3 段**分层摘要**，标注覆盖区间；单段失败保留原文片段，全失败才退化为截断 |
| ~~**MasterAgent 无死循环检测**~~ | `agent/master_loop.py` | ✅ **第三轮已修** —— 同一 tool+params 累计成功 N 次即收尾 + 单步失败重试 + `MAX_STEPS` 从 config 读 |

#### 🟡 P2 —— 既有缺陷 / 工程质量

| 项 | 位置 | 现状 |
|---|---|---|
| ~~**Web 控制台静态资源 404**~~ | `web/console/handler.py` | ✅ **第三轮已修** —— 静态资源路径指向实际目录；`pyproject.toml` / `MANIFEST.in` 收录 `web/static/*` |
| ~~**Hermes GET 端点免鉴权**~~ | `agent/hermes_api.py` | ✅ **第三轮已修** —— 走统一鉴权，默认要求 Bearer token；保留可配置的公开只读端点 |
| ~~**`/api/command` 被硬禁用**~~ | `web/console/handler.py` | ✅ **第三轮已定论** —— **默认仍关闭**，但给了依据与放开条件：需要独立高权限 token + 命令白名单 + 强制非交互（handler 是工厂闭包，拿不到 AppState；命令会走到 `input()` 抢终端 stdin） |
| ~~**HTTP 三套各自实现**~~ | `web/http_base.py` | ✅ **第三轮已修** —— 公共基类：`ThreadingHTTPServer` + 可插拔响应包裹策略（`result_error` / `ok_data` / `flat`，**默认沿用各服务现值**）+ 统一鉴权 + 统一异常处理 |
| ~~**无 eval 体系**~~ | `tests/evals/` | ✅ **第三轮已修** —— 最小 agent 任务集 + 四个指标（工具选择正确率 / 参数正确率 / 多步完成率 / 越权拦截率）+ 离线评分脚本 + 录制回放；完全离线，不需要 API key |
| ~~**4 个既有测试失败**~~ | `tests/test_output_consistency.py` / `test_start_wizard.py` | ✅ **第三轮已修** —— 根因是 `fr_cli/ui/ui.py` 在 import 时 `set_no_color(_NO_COLOR)` 把颜色常量清空（非 TTY），断言 ANSI 码的用例在 CI 里必然失败。测试改为显式恢复常量 + 强制判定，而不是依赖环境碰运气 |

> **第二轮（P0-1）后的失败集合**：`{test_error_messages::test_scan_failure_uses_friendly_print,
> test_output_consistency::test_success_includes_check_mark, test_start_wizard::test_main_flow_uses_output_api}`。
> 再次用 pristine HEAD worktree 对照：这 3 个用例在**纯净 HEAD 上单独跑同样失败**
> （`test_output_consistency` / `test_start_wizard` 断言依赖 ANSI 色彩，在非 TTY 环境下必然失败；
> `test_error_messages` 单独跑通过、全量跑失败 = 顺序污染）。**与本轮改动无关。**
>
> **第三轮**：这 3 个已全部修好 —— 根因（import 时清空颜色常量）一并修掉，
> `test_hermes_demo` / `test_hermes_subtasks` 的 mock 也补了 `**kwargs`
> （`stream_cnt` 新增 `provider` / `timeout` / `tools` 等关键字参数后，固定签名的 mock 会被打成 TypeError）。

---

## 0.1 原始结论摘要

fr-cli 现在是**一个功能丰富的终端应用**，不是**一个为可靠性设计的 Agent Harness**，更不是**一个 bot**。

三个结论：

1. **Bot 化缺的不是功能，是入口。** 六个 IM 平台全是单向出站 webhook（`fr_cli/weapon/notifier.py:7,114-294`，模块自述"fr-cli 不接收消息，只推送通知"）。入站消息接收、会话映射、@ 判定、消息去重这一整套**完全不存在**。已有的三套 HTTP 服务（Agent / Hermes / Web Console）各自实现鉴权、各自 `http.server`，没有一个能接收"一句话"并返回"一段回复"。

2. **Harness 化的瓶颈不在能力，在契约。** 十个维度里八个是"半成品"，两个是"可用"，**没有一个是"成熟"**。共同根因只有一条：**同一件事有多条实现路径且各自独立演进** —— 传统对话 vs MasterAgent、`command/executor.py` vs `agent/master_loop.py`、`agent/swarm.py` vs `agent/workflow.py`。行为契约没有单一真相源，于是每个缺陷都要修 N 遍，且修完还会漂移。

3. **两件事必须先合并成一条路。** Bot 需要一条**确定的、可无头运行的**执行路径；Harness 需要一条**统一的**执行路径。这正是同一件事。所以顺序是：**先统一执行路径（收敛为单一 harness 内核），再在上面挂 bot 适配层**。反过来做（先写 bot 适配层去迁就现有四条路径）会把 N 倍的债固化进 bot 代码里。

---

## 1. Bot 侧现状盘点

### 1.1 入站通道：零

| 平台 | 出站 | 入站 | 证据 |
|---|---|---|---|
| 飞书 / 钉钉 / 企微 / Slack / Discord / Telegram | ✅ | ❌ | `fr_cli/weapon/notifier.py:114-294` |
| 邮件（IMAP / Graph） | ✅ | ❌ 仅一次性拉取 | `fr_cli/weapon/mail.py:75-121`（`inbox()` 只取最近 10 封）、`fr_cli/weapon/m365.py:92-166` |
| 微信 | ❌ | ❌ | 无任何实现 |
| MCP | ✅ client | ❌ 无 server | `fr_cli/weapon/mcp/models.py:25-40`（仅 stdio/http/sse 三种 client transport） |

关键缺口：

- **无消息领域模型**：全仓无 `chat_id` / `group_id` / `user_id` / `mentions` 实体。
- **无"是否在叫我"路由**：无 @ 判定、无群白名单、无按 sender 分区的上下文。
- **无消息去重 / 幂等**：`PersistentTaskManager` 只有任务 id，无消息 id 语义（`fr_cli/agent/hermes/managers.py:52-87`）。

### 1.2 已有的三套服务端底座（可复用，但各写各的）

| 服务 | 入口 | 鉴权 | 流式 | 会话隔离 | 并发 |
|---|---|---|---|---|---|
| Agent HTTP | `fr_cli/agent/server.py:252` | Bearer（`:33-41`）+ IP 白名单（`:43-49`）+ CORS（`:51-61`） | ❌ | ❌ 全局单 AppState（`:282`） | ❌ **单线程** `HTTPServer`（`:281`） |
| Hermes API | `fr_cli/agent/hermes_api.py:62` | Bearer（写操作，`secrets.compare_digest` `:90`）；**所有 GET 端点免鉴权**（`:106-201`） | ❌ | ❌ | ✅ |
| Web Console | `fr_cli/web/console/lifecycle.py:44` | Bearer + `?token=`（`handler.py:148-157`） | ✅ SSE（`handler.py:49-95`） | ❌ | ✅ `ThreadingHTTPServer`（`:74`） |

三套各自实现 Bearer 校验，无公共基类 —— 应抽 `fr_cli/core/http/base.py`。

### 1.3 最接近 bot 的两条链路，各差一环

**链路 A —— Hermes `POST /chat`（拉取式，差"推回"）**

```
POST /chat (hermes_api.py:307)
  → PersistentTaskManager 落盘 (managers.py:29-50)
  → HermesScheduler 5s 轮询 (scheduler.py:13,26-41)
  → master_agent.handle(..., background=True) (engine_execution.py:86-93)
  → task.result (engine_execution.py:94)
  → GET /tasks/<id> 取回 (hermes_api.py:137-146)
```
✅ 全链路已通 ❌ 结果要客户端轮询取回，用户侧体验不是 bot。

**链路 B —— Web Console SSE（推送式，差"入站"）**

```
POST /api/event (handler.py:210-216)
  → push_event (events.py:26-48)
  → SSE 广播 (handler.py:49-95)
```
✅ 完整推送管道 ❌ `/api/command` 被**硬性禁用**返回 403「Web 命令未启用(安全考虑)」（`handler.py:207-209`）—— "Web → AI"这条路是堵死的。

### 1.4 顺带发现的现成 bug（改造前应先修）

| 问题 | 证据 |
|---|---|
| Web Console 静态资源路径写错 → PWA 三件套实际 404 | handler 取 `console/static/`（`handler.py:129`），真实文件在 `fr_cli/web/static/`；`pyproject.toml` 的 `package-data` 也未收录 `web/static` |
| Hermes GET 端点全免鉴权 | `hermes_api.py:106-201` |
| 企微签名收了 `secret` 但完全没用 | `fr_cli/weapon/notifier.py:210-234` |
| `TEST_REPORT.md` 记录 357 passed，实际 2044 | `TEST_REPORT.md:8-11` |

---

## 2. Harness 侧成熟度矩阵

| 维度 | 等级 | 一句话理由 | 关键证据 |
|---|---|---|---|
| 工具调用协议 | 半成品 | 纯文本标记解析（容错扎实），但无原生 function calling，且两条解析路径容错强度不一致 | `command/executor_parse.py:108`、`core/llm/base.py:15-21`、`agent/master_loop.py:290-294` |
| 上下文与记忆 | 半成品 | 有阈值压缩 + 摘要持久化 + 会话续接，但 token 估算对中文低估 4 倍，压缩有损不可逆 | `memory/compress.py:48-54`、`core/chat/helpers.py:26`、`agent/master_reflect.py:79` |
| 多步循环与终止 | 半成品 | 步数上限 / 终止 / 反思进化齐备，但无死循环检测，单步 LLM 失败零重试且静默返回空答案 | `agent/master_loop.py:45,139,150-155`、`core/stream.py:286-294` |
| 编排能力 | 半成品 | 三模式 + 依赖图 + 环检测齐全，但 swarm timeout 失效、DAG 并行未实现 | `agent/swarm.py:109-115`、`agent/workflow.py:243` |
| 权限与沙箱 | 半成品 | 文件路径沙盒扎实、四阶确认细致，但 per-tool 权限是死代码、shell 走 `shell=True`、动态工具 `exec` 无隔离 | `weapon/fs.py:27-42`、`security/permissions.py:39`、`agent/shell_mode.py:32`、`dynamic_builder/registry_manager.py:179` |
| 观测与计量 | 半成品 | 指标 / 用量 / 错误账本三件套完整且线程安全，但只覆盖主对话路径，10 个事件是死代码，无 trace | `core/metrics/hooks.py:16-96`、`core/usage.py:70`、`core/events.py:36-77`、`core/errors.py:22-29` |
| 错误处理与韧性 | 半成品 | Result 统一 + 错误账本 + Hermes 指数退避重试，但模型调用层无重试 / 无降级 / 超时硬编码 | `core/result.py:22`、`core/stream.py:258,286-294`、`command/registry.py:92` |
| 可复现与测试 | 可用 | 2044 用例 + 4×2 CI 矩阵 + 真实故障回归测试，但无 eval、无快照基线、无录制回放、无 conftest | `.github/workflows/tests.yml:16-41`、`tests/test_toolcall_extraction.py:1-95` |
| 扩展机制 | 可用 | 插件 / MCP / 动态构建三条路径 + 统一注册表，但隔离强度差异极大（subprocess > MCP > 无隔离 exec） | `addon/plugin.py:58-61`、`weapon/mcp/manager_invocation.py:96`、`dynamic_builder/registry_manager.py:179` |
| 并发模型 | 半成品 | JsonStore / metrics / ledger / 事件总线均线程安全，但 `AppState.messages`、`UsageTracker`、注册表 dict 三处无锁 | `core/store.py:34`、`core/app_state_core.py:101`、`core/usage.py`（无 threading）、`command/registry.py:30-31` |

**没有任何维度达到"成熟"。** 维度 8/9 达到"可用"是因为它们解决的是"功能是否存在"而非"行为是否可预测"。

---

## 3. 核心洞察：为什么"半成品"这么多

不是作者写得不用心，是**架构决定的**。三条根因：

### 3.1 同一件事有 N 条实现路径

| 职责 | 实现 A | 实现 B | 实现 C |
|---|---|---|---|
| 工具调用解析 | `command/executor_parse.py`（三级回退） | `agent/master_loop.py:248-297`（**只有 `json.loads`**） | `core/plan/toolcalls.py`（四层容错） |
| 上下文压缩 | `memory/compress.py` | `agent/master_reflect.py:75-96`（**实际被短路成死代码**） | — |
| 多步编排 | `agent/master_loop.py`（ReAct，8 步） | `agent/swarm.py`（三模式） | `agent/workflow.py`（DAG 串行） |
| 服务端底座 | `agent/server.py` | `agent/hermes_api.py` | `web/console/handler.py` |

**已经造成实伤**：同一段 AI 文本，在传统对话路径能被 `_loose_parse_kwargs` 兜底解析出来，在 ReAct 路径会被**静默丢弃** —— 用户看到"AI 好像想调工具但什么都没发生"。`tests/test_toolcall_extraction.py:1-95` 固化的正是这个 live 实测问题。

### 3.2 契约写在提示词里，不在代码里

工具 schema 以**纯文本**注入 system prompt（`core/chat/pipeline_intent.py:83` → `:74`），LLM 客户端层**完全不透传 `tools`**（`core/llm/base.py:15-21`；`zhipu.py:15`、`openai_compat.py:21` 只传 model/messages/stream/max_tokens/timeout）。这意味着：

- 模型输出格式一偏，工具就静默不执行，且**没有任何机制把错误反馈给模型让它自纠正**（`command/executor_ai.py:131-134` 只写一行 `[x] 参数解析失败`）。
- 无法用模型的原生约束保证参数合法，注册表的 `params` 只做**键存在性**检查、不做类型校验（`command/registry.py:74-77`）。

### 3.3 已写好的能力没接线

`fr_cli/security/permissions.py:39-77` 的 `PermissionManager.check_tool` 完整实现了 `always_allow` / `always_deny` / `ask_each_time` + path_rules（glob 与 `re:` 正则，`:79-118`），**有独立测试 `tests/test_permissions.py`**，但**全仓无任何生产调用点** —— `command/registry.py:68-92` 的 `dispatch` 只查 `tool["security"]` 这一个 sec_* 级别。用户写在 config 里的 `permissions` 规则**永远不生效**。

同类的"死代码"还有：`core/events.py:36-77` 声明的 10 个事件（`session.created` / `command.executed` / `usage.recorded` / `error.occurred` / `llm.chunk` …）**零派发点**，导致对应 metrics 钩子（`core/metrics/hooks.py:72-90`）恒为 0 —— **监控面板给的是假零**。

---

## 4. Harness 改造清单

> **第三轮收口**：本节 P0 / P1 / P2 的全部条目均已落地（✅）或已明确关闭（⚠️）。
> 落地位置见上文「剩余缺口」三张表的「现状」列，以及 `CHANGELOG.md` 的 `[Unreleased]` 段。
> 唯一标注 ⚠️ 的是 **P1-13**：`weapon/launcher.py` 已消除全部 `shell=True`；
> `agent/shell_mode.py` **刻意保留** `shell=True` —— 命令来源只有用户手输
> （注册表里的 `shell` 工具只是桩，无 LLM 路径可达），且 `!ls | grep x` 正是这个功能本身。

### P0 —— 不做这些，"生产级"不成立

| # | 改哪里 | 做什么 | 为什么 |
|---|---|---|---|
| ✅ **P0-1** | `core/llm/base.py:15-21` + `zhipu.py:15` + `openai_compat.py:21` + `anthropic_compat.py` | `stream_chat` 增加 `tools` / `tool_choice` 透传；新增非流式 `chat_with_tools()` 返回结构化 `tool_calls` | 工具调用靠模型复述文本标记，是 harness 与模型的**契约根基**。这是最高优先级 |
| ✅ **P0-2** | 新建 `core/tool_protocol.py`；改 `command/executor_parse.py:108` + `agent/master_loop.py:248` | 把两条解析路径合并为**唯一**归一化层，统一复用 `core/plan/toolcalls.py:18` 的 `_normalize_tool_call`（含 `_loose_parse_kwargs` 兜底） | 消除"同一段文本两条路径行为不一致"。**bot 场景必须踩过这个坑**——bot 只会走一条路径 |
| ✅ **P0-3** | `command/registry.py:68-92` | `dispatch` 中接入 `security/permissions.py:39` 的 `PermissionManager.check_tool`，并把实例注入 `deps` | 现成的精细化权限层是死代码，配置写了不生效 —— 这是"配置即契约"的直接违约 |
| ✅ **P0-4** | `dynamic_builder/registry_manager.py:176-200` + `runner.py:140-142` | 动态工具改子进程执行（复用 `addon/plugin.py:58` 模式：独立进程 + 超时 + stdio 传参），或至少加 `resource.setrlimit` + AST 白名单；自测不得 `skip_security=True` | `exec(code, module.__dict__)`（`:179`）让 **LLM 生成的代码在主进程无限制运行**。这是 prompt injection → RCE 的直通路，**所有缺口里风险最高的一条** |
| ✅ **P0-5** | `core/stream.py:243-294` + `:258` | LLM 调用加**重试 + 指数退避 + 错误分类**（429 / 5xx / 超时分开处理），失败向上抛而非返回空字符串；`timeout` 从 config 读，去掉写死的 60 | 任何 LLM 异常被吞掉返回空文本（`:286-294`），MasterAgent 会把它当"最终答案"（`master_loop.py:154`）→ 用户看到**空回复而非错误**。timeout 写死导致配置层的 timeout 设置完全无效 |
| ✅ **P0-6** | `core/usage.py` + `agent/master_loop.py:144` | `UsageTracker` 加锁 + 批量落盘（现在每次全量重写 10 万条 JSON，且**声称线程安全却无 `import threading`**）；把事件派发下沉进 `core/stream.py`，覆盖 MasterAgent 路径 | MasterAgent 的 LLM 调用**既不进 metrics 也不进 usage.json**（`record_usage` 仅在 `pipeline_respond.py:77,169`）。成本不可见 = 生产不可用 |
| ✅ **P0-7** | `agent/swarm.py:109-115` | 修 timeout 语义：`as_completed(futures, timeout=...)` + `future.cancel()` + 显式上报"超时"状态；pipeline 模式补 timeout 与部分结果保留 | 现在的 TimeoutError 分支（`:114`）**几乎不可达**，超时不生效、不取消、不上报 —— 是**假能力，比没有更危险** |
| ✅ **P0-8** | `security/security.py:25-88` + `command/security.py:54-81` | 把四阶确认从"终端 input()"抽象为**可注入的确认策略对象**；`full_auto` 收窄为"只放行 `SANDBOX_SECURITY_KEYS` + 显式白名单"，`sec_shell`/`sec_exec` 永不自动放行；`FR_CLI_BATCH_CONFIRM=1` 同样收窄 | bot 场景需要第三种语义：**把确认问题发回聊天窗口等人回答**，现有的"拒绝 / 全放行"两档都不够。且 `full_auto`（`command/security.py:64-65`）等价于永久 F，被 env 误设即沙盒全废 |

### P1 —— 决定 harness 是否"可运营"

| # | 改哪里 | 做什么 | 为什么 |
|---|---|---|---|
| ✅ **P1-1** | 新建 `core/trace.py`；改 `core/errors.py:22-29` | 引入 `trace_id` / `span_id`，随事件 payload 传播；日志改结构化 JSON | 现在**无 trace / span / correlation**（全仓零命中），日志是纯文本行，一次调用里的工具与 LLM 无法串联 —— 排障与审计都缺基础 |
| ✅ **P1-2** | `core/events.py:36-77` | 补齐 10 个未派发事件的派发点，或删掉这些常量与对应钩子 | 声明了零派发 → 指标恒为 0 → 监控面板给的是假零 |
| ✅ **P1-3** | `repl/commands/` 新增 `/metrics` | 把 `core/metrics/render.py:16` 的 Prometheus 文本暴露为 REPL 命令 | 现在只有 Web Console 可见（`web/console/handler.py:108`），终端用户看不到指标 = 观测能力等于不存在 |
| ✅ **P1-4** | `memory/compress.py:48-54` | 替换 `len//4` 启发式：CJK 约 1 字 1 token、ASCII 约 4 字符 1 token；压缩时为 output 预留 token 空间 | 中文场景低估约 4 倍 → 压缩触发点远晚于模型真实上限 → 直接导致 context 超限 |
| ✅ **P1-5** | `memory/compress.py:71-133` | 分层压缩：保留 N 段滚动摘要而非一次性合并成 300 字；保留被压缩区间引用 | 当前压缩不可逆且信息损失大，长会话必然丢早期关键事实 |
| ✅ **P1-6** | `agent/master_loop.py:139-197` | 加跨 step 重复调用检测（同 tool+params 连续 N 次即中断）、单步失败可选重试、`MAX_STEPS` 从 config 读 | 现在无死循环检测（同工具连调 8 次耗尽预算） |
| ✅ **P1-7** | `core/app_state_core.py:57` + `repl/queue.py:65-89` + `core/chat/pipeline_post.py:57` | `state.messages` 所有读写加同一把锁，或改为单一 `MessageStore` 抽象 | 目前零锁保护却有 4 个写点（`pipeline_post.py:57` 是整体替换）→ 并发下丢轮次 / 串消息 |
| ✅ **P1-8** | `command/registry.py:30-31` | 注册表加锁，或改不可变快照 + copy-on-write | 动态工具运行时注册（`dynamic_builder/registry_manager.py:189`）与并发 dispatch 无同步 |
| ✅ **P1-9** | `weapon/mcp/manager_invocation.py:60-96` | MCP 调用加 `asyncio.wait_for` 超时；`asyncio.run` 包装改线程本地 event loop 或加锁串行化 session | 现在无超时（完全依赖服务端），且跨线程共享 `ClientSession`（`:96`） |
| ✅ **P1-10** | `core/chat/helpers.py:80-101` | MCP 工具注入时带上完整 schema（名称 / 描述 / 参数 JSON Schema） | 现在只列名字（`:93-96`），模型拿不到参数定义就无法正确构造调用 |
| ✅ **P1-11** | `agent/workflow.py:71-108,243` | 用已建好的依赖图做**拓扑并行调度**；失败返回部分结果而非整体 fail | 依赖图已算出却只用于环检测，执行仍串行；任一步失败则已成功步骤结果丢失（`:279-280`） |
| ✅ **P1-12** | `agent/workflow.py:144-154` + `agent/server.py:171-176` | 超时改可中断机制（子进程 + kill 或协作式取消标志） | `future.cancel()` 对已运行线程无效，步骤会继续跑完并**产生副作用**（写文件、发请求） |
| ⚠️ **P1-13** | `agent/shell_mode.py:30-36` + `agent/hooks.py:281-284` + `weapon/launcher.py:184-218` | 消除 `shell=True`，改 `shlex.split` + `shell=False`（`agent/builtins/local.py:110-118` 已有正确范例，只是未推广） | shell 拼接是注入面 |
| ✅ **P1-14** | `agent/master_storage.py:142-149` | 改用 `JsonStore`（tmp+replace 原子写）替代裸 `open(path,"w")` | MasterAgent 的 session/memory/evolution 是持久化基座，写入中途崩溃会损坏文件 |

### P2 —— 工程质量与长期可维护

| # | 改哪里 | 做什么 | 为什么 |
|---|---|---|---|
| ✅ **P2-1** | `tests/conftest.py` + `tests/fixtures/`；`core/llm/mock.py` | 提供 fixture（临时 HOME、隔离 config、脚本化 LLM）；mock 增加"按调用序列返回"能力 | 2044 用例各自手写 patch；回声式 mock（`mock.py:8-68`）无法编排多步 agent |
| ✅ **P2-2** | 新建 `tests/evals/` | 最小 agent 任务集（工具选择正确率 / 参数正确率 / 多步完成率 / 越权拦截率）+ 离线评分脚本 + 录制回放 | **完全没有 eval 层**，无法回答"改 prompt 后 agent 变好还是变坏" |
| ✅ **P2-3** | `command/registry.py:33-50,74-77` | `params` 增加类型校验；提供 JSON Schema 导出 | 为 P0-1 的原生 tools 透传准备可导出的契约 |
| ✅ **P2-4** | `agent/server.py:281` | 换 `ThreadingHTTPServer`，或给 handler 加并发上限（复用 `command/parallel.py:33` 的钳制） | HTTP 服务单线程串行，并发调用直接排队 |
| ✅ **P2-5** | `command/parallel.py:187-191` | 并行工具不再共享同一 `msgs` list（改为每线程副本） | 任何 `needs_msgs` 工具修改它都会竞态 |
| ✅ **P2-6** | `command/registry.py:92` | 保留异常类型而非只留 `str(e)` | 错误账本现在只能靠事后字符串匹配分类（`agent/master_storage.py` 的 `_classify_error`） |
| ✅ **P2-7** | `core/usage.py:70-74` | 追加写（JSONL）或按日分片，替代全量重写 | 写放大严重，并发下还无锁 |
| ✅ **P2-8** | `TEST_REPORT.md` + `.github/workflows/tests.yml` | 删掉手工维护的静态报告，改为 CI 生成覆盖率与测试报告产物 | 静态报告必然与真实结果脱节 |
| ✅ **P2-9** | `AGENTS.md` / `README.md` 中的 `fr_cli/ui/markdown.py` 引用 | 文档与代码漂移校正（该文件已不存在，实为 `ui/markdown_stream.py`） | 文档误导后续 agent |

---

## 5. Bot 改造清单

Bot 层的改造**依赖于**第 4 节的 P0-2（统一 tool-call 解析）与 P0-8（可注入确认策略）。以下是 bot 特有部分。

### 5.1 新增模块骨架

```
fr_cli/bot/
├── __init__.py
├── core/
│   ├── message.py        # BotMessage / BotEvent 领域模型（chat_id/user_id/thread_id/text/ts/dedup_key）
│   ├── channel.py        # Channel 抽象基类：on_message() / send() / send_stream()
│   ├── router.py         # @ 判定 / 群白名单 / 路由到执行器
│   ├── session_map.py    # (channel, chat_id, thread_id) → 会话存储的映射
│   ├── idempotency.py    # 消息去重（dedup_key + TTL）
│   ├── confirm.py        # 把 security.ask 转成"发问回 IM，等待回复"的确认策略
│   └── dispatch.py       # 入站消息 → 统一执行内核
├── channels/
│   ├── webhook_generic.py  # 通用 webhook 入站（飞书/企微/钉钉共用骨架）
│   ├── lark.py             # 飞书：url_verification 挑战 + 签名校验 + 事件订阅
│   ├── wecom.py            # 企微：明文/加密模式 + 签名
│   ├── dingtalk.py         # 钉钉：加签 + 机器人回调
│   ├── telegram.py         # Telegram：setWebhook / getUpdates
│   └── mail.py             # 邮件入站（轮询 IMAP + 去重 + 自动回复）
└── runtime/
    ├── daemon.py           # 常驻进程：pid 文件 + stop 标记 + 看门狗（照抄 rag_watcher_daemon.py:92-153）
    └── queue.py            # 入站消息队列（复用 PersistentTaskManager）
```

### 5.2 Bot 侧 P0

| # | 改哪里 | 做什么 | 为什么 |
|---|---|---|---|
| **B0-1** | 新建 `fr_cli/bot/core/channel.py` | 定义 `Channel` 抽象：`on_message() -> BotEvent` / `send(chat_id, text)` / `send_stream(chat_id, chunks)` | 没有这层抽象，接第 3 个平台时就要复制一遍签名验签逻辑 |
| **B0-2** | 新建 `fr_cli/bot/core/message.py` | 领域模型：`channel / chat_id / user_id / thread_id / text / ts / dedup_key / reply_to` | 现在完全没有消息领域模型（所有 `chat_id` 类关键词命中均为误报） |
| **B0-3** | 新建 `fr_cli/bot/core/confirm.py` | 实现 `ConfirmPolicy`，把 `security.ask()` 的 Y/A/F/N 转成「向 IM 发确认卡片 → 等待用户回复 → 解析为 y/a/f/n」 | 现有 `ask()` 是裸 `input()`（`security/security.py:68`），**无超时、无重试上限**（`:88` 无限重试）。bot 里必须换掉 |
| **B0-4** | 新建 `fr_cli/bot/core/session_map.py` + 改 `memory/context.py:79` | 按 `(channel, chat_id, thread_id)` 隔离会话与摘要，**不写全局 `config.json` 的 `context.summaries`** | 现在摘要以全局 `session_name`（默认 `__default__`）为 key，**A 用户的摘要会喂给 B 用户**（注入点 `core/chat/pipeline_intent.py:74`）。这是数据串台，比任何功能缺失都严重 |
| **B0-5** | 新建 `fr_cli/bot/core/idempotency.py` | 基于 `dedup_key`（平台 message_id）+ TTL 的去重 | 平台 webhook 会重投；`PersistentTaskManager` 无消息 id 语义（`hermes/managers.py:52-87`） |
| **B0-6** | 改 `agent/artifact_detector.py:77,128,139` | 交互式产物检测在无头模式必须**完全关闭**（而非"检测到再问") | 它在 `_post_process` 里被**无条件调用**（`core/chat/pipeline_post.py:48-49`），只要 AI 回复含 `def run(...)` 代码块就 `input()` 索要名称 → **bot 必然挂死** |
| **B0-7** | 改 `core/chat/pipeline_respond.py:58-61,162-165` | `stream_cnt` 调用补 `silent=True` | 普通对话**必定写 stdout**，bot 场景会污染日志并阻塞管道 |
| **B0-8** | 改 `core/chat/pipeline.py:46` + `pipeline_post.py:57` | `handle_ai_chat` 返回值带上**回复正文**（现在只返回统计 dict） | bot 只能去 `state.messages[-1]["content"]` 挖 —— 最别扭的一处 |
| **B0-9** | 改 `agent/server.py:281` | `HTTPServer` → `ThreadingHTTPServer` + 并发上限 | 单线程串行处理，并发 bot 请求直接排队 |

### 5.3 Bot 侧 P1

| # | 改哪里 | 做什么 | 为什么 |
|---|---|---|---|
| **B1-1** | 新建 `fr_cli/bot/runtime/daemon.py` | 常驻进程：pid 文件 + stop 标记 + 看门狗 + 日志 | 直接照抄 `agent/builtins/rag_watcher_daemon.py:92-153` 与 `agent/hermes_manager.py:205-299` 的成熟范式 |
| **B1-2** | 新建 `fr_cli/bot/runtime/queue.py` | 入站消息进队列，异步消费，复用 `PersistentTaskManager` | 复用 `agent/hermes/managers.py:29-50`（JsonStore + RLock），不重复造 |
| **B1-3** | 新建 `fr_cli/bot/core/router.py` | @ 判定 / 群白名单 / 私聊直答 / 群里仅响应 @ | bot 的核心路由规则，现在完全缺失 |
| **B1-4** | 改 `core/chat/pipeline_post.py:30-44,64` + `pipeline_respond.py:107,111,114` | 全部 `print` / `print_styled` 副作用改为可注入 sink | bot 需要把工具执行结果、token 统计**作为消息发回**，而不是打到 stdout |
| **B1-5** | 改 `core/thinking.py:196,199,213,216` | cot/tot 模式在 bot 下 silent 或禁用 | 会额外发起一次 `silent=False` 流式调用并打印"正在深度思考..." |
| **B1-6** | 改 `repl/router.py:337` | 多匹配时 `input()` 改为返回候选列表交由 bot 呈现 | bot 收到 `/a` 会挂死等编号 |
| **B1-7** | 改 `conf/config.py:296-298,332` | 向导判定改为**显式非交互判定**（不只看 `stdin.isatty()`） | 容器 / pty 包装下 stdin 是 TTY，向导会卡住启动 |
| **B1-8** | 改 `repl/commands/base.py:33-47` | `/shell` 的 `while + input()` 死循环在非交互下直接拒绝 | 会永久占用一个 worker |
| **B1-9** | 改 `memory/session.py:39` + `core/app_state_core.py:48` | 按 bot 会话 key 而非全局 `session_id` 归档 | `create_session(messages, session_id=...)` 已支持 `<uuid>.json` 命名（`session.py:44-45`），是仓内唯一做对的隔离 |
| **B1-10** | 改 `core/app_state_core.py:104-106,178-185` + `repl/batch.py:44-45` | bot 模式不恢复 cron、不设进程级 `FR_CLI_NON_INTERACTIVE` | 每次构造 AppState 都恢复全局 cron；`batch.py` 设的是**进程级全局副作用**，会让整个进程的安全确认转默认拒绝 |
| **B1-11** | 新建 `fr_cli/bot/channels/` 逐平台实现 | 签名校验 + url_verification 挑战 + 重投去重 | 飞书/钉钉/企微各有各的签名算法，`notifier.py` 里只有出站侧实现 |
| **B1-12** | 改 `weapon/mail.py` 或新建 `bot/channels/mail.py` | 邮件入站：轮询（IMAP IDLE 或定时）+ 去重 + 触发 + 自动回信 | 现在 `inbox()` 只取最近 10 封（`mail.py:88-92`），且无轮询、无 UNSEEN 标记、无回调 |
| **B1-13** | 改 `weapon/notifier.py:210-234` | 补企微签名 | 收了 `secret` 却完全没用 |
| **B1-14** | 改 `repl/commands/` 新增 `/bot_start` / `/bot_stop` / `/bot_status` | bot 生命周期命令 | 参考 `/hermes` `/console` 的既有模式 |

### 5.4 Bot 侧 P2

| # | 改哪里 | 做什么 | 为什么 |
|---|---|---|---|
| **B2-1** | 新建 `fr_cli/bot/channels/mcp_server.py` | 把 fr-cli 暴露为 MCP server（当前只有 client，`weapon/mcp/models.py:25-40`） | 外部 agent 生态的标准接入方式 |
| **B2-2** | 新建 `fr_cli/core/http/base.py` | 抽三套 HTTP 服务的公共基类（Bearer 校验 + JSON 响应 + Result 序列化 + 线程池 + 优雅关闭） | 现在三份几乎相同的实现 |
| **B2-3** | 改 `web/console/handler.py:129` + `pyproject.toml` package-data | 修静态资源路径 + 收录 `web/static` | PWA 三件套现在实际 404 |
| **B2-4** | 改 `agent/hermes_api.py:106-201` | GET 端点补鉴权（若 bot 任务内容经此暴露） | 读端点全免鉴权 |
| **B2-5** | 改 `web/console/handler.py:207-209` | 评估是否放开 `/api/command`（带完整权限策略后） | 现在 Web → AI 完全堵死 |
| **B2-6** | 新建 `fr_cli/bot/` 的单元测试 | 每个 channel 的签名/解析/去重单测 + 一条端到端"入站→回复"集成测试 | 参照 `tests/test_toolcall_extraction.py` 的回归测试写法 |

---

## 6. 落地路线（三阶段）

### 阶段 0 —— 地基（约 30% 工作量，必须先做）

目标：**把执行路径收敛成一条**，这是 bot 与 harness 的共同前提。

1. P0-2 统一 tool-call 解析（新建 `core/tool_protocol.py`）
2. P0-5 LLM 调用加重试/退避/错误分类，失败不再返回空字符串
3. P0-8 四阶确认抽象为可注入策略
4. P1-7 `state.messages` 加锁
5. B0-4 会话/摘要按 key 隔离（不做这步，后面全是串台）
6. P0-6 UsageTracker 加锁 + 事件派发下沉到 `core/stream.py`

**验收**：同一段含工具调用的 AI 文本，在传统路径与 ReAct 路径解析结果一致；LLM 失败时用户看到明确错误而非空回复；两个并发会话的消息不交叉。

### 阶段 1 —— Harness 硬化

7. P0-1 原生 function calling 透传（保留文本标记为 fallback）
8. P0-3 接入 per-tool 权限层（复活 `security/permissions.py`）
9. P0-4 动态工具子进程隔离
10. P1-1 trace/span + 结构化日志
11. P1-2 补齐 10 个事件派发点 + P1-3 `/metrics` 命令
12. P1-4/P1-5 中文 token 估算 + 分层压缩
13. P1-7/P1-8 swarm timeout 修正 + 注册表加锁
14. P2-1/P2-2 conftest + fixtures + evals 骨架

**验收**：权限配置真正生效；动态工具跑在子进程；能用 `/metrics` 与 trace 看到一次完整调用链；有离线 eval 可对比改动前后。

### 阶段 2 —— Bot 接入

15. `bot/core/` 领域模型 + Channel 抽象 + 路由 + 去重 + 会话映射
16. `bot/runtime/` 常驻进程 + 消息队列（复用 Hermes 范式）
17. `bot/channels/` 首批平台（按目标选：飞书 / 企微 / 钉钉 / Telegram / 邮件）
18. B0-6/B0-7/B0-8 关闭无头阻塞点（产物检测、stdout 副作用、返回值正文）
19. `/bot_start` / `/bot_stop` / `/bot_status` 命令

**验收**：在 IM 里 @机器人 发一条消息，收到回复；连续多轮上下文正确；工具调用在高危操作时**在 IM 里弹出确认**且拒绝后正确终止。

---

## 7. 需要你拍板的三个决策

1. **首个接入哪个平台？** 飞书（事件订阅 + 签名 + 群 @ 语义最完整）、企微（加密模式）、钉钉、Telegram（最简，webhook 无签名）或邮件（复用现有 IMAP，但轮询有延迟）—— 决定 `bot/channels/` 的实现顺序与验签工作量。
2. **Harness 优先级？** 可靠性（原生 function calling、幂等、断点恢复）／可观测性（trace、指标、归因）／扩展性（工具动态注册、MCP 全面接入）／成本控制（token 预算、模型分级路由）—— 决定阶段 1 内部的排序。
3. **交付形态？** 只出方案文档（本文已覆盖）／最小可用骨架（bot 适配层 + harness 接口能跑通）／分阶段完整落地。

---

## 8. 未验证项

以下结论基于代码静态阅读或路径比对，**未运行时验证**：

- Web Console 静态资源 404：`handler.py:129` 的路径与实际目录比对得出，未启动服务抓包确认。
- `pyproject.toml` 的 `package-data` 缺 `web/static`：已确认文本内容，未执行构建产物核对。
- `security/permissions.py` 无生产调用点：全仓 grep 得出，未穷举动态调用（`getattr` / 反射）路径。
- `core/events.py:36-77` 的 10 个事件零派发：grep 得出，未考虑跨模块 re-export 后的间接派发。
- `agent/master_reflect.py:75-96` 的压缩是死代码：依据 `master_loop.py:100` 调用点消息数为 2 的推算，未运行验证。
- `agent/swarm.py:114` 的 TimeoutError 分支几乎不可达：依据 `as_completed` 不带 timeout 的控制流分析，未构造超时场景实测。
