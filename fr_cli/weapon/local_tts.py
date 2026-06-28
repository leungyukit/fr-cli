"""
本地 TTS 集成 —— 系统命令直接朗读,无需 MCP / 云服务

平台支持:
- macOS:`say` 命令(系统自带)
- Linux:`espeak` / `spd-say` / `festival`(需装)
- Windows:SAPI COM(`win32com.client`)

命令:
- /say "你好世界":朗读文本
- /say -o out.aiff "hello":保存到文件
- /voices:列出可用声音(macOS)
"""
import platform
import shutil
import subprocess
import threading
from typing import List, Dict, Any, Optional


def detect_tts_engine() -> Dict[str, Any]:
    """探测可用的 TTS 引擎

    Returns:
        {"ok": bool, "engine": "say"/"espeak"/..., "platform": "Darwin"|"Linux"|"Windows", "error": str?}
    """
    system = platform.system()

    if system == "Darwin":
        if shutil.which("say"):
            try:
                r = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=5)
                return {"ok": True, "engine": "say", "platform": "Darwin",
                        "voices": _parse_say_voices(r.stderr)}
            except Exception:
                return {"ok": True, "engine": "say", "platform": "Darwin"}
        return {"ok": False, "engine": None, "platform": "Darwin", "error": "say 命令不存在"}

    elif system == "Linux":
        for cmd in ["espeak", "spd-say", "festival", "flite"]:
            if shutil.which(cmd):
                return {"ok": True, "engine": cmd, "platform": "Linux"}
        return {"ok": False, "engine": None, "platform": "Linux",
                "error": "需要安装 espeak / spd-say / festival(brew install espeak / apt install espeak)"}

    elif system == "Windows":
        try:
            __import__("win32com.client")  # noqa: F401  # type: ignore
            return {"ok": True, "engine": "sapi", "platform": "Windows"}
        except ImportError:
            return {"ok": False, "engine": None, "platform": "Windows",
                    "error": "需要 pywin32:pip install pywin32"}

    return {"ok": False, "engine": None, "platform": system, "error": "不支持的平台"}


# 去除冗余 normalize 函数


def _parse_say_voices(text: str) -> List[Dict[str, str]]:
    """解析 `say -v ?` 输出

    格式示例:
    #  Samantha               en_US    # Sample of computer generated voice
    """
    voices = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            voice = {
                "name": parts[0],
                "lang": parts[1] if len(parts) > 1 else "",
            }
            voices.append(voice)
    return voices


def speak(text: str, voice: Optional[str] = None,
          rate: Optional[int] = None,
          output_file: Optional[str] = None,
          async_play: bool = False) -> Dict[str, Any]:
    """朗读文本

    Args:
        text: 要朗读的文本
        voice: 声音名(macOS:"Samantha" / "Tingting" / Linux:"-v en+f3")
        rate: 语速(words per minute,macOS 默认 175)
        output_file: 输出文件路径(macOS .aiff / Linux .wav)
        async_play: 异步播放(不阻塞)

    Returns:
        {"ok": bool, "engine": str, "file": str?, "pid": int?, "error": str?}
    """
    det = detect_tts_engine()
    if not det["ok"]:
        return det

    engine = det["engine"]
    system = det["platform"]

    if system == "Darwin" and engine == "say":
        cmd = ["say"]
        if voice:
            cmd.extend(["-v", voice])
        if rate:
            cmd.extend(["-r", str(rate)])
        if output_file:
            cmd.extend(["-o", output_file])
        cmd.append(text)

    elif system == "Linux" and engine == "espeak":
        cmd = ["espeak"]
        if voice:
            cmd.extend(["-v", voice])
        if rate:
            cmd.extend(["-s", str(rate)])
        if output_file:
            cmd.extend(["-w", output_file])
        cmd.append(text)

    elif system == "Linux" and engine == "spd-say":
        cmd = ["spd-say"]
        if voice:
            cmd.extend(["-l", voice])
        cmd.append(text)

    elif system == "Linux" and engine in ("festival", "flite"):
        # 通过 stdin 喂文本
        cmd = [engine]
        if output_file and engine == "flite":
            cmd.extend(["-o", output_file])
        if engine == "flite" and output_file:
            cmd.extend(["-voice", voice or "slt"])
        # festival 用 --tts
        if engine == "festival":
            cmd = ["festival", "--tts"]
        cmd = [c for c in cmd if c]

    elif system == "Windows" and engine == "sapi":
        # 通过 win32com 同步播
        try:
            import win32com.client  # type: ignore
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            if voice:
                try:
                    speaker.Voice = speaker.GetVoices().Item(voice)
                except Exception:
                    pass
            if rate:
                speaker.Rate = rate
            stream = None
            if output_file:
                # 输出到文件
                stream = win32com.client.Dispatch("SAPI.SpFileStream")
                stream.Format.Type = 22  # WAV
                stream.Open(output_file)
                stream.AudioOutputStream = stream
                speaker.AudioOutputStream = stream
            if async_play:
                speaker.Speak(text)
            else:
                speaker.Speak(text)
                if stream:
                    stream.Close()
            return {"ok": True, "engine": engine, "file": output_file}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    else:
        return {"ok": False, "error": f"不支持的引擎: {engine}"}

    try:
        if async_play:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            return {"ok": True, "engine": engine, "pid": proc.pid,
                    "file": output_file, "async": True}
        else:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                return {"ok": False, "engine": engine,
                        "error": proc.stderr or "TTS 失败"}
            return {"ok": True, "engine": engine, "file": output_file}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "TTS 朗读超时(120s)"}
    except FileNotFoundError:
        return {"ok": False, "error": f"找不到命令: {cmd[0]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_voices() -> List[Dict[str, str]]:
    """列出可用声音"""
    det = detect_tts_engine()
    if not det["ok"]:
        return []

    if det["platform"] == "Darwin" and det.get("voices"):
        return det["voices"]

    # Linux / Windows 简单返回
    return [{"name": "default", "lang": "?"}]


def format_voices(voices: List[Dict[str, str]], lang: str = "zh") -> str:
    """格式化声音列表"""
    if not voices:
        return "📢 没有可用声音"

    lines = [f"📢 可用声音 ({len(voices)}):"]
    for v in voices[:30]:
        name = v.get("name", "")
        language = v.get("lang", "")
        lines.append(f"  • {name} ({language})")
    if len(voices) > 30:
        lines.append(f"  ... 还有 {len(voices) - 30} 个")
    return "\n".join(lines)


def speak_stream(text: str, voice: Optional[str] = None,
                  rate: Optional[int] = None,
                  chunk_size: int = 200,
                  on_chunk: Optional[callable] = None,
                  async_play: bool = False) -> Dict[str, Any]:
    """流式 TTS —— 分块朗读长文本

    把长文本按句号/段落拆成多个小块,逐块朗读。优势:
    - 避免单个 say 命令参数过长被截断
    - 可以边生成边朗读(传入 on_chunk 回调)
    - 失败时已经播的部分不会中断
    - 后台线程顺序播,主线程不阻塞

    Args:
        text: 要朗读的长文本
        voice: 声音
        rate: 语速
        chunk_size: 每块最大字符数(默认 200)
        on_chunk: 块播完后回调 fn(chunk_text, index)
        async_play: True 时不等待播完

    Returns:
        {"ok": bool, "chunks": int, "engine": str, "errors": [...]}
    """
    det = detect_tts_engine()
    if not det["ok"]:
        return det

    # 分块:优先按句子分(。!?\n),再按 chunk_size
    import re
    chunks = []
    remaining = text.strip()

    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            remaining = ""
        else:
            # 在 chunk_size 范围内找最近的句末标点
            best_end = chunk_size
            for m in re.finditer(r"[。.!?\n]", remaining[:chunk_size + 50]):
                if m.end() > best_end:
                    continue  # 跳过超过 chunk_size 的
                best_end = m.end()
            if best_end <= 0:
                best_end = chunk_size  # 没找到标点,硬切
            chunks.append(remaining[:best_end])
            remaining = remaining[best_end:].lstrip()

    if not chunks:
        return {"ok": False, "error": "空文本", "chunks": 0}

    def _play_all():
        errors = []
        for i, chunk in enumerate(chunks):
            try:
                speak(chunk, voice=voice, rate=rate, async_play=False)
                if on_chunk:
                    try:
                        on_chunk(chunk, i)
                    except Exception:
                        pass
            except Exception as e:
                errors.append({"chunk": i, "error": str(e)})
        return errors

    if async_play:
        thread = threading.Thread(target=_play_all, daemon=True, name="fr-cli-tts-stream")
        thread.start()
        return {"ok": True, "chunks": len(chunks), "engine": det["engine"],
                "async": True, "thread": thread.name}

    errors = _play_all()
    return {
        "ok": len(errors) == 0,
        "chunks": len(chunks),
        "engine": det["engine"],
        "errors": errors,
    }
