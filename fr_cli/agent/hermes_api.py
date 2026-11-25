"""
Hermes HTTP API —— 请求处理器与序列化

从 fr_cli.agent.hermes_daemon 拆出(原文件 449 行,其中约 320 行是 HTTP 路由)。
本文件包含:
- _task_to_json / _goal_to_json: 引擎对象 -> JSON dict
- HermesHandler: GET/POST/PUT 路由(经 self.server.daemon 动态访问
  HermesDaemon 的 token / engine,与守护进程本体零静态耦合)

HermesDaemon 与 main() 仍在 fr_cli.agent.hermes_daemon,本模块符号
经其 re-export 保持旧导入路径可用。

服务骨架(鉴权 / 响应包裹 / 异常处理)统一到 fr_cli.core.http_base:
- 响应形状保持扁平(flat 包裹策略),与历史完全一致
- 鉴权策略:默认所有方法都需要 Bearer Token;只读公开白名单
  (默认仅 /health)可通过 daemon.public_paths 配置
"""
from fr_cli import __version__
from fr_cli.core.http_base import (
    WRAP_FLAT,
    AuthPolicy,
    BaseHTTPHandler,
)

# 只读公开端点（免鉴权）—— 默认仅暴露健康检查
# 可通过 HermesDaemon.public_paths 覆盖（写入 daemon 实例属性即可）
HERMES_PUBLIC_PATHS = frozenset({"/health"})


def _task_to_json(task) -> dict:
    return {
        "id": task.id,
        "description": task.description,
        "status": task.status.value,
        "priority": task.priority.name,
        "created_at": task.created_at,
        "scheduled_at": task.scheduled_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "result": task.result,
        "error": task.error,
        "retries": task.retries,
        "max_retries": task.max_retries,
        "owner": task.owner,
        "task_type": task.task_type,
        "source": task.source,
        "execution_mode": task.execution_mode,
        "parent_id": task.parent_id,
        "dependencies": task.dependencies,
        "children_ids": task.children_ids,
        "chain_next": task.chain_next,
        "context_tags": task.context_tags,
    }


def _goal_to_json(goal) -> dict:
    return {
        "id": goal.id,
        "description": goal.description,
        "status": goal.status.value,
        "milestones": goal.milestones,
        "progress": goal.progress,
        "created_at": goal.created_at,
        "completed_at": goal.completed_at,
        "task_ids": goal.task_ids,
    }


class HermesHandler(BaseHTTPHandler):
    """HTTP 请求处理器 —— 扁平 JSON 响应"""

    # 响应包裹策略：保持历史的扁平 JSON
    wrap_mode = WRAP_FLAT
    json_content_type = "application/json"

    def send_json(self, status, data):
        """发送 JSON 响应（保留旧方法名，内部走统一发送逻辑）"""
        self._send_json(status, data)

    def auth_policy(self) -> AuthPolicy:
        """鉴权策略 —— token 从 daemon 动态读取（启动后仍可替换）

        - 默认**所有方法**（含 GET）都需要 Bearer Token
        - 只读公开白名单：默认仅 /health，可用 daemon.public_paths 覆盖
          （白名单只对 GET/HEAD/OPTIONS 生效，POST 到同一路径仍需鉴权）
        - daemon 未配置 token 时一律拒绝（deny_without_token）
        """
        daemon = getattr(self.server, "daemon", None)
        token = getattr(daemon, "token", "") or ""
        public_paths = getattr(daemon, "public_paths", None)
        if public_paths is None:
            public_paths = HERMES_PUBLIC_PATHS
        return AuthPolicy(
            token=token,
            protected_methods=None,  # 所有方法都要鉴权
            public_paths=set(public_paths),
            deny_without_token=True,
            missing_status=401,
            missing_message="Missing Authorization: Bearer <token>",
            invalid_status=403,
            invalid_message="Invalid token",
        )

    def _read_body(self) -> dict:
        """读取 JSON 请求体（解析失败返回空 dict）"""
        return self._read_json_body()

    def _engine(self):
        return getattr(self.server.daemon, "engine", None)

    def do_GET(self):
        # 统一鉴权：GET 不再无条件免鉴权（只读公开白名单除外）
        if not self._check_auth():
            return
        engine = self._engine()

        if self.path == "/health":
            self.send_json(200, {
                "status": "ok",
                "daemon": "hermes",
                "version": __version__,
                "engine_ready": engine is not None,
            })

        elif self.path == "/info":
            counts = engine.task_manager.counts() if engine else {}
            stats = engine.analytics.get_stats() if engine else {}
            self.send_json(200, {
                "daemon": "hermes",
                "version": __version__,
                "tasks": counts,
                "goals": len(engine.goal_tracker.list_goals()) if engine else 0,
                "analytics": stats,
            })

        elif self.path == "/tasks":
            if not engine:
                self.send_json(503, {"error": "Hermes engine not available"})
                return
            status = self.headers.get("X-Task-Status")
            limit = self.headers.get("X-Task-Limit")
            tasks = engine.list_tasks(status=status, limit=int(limit) if limit else None)
            self.send_json(200, {"tasks": [_task_to_json(t) for t in tasks]})

        elif self.path.startswith("/tasks/"):
            if not engine:
                self.send_json(503, {"error": "Hermes engine not available"})
                return
            task_id = self.path[len("/tasks/"):]
            task = engine.get_task(task_id)
            if task:
                self.send_json(200, {"task": _task_to_json(task)})
            else:
                self.send_json(404, {"error": "Task not found"})

        elif self.path == "/goals":
            if not engine:
                self.send_json(503, {"error": "Hermes engine not available"})
                return
            goals = engine.goal_tracker.list_goals()
            self.send_json(200, {"goals": [_goal_to_json(g) for g in goals]})

        elif self.path == "/analytics":
            if not engine:
                self.send_json(503, {"error": "Hermes engine not available"})
                return
            self.send_json(200, engine.analytics.get_stats())

        elif self.path == "/review":
            from fr_cli.agent.review_queue import PersistentReviewQueue
            queue = PersistentReviewQueue()
            status = self.headers.get("X-Review-Status")
            items = queue.list(status=status)
            self.send_json(200, {
                "items": [
                    {
                        "id": item.id,
                        "artifact_type": item.artifact_type,
                        "suggested_name": item.suggested_name,
                        "status": item.status,
                        "task_id": item.task_id,
                        "created_at": item.created_at,
                    }
                    for item in items
                ],
                "counts": queue.counts(),
            })

        elif self.path == "/capabilities":
            self.send_json(200, {
                "endpoints": [
                    {"method": "GET", "path": "/health", "desc": "健康检查"},
                    {"method": "GET", "path": "/info", "desc": "守护进程信息"},
                    {"method": "GET", "path": "/tasks", "desc": "任务列表"},
                    {"method": "GET", "path": "/tasks/<id>", "desc": "单个任务"},
                    {"method": "POST", "path": "/tasks/<id>/confirm", "desc": "确认 autonomous 任务"},
                    {"method": "POST", "path": "/task", "desc": "添加任务", "body": {"task": "任务描述", "priority": "normal", "execution_mode": "sandbox"}},
                    {"method": "GET", "path": "/goals", "desc": "目标列表"},
                    {"method": "POST", "path": "/goal", "desc": "设置目标", "body": {"description": "目标", "milestones": ["阶段1"]}},
                    {"method": "GET", "path": "/analytics", "desc": "使用统计"},
                    {"method": "POST", "path": "/execute", "desc": "执行命令（作为任务提交）", "body": {"command": "ls -la"}},
                    {"method": "POST", "path": "/chat", "desc": "AI 对话（作为任务提交）", "body": {"message": "你好"}},
                    {"method": "GET", "path": "/review", "desc": "审核队列列表"},
                    {"method": "POST", "path": "/review/<id>/approve", "desc": "批准并安装产物", "query": {"name": "可选最终名称"}},
                    {"method": "POST", "path": "/review/<id>/reject", "desc": "拒绝产物"},
                ]
            })
        else:
            self.send_json(404, {"error": "Not Found", "hint": "访问 /capabilities 查看所有端点"})

    def do_POST(self):
        if not self._check_auth():
            return
        engine = self._engine()
        if not engine:
            self.send_json(503, {"error": "Hermes engine not available"})
            return

        data = self._read_body()

        if self.path == "/task":
            description = data.get("task", "")
            if not description:
                self.send_json(400, {"error": "task is required"})
                return
            priority = data.get("priority", "normal")
            execution_mode = data.get("execution_mode", "sandbox")
            task = engine.create_task(
                description=description,
                priority=priority,
                task_type="adhoc",
                source="http",
                execution_mode=execution_mode,
            )
            needs_confirmation = (
                task.execution_mode == "autonomous" and task.user_confirmed_at is None
            )
            self.send_json(
                202,
                {
                    "id": task.id,
                    "status": task.status.value,
                    "needs_confirmation": needs_confirmation,
                },
            )

        elif self.path == "/goal":
            description = data.get("description", "")
            if not description:
                self.send_json(400, {"error": "description is required"})
                return
            if data.get("decompose"):
                execution_mode = data.get("execution_mode", "sandbox")
                tags = data.get("tags", [])
                goal_task = engine.decompose_goal(
                    description,
                    execution_mode=execution_mode,
                    context_tags=tags,
                )
                if goal_task is None:
                    self.send_json(500, {"error": "Goal decomposition failed"})
                    return
                steps = [
                    engine.get_task(cid).description
                    for cid in goal_task.children_ids
                    if engine.get_task(cid)
                ]
                self.send_json(
                    202,
                    {
                        "goal_id": goal_task.id,
                        "status": goal_task.status.value,
                        "steps": steps,
                    },
                )
                return
            milestones = data.get("milestones", [])
            goal = engine.create_goal(description, milestones)
            self.send_json(202, {"id": goal.id, "status": goal.status.value})

        elif self.path == "/execute":
            command = data.get("command", "").strip()
            if not command:
                self.send_json(400, {"error": "command is required"})
                return
            # 作为 command 类型任务提交，不再直接 subprocess
            execution_mode = data.get("execution_mode", "sandbox")
            task = engine.create_task(
                description=command,
                task_type="command",
                source="http",
                execution_mode=execution_mode,
            )
            needs_confirmation = (
                task.execution_mode == "autonomous" and task.user_confirmed_at is None
            )
            self.send_json(
                202,
                {
                    "id": task.id,
                    "status": task.status.value,
                    "needs_confirmation": needs_confirmation,
                    "note": "queued as Hermes task",
                },
            )

        elif self.path.startswith("/tasks/") and self.path.endswith("/confirm"):
            task_id = self.path[len("/tasks/") : -len("/confirm")].strip("/")
            if not task_id:
                self.send_json(404, {"error": "Task id required"})
                return
            ok = engine.confirm_task(task_id)
            self.send_json(200 if ok else 404, {"confirmed": ok})

        elif self.path == "/chat":
            message = data.get("message", "")
            if not message:
                self.send_json(400, {"error": "message is required"})
                return
            task = engine.create_task(
                description=message,
                task_type="chat",
                source="http",
                execution_mode=data.get("execution_mode", "sandbox"),
            )
            self.send_json(202, {"id": task.id, "status": task.status.value})

        elif self.path.startswith("/review/") and self.path.endswith("/approve"):
            item_id = self.path[len("/review/") : -len("/approve")].strip("/")
            if not item_id:
                self.send_json(404, {"error": "Review id required"})
                return
            from fr_cli.agent.review_queue import PersistentReviewQueue
            from fr_cli.agent.artifact_detector import install_plugin, install_agent
            queue = PersistentReviewQueue()
            item = queue.get(item_id)
            if item is None:
                self.send_json(404, {"error": "Review item not found"})
                return
            final_name = data.get("name") or item.suggested_name or None
            item = queue.approve(item_id, final_name=final_name)
            # 使用 HermesEngine 关联的 AppState 进行安装
            install_state = engine.state_provider() if engine else None
            if install_state is None:
                self.send_json(503, {"error": "AppState not available"})
                return
            if item.artifact_type == "plugin":
                name = final_name or item.suggested_name or "auto_plugin"
                ok, msg = install_plugin(name, item.code, install_state)
            elif item.artifact_type == "agent":
                name = final_name or item.suggested_name or "auto_agent"
                ok, msg = install_agent(name, item.code, install_state)
            else:
                ok, msg = False, f"未知产物类型: {item.artifact_type}"
            self.send_json(
                200 if ok else 500,
                {"approved": True, "installed": ok, "name": msg if ok else None, "error": None if ok else msg},
            )

        elif self.path.startswith("/review/") and self.path.endswith("/reject"):
            item_id = self.path[len("/review/") : -len("/reject")].strip("/")
            if not item_id:
                self.send_json(404, {"error": "Review id required"})
                return
            from fr_cli.agent.review_queue import PersistentReviewQueue
            queue = PersistentReviewQueue()
            item = queue.reject(item_id)
            self.send_json(200 if item else 404, {"rejected": item is not None})

        elif self.path == "/analytics":
            # 允许外部上报统计
            requests = data.get("requests", 0)
            tokens = data.get("tokens", 0)
            cost = data.get("cost", 0.0)
            if requests or tokens:
                # 这里只记录 tokens，model 未知时用 "external"
                engine.analytics.record_request("external", tokens, cost)
            self.send_json(200, {"status": "recorded", "analytics": engine.analytics.get_stats()})

        else:
            self.send_json(404, {"error": "Not Found"})

    def do_PUT(self):
        """保留旧端点兼容（skill/goal progress 相关）- 现在返回未实现"""
        if not self._check_auth():
            return
        self.send_json(501, {"error": "Not implemented in new Hermes engine"})
