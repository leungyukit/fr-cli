# Changelog

所有 fr-cli 的变更记录。

## [Unreleased]

### ✨ 新增功能

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

### 🔧 优化
- MasterAgent 启动即可用上历史选品经验，无需人工搬运

### 📊 测试
- 新增 `tests/test_insight_extractor.py`（24 个测试），全部通过
  - 覆盖：数据源(Mock/JSON/CSV)、存储、format_for_prompt、分批-聚合抽取(含 code block 解析)、Dream 集成、prompt 注入
- 现有 dream / master_evolution / master_prompt_fix / integration 测试 45/45 全部通过

### 🔄 兼容
- 路径访问改为 lambda 形式，便于测试 monkeypatch `MASTER_DIR` 隔离
- 无破坏性变更

---

## [2.8.0] - 2026-07-07

### ✨ 新增功能

#### Cron 表达式标准支持
- `cron` 引擎升级到支持三种调度模式：
  - `interval` 模式（旧式兼容）：`/cron_add echo hello 60`
  - `cron` 表达式：`/cron_add echo morning "0 9 * * *"`（每天 9 点）
  - `at` 一次性任务：`/cron_add echo bye "2026-12-31 23:59"`
- 新增依赖 `croniter>=2.0.0`
- 定时任务持久化格式升级（含 `mode` + `value` 字段），向下兼容

#### Dream 梦境机制 ✨
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

### 🔧 优化

- **代码结构清理**：移除死代码、合并重复模块
- **CI/CD**：新增 `.github/workflows/tests.yml`，自动跑测试矩阵（Python 3.10-3.13 × Ubuntu/macOS）+ 自动构建
- **依赖**：新增 `croniter>=2.0.0`
- **Ruff 静态检查**：0 警告

### 📊 测试
- **1687 个测试全部通过**（新增 46 个）
  - `test_cron_schedules.py` (13 个) - cron 表达式/at/迁移
  - `test_dream.py` (12 个) - 梦境机制
  - `test_notifier.py` (21 个) - 多平台推送

### 🔄 兼容
- 全部向下兼容：旧式 `interval` 调用、已有 `cron.json`、`m365.json` 等配置文件自动迁移到主配置

---

## [2.7.0] - 之前

详见 git log。