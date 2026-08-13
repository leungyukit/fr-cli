"""
选品洞察提炼器 测试
"""
import json
import csv
from unittest.mock import MagicMock, patch

import pytest


# ---------- 隔离 fixture ----------

@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """隔离 ~/.fr_cli/master/,避免污染真实环境"""
    fake_fr_cli = tmp_path / ".fr_cli"
    fake_master = fake_fr_cli / "master"
    fake_master.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    import fr_cli.conf.paths as _paths_mod
    if hasattr(_paths_mod, "_root_holder"):
        monkeypatch.setattr(_paths_mod._root_holder, "value", fake_fr_cli)
    else:
        # 兼容:直接 set MASTER_DIR
        monkeypatch.setattr(_paths_mod, "MASTER_DIR", fake_master)
    yield
    # 清空模块缓存,避免后测影响前测
    import sys
    for mod in list(sys.modules):
        if mod.startswith("fr_cli.agent.insight"):
            del sys.modules[mod]


# ---------- SelectionRecord ----------

def test_selection_record_basic():
    from fr_cli.agent.insight_source import SelectionRecord
    r = SelectionRecord(
        name="连衣裙",
        category="女装/连衣裙",
        price=99.0,
        sales_30d=1200,
        lifecycle_days=14,
        peak_date="2026-08-01",
        tags=["应季", "颜值经济"],
    )
    assert r.name == "连衣裙"
    assert r.source == "unknown"
    d = r.to_dict()
    assert d["name"] == "连衣裙"
    assert d["tags"] == ["应季", "颜值经济"]


# ---------- Mock 数据源 ----------

def test_mock_source_default_count():
    from fr_cli.agent.insight_source import MockSelectionSource
    src = MockSelectionSource()
    records = src.load()
    assert len(records) > 0
    # 至少覆盖多个品类
    cats = {r.category.split("/")[0] for r in records}
    assert len(cats) >= 3


def test_mock_source_filter_by_since():
    from fr_cli.agent.insight_source import MockSelectionSource
    src = MockSelectionSource(count=30)
    all_records = src.load()
    # 过滤只看最近 30 天内峰值
    recent = src.load(since="2026-07-15")
    assert len(recent) <= len(all_records)
    for r in recent:
        assert r.peak_date >= "2026-07-15"


def test_mock_source_deterministic_seed():
    from fr_cli.agent.insight_source import MockSelectionSource
    a = MockSelectionSource(count=20, seed=7).load()
    b = MockSelectionSource(count=20, seed=7).load()
    names_a = [r.name for r in a]
    names_b = [r.name for r in b]
    assert names_a == names_b


# ---------- JSON 数据源 ----------

def test_json_source_loads_file(tmp_path):
    from fr_cli.agent.insight_source import JSONSelectionSource
    f = tmp_path / "selection.json"
    data = [
        {
            "name": "充电宝",
            "category": "3C数码/充电宝",
            "price": 89.0,
            "sales_30d": 5000,
            "lifecycle_days": 21,
            "peak_date": "2026-08-10",
            "tags": ["高频复购"],
        },
        {
            "name": "口红",
            "category": "美妆个护/口红",
            "price": 199.0,
            "sales_30d": 3000,
            "lifecycle_days": 30,
            "peak_date": "2026-07-20",
            "tags": [],
        },
    ]
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    src = JSONSelectionSource(path=str(f))
    records = src.load()
    assert len(records) == 2
    assert records[0].source == "json"
    assert records[0].name == "充电宝"


def test_json_source_missing_file_returns_empty():
    from fr_cli.agent.insight_source import JSONSelectionSource
    src = JSONSelectionSource(path="/nonexistent/file.json")
    assert src.load() == []


def test_json_source_skips_invalid_rows(tmp_path):
    from fr_cli.agent.insight_source import JSONSelectionSource
    f = tmp_path / "selection.json"
    f.write_text(
        json.dumps([
            {"name": "ok", "category": "x", "price": 1, "sales_30d": 1,
             "lifecycle_days": 1, "peak_date": "2026-01-01"},
            {"name": "bad"},  # 缺字段,应被跳过
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    src = JSONSelectionSource(path=str(f))
    records = src.load()
    assert len(records) == 1


# ---------- CSV 数据源 ----------

def test_csv_source_loads_file(tmp_path):
    from fr_cli.agent.insight_source import CSVSelectionSource
    f = tmp_path / "selection.csv"
    with open(f, "w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=[
            "name", "category", "price", "sales_30d",
            "lifecycle_days", "peak_date", "tags",
        ])
        w.writeheader()
        w.writerow({
            "name": "瑜伽裤", "category": "运动/瑜伽裤", "price": 159,
            "sales_30d": 2000, "lifecycle_days": 30,
            "peak_date": "2026-08-05", "tags": "高客单|颜值经济",
        })
        w.writerow({
            "name": "坚果礼盒", "category": "食品/坚果", "price": 99,
            "sales_30d": 8000, "lifecycle_days": 14,
            "peak_date": "2026-07-25", "tags": "送礼场景",
        })

    src = CSVSelectionSource(path=str(f))
    records = src.load()
    assert len(records) == 2
    assert records[0].tags == ["高客单", "颜值经济"]


# ---------- Source 注册表 ----------

def test_register_and_list_sources():
    from fr_cli.agent.insight_source import register_source, list_sources, get_source

    class FakeSource:
        name = "fake"
        def __init__(self, **kw):
            self.kw = kw
        def load(self, since=None):
            return []

    register_source("test_fake", FakeSource)
    assert "test_fake" in list_sources()
    inst = get_source("test_fake", x=1)
    assert isinstance(inst, FakeSource)
    assert inst.kw == {"x": 1}


def test_get_source_unknown_raises():
    from fr_cli.agent.insight_source import get_source
    with pytest.raises(ValueError, match="未知的选品数据源"):
        get_source("__nope__")


# ---------- Storage ----------

def test_storage_save_and_load():
    from fr_cli.agent import insight_storage as st
    insights = {
        "summary": "测试洞察",
        "categories": [{"name": "测试品类", "hit_rate": "高", "evidence": "1"}],
        "key_signals": ["信号1"],
    }
    path = st.save(insights, source_name="mock", record_count=42)
    assert "latest.json" in path

    latest = st.load_latest()
    assert latest is not None
    assert latest["source_name"] == "mock"
    assert latest["record_count"] == 42
    assert latest["insights"]["summary"] == "测试洞察"


def test_storage_list_and_load_history():
    from fr_cli.agent import insight_storage as st
    # 连续保存两次
    st.save({"summary": "first", "categories": []}, source_name="mock", record_count=10)
    st.save({"summary": "second", "categories": []}, source_name="mock", record_count=20)

    entries = st.list_history(limit=5)
    assert len(entries) == 2
    # 最新的在前面
    assert entries[0]["summary"] == "second"

    # 加载某条历史
    payload = st.load_history(entries[0]["history_path"])
    assert payload is not None
    assert payload["insights"]["summary"] == "second"


def test_storage_get_latest_meta():
    from fr_cli.agent import insight_storage as st
    # 空时返回 None
    assert st.get_latest_meta() is None
    st.save({"summary": "meta test", "categories": []}, source_name="mock", record_count=5)
    meta = st.get_latest_meta()
    assert meta is not None
    assert meta["source_name"] == "mock"
    assert meta["summary"] == "meta test"


# ---------- InsightExtractor.format_for_prompt ----------

def test_format_for_prompt_empty():
    from fr_cli.agent.insight_extractor import InsightExtractor
    ex = InsightExtractor()
    assert ex.format_for_prompt({}) == ""
    assert ex.format_for_prompt(None) == ""


def test_format_for_prompt_full():
    from fr_cli.agent.insight_extractor import InsightExtractor
    insights = {
        "summary": "连衣裙 + 高客单 容易出爆款",
        "categories": [
            {"name": "女装/连衣裙", "hit_rate": "高",
             "evidence": "20/30 批次都强势",
             "key_signals": ["应季", "颜值经济"]},
            {"name": "3C/充电宝", "hit_rate": "中", "evidence": "稳定", "key_signals": []},
        ],
        "price_bands": [
            {"range": "50-200", "verdict": "高频走量", "evidence": "60% 命中"},
        ],
        "lifecycle_patterns": [
            {"pattern": "7-14 天", "description": "应季品爆发快"},
        ],
        "seasonal_trends": [
            {"signal": "Q3 连衣裙爆发", "evidence": "历史数据"},
        ],
        "key_signals": ["信号A", "信号B", "信号C"],
    }
    text = InsightExtractor().format_for_prompt(insights)
    assert "[选品经验]" in text
    assert "连衣裙" in text
    assert "高客单" in text
    assert "应季" in text
    assert "50-200" in text
    assert "7-14 天" in text
    assert "Q3 连衣裙爆发" in text
    assert "信号A" in text


def test_format_for_prompt_truncates_long():
    from fr_cli.agent.insight_extractor import InsightExtractor
    insights = {
        "summary": "x" * 5000,
        "categories": [],
        "price_bands": [],
    }
    text = InsightExtractor().format_for_prompt(insights, max_chars=200)
    assert len(text) <= 250  # 留点余地给截断标记
    assert "已截断" in text


# ---------- InsightExtractor.extract(用 mock client) ----------

def _mock_client_factory(per_call_outputs):
    """构造一个 mock client,每次 stream_cnt 返回下一段输出"""
    outputs = list(per_call_outputs)
    mock = MagicMock()
    def fake_stream(*a, **kw):
        raw = outputs.pop(0) if outputs else "{}"
        return (raw, None, 0.1, None)
    return mock, fake_stream


def test_extract_with_mock_client():
    from fr_cli.agent.insight_extractor import InsightExtractor
    from fr_cli.agent import insight_storage as st

    # 准备 mock client: 80 条数据分 2 批 + 1 次聚合 = 3 次 LLM 调用
    outputs = [
        json.dumps({
            "summary": "batch1 总结",
            "categories": [{"name": "女装/连衣裙", "hit_rate": "高", "evidence": "1"}],
            "price_bands": [{"range": "50-200", "verdict": "高频", "evidence": "60%"}],
            "lifecycle_patterns": [{"pattern": "7-14", "description": "快"}],
            "seasonal_trends": [],
            "key_signals": ["信号1"],
        }, ensure_ascii=False),
        json.dumps({
            "summary": "batch2 总结",
            "categories": [{"name": "3C/充电宝", "hit_rate": "中", "evidence": "2"}],
            "price_bands": [],
            "lifecycle_patterns": [],
            "seasonal_trends": [],
            "key_signals": ["信号2"],
        }, ensure_ascii=False),
        json.dumps({
            "summary": "全局规律一句话",
            "categories": [{"name": "女装/连衣裙", "hit_rate": "高", "evidence": "跨批次",
                            "key_signals": ["应季"]}],
            "price_bands": [{"range": "50-200", "verdict": "高频", "evidence": "跨批次"}],
            "lifecycle_patterns": [{"pattern": "7-14 天爆发", "description": "应季品规律"}],
            "seasonal_trends": [{"signal": "Q3 连衣裙", "evidence": "跨批次"}],
            "key_signals": ["核心信号 1", "核心信号 2"],
        }, ensure_ascii=False),
    ]
    mock_client, fake_stream = _mock_client_factory(outputs)

    with patch("fr_cli.core.stream.stream_cnt", side_effect=fake_stream):
        extractor = InsightExtractor(
            client=mock_client,
            model_name="mock-model",
            lang="zh",
            source=None,  # 用默认
            batch_size=40,  # 80 条 mock 数据 → 2 批
        )
        result = extractor.extract()

    assert result["skipped"] is False
    assert result["batch_count"] == 2
    assert result["record_count"] == 80
    insights = result["insights"]
    assert insights["summary"] == "全局规律一句话"
    assert "应季" in insights["key_signals"] or any(
        "应季" in (c.get("key_signals") or []) for c in insights["categories"]
    )

    # 持久化检查
    latest = st.load_latest()
    assert latest is not None
    assert latest["source_name"] == "mock"
    assert latest["record_count"] == 80


def test_extract_handles_llm_codeblock():
    """LLM 返回带 markdown code block 的 JSON 也能正确解析"""
    from fr_cli.agent.insight_extractor import InsightExtractor

    wrapped_payload = {
        "summary": "wrapped",
        "categories": [], "price_bands": [], "lifecycle_patterns": [],
        "seasonal_trends": [], "key_signals": [],
    }
    wrapped = "```json\n" + json.dumps(wrapped_payload, ensure_ascii=False) + "\n```"
    # 80 条数据分 2 批 + 1 次聚合,3 次 LLM 调用
    mock_client, fake_stream = _mock_client_factory([wrapped, wrapped, wrapped])
    with patch("fr_cli.core.stream.stream_cnt", side_effect=fake_stream):
        ex = InsightExtractor(client=mock_client, model_name="m", lang="zh", batch_size=40)
        r = ex.extract()
    assert r["skipped"] is False
    assert r["insights"]["summary"] == "wrapped"


def test_extract_no_records_skipped():
    """无数据时返回 skipped"""
    from fr_cli.agent.insight_extractor import InsightExtractor
    from fr_cli.agent.insight_source import MockSelectionSource

    ex = InsightExtractor(client=MagicMock(), model_name="m", lang="zh",
                          source=MockSelectionSource(count=0), batch_size=10)
    r = ex.extract()
    assert r["skipped"] is True
    assert r["reason"] == "no_records"


def test_extract_no_client_returns_empty_batches_skipped():
    """无 LLM client 时,所有 batch 都会失败,聚合也失败 → skipped"""
    from fr_cli.agent.insight_extractor import InsightExtractor
    from fr_cli.agent.insight_source import MockSelectionSource

    ex = InsightExtractor(client=None, model_name=None, lang="zh",
                          source=MockSelectionSource(count=20), batch_size=10)
    r = ex.extract()
    assert r["skipped"] is True


# ---------- Dream 集成 ----------

def test_dream_runs_insight_extract_when_source_provided(tmp_path):
    """DreamEngine 配 selection_source 时,dream_now 末尾会顺带跑 insight_extract"""
    from fr_cli.agent.dream import DreamEngine
    from fr_cli.agent.insight_source import MockSelectionSource

    # 准备 memory.json 让 dream 有内容可整理
    import fr_cli.conf.paths as _paths
    memory = {"interactions": [
        {"time": "2026-08-13T10:00:00", "input": f"测试{i}",
         "tool": "search_web", "success": True, "detail": "ok",
         "error_type": None}
        for i in range(5)
    ]}
    (_paths.MASTER_DIR / "memory.json").write_text(
        json.dumps(memory, ensure_ascii=False), encoding="utf-8"
    )

    # mock client
    outputs = [
        json.dumps({
            "summary": "dream summary",
            "themes": [{"name": "theme1", "description": "d", "frequency": "高"}],
            "preferences": ["p1"], "best_practices": [], "improvements": [],
        }, ensure_ascii=False),
        json.dumps({
            "summary": "insight from dream",
            "categories": [], "price_bands": [], "lifecycle_patterns": [],
            "seasonal_trends": [], "key_signals": [],
        }, ensure_ascii=False),
    ]
    call_count = [0]
    def fake_stream(*a, **kw):
        raw = outputs[call_count[0]]
        call_count[0] += 1
        return (raw, None, 0.1, None)

    with patch("fr_cli.core.stream.stream_cnt", side_effect=fake_stream):
        engine = DreamEngine(
            client=MagicMock(), model_name="mock",
            lang="zh",
            selection_source=MockSelectionSource(count=10),
        )
        result = engine.dream_now(lookback=5)

    assert result["skipped"] is False
    assert "insight_extract" in result
    assert result["insight_extract"]["skipped"] is False
    assert result["insight_extract"]["summary"] == "insight from dream"


def test_dream_skips_insight_when_no_source():
    """不传 selection_source 时,Dream 不会跑 insight_extract"""
    from fr_cli.agent.dream import DreamEngine

    import fr_cli.conf.paths as _paths
    memory = {"interactions": [
        {"time": "2026-08-13T10:00:00", "input": f"t{i}",
         "tool": "search_web", "success": True, "detail": "ok", "error_type": None}
        for i in range(5)
    ]}
    (_paths.MASTER_DIR / "memory.json").write_text(
        json.dumps(memory, ensure_ascii=False), encoding="utf-8"
    )

    out = json.dumps({
        "summary": "no insight",
        "themes": [{"name": "t", "description": "d", "frequency": "中"}],
        "preferences": [], "best_practices": [], "improvements": [],
    }, ensure_ascii=False)

    with patch("fr_cli.core.stream.stream_cnt", return_value=(out, None, 0.1, None)):
        engine = DreamEngine(client=MagicMock(), model_name="m", lang="zh")
        result = engine.dream_now(lookback=5)

    assert result["skipped"] is False
    assert "insight_extract" not in result


# ---------- MasterAgent prompt 注入 ----------

def test_master_prompt_includes_insights_when_available():
    """master_prompt_builder 在有洞察档案时,会注入 [选品经验] 段落"""
    from fr_cli.agent import insight_storage as st
    st.save({
        "summary": "测试注入",
        "categories": [{"name": "X", "hit_rate": "高", "evidence": "1", "key_signals": []}],
        "price_bands": [],
        "lifecycle_patterns": [],
        "seasonal_trends": [],
        "key_signals": ["关键信号"],
    }, source_name="mock", record_count=10)

    class _FakeSecurity:
        autonomous_mode = "manual"
    class _FakeState:
        lang = "zh"
        security = _FakeSecurity()
        client = None
        model_name = "test"
        messages = []
        vfs = None
    state = _FakeState()

    # 用 mixin 本身的 _build_insights_section,避免重复造轮子
    from fr_cli.agent.master_prompt_builder import MasterAgentPromptMixin
    class _Stub(MasterAgentPromptMixin):
        def __init__(self, state):
            self.state = state
            self.persona = ""
            self.skills = ""
            self.evolution = {}
            self.session = {}
        def _build_tools_desc(self):
            return "(stub tools)"
    stub = _Stub(state)
    prompt = stub._build_system_prompt(lang="zh")
    assert "[选品经验]" in prompt
    assert "测试注入" in prompt


def test_master_prompt_omits_insights_when_empty():
    """master_prompt_builder 在没洞察档案时,不会注入 [选品经验]"""
    class _FakeSecurity:
        autonomous_mode = "manual"
    class _FakeState:
        lang = "zh"
        security = _FakeSecurity()
        client = None
        model_name = "test"
        messages = []
        vfs = None
    state = _FakeState()

    from fr_cli.agent.master_prompt_builder import MasterAgentPromptMixin
    class _Stub(MasterAgentPromptMixin):
        def __init__(self, state):
            self.state = state
            self.persona = ""
            self.skills = ""
            self.evolution = {}
            self.session = {}
        def _build_tools_desc(self):
            return "(stub tools)"
    stub = _Stub(state)
    prompt = stub._build_system_prompt(lang="zh")
    assert "[选品经验]" not in prompt


# ---------- 端到端 smoke test ----------

def test_e2e_insight_command_to_prompt_injection():
    """端到端:模拟 /insight extract 命令,验证整条链路(路由→extractor→存储→prompt 注入)"""
    from fr_cli.repl.commands.insight import _cmd_insight
    from fr_cli.agent import insight_storage as st

    # 准备 mock client:80 条数据分 2 批 + 1 次聚合
    outputs = [
        json.dumps({"summary": "b1", "categories": [], "price_bands": [],
                    "lifecycle_patterns": [], "seasonal_trends": [], "key_signals": []},
                   ensure_ascii=False),
        json.dumps({"summary": "b2", "categories": [], "price_bands": [],
                    "lifecycle_patterns": [], "seasonal_trends": [], "key_signals": []},
                   ensure_ascii=False),
        json.dumps({"summary": "E2E 端到端验证洞察", "categories": [
                        {"name": "女装/连衣裙", "hit_rate": "高", "evidence": "跨批次",
                         "key_signals": ["应季"]}],
                    "price_bands": [{"range": "50-200", "verdict": "高频", "evidence": "x"}],
                    "lifecycle_patterns": [], "seasonal_trends": [], "key_signals": ["E2E 信号"]},
                   ensure_ascii=False),
    ]
    call_count = [0]
    def fake_stream(*a, **kw):
        raw = outputs[call_count[0]] if call_count[0] < len(outputs) else "{}"
        call_count[0] += 1
        return (raw, None, 0.1, None)

    class _FakeVfs:
        cwd = "/fake/cwd"
    class _FakeSecurity:
        autonomous_mode = "manual"
    class _FakeState:
        lang = "zh"
        security = _FakeSecurity()
        client = MagicMock()
        model_name = "mock-model"
        display_model = "mock-model"
        messages = []
        vfs = _FakeVfs()

    state = _FakeState()
    parts = ["/insight", "extract", "--batch", "40"]  # 80 条 / 40 = 2 批

    with patch("fr_cli.core.stream.stream_cnt", side_effect=fake_stream):
        result = _cmd_insight(state, parts)
    assert result is False  # 不退出 REPL

    # 链路产物 1:磁盘上有 latest.json
    latest = st.load_latest()
    assert latest is not None
    assert latest["source_name"] == "mock"
    assert latest["record_count"] == 80
    assert latest["insights"]["summary"] == "E2E 端到端验证洞察"

    # 链路产物 2:MasterAgent prompt 能读出
    from fr_cli.agent.master_prompt_builder import MasterAgentPromptMixin
    class _Stub(MasterAgentPromptMixin):
        def __init__(self, state):
            self.state = state
            self.persona = ""
            self.skills = ""
            self.evolution = {}
            self.session = {}
        def _build_tools_desc(self):
            return "(stub)"
    class _S:
        lang = "zh"
        security = _FakeSecurity()
        client = None
        model_name = "m"
        messages = []
        vfs = None
    stub = _Stub(_S())
    prompt = stub._build_system_prompt(lang="zh")
    assert "[选品经验]" in prompt
    assert "E2E 端到端验证洞察" in prompt
    assert "应季" in prompt  # 来自 key_signals 注入


def test_e2e_insight_alias_extract_routes_correctly():
    """端到端:验证 /insight_extract 别名也走相同链路"""
    from fr_cli.repl.commands.insight import _cmd_insight_extract
    from fr_cli.agent import insight_storage as st

    outputs = [
        json.dumps({"summary": "b1", "categories": [], "price_bands": [],
                    "lifecycle_patterns": [], "seasonal_trends": [], "key_signals": []},
                   ensure_ascii=False),
        json.dumps({"summary": "b2", "categories": [], "price_bands": [],
                    "lifecycle_patterns": [], "seasonal_trends": [], "key_signals": []},
                   ensure_ascii=False),
        json.dumps({"summary": "alias 路径 OK", "categories": [], "price_bands": [],
                    "lifecycle_patterns": [], "seasonal_trends": [],
                    "key_signals": ["alias 信号"]},
                   ensure_ascii=False),
    ]
    call_count = [0]
    def fake_stream(*a, **kw):
        raw = outputs[call_count[0]] if call_count[0] < len(outputs) else "{}"
        call_count[0] += 1
        return (raw, None, 0.1, None)

    class _FakeVfs:
        cwd = "/x"
    class _FakeSecurity:
        autonomous_mode = "manual"
    class _FakeState:
        lang = "zh"
        security = _FakeSecurity()
        client = MagicMock()
        model_name = "m"
        display_model = "m"
        messages = []
        vfs = _FakeVfs()
    state = _FakeState()

    with patch("fr_cli.core.stream.stream_cnt", side_effect=fake_stream):
        result = _cmd_insight_extract(state, ["/insight_extract", "--batch", "40"])

    assert result is False
    latest = st.load_latest()
    assert latest is not None
    assert latest["insights"]["summary"] == "alias 路径 OK"
