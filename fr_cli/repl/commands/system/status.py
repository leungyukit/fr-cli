"""
全局状态面板：/status [json|errors]
"""
import json

from fr_cli.ui.ui import CYAN, RED, YELLOW, GREEN, DIM, RESET


def _cmd_status(state, parts):
    """查看 fr-cli 全局状态面板

    用法:
      /status           人类可读面板
      /status json      输出 JSON
      /status errors    输出最近错误报告
    """
    fmt = parts[1].lower() if len(parts) > 1 else "text"
    summary = state.status_summary()

    if fmt == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return False

    errors = summary.get("errors", {})
    if fmt == "errors":
        print(json.dumps(errors, ensure_ascii=False, indent=2, default=str))
        return False

    # 文本面板
    print(f"{CYAN}📊 fr-cli 全局状态{RESET}")
    print(f"{DIM}{'━' * 40}{RESET}")

    key_ok = "✅" if summary.get("api_key_configured") else "❌"
    print(f"🤖 模型: {summary.get('provider')} / {summary.get('model')}")
    print(f"🔑 API Key: {key_ok}")
    print(f"🔐 自主模式: {summary.get('autonomous_mode')}")

    ma = summary.get("master_agent", {})
    ma_state = "已启用" if ma.get("enabled") else "未启用"
    print(f"🧠 MasterAgent: {ma_state} (interactions: {ma.get('total_interactions', 0)})")

    print()
    agent_srv = summary.get("agent_server", {})
    if agent_srv.get("running"):
        print(f"{GREEN}🌐 Agent HTTP 服务: 运行中{RESET}")
        print(f"   {DIM}{agent_srv.get('status')}{RESET}")
    else:
        print(f"{DIM}🌐 Agent HTTP 服务: 未运行{RESET}")

    hermes = summary.get("hermes_daemon", {})
    if hermes.get("running"):
        print(f"{GREEN}🧚 Hermes 守护进程: {hermes.get('status')}{RESET}")
    else:
        print(f"{DIM}🧚 Hermes 守护进程: {hermes.get('status')}{RESET}")

    # Hermes 任务统计
    tasks = summary.get("hermes_tasks", {})
    print(
        f"   任务: pending={tasks.get('pending', 0)} running={tasks.get('running', 0)} "
        f"completed={tasks.get('completed', 0)} failed={tasks.get('failed', 0)} paused={tasks.get('paused', 0)}"
    )

    gk = summary.get("gatekeeper", {})
    if gk.get("running"):
        print(f"{GREEN}🛡️ Gatekeeper: {gk.get('status')}{RESET}")
    else:
        print(f"{DIM}🛡️ Gatekeeper: {gk.get('status')}{RESET}")

    print()
    rq = summary.get("review_queue", {})
    print(f"📋 审核队列: {rq.get('pending', 0)} pending / {rq.get('total', 0)} total")
    print(f"⏰ 定时任务: {summary.get('cron_jobs', 0)} 个")
    print(f"📦 插件: {summary.get('plugins', 0)} | Agent 分身: {summary.get('agents', 0)}")

    rag = summary.get("rag_watcher", {})
    if rag.get("kb_dir"):
        rag_state = "运行中" if rag.get("running") else "未运行"
        print(f"📚 RAG 监控: {rag_state} ({rag.get('kb_dir')})")

    # 最近错误摘要
    failed_count = len(errors.get("hermes_failed_tasks", []))
    selftest_count = len(errors.get("dynamic_builder_selftest_failures", []))
    rejected_count = len(errors.get("review_queue_rejected", []))
    if failed_count or selftest_count or rejected_count:
        print()
        print(f"{YELLOW}⚠️ 最近错误: Hermes失败={failed_count} 自测回滚={selftest_count} 审核拒绝={rejected_count}{RESET}")
        print(f"   使用 {CYAN}/status errors{RESET} 查看详情")

    return False