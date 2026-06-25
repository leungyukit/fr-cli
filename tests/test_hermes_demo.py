"""
Hermes 端到端 Demo 测试

模拟一个多步研究任务：AI 先调用 write_file 写报告，然后给出最终总结。
验证：
  1. Hermes 任务创建后持久化
  2. 调度器/执行器在 sandbox_auto 模式下自动放行 write_file
  3. 文件确实写入 VFS 沙盒
  4. 用户主会话 state.messages 不被污染
"""
import shutil
import sys
import tempfile
from pathlib import Path


project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class DemoTestEnv:
    """为 demo 测试创建隔离的真实环境"""

    def __init__(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="fr_cli_hermes_demo_"))
        self.agents_dir = self.tmpdir / "agents"
        self.config_file = self.tmpdir / "config.json"
        self.workspace = self.tmpdir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.agents_dir.mkdir(parents=True, exist_ok=True)

        import fr_cli.agent.manager as mgr
        self._orig_agents_dir = mgr.AGENTS_DIR
        mgr.AGENTS_DIR = self.agents_dir

        self._orig_home = Path.home
        Path.home = lambda: self.tmpdir

        # 隔离 Hermes 路径
        import fr_cli.agent.hermes as hermes_mod
        self._orig_hermes_dir = hermes_mod.HERMES_DIR
        self._orig_tasks_file = hermes_mod.HERMES_TASKS_FILE
        self._orig_goals_file = hermes_mod.HERMES_GOALS_FILE
        self._orig_analytics_file = hermes_mod.HERMES_ANALYTICS_FILE
        self._orig_log_file = hermes_mod.HERMES_LOG_FILE
        hermes_mod.HERMES_DIR = self.tmpdir / "hermes"
        hermes_mod.HERMES_TASKS_FILE = hermes_mod.HERMES_DIR / "tasks.json"
        hermes_mod.HERMES_GOALS_FILE = hermes_mod.HERMES_DIR / "goals.json"
        hermes_mod.HERMES_ANALYTICS_FILE = hermes_mod.HERMES_DIR / "analytics.json"
        hermes_mod.HERMES_LOG_FILE = hermes_mod.HERMES_DIR / "hermes.log"

    def cleanup(self):
        import fr_cli.agent.manager as mgr
        mgr.AGENTS_DIR = self._orig_agents_dir
        Path.home = self._orig_home

        import fr_cli.agent.hermes as hermes_mod
        hermes_mod.HERMES_DIR = self._orig_hermes_dir
        hermes_mod.HERMES_TASKS_FILE = self._orig_tasks_file
        hermes_mod.HERMES_GOALS_FILE = self._orig_goals_file
        hermes_mod.HERMES_ANALYTICS_FILE = self._orig_analytics_file
        hermes_mod.HERMES_LOG_FILE = self._orig_log_file

        shutil.rmtree(self.tmpdir, ignore_errors=True)


def test_hermes_research_demo():
    """端到端：Hermes 后台任务自动写报告到沙盒"""
    env = DemoTestEnv()
    try:
        # 准备配置
        from fr_cli.conf.config import load_config, save_config
        import fr_cli.conf.config as conf_mod
        orig_config_file = conf_mod.CONFIG_FILE
        orig_backup = conf_mod.CONFIG_BACKUP
        conf_mod.CONFIG_FILE = env.config_file
        conf_mod.CONFIG_BACKUP = env.tmpdir / "config.json.bak"

        cfg = load_config()
        cfg["provider"] = "zhipu"
        cfg["model"] = "glm-4-flash"
        cfg["key"] = "fake-key"
        cfg["providers"] = {"zhipu": {"key": "fake-key", "model": "glm-4-flash"}}
        cfg["allowed_dirs"] = [str(env.workspace)]
        save_config(cfg)

        from fr_cli.core.core import AppState
        state = AppState(cfg)

        # 设置沙盒自动模式
        state.security.set_autonomous_mode("sandbox_auto")

        original_messages = list(state.messages)

        # mock stream_cnt：第一次返回 write_file 调用，第二次返回最终回答
        call_count = [0]
        report_path = str(env.workspace / "report.md")
        report_content = "# AI Agent 调研报告\\n\\n这是自动生成的报告。"

        def fake_stream_cnt(client, model, messages, lang, custom_prefix="", max_tokens=2048, silent=True):
            call_count[0] += 1
            if call_count[0] == 1:
                text = f'```tool\n{{"tool": "write_file", "params": {{"path": "{report_path}", "content": "{report_content}"}}}}\n```'
            else:
                text = "报告已写入 workspace/report.md。"
            # stream_cnt 返回 (text, usage, something, something)
            return text, None, None, None

        import fr_cli.core.stream as stream_mod
        orig_stream_cnt = stream_mod.stream_cnt
        stream_mod.stream_cnt = fake_stream_cnt

        try:
            # 创建并执行后台任务
            task = state.hermes.create_task(
                "写一份 AI Agent 调研报告到 workspace/report.md",
                source="repl",
                execution_mode="sandbox",
            )
            # 手动执行，避免等待调度器轮询
            state.hermes._execute_task(task)
        finally:
            stream_mod.stream_cnt = orig_stream_cnt
            conf_mod.CONFIG_FILE = orig_config_file
            conf_mod.CONFIG_BACKUP = orig_backup

        # 验证文件已写入
        expected_file = env.workspace / "report.md"
        assert expected_file.exists(), f"报告文件未写入: {expected_file}"
        expected_content = report_content.replace("\\n", "\n")
        assert expected_content in expected_file.read_text(encoding="utf-8")

        # 验证任务状态
        assert task.status.value == "completed"

        # 验证用户主会话未被污染
        assert state.messages == original_messages

        # 验证 Hermes 任务已持久化
        persisted = state.hermes.get_task(task.id)
        assert persisted is not None
        assert persisted.status.value == "completed"

        print("✅ test_hermes_research_demo 通过")
    finally:
        env.cleanup()
