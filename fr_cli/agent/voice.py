"""
Voice / 多模态输出 —— TTS 集成

复用 matrix MCP 的 TTS 工具,让 fr-cli 可以朗读 AI 回复。

能力:
  - voice_speak(text): 朗读文本
  - voice_list_voices(): 列出可用声音
  - /voice on/off: 切换自动朗读模式

降级策略:
  - 如果 matrix MCP 不可用 → 提示未启用
  - 如果 TTS 失败 → 优雅降级到文本输出
"""
from pathlib import Path
from typing import List, Optional


_voice_enabled = False
_voice_cache_dir: Optional[Path] = None


def _get_voice_cache_dir() -> Path:
    """TTS 音频缓存目录"""
    global _voice_cache_dir
    if _voice_cache_dir is None:
        _voice_cache_dir = Path.home() / ".fr_cli" / "voice"
    _voice_cache_dir.mkdir(parents=True, exist_ok=True)
    return _voice_cache_dir


def is_voice_available() -> bool:
    """检测 matrix MCP TTS 工具是否可用"""
    try:
        from fr_cli.weapon.mcp import get_mcp_manager
        mgr = get_mcp_manager()
        if not mgr:
            return False
        # 查找包含 TTS 能力的 MCP server
        for name in mgr.servers:
            srv = mgr.get_server(name)
            if not srv or not srv.enabled:
                continue
            # 检查 server 名字里包含 "matrix"(matrix 是官方多模态网关)
            if "matrix" in name.lower():
                return True
        return False
    except Exception:
        return False


def is_voice_enabled() -> bool:
    """voice 是否启用(全局开关)"""
    return _voice_enabled


def set_voice_enabled(enabled: bool) -> bool:
    """设置 voice 开关"""
    global _voice_enabled
    _voice_enabled = enabled
    return _voice_enabled


async def voice_speak_async(text: str, voice: str = "zh_male_en_motion",
                            save_to_file: bool = False) -> Optional[str]:
    """异步 TTS 朗读(text → audio file path)

    Returns:
        音频文件路径(如果 save_to_file=True),否则 None
    """
    if not text or not text.strip():
        return None

    if not is_voice_available():
        raise RuntimeError("TTS 不可用:请先配置 matrix MCP server(/mcp_add 或 /mcp_refresh)")

    try:
        from fr_cli.weapon.mcp import get_mcp_manager
        mgr = get_mcp_manager()

        # 找到 matrix server
        matrix_server = None
        for name in mgr.servers:
            if "matrix" in name.lower():
                matrix_server = name
                break

        if not matrix_server:
            raise RuntimeError("未配置 matrix MCP server")

        # 调用 TTS 工具
        # matrix MCP 一般暴露 matrix_synthesize_speech 或 matrix_batch_text_to_audio
        for tool_name in ["matrix_synthesize_speech", "matrix_batch_text_to_audio",
                          "tts", "synthesize_speech"]:
            try:
                result, err = mgr.call_tool_sync(
                    matrix_server,
                    tool_name,
                    {"text": text, "voice": voice},
                )
                if err is None and result:
                    if save_to_file:
                        cache = _get_voice_cache_dir()
                        out = cache / f"speech_{abs(hash(text))}.mp3"
                        out.write_bytes(result.encode("latin1") if isinstance(result, str) else result)
                        return str(out)
                    return None
            except Exception:
                continue

        raise RuntimeError("matrix MCP 未找到 TTS 工具(matrix_synthesize_speech 等)")
    except Exception as e:
        raise RuntimeError(f"TTS 调用失败: {e}")


def voice_speak(text: str, voice: str = "zh_male_en_motion") -> "Result":
    """同步 TTS 入口"""
    from fr_cli.core.result import Result
    try:
        import asyncio
        path = asyncio.run(voice_speak_async(text, voice=voice, save_to_file=True))
        return Result.ok({
            "audio_path": path,
            "played": path is not None,
            "text_length": len(text),
        })
    except Exception as e:
        return Result.fail(str(e))


def list_available_voices() -> List[str]:
    """列出可用声音(从 matrix MCP 获取)"""
    try:
        from fr_cli.weapon.mcp import get_mcp_manager
        mgr = get_mcp_manager()
        matrix_server = None
        for name in mgr.servers:
            if "matrix" in name.lower():
                matrix_server = name
                break
        if not matrix_server:
            return []

        try:
            tools, _ = mgr.list_all_tools() if hasattr(mgr, "list_all_tools") else ([], None)
        except Exception:
            tools = []

        voices = []
        for t in tools:
            if "voice" in str(t).lower() or "synth" in str(t).lower():
                voices.append(t.get("name", ""))
        return voices
    except Exception:
        return []


def speak_if_enabled(text: str) -> Optional[str]:
    """如果 voice 启用,朗读文本(异步后台)

    Returns:
        音频路径(如果朗读了)或 None
    """
    if not _voice_enabled:
        return None
    if not text or not text.strip():
        return None

    try:
        import threading
        result_holder = [None]
        def _run():
            try:
                import asyncio
                path = asyncio.run(voice_speak_async(text, save_to_file=True))
                result_holder[0] = path
            except Exception:
                pass

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return None  # 异步,先返回
    except Exception:
        return None
