"""Ollama 测试"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fr_cli.weapon.ollama import (
    detect_ollama, list_models, delete_model, format_status,
    _human_size, _http_request,
)


class TestHumanSize(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual(_human_size(512), "512.0B")

    def test_kb(self):
        self.assertIn("KB", _human_size(2048))

    def test_mb(self):
        self.assertIn("MB", _human_size(2 * 1024 * 1024))

    def test_gb(self):
        self.assertIn("GB", _human_size(3 * 1024 * 1024 * 1024))

    def test_zero(self):
        self.assertEqual(_human_size(0), "?")


class TestDetect(unittest.TestCase):
    @patch("fr_cli.weapon.ollama._http_request")
    def test_detect_success(self, mock_http):
        mock_http.return_value = {"ok": True, "data": {"version": "0.1.0"}}
        r = detect_ollama()
        self.assertTrue(r["ok"])
        self.assertEqual(r["version"], "0.1.0")

    @patch("fr_cli.weapon.ollama._http_request")
    def test_detect_fail(self, mock_http):
        mock_http.return_value = {"ok": False, "error": "connection refused"}
        r = detect_ollama()
        self.assertFalse(r["ok"])


class TestListModels(unittest.TestCase):
    @patch("fr_cli.weapon.ollama._http_request")
    def test_list(self, mock_http):
        mock_http.return_value = {
            "ok": True,
            "data": {
                "models": [
                    {
                        "name": "llama3.2:latest",
                        "size": 2 * 1024 * 1024 * 1024,
                        "modified_at": "2026-06-01",
                        "details": {"family": "llama", "parameter_size": "3B", "quantization_level": "Q4_0"},
                    }
                ]
            }
        }
        r = list_models()
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["models"]), 1)
        self.assertEqual(r["models"][0]["name"], "llama3.2:latest")
        self.assertIn("GB", r["models"][0]["size_human"])

    @patch("fr_cli.weapon.ollama._http_request")
    def test_list_empty(self, mock_http):
        mock_http.return_value = {"ok": True, "data": {"models": []}}
        r = list_models()
        self.assertTrue(r["ok"])
        self.assertEqual(r["models"], [])

    @patch("fr_cli.weapon.ollama._http_request")
    def test_list_fail(self, mock_http):
        mock_http.return_value = {"ok": False, "error": "x"}
        r = list_models()
        self.assertFalse(r["ok"])
        self.assertEqual(r["models"], [])


class TestDelete(unittest.TestCase):
    @patch("fr_cli.weapon.ollama._http_request")
    def test_delete(self, mock_http):
        mock_http.return_value = {"ok": True}
        r = delete_model("llama3.2")
        self.assertTrue(r["ok"])

    @patch("fr_cli.weapon.ollama._http_request")
    def test_delete_fail(self, mock_http):
        mock_http.return_value = {"ok": False, "error": "not found"}
        r = delete_model("nope")
        self.assertFalse(r["ok"])


class TestFormat(unittest.TestCase):
    @patch("fr_cli.weapon.ollama.detect_ollama")
    @patch("fr_cli.weapon.ollama.list_models")
    def test_format_running(self, mock_list, mock_detect):
        mock_detect.return_value = {"ok": True, "version": "0.1.0"}
        mock_list.return_value = {
            "ok": True,
            "models": [{"name": "llama3.2", "size_human": "2.0GB", "parameter_size": "3B"}]
        }
        out = format_status()
        self.assertIn("Ollama 运行中", out)
        self.assertIn("llama3.2", out)
        self.assertIn("2.0GB", out)

    @patch("fr_cli.weapon.ollama.detect_ollama")
    def test_format_not_running(self, mock_detect):
        mock_detect.return_value = {"ok": False, "error": "refused"}
        out = format_status()
        self.assertIn("未运行", out)
        self.assertIn("ollama serve", out)


if __name__ == "__main__":
    unittest.main()