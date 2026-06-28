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
