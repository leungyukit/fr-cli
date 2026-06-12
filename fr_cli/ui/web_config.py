"""
简易 Web 配置界面
启动命令: /config_server start [port]
提供浏览器-based 的配置管理，降低 CLI 配置门槛
"""
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>fr-cli 配置中心</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; background: #f5f5f5; }
.card { background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
h1 { color: #333; font-size: 24px; margin-bottom: 8px; }
h2 { color: #555; font-size: 18px; margin-top: 0; border-bottom: 1px solid #eee; padding-bottom: 12px; }
label { display: block; margin: 16px 0 6px; color: #666; font-size: 14px; font-weight: 500; }
input, select { width: 100%; padding: 10px 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; box-sizing: border-box; }
input:focus, select:focus { outline: none; border-color: #4a90d9; }
button { background: #4a90d9; color: white; border: none; padding: 12px 24px; border-radius: 8px; font-size: 14px; cursor: pointer; margin-top: 16px; }
button:hover { background: #357abd; }
.success { color: #2e7d32; background: #e8f5e9; padding: 12px; border-radius: 8px; margin-top: 12px; }
.error { color: #c62828; background: #ffebee; padding: 12px; border-radius: 8px; margin-top: 12px; }
.hint { color: #999; font-size: 12px; margin-top: 4px; }
</style>
</head>
<body>
<div class="card">
<h1>🔧 fr-cli 配置中心</h1>
<p style="color:#666;">在浏览器中管理你的 fr-cli 配置</p>
</div>

<div class="card">
<h2>🤖 AI 模型配置</h2>
<form id="configForm">
  <label>当前提供商</label>
  <select name="provider" id="provider">
    <!-- 选项由 /api/providers 动态填充 -->
  </select>

  <label>API Key</label>
  <input type="password" name="key" id="key" placeholder="输入你的 API Key">
  <div class="hint">密钥仅存储在本地，不会上传到任何服务器</div>

  <label>Token 上限</label>
  <input type="number" name="limit" id="limit" value="20000" min="1000">

  <label>界面语言</label>
  <select name="lang" id="lang">
    <option value="zh">中文</option>
    <option value="en">English</option>
  </select>

  <button type="submit">💾 保存配置</button>
  <div id="result"></div>
</form>
</div>

<div class="card">
<h2>📂 工作目录</h2>
<label>允许访问的目录</label>
<input type="text" id="workdir" placeholder="/path/to/your/project">
<button onclick="addDir()">➕ 添加目录</button>
<div id="dirs"></div>
</div>

<script>
async function loadProviders() {
  try {
    const res = await fetch('/api/providers');
    const providers = await res.json();
    const select = document.getElementById('provider');
    select.innerHTML = providers.map(p => `<option value="${p.id}">${p.name}</option>`).join('');
  } catch(e) { console.error(e); }
}

async function loadConfig() {
  try {
    await loadProviders();
    const res = await fetch('/api/config');
    const cfg = await res.json();
    if (cfg.provider) document.getElementById('provider').value = cfg.provider;
    if (cfg.key) document.getElementById('key').value = cfg.key;
    if (cfg.limit) document.getElementById('limit').value = cfg.limit;
    if (cfg.lang) document.getElementById('lang').value = cfg.lang;
    if (cfg.allowed_dirs) {
      document.getElementById('dirs').innerHTML = cfg.allowed_dirs.map(d => `<div style="margin-top:8px;padding:8px;background:#f5f5f5;border-radius:6px;">${d}</div>`).join('');
    }
  } catch(e) { console.error(e); }
}

document.getElementById('configForm').onsubmit = async function(e) {
  e.preventDefault();
  const data = {
    provider: document.getElementById('provider').value,
    key: document.getElementById('key').value,
    limit: parseInt(document.getElementById('limit').value),
    lang: document.getElementById('lang').value,
  };
  try {
    const res = await fetch('/api/config', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) });
    const result = await res.json();
    document.getElementById('result').className = result.ok ? 'success' : 'error';
    document.getElementById('result').textContent = result.message;
  } catch(e) {
    document.getElementById('result').className = 'error';
    document.getElementById('result').textContent = '保存失败: ' + e.message;
  }
};

async function addDir() {
  const dir = document.getElementById('workdir').value;
  if (!dir) return;
  try {
    const res = await fetch('/api/dir', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({dir}) });
    const result = await res.json();
    loadConfig();
    document.getElementById('workdir').value = '';
  } catch(e) { alert(e.message); }
}

loadConfig();
</script>
</body>
</html>
"""

class ConfigHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        elif self.path == '/api/config':
            self._send_json(self._load_config())
        elif self.path == '/api/providers':
            self._send_json(self._list_providers())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/api/config':
            content_len = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_len).decode('utf-8')
            data = json.loads(body)
            self._save_config(data)
            self._send_json({"ok": True, "message": "配置已保存"})
        elif self.path == '/api/dir':
            content_len = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_len).decode('utf-8')
            data = json.loads(body)
            self._add_dir(data.get('dir', ''))
            self._send_json({"ok": True, "message": "目录已添加"})
        else:
            self.send_error(404)

    def _load_config(self):
        from fr_cli.conf.config import load_config
        cfg = load_config()
        safe_cfg = {
            "provider": cfg.get("provider", ""),
            "limit": cfg.get("limit", 20000),
            "lang": cfg.get("lang", "zh"),
            "allowed_dirs": cfg.get("allowed_dirs", []),
        }
        key = cfg.get("key", "")
        if key:
            safe_cfg["key"] = key[:8] + "****"
        return safe_cfg

    def _list_providers(self):
        from fr_cli.core.llm import list_providers
        try:
            return list_providers()
        except Exception:
            return []

    def _save_config(self, data):
        from fr_cli.conf.config import load_config, save_config
        cfg = load_config()
        for k in ["provider", "key", "limit", "lang"]:
            if k in data:
                cfg[k] = data[k]
        save_config(cfg)

    def _add_dir(self, d):
        from fr_cli.conf.config import load_config, save_config
        cfg = load_config()
        dirs = cfg.get("allowed_dirs", [])
        if d not in dirs:
            dirs.append(d)
            cfg["allowed_dirs"] = dirs
            save_config(cfg)

    def _send_json(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))


class ConfigWebUIServer:
    """配置 Web UI 服务器"""

    def __init__(self, port=17891):
        self.port = port
        self.server = None
        self.thread = None
        self._running = False

    def start(self):
        try:
            self.server = HTTPServer(("127.0.0.1", self.port), ConfigHandler)
            self._running = True
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            return True, f"配置界面已启动: http://127.0.0.1:{self.port}"
        except Exception as e:
            return False, f"启动失败: {e}"

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server = None
        self._running = False
        return True, "已停止"

    def is_running(self):
        return self._running
