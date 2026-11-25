# fr-cli eval 层 —— 离线 / 可重复 / 零网络

> 仓库此前有 2200+ 个单元测试，但**没有 eval 层**：改了 prompt、换了模型、
> 改了工具描述之后，没人能回答"agent 是变好了还是变坏了"。
> 这一层就是回答这个问题的护栏。

## 快速开始

```bash
# 跑完整评测，输出四个核心指标
.venv/bin/python tests/evals/run_evals.py

# 机器可读输出
.venv/bin/python tests/evals/run_evals.py --json

# CI 用：任一核心指标不到 100% 就退出码 1
.venv/bin/python tests/evals/run_evals.py --strict

# 当成 pytest 跑
.venv/bin/python -m pytest tests/evals/ -q
FR_CLI_SKIP_EVALS=1 .venv/bin/python -m pytest tests/evals/ -q   # 显式跳过
```

**不需要网络，不需要 API Key。** LLM 走脚本化 mock，web / mail / disk 全是桩件。

## 四个核心指标

| 指标 | 口径 |
|---|---|
| 工具选择正确率 | 模型选中的工具 == 期望工具 的任务占比 |
| 参数正确率 | 在"工具命中"的任务里，期望参数的逐 key 命中率均值 |
| 多步完成率 | 多步任务在 `max_steps` 内按序跑完并收敛（拿到最终答复）的占比 |
| 越权拦截率 | 该被拦的调用**真的走了 `state.security` 确认流程**且被拦下的占比 |

辅助指标：端到端成功率、回归基线（排除已知缺陷）、误拦率（对照组本该放行却被拦）。

## 它测什么 / 不测什么

**测（解析与调度层）** —— 每一轮都走生产实现：

```
模型文本 → 标记解析(executor._extract_tool_calls)
         → 参数解析(executor._parse_tool_kwargs)
         → 工具调度(executor.invoke_tool → registry.dispatch)
         → 安全确认(state.security.check → ConfirmStrategy)
         → 工具 handler(VFS / 桩件)
```

所以它能发现：工具被改名/下线、参数 schema 变了、注册表调度断了、
安全级别被摘掉了、handler 本身坏了。

**不测（模型真实能力层）** —— 那需要联网 + API Key，属于 live eval，
本仓库**没有**默认开启。所以这套 eval **测不出**"真实模型会不会选对工具"、
"回答质量好不好"。它测的是**给定模型输出后，fr-cli 的链路有没有把它正确执行**。

## 目录结构

```
tests/evals/
├── README.md              本文件
├── harness.py             评测核心：任务模型 / 状态装配 / 运行 / 指标
├── run_evals.py           评分脚本（可独立运行）
├── record.py              录制工具（把一次交互录成 fixture）
├── test_evals.py          pytest 集成（含"封死 socket 再跑一遍"的离线证明）
├── test_scripted_mock.py  脚本化 mock 的单元测试
├── datasets/              任务集（JSON）
│   ├── tool_selection.json  单步工具选择
│   ├── multi_step.json      多步收敛
│   └── security.json        越权拦截 + 对照组
└── fixtures/
    └── sample_session.json  样例录制（回放零网络）
```

## 任务集格式

```json
{
  "id": "tool_select_write_file",
  "user_input": "帮我把内容写到 a.txt",
  "expect_tool": "write_file",
  "expect_params": {"path": "a.txt", "content": "hello world"},
  "max_steps": 3,
  "tags": ["single", "fs"],
  "notes": "最基础的写文件调用",
  "known_issue": "",
  "setup": {"files": {"notes.md": "内容"}},
  "script": ["模型第 1 轮输出", "模型第 2 轮输出"]
}
```

| 字段 | 含义 |
|---|---|
| `expect_tool` | 期望选中的工具（多步任务里指**最后一步**） |
| `expect_tools` | 多步任务的期望工具序列（按顺序） |
| `expect_params` | 期望参数；只校验列出的 key，多余参数不扣分 |
| `expect_security` | 期望触发的安全类别（`sec_*`） |
| `expect_blocked` | `true`=应被拦 / `false`=不该被拦（对照组）/ 省略=不关心 |
| `setup` | 运行前在工作目录里准备的文件与子目录 |
| `script` | **模型输出脚本** —— 每轮返回的文本 |
| `known_issue` | 已知缺陷说明；标了它就不会被当成"新回归" |

## 安全类任务为什么跑两遍

安全任务跑两遍：

* `allow` 遍 —— 放行确认，验证工具链路**真的能跑通**（文件真被写进去了）
* `deny` 遍 —— fail-closed，验证该被拦的调用**真的被拦下**

拦截结论取 `deny` 遍。对照组任务（`expect_blocked: false`）在 `deny` 遍里
如果被拦住了 → 误拦率上升 → 说明有人给无安全级别的工具乱加了 `sec_*`。

## 脚本化 Mock LLM（`fr_cli/core/llm/mock.py`）

| 类 / 方法 | 作用 |
|---|---|
| `MockLLMClient(api_key="mock", **kw)` | **回声式 mock —— 行为与 v2.8.6 完全一致**（一个字节都没改） |
| `MockLLMClient(script=[...], rules=[...])` | 传了脚本参数 → 切脚本化；不传 → 老行为 |
| `MockClient` | `MockLLMClient` 的别名 |
| `ScriptedMockClient(script=None, rules=None, default_response=None, api_key="mock-script-key", model="mock-script", usage=None)` | 脚本化 mock |
| `.push(response)` / `.on(pattern, response)` | 追加脚本条目 / 追加匹配规则（链式） |
| `.reset()` | 重置调用序号与调用记录 |
| `.calls` / `.last_response` | 调用记录 / 最近一次响应 |
| `.save_fixture(path, name=...)` | 把调用记录写成 fixture |
| `ScriptedMockClient.load_fixture(path, mode="sequence"\|"match")` | 从 fixture 回放（零网络） |
| `RecordingClient(inner, name=...)` | 录制包装器 —— 包住任意 client，把交互录下来 |
| `RecordingClient.save_fixture(path)` | 落盘 fixture |
| `save_fixture(path, calls, name)` / `load_fixture(path)` | 模块级 fixture 读写helper |

两种模式：

```python
# 序列模式：第 n 次调用返回 script[n-1]
client = ScriptedMockClient(script=["A", "B"])

# 匹配模式：按输入内容匹配（子串 / 正则 / 可调用对象），优先于序列
client = ScriptedMockClient(rules=[
    ("关键词", "命中关键词的回复"),
    (re.compile(r"^tool"), "命中正则的回复"),
    (lambda msgs: msgs[-1]["content"].endswith("?"), "命中问句的回复"),
])
```

匹配目标按优先级依次尝试：**最后一条 user 消息 → 第一条 user 消息 → 全部 user 消息拼接**
（所以多轮 agent 流程里，"原始任务输入"和"最新一轮追问"都能命中）。

## 录制 / 回放

```bash
# 离线录一份样例（不联网）
.venv/bin/python tests/evals/record.py --out tests/evals/fixtures/sample_session.json

# 录一次真实交互（需要本机已配 API Key，CI 不会调它）
.venv/bin/python tests/evals/record.py --live --out my.json "帮我写个文件"
```

回放：

```python
from fr_cli.core.llm.mock import ScriptedMockClient

client = ScriptedMockClient.load_fixture("tests/evals/fixtures/sample_session.json")
client = ScriptedMockClient.load_fixture(path, mode="match")   # 按输入内容匹配
```

fixture 格式：

```json
{
  "version": 1,
  "kind": "fr_cli.llm.fixture",
  "name": "scripted-session",
  "calls": [{"model": "...", "messages": [...], "response": "..."}]
}
```

## 已知缺陷

| 任务 | 问题 |
|---|---|
| `tool_select_replace_text` | `fr_cli/command/registered/fs.py` 里 `replace_text` 的 `@register` 装饰器**错位到了 `_to_bool` 上**（真正的 handler `_replace_text` 没被注册）。该工具目前 100% 报 `TypeError: _to_bool() got an unexpected keyword argument 'path'`。把装饰器挪回 `_replace_text` 后本用例即转绿。 |

任务里标了 `known_issue` 的失败**不算回归** —— 报告会把它们单独列在
「已知缺陷」一节，回归基线（`regression_rate`）不含它们。

## conftest 提供的夹具

`tests/conftest.py` 里新增（原有的 HOME 隔离逻辑一行未动）：

| fixture | 作用 |
|---|---|
| `tmp_home` | 临时 HOME，并把 `fr_cli.conf.paths.ROOT` 等路径一并指过去 |
| `isolated_cfg` | 干净的配置字典（无 API Key / `manual` 自治模式） |
| `scripted_llm` | 脚本化 mock 客户端 |
| `eval_workdir` | 沙盒工作目录 |

### 跳过开关

`FR_CLI_SKIP_EVALS=1` 只跳过 **需要外部资产**的评测套件（`test_evals.py` ——
依赖 `datasets/` 与 `fixtures/`）。`test_scripted_mock.py` 与
`test_conftest_support.py` 是自包含的单测（不依赖任何 fixture 文件），
始终会跑 —— 它们守的是 `fr_cli/core/llm/mock.py` 这个生产代码的回归。
