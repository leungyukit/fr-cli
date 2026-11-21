#!/usr/bin/env python3
"""
Hermes 守护进程 - 后台 HTTP 服务接收任务
用法: /hermes start [port]

改造后职责：
- 所有任务/目标/统计都委托给 HermesEngine，不再自己维护内存状态。
- /execute 不再直接 subprocess，而是作为任务提交到引擎。
- /chat 不再硬编码回复，而是作为任务提交给 MasterAgent。

模块拆分(原单文件 449 行):
- hermes_api.py:     HTTP 请求处理器 HermesHandler + 序列化(约 320 行)
- hermes_daemon.py:  本文件——HermesDaemon(token/启停) + main() 入口

HermesHandler 与本类零静态耦合:处理器经 self.server.daemon
动态取 token / engine,因此拆开后无需循环导入。
"""

import os
import secrets
from http.server import HTTPServer

from fr_cli.conf.paths import DAEMON_TOKEN_FILE

from fr_cli.agent.hermes_api import (  # noqa: F401 (re-export,旧导入路径兼容)
    HermesHandler,
    _goal_to_json,
    _task_to_json,
)


class HermesDaemon:
    """Hermes 守护进程 - 后台 HTTP 服务"""

    def __init__(self, port=8765, host="127.0.0.1", engine=None):
        self.port = port
        self.host = host
        self.engine = engine
        self.running = True
        # 启动时生成 Bearer Token，持久化到 ~/.fr_cli/daemon/token
        self.token = self._load_or_create_token()

    @staticmethod
    def _load_or_create_token() -> str:
        token_file = DAEMON_TOKEN_FILE
        if os.path.exists(token_file):
            try:
                with open(token_file, "r") as f:
                    tok = f.read().strip()
                    if tok:
                        return tok
            except Exception:
                pass
        tok = secrets.token_urlsafe(24)
        try:
            os.makedirs(os.path.dirname(token_file), exist_ok=True)
            with open(token_file, "w") as f:
                f.write(tok)
            os.chmod(token_file, 0o600)
        except Exception:
            pass
        return tok

    def stop(self):
        self.running = False

    def start(self):
        """启动守护进程"""
        server = HTTPServer((self.host, self.port), HermesHandler)
        server.daemon = self
        print(f"Hermes 守护进程已启动: http://{self.host}:{self.port}")
        print(f"Bearer Token: {self.token}")
        print("   (已保存到 ~/.fr_cli/daemon/token，权限 600)")
        print("监听命令中...")

        while self.running:
            try:
                server.handle_request()
            except Exception:
                pass


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
