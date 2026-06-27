"""
STT 语音输入 —— 音频转写

支持两种模式:
1. 文件转写:传入音频路径,调用 matrix MCP transcribe_audio
2. 流式录音:OS 录音 → 转写(仅 macOS,其他平台降级)

文件格式:mp3 / wav / m4a / flac / ogg / opus / webm
"""
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any

# 支持的音频格式
SUPPORTED_FORMATS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".webm", ".aac"}


def is_supported_audio(path: str) -> bool:
    """检查是否是支持的音频格式"""
    return Path(path).suffix.lower() in SUPPORTED_FORMATS


def validate_audio_file(path: str) -> Dict[str, Any]:
    """验证音频文件

    Returns:
        {"ok": bool, "size": int, "format": str, "error": str?}
    """
    if not os.path.exists(path):
        return {"ok": False, "error": f"文件不存在: {path}"}

    size = os.path.getsize(path)
    if size == 0:
        return {"ok": False, "error": "文件为空"}

    if size > 100 * 1024 * 1024:  # 100MB
        return {"ok": False, "error": f"文件过大({size // 1024 // 1024}MB),建议 < 100MB"}

    fmt = Path(path).suffix.lower().lstrip(".")
    if fmt not in {f.lstrip(".") for f in SUPPORTED_FORMATS}:
        return {"ok": False, "error": f"不支持的格式: {fmt},支持: {', '.join(f.lstrip('.') for f in sorted(SUPPORTED_FORMATS))}"}

    return {"ok": True, "size": size, "format": fmt}


def call_matrix_transcribe(audio_path: str, language: str = "zh") -> Dict[str, Any]:
    """调用 matrix MCP transcribe_audio

    Args:
        audio_path: 音频文件路径(必须存在)
        language: zh / en / ja / auto

    Returns:
        {"ok": bool, "text": str, "duration": float?, "error": str?}
    """
    import json

    # 调用 mavis mcp call matrix matrix_transcribe_audio
    args_json = json.dumps({
        "audio_path": audio_path,
        "language": language,
    }, ensure_ascii=False)

    try:
        proc = subprocess.run(
            ["mavis", "mcp", "call", "matrix", "matrix_transcribe_audio", args_json],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            return {"ok": False, "error": f"MCP 调用失败: {proc.stderr[:200]}"}

        # 解析结果
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"ok": False, "error": f"无法解析结果: {proc.stdout[:200]}"}

        # 不同 MCP server 返回结构可能不同,尝试多种
        if isinstance(data, dict):
            if data.get("error"):
                return {"ok": False, "error": data["error"]}
            text = data.get("text") or data.get("transcript") or data.get("result") or ""
            return {
                "ok": True,
                "text": text,
                "language": data.get("language", language),
                "duration": data.get("duration"),
            }
        return {"ok": False, "error": f"未预期结果格式: {str(data)[:200]}"}

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "转写超时(120s)"}
    except FileNotFoundError:
        return {"ok": False, "error": "mavis 命令未找到,无法调用 MCP"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def fallback_local_whisper(audio_path: str, language: str = "zh") -> Dict[str, Any]:
    """fallback:本地 whisper(如果装了 faster-whisper)"""
    try:
        from faster_whisper import WhisperModel  # type: ignore
        model_size = os.environ.get("FR_CLI_WHISPER_MODEL", "base")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path, language=language if language != "auto" else None)
        text = "".join(seg.text for seg in segments)
        return {
            "ok": True,
            "text": text,
            "language": info.language,
            "duration": info.duration,
        }
    except ImportError:
        return {"ok": False, "error": "本地 whisper 未安装,需 pip install faster-whisper"}
    except Exception as e:
        return {"ok": False, "error": f"whisper 转写失败: {e}"}


def transcribe_audio(audio_path: str, language: str = "zh",
                     prefer_local: bool = False) -> Dict[str, Any]:
    """转写音频文件(统一入口)

    Args:
        audio_path: 音频文件路径
        language: zh / en / ja / auto
        prefer_local: True 时优先本地 whisper,否则优先 MCP

    Returns:
        {"ok": bool, "text": str, "language": str?, "duration": float?, "engine": str?, "error": str?}
    """
    # 验证
    v = validate_audio_file(audio_path)
    if not v["ok"]:
        return v

    # 选择引擎
    if prefer_local:
        result = fallback_local_whisper(audio_path, language)
        if result["ok"]:
            result["engine"] = "local-whisper"
            return result
        # 失败回退到 MCP
        result = call_matrix_transcribe(audio_path, language)
        if result["ok"]:
            result["engine"] = "matrix-mcp"
        return result
    else:
        result = call_matrix_transcribe(audio_path, language)
        if result["ok"]:
            result["engine"] = "matrix-mcp"
            return result
        # MCP 失败回退到本地
        result = fallback_local_whisper(audio_path, language)
        if result["ok"]:
            result["engine"] = "local-whisper"
        return result


def record_audio_macos(output_path: str, duration_sec: int = 0) -> Dict[str, Any]:
    """macOS 录音(用 sox 或 ffmpeg)

    Args:
        output_path: 输出 wav 路径
        duration_sec: 录音时长(0 = 手动 Ctrl+C 停止)
    """
    if not sys.platform == "darwin":
        return {"ok": False, "error": "录音功能仅支持 macOS(后续会扩展)"}

    if not shutil.which("ffmpeg") and not shutil.which("sox"):
        return {"ok": False, "error": "需要安装 ffmpeg 或 sox:brew install ffmpeg"}

    cmd = ["ffmpeg", "-y", "-f", "avfoundation", "-i", ":0"]
    if duration_sec > 0:
        cmd.extend(["-t", str(duration_sec)])
    cmd.append(output_path)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=duration_sec + 10 if duration_sec else None)
        if proc.returncode != 0 and "Exiting normally" not in proc.stderr:
            return {"ok": False, "error": f"录音失败: {proc.stderr[:200]}"}
        return {"ok": True, "path": output_path}
    except subprocess.TimeoutExpired:
        # 手动停止时 ffmpeg 超时 = 正常
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return {"ok": True, "path": output_path}
        return {"ok": False, "error": "录音失败或中断"}
    except KeyboardInterrupt:
        return {"ok": True, "path": output_path}


import sys  # 放到底部避免循环 import
