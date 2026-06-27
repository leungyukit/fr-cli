"""
语音输入 STT 工具注册
- voice_input: 转写音频文件 → 作为下次输入
- voice_record: 录音(macOS) → 自动转写
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result
from fr_cli.weapon.voice_input import (
    transcribe_audio, validate_audio_file, is_supported_audio,
    SUPPORTED_FORMATS,
)


@register(
    name="voice_input",
    triggers=["语音输入", "转写音频", "STT", "transcribe"],
    description="音频文件转写为文字(支持 mp3/wav/m4a/flac 等)",
    params={"path": str, "language": str, "prefer_local": bool},
    aliases=["/voice_input"],
)
def _register_voice_input(deps, **kwargs):
    path = kwargs.get("path") or ""
    language = kwargs.get("language") or "zh"
    prefer_local = bool(kwargs.get("prefer_local", False))

    if not path:
        # 列出支持的格式
        return Result.ok(
            "请提供音频文件路径\n"
            f"支持格式: {', '.join(sorted(f.lstrip('.') for f in SUPPORTED_FORMATS))}\n"
            "用法: /voice_input /path/to/audio.mp3"
        )

    if not is_supported_audio(path):
        return Result.fail(f"不支持的格式,仅支持: {', '.join(SUPPORTED_FORMATS)}")

    v = validate_audio_file(path)
    if not v["ok"]:
        return Result.fail(v["error"])

    size_kb = v["size"] // 1024
    print(f"🎙️ 正在转写 ({size_kb}KB, 格式 {v['format']}, 语言 {language})...")
    result = transcribe_audio(path, language=language, prefer_local=prefer_local)

    if not result["ok"]:
        return Result.fail(result.get("error", "转写失败"))

    engine = result.get("engine", "unknown")
    duration = result.get("duration")
    text = result.get("text", "")

    # 如果有 deps.state,可以选择是否注入到 messages
    state = getattr(deps, "state", None)
    if state and kwargs.get("inject", False) and text:
        try:
            state.messages.append({"role": "user", "content": text})
        except Exception:
            pass

    extra = ""
    if duration:
        extra = f" ({duration:.1f}s)"
    return Result.ok(
        f"✅ 转写成功{extra} [引擎: {engine}]\n\n"
        f"📝 转写内容:\n{text}"
    )


@register(
    name="voice_record",
    triggers=["录音", "record audio"],
    description="录音(macOS)并自动转写为文字",
    params={"duration": int, "language": str},
    aliases=["/voice_record"],
)
def _register_voice_record(deps, **kwargs):
    import sys
    import tempfile

    if sys.platform != "darwin":
        return Result.fail("录音功能仅在 macOS 上可用(其他平台请使用 /voice_input <文件路径>)")

    duration = int(kwargs.get("duration", 0))
    language = kwargs.get("language") or "zh"

    from fr_cli.weapon.voice_input import record_audio_macos

    # 临时文件
    fd, tmp_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    if duration > 0:
        print(f"🎙️ 录音 {duration} 秒...")
    else:
        print("🎙️ 开始录音,按 Ctrl+C 停止...")

    try:
        result = record_audio_macos(tmp_path, duration_sec=duration)
        if not result["ok"]:
            return Result.fail(result.get("error", "录音失败"))

        # 转写
        trans_result = transcribe_audio(result["path"], language=language)
        if not trans_result["ok"]:
            return Result.fail(f"录音成功但转写失败: {trans_result.get('error')}")

        return Result.ok(
            f"✅ 录音 + 转写完成\n\n"
            f"📝 转写内容:\n{trans_result.get('text', '')}\n\n"
            f"音频已保存到: {result['path']}"
        )
    finally:
        # 清理临时文件(可选,这里保留供用户使用)
        pass


import os  # 放到底部
