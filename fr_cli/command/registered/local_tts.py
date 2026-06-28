"""
本地 TTS 工具:
- say: 朗读文本(系统 say / espeak / SAPI)
- voices: 列出可用声音
- tts_status: 检查 TTS 引擎可用性
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result


@register(
    name="say",
    triggers=["朗读", "speak", "say"],
    description="朗读文本(macOS say / Linux espeak / Windows SAPI,本地无云端)",
    params={"text": str, "voice": str, "rate": int, "output": str, "async": bool},
    aliases=["/say", "/speak"],
)
def _register_say(deps, **kwargs):
    text = kwargs.get("text") or ""
    voice = kwargs.get("voice") or None
    rate = kwargs.get("rate") or None
    if rate is not None:
        try:
            rate = int(rate)
        except (ValueError, TypeError):
            rate = None
    output = kwargs.get("output") or None
    async_play = bool(kwargs.get("async", False))

    if not text:
        return Result.fail("需要提供文本")

    from fr_cli.weapon.local_tts import speak
    result = speak(text, voice=voice, rate=rate,
                  output_file=output, async_play=async_play)

    if not result["ok"]:
        return Result.fail(result.get("error", "TTS 失败"))

    extra = ""
    if result.get("async"):
        extra = f" (PID {result.get('pid')}, 后台播放中)"
    if output:
        extra += f"\n  保存到: {output}"
    return Result.ok(
        f"🔊 朗读成功 ({result['engine']}){extra}\n"
        f"  文本: {text[:50]}{'...' if len(text) > 50 else ''}"
    )


@register(
    name="voices",
    triggers=["列出声音", "voices"],
    description="列出本地 TTS 可用声音",
    params={},
    aliases=["/voices"],
)
def _register_voices(deps, **kwargs):
    from fr_cli.weapon.local_tts import list_voices, format_voices
    voices = list_voices()
    return Result.ok(format_voices(voices, lang="zh"))


@register(
    name="tts_status",
    triggers=["TTS 状态", "tts status"],
    description="检查本地 TTS 引擎是否可用",
    params={},
    aliases=["/tts_status"],
)
def _register_tts_status(deps, **kwargs):
    from fr_cli.weapon.local_tts import detect_tts_engine
    det = detect_tts_engine()
    if not det["ok"]:
        return Result.fail(det.get("error", "TTS 不可用"))
    return Result.ok(
        f"✅ TTS 可用:\n"
        f"  平台: {det['platform']}\n"
        f"  引擎: {det['engine']}"
    )


@register(
    name="say_stream",
    triggers=["流式朗读", "stream say"],
    description="流式朗读长文本(自动分块,避免单个命令过长被截断)",
    params={"text": str, "voice": str, "rate": int, "chunk_size": int, "async": bool},
    aliases=["/say_stream", "/stream_say"],
)
def _register_say_stream(deps, **kwargs):
    text = kwargs.get("text") or ""
    voice = kwargs.get("voice") or None
    rate = kwargs.get("rate") or None
    if rate is not None:
        try:
            rate = int(rate)
        except (ValueError, TypeError):
            rate = None
    chunk_size = int(kwargs.get("chunk_size", 200))
    async_play = bool(kwargs.get("async", True))

    if not text:
        return Result.fail("需要提供文本")

    from fr_cli.weapon.local_tts import speak_stream
    result = speak_stream(
        text, voice=voice, rate=rate,
        chunk_size=chunk_size, async_play=async_play,
    )
    if not result["ok"]:
        return Result.fail(result.get("error", "TTS 流式失败"))

    extra = ""
    if result.get("async"):
        extra = f" (后台线程: {result.get('thread')})"
    err_lines = ""
    if result.get("errors"):
        err_lines = "\n⚠️ 部分失败:\n" + "\n".join(
            f"  chunk {e['chunk']}: {e['error']}" for e in result["errors"]
        )
    return Result.ok(
        f"🔊 流式朗读 ({result['engine']}) {result['chunks']} 块{extra}\n"
        f"  文本: {text[:60]}{'...' if len(text) > 60 else ''}"
        f"{err_lines}"
    )
