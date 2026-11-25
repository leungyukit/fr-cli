# 测试报告 —— 已改为 CI 自动生成

> **v2.8.7(P2-8) 起本文件不再手工维护。**

手工维护的静态报告必然与真实结果脱节 —— 本文件上一版还停留在
v2.4.3 / 357 个用例，而仓库当前已有 2300+ 个用例。报告改为由 CI
在每次 push / PR 时生成，作为**构建产物**上传。

## CI 产物

`.github/workflows/tests.yml` 的 test job 现在会生成并上传：

| 产物 | 路径 | 内容 |
|---|---|---|
| JUnit XML | `test-results/junit.xml` | 每个用例的通过/失败/耗时，GitHub Actions 会自动渲染成测试报告表格 |
| 覆盖率 XML | `coverage.xml` | 机器可读，供 Codecov / SonarQube 之类的服务消费 |
| 覆盖率 HTML | `htmlcov/` | 逐行覆盖视图，可下载后本地打开 |

产物名：`test-report-py<版本>-<系统>`，保留 14 天。

## 本地生成同样的产物

```bash
# 依赖（dev extra 里已声明 pytest-cov）
pip install pytest-cov

# 跑测试 + 出报告
pytest tests/ -v --tb=short \
  --junitxml=test-results/junit.xml \
  --cov=fr_cli --cov-report=xml --cov-report=html --cov-report=term:skip-covered
```

然后打开 `htmlcov/index.html` 看逐行覆盖。

## 只想快速看一眼结果

```bash
pytest tests/ -q
```

## 终端里看运行时指标

除了 CI 覆盖率，fr-cli 自己在运行时也会记录指标（LLM 调用次数、
工具调用次数、token 消耗、错误计数等）。终端里直接看：

```
/metrics          # 人类可读摘要
/metrics json     # 结构化 JSON
/metrics prom     # Prometheus 文本格式
```

指标的生产派发点见 `fr_cli/core/events.py::ALL_V2_EVENTS`（事件名清单）
与 `fr_cli/core/metrics/`（渲染与聚合）。

## 离线评测（eval）

单元测试之外，仓库还有一层**离线 eval**（不需要 API key），
用于回答"改了 prompt / 模型 / 工具描述之后，agent 是变好还是变坏"：

```bash
python tests/evals/run_evals.py
```

指标包含工具选择正确率、参数正确率、多步完成率、越权拦截率。
详见 `tests/evals/README.md`。
