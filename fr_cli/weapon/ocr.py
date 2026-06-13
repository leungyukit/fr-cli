"""
OCR 神通 —— 识别图片与 PDF 中的文字

支持：
- 常见图片格式（PNG/JPG/GIF/BMP/WEBP/TIFF）
- PDF 文件（依赖 PyMuPDF 逐页渲染后识别）
- 任意 OpenAI 兼容的多模态 Vision API
- PaddleOCR 本地引擎（离线识别，无需 API Key）

配置项收敛在 cfg["ocr"] 下：
  engine:    识别引擎，"vision"（默认）或 "paddle"
  provider:  复用全局 providers 中的某个厂商（如 zhipu / deepseek / kimi）
  model:     OCR  vision 模型名（如 glm-4v / deepseek-vl 等）
  key:       专属 API Key；若为空且 provider 已配置，则回退到全局 key
  base_url:  自定义接口地址（当 provider 为空或自定义服务时使用）
  prompt:    默认 OCR 提示词
"""
import base64
import io
from pathlib import Path

from openai import OpenAI

from fr_cli.core.llm import create_llm_client_for, get_provider_info
from fr_cli.core.result import Result


DEFAULT_OCR_PROMPT = "请识别图片中的所有文字，保持原有排版，不要添加解释。"
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}


def get_ocr_config(cfg):
    """读取 OCR 配置，缺失字段用默认值补齐"""
    default = {
        "engine": "vision",
        "provider": "",
        "model": "",
        "key": "",
        "base_url": "",
        "prompt": DEFAULT_OCR_PROMPT,
    }
    ocr = cfg.get("ocr", {}) if isinstance(cfg, dict) else {}
    for k, v in default.items():
        if k not in ocr or ocr[k] is None:
            ocr[k] = v
    return ocr


def _create_ocr_client(cfg):
    """
    根据 cfg["ocr"] 创建 OCR 客户端，返回 Result[(client, model)]。

    策略：
    1. 若指定了 model 且 provider 是已知厂商，优先复用全局 providers 配置；
    2. 若 ocr.key 非空，以此覆盖全局 key；
    3. 若 provider 为空或未知，使用 ocr.base_url + ocr.key 创建 OpenAI 兼容客户端。
    """
    ocr_cfg = get_ocr_config(cfg)
    provider = ocr_cfg.get("provider", "").strip()
    model = ocr_cfg.get("model", "").strip()
    key = ocr_cfg.get("key", "").strip()
    base_url = ocr_cfg.get("base_url", "").strip()

    if not model:
        return Result.fail("OCR 模型未配置，请先执行 /ocr_config setup")

    # 情况 1：复用已知全局 provider
    if provider:
        if get_provider_info(provider):
            try:
                client, _, _ = create_llm_client_for(provider, model, cfg, override_key=key or None)
                return Result.ok((client, model))
            except Exception as e:
                return Result.fail(f"创建 OCR 客户端失败: {e}")

    # 情况 2：自定义接口
    if not key:
        return Result.fail("OCR API Key 未配置")

    try:
        kwargs = {"api_key": key}
        if base_url:
            kwargs["base_url"] = base_url
        return Result.ok((OpenAI(**kwargs), model))
    except Exception as e:
        return Result.fail(f"创建 OCR 客户端失败: {e}")


def _encode_image(image_bytes):
    """将图片字节流编码为 base64 data URI"""
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def _ocr_single_image_paddle(image_bytes, lang="zh"):
    """使用 PaddleOCR 本地引擎识别单张图片，返回识别到的文字"""
    try:
        from paddleocr import PaddleOCR
        from PIL import Image
        import numpy as np
    except ImportError as e:
        raise ImportError(
            "PaddleOCR 引擎需要 paddleocr 与 paddlepaddle，请执行: pip install paddleocr paddlepaddle"
        ) from e

    # 按语言选择 PaddleOCR 语言包：中文用 ch，其他默认用 en
    paddle_lang = "ch" if lang == "zh" else "en"

    # 懒加载全局 OCR 实例，避免重复初始化模型
    cache_key = f"paddle_ocr_{paddle_lang}"
    if not hasattr(_ocr_single_image_paddle, "_cache"):
        _ocr_single_image_paddle._cache = {}
    ocr = _ocr_single_image_paddle._cache.get(cache_key)
    if ocr is None:
        ocr = PaddleOCR(use_angle_cls=True, lang=paddle_lang, show_log=False)
        _ocr_single_image_paddle._cache[cache_key] = ocr

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image_array = np.array(image)
    result = ocr.ocr(image_array, cls=True)

    return _parse_paddle_result(result)


def _parse_paddle_result(result):
    """解析 PaddleOCR 返回结果，返回合并后的文字"""
    if not result or not result[0]:
        return ""

    lines = []
    for line in result[0]:
        if line and len(line) >= 2:
            text = line[1][0]
            lines.append(text)
    return "\n".join(lines)


def _ocr_single_image(client, model, image_bytes, prompt, lang="zh"):
    """识别单张图片，返回识别到的文字"""
    data_uri = _encode_image(image_bytes)
    messages = [
        {"role": "system", "content": "你是 OCR 助手，请忠实识别图片中的文字，保持原有排版，不添加解释。"},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_uri}},
                {"type": "text", "text": prompt or DEFAULT_OCR_PROMPT},
            ],
        },
    ]

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"[OCR 识别失败: {e}]"


def _pdf_to_images(path, dpi=200):
    """
    将 PDF 逐页渲染为 PNG 字节流列表。
    依赖 PyMuPDF (fitz)，未安装时抛出 ImportError。
    """
    try:
        import fitz
    except ImportError as e:
        raise ImportError(
            "PDF OCR 需要 PyMuPDF，请执行: pip install pymupdf"
        ) from e

    doc = fitz.open(path)
    images = []
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(matrix=mat)
        images.append(pix.tobytes("png"))
    doc.close()
    return images


def _resolve_file(path, vfs=None):
    """解析文件路径，优先使用 VFS 沙盒，返回 Result[path]"""
    if vfs is not None:
        resolved = vfs._resolve(path)
        if resolved is None:
            return Result.fail(f"路径不在允许的工作区内: {path}")
        if not resolved.exists():
            return Result.fail(f"文件不存在: {path}")
        return Result.ok(str(resolved))

    p = Path(path)
    if not p.exists():
        return Result.fail(f"文件不存在: {path}")
    return Result.ok(str(p.resolve()))


def _is_image(path):
    return Path(path).suffix.lower() in SUPPORTED_IMAGE_EXTS


def _is_pdf(path):
    return Path(path).suffix.lower() == ".pdf"


def _recognize_image_bytes(engine, client, model, image_bytes, prompt, lang="zh"):
    """根据引擎识别单张图片字节流"""
    if engine == "paddle":
        return _ocr_single_image_paddle(image_bytes, lang=lang)
    return _ocr_single_image(client, model, image_bytes, prompt, lang=lang)


def ocr_recognize_file(path, cfg, vfs=None, lang="zh"):
    """
    OCR 主入口：识别指定图片或 PDF 文件，返回 Result。

    Args:
        path: 文件路径
        cfg: 全局配置字典
        vfs: VFS 实例（可选）
        lang: 界面语言

    Returns:
        Result:
        - 图片成功：Result.ok(str)
        - PDF 成功：Result.ok({"pages": [...], "combined": ..., "total_pages": N})
    """
    resolve_result = _resolve_file(path, vfs=vfs)
    if resolve_result.is_fail():
        return Result.fail(resolve_result.error)
    file_path = resolve_result.unwrap()

    ocr_cfg = get_ocr_config(cfg)
    engine = ocr_cfg.get("engine", "vision")

    client, model = None, None
    prompt = ocr_cfg.get("prompt") or DEFAULT_OCR_PROMPT

    if engine == "vision":
        client_result = _create_ocr_client(cfg)
        if client_result.is_fail():
            return Result.fail(client_result.error)
        client, model = client_result.unwrap()
    elif engine == "paddle":
        pass  # PaddleOCR 本地引擎不需要远程客户端
    else:
        return Result.fail(f"未知 OCR 引擎: {engine}，可选: vision / paddle")

    try:
        if _is_image(file_path):
            with open(file_path, "rb") as f:
                image_bytes = f.read()
            text = _recognize_image_bytes(engine, client, model, image_bytes, prompt, lang=lang)
            return Result.ok(text)

        if _is_pdf(file_path):
            try:
                images = _pdf_to_images(file_path)
            except ImportError as e:
                return Result.fail(str(e))
            except Exception as e:
                return Result.fail(f"PDF 渲染失败: {e}")

            if not images:
                return Result.fail("PDF 没有可识别的页面")

            pages = []
            for idx, image_bytes in enumerate(images, 1):
                page_text = _recognize_image_bytes(engine, client, model, image_bytes, prompt, lang=lang)
                pages.append(f"--- 第 {idx} 页 ---\n{page_text}")

            combined = "\n\n".join(pages)
            return Result.ok({"pages": pages, "combined": combined, "total_pages": len(pages)})

        return Result.fail(f"不支持的文件类型: {Path(file_path).suffix}")
    except Exception as e:
        return Result.fail(f"OCR 处理失败: {e}")


def format_ocr_result(result):
    """将 OCR 结果格式化为用户可读字符串"""
    if isinstance(result, dict):
        return result.get("combined", "")
    return str(result)
