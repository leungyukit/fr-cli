"""
Web Console HTML 模板

首页 HTML(包含导航 + token 提示 + PWA + 事件订阅)拆到独立文件。
render_homepage(token) 返回完整 HTML 字符串。
"""
def render_homepage(token: str) -> str:
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
const _EVENT_ICONS = {{
  tool: '🛠️', llm: '🧠', agent: '🤖', command: '⌨️',
  session: '💬', app: '🚀', config: '⚙️', error: '❌',
  usage: '📊', status: '📊', task: '⚙️', log: '📝',
}};
function startSSE() {{
  if (eventSource) return;
  eventSource = new EventSource('/api/events?token=' + TOKEN);
  // 通用 channel 监听器:v3 EventBus 桥接过来的所有事件
  ['tool', 'llm', 'agent', 'command', 'session', 'app', 'config', 'error', 'usage'].forEach(ch => {{
    eventSource.addEventListener(ch, (e) => {{
      const data = JSON.parse(e.data);
      const sub = data.data._sub || '';
      const src = data.data._source || '';
      const icon = _EVENT_ICONS[ch] || '•';
      const detail = Object.entries(data.data)
        .filter(([k, _]) => !k.startsWith('_'))
        .map(([k, v]) => k + '=' + (typeof v === 'string' && v.length > 30 ? v.slice(0, 27) + '...' : v))
        .join(' ');
      showEvent(icon + ' ' + (sub ? ch + '.' + sub : ch) + (src ? ' (' + src + ')' : '') + ': ' + detail, data);
    }});
  }});
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
