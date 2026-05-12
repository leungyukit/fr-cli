#!/usr/bin/env python3
"""
Hermes 守护进程 - 后台服务接收终端命令
用法: /hermes start
"""

import os
import sys
import json
import time
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HermesDaemon:
    """Hermes 守护进程 - 后台服务"""

    def __init__(self, port=8765, host="127.0.0.1"):
        self.port = port
        self.host = host
        self.tasks = []
        self.skills = []
        self.goals = []
        self.analytics = {"requests": 0, "tokens": 0, "cost": 0.0}
        self.running = True

    def start(self):
        """启动守护进程"""
        server = HTTPServer((self.host, self.port), HermesHandler)
        server.daemon = self
        print(f"🧚 Hermes 守护进程已启动: http://{self.host}:{self.port}")
        print("📡 监听命令中...")

        while self.running:
            try:
                server.handle_request()
            except Exception:
                pass


class HermesHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器"""

    def log_message(self, format, *args):
        pass

    def send_json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def do_GET(self):
        daemon = self.server.daemon

        if self.path == "/health":
            self.send_json(200, {"status": "ok", "daemon": "hermes", "version": "2.3.2"})
        elif self.path == "/info":
            self.send_json(200, {
                "daemon": "hermes",
                "version": "2.3.2",
                "tasks": len(daemon.tasks),
                "skills": len(daemon.skills),
                "goals": len(daemon.goals),
                "analytics": daemon.analytics
            })
        elif self.path == "/tasks":
            self.send_json(200, {"tasks": daemon.tasks})
        elif self.path == "/skills":
            self.send_json(200, {"skills": daemon.skills})
        elif self.path == "/goals":
            self.send_json(200, {"goals": daemon.goals})
        elif self.path == "/analytics":
            self.send_json(200, daemon.analytics)
        elif self.path == "/capabilities":
            self.send_json(200, {
                "endpoints": [
                    {"method": "GET", "path": "/health", "desc": "健康检查"},
                    {"method": "GET", "path": "/info", "desc": "守护进程信息"},
                    {"method": "GET", "path": "/tasks", "desc": "任务列表"},
                    {"method": "POST", "path": "/task", "desc": "添加任务", "body": {"task": "任务描述"}},
                    {"method": "GET", "path": "/skills", "desc": "技能列表"},
                    {"method": "POST", "path": "/skill", "desc": "添加技能", "body": {"name": "名称", "content": "内容"}},
                    {"method": "GET", "path": "/goals", "desc": "目标列表"},
                    {"method": "POST", "path": "/goal", "desc": "设置目标", "body": {"description": "目标", "milestones": ["阶段1", "阶段2"]}},
                    {"method": "PUT", "path": "/goal/progress", "desc": "更新进度", "body": {"id": "目标ID", "progress": 0.5}},
                    {"method": "GET", "path": "/analytics", "desc": "使用统计"},
                    {"method": "POST", "path": "/execute", "desc": "执行命令", "body": {"command": "ls -la"}},
                    {"method": "POST", "path": "/chat", "desc": "AI 对话", "body": {"message": "你好"}},
                ]
            })
        else:
            self.send_json(404, {"error": "Not Found", "hint": "访问 /capabilities 查看所有端点"})

    def do_POST(self):
        daemon = self.server.daemon
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length > 0 else "{}"
        data = json.loads(body) if body else {}

        if self.path == "/task":
            task_id = f"task-{int(time.time())}"
            daemon.tasks.append({
                "id": task_id,
                "task": data.get("task", ""),
                "status": "pending",
                "created_at": time.strftime("%Y-%m-%d %H:%M")
            })
            self.send_json(200, {"id": task_id, "status": "queued"})

        elif self.path == "/skill":
            skill_id = f"skill-{int(time.time())}"
            daemon.skills.append({
                "id": skill_id,
                "name": data.get("name", ""),
                "content": data.get("content", ""),
                "tags": data.get("tags", []),
                "created_at": time.strftime("%Y-%m-%d %H:%M")
            })
            self.send_json(200, {"id": skill_id, "status": "added"})

        elif self.path == "/goal":
            goal_id = f"goal-{int(time.time())}"
            daemon.goals.append({
                "id": goal_id,
                "description": data.get("description", ""),
                "milestones": data.get("milestones", []),
                "progress": 0,
                "status": "active",
                "created_at": time.strftime("%Y-%m-%d %H:%M")
            })
            self.send_json(200, {"id": goal_id, "status": "created"})

        elif self.path == "/execute":
            cmd = data.get("command", "")
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                self.send_json(200, {
                    "output": result.stdout,
                    "error": result.stderr,
                    "returncode": result.returncode,
                    "duration": f"{result.returncode}s"
                })
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif self.path == "/chat":
            message = data.get("message", "")
            daemon.analytics["requests"] += 1
            self.send_json(200, {
                "reply": f"[Hermes] 收到消息: {message[:50]}...",
                "task_id": f"task-{int(time.time())}",
                "model": "hermes-ai"
            })

        elif self.path == "/analytics":
            daemon.analytics["requests"] += data.get("requests", 0)
            daemon.analytics["tokens"] += data.get("tokens", 0)
            daemon.analytics["cost"] += data.get("cost", 0.0)
            self.send_json(200, {"status": "recorded", "analytics": daemon.analytics})

        else:
            self.send_json(404, {"error": "Not Found"})

    def do_PUT(self):
        daemon = self.server.daemon
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length > 0 else "{}"
        data = json.loads(body) if body else {}

        if self.path == "/goal/progress":
            goal_id = data.get("id")
            for goal in daemon.goals:
                if goal.get("id") == goal_id:
                    goal["progress"] = data.get("progress", 0)
                    goal["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
                    self.send_json(200, {"status": "updated", "goal": goal})
                    return
            self.send_json(404, {"error": "Goal not found"})
        else:
            self.send_json(404, {"error": "Not Found"})


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Hermes 守护进程")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    daemon = HermesDaemon(port=args.port, host=args.host)
    try:
        daemon.start()
    except KeyboardInterrupt:
        daemon.stop()


if __name__ == "__main__":
    main()
