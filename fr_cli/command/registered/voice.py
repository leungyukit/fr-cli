"""
Voice / TTS 命令注册
- voice_speak: 朗读文本
- voice_list_voices: 列出可用声音
- voice_enable / voice_disable: 开关自动朗读
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result
from fr_cli.agent.voice import (
    voice_speak as _voice_speak,
    is_voice_available, is_voice_enabled, set_voice_enabled,
    list_available_voices,
)


@register(
    name="voice_speak",
    triggers=["朗读", "读出来", "speak", "tts", "语音"],
    description="用 TTS 朗读文本(需要 matrix MCP 支持)",
    params={"text": str, "voice": str},
    aliases=["/speak"],
)
def _register_voice_speak(deps, **kwargs):
    text = kwargs.get("text", "").strip()
    voice = kwargs.get("voice", "zh_male_en_motion")
    if not text:
        return Result.fail("需要提供 text 参数")
    if not is_voice_available():
        return Result.fail("TTS 不可用:请先配置 matrix MCP server(/mcp_add 或 /mcp_refresh)")
    return _voice_speak(text, voice=voice)


@register(
    name="voice_list",
    triggers=["列出声音", "list voices", "voice list"],
    description="列出可用的 TTS 声音",
    params={},
    aliases=["/voices"],
)
def _register_voice_list(deps, **kwargs):
    if not is_voice_available():
        return Result.fail("TTS 不可用:请先配置 matrix MCP server")
    voices = list_available_voices()
    if not voices:
        return Result.ok("未发现可用声音(需要 matrix MCP 提供 voice 工具)")
    return Result.ok("可用声音:\n" + "\n".join(f"  - {v}" for v in voices))


@register(
    name="voice_toggle",
    triggers=["voice开关", "auto speak", "自动朗读"],
    description="切换自动朗读模式(开启后 AI 回复会自动朗读)",
    params={"enabled": bool},
    aliases=["/voice"],
)
def _register_voice_toggle(deps, **kwargs):
    enabled = bool(kwargs.get("enabled", True))
    set_voice_enabled(enabled)
    status = "已开启" if is_voice_enabled() else "已关闭"
    return Result.ok(f"自动朗读模式 {status}")
