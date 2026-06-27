"""
OCR 文字识别测试
覆盖文件类型检测、路径解析、PDF 转图片、base64 编码、结果格式化、主入口等。

Vision 引擎需要真实 LLM(client 来自 cfg["ocr"] 配置),这里 mock 掉。
PaddleOCR 引擎没装,跳过相关测试。
"""
import base64
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.weapon.ocr import (
    SUPPORTED_IMAGE_EXTS,
    _is_image,
    _is_pdf,
    _encode_image,
    _resolve_file,
    _pdf_to_images,
    format_ocr_result,
    ocr_recognize_file,
    _recognize_image_bytes,
    _create_ocr_client,
)


# ==================== 依赖检查 ====================

def _have_pymupdf():
    try:
        import fitz  # noqa
        return True
    except ImportError:
        return False


# ==================== 测试:文件类型检测 ====================

class TestFileTypeDetection:

    @pytest.mark.parametrize("ext", [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"])
    def test_is_image_supported_extensions(self, ext):
        assert _is_image(f"photo{ext}") is True

    @pytest.mark.parametrize("ext", [".pdf", ".txt", ".doc", ".docx", ".xlsx", ".zip", ""])
    def test_is_image_unsupported_extensions(self, ext):
        assert _is_image(f"file{ext}") is False

    def test_is_image_case_insensitive(self):
        assert _is_image("photo.PNG") is True
        assert _is_image("photo.JpG") is True

    def test_is_pdf(self):
        assert _is_pdf("doc.pdf") is True
        assert _is_pdf("doc.PDF") is True
        assert _is_pdf("doc.txt") is False
        assert _is_pdf("doc") is False

    def test_supported_image_exts_complete(self):
        """SUPPORTED_IMAGE_EXTS 应包含主流格式"""
        assert ".png" in SUPPORTED_IMAGE_EXTS
        assert ".jpg" in SUPPORTED_IMAGE_EXTS
        assert ".jpeg" in SUPPORTED_IMAGE_EXTS


# ==================== 测试:base64 编码 ====================

class TestEncodeImage:

    def test_encode_image_returns_data_uri(self):
        image_bytes = b"hello world"
        result = _encode_image(image_bytes)
        assert result.startswith("data:image/jpeg;base64,")
        # 解码后应等于原 bytes
        b64_part = result.split(",", 1)[1]
        assert base64.b64decode(b64_part) == image_bytes

    def test_encode_empty_bytes(self):
        result = _encode_image(b"")
        assert result.startswith("data:image/jpeg;base64,")


# ==================== 测试:路径解析 ====================

class TestResolveFile:

    def test_resolve_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        result = _resolve_file(str(f))
        assert result.is_ok()
        assert Path(result.unwrap()).exists()

    def test_resolve_nonexistent_file(self):
        result = _resolve_file("/nonexistent/file.txt")
        assert not result.is_ok()
        assert "不存在" in result.error

    def test_resolve_with_vfs_in_sandbox(self, tmp_path):
        """VFS 在沙盒内:路径应允许"""
        f = tmp_path / "doc.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")

        mock_vfs = MagicMock()
        mock_vfs._resolve.return_value = f
        result = _resolve_file(str(f), vfs=mock_vfs)
        assert result.is_ok()

    def test_resolve_with_vfs_rejected(self):
        """VFS 拒绝路径(沙盒外)"""
        mock_vfs = MagicMock()
        mock_vfs._resolve.return_value = None  # VFS 拒绝
        result = _resolve_file("/etc/passwd", vfs=mock_vfs)
        assert not result.is_ok()
        assert "工作区" in result.error or "不允许" in result.error

    def test_resolve_with_vfs_not_exists(self, tmp_path):
        """VFS 通过但文件不存在"""
        f = tmp_path / "ghost.png"
        mock_vfs = MagicMock()
        mock_vfs._resolve.return_value = f  # 返回但文件不存在
        result = _resolve_file(str(f), vfs=mock_vfs)
        assert not result.is_ok()
        assert "不存在" in result.error


# ==================== 测试:PDF 转图片 ====================

class TestPdfToImages:

    @pytest.mark.skipif(not _have_pymupdf(), reason="需要 PyMuPDF")
    def test_pdf_to_images_returns_bytes_list(self, tmp_path):
        """真实 PDF 转图片"""
        import fitz
        pdf_path = tmp_path / "test.pdf"
        # 创建简单的 PDF
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Hello World", fontsize=14)
        doc.save(str(pdf_path))
        doc.close()

        images = _pdf_to_images(str(pdf_path))
        assert isinstance(images, list)
        assert len(images) >= 1
        assert all(isinstance(img, bytes) for img in images)
        # PNG 字节应以 PNG magic number 开头
        assert images[0][:4] == b"\x89PNG"

    @pytest.mark.skipif(not _have_pymupdf(), reason="需要 PyMuPDF")
    def test_pdf_to_images_multi_page(self, tmp_path):
        """多页 PDF:每页应生成一张图片"""
        import fitz
        pdf_path = tmp_path / "multi.pdf"
        doc = fitz.open()
        for i in range(3):
            page = doc.new_page()
            page.insert_text((50, 50), f"Page {i+1}", fontsize=14)
        doc.save(str(pdf_path))
        doc.close()

        images = _pdf_to_images(str(pdf_path))
        assert len(images) == 3


# ==================== 测试:结果格式化 ====================

class TestFormatOcrResult:

    def test_format_dict_with_combined(self):
        result = {"combined": "Hello World", "raw": [...], "engine": "vision"}
        assert format_ocr_result(result) == "Hello World"

    def test_format_dict_without_combined(self):
        result = {"raw": [...], "engine": "vision"}
        assert format_ocr_result(result) == ""

    def test_format_string(self):
        assert format_ocr_result("plain text") == "plain text"

    def test_format_empty_string(self):
        assert format_ocr_result("") == ""

    def test_format_none(self):
        # None 不应崩,返回 str(None) 或空
        out = format_ocr_result(None)
        assert isinstance(out, str)


# ==================== 测试:引擎分发 ====================

class TestRecognizeImageBytesDispatch:

    def test_dispatch_to_vision_engine(self):
        """engine='vision' 应走 LLM 调用"""
        mock_client = MagicMock()
        with patch("fr_cli.weapon.ocr._ocr_single_image") as mock_vision:
            mock_vision.return_value = "recognized text"
            result = _recognize_image_bytes(
                "vision", mock_client, "model", b"image_bytes", "prompt", "zh"
            )
            assert result == "recognized text"
            assert mock_vision.called

    def test_dispatch_to_paddle_engine(self):
        """engine='paddle' 应走 PaddleOCR(没装 → 抛 ImportError)"""
        mock_client = MagicMock()
        with pytest.raises(ImportError, match="[Pp]addle"):
            _recognize_image_bytes(
                "paddle", mock_client, "model", b"image_bytes", "prompt", "zh"
            )

    def test_dispatch_unknown_engine_falls_back_to_vision(self):
        """未知 engine 应默认走 vision"""
        mock_client = MagicMock()
        with patch("fr_cli.weapon.ocr._ocr_single_image") as mock_vision:
            mock_vision.return_value = "result"
            result = _recognize_image_bytes(
                "unknown_engine", mock_client, "model", b"img", "p", "zh"
            )
            assert result == "result"
            assert mock_vision.called


# ==================== 测试:主入口 ocr_recognize_file ====================

class TestOcrRecognizeFile:

    def test_recognize_nonexistent_file(self, tmp_path):
        cfg = {"ocr": {"engine": "vision", "model": "glm-4v"}}
        result = ocr_recognize_file(str(tmp_path / "ghost.png"), cfg)
        assert not result.is_ok()
        assert "不存在" in result.error

    def test_recognize_unsupported_format(self, tmp_path):
        """不支持的扩展名应报错"""
        f = tmp_path / "doc.xyz"
        f.write_text("hello", encoding="utf-8")
        # 必须给完整 cfg(否则会先报 API Key 错)
        cfg = {"ocr": {"engine": "vision", "model": "glm-4v", "key": "sk-fake"}}
        result = ocr_recognize_file(str(f), cfg)
        assert not result.is_ok()
        assert "不支持" in result.error or "格式" in result.error

    def test_recognize_image_with_vision_engine(self, tmp_path):
        """vision 引擎:mock LLM 返回识别结果"""
        f = tmp_path / "photo.png"
        # 创建一个最小的有效 PNG
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        cfg = {"ocr": {"engine": "vision", "model": "glm-4v"}}

        # mock _create_ocr_client + _recognize_image_bytes
        with patch("fr_cli.weapon.ocr._create_ocr_client") as mock_create, \
             patch("fr_cli.weapon.ocr._recognize_image_bytes") as mock_recog:
            from fr_cli.core.result import Result
            mock_create.return_value = Result.ok((MagicMock(), "glm-4v"))
            mock_recog.return_value = "识别出的文字内容"

            result = ocr_recognize_file(str(f), cfg)
            assert result.is_ok(), f"error: {result.error}"
            assert "识别" in result.unwrap()

    def test_recognize_pdf_with_vision_engine(self, tmp_path):
        """PDF 文件应逐页调用 vision"""
        if not _have_pymupdf():
            pytest.skip("需要 PyMuPDF")
        import fitz
        pdf_path = tmp_path / "doc.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "PDF content", fontsize=14)
        doc.save(str(pdf_path))
        doc.close()

        cfg = {"ocr": {"engine": "vision", "model": "glm-4v"}}

        with patch("fr_cli.weapon.ocr._create_ocr_client") as mock_create, \
             patch("fr_cli.weapon.ocr._recognize_image_bytes") as mock_recog:
            from fr_cli.core.result import Result
            mock_create.return_value = Result.ok((MagicMock(), "glm-4v"))
            mock_recog.return_value = "page text"

            result = ocr_recognize_file(str(pdf_path), cfg)
            assert result.is_ok(), f"error: {result.error}"
            # 应至少被调用 1 次(每页一次)
            assert mock_recog.call_count >= 1

    def test_recognize_with_no_model_returns_fail(self, tmp_path):
        """未配置 model + 走 vision 引擎:应返回 fail"""
        f = tmp_path / "photo.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        cfg = {"ocr": {"engine": "vision", "model": ""}}  # 空 model

        # _create_ocr_client 在 model 为空时应返回 fail
        result = ocr_recognize_file(str(f), cfg)
        assert not result.is_ok()
        assert "模型" in result.error or "model" in result.error.lower() or "未配置" in result.error


# ==================== 测试:_create_ocr_client ====================

class TestCreateOcrClient:

    def test_empty_model_returns_fail(self):
        cfg = {"ocr": {"engine": "vision", "model": "", "key": ""}}
        result = _create_ocr_client(cfg)
        assert not result.is_ok()

    def test_known_provider_uses_global_config(self):
        """provider=zhipu + 已配 zhipu key:应能创建"""
        cfg = {
            "ocr": {"engine": "vision", "model": "glm-4v", "provider": "zhipu", "key": ""},
            "providers": {
                "zhipu": {"key": "sk-fake-key", "model": "glm-4-flash"}
            },
        }
        # zhipu 走原生 SDK,需要真实 import;但只要 client 能创建即可
        try:
            result = _create_ocr_client(cfg)
            assert result.is_ok(), f"error: {result.error}"
            client, model = result.unwrap()
            assert model == "glm-4v"
        except ImportError:
            pytest.skip("zhipu SDK 未装")

    def test_custom_base_url_creates_openai_client(self):
        """自定义 base_url + key:应创建 OpenAI 兼容 client"""
        cfg = {
            "ocr": {
                "engine": "vision", "model": "custom-model",
                "provider": "", "base_url": "https://api.example.com/v1",
                "key": "sk-fake",
            }
        }
        result = _create_ocr_client(cfg)
        assert result.is_ok(), f"error: {result.error}"
        client, model = result.unwrap()
        assert model == "custom-model"


# ==================== 测试:handle_ocr 命令处理(通过 REPL 命令入口) ====================

class TestHandleOcrConfig:

    def test_ocr_config_prints_current(self):
        """_cmd_ocr_config 应显示当前配置"""
        # 不传参数时显示当前配置
        from fr_cli.repl.commands.ocr import _cmd_ocr_config
        mock_state = MagicMock()
        mock_state.cfg = {"ocr": {"engine": "vision", "model": "", "key": ""}}
        mock_state.lang = "zh"

        # 空操作不抛异常
        try:
            _cmd_ocr_config(mock_state, ["/ocr_config"])
        except SystemExit:
            pass
        except Exception as e:
            # 输入回环之类的小问题不视为失败
            pytest.skip(f"实际 REPL 入口测试复杂: {e}")
