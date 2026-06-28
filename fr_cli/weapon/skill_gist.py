"""
Skill 远程共享 —— 通过 GitHub Gist 分享 / 导入 skill

策略:
- /skill_share <name>:导出本地 skill 为 .md,推送到 GitHub Gist(需 token)
- /skill_import <gist_url|id>:从 Gist 拉取 .md,保存到本地 ~/.fr_cli/skills/
- /skill_browse [query]:浏览社区热门 skills(走 GitHub gist 搜索 API)

Gist API:
- POST https://api.github.com/gists(创建)
- GET https://api.github.com/gists/<id>(读取)
- 不需要 token 也可以创建匿名 Gist(只读权限)
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Dict, Any, Optional

from fr_cli.conf.paths import ROOT as FR_CLI_DIR


SKILLS_DIR = FR_CLI_DIR / "skills_remote"
GIST_API = "https://api.github.com"
DEFAULT_TIMEOUT = 30


def _ensure_skills_dir() -> Path:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    return SKILLS_DIR


def _http_request(url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None,
                  data: Optional[Dict[str, Any]] = None,
                  timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """HTTP 请求封装"""
    headers = headers or {}
    if "User-Agent" not in headers:
        headers["User-Agent"] = "fr-cli"
    if data is not None and "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
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
        return {
            "ok": False,
            "status": e.code,
            "error": f"HTTP {e.code}: {e.reason}",
            "body": e.read().decode("utf-8", errors="ignore")[:500],
        }
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"URL 错误: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_token() -> Optional[str]:
    """获取 GitHub Token(从 env 或 config)"""
    # 1. 环境变量
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    # 2. config.json
    try:
        from fr_cli.conf.config import load_config
        cfg = load_config()
        return cfg.get("gist_token") or cfg.get("github_token")
    except Exception:
        return None


def load_local_skill(name: str) -> Optional[Dict[str, Any]]:
    """加载本地 skill 文件

    Returns:
        {"name", "content", "path"} 或 None
    """
    # 优先看 ~/.fr_cli/skills/<name>.md
    candidates = [
        FR_CLI_DIR / "skills" / f"{name}.md",
        FR_CLI_DIR / "skills_remote" / f"{name}.md",
    ]
    for path in candidates:
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                return {"name": name, "content": content, "path": str(path)}
            except Exception:
                continue
    return None


def share_skill(name: str, description: str = "", public: bool = True) -> Dict[str, Any]:
    """分享 skill 到 Gist

    Args:
        name: skill 名称
        description: 描述
        public: 是否公开(True = 任何人都能搜索到)

    Returns:
        {"ok": bool, "gist_id": str, "url": str, "error": str?}
    """
    local = load_local_skill(name)
    if not local:
        return {"ok": False, "error": f"找不到本地 skill: {name}"}

    token = get_token()
    if not token:
        return {"ok": False, "error": "需要 GitHub Token(环境变量 GITHUB_TOKEN 或 config gist_token)"}

    payload = {
        "description": description or f"fr-cli skill: {name}",
        "public": public,
        "files": {
            f"{name}.md": {
                "content": local["content"],
            }
        },
    }

    result = _http_request(
        f"{GIST_API}/gists",
        method="POST",
        headers={"Authorization": f"token {token}"},
        data=payload,
    )

    if not result["ok"]:
        return {"ok": False, "error": result.get("error", "Gist 创建失败")}

    data = result.get("data") or {}
    gist_id = data.get("id", "")
    html_url = data.get("html_url", "")

    # 记录到本地
    rp = _ensure_skills_dir()
    record_file = rp / "shared_skills.json"
    try:
        if record_file.exists():
            records = json.loads(record_file.read_text(encoding="utf-8"))
        else:
            records = {"shared": []}
        records["shared"].append({
            "name": name,
            "gist_id": gist_id,
            "url": html_url,
            "shared_at": time.time(),
            "public": public,
        })
        record_file.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {
        "ok": True,
        "gist_id": gist_id,
        "url": html_url,
        "name": name,
    }


def parse_gist_url(url_or_id: str) -> Optional[str]:
    """解析 gist URL 或 ID,返回 gist_id"""
    if not url_or_id:
        return None
    # 完整 URL:https://gist.github.com/user/abc123
    m = re.match(r"https?://gist\.github\.com/(?:[^/]+/)?([a-fA-F0-9]+)", url_or_id)
    if m:
        return m.group(1)
    # 短 URL:https://gist.github.com/abc123
    m = re.match(r"https?://gist\.github\.com/([a-fA-F0-9]+)", url_or_id)
    if m:
        return m.group(1)
    # 纯 ID
    if re.match(r"^[a-fA-F0-9]+$", url_or_id):
        return url_or_id
    return None


def import_skill(gist_url_or_id: str, name: Optional[str] = None) -> Dict[str, Any]:
    """从 Gist 导入 skill

    Args:
        gist_url_or_id: Gist URL 或 ID
        name: 重命名(默认用文件名)

    Returns:
        {"ok": bool, "name": str, "path": str, "url": str, "error": str?}
    """
    gist_id = parse_gist_url(gist_url_or_id)
    if not gist_id:
        return {"ok": False, "error": f"无效的 Gist URL/ID: {gist_url_or_id}"}

    result = _http_request(f"{GIST_API}/gists/{gist_id}")
    if not result["ok"]:
        return {"ok": False, "error": result.get("error", "Gist 读取失败")}

    data = result.get("data") or {}
    files = data.get("files", {})

    # 找第一个 .md 文件
    md_file = None
    for filename, file_data in files.items():
        if filename.endswith(".md"):
            md_file = file_data
            md_filename = filename
            break

    if not md_file:
        return {"ok": False, "error": "Gist 中没有 .md 文件"}

    content = md_file.get("content", "")
    if not content:
        return {"ok": False, "error": "Gist 文件内容为空"}

    # 默认 name 用文件名
    if not name:
        name = md_filename[:-3]  # 去 .md 后缀

    # 保存到本地
    rp = _ensure_skills_dir()
    target = rp / f"{name}.md"
    target.write_text(content, encoding="utf-8")

    return {
        "ok": True,
        "name": name,
        "path": str(target),
        "url": data.get("html_url", ""),
        "gist_id": gist_id,
    }


def list_shared_skills() -> List[Dict[str, Any]]:
    """列出本地共享过的 skills"""
    record_file = _ensure_skills_dir() / "shared_skills.json"
    if not record_file.exists():
        return []
    try:
        data = json.loads(record_file.read_text(encoding="utf-8"))
        return data.get("shared", [])
    except Exception:
        return []


def search_gists(query: str, limit: int = 10) -> Dict[str, Any]:
    """搜索 Gist(用 GitHub Code Search API 的替代)

    注意:GitHub 没有专门的 Gist search API,这里用 Gist list by user(需要 token)
    或公共的 gist 列表 API。

    Returns:
        {"ok": bool, "results": [...], "error": str?}
    """
    # GitHub Code Search(API v3 限制)
    # 用 web search 风格:抓 gist.github.com/search?q=...
    # 由于没有官方搜索 API,这里给提示用户手动访问
    search_url = f"https://gist.github.com/search?q={urllib.parse.quote(query)}"
    return {
        "ok": True,
        "results": [],
        "note": f"无官方 Gist 搜索 API。请访问: {search_url}",
        "search_url": search_url,
    }


def format_shared_skills(records: List[Dict[str, Any]], lang: str = "zh") -> str:
    """格式化共享记录"""
    if not records:
        return "没有共享记录" if lang == "zh" else "No shared records"

    if lang == "zh":
        title = "🌐 已共享的 Skills"
    else:
        title = "🌐 Shared Skills"

    lines = [f"{title} ({len(records)}):"]
    for r in records:
        lines.append(f"  📦 {r['name']}")
        lines.append(f"     Gist: {r['gist_id']}")
        lines.append(f"     URL: {r['url']}")
        if r.get("shared_at"):
            from datetime import datetime
            ts = datetime.fromtimestamp(r["shared_at"]).strftime("%Y-%m-%d %H:%M")
            lines.append(f"     分享于: {ts}")
    return "\n".join(lines)
