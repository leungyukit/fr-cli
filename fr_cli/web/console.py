"""
Web 控制台 —— 浏览器查看 fr-cli 状态

功能:
- 启动本地 HTTP 服务(默认 127.0.0.1:7777)
- 提供 REST API:
  - GET /                : 首页 HTML
  - GET /api/status      : 全局状态(provider / model / 工作目录 / 后台任务数)
  - GET /api/sessions    : 列出最近会话
  - GET /api/sessions/<idx> : 查看会话详情
  - GET /api/tasks       : 列出 Hermes 任务
  - GET /api/worktrees   : 列出所有 worktree
  - GET /api/bookmarks   : 列出 bookmark
  - GET /api/stats       : 统计(消息数 / 用量 / RAG 缓存命中率)

- 默认绑定 127.0.0.1(不暴露公网)
- Bearer Token 鉴权(随机生成,启动时打印一次)
- 后台 daemon thread,不影响 REPL
"""
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, parse_qs

from fr_cli.conf.paths import ROOT as FR_CLI_DIR
from fr_cli.core.store import JsonStore


CONSOLE_DIR = FR_CLI_DIR / "console"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7777


# --------------------------- 数据聚合 ---------------------------

def _get_global_status(state=None) -> Dict[str, Any]:
    """聚合全局状态"""
    status = {
        "timestamp": time.time(),
        "cwd": os.getcwd(),
        "provider": None,
        "model": None,
        "key_configured": False,
        "hermes_tasks": 0,
        "cron_jobs": 0,
        "agent_count": 0,
        "worktree_count": 0,
        "bookmark_count": 0,
        "session_count": 0,
    }

    try:
        from fr_cli.conf.config import load_config
        cfg = load_config()
        status["provider"] = cfg.get("provider")
        status["model"] = cfg.get("model")
        status["key_configured"] = bool(cfg.get("key"))
        status["autonomous_mode"] = cfg.get("autonomous_mode", "manual")
    except Exception:
        pass

    # Hermes 任务
    try:
        tasks_file = FR_CLI_DIR / "hermes" / "tasks.json"
        if tasks_file.exists():
            data = JsonStore(str(tasks_file), default=dict).read()
            status["hermes_tasks"] = len(data.get("tasks", []))
    except Exception:
        pass

    # Cron jobs
    try:
        cron_file = FR_CLI_DIR / "cron.json"
        if cron_file.exists():
            data = JsonStore(str(cron_file), default=dict).read()
            status["cron_jobs"] = len(data.get("jobs", []))
    except Exception:
        pass

    # Agent 数量
    try:
        agents_dir = FR_CLI_DIR / "agents"
        if agents_dir.exists():
            status["agent_count"] = sum(
                1 for d in agents_dir.iterdir()
                if d.is_dir() and (d / "persona.md").exists()
            )
    except Exception:
        pass

    # Worktree 数量
    try:
        from fr_cli.weapon.worktree_cleanup import list_worktrees_for_cleanup
        status["worktree_count"] = len(list_worktrees_for_cleanup())
    except Exception:
        pass

    # Bookmark 数量
    try:
        bm_file = FR_CLI_DIR / "bookmarks" / "bookmarks.json"
        if bm_file.exists():
            data = JsonStore(str(bm_file), default=dict).read()
            status["bookmark_count"] = len(data.get("bookmarks", []))
    except Exception:
        pass

    # Session 数量
    try:
        from fr_cli.memory.session import list_sessions
        status["session_count"] = len(list_sessions())
    except Exception:
        pass

    return status


def _get_sessions_list(limit: int = 50) -> List[Dict[str, Any]]:
    """列出最近会话"""
    try:
        from fr_cli.memory.session import list_sessions
        return list_sessions()[:limit]
    except Exception:
        return []


def _get_session_detail(idx: int) -> Optional[Dict[str, Any]]:
    """获取会话详情"""
    try:
        from fr_cli.memory.session import load_session
        ok, msgs, filename = load_session(idx)
        if ok:
            return {"filename": filename, "messages": msgs, "count": len(msgs)}
    except Exception:
        pass
    return None


def _get_hermes_tasks() -> List[Dict[str, Any]]:
    """列出 Hermes 任务"""
    try:
        # 简化:直接读 JSON
        tasks_file = FR_CLI_DIR / "hermes" / "tasks.json"
        if tasks_file.exists():
            data = JsonStore(str(tasks_file), default=dict).read()
            return data.get("tasks", [])
    except Exception:
        pass
    return []


def _get_worktrees() -> List[Dict[str, Any]]:
    """列出 worktree"""
    try:
        from fr_cli.weapon.worktree_cleanup import list_worktrees_for_cleanup
        return list_worktrees_for_cleanup()
    except Exception:
        return []


def _get_bookmarks(limit: int = 100) -> List[Dict[str, Any]]:
    """列出 bookmark"""
    try:
        from fr_cli.weapon.bookmark import list_bookmarks
        return list_bookmarks(limit=limit)
    except Exception:
        return []


def _get_stats() -> Dict[str, Any]:
    """统计信息"""
    stats = {
        "total_messages": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
        "rag_cache_hits": 0,
        "rag_cache_total": 0,
    }
    try:
        usage_file = FR_CLI_DIR / "usage.json"
        if usage_file.exists():
            data = JsonStore(str(usage_file), default=dict).read()
            calls = data.get("calls", [])
            stats["total_messages"] = len(calls)
            stats["total_tokens"] = sum(c.get("total_tokens", 0) for c in calls)
            stats["total_cost"] = sum(c.get("cost", 0) for c in calls)
    except Exception:
        pass

    try:
        # 单实例,检查 cache 统计
        # 注:实际命中率需要在 RAGManager 里调用
        stats["rag_cache_total"] = 1
    except Exception:
        pass

    return stats


# --------------------------- HTTP 服务 ---------------------------

_console_state = {
    "server": None,
    "thread": None,
    "token": None,
    "host": DEFAULT_HOST,
    "port": DEFAULT_PORT,
    "running": False,
}

# v2.8+:SSE 事件队列(多客户端)
_sse_clients: List[threading.Event] = []
_sse_history: List[Dict[str, Any]] = []  # 最近 50 条事件(供新客户端拉取)
_sse_history_max = 50
_sse_lock = threading.Lock()


def push_event(event_type: str, data: Dict[str, Any]):
    """推送一个 SSE 事件给所有连接的客户端

    Args:
        event_type: 事件类型(status / task / log / custom)
        data: 事件数据(dict)
    """
    global _sse_history
    event = {
        "type": event_type,
        "timestamp": time.time(),
        "data": data,
    }
    with _sse_lock:
        _sse_history.append(event)
        if len(_sse_history) > _sse_history_max:
            _sse_history = _sse_history[-_sse_history_max:]
        # 通知所有等待中的客户端
        clients = list(_sse_clients)
    for ev in clients:
        try:
            ev.set()
        except Exception:
            pass


def get_recent_events(limit: int = 50) -> List[Dict[str, Any]]:
    """获取最近的事件(给新客户端)"""
    global _sse_history
    with _sse_lock:
        return list(_sse_history[-limit:])


def _generate_token() -> str:
    """生成随机 token"""
    return secrets.token_hex(16)


def _make_handler(token: str) -> type:
    """构造 HTTP handler 类"""

    class ConsoleHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # 静默日志

        def _send_json(self, data: Dict[str, Any], status: int = 200):
            body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html: str, status: int = 200):
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_static(self, filename: str, content_type: str,
                          cache_max_age: int = 3600):
            """服务 PWA 静态文件"""
            from pathlib import Path as _P
            static_file = _P(__file__).parent / "static" / filename
            if not static_file.exists():
                self.send_response(404)
                self.end_headers()
                return
            try:
                body = static_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", f"max-age={cache_max_age}")
                self.send_header("Service-Worker-Allowed", "/")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                self.send_response(500)
                self.end_headers()

        def _check_auth(self) -> bool:
            """Bearer Token 鉴权"""
            auth = self.headers.get("Authorization", "")
            if auth == f"Bearer {token}":
                return True
            # 也接受 query 参数 ?token=xxx(便于浏览器)
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            if qs.get("token", [None])[0] == token:
                return True
            return False

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if not self._check_auth():
                self.send_response(401)
                self.end_headers()
                return

            # 读 body
            length = int(self.headers.get("Content-Length", 0))
            body_raw = self.rfile.read(length) if length > 0 else b""
            try:
                _body = json.loads(body_raw.decode("utf-8")) if body_raw else {}
            except Exception:
                _body = {}

            if path == "/api/command":
                # 预留:从 web 端发命令(需要额外鉴权)
                self._send_json({"ok": False, "error": "Web 命令未启用(安全考虑)"}, 403)
            elif path == "/api/event":
                # 接收客户端发来的事件(上传日志等)
                try:
                    push_event(_body.get("type", "client"), _body.get("data", {}))
                    self._send_json({"ok": True})
                except Exception as e:
                    self._send_json({"ok": False, "error": str(e)})
            else:
                self._send_json({"ok": False, "error": f"Unknown endpoint: {path}"}, 404)

        def do_GET(self):  # noqa: F811 — 重复定义是为了保留 SSE 流式实现
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            # PWA 静态资源(免鉴权)
            if path == "/manifest.json":
                self._serve_static("manifest.json", "application/manifest+json")
                return
            if path == "/icon.svg":
                self._serve_static("icon.svg", "image/svg+xml")
                return
            if path == "/sw.js":
                self._serve_static("sw.js", "application/javascript",
                                   cache_max_age=0)
                return

            # 首页(免鉴权)
            if path == "/" or path == "/index.html":
                self._send_html(_render_homepage(token))
                return

            # SSE 实时推送
            if path == "/api/events":
                if not self._check_auth():
                    self.send_response(401)
                    self.end_headers()
                    return
                self._handle_sse()
                return

            # 鉴权
            if not self._check_auth():
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Unauthorized, use Authorization: Bearer <token> or ?token=<token>"}')
                return

            # API
            if path == "/api/status":
                self._send_json({"ok": True, "data": _get_global_status()})
            elif path == "/api/sessions":
                limit = int(qs.get("limit", [50])[0])
                self._send_json({"ok": True, "data": _get_sessions_list(limit)})
            elif path.startswith("/api/sessions/"):
                idx = int(path.split("/")[-1])
                detail = _get_session_detail(idx)
                if detail:
                    self._send_json({"ok": True, "data": detail})
                else:
                    self._send_json({"ok": False, "error": "会话不存在"}, 404)
            elif path == "/api/tasks":
                self._send_json({"ok": True, "data": _get_hermes_tasks()})
            elif path == "/api/worktrees":
                self._send_json({"ok": True, "data": _get_worktrees()})
            elif path == "/api/bookmarks":
                limit = int(qs.get("limit", [100])[0])
                self._send_json({"ok": True, "data": _get_bookmarks(limit)})
            elif path == "/api/stats":
                self._send_json({"ok": True, "data": _get_stats()})
            elif path == "/api/health":
                self._send_json({"ok": True, "service": "fr-cli-console"})
            else:
                self._send_json({"ok": False, "error": f"Unknown endpoint: {path}"}, 404)

        def _handle_sse(self):
            """SSE 长连接处理器"""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")  # 禁用 nginx 缓冲
            self.end_headers()

            # 先发历史
            try:
                for event in get_recent_events(limit=20):
                    line = f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    self.wfile.write(line.encode("utf-8"))
                    self.wfile.flush()
            except Exception:
                return

            # 注册客户端
            global _sse_clients
            event_signal = threading.Event()
            with _sse_lock:
                _sse_clients.append(event_signal)

            try:
                last_ping = time.time()
                while True:
                    signaled = event_signal.wait(timeout=15.0)
                    if signaled:
                        event_signal.clear()
                        # 拉取最新事件
                        try:
                            for event in get_recent_events(limit=10):
                                line = f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                                self.wfile.write(line.encode("utf-8"))
                                self.wfile.flush()
                        except Exception:
                            return

                    # 心跳(防止 proxy 切断)
                    now = time.time()
                    if now - last_ping > 10:
                        try:
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                        except Exception:
                            return
                        last_ping = now
            finally:
                with _sse_lock:
                    if event_signal in _sse_clients:
                        _sse_clients.remove(event_signal)

    return ConsoleHandler


def _render_homepage(token: str) -> str:
    """渲染首页 HTML(包含导航 + token 提示 + PWA)"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>fr-cli 控制台</title>
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#58a6ff">
<link rel="icon" type="image/svg+xml" href="/icon.svg">
<link rel="apple-touch-icon" href="/icon.svg">
<meta name="apple-mobile-web-app-capable" content="yes">
<style>
:root {{
  --bg: #0d1117;
  --bg-2: #161b22;
  --border: #30363d;
  --text: #c9d1d9;
  --text-2: #8b949e;
  --accent: #58a6ff;
  --green: #3fb950;
  --red: #f85149;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, "PingFang SC", sans-serif;
  padding: 24px;
  line-height: 1.5;
}}
h1 {{ color: var(--accent); margin-bottom: 16px; }}
nav {{ display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }}
nav a {{
  background: var(--bg-2);
  border: 1px solid var(--border);
  padding: 8px 16px;
  border-radius: 6px;
  color: var(--text);
  text-decoration: none;
  cursor: pointer;
}}
nav a:hover {{ border-color: var(--accent); }}
.token-box {{
  background: var(--bg-2);
  border: 1px solid var(--border);
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 16px;
  font-family: monospace;
  word-break: break-all;
}}
.section {{
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 16px;
}}
.section h2 {{ font-size: 18px; margin-bottom: 12px; color: var(--accent); }}
.stat-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }}
.stat {{
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 12px;
  border-radius: 6px;
}}
.stat .label {{ color: var(--text-2); font-size: 12px; }}
.stat .value {{ font-size: 24px; font-weight: 600; color: var(--accent); margin-top: 4px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid var(--border); font-size: 13px; }}
th {{ color: var(--text-2); font-weight: 500; }}
pre {{ background: var(--bg); padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 12px; }}
.loading {{ color: var(--text-2); font-style: italic; }}
</style>
</head>
<body>
<h1>🎛️ fr-cli Web 控制台</h1>

<div class="token-box">
  <strong>Bearer Token:</strong> <code id="token">{token}</code>
  <br><small style="color: var(--text-2);">
    API 调用时加 <code>?token={token}</code> 或 <code>Authorization: Bearer {token}</code>
  </small>
</div>

<nav>
  <a onclick="document.getElementById('content').dataset.active='status'; load('status')">📊 全局状态</a>
  <a onclick="document.getElementById('content').dataset.active='sessions'; load('sessions')">💬 会话</a>
  <a onclick="document.getElementById('content').dataset.active='tasks'; load('tasks')">⚙️ Hermes 任务</a>
  <a onclick="document.getElementById('content').dataset.active='worktrees'; load('worktrees')">🌳 Worktree</a>
  <a onclick="document.getElementById('content').dataset.active='bookmarks'; load('bookmarks')">📚 Bookmark</a>
  <a onclick="document.getElementById('content').dataset.active='stats'; load('stats')">📈 统计</a>
</nav>

<div class="section" style="max-height:200px;overflow-y:auto;">
  <h2>📡 实时事件 (SSE)</h2>
  <div id="event-log"><p class="loading">等待事件...</p></div>
</div>

<div id="content" class="section">
  <p class="loading">点击上方按钮加载数据...</p>
</div>

<script>
const TOKEN = '{token}';
async function fetchJSON(path) {{
  const resp = await fetch(path + (path.includes('?') ? '&' : '?') + 'token=' + TOKEN);
  return resp.json();
}}

function renderStatus(d) {{
  return `
    <h2>📊 全局状态</h2>
    <div class="stat-grid">
      <div class="stat"><div class="label">Provider</div><div class="value">${{d.provider || '-'}}</div></div>
      <div class="stat"><div class="label">Model</div><div class="value">${{d.model || '-'}}</div></div>
      <div class="stat"><div class="label">API Key</div><div class="value">${{d.key_configured ? '✅' : '❌'}}</div></div>
      <div class="stat"><div class="label">自治模式</div><div class="value">${{d.autonomous_mode || '-'}}</div></div>
      <div class="stat"><div class="label">Hermes 任务</div><div class="value">${{d.hermes_tasks}}</div></div>
      <div class="stat"><div class="label">Cron Jobs</div><div class="value">${{d.cron_jobs}}</div></div>
      <div class="stat"><div class="label">Agent 分身</div><div class="value">${{d.agent_count}}</div></div>
      <div class="stat"><div class="label">Worktree</div><div class="value">${{d.worktree_count}}</div></div>
      <div class="stat"><div class="label">Bookmark</div><div class="value">${{d.bookmark_count}}</div></div>
      <div class="stat"><div class="label">会话数</div><div class="value">${{d.session_count}}</div></div>
    </div>
    <p style="color:var(--text-2);margin-top:12px;font-size:12px;">
      工作目录: <code>${{d.cwd}}</code><br>
      时间戳: <code>${{new Date(d.timestamp * 1000).toLocaleString()}}</code>
    </p>
  `;
}}

function renderSessions(d) {{
  if (!d.length) return '<h2>💬 会话</h2><p class="loading">没有会话</p>';
  return `<h2>💬 会话 (${{d.length}})</h2>
    <table>
      <tr><th>索引</th><th>文件名</th><th>创建</th><th>更新</th><th>消息数</th></tr>
      ${{d.map(s => `
        <tr>
          <td>${{s.index}}</td>
          <td><a href="/api/sessions/${{s.index}}?token=${{TOKEN}}" target="_blank">${{s.filename}}</a></td>
          <td>${{s.created_at}}</td>
          <td>${{s.updated_at}}</td>
          <td>${{s.msg_count}}</td>
        </tr>
      `).join('')}}
    </table>`;
}}

function renderTasks(d) {{
  if (!d.length) return '<h2>⚙️ Hermes 任务</h2><p class="loading">没有任务</p>';
  return `<h2>⚙️ Hermes 任务 (${{d.length}})</h2>
    <pre>${{JSON.stringify(d.slice(0, 20), null, 2)}}</pre>`;
}}

function renderWorktrees(d) {{
  if (!d.length) return '<h2>🌳 Worktree</h2><p class="loading">没有 worktree</p>';
  return `<h2>🌳 Worktree (${{d.length}})</h2>
    <table>
      <tr><th>路径</th><th>分支</th><th>创建</th><th>最后使用</th></tr>
      ${{d.map(w => `
        <tr>
          <td><code>${{w.path}}</code></td>
          <td><code>${{w.branch || '(detached)'}}</code></td>
          <td>${{new Date(w.created_at * 1000).toLocaleString()}}</td>
          <td>${{new Date(w.last_used_at * 1000).toLocaleString()}}</td>
        </tr>
      `).join('')}}
    </table>`;
}}

function renderBookmarks(d) {{
  if (!d.length) return '<h2>📚 Bookmark</h2><p class="loading">没有书签</p>';
  return `<h2>📚 Bookmark (${{d.length}})</h2>
    <table>
      <tr><th>ID</th><th>标题</th><th>URL</th><th>标签</th><th>RAG</th></tr>
      ${{d.slice(0, 30).map(b => `
        <tr>
          <td><code>${{b.id}}</code></td>
          <td>${{b.title || '?'}}</td>
          <td><a href="${{b.url}}" target="_blank">${{b.url}}</a></td>
          <td>${{(b.tags || []).map(t => '#' + t).join(' ')}}</td>
          <td>${{b.in_rag ? '🧠' : ''}}</td>
        </tr>
      `).join('')}}
    </table>
    <p style="color:var(--text-2);font-size:12px;margin-top:8px;">显示前 30 个</p>`;
}}

function renderStats(d) {{
  return `
    <h2>📈 用量统计</h2>
    <div class="stat-grid">
      <div class="stat"><div class="label">总消息数</div><div class="value">${{d.total_messages}}</div></div>
      <div class="stat"><div class="label">总 Token</div><div class="value">${{d.total_tokens.toLocaleString()}}</div></div>
      <div class="stat"><div class="label">总费用 (元)</div><div class="value">${{d.total_cost.toFixed(4)}}</div></div>
    </div>
    <pre style="margin-top:12px;">${{JSON.stringify(d, null, 2)}}</pre>
  `;
}}

async function load(name) {{
  const content = document.getElementById('content');
  content.innerHTML = '<p class="loading">加载中...</p>';
  try {{
    const r = await fetchJSON('/api/' + name);
    if (!r.ok) throw new Error(r.error || '加载失败');
    const renderers = {{
      status: renderStatus,
      sessions: renderSessions,
      tasks: renderTasks,
      worktrees: renderWorktrees,
      bookmarks: renderBookmarks,
      stats: renderStats,
    }};
    content.innerHTML = renderers[name](r.data);
  }} catch (e) {{
    content.innerHTML = '<p style="color:var(--red)">错误: ' + e.message + '</p>';
  }}
}}

// v2.8+:SSE 实时事件订阅
let eventSource = null;
function startSSE() {{
  if (eventSource) return;
  eventSource = new EventSource('/api/events?token=' + TOKEN);
  eventSource.addEventListener('status', (e) => {{
    const data = JSON.parse(e.data);
    showEvent('📊 ' + (data.data.message || JSON.stringify(data.data)), data);
    // 自动刷新 status tab(如果当前在)
    const content = document.getElementById('content');
    if (content.dataset.active === 'status') load('status');
  }});
  eventSource.addEventListener('task', (e) => {{
    const data = JSON.parse(e.data);
    showEvent('⚙️ 任务: ' + (data.data.task_id || '?') + ' → ' + (data.data.status || '?'), data);
    const content = document.getElementById('content');
    if (content.dataset.active === 'tasks') load('tasks');
  }});
  eventSource.addEventListener('log', (e) => {{
    const data = JSON.parse(e.data);
    showEvent('📝 ' + (data.data.message || ''), data);
  }});
  eventSource.addEventListener('error', () => {{
    // 自动重连
    eventSource.close();
    eventSource = null;
    setTimeout(startSSE, 5000);
  }});
}}

function showEvent(text, data) {{
  const log = document.getElementById('event-log');
  if (!log) return;
  const ts = new Date(data.timestamp * 1000).toLocaleTimeString();
  const div = document.createElement('div');
  div.className = 'event-item';
  div.innerHTML = '<span style="color:var(--text-2);font-size:11px;">' + ts + '</span> ' +
                  '<span style="color:var(--accent);">[' + data.type + ']</span> ' +
                  '<span>' + text + '</span>';
  log.insertBefore(div, log.firstChild);
  while (log.children.length > 30) log.removeChild(log.lastChild);
}}
startSSE();

// 注册 service worker(PWA 离线)
if ('serviceWorker' in navigator) {{
  navigator.serviceWorker.register('/sw.js').catch(() => {{}});
}}
</script>
</body>
</html>"""


def start_console(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                  token: Optional[str] = None,
                  open_browser: bool = True) -> Dict[str, Any]:
    """启动 Web 控制台

    Args:
        host: 绑定地址(默认 127.0.0.1)
        port: 端口
        token: Bearer Token(默认随机生成)
        open_browser: 是否自动打开浏览器

    Returns:
        {"ok": bool, "url": str, "token": str, "pid": int, "error": str?}
    """
    global _console_state

    if _console_state["running"]:
        return {
            "ok": False,
            "error": f"控制台已在运行: http://{_console_state['host']}:{_console_state['port']}",
        }

    token = token or _generate_token()
    handler_cls = _make_handler(token)

    try:
        server = ThreadingHTTPServer((host, port), handler_cls)
    except OSError as e:
        return {"ok": False, "error": f"无法绑定 {host}:{port}: {e}"}

    thread = threading.Thread(target=server.serve_forever, daemon=True, name="fr-cli-console")
    thread.start()

    _console_state.update({
        "server": server,
        "thread": thread,
        "token": token,
        "host": host,
        "port": port,
        "running": True,
    })

    url = f"http://{host}:{port}"

    # 自动打开浏览器
    if open_browser:
        try:
            import subprocess
            import platform
            if platform.system() == "Darwin":
                subprocess.Popen(["open", url])
            elif platform.system() == "Linux":
                subprocess.Popen(["xdg-open", url])
            elif platform.system() == "Windows":
                os.startfile(url)  # type: ignore
        except Exception:
            pass

    return {
        "ok": True,
        "url": url,
        "url_with_token": f"{url}/?token={token}",
        "token": token,
        "host": host,
        "port": port,
    }


def stop_console() -> Dict[str, Any]:
    """停止 Web 控制台"""
    global _console_state
    if not _console_state["running"]:
        return {"ok": False, "error": "控制台未运行"}

    try:
        _console_state["server"].shutdown()
        _console_state["server"].server_close()
    except Exception:
        pass

    _console_state.update({
        "server": None,
        "thread": None,
        "running": False,
    })
    return {"ok": True}


def console_status() -> Dict[str, Any]:
    """获取控制台状态"""
    return {
        "running": _console_state["running"],
        "host": _console_state["host"],
        "port": _console_state["port"],
        "url": f"http://{_console_state['host']}:{_console_state['port']}" if _console_state["running"] else None,
        "token": _console_state["token"] if _console_state["running"] else None,
    }
