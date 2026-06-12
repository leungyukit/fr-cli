"""
批处理 / 非交互模式测试

验证 fr-cli 可以在不进入 REPL 的情况下执行单条命令或单次对话。
"""
import os
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest


class TestBatchArgumentParser:
    """测试命令行参数解析"""

    def _parse(self, argv):
        from fr_cli.main import _build_parser, _get_batch_input
        parser = _build_parser()
        args = parser.parse_args(argv)
        return _get_batch_input(args), args

    def test_positional_prompt(self):
        (text, is_cmd), args = self._parse(["你好"])
        assert text == "你好"
        assert is_cmd is False

    def test_multiple_positional_prompt(self):
        (text, is_cmd), args = self._parse(["请", "总结", "README.md"])
        assert text == "请 总结 README.md"
        assert is_cmd is False

    def test_prompt_option(self):
        (text, is_cmd), args = self._parse(["-p", "Python 如何读取 JSON？"])
        assert text == "Python 如何读取 JSON？"
        assert is_cmd is False

    def test_command_option(self):
        (text, is_cmd), args = self._parse(["-c", "/model current"])
        assert text == "/model current"
        assert is_cmd is True

    def test_no_batch_mode(self):
        (text, is_cmd), args = self._parse([])
        assert text is None
        assert is_cmd is False

    def test_quiet_flag(self):
        _, args = self._parse(["-q", "-c", "/model current"])
        assert args.quiet is True


class TestBatchRun:
    """测试批处理执行器"""

    def _make_state(self):
        state = MagicMock()
        state.aliases = {}
        state.messages = []
        state._queue_mgr = None
        return state

    def test_run_batch_empty_input(self, capsys):
        from fr_cli.repl.batch import run_batch
        state = self._make_state()
        rc = run_batch(state, "   ", quiet=True)
        assert rc == 0

    def test_run_batch_command(self):
        from fr_cli.repl.batch import run_batch
        state = self._make_state()
        with patch("fr_cli.repl.router.dispatch") as mock_dispatch:
            mock_dispatch.return_value = False
            rc = run_batch(state, "/model current", is_command=True, quiet=True)
        assert rc == 0
        mock_dispatch.assert_called_once_with(state, "/model current")

    def test_run_batch_command_exit(self):
        from fr_cli.repl.batch import run_batch
        state = self._make_state()
        with patch("fr_cli.repl.router.dispatch") as mock_dispatch:
            mock_dispatch.return_value = True
            rc = run_batch(state, "/exit", is_command=True, quiet=True)
        assert rc == 0

    def test_run_batch_prompt(self):
        from fr_cli.repl.batch import run_batch
        state = self._make_state()
        with patch("fr_cli.core.chat.handle_ai_chat") as mock_chat:
            rc = run_batch(state, "你好", is_command=False, quiet=True)
        assert rc == 0
        mock_chat.assert_called_once_with(state, "你好")

    def test_run_batch_sets_non_interactive_env(self):
        from fr_cli.repl.batch import run_batch
        state = self._make_state()
        # 先清除环境变量
        old = os.environ.pop("FR_CLI_NON_INTERACTIVE", None)
        try:
            with patch("fr_cli.repl.router.dispatch", return_value=False):
                run_batch(state, "/model current", is_command=True, quiet=True)
            assert os.environ.get("FR_CLI_NON_INTERACTIVE") == "1"
        finally:
            if old is not None:
                os.environ["FR_CLI_NON_INTERACTIVE"] = old
            else:
                os.environ.pop("FR_CLI_NON_INTERACTIVE", None)


class TestBootstrapShowBanner:
    """测试启动引导的 banner 控制参数"""

    def test_bootstrap_accepts_show_banner(self):
        from fr_cli.repl.bootstrap import bootstrap
        # 通过 mock 确保 show_banner=False 不调用 print_startup_banner
        with patch("fr_cli.repl.bootstrap.print_startup_banner") as mock_banner:
            with patch("fr_cli.repl.bootstrap.init_config") as mock_init:
                cfg = {"lang": "zh", "allowed_dirs": [], "provider": "zhipu"}
                mock_init.return_value = cfg
                with patch("fr_cli.repl.bootstrap.AppState") as MockState:
                    MockState.return_value = MagicMock()
                    bootstrap(show_logo=False, show_banner=False)
        mock_banner.assert_not_called()
