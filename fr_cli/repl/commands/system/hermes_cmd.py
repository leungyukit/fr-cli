"""
Hermes 守护进程命令：/hermes start/stop/status/task/goal/confirm/list/log/cancel/review
"""
from fr_cli.ui.ui import CYAN, RED, YELLOW, GREEN, DIM, RESET


def _cmd_hermes_daemon(state, parts):
    """Hermes 守护进程命令

    用法:
      /hermes start [port]                  启动独立 HTTP 守护进程（子进程）
      /hermes stop                          停止守护进程
      /hermes status                        查看引擎状态
      /hermes task [--autonomous|-a] <描述>  创建后台任务（默认 sandbox 模式）
      /hermes goal [--autonomous|-a] [--tags tag1,tag2] <描述>  创建目标并自动分解为步骤
      /hermes confirm <id>                  确认 autonomous 任务
      /hermes list [status]                 列任务（status: pending/running/completed/failed/paused）
      /hermes log <id>                      查看任务结果/错误
      /hermes cancel <id>                   暂停任务
      /hermes review                        查看后台产物审核队列
      /hermes review approve <id> [name]    批准并安装队列中的产物
      /hermes review reject <id>            拒绝队列中的产物
    """
    arg1 = parts[1] if len(parts) > 1 else ""

    from fr_cli.agent.hermes_manager import HermesManager
    manager = HermesManager()

    if arg1 == "start":
        port = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 8765
        result = manager.start(port=port, lang=state.lang)
        color = GREEN if result.is_ok() else RED
        print(f"{color}{result.unwrap_or(result.error)}{RESET}")
        if result.is_ok():
            print(f"{DIM}  监听地址: http://127.0.0.1:{port}{RESET}")

    elif arg1 == "stop":
        result = manager.stop()
        color = GREEN if result.is_ok() else YELLOW
        print(f"{color}{result.unwrap_or(result.error)}{RESET}")

    elif arg1 == "status":
        print(f"{CYAN}{manager.status()}{RESET}")
        print(f"{CYAN}{state.hermes.status_report()}{RESET}")

    elif arg1 == "task":
        # 解析 --autonomous / -a 标志
        execution_mode = "sandbox"
        desc_parts = parts[2:]
        if desc_parts and desc_parts[0] in ("--autonomous", "-a"):
            execution_mode = "autonomous"
            desc_parts = desc_parts[1:]
        description = " ".join(desc_parts)
        if not description:
            print(f"{YELLOW}用法: /hermes task [--autonomous|-a] <描述>{RESET}")
            return False
        task = state.hermes.create_task(description, source="repl", execution_mode=execution_mode)
        if task.execution_mode == "autonomous" and task.user_confirmed_at:
            print(f"{GREEN}✅ autonomous 任务已创建并授权: {task.id} [{task.status.value}]{RESET}")
        elif task.execution_mode == "autonomous":
            print(f"{YELLOW}⏸️  autonomous 任务已创建但未授权: {task.id} [{task.status.value}]{RESET}")
            print(f"{DIM}      执行 /hermes confirm {task.id} 授权后才会以 full_auto 运行{RESET}")
        else:
            print(f"{GREEN}✅ 任务已创建: {task.id} [{task.status.value}]{RESET}")

    elif arg1 == "goal":
        # 解析 --autonomous / -a 和 --tags 标志
        execution_mode = "sandbox"
        tags = []
        desc_parts = parts[2:]
        while desc_parts:
            if desc_parts[0] in ("--autonomous", "-a"):
                execution_mode = "autonomous"
                desc_parts = desc_parts[1:]
            elif desc_parts[0] == "--tags" and len(desc_parts) > 1:
                tags = [t.strip() for t in desc_parts[1].split(",") if t.strip()]
                desc_parts = desc_parts[2:]
            else:
                break
        description = " ".join(desc_parts)
        if not description:
            print(f"{YELLOW}用法: /hermes goal [--autonomous|-a] [--tags tag1,tag2] <描述>{RESET}")
            return False
        goal = state.hermes.decompose_goal(description, execution_mode=execution_mode, context_tags=tags)
        if goal is None:
            print(f"{RED}目标分解失败{RESET}")
            return False
        print(f"{GREEN}✅ 目标已创建: {goal.id}{RESET}")
        print(f"{CYAN}步骤:{RESET}")
        for i, cid in enumerate(goal.children_ids, 1):
            child = state.hermes.get_task(cid)
            if child:
                print(f"  {i}. {child.description}")

    elif arg1 == "confirm":
        task_id = parts[2] if len(parts) > 2 else ""
        if not task_id:
            print(f"{YELLOW}用法: /hermes confirm <id>{RESET}")
            return False
        if state.hermes.confirm_task(task_id):
            print(f"{GREEN}✅ 任务已授权: {task_id}{RESET}")
        else:
            print(f"{RED}未找到任务或该任务不是 autonomous 模式: {task_id}{RESET}")

    elif arg1 == "list":
        status_filter = parts[2] if len(parts) > 2 else None
        tasks = state.hermes.list_tasks(status=status_filter)
        if not tasks:
            print(f"{DIM}暂无任务{RESET}")
            return False
        print(f"{CYAN}任务列表 ({len(tasks)} 个):{RESET}")
        for t in tasks:
            flag = {
                "pending": "⏳", "running": "🏃", "completed": "✅",
                "failed": "❌", "paused": "⏸️"
            }.get(t.status.value, "❓")
            mode_flag = "🤖" if t.execution_mode == "autonomous" else ""
            confirm_flag = "✓" if (t.execution_mode == "autonomous" and t.user_confirmed_at) else ""
            print(f"  {flag} {mode_flag}{confirm_flag} {t.id} [{t.priority.name}] [{t.status.value}] {t.description[:50]}")

    elif arg1 == "log":
        task_id = parts[2] if len(parts) > 2 else ""
        if not task_id:
            print(f"{YELLOW}用法: /hermes log <id>{RESET}")
            return False
        task = state.hermes.get_task(task_id)
        if not task:
            print(f"{RED}未找到任务: {task_id}{RESET}")
            return False
        print(f"{CYAN}任务: {task.id}{RESET}")
        print(f"  状态: {task.status.value}")
        print(f"  优先级: {task.priority.name}")
        print(f"  模式: {task.execution_mode}")
        if task.execution_mode == "autonomous":
            confirmed = "是" if task.user_confirmed_at else "否"
            print(f"  已授权: {confirmed}")
        print(f"  描述: {task.description}")
        if task.result:
            print(f"  结果:\n{DIM}{task.result}{RESET}")
        if task.error:
            print(f"  错误:\n{RED}{task.error}{RESET}")

    elif arg1 == "cancel":
        task_id = parts[2] if len(parts) > 2 else ""
        if not task_id:
            print(f"{YELLOW}用法: /hermes cancel <id>{RESET}")
            return False
        if state.hermes.cancel_task(task_id):
            print(f"{GREEN}✅ 任务已暂停: {task_id}{RESET}")
        else:
            print(f"{RED}未找到任务: {task_id}{RESET}")

    elif arg1 == "review":
        from fr_cli.agent.review_queue import PersistentReviewQueue
        queue = PersistentReviewQueue()
        sub = parts[2] if len(parts) > 2 else ""
        if sub == "approve":
            item_id = parts[3] if len(parts) > 3 else ""
            final_name = parts[4] if len(parts) > 4 else None
            if not item_id:
                print(f"{YELLOW}用法: /hermes review approve <id> [name]{RESET}")
                return False
            item = queue.approve(item_id, final_name=final_name)
            if item is None:
                print(f"{RED}未找到审核项: {item_id}{RESET}")
                return False
            # 立即安装
            from fr_cli.agent.artifact_detector import install_plugin, install_agent
            if item.artifact_type == "plugin":
                ok, msg = install_plugin(item.suggested_name or final_name or "auto_plugin", item.code, state)
            elif item.artifact_type == "agent":
                ok, msg = install_agent(item.suggested_name or final_name or "auto_agent", item.code, state)
            else:
                ok, msg = False, f"未知产物类型: {item.artifact_type}"
            if ok:
                print(f"{GREEN}✅ 已批准并安装: {item_id} ({item.artifact_type}){RESET}")
            else:
                print(f"{RED}批准成功但安装失败: {msg}{RESET}")
        elif sub == "reject":
            item_id = parts[3] if len(parts) > 3 else ""
            if not item_id:
                print(f"{YELLOW}用法: /hermes review reject <id>{RESET}")
                return False
            if queue.reject(item_id):
                print(f"{GREEN}✅ 已拒绝: {item_id}{RESET}")
            else:
                print(f"{RED}未找到审核项: {item_id}{RESET}")
        else:
            items = queue.list(status="pending")
            counts = queue.counts()
            print(f"{CYAN}审核队列 ({counts['pending']} pending / {counts['total']} total):{RESET}")
            if not items:
                print(f"{DIM}  暂无待审核产物{RESET}")
            for item in items:
                task_info = f" (task: {item.task_id})" if item.task_id else ""
                print(f"  {YELLOW}{item.id}{RESET} [{item.artifact_type}]{task_info}")
                print(f"    {DIM}建议名: {item.suggested_name or '-'}{RESET}")

    else:
        print(f"{DIM}用法:{RESET}")
        print("  /hermes start [port]                  启动独立 HTTP 守护进程（子进程）")
        print("  /hermes stop                          停止守护进程")
        print("  /hermes status                        查看引擎状态")
        print("  /hermes task [--autonomous|-a] <描述>  创建后台任务")
        print("  /hermes goal [--autonomous|-a] [--tags tag1,tag2] <描述>  创建目标并自动分解")
        print("  /hermes confirm <id>                  确认 autonomous 任务")
        print("  /hermes list [status]                 列任务")
        print("  /hermes log <id>                      查看任务详情")
        print("  /hermes cancel <id>                   暂停任务")
        print("  /hermes review                        查看后台产物审核队列")
        print("  /hermes review approve <id> [name]    批准并安装队列中的产物")
        print("  /hermes review reject <id>            拒绝队列中的产物")
    return False