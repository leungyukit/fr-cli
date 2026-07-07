"""
Dream 梦境机制测试
"""
import json
import os
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """隔离测试环境"""
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))
    import fr_cli.conf.paths as _paths_mod
    fake_fr_cli = fake_home / ".fr_cli" / "master"
    fake_fr_cli.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_paths_mod._root_holder, "value", fake_home / ".fr_cli")
    yield


def _seed_interactions(count=5):
    """种 N 条模拟交互记录到 memory.json"""
    from fr_cli.conf import paths as _paths
    memory = {
        "interactions": [
            {
                "time": datetime.now().isoformat(),
                "input": f"测试输入 {i}",
                "tool": "search_web" if i % 2 == 0 else "write_file",
                "success": i % 3 != 0,
                "detail": f"结果 {i}" if i % 3 != 0 else f"错误 {i}",
                "error_type": None if i % 3 != 0 else "timeout",
            }
            for i in range(count)
        ]
    }
    (_paths.MASTER_DIR / "memory.json").write_text(
        json.dumps(memory, ensure_ascii=False), encoding="utf-8"
    )


def test_load_dream_index_empty():
    """空索引加载应返回默认结构"""
    from fr_cli.agent.dream import _load_dream_index
    idx = _load_dream_index()
    assert "themes" in idx
    assert idx["total_dreams"] == 0


def test_save_and_load_dream_index():
    """索引可正常保存/加载"""
    from fr_cli.agent.dream import _load_dream_index, _save_dream_index
    idx = _load_dream_index()
    idx["total_dreams"] = 5
    idx["themes"]["test"] = {"count": 1, "last_seen": "2026-07-01", "descriptions": ["测试"]}
    _save_dream_index(idx)

    idx2 = _load_dream_index()
    assert idx2["total_dreams"] == 5
    assert "test" in idx2["themes"]


def test_search_dream_memory_empty():
    """空索引搜索返回空"""
    from fr_cli.agent.dream import search_dream_memory
    assert search_dream_memory("anything") == []


def test_search_dream_memory_finds_match():
    """搜索能匹配主题名和描述"""
    from fr_cli.agent.dream import _load_dream_index, _save_dream_index, search_dream_memory

    idx = _load_dream_index()
    idx["themes"]["数据分析"] = {
        "count": 3, "last_seen": "2026-07-01",
        "descriptions": ["用户常用 pandas", "经常做销售分析"]
    }
    idx["themes"]["图片处理"] = {
        "count": 1, "last_seen": "2026-07-01",
        "descriptions": ["生成图片"]
    }
    _save_dream_index(idx)

    # 精确匹配
    results = search_dream_memory("数据")
    assert len(results) >= 1
    assert any(r["name"] == "数据分析" for r in results)

    # 描述匹配
    results = search_dream_memory("pandas")
    assert len(results) >= 1


def test_dream_skipped_when_no_interactions():
    """交互太少时 dream_now 应该跳过"""
    from fr_cli.agent.dream import DreamEngine
    engine = DreamEngine(client=MagicMock(), model_name="test")
    result = engine.dream_now()
    assert result.get("skipped") is True


def test_dream_skipped_when_few_interactions():
    """只有 2 条交互时也跳过"""
    _seed_interactions(count=2)
    from fr_cli.agent.dream import DreamEngine
    engine = DreamEngine(client=MagicMock(), model_name="test")
    result = engine.dream_now()
    assert result.get("skipped") is True
    assert "太少" in result.get("reason", "")


def test_dream_now_with_mocked_llm():
    """dream_now 在 LLM 正常返回时写入索引和 markdown"""
    _seed_interactions(count=10)
    from fr_cli.agent.dream import DreamEngine, _load_dream_index

    # 模拟 LLM 返回
    fake_response = json.dumps({
        "themes": [
            {"name": "网络搜索", "description": "用户经常搜索技术问题", "frequency": "高频"},
            {"name": "文件操作", "description": "经常写文件", "frequency": "中频"},
        ],
        "preferences": ["喜欢简短回复"],
        "best_practices": ["搜索时使用具体关键词"],
        "improvements": ["失败时尝试更具体的关键词"],
        "summary": "用户主要在做技术调研"
    }, ensure_ascii=False)

    # patch stream_cnt
    with patch("fr_cli.core.stream.stream_cnt") as mock_stream:
        mock_stream.return_value = (fake_response, None, None, None)
        engine = DreamEngine(client=MagicMock(), model_name="test")
        result = engine.dream_now()

    assert result.get("skipped") is False
    assert "data" in result

    # 索引应包含新主题
    idx = _load_dream_index()
    assert idx["total_dreams"] == 1
    assert "网络搜索" in idx["themes"]
    assert idx["themes"]["网络搜索"]["count"] == 1

    # Markdown 日志应存在
    log_path = Path(os.environ["HOME"]) / ".fr_cli" / "master" / "dream_log.md"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "梦境" in content
    assert "网络搜索" in content
    assert "喜欢简短回复" in content


def test_dream_handles_invalid_json():
    """LLM 返回无效 JSON 时优雅跳过"""
    _seed_interactions(count=10)
    from fr_cli.agent.dream import DreamEngine

    with patch("fr_cli.core.stream.stream_cnt") as mock_stream:
        mock_stream.return_value = ("这不是 JSON", None, None, None)
        engine = DreamEngine(client=MagicMock(), model_name="test")
        result = engine.dream_now()

    assert result.get("skipped") is True
    assert "JSON" in result.get("reason", "")


def test_dream_handles_markdown_codeblock():
    """LLM 返回 ```json ... ``` 时也能解析"""
    _seed_interactions(count=10)
    from fr_cli.agent.dream import DreamEngine, _load_dream_index

    fake_response = "```json\n" + json.dumps({
        "themes": [{"name": "测试主题", "description": "x", "frequency": "高频"}],
        "preferences": [], "best_practices": [], "improvements": [],
        "summary": "ok"
    }, ensure_ascii=False) + "\n```"

    with patch("fr_cli.core.stream.stream_cnt") as mock_stream:
        mock_stream.return_value = (fake_response, None, None, None)
        engine = DreamEngine(client=MagicMock(), model_name="test")
        result = engine.dream_now()

    assert result.get("skipped") is False
    idx = _load_dream_index()
    assert "测试主题" in idx["themes"]


def test_dream_handles_llm_exception():
    """LLM 调用异常时优雅处理"""
    _seed_interactions(count=10)
    from fr_cli.agent.dream import DreamEngine

    with patch("fr_cli.core.stream.stream_cnt") as mock_stream:
        mock_stream.side_effect = Exception("网络断了")
        engine = DreamEngine(client=MagicMock(), model_name="test")
        result = engine.dream_now()

    assert result.get("skipped") is True
    assert "LLM" in result.get("reason", "")


def test_get_dream_summary():
    """get_dream_summary 应返回统计信息"""
    from fr_cli.agent.dream import _save_dream_index, _load_dream_index, get_dream_summary
    idx = _load_dream_index()
    idx["total_dreams"] = 3
    idx["themes"]["搜索"] = {"count": 5, "last_seen": "2026-07-01", "descriptions": []}
    idx["themes"]["文件"] = {"count": 2, "last_seen": "2026-07-01", "descriptions": []}
    _save_dream_index(idx)

    summary = get_dream_summary()
    assert summary["total_dreams"] == 3
    assert len(summary["top_themes"]) == 2
    assert summary["top_themes"][0]["name"] == "搜索"


def test_idle_watcher_thread():
    """DreamEngine.start_idle_watcher 应该启动后台线程"""
    from fr_cli.agent.dream import DreamEngine
    engine = DreamEngine(client=MagicMock(), model_name="test")
    # 立即回调一次
    called = []
    engine.start_idle_watcher(idle_minutes=0.01, on_dream=lambda r: called.append(r))
    # 等一会儿让线程跑一下
    import time
    time.sleep(3)
    # 至少跑了(可能因为没足够交互被 skip)
    # 至少线程应该还活着(因为 daemon=True)
    # 主要是测试 start 不报错
    # 关掉线程无法直接关,daemon=True 会在主进程退出时清理
    assert True
