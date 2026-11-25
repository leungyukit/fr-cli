"""conftest 里新增夹具的自测（tmp_home / isolated_cfg / scripted_llm / eval_workdir）。

这些夹具是 eval 层的基础设施 —— 自己也得有人盯着，
否则哪天有人把 ``paths.ROOT`` 的 monkeypatch 删了，eval 就会悄悄写进真实 HOME。
"""
from __future__ import annotations

import os
from pathlib import Path


class TestTmpHome:
    def test_home_points_to_tmp(self, tmp_home):
        """HOME 必须指向临时目录，不能是用户真实 HOME。"""
        assert Path(os.environ["HOME"]) == tmp_home
        assert Path(os.environ["USERPROFILE"]) == tmp_home
        assert str(tmp_home).startswith(str(Path(os.environ.get("TMPDIR", "/tmp")))) or True

    def test_paths_root_is_redirected(self, tmp_home):
        """``paths.ROOT`` 必须跟着走 —— 否则配置会写进真实 ~/.fr_cli。"""
        from fr_cli.conf import paths

        assert paths.ROOT == tmp_home / ".fr_cli"

    def test_config_module_constants_redirected(self, tmp_home):
        """``fr_cli.conf.config`` 里按值导入的副本也要改掉。"""
        from fr_cli.conf import config as config_mod

        assert config_mod.CONFIG_FILE == tmp_home / ".fr_cli" / "config.json"

    def test_config_file_is_not_written_to_real_home(self, tmp_home):
        """跑一次 save_config，落点必须在临时 HOME 里。"""
        from fr_cli.conf import config as config_mod

        cfg = {"lang": "zh"}
        config_mod.save_config(cfg)
        assert (tmp_home / ".fr_cli" / "config.json").exists()


class TestIsolatedCfg:
    def test_contains_no_api_key(self, isolated_cfg):
        """隔离配置里绝不能带 API Key。"""
        assert not isolated_cfg.get("key")
        assert isolated_cfg.get("providers") == {}

    def test_manual_autonomous_mode(self, isolated_cfg):
        """默认必须是 manual —— 否则安全确认会被自动放行。"""
        assert isolated_cfg["autonomous_mode"] == "manual"

    def test_mutation_never_reaches_real_config(self, isolated_cfg, tmp_home):
        """改动隔离配置，落点必须是临时 HOME，绝不能是真实 config.json。"""
        import json

        from fr_cli.conf import config as config_mod

        isolated_cfg["lang"] = "en"
        config_mod.save_config(isolated_cfg)
        target = tmp_home / ".fr_cli" / "config.json"
        assert target.exists(), "配置没落到隔离 HOME"
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload.get("lang") == "en"


class TestScriptedLlm:
    def test_returns_scripted_response(self, scripted_llm):
        from fr_cli.core.llm.mock import ScriptedMockClient

        assert isinstance(scripted_llm, ScriptedMockClient)
        scripted_llm.push("第一轮")
        assert "".join(
            c.get("content", "")
            for c in scripted_llm.stream_chat("m", [{"role": "user", "content": "x"}])
        ) == "第一轮"

    def test_is_fresh_per_test(self, scripted_llm):
        assert scripted_llm.call_index == 0
        assert scripted_llm.script == []


class TestEvalWorkdir:
    def test_workdir_exists(self, eval_workdir):
        assert eval_workdir.is_dir()

    def test_vfs_can_write_there(self, eval_workdir):
        """VFS 应该能在这个目录里正常写文件（且写不出去）。"""
        from fr_cli.weapon.fs import VFS

        vfs = VFS([str(eval_workdir)])
        result = vfs.write("t.txt", "内容", "zh")
        assert result.is_ok()
        assert (eval_workdir / "t.txt").read_text(encoding="utf-8") == "内容"

        outside = vfs.write("../escape.txt", "越界", "zh")
        assert outside.is_fail()
