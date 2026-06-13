"""
OCR 文字识别测试
"""
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

from fr_cli.core.result import Result


class TestOcrConfig:
    """测试 OCR 配置读取"""

    def test_get_ocr_config_default(self):
        from fr_cli.weapon.ocr import get_ocr_config
        cfg = {}
        ocr_cfg = get_ocr_config(cfg)
        assert ocr_cfg["engine"] == "vision"
        assert ocr_cfg["provider"] == ""
        assert ocr_cfg["model"] == ""
        assert ocr_cfg["key"] == ""
        assert ocr_cfg["base_url"] == ""
        assert "识别" in ocr_cfg["prompt"]

    def test_get_ocr_config_merge(self):
        from fr_cli.weapon.ocr import get_ocr_config
        cfg = {"ocr": {"engine": "paddle", "model": "glm-4v", "prompt": "自定义"}}
        ocr_cfg = get_ocr_config(cfg)
        assert ocr_cfg["engine"] == "paddle"
        assert ocr_cfg["model"] == "glm-4v"
        assert ocr_cfg["prompt"] == "自定义"
        assert ocr_cfg["provider"] == ""


class TestOcrClient:
    """测试 OCR 客户端创建"""

    def test_create_client_missing_model(self):
        from fr_cli.weapon.ocr import _create_ocr_client
        result = _create_ocr_client({})
        assert result.is_fail()
        assert "模型" in result.error

    @patch("fr_cli.weapon.ocr.OpenAI")
    def test_create_client_custom_openai(self, mock_openai):
        from fr_cli.weapon.ocr import _create_ocr_client
        cfg = {"ocr": {"model": "custom-vl", "key": "sk-test", "base_url": "https://api.test.com/v1"}}
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        result = _create_ocr_client(cfg)
        assert result.is_ok()
        client, model = result.unwrap()
        assert model == "custom-vl"
        mock_openai.assert_called_once_with(api_key="sk-test", base_url="https://api.test.com/v1")

    @patch("fr_cli.weapon.ocr.create_llm_client_for")
    @patch("fr_cli.weapon.ocr.get_provider_info")
    def test_create_client_reuse_provider(self, mock_get_info, mock_create):
        from fr_cli.weapon.ocr import _create_ocr_client
        mock_get_info.return_value = {"default_model": "glm-4v"}
        mock_create.return_value = (MagicMock(), "zhipu", "glm-4v")
        cfg = {"ocr": {"provider": "zhipu", "model": "glm-4v"}, "providers": {"zhipu": {"key": "gk-test"}}}
        result = _create_ocr_client(cfg)
        assert result.is_ok()
        client, model = result.unwrap()
        assert model == "glm-4v"
        mock_create.assert_called_once_with("zhipu", "glm-4v", cfg, override_key=None)


class TestOcrRecognize:
    """测试 OCR 主流程"""

    def _make_state(self):
        state = SimpleNamespace()
        state.cfg = {"ocr": {"provider": "zhipu", "model": "glm-4v"}}
        state.lang = "zh"
        return state

    @patch("fr_cli.weapon.ocr._create_ocr_client")
    @patch("fr_cli.weapon.ocr._ocr_single_image")
    def test_recognize_image_success(self, mock_ocr_image, mock_create_client, tmp_path):
        from fr_cli.weapon.ocr import ocr_recognize_file
        img = tmp_path / "sample.png"
        img.write_bytes(b"fake-image")
        mock_client = MagicMock()
        mock_create_client.return_value = Result.ok((mock_client, "glm-4v"))
        mock_ocr_image.return_value = "识别结果"

        result = ocr_recognize_file(str(img), self._make_state().cfg)
        assert result.is_ok()
        assert result.unwrap() == "识别结果"

    @patch("fr_cli.weapon.ocr._create_ocr_client")
    @patch("fr_cli.weapon.ocr._ocr_single_image")
    @patch("fr_cli.weapon.ocr._pdf_to_images")
    def test_recognize_pdf_success(self, mock_pdf, mock_ocr_image, mock_create_client, tmp_path):
        from fr_cli.weapon.ocr import ocr_recognize_file
        pdf = tmp_path / "sample.pdf"
        pdf.write_bytes(b"fake-pdf")
        mock_client = MagicMock()
        mock_create_client.return_value = Result.ok((mock_client, "glm-4v"))
        mock_pdf.return_value = [b"page1", b"page2"]
        mock_ocr_image.side_effect = ["第一页文字", "第二页文字"]

        result = ocr_recognize_file(str(pdf), self._make_state().cfg)
        assert result.is_ok()
        data = result.unwrap()
        assert data["total_pages"] == 2
        assert "第一页文字" in data["combined"]
        assert "第二页文字" in data["combined"]

    @patch("fr_cli.weapon.ocr._create_ocr_client")
    def test_recognize_unsupported_type(self, mock_create_client, tmp_path):
        from fr_cli.weapon.ocr import ocr_recognize_file
        txt = tmp_path / "sample.txt"
        txt.write_text("text")
        mock_client = MagicMock()
        mock_create_client.return_value = Result.ok((mock_client, "glm-4v"))

        result = ocr_recognize_file(str(txt), self._make_state().cfg)
        assert result.is_fail()
        assert "不支持" in result.error


class TestOcrRegistry:
    """测试注册表解析"""

    def test_parse_ocr_args(self):
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        kwargs = reg._parse_cmd_args(
            ["/ocr", "photo.jpg"],
            {"name": "ocr_recognize"},
            None,
        )
        assert kwargs == {"path": "photo.jpg"}


class TestOcrConfigCommand:
    """测试 /ocr_config 命令"""

    def test_cmd_ocr_config_show(self, capsys):
        from fr_cli.repl.commands.ocr import _cmd_ocr_config
        state = SimpleNamespace()
        state.cfg = {"ocr": {"model": "glm-4v"}}
        state.save_cfg = MagicMock()
        _cmd_ocr_config(state, ["/ocr_config"])
        captured = capsys.readouterr()
        assert "glm-4v" in captured.out


class TestOcrPaddle:
    """测试 PaddleOCR 引擎支持"""

    @patch("fr_cli.weapon.ocr._ocr_single_image_paddle")
    def test_recognize_image_with_paddle_engine(self, mock_paddle, tmp_path):
        from fr_cli.weapon.ocr import ocr_recognize_file
        img = tmp_path / "sample.png"
        img.write_bytes(b"fake-image")
        mock_paddle.return_value = "Paddle 识别结果"

        cfg = {"ocr": {"engine": "paddle"}}
        result = ocr_recognize_file(str(img), cfg)

        assert result.is_ok()
        assert result.unwrap() == "Paddle 识别结果"
        mock_paddle.assert_called_once()

    @patch("fr_cli.weapon.ocr._ocr_single_image_paddle")
    @patch("fr_cli.weapon.ocr._pdf_to_images")
    def test_recognize_pdf_with_paddle_engine(self, mock_pdf, mock_paddle, tmp_path):
        from fr_cli.weapon.ocr import ocr_recognize_file
        pdf = tmp_path / "sample.pdf"
        pdf.write_bytes(b"fake-pdf")
        mock_pdf.return_value = [b"page1", b"page2"]
        mock_paddle.side_effect = ["第一页", "第二页"]

        cfg = {"ocr": {"engine": "paddle"}}
        result = ocr_recognize_file(str(pdf), cfg)

        assert result.is_ok()
        data = result.unwrap()
        assert data["total_pages"] == 2
        assert "第一页" in data["combined"]
        assert "第二页" in data["combined"]
        assert mock_paddle.call_count == 2

    @patch("fr_cli.weapon.ocr._ocr_single_image_paddle")
    def test_paddle_engine_skips_vision_client(self, mock_paddle, tmp_path):
        """PaddleOCR 引擎不应尝试创建 Vision API 客户端"""
        from fr_cli.weapon.ocr import ocr_recognize_file
        img = tmp_path / "sample.png"
        img.write_bytes(b"fake-image")
        mock_paddle.return_value = "本地识别"

        with patch("fr_cli.weapon.ocr._create_ocr_client") as mock_create_client:
            cfg = {"ocr": {"engine": "paddle"}}
            result = ocr_recognize_file(str(img), cfg)
            mock_create_client.assert_not_called()

        assert result.is_ok()
        assert result.unwrap() == "本地识别"

    def test_paddle_ocr_parse_result_format(self):
        """测试 PaddleOCR 返回结果解析"""
        from fr_cli.weapon.ocr import _parse_paddle_result

        result = [
            [
                [[], ("第一行文字", 0.98)],
                [[], ("第二行文字", 0.95)],
            ]
        ]
        text = _parse_paddle_result(result)

        assert "第一行文字" in text
        assert "第二行文字" in text

    def test_paddle_ocr_parse_empty_result(self):
        """测试 PaddleOCR 空结果解析"""
        from fr_cli.weapon.ocr import _parse_paddle_result

        assert _parse_paddle_result(None) == ""
        assert _parse_paddle_result([]) == ""
        assert _parse_paddle_result([[]]) == ""
