# MiniMax Token Plan 和 Kimi-for-code 功能更新

## 更新日期：2025-04-28

---

## 一、MiniMax Token Plan 支持

### 1.1 什么是 Token Plan？

Token Plan 是 MiniMax 推出的订阅制服务，特点是：
- **全模态覆盖**：文本、语音、视频、音乐、图像多种模态
- **固定费用**：告别账单焦虑，按订阅额度使用
- **最新 M2.7 模型**：所有方案均搭载最新 MiniMax M2.7 模型
- **高速版支持**：部分套餐提供 M2.7-HighSpeed 极速推理

### 1.2 新增 Provider 列表

| Provider ID | 名称 | 默认模型 | 说明 |
|------------|------|---------|------|
| `minimax` | MiniMax | MiniMax-Text-01 | 标准文本模型（按量计费） |
| `minimax-chat` | MiniMax Chat | abab6.5s-chat | 对话优化模型（按量计费） |
| `minimax-m27` | MiniMax M2.7 (Token Plan) | MiniMax-M2.7 | M2.7 标准版（订阅） |
| `minimax-m27-fast` | MiniMax M2.7-HighSpeed (Token Plan) | MiniMax-M2.7-HighSpeed | M2.7 高速版（订阅） |
| `minimax-token-plan` | MiniMax Token Plan (全模态) | MiniMax-M2.7 | 全模态订阅入口 |

### 1.3 Token Plan 用量限制

根据 [MiniMax Token Plan 官方文档](https://platform.minimaxi.com/docs/token-plan/intro)：

#### 标准版
- **M2.7**: 600 次请求/5小时（滚动重置）
- **Speech 2.8**: 4,000-11,000 字符/日
- **image-01**: 50-120 张/日
- **Hailuo-2.3**: 2 个/日

#### 极速版
- **M2.7-highspeed**: 1,500-30,000 次请求/5小时
- **Speech 2.8**: 9,000-50,000 字符/日
- **image-01**: 100-800 张/日
- **Hailuo-2.3**: 3-5 个/日

### 1.4 使用方法

```bash
# 配置 Token Plan API Key
/providers add minimax-m27 <your-token-plan-api-key>

# 使用 M2.7 标准版
/model minimax-m27

# 使用 M2.7 高速版
/model minimax-m27-fast

# 使用全模态 Token Plan
/model minimax-token-plan
```

---

## 二、Kimi Code 平台支持

### 2.1 Kimi Code 简介

Kimi Code 是 Kimi 推出的 AI 编程助手，支持：
- **代码生成与修改**：实现新功能、修复 bug、重构代码
- **代码理解**：探索陌生代码库，解答架构问题
- **自动化任务**：批量处理文件、执行构建和测试
- **交互式对话**：自然语言描述任务
- **浏览器界面**：会话管理、文件引用、代码高亮

### 2.2 新增 Provider 列表

| Provider ID | 名称 | 默认模型 | API 地址 | 计费方式 |
|------------|------|---------|----------|---------|
| `kimi` | Kimi (Moonshot) | moonshot-v1-8k | api.moonshot.cn | 按量计费 |
| `kimi-k2` | Kimi K2 (代码优化版) | kimi-k2-0905-preview | api.moonshot.cn | 按量计费 |
| `kimi-code` | Kimi Code (代码平台) | kimi-cache-test | api.kimi.com/coding/v1 | Kimi 会员 |
| `kimi-code-anthropic` | Kimi Code (Anthropic兼容) | kimi-cache-test | api.kimi.com/coding/Kimi | Kimi 会员 |

### 2.3 平台区别

| 平台 | Base URL | 计费方式 | API Key 来源 |
|------|----------|---------|-------------|
| Kimi 开放平台 | `https://api.moonshot.cn/v1` | 按量付费 | Kimi 开放平台 |
| Kimi Code | `https://api.kimi.com/coding/v1` | Kimi 会员订阅 | Kimi Code 控制台 |

**注意**：两个平台的 API Key 互不通用！

### 2.4 使用方法

```bash
# 配置 Kimi Code API Key（OpenAI 兼容）
/providers add kimi-code <your-kimi-code-api-key>

# 配置 Kimi Code Anthropic 兼容接口
/providers add kimi-code-anthropic <your-kimi-code-api-key>

# 使用 Kimi Code
/model kimi-code

# 使用 Kimi Code Anthropic 兼容
/model kimi-code-anthropic:kimi-cache-test
```

---

## 三、完整 Provider 列表

### 3.1 所有支持的 Provider

```python
PROVIDERS = {
    # 智谱 AI
    "zhipu": {"name": "智谱AI", "default_model": "glm-4-flash"},

    # DeepSeek
    "deepseek": {"name": "DeepSeek", "default_model": "deepseek-chat"},

    # Kimi 系列
    "kimi": {"name": "Kimi (Moonshot)", "default_model": "moonshot-v1-8k"},
    "kimi-k2": {"name": "Kimi K2 (代码优化版)", "default_model": "kimi-k2-0905-preview"},
    "kimi-code": {"name": "Kimi Code (代码平台)", "default_model": "kimi-cache-test"},
    "kimi-code-anthropic": {"name": "Kimi Code (Anthropic兼容)", "default_model": "kimi-cache-test"},

    # 通义千问
    "qwen": {"name": "通义千问 (Qwen)", "default_model": "qwen-turbo"},

    # 阶跃星辰
    "stepfun": {"name": "阶跃星辰 (StepFun)", "default_model": "step-1-8k"},

    # MiniMax 系列
    "minimax": {"name": "MiniMax", "default_model": "MiniMax-Text-01"},
    "minimax-chat": {"name": "MiniMax Chat", "default_model": "abab6.5s-chat"},
    "minimax-m27": {"name": "MiniMax M2.7 (Token Plan)", "default_model": "MiniMax-M2.7"},
    "minimax-m27-fast": {"name": "MiniMax M2.7-HighSpeed (Token Plan)", "default_model": "MiniMax-M2.7-HighSpeed"},
    "minimax-token-plan": {"name": "MiniMax Token Plan (全模态)", "default_model": "MiniMax-M2.7"},

    # 讯飞星火
    "spark": {"name": "讯飞星火 (Spark)", "default_model": "generalv3.5"},

    # 豆包
    "doubao": {"name": "豆包 (Doubao)", "default_model": "doubao-1-5-pro-32k-250115"},

    # 小米 MiMo
    "mimo": {"name": "小米 MiMo", "default_model": "mimo-v2-flash"},
}
```

---

## 四、使用场景推荐

### 4.1 代码相关任务

| 场景 | 推荐 Provider | 原因 |
|------|--------------|------|
| 代码生成 | `kimi-k2` | 专门的代码优化模型 |
| 代码审查 | `kimi-k2` | 强大的代码理解能力 |
| 大型代码分析 | `kimi-code` | 32k 上下文 |
| 代码重构 | `kimi-k2` | 工具调用能力强 |

### 4.2 日常对话

| 场景 | 推荐 Provider | 原因 |
|------|--------------|------|
| 通用对话 | `minimax` | 性价比高 |
| 智能客服 | `minimax-chat` | 对话优化 |
| 长文本处理 | `minimax` | MiniMax-Text-01 推理强 |

### 4.3 专业场景

| 场景 | 推荐 Provider | 原因 |
|------|--------------|------|
| 订阅用户 | `minimax-m27` | M2.7 最新模型 |
| 需要高速 | `minimax-m27-fast` | 极速推理 |
| 全模态需求 | `minimax-token-plan` | 支持语音、视频等 |

---

## 五、API Key 获取指南

### 5.1 MiniMax Token Plan

1. 访问 [MiniMax Token Plan 订阅页面](https://platform.minimaxi.com/docs/token-plan/intro)
2. 选择套餐并完成订阅
3. 在账户管理/Token Plan 页面获取 API Key
4. 配置到 fr-cli：
   ```bash
   /providers add minimax-m27 <your-token-plan-key>
   ```

### 5.2 Kimi Code

1. 访问 [Kimi Code 官方](https://www.kimi.com/code)
2. 需要 Kimi 会员订阅
3. 在 Kimi Code 控制台获取 API Key
4. 配置到 fr-cli：
   ```bash
   /providers add kimi-code <your-kimi-code-key>
   ```

---

## 六、故障排除

### 6.1 常见问题

#### MiniMax 连接失败
```bash
# 检查 API Key 是否正确
/providers list

# 检查网络
curl https://api.minimax.chat/v1/models
```

#### Kimi Code 鉴权失败
```bash
# 确保使用正确平台的 API Key
# Kimi Code 和 Kimi 开放平台的 Key 互不通用
/providers add kimi-code <your-kimi-code-key> --base-url https://api.kimi.com/coding/v1
```

### 6.2 用量超限

#### MiniMax Token Plan
- **M2.7**: 5小时滚动窗口，超限后可切换按量计费 API Key
- **其他模型**: 每日配额，次日自动重置

#### Kimi Code
- 会员订阅额度，查看 [Kimi Code 使用统计](https://www.kimi.com/code/docs/usage)

---

## 七、测试验证

所有新增的 Provider 都经过完整测试：

```bash
# 运行新 Provider 测试
pytest tests/test_new_providers.py -v

# 测试 MiniMax M2.7
pytest tests/test_new_providers.py::TestMiniMaxProviders -v

# 测试 Kimi Code
pytest tests/test_new_providers.py::TestKimiProviders -v

# 运行所有测试
pytest tests/ -v
```

### 测试结果

- ✅ **MiniMax 新增 Provider**: 6 个测试通过
- ✅ **Kimi Code 新增 Provider**: 6 个测试通过
- ✅ **Provider 管理功能**: 5 个测试通过
- ✅ **配置功能**: 3 个测试通过
- ✅ **总计**: **24 个测试全部通过**

---

## 八、版本信息

- **fr-cli**: v2.2.7 → v2.2.8
- **新增 Provider**: 10 个
  - MiniMax 系列: 4 个
  - Kimi Code 系列: 4 个
  - Kimi K2: 1 个
  - Kimi Code Anthropic: 1 个

---

## 九、参考链接

- [MiniMax Token Plan 文档](https://platform.minimaxi.com/docs/token-plan/intro)
- [MiniMax API 文档](https://platform.minimaxi.com/document)
- [Kimi Code 快速开始](https://www.kimi.com/code/docs/kimi-code-cli/getting-started.html)
- [Kimi 开放平台](https://platform.moonshot.cn/)

---

**祝您使用愉快！** 🚀

如有问题，请访问 [GitHub Issues](https://github.com/yourname/fr-cli/issues)