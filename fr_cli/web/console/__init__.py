"""
Web Console —— 浏览器查看 fr-cli 状态

模块拆分:
- fr_cli.web.console.api_queries:7 个数据查询函数
- fr_cli.web.console.events:SSE 推送 + v3 EventBus 桥接
- fr_cli.web.console.handler:HTTP handler 工厂
- fr_cli.web.console.templates:首页 HTML
- fr_cli.web.console.lifecycle:start/stop/status

公开 API(向后兼容):
- start_console / stop_console / console_status
- push_event / get_recent_events / attach_event_bus / detach_event_bus

Endpoints:
- GET /                       首页 HTML
- GET /api/status             全局状态
- GET /api/sessions           会话列表
- GET /api/sessions/<idx>     会话详情
- GET /api/tasks              Hermes 任务
- GET /api/worktrees          Worktree
- GET /api/bookmarks          Bookmark
- GET /api/stats              统计
- GET /api/health             健康检查
- GET /api/metrics            指标查询(json/prom/summary)
- GET /api/events             SSE 长连接(需鉴权)
- POST /api/event             客户端发事件(上传日志)

- 默认绑定 127.0.0.1(不暴露公网)
- Bearer Token 鉴权(随机生成,启动时打印一次)
- 后台 daemon thread,不影响 REPL
"""
from fr_cli.web.console.lifecycle import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    console_status,
    reset_for_testing,
    start_console,
    stop_console,
)
from fr_cli.web.console.events import (
    _console_event_handler,
    _sse_clients,
    _sse_history,
    _sse_history_max,
    _sse_lock,
    attach_event_bus,
    detach_event_bus,
    get_recent_events,
    push_event,
    reset_sse_state,
)
from fr_cli.web.console.api_queries import (
    get_bookmarks as _get_bookmarks,
    get_global_status as _get_global_status,
    get_hermes_tasks as _get_hermes_tasks,
    get_session_detail as _get_session_detail,
    get_sessions_list as _get_sessions_list,
    get_stats as _get_stats,
    get_worktrees as _get_worktrees,
)
from fr_cli.web.console.handler import (
    generate_token as _generate_token,
    make_handler as _make_handler,
)
from fr_cli.web.console.templates import (
    render_homepage as _render_homepage,
)
# 向后兼容:老的测试可能 mock JsonStore / FR_CLI_DIR 在 fr_cli.web.console 命名空间
from fr_cli.core.store import JsonStore  # noqa: F401
from fr_cli.conf.paths import ROOT as FR_CLI_DIR  # noqa: F401

__all__ = [
    # Lifecycle
    "start_console",
    "stop_console",
    "console_status",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "reset_for_testing",
    # Events / SSE
    "push_event",
    "get_recent_events",
    "attach_event_bus",
    "detach_event_bus",
    "reset_sse_state",
    # 内部 SSE 状态(向后兼容:测试和第三方代码可能直接访问)
    "_sse_history",
    "_sse_history_max",
    "_sse_clients",
    "_sse_lock",
    "_console_event_handler",
    # 向后兼容:老的私有 _get_* 名字
    "_get_global_status",
    "_get_sessions_list",
    "_get_session_detail",
    "_get_hermes_tasks",
    "_get_worktrees",
    "_get_bookmarks",
    "_get_stats",
    "_make_handler",
    "_generate_token",
    "_render_homepage",
]
