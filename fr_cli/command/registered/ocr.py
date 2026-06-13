"""
注册表分组：OCR 文字识别
- ocr_recognize
"""
from fr_cli.command.registry import register


@register(
    name="ocr_recognize",
    triggers=["OCR", "ocr", "识别文字", "提取文字", "文字识别", "图片转文字", "PDF识别"],
    description="OCR 识别图片或 PDF 中的文字",
    params={"path": str},
    security="sec_read",
    aliases=["/ocr"],
)
def _ocr_recognize(deps, **kwargs):
    from fr_cli.weapon.ocr import ocr_recognize_file, format_ocr_result

    path = kwargs.get("path", "")
    if not path:
        return None, "请指定要识别的文件路径，例如 /ocr screenshot.png"

    result = ocr_recognize_file(path, deps.cfg, vfs=getattr(deps, "vfs", None), lang=deps.lang)
    if result.is_fail():
        return None, result.error
    return format_ocr_result(result.unwrap()), None
