"""
AI 回复产物检测器测试
"""
from unittest.mock import MagicMock

import pytest

from fr_cli.agent.artifact_detector import detect_plugin_artifact, detect_agent_artifact
from fr_cli.agent.review_queue import PersistentReviewQueue


@pytest.fixture
def tmp_review_queue(tmp_path, monkeypatch):
    path = tmp_path / "review_queue.json"
    monkeypatch.setattr("fr_cli.agent.review_queue.HERMES_REVIEW_QUEUE_FILE", path)
    return path


class TestDetectPluginArtifact:
    def test_non_interactive_queues_plugin(self, tmp_review_queue):
        state = MagicMock()
        txt = """```python\ndef run(args=''):\n    '''A longer plugin so that the detector does not reject it for being too short.'''\n    return 'hello'\n```"""
        assert detect_plugin_artifact(txt, "zh", state, interactive=False, task_id="t1") is True

        q = PersistentReviewQueue()
        items = q.list(status="pending")
        assert len(items) == 1
        assert items[0].artifact_type == "plugin"
        assert items[0].task_id == "t1"
        assert "def run" in items[0].code

    def test_no_artifact_returns_false(self, tmp_review_queue):
        state = MagicMock()
        assert detect_plugin_artifact("hello", "zh", state, interactive=False) is False


class TestDetectAgentArtifact:
    def test_non_interactive_queues_agent(self, tmp_review_queue):
        state = MagicMock()
        txt = """```python\ndef run(context, **kwargs):\n    '''A longer agent so that the detector does not reject it for being too short.'''\n    return 'hello'\n```"""
        assert detect_agent_artifact(txt, "zh", state, interactive=False, task_id="t2") is True

        q = PersistentReviewQueue()
        items = q.list(status="pending")
        assert len(items) == 1
        assert items[0].artifact_type == "agent"
        assert items[0].task_id == "t2"
