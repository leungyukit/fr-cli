"""
Ollama 本地 LLM 集成 —— 离线/本地推理

策略:
- 探测本地 Ollama 服务(http://localhost:11434/api/tags)
- 列出已下载模型
- 提供 pull/delete 模型能力
- 通过 OpenAI 兼容协议接入 fr-cli(已有 ollama provider 配置)

命令:
- /ollama_status: 检查 Ollama 是否运行,列出模型
- /ollama_pull <model>: 下载模型
- /ollama_rm <model>: 删除模型
- /ollama_use <model>: 切换当前 provider 到 ollama + 指定 model
- /ollama_setup: 配置(自动检测 base_url)

API:
- GET /api/tags: 列出本地模型
- POST /api/pull: 下载模型(流式)
- DELETE /api/delete: 删除模型
- POST /api/show: 显示模型详情
"""
import json
import urllib.error
import urllib.request
from typing import Dict, Any, Optional, Iterator


DEFAULT_OLLAMA_URL = "http://localhost:11434"


def _http_request(url: str, method: str = "GET",
                  headers: Optional[Dict[str, str]] = None,
                  data: Optional[Dict[str, Any]] = None,
                  timeout: int = 10,
                  stream: bool = False) -> Dict[str, Any]:
    """HTTP 请求

    stream=True 时返回 {"ok", "iter": iterator of lines}
    否则返回 {"ok", "status", "data", "raw"}
    """
    headers = headers or {}
    if "Content-Type" not in headers and data is not None:
        headers["Content-Type"] = "application/json"

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        if stream:
            resp = urllib.request.urlopen(req, timeout=timeout)
            return {"ok": True, "response": resp, "status": resp.status}
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            response_body = resp.read().decode("utf-8")
            try:
                return {
                    "ok": True,
                    "status": resp.status,
                    "data": json.loads(response_body),
                    "raw": response_body,
                }
            except json.JSONDecodeError:
                return {"ok": True, "status": resp.status, "data": None, "raw": response_body}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")[:500]
        return {"ok": False, "status": e.code, "error": f"HTTP {e.code}: {e.reason}", "body": body}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"无法连接 Ollama({e.reason}):请先启动 ollama serve"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def detect_ollama(base_url: str = DEFAULT_OLLAMA_URL) -> Dict[str, Any]:
    """探测 Ollama 是否在运行

    Returns:
        {"ok": bool, "version": str, "error": str?}
    """
    r = _http_request(f"{base_url}/api/version")
    if not r["ok"]:
        return {"ok": False, "error": r.get("error", "无法连接")}
    data = r.get("data") or {}
    return {"ok": True, "version": data.get("version", "unknown")}


def list_models(base_url: str = DEFAULT_OLLAMA_URL) -> Dict[str, Any]:
    """列出本地已下载的模型

    Returns:
        {"ok": bool, "models": [{name, size, modified_at, details}], "error": str?}
    """
    r = _http_request(f"{base_url}/api/tags")
    if not r["ok"]:
        return {"ok": False, "error": r.get("error", "查询失败"), "models": []}

    data = r.get("data") or {}
    models = data.get("models", [])
    # 规范化字段
    normalized = []
    for m in models:
        normalized.append({
            "name": m.get("name", ""),
            "size": m.get("size", 0),
            "size_human": _human_size(m.get("size", 0)),
            "modified_at": m.get("modified_at", ""),
            "family": m.get("details", {}).get("family", ""),
            "parameter_size": m.get("details", {}).get("parameter_size", ""),
            "quantization_level": m.get("details", {}).get("quantization_level", ""),
        })
    return {"ok": True, "models": normalized}


def _human_size(size_bytes: int) -> str:
    """字节 → 人类可读"""
    if not size_bytes:
        return "?"
    units = ["B", "KB", "MB", "GB", "TB"]
    n = 0
    while size_bytes >= 1024 and n < len(units) - 1:
        size_bytes /= 1024
        n += 1
    return f"{size_bytes:.1f}{units[n]}"


def pull_model(model_name: str, base_url: str = DEFAULT_OLLAMA_URL,
               stream: bool = True) -> Iterator[Dict[str, Any]]:
    """下载模型(流式)

    Yields:
        {"status": str, "completed": int?, "total": int?, "error": str?}
    """
    try:
        url = f"{base_url}/api/pull"
        req = urllib.request.Request(
            url,
            data=json.dumps({"name": model_name, "stream": True}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=None) as resp:
            for line in resp:
                line = line.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    yield {"status": line, "error": "parse failed"}
    except Exception as e:
        yield {"error": str(e)}


def delete_model(model_name: str, base_url: str = DEFAULT_OLLAMA_URL) -> Dict[str, Any]:
    """删除本地模型"""
    r = _http_request(
        f"{base_url}/api/delete",
        method="DELETE",
        data={"name": model_name},
    )
    return {"ok": r["ok"], "error": r.get("error")}


def show_model(model_name: str, base_url: str = DEFAULT_OLLAMA_URL) -> Dict[str, Any]:
    """显示模型详情"""
    r = _http_request(
        f"{base_url}/api/show",
        method="POST",
        data={"name": model_name},
    )
    return r


def format_status(base_url: str = DEFAULT_OLLAMA_URL) -> str:
    """格式化 Ollama 状态"""
    det = detect_ollama(base_url)
    if not det["ok"]:
        return (
            f"❌ Ollama 未运行\n"
            f"  地址: {base_url}\n"
            f"  错误: {det.get('error', '?')}\n\n"
            f"💡 启动方式:\n"
            f"  1. 安装: https://ollama.com/download\n"
            f"  2. 运行: ollama serve\n"
            f"  3. 下载模型: ollama pull llama3.2"
        )

    models_r = list_models(base_url)
    version = det.get("version", "?")
    if not models_r["ok"]:
        models_text = f"  模型列表失败: {models_r.get('error', '?')}"
    else:
        ms = models_r["models"]
        if not ms:
            models_text = "  (暂无模型,运行 ollama pull llama3.2 下载)"
        else:
            lines = []
            for m in ms:
                lines.append(f"  • {m['name']} ({m['size_human']}) [{m['parameter_size']}]")
            models_text = "\n".join(lines)

    return (
        f"✅ Ollama 运行中\n"
        f"  版本: {version}\n"
        f"  地址: {base_url}\n"
        f"  模型 ({len(models_r.get('models', []))}):\n{models_text}"
    )
