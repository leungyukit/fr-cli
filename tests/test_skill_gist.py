"""Skill Gist 远程共享测试"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fr_cli.weapon.skill_gist import (
    parse_gist_url, share_skill, import_skill,
    list_shared_skills, search_gists, _ensure_skills_dir,
)


class TestParseGistUrl(unittest.TestCase):
    def test_full_url(self):
        self.assertEqual(parse_gist_url("https://gist.github.com/user/abc123"), "abc123")

    def test_short_url(self):
        self.assertEqual(parse_gist_url("https://gist.github.com/abc123"), "abc123")

    def test_bare_id(self):
        self.assertEqual(parse_gist_url("a1b2c3d4e5"), "a1b2c3d4e5")

    def test_invalid(self):
        self.assertIsNone(parse_gist_url("not-a-gist"))
        self.assertIsNone(parse_gist_url(""))
        self.assertIsNone(parse_gist_url(None))


class TestEnsureSkillsDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test_gist_")
        self.patcher = patch(
            "fr_cli.weapon.skill_gist.SKILLS_DIR",
            Path(self.tmp),
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ensure(self):
        path = _ensure_skills_dir()
        self.assertTrue(path.exists())


class TestShare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test_share_")
        # patch skills 目录
        from fr_cli.conf.paths import ROOT as FR_CLI_DIR
        self.real_root = FR_CLI_DIR
        # patch conf.config.load_config
        self.patcher_load = patch(
            "fr_cli.weapon.skill_gist.load_local_skill",
            return_value={"name": "test_skill", "content": "# test", "path": "/tmp/x.md"},
        )
        self.patcher_load.start()

    def tearDown(self):
        self.patcher_load.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_token(self):
        # 没有 token 时 share 应该失败
        with patch.dict(os.environ, {}, clear=True):
            result = share_skill("test_skill")
            self.assertFalse(result["ok"])
            self.assertIn("Token", result["error"])

    def test_no_local_skill(self):
        # 没有本地 skill 时 share 应该失败
        with patch("fr_cli.weapon.skill_gist.load_local_skill", return_value=None):
            result = share_skill("nonexistent")
            self.assertFalse(result["ok"])

    @patch("fr_cli.weapon.skill_gist._http_request")
    def test_share_success(self, mock_http):
        mock_http.return_value = {
            "ok": True,
            "status": 201,
            "data": {
                "id": "abc123",
                "html_url": "https://gist.github.com/abc123",
            }
        }
        with patch.dict(os.environ, {"GITHUB_TOKEN": "fake_token"}):
            result = share_skill("test_skill", description="desc")
            self.assertTrue(result["ok"])
            self.assertEqual(result["gist_id"], "abc123")
            self.assertEqual(result["url"], "https://gist.github.com/abc123")

    @patch("fr_cli.weapon.skill_gist._http_request")
    def test_share_http_fail(self, mock_http):
        mock_http.return_value = {"ok": False, "error": "401 unauthorized"}
        with patch.dict(os.environ, {"GITHUB_TOKEN": "bad"}):
            result = share_skill("test_skill")
            self.assertFalse(result["ok"])


class TestImport(unittest.TestCase):
    @patch("fr_cli.weapon.skill_gist._http_request")
    def test_import_success(self, mock_http):
        mock_http.return_value = {
            "ok": True,
            "data": {
                "html_url": "https://gist.github.com/abc",
                "files": {
                    "my_skill.md": {"content": "# Skill\n\nDescription"}
                }
            }
        }
        with patch("fr_cli.weapon.skill_gist.SKILLS_DIR",
                   Path(tempfile.mkdtemp())):
            result = import_skill("abc123", name="my_skill")
            self.assertTrue(result["ok"])
            self.assertEqual(result["name"], "my_skill")

    @patch("fr_cli.weapon.skill_gist._http_request")
    def test_import_invalid_url(self, mock_http):
        result = import_skill("not-a-gist-url")
        self.assertFalse(result["ok"])

    @patch("fr_cli.weapon.skill_gist._http_request")
    def test_import_no_md(self, mock_http):
        mock_http.return_value = {
            "ok": True,
            "data": {"html_url": "x", "files": {"readme.txt": {"content": "x"}}}
        }
        result = import_skill("abc")
        self.assertFalse(result["ok"])


class TestListShared(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test_list_")
        # 写一个 records
        self.patcher = patch("fr_cli.weapon.skill_gist.SKILLS_DIR", Path(self.tmp))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_list_empty(self):
        records = list_shared_skills()
        self.assertEqual(records, [])

    def test_list_with_data(self):
        records_file = Path(self.tmp) / "shared_skills.json"
        records_file.write_text(json.dumps({
            "shared": [
                {"name": "x", "gist_id": "abc", "url": "https://gist.github.com/abc"},
            ]
        }), encoding="utf-8")
        records = list_shared_skills()
        self.assertEqual(len(records), 1)


class TestSearch(unittest.TestCase):
    def test_search(self):
        result = search_gists("python")
        self.assertTrue(result["ok"])
        self.assertIn("search_url", result)


class TestGetToken(unittest.TestCase):
    @patch.dict(os.environ, {"GITHUB_TOKEN": "env_token"})
    def test_env(self):
        from fr_cli.weapon.skill_gist import get_token
        self.assertEqual(get_token(), "env_token")

    @patch.dict(os.environ, {}, clear=True)
    @patch("fr_cli.conf.config.load_config",
           return_value={"gist_token": "cfg_token"})
    def test_config(self, mock_load):
        from fr_cli.weapon.skill_gist import get_token
        self.assertEqual(get_token(), "cfg_token")

    @patch.dict(os.environ, {}, clear=True)
    @patch("fr_cli.conf.config.load_config", return_value={})
    def test_none(self, mock_load):
        from fr_cli.weapon.skill_gist import get_token
        self.assertIsNone(get_token())


if __name__ == "__main__":
    unittest.main()
