# Changelog

所有 fr-cli 的变更记录。

## [Unreleased]

## [2.8.7] - 2026-11-26

### 新增功能

#### Bot 统一适配层（`fr_cli/bot/`）
- fr-cli 此前只有**出站** webhook 推送，没有任何入站通道。现在可以把 fr-cli 当作 IM 机器人使用。
- **统一适配层**：新增 `fr_cli/bot/core/channel.py` 的 `Channel` 抽象 —— 新增一个平台只需实现 `verify` / `parse` / `send` 三个方法 + 一段配置，**不做任何平台特判**。
  - 统一消息模型 `fr_cli/bot/core/message.py`（`BotMessage` / `BotReply`）
  - 路由 `fr_cli/bot/core/router.py`：群里是否 @ 我、群白名单、命令前缀
  - 幂等 `fr_cli/bot/core/idempotency.py`：平台会重投 webhook
  - 会话隔离 `fr_cli/bot/core/session_store.py`：按 `session_key` 隔离消息与摘要
  - 聊天窗口确认 `fr_cli/bot/core/confirm.py` + `confirm_broker.py`：Y/A/F/N 搬到 IM，**超时按拒绝**
  - 状态池 `fr_cli/bot/core/state_pool.py`：多会话安全共享运行时
  - 调度器 `fr_cli/bot/core/dispatcher.py`
- **运行时** `fr_cli/bot/runtime/`：HTTP 网关（统一接收平台 webhook，立即 ack + 异步处理）、引擎（配置装配）、守护进程（脱离 REPL 独立运行）、进程管理
- **首批通道** `fr_cli/bot/channels/`：`generic`（通用 webhook，基准实现）、`lark`（飞书）、`telegram`（Telegram）
- **REPL 命令**：`/bot_start`（别名 `/bot`）、`/bot_stop`、`/bot_status`、`/bot_config`、`/bot_channels`
- 配置位置 `~/.fr_cli/bot/config.json`；运行时文件在 `~/.fr_cli/bot/`

#### 统一工具调用协议层（`fr_cli/core/tool_protocol.py`）
- 把两条独立的 tool-call 解析路径合并为**唯一**实现（`command/executor_parse.py` 与 `agent/master_loop.py` 改为委托）。
- 支持格式：【调用：tool({...})】/ ```tool 围栏 / 裸 JSON / `<tool_call>` XML / 对象数组
- 参数解析三级回退（JSON → `ast.literal_eval` → 正则宽松），且**修复了宽松解析匹配不到无引号 key** 的缺陷
- 参数解析失败返回带 `error` 的 `ToolCall`（不静默丢弃），上层可把错误反馈给模型自纠正

#### 可注入的确认策略（`fr_cli/security/strategy.py`）
- 把安全确认从"终端 `input()`"抽象为可替换的策略对象：`TerminalStrategy`（默认，行为不变）/ `AutoDenyStrategy` / `AutoAllowStrategy` / `CallbackStrategy`（bot：把确认问题发回聊天窗口）
- `SecurityManager.set_strategy()` 支持运行时替换

#### 工具 Schema 与参数校验（`fr_cli/command/schema.py`）
- `export_schemas()` 导出全部工具的 JSON Schema（实测 149 个），`export_schema_text()` 导出可注入 prompt 的文本
- `validate_params()` 接入 `registry.dispatch()`：类型不符先宽容转换再报错

#### 子 Agent 统一注册表（`fr_cli/agent/registry.py`）
- 本地 / 远程 / 内置 / 动态 Agent 的统一视图，已接入 `/agent_list`

#### 动态工具子进程沙箱（P0-1）
- `/build` 生成的工具是 **LLM 生成的代码**，此前直接在 fr-cli **主进程**里 `exec()` —— 无沙箱、无超时、无资源限制，bot 场景下构成完整的 RCE 链（平台消息 → prompt injection → 模型调 `/build` → 任意代码在主进程执行）。现改为 **父进程授权 + 子进程执行 + 能力 RPC 回代理**
- 新增 `fr_cli/dynamic_builder/sandbox.py`（父进程侧）：静态 AST 校验、带类型标签的线上协议编解码、凭证脱敏、RPC 宿主、超时终止、rlimit 下发
- 新增 `fr_cli/dynamic_builder/sandbox_worker.py`（子进程侧）：受限 builtins（`open`/`eval`/`exec`/`compile`/`input` 直接不存在）、`__import__` 守卫（黑名单模块直接 ImportError，并清洗放行模块夹带的黑名单属性如 `logging.os`）、RPC 客户端
- 协议走 stdin/stdout 双向管道（父→子：请求 + RPC 回执；子→父：RPC 请求 + 最终结果），跨平台一致（Windows 上 `pass_fds` 不可用）
- **凭证不出主进程**：`deps.cfg` 传的是脱敏副本，api key / secret / token / password 全部替换为 `***`
- **网络与文件只走 deps**：`deps.web_c` / `deps.mail_c` / `deps.disk_c` / `deps.client` / `deps.mcp` 是 RPC 代理，实际调用回到父进程执行，并按 `sec_fetch_web` / `sec_send_mail` / `sec_write` / `sec_exec` / `sec_mcp_call` 走**真实**确认
- **授权永远在父进程**：沙箱内 `deps.security` 是一律拒绝的桩
- **超时与资源限额**：默认 30s（`meta["timeout"]` 可调），超时杀掉整个进程组；子进程内设 `RLIMIT_CPU` / `RLIMIT_AS` / `RLIMIT_FSIZE` / `RLIMIT_NPROC`
- 动态工具注册时 `security="sec_exec"` —— 每次调用走正常 Y/A/F/N 确认
- 代码生成 prompt 增加「沙箱限制」章节，明确引导模型用 `deps.vfs` / `deps.web_c` 而非 `open()` / `requests`
- ⚠️ **诚实边界**：子进程**不是**操作系统级沙箱 —— 它仍能用自己的 Python 能力访问真实文件系统与网络（只要不写 `open()`），第三方 pip 依赖也能读写本机文件。本层提供的是崩溃隔离 + 超时 + 资源限额 + 凭证隔离 + 静态白名单 + import 守卫；内核级隔离需 Landlock（Linux）/ Seatbelt（macOS），属独立议题

#### 原生 function calling（P0-3）
- 新增 `fr_cli/core/llm/function_calling.py`：`ToolCall` / `ToolCallAccumulator`（按 index 归并流式分片、JSON 解析失败不静默吞）/ `build_tools_payload`（复用 `command/schema.py::export_schemas`）/ `client_supports_tools`
- `core/llm/base.py::stream_chat` 新增 `tools` / `tool_choice` 参数；`_yield_chunks` 只在真有分片时透出 `delta.tool_calls`，**不改变既有 chunk 形状**
- provider 支持情况：zhipu / openai_compat 原生支持；**anthropic / 文心暂不支持**（协议不同，`SUPPORTS_TOOLS=False`，走文本标记路径）
- `core/chat/pipeline_respond.py` 补齐闭环：模型请求工具 → 本地执行 → `role="tool"` 回填 → 第二轮 LLM
- 与文本标记路径（`【调用：tool({...})】`）**并存**：provider 不支持或拒绝 tools 时自动退回（`_looks_like_tools_rejection()`）
- ⚠️ 关键修复：provider 客户端是生成器函数，**拒绝异常发生在迭代期而非调用期** —— 兜底逻辑必须包住整个迭代，否则第一次就崩

#### LLM 调用韧性（P0-2）
- 新增 `fr_cli/core/llm/resilience.py`：`classify_error`（瞬时/认证/致命三分）/ `is_transient` / `describe_error` / `call_with_retry`（指数退避）/ `resolve_fallback`
- `core/stream.py::stream_cnt` 新增 `timeout` / `retry` / `fallback` / `provider` 参数
- **重试仅在未产出任何内容时进行** —— 已产出内容则保留 partial 并如实报错，避免重复输出
- **降级不改变用户的 `/model` 选择**：`state.get_fallback_client()` 只影响本次调用
- **失败原因如实带回** —— 不再笼统报「请检查 API 密钥配置」
- 超时秒数从 `config.json` 的 `llm_timeout` 读（此前写死 60，配置层形同虚设）

#### Trace / Span（P1-1）
- 新增 `fr_cli/core/trace.py`：`TraceSpan` / `start_span` / `current_span` / `TraceRecorder` / `get_recent_spans` / `get_traces` / `trace_summary`
- `command/executor_dispatch.py::invoke_tool` 埋点：一次工具调用 = 一个 span（`kind="tool"`）
- 落盘默认关闭，`FR_CLI_TRACE_ENABLE=1` / `FR_CLI_TRACE_DIR=<dir>` 开启（JSONL，每 trace 一文件）

#### `/metrics` 命令（P1-3）
- 新增 `fr_cli/repl/commands/config/metrics.py`：终端里直接看运行时指标
- `/metrics`（人类可读摘要）/ `/metrics json` / `/metrics prom`（Prometheus 文本）
- 此前指标只在 Web Console 可见 —— 终端用户完全看不到观测数据

#### 流式期间可交互（UX）
- 新增 `fr_cli/core/steering.py`：`push_steer` / `drain_steer` / `peek_steer` / `steer_count` / `clear_steer`
- **Ctrl+S 转向注入**：AI 生成途中把当前输入作为**本轮**的追加指令注入 —— 与对话队列（排成下一轮）不同，模型在同一轮里带着新指令继续推理
- **Ctrl+C 语义拆分**：生成中只中断流式输出、**保留草稿**（此前会连草稿一起清掉）；空闲时才清空输入行
- 状态栏新增**队列深度**与**待生效转向指令数**
- 注入点覆盖两条路径：传统对话流水线（`core/chat/pipeline_respond.py`）与 MasterAgent ReAct 循环（`agent/master_loop.py`）

#### 显示层与交互重构（UX）
- **代码块语法高亮**（零依赖）：新增 `fr_cli/ui/syntax.py` —— 此前代码块内容整行染成 DIM 灰，关键字/字符串/注释/数字全是同一个颜色；而 `core/optimizations.py::LANG_KEYWORDS` 早就有现成的关键字表却**全仓零引用**
- **长回答自动折叠 + Ctrl+O 展开**：新增 `fr_cli/core/collapse.py`（折叠内容登记表）；超长回答折叠成「头部 + 折叠提示 + 尾部」，命令输出折叠后的省略部分也不再**直接丢弃** —— 两者都能按 Ctrl+O 原样找回。阈值 60 行，正常长度回答流式体验零损失
- **`@` 补全文件路径**：此前 `@` 只能补 Agent，引用工作区文件得手打完整路径；现在同时补全单层文件/目录路径
- **状态栏重排**：从"十来项用 `│` 平铺"改为**左右分栏 + 全局优先级裁剪** —— 模型与忙碌状态永远保留，目录/时间/模式等低优先级项按终端宽度自动丢弃，窄屏不再折行把输入框顶变形
- **状态栏新增上下文占用 %**：接近压缩阈值时黄/红预警（此前只有回答末尾一行 `usage_pct`，状态栏看不到）
- **状态栏展示工具参数**：此前 `tool_name` 字段**从未被赋值**，工具执行分支是死代码 —— 用户只能看到 spinner，看不到在跑什么；现由 `command/executor_dispatch.py` 上报真实工具名与关键参数摘要
- **状态栏展示工具来源与失败原因**：原文要求的"来源 agent、失败原因"此前也缺 —— 现补上 `[master]` / `[local]` / `[workflow]` / `[plan]` 来源前缀，工具失败时以红色显示失败原因（工具结果本身不回显给用户，状态栏是失败现场唯一可见的地方；失败原因保留到本轮对话结束）。来源用 ContextVar 传递（`tool_source_scope`），因为 Agent 内部代码调 `invoke_tool` 时不会传来源
- **首次启动"快速上手"卡片**：只出现一次（`onboarding_card_shown` 标志），给出快捷键与四种输入形态，并附一条可直接抄的示例（`@local 帮我总结 README.md`）
- **占位符精简**：原先是一行 40+ 字符的固定提示（把所有快捷键塞进去），窄终端溢出且一输入就消失；现在只留「输消息 · /命令 · @Agent或文件 · !shell」
- **代码块分隔线跟随终端宽度**：不再硬编码 60 列（窄屏折行、宽屏留白）
- **表格列宽对齐**：中英混排不再列列歪斜
- **上手卡片框线对齐**：此前顶边 / 内容行 / 底边三者宽度互不相同（+3 / +2 / +4），框是歪的；现按显示宽度统一，并随终端宽度自适应（窄屏压缩描述列 + 省略号，框线仍对齐）

#### 欠账收口（P2 细节打磨 + 长线 3/4/5）

> 这一批是把此前**清单上挂着、实际没做**的项清干净。逐条核实代码后发现：三条"长线"里有两条的 TODO 本身就是**过时信息**。

- **token 三处口径统一**：状态栏显示 `100/200/300`、回答末尾显示 `↓100 ↑200 Σ300 (12%)`、第三处显示 `tokens_used/limit` —— 而 `tokens_used` **全仓无人写入**（与当年的 `tool_name` 同一类死代码）。现由 `core/usage.py::format_token_usage` 作为唯一真相源，两处同一格式、同一占比分母，死分支删除
- **多行粘贴降级（`/paste`）**：prompt_toolkit 的渲染器会自动开启 bracketed paste，所以现代终端粘贴多行**本来就是一条消息**；真正缺的是**不支持该协议的终端没有降级出路**。新增 `/paste`：读到 EOF（Ctrl+D）或单独一行 `.` 为止，整段作为**一条消息**提交，任何终端都能用
- **未知命令模糊建议**：此前只有 `get_close_matches(n=3, cutoff=0.3)` —— 只给 3 条且不认子序列（`/mdl` 想打 `/model` 常常一条都匹配不上）。现按统一相似度排序（编辑距离 + 子序列 + 前缀），最多 5 条，子序列权重按覆盖率折算（`/kee` → `/key` 而不是 `/gatekeeper`）
- **原生 function calling 多调用并发**（长线-3）：模型一次返回多个 tool_calls 时，此前仍是**串行**执行，把模型的一次决策拆成 N 次等待。现并发执行，结果按调用顺序回填（`role="tool"` 消息必须与请求一一对应）
- **并行执行下的安全确认互斥**（新发现的安全问题）：并发工具调用会让多个线程同时 `input()` 抢终端 —— 用户回答的 Y/A/F/N 可能落到**另一个工具**上（"允许读文件"被当成"允许执行命令"）。已加全局确认锁（`security/security.py::_CONFIRM_LOCK`），一次只会有一个确认问句
- **会话增量持久化接线**（长线-4）：增量写入器（snapshot + delta + 周期全量快照）**早就写好了，但只有它自己的测试在用** —— 生产路径 `memory/session.py::update_session` 仍是每轮把整个 messages 重写一遍（1000 条消息 ≈ 1MB/轮）。现已接线，并补上 v1 → v2 存量迁移、`/undo` 截断历史时的全量重写、`list_sessions` 对 v2 的计数、删除时清理附属文件
- **长线-5 RAG 缓存**：**早已实现并接线**（`agent/builtins/rag_cache.py` 内存 TTL 600s + 跨会话磁盘持久化，查询路径命中即返回）。`optimizations.py` 里那条"未实现"的 TODO 是**过时信息**，已更正 —— 留着会让人以为缓存没做
- **`optimizations.py` 收口记录**：把三条过时 TODO 换成逐条核实后的真实状态（已实现 / 本次补齐 / 有意不做），并注明各项的真实归属

#### 顺带清掉的既有欠账

- **并行工具调用的安全确认会串**（安全问题，不只是显示问题）：并发执行时多个线程同时 `input()` 抢终端 —— 用户回答的 Y/A/F/N 可能落到**另一个工具**上（"允许读文件"被当成"允许执行命令"）。已加全局确认锁（RLock，可重入），一次只出现一个确认问句；EOF/中断按**拒绝**处理，不让整批工具卡死
- **状态栏工具状态在并行下会误清**：一个工具结束时会把另一个还在跑的工具状态清成"就绪"。已改为"只有状态栏显示的仍是自己时才清"
- **`tests/test_security.py` 环境变量泄漏**：`os.environ["FR_CLI_BATCH_CONFIRM"] = "1"` **不会被回滚** —— autouse fixture 里的 `monkeypatch.delenv(..., raising=False)` 对"本来就不存在的变量"是空操作、不登记 undo，于是这个变量永久留在进程环境里，把后续所有用例的确认流程变成"一律放行"。已改用 `monkeypatch.setenv`
- **`tests/test_dataframe.py` 用了未导入的 `MagicMock`**（F821）：该文件整类被 `skipif` 跳过（缺 pandas），**掩盖了这个错误** —— 装了 pandas 的环境会直接 NameError 崩掉。已补导入
- **测试目录 lint 全绿**：README 里写的 `ruff check fr_cli tests` 此前一直有 19 处报错（未用导入、未用变量、F821），现已全部清零 —— CI 只门禁 `fr_cli/`，所以这些一直没人管
- **文档漂移**：USAGE.md 两处快捷键表写的是 `Shift+Enter`，代码里绑定的其实是 **`Esc+Enter`**（`ui/prompt/tui.py`）；README 的"745+ 个测试用例"实际已是 2563。均已校正

### 修复

- **颜色常量被"按值冻结"，全局关色对 95 个模块无效**：`from fr_cli.ui.ui import RED` 拿到的是 import 期的**字符串副本**，运行时 `set_no_color(True)` 只能改 `ui.ui` 自己的全局 —— 那 95 个副本纹丝不动，非 TTY / prompt_toolkit.patch_stdout 代理期仍会漏出 `?[91m` 乱码。现改为 `_LiveColor`（str 子类活引用）：常量记住自己的名字，取值时实时回读；`CYAN + BOLD` 这类组合即使在 import 期求值也同样是活的
- **`save_config` 是整文件替换 → "只改一个字段"就能抹掉用户整份配置**：`save_config(c)` 把传进来的字典**原样写全量文件**，`c` 里没有的键就没了。上手卡片为了记一个 `onboarding_card_shown` 标志直接 `save_config(cfg)`，一旦传入的是局部字典，用户整份配置（provider / API Key / 定时任务）当场蒸发 —— 本轮真实踩中，配置被抹成 `{"onboarding_card_shown": true}`。现已新增 `conf/config.py::save_config_merge(c)`（读磁盘 → 逐键覆盖 → 整份写回）并改用它；`save_config` 的替换语义保持不变（`/providers del` 等依赖它真正删键）
- **`core/optimizations.py` 一半是"只有标题没有实现"的空桩**：`FOLD_THRESHOLD_LINES` / `LANG_KEYWORDS` 全仓零引用，读代码会以为功能已存在。现已清理为显式 TODO，并注明各项的真实归属
- **AGENTS.md 文档漂移**：项目结构里列的 `ui/buddha.py` 早已被删除（commit b304121），已校正

- **11 个事件常量零派发 → 指标恒为 0**：`core/events.py` 23 个事件里有一半从未被派发，监控面板给的是**假零**。现已建立 `ALL_V2_EVENTS` 事件名清单 + 派发自检，并补齐 `command.executed` / `session.created` / `session.saved` / `app.stopped` / `error.occurred` 的生产派发点
- **`llm.*` 事件绕过 MasterAgent**：`stream_cnt` 是全仓 LLM 调用的唯一漏斗，事件派发已下沉到此处 —— 覆盖 ReAct 循环，且不重复计数
- **MasterAgent 工具调用绕过统一执行器**：此前直调 `registry.dispatch`，绕过了 `tool.*` 事件与 Pre/PostToolUse hook。现已改走 `executor.invoke_tool`
- **swarm 的 timeout 是死代码**：`as_completed(futures, timeout=...)` 不带 timeout → `future.result(timeout=)` 立刻返回，超时分支几乎不可达 —— **假能力比没有更危险**。现已改为真整体 deadline（实测 `timeout=0.1 + sleep 1.0` 从 1.003s 降到 0.107s），超时条目带真实任务名并按部分失败语义返回
- **workflow 依赖图算了却不用**：只用于环检测，执行仍全串行；任一步失败则已成功步骤的结果全丢。现已按依赖图**分层并行**（纯 LLM 补全层才并行，碰 `state.executor` 的层保守串行），失败保留部分结果
- **`_run_with_timeout` 名不副实**：`with ThreadPoolExecutor(...)` 退出时 `shutdown(wait=True)` 阻塞到挂起任务结束 → 超时后仍要等任务跑完。已改显式 `shutdown(wait=False)`
- **MasterAgent session/memory 落盘非原子**：`master_storage._save_json` 裸 `open(path,"w")`，写入中途崩溃会损坏文件。已改 tmp + fsync + `os.replace`
- **中文 token 低估 2.7~4 倍**：`memory/compress.py` 用 `len//4`（英文经验值）估算，中文实际约 1.5 字/token → 压缩触发点远晚于模型真实上限 → 直接导致 context 超限。已改为 CJK/西文分别计权 + 安全系数
- **上下文压缩信息不可逆丢失**：早期对话一次性合并成 300 字摘要，模型分不清"早期定了什么"和"中期改了什么"。已改为**分层摘要**（最多 3 段，按时间顺序各出一份，标注覆盖的对话区间；单段失败保留原文片段；全失败才退化为截断）
- **MasterAgent 无死循环检测**：同一 tool+params 连调 8 次只是把预算耗光。现已加**重复调用检测**（累计成功 N 次即收尾）+ 单步失败重试 + `MAX_STEPS` 从 config 读
- **并行工具共享同一个 `msgs` list**：任何 `needs_msgs` 工具往上下文里写东西都会与其他线程互相踩。已改为每线程一份独立副本（列表 + 每条消息 dict 各拷一份）
- **异常类型被吞成纯字符串**：`registry.dispatch` 的 `except Exception as e` 只留 `str(e)` → 错误账本只能靠事后字符串匹配分类，等于没有分类。`Result` 现已支持 `error_type`
- **Windows 上 `shell=True` 是注入面**：`weapon/launcher.py` 把应用名与目标拼成 shell 命令。现已消除全部 `shell=True`（`os.startfile` / `Popen([...], shell=False)`）
- **`agent/shell_mode.py` 的 `shell=True` 刻意保留**：命令来源只有用户手输（`!cmd` 与 shell 模式），**没有任何 LLM 输出路径能到达**（注册表里的 `shell` 工具只是桩）；且 `!ls | grep x` 这类管道正是这个功能本身。真正的加固点是"谁能把命令送进来"，已在注释里写明
- **断言 ANSI 色的用例在 CI 里必然失败**：`fr_cli/ui/ui.py` 在 import 时就 `set_no_color(_NO_COLOR)`，非 TTY 下把颜色常量清空。测试现改为显式恢复常量 + 强制判定，而不是依赖环境碰运气
- **文档与代码漂移**：AGENTS.md 写的 `fr_cli/ui/markdown.py` 实际是 `ui/markdown_stream.py`；`docker build -t fr-cli .` 因 Dockerfile 在 `docker/` 下根本跑不通。均已校正


- **两条 tool-call 解析路径容错不一致**：同一段 AI 文本在传统路径能被兜底救回，在 ReAct 路径被**静默丢弃** —— 用户看到"AI 好像想调工具但什么都没发生"。现已统一
- **per-tool 权限层是死代码**：`security/permissions.py` 的 `PermissionManager.check_tool` 实现了、有测试，但全仓零调用点 —— 用户写在 config 里的权限规则**永远不生效**。现已接入 `registry.dispatch()`
- **MCP 工具描述恒为空**：`core/chat/helpers.py::fetch_mcp_desc` 读 `srv.tools`，而 `MCPServer` dataclass 根本没有该字段 → 真实 manager 恒返回 `""`，模型拿不到任何 MCP 工具。现已修复并输出完整参数 schema
- **MCP 调用无超时 / 跨线程不安全**：新增 `asyncio.wait_for` 超时；`call_tool_sync` 在已有 running event loop 的线程里不再抛 RuntimeError
- **`UsageTracker` 自称线程安全却无锁**：全文件无 `import threading`，并发调用丢记录；且每次调用全量重写 10 万条 JSON。现已加锁 + 批量延迟落盘
- **`state.messages` 读-改-写无锁**：4 个写点 + 后台 worker → 多用户场景消息交错。现已提供加锁访问器
- **交互式产物检测在无头环境必然挂死**：`agent/artifact_detector.py` 在 `_post_process` 里无条件 `input()`，只要 AI 回复含 `def run(...)` 代码块就索要名称。现已在无头模式跳过
- **MCP 工具发现拖慢启动与每轮对话**：改为后台线程预热，prompt 组装只读缓存
- **Bot 停止时被误判为"还活着"**：僵尸进程对 `os.kill(pid, 0)` 仍返回成功，导致停止流程一路走到 SIGKILL。现已回收子进程
- **`/bot_start` 在网关监听前就返回**：原先只等 PID 文件出现，调用方立刻发请求会连接被拒。现改为等健康检查通过
- **`build_tool` 规划失败时返回元组而非 `Result`**：`dynamic_builder/runner.py` 里 `return False, f"规划失败: ..."`，而调用方（`repl/commands/build.py`）直接调 `result.is_ok()` → `AttributeError` 崩溃。现已改为 `Result.fail(...)`
- **推理模型的思考过程被当成代码喂给 `exec()`**：`core/llm/base.py::_yield_chunks` 在 `content` 为空时回退到 `reasoning_content`，于是 stepfun / glm 等推理模型的返回文本变成「思考过程 + 代码块 + 后续思考」。`_clean_code_markers` 原来只处理「整段就是 ``` 代码```」的情况，散文会原样进入 `exec()` → `SyntaxError` → `/build` 对推理模型**完全不可用**。现已改为：优先抽取包含 `def run(` 的代码块（多个草稿时取最完整的一段），无围栏时从 `def run(` 处切开
- **REPL 假死：安全确认与输入框抢同一个 stdin**：REPL 主循环用 prompt_toolkit 占着 stdin（raw 模式），而工具执行跑在**后台线程**（`repl/queue.py` 的 worker）。工具需要安全确认时原实现直接 `input()` —— 两个读者抢同一个 fd，prompt_toolkit 的读取器先拿到按键，用户敲的 Y/A/F/N 全被吞进输入框，`input()` 永远等不到 → 终端**完全没反应**（每按一次回车只是把一条空消息塞进对话队列），高危操作既批不了也停不下。现已改为「确认中转站」（新增 `fr_cli/security/interactive.py`）：后台线程经 `BROKER.request()` 阻塞等答案，拥有 stdin 的**主线程**把用户输入经 `BROKER.deliver()` 送回去；状态栏同步显示 `⚠ 待确认 <工具名> (Y/A/F/N)`。边界处理：主线程自己发起的确认（斜杠命令触发的高危操作）仍走裸 `input()`（此刻没有 prompt_toolkit 在读 stdin，走中转站会自己等自己）；中转站关闭时（非 TTY / 批处理 / HTTP 服务 / bot）行为**零变化**；等待超时（300s）、退出或 Ctrl+D 时按**拒绝**处理（fail-closed）；非 Y/A/F/N 的输入一律当普通对话消息，不会被误当成授权。新增 `tests/test_confirm_broker.py`（20 个用例）
- **`tests/test_batch_mode.py` 的环境变量泄漏**：`run_batch` 会把 `FR_CLI_NON_INTERACTIVE=1` 写进**进程环境**且不还原 —— 该语义被既有测试固化（`test_run_batch_sets_non_interactive_env` 断言调用返回后变量仍在），生产代码不能改；但测试文件里 4 个用例调完 `run_batch` 就没还原，这个变量因此永久留在进程环境里，把后续所有用例的安全确认变成"一律拒绝"，表现为别的测试文件**单跑绿、全量红**。现已加 autouse fixture 逐例还原（与当初 `tests/test_security.py` 的 `FR_CLI_BATCH_CONFIRM` 泄漏同类）
- **代码生成 token 上限偏小**：`generate_tool_code` 的 `max_tokens=2048` 对推理模型不够（思考就吃掉了预算，代码被截断）。现已提到 4096，并在 prompt 中要求「只输出一个完整实现」
- **推理模型的「思考过程」被当成最终答案写进历史/记忆**：stepfun step-5 / GLM thinking 系 / 火山方舟 thinking 系把思考下发到 `delta.reasoning_content`、把答案下发到 `delta.content`，而 `core/llm/base.py::_yield_chunks` 在 `content` 为空时回退到 `reasoning_content` —— 于是思考与答案被拼成同一段文本，思考被写进历史/记忆/`context.json` 摘要，污染后续每一轮的上下文。现已分离：`_yield_chunks` 保持 `content` 语义**完全不变**（既有调用方与测试零影响），仅在正文实际取自 `reasoning_content` 时追加 `reasoning: True` 标记；`core/stream.py` 把思考单独收集，**不进返回文本**（只有答案进历史/记忆），终端显示路径不变 —— 思考照常可见。兜底保留：答案只出现在 `reasoning_content`（火山方舟 coding endpoint）时把思考内容当答案返回，避免「答非所问」。实测 step-5-preview 返回文本从 615 字符（含思考）降到 86 字符（纯答案）。新增 `tests/test_reasoning_separation.py`（10 个用例）
- **沙箱子进程启动慢**：`sandbox_worker` 通过 `python -m` 拉起，包 `__init__` 会连带导入 `runner` → `command.executor` → `command.registry` → `weapon.mcp` → `mcp` 整条重链（实测 0.79s，其中 `mcp.types` 一项 174ms），而子进程只需要 `sandbox` + `weapon.fs`。现把 `fr_cli/dynamic_builder/__init__.py` 改为**惰性导入**（PEP 562），对外接口不变 —— 沙箱单次调用从 ~0.45s 降到 **0.13s**
- **CronManager 多实例割裂**：恢复任务时新建了一个临时 `CronManager()`，而 `/cron_list`、`/status`、gatekeeper 同步读的都是模块级默认管理器 —— 结果是**任务在跑却谁都看不见它**；`/status` 的定时任务数恒为 0，gatekeeper 同步过去的 `cron_jobs` 恒为空。现已统一收敛到默认管理器（单一真相源），并让 `load_persistent_jobs()` **幂等**（重复恢复不产生重复任务）
- **定时任务计时器从不回收 → 跨用例随机污染**：计时器是 daemon 线程，用例创建的 interval 任务会在整套测试跑到一半时触发；每次触发都进入 `prompt_toolkit.patch_stdout` 守卫，而它是**进程级**的 `sys.stdout` 替换，会把此刻其它线程/用例的 print 全部劫持走 —— 表现为"某个用例单跑通过、全量跑时随机失败且断言输出为空"。现新增 `CronManager.stop()` / `stop_all()`，应用退出时收干净（`_dispatch_app_stopped`），测试夹具 teardown 也收干净

### 新增

- 无头模式（headless）：`state.headless = True` 时对话流水线不写 stdout、跳过交互式产物检测、不写全局 `context.summaries`，回复正文经 `state.last_reply` 回传
- 新增 6 个测试文件共 192 个用例（tool_protocol / security_strategy / bot_core / bot_gateway / bot_integration / dynamic_sandbox）

### 变更

- **测试报告改为 CI 生成**：`TEST_REPORT.md` 原是手工维护的静态报告（还停留在 v2.4.3 / 357 个用例），必然与真实结果脱节。现已改为**指针文档** —— `.github/workflows/tests.yml` 生成 JUnit XML + 覆盖率 XML/HTML 并作为构建产物上传（`test-report-py<版本>-<系统>`，保留 14 天）
- CI 的测试步骤去掉了 `-x`（fail-fast 会让报告只跑到第一个失败就停），改用 `--junitxml` + `--cov`
- 新增测试文件：`tests/test_steering.py`（流式期间交互）、`tests/test_master_loop_limits.py`（ReAct 运行时预算）、`tests/test_parallel_isolation.py`（msgs 隔离 + 异常类型）、`tests/test_function_calling.py`、`tests/test_token_estimate.py`、`tests/test_trace.py`、`tests/test_metrics_command.py`、`tests/test_cron_lifecycle.py`（定时任务停止 / 单一真相源 / 幂等恢复）

## [2.8.6] - 2026-11-24

### 新增功能

#### 韩立启动字符画
- 新增 `fr_cli/ui/hanli.py`：半块真彩色字符画渲染（`print_hanli(variant, min_free_rows)`）
  - 素材：`fr_cli/assets/hanli_bust.ansi`（56×80 半身像，默认）/ `hanli_full.ansi`（72×103 完整立绘）
  - 修复 `hanli_full.ansi`（43 个）/ `hanli_bust.ansi`（29 个）中所有只设背景色的 `▄` 单元格：统一改写为等价上半块 `[38;2;X;49m▀`，避免深色主题下下半块透出默认前景的浅灰杂点或行内继承色；修复后素材不再含独立 bg SGR 序列（fg/bg 均合并或显式声明）
  - 终端高度不足时自动跳过，不撑破布局
- 启动时默认打印（`repl/bootstrap.py`）；`fr-cli -noart` 跳过；配置 `startup_art: false` 永久关闭
- REPL 内 `/hanli [full]` 随时重看

#### `!` 命令直执行 + 管道模式
- 新增 `fr_cli/repl/bang.py`：
  - 普通模式 `!<cmd>`：执行并展示（截断 3000 字符），不进 AI 上下文
  - 管道模式 `!<cmd> | <prompt>`：输出截断后作为 user 消息进上下文，问题走对话队列
- 安全口径：用户显式键入的命令不再二次确认（与 `/shell` 一致）；AI 发起的调用仍走 `sec_shell` 四阶确认

#### 流式 Markdown 渲染
- `core/stream.py::stream_cnt` 新增 `markdown=True`：非 silent 时经 `ui/markdown_stream.py::StreamingMarkdownRenderer` 边生成边排版（标题/列表/代码块/表格），代码块带 `─` 分隔线与语言标签
- 中断路径输出 `[已中断]` 标记，三个退出点均先 flush
- `NO_COLOR=1` 下自动降级纯文本

#### Ctrl+C 中断 + 工具调用可视化
- AI 输出 / 工具执行中按 `Ctrl+C` 中断当前轮（不再只是清空输入）
- 工具调用改 Claude Code 风格：`[*]` 头 + dim 体

### 清理与拆分

#### 死代码清理
- 删除约 28 个零引用函数与 v3 未接线模块（container / lifecycle / pipeline / provider / errors / builtin_plugins / compat / examples）
- 删除重复全量渲染的 `fr_cli/ui/markdown.py`（流式渲染器上线后无用）

#### 大文件拆分（均保持导入面不变）
- `command/registered/services.py`（532 行）→ 扁平 6 文件：mail / cron / notify / dream / disk / m365
- `core/metrics/plugin.py`（485 行）→ 4 mixin：primitives / hooks / render / labels
- `agent/builtins/rag.py`（509 行）→ 4 mixin：rag_chunking / rag_index / rag_query / rag_cache
- `command/executor.py`（509 行）→ 3 mixin：executor_parse / executor_dispatch / executor_ai（顺带提取共享的 `_fmt_tool_result`，消灭 5 处重复）
- `repl/commands/_common.py`（420 行）→ _help_data（纯数据）/ _help_views（视图）
- `weapon/defi.py`（464 行）→ defi_format（渲染层）
- `weapon/m365.py`（456 行）→ m365_auth（认证层）
- `weapon/cron.py`（439 行）→ cron_schedule（纯函数）
- `weapon/fs.py`（415 行）→ fs_diff（渲染辅助）
- `agent/hermes_daemon.py`（449 行）→ hermes_api（HTTP 层）
- `core/chat/pipeline.py`（488 行）→ pipeline_intent / pipeline_respond / pipeline_post 三阶段

#### 拆分约束（后续维护注意）
- 测试 monkeypatch 的模块属性不能搬：`weapon.defi._http_get`、`weapon.m365.M365_CONFIG_FILE`、`weapon.cron.CRON_STORE_FILE` 必须留在原模块
- 带 `@register` / `@hook` 装饰器的函数不是死代码（引用计数分析看不到装饰器注册）

### 修复
- 降级路径 Markdown 围栏被 chunk 边界截断、语言标签状态丢失、表格头行不含 `-` 不被识别（3 个既存 bug）
- 韩立字符画高度保护按纯文本版行数（40）判断，彩色终端实际打印 80 行会溢出一倍——改为按实际打印版本（彩色/纯文本）计算
- 流式输出在未闭合代码块内结束时最后一行重复打印：`flush()` 的 IN_CODE 分支不清空 buffer，且 `stream_cnt` 两个退出点都 flush——flush 改为幂等 + 去掉重复调用
- MasterAgent（默认开启）路径的最终回答原文 `print`，绕过流式 Markdown 渲染——改为交互模式流式输出（每轮 ReAct 思考与最终回答都实时渲染），Hermes 后台隔离运行保持 silent；pipeline 不再重复打印
- `m365_config_wizard` 对 Result 解包必抛 TypeError（`__slots__` 不可迭代）

### 测试
- 新增 `tests/test_hanli_art.py`（15）、`tests/test_bang_and_interrupt.py`（9）、`tests/test_stream_markdown.py`（12）、`tests/test_markdown_stream.py`（+1 flush 幂等回归）
- 全量：74 failed / 1715 passed / 12 skipped —— 失败数与改动前基线（74 failed / 1750 passed）完全一致，均为环境性预存失败（无 API Key / 无默认模型配置 / 顺序依赖）；passed 减少来自随 v3 死代码一并删除的测试

---

### 新增功能

#### 选品洞察提炼器(Insight Extractor)
- 新增 `fr_cli/agent/insight_source.py`：可插拔选品数据源
  - `MockSelectionSource`（默认，~80 条合成数据，让流程在没有真实数据时也能跑通）
  - `JSONSelectionSource` / `CSVSelectionSource`
  - `register_source(name, cls)` 动态扩展
- 新增 `fr_cli/agent/insight_extractor.py`：LLM 提炼引擎
  - 分批-聚合模式，应对 100-1000 条规模
  - 输出结构化洞察（品类/价格带/生命周期/季节性/关键信号）
  - `format_for_prompt(insights)` 输出可注入 system prompt 的 Markdown
- 新增 `fr_cli/agent/insight_storage.py`：洞察档案
  - `~/.fr_cli/master/insights/latest.json`（最新洞察，供 prompt 注入）
  - `~/.fr_cli/master/insights/history/`（历史快照，便于回溯对比）
- 新增 `/insight` 与 `/insight_extract` 命令：
  - `/insight show` — 查看最新
  - `/insight extract [--source mock|json|csv] [--path <file>] [--since <YYYY-MM-DD>] [--batch <N>]` — 立即跑一次提炼
  - `/insight history [N]` — 查看历史快照
  - `/insight sources` — 列出可用数据源
- 扩展 `master_prompt_builder.py`：在 system prompt 中新增 `[选品经验]` 段落，自动读取最新洞察并注入
- 扩展 `dream.py`：DreamEngine 支持可选 `selection_source`；每次 Dream 末尾会顺带跑一次 insight_extract（失败不影响 Dream 主流程）

#### 竞品监控 能力缺口扫描器(Competitor Gap Scan)
- 新增 `fr_cli/dynamic_builder/capabilities/competitor_monitor.yaml`：能力模型（8 个子能力）
  - 价格/库存/上新/活动/评价/销量/搜索排名/SKU 变更
  - 每个能力带 `name / description / key_signals / priority / example_usage`
- 新增 `fr_cli/dynamic_builder/competitor_gap_scan.py`：扫描器
  - `CompetitorGapScanner(model_path, state, lang)` — 加载能力模型 → 遍历 → 复用 `CapabilityGapAnalyzer` 判断覆盖
  - 报告 schema：scanned / gap_count / tools_count / gaps（按优先级+置信度排序）
  - 持久化：`~/.fr_cli/dynamic_builder/gap_reports/competitor_monitor/{latest.json, history/}`
  - 兜底排序：`format_report_text` 也按优先级排序（高 → 中 → 低）
- 新增 `/competitor_gaps` 命令：
  - `/competitor_gaps scan` — 立即跑扫描，打印缺口报告
  - `/competitor_gaps show` — 查看最近一次报告
  - `/competitor_gaps add <name>` — 把指定缺口推到 `/hermes review` 队列（供后续自动构建）
  - `/competitor_gaps model` — 显示当前能力模型概要

### 优化
- MasterAgent 启动即可用上历史选品经验，无需人工搬运
- 能力扩展从"被动等需求"升级为"主动扫领域"：dynamic_builder 可主动扫描"竞品监控"领域，把缺口推到 review queue

### 测试
- 新增 `tests/test_insight_extractor.py`（26 个测试，含 2 个 E2E smoke test），全部通过
  - 覆盖：数据源(Mock/JSON/CSV)、存储、format_for_prompt、分批-聚合抽取(含 code block 解析)、Dream 集成、prompt 注入、命令端到端
- 新增 `tests/test_competitor_gap_scan.py`（16 个测试），全部通过
  - 覆盖：YAML 加载、模型验证、扫描流程、异常处理、format_report 排序、4 个命令路径
- 现有 dream / master_evolution / master_prompt_fix / integration / dynamic_builder / gap_analyzer / review_queue 测试 87/87 全部通过

### 兼容
- 路径访问改为 lambda/函数形式，便于测试 monkeypatch `MASTER_DIR / ROOT` 隔离
- 无破坏性变更

### 新增功能

#### ReAct 主循环强制规划步
- 新增 `fr_cli/agent/master_planner.py`：任务型输入（本地启发式门控，零成本）先让 LLM 产出 N 步结构化计划并渲染，再把计划作为 system 消息播种进 ReAct 循环
- 修"模型不自觉就静默退化成一问一答"（session.json 实证 17 个任务 11 个零工具调用）
- 规划调用 silent=True，模型思维链不刷屏；计划展示统一走 `render_plan`
- `/mode plan` 与 MasterAgent 解耦：计划模式不再被整体禁用（cot/tot/react 仍禁用）

#### 工具调用容错识别
- 新增 `fr_cli/core/plan/toolcalls.py::extract_tool_calls`：四层兜底（整段裸 JSON / 任意代码围栏 / 字符串感知括号匹配挖标签内 JSON / 显式扫工具标签内层），键位兼容 `tool+params`、`tool+arguments`、`name+arguments`、OpenAI `function` 风格，按 `(tool, params)` 去重
- 修 live 实测静默失败：step-5-preview 实际吐裸 JSON，旧解析只认 tool 围栏，导致工具调用被当成"最终答案"、ReAct 循环一步退出、工具从未执行
- 播种消息补显式格式规定作双保险

### 优化

#### 输入区蓝色箭头 + 自适应分隔线
- 提示位置蓝色小箭头；输入区蓝色横线，Enter 后变浅灰

### 修复

#### ANSI 序列泄漏治理
- security 高危确认路径 5 处带色裸 print / `input()` 提示，在 REPL `patch_stdout` 代理期把 ESC 吐成字面问号加方括号，用户看到乱码；改走 `print_styled` 并新增公开 `ui.use_color()` 助手
- 核心对话路径 19 处带色裸 print 转 `print_styled()`，带全量对比基线
- 计划 JSON 容错：`parse_plan_json` 容忍思维链前后文与代码围栏，不再一讲废话就解析失败

### 测试
- 新增 `test_master_planner` / `test_input_separator` / `test_toolcall_extraction`；全量 3 失败 / 1990 通过 / 12 跳过，零新增失败
- live 复验：裸 JSON 工具调用真执行（session.json 实证 step_count=4、3 个 steps），原始字节流乱码计数 0

---

## [2.8.0] - 2026-07-07

### 新增功能

#### Cron 表达式标准支持
- `cron` 引擎升级到支持三种调度模式：
  - `interval` 模式（旧式兼容）：`/cron_add echo hello 60`
  - `cron` 表达式：`/cron_add echo morning "0 9 * * *"`（每天 9 点）
  - `at` 一次性任务：`/cron_add echo bye "2026-12-31 23:59"`
- 新增依赖 `croniter>=2.0.0`
- 定时任务持久化格式升级（含 `mode` + `value` 字段），向下兼容

#### Dream 梦境机制
- 新增 `~/.fr_cli/master/dream_log.md`：长期记忆归档
- 新增 `~/.fr_cli/master/dream_index.json`：按主题索引
- 新增 `/dream` 命令：
  - `/dream` 立即整理（提炼经验/偏好/技能/改进）
  - `/dream status` 显示统计
- 自动空闲监听（>30 分钟无交互触发）

#### Notifier 多平台消息推送
- 支持 6 大协作平台 webhook 推送：
  - 飞书 / Lark（支持签名校验）
  - 钉钉（支持加签 + @手机号/所有人）
  - 企业微信（支持 @成员）
  - Slack / Discord / Telegram
- 新增命令：
  - `/notify_add <channel> <webhook_url> [secret]`
  - `/notify_list` / `/notify_rm <channel>`
  - `/notify <channel|all> <消息>` / `/notify all <消息>`
- 配合 `/cron_add` 实现定时通知：
  ```bash
  /cron_add "0 9 * * *" "/notify lark '早安,今日数据已就绪'"
  ```

### 优化

- **代码结构清理**：移除死代码、合并重复模块
- **CI/CD**：新增 `.github/workflows/tests.yml`，自动跑测试矩阵（Python 3.10-3.13 × Ubuntu/macOS）+ 自动构建
- **依赖**：新增 `croniter>=2.0.0`
- **Ruff 静态检查**：0 警告

### 测试
- **1687 个测试全部通过**（新增 46 个）
  - `test_cron_schedules.py` (13 个) - cron 表达式/at/迁移
  - `test_dream.py` (12 个) - 梦境机制
  - `test_notifier.py` (21 个) - 多平台推送

### 兼容
- 全部向下兼容：旧式 `interval` 调用、已有 `cron.json`、`m365.json` 等配置文件自动迁移到主配置

---

## [2.7.0] - 之前

详见 git log。