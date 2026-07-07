"""
Agent 分身创建与调用测试
覆盖：
1. create_agent_dir 初始化 workflow.md
2. load_agent_description 从 persona.md 提取描述
3. dispatch_agent_call 解析 @agent_name 并调用
4. discover_all_agents 使用友好描述
5. generate_agent 默认兜底代码和工作流
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def temp_agents_dir(tmp_path, monkeypatch):
    """使用临时目录作为 Agent 根目录，避免污染真实 ~/.fr_cli/agents"""
    d = tmp_path / "agents"
    d.mkdir(parents=True, exist_ok=True)
    import fr_cli.agent
    # 通过改 _root_holder.value 让所有路径都指向 tmp_path
    # AGENTS_DIR = ROOT / "agents",所以 ROOT = tmp_path 时自然指向 tmp_path/agents
    monkeypatch.setattr(fr_cli.conf.paths._root_holder, "value", tmp_path)
    return tmp_path / "agents"


class TestAgentManager:
    """测试 Agent 管理器"""

    def test_create_agent_dir_initializes_workflow(self, temp_agents_dir):
        """create_agent_dir 应初始化 workflow.md"""
        from fr_cli.agent.manager import create_agent_dir, WORKFLOW_FILE

        d = create_agent_dir("test_agent")
        workflow_path = d / WORKFLOW_FILE

        assert workflow_path.exists()
        content = workflow_path.read_text(encoding="utf-8")
        assert "# test_agent 工作流" in content
        assert "步骤1" in content

    def test_load_agent_description_from_persona(self, temp_agents_dir):
        """load_agent_description 应从 persona.md 第一行提取标题"""
        from fr_cli.agent.manager import create_agent_dir, save_persona, load_agent_description

        create_agent_dir("desc_agent")
        save_persona("desc_agent", "# 代码助手\n\n帮我写代码。\n")

        desc = load_agent_description("desc_agent")
        assert desc == "代码助手"

    def test_load_agent_description_empty(self, temp_agents_dir):
        """persona 文件不存在或为空时返回空字符串"""
        from fr_cli.agent.manager import create_agent_dir, load_agent_description, _agent_dir, PERSONA_FILE

        create_agent_dir("empty_agent")
        # create_agent_dir 会生成默认 persona，删除后测试空路径
        (_agent_dir("empty_agent") / PERSONA_FILE).unlink()
        assert load_agent_description("empty_agent") == ""


class TestAgentDispatch:
    """测试 @agent_name 调度器"""

    def test_parse_at_command(self):
        """测试 @agent_name 解析"""
        from fr_cli.agent.dispatch import _parse_at_command

        assert _parse_at_command("@coder 写代码") == ("coder", "写代码")
        assert _parse_at_command("@coder") == ("coder", "")
        assert _parse_at_command("hello") == (None, None)
        assert _parse_at_command("@  coder  多空格  任务") == ("coder", "多空格  任务")

    @patch("fr_cli.agent.dispatch.run_agent")
    @patch("fr_cli.agent.dispatch.agent_exists", return_value=True)
    def test_dispatch_agent_call_runs_agent(self, mock_exists, mock_run_agent, temp_agents_dir, capsys):
        """dispatch_agent_call 应调用 run_agent 并打印结果"""
        from fr_cli.agent.dispatch import dispatch_agent_call

        from fr_cli.core.result import Result
        mock_run_agent.return_value = Result.ok("执行结果")
        state = MagicMock()

        result = dispatch_agent_call(state, "@coder 写一个排序")

        assert result is True
        mock_run_agent.assert_called_once_with("coder", state, user_input="写一个排序")
        captured = capsys.readouterr()
        assert "正在召唤 Agent [coder]" in captured.out
        assert "执行结果" in captured.out

    @patch("fr_cli.agent.dispatch.agent_exists", return_value=False)
    def test_dispatch_agent_call_not_found(self, mock_exists, temp_agents_dir, capsys):
        """Agent 不存在时应提示"""
        from fr_cli.agent.dispatch import dispatch_agent_call

        state = MagicMock()
        result = dispatch_agent_call(state, "@not_exist 任务")

        assert result is True
        captured = capsys.readouterr()
        assert "Agent [not_exist] 不存在" in captured.out


class TestAgentClient:
    """测试 Agent 客户端发现"""

    def test_discover_all_agents_uses_description(self, temp_agents_dir):
        """discover_all_agents 应使用 persona.md 第一行作为描述"""
        from fr_cli.agent.manager import create_agent_dir, save_persona, save_agent_code
        from fr_cli.agent.client import discover_all_agents

        create_agent_dir("described_agent")
        save_persona("described_agent", "# 我的专属助手\n\n擅长写 Python。\n")
        save_agent_code("described_agent", "def run(context, **kwargs):\n    return 'ok'\n")

        agents = discover_all_agents()
        names = [a["name"] for a in agents]
        assert "described_agent" in names

        described = next(a for a in agents if a["name"] == "described_agent")
        assert described["description"] == "我的专属助手"
        assert described["type"] == "local"


class TestAgentGenerator:
    """测试 Agent 生成器"""

    def test_generate_agent_fallback_code_and_workflow(self):
        """当 LLM 返回空时，generate_agent 应返回兜底代码和工作流"""
        from fr_cli.agent.generator import generate_agent

        client = MagicMock()
        # stream_cnt 返回空字符串表示 LLM 没有生成内容
        with patch("fr_cli.agent.generator.stream_cnt", return_value=("", None, None, None)):
            result = generate_agent(client, "glm-4-flash", "fallback_agent", "测试兜底", lang="zh")

        assert result["code"]
        assert "def run(context, **kwargs):" in result["code"]
        assert "fallback_agent" in result["code"]
        assert result["workflow"]
        assert "fallback_agent 工作流" in result["workflow"]

    def test_generate_agent_extracts_all_sections(self):
        """测试正确解析 LLM 返回的四个部分"""
        from fr_cli.agent.generator import generate_agent

        raw = """
---PERSONA_START---
# test_agent

人设内容
---PERSONA_END---

---SKILLS_START---
## 技能
- 技能1
---SKILLS_END---

---CODE_START---
```python
def run(context, **kwargs):
    return "hello"
```
---CODE_END---

---WORKFLOW_START---
# test_agent 工作流

## 步骤1
- **action**: ai_generate
---WORKFLOW_END---
"""
        client = MagicMock()
        with patch("fr_cli.agent.generator.stream_cnt", return_value=(raw, None, None, None)):
            result = generate_agent(client, "glm-4-flash", "test_agent", "测试解析", lang="zh")

        assert "# test_agent" in result["persona"]
        assert "技能1" in result["skills"]
        assert "def run(context, **kwargs):" in result["code"]
        assert "return \"hello\"" in result["code"]
        assert "## 步骤1" in result["workflow"]
