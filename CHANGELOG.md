# 更新日志 v2.2.8

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
| Kimi Code | kimi-code | kimi-cache-test |
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
