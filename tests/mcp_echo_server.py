#!/usr/bin/env python3
"""用于测试的简单 MCP stdio 服务器：提供一个 echo 工具"""
import asyncio
import json
import sys


async def main():
    # 简化的 JSON-RPC 处理：只响应 initialize 和 tools/call
    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            break
        try:
            msg = json.loads(line)
        except Exception:
            continue
        msg_id = msg.get("id")
        method = msg.get("method")
        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "echo", "version": "1.0"},
                },
            }
        elif method == "initialized":
            continue
        elif method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "Echo input",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"message": {"type": "string"}},
                                "required": ["message"],
                            },
                        }
                    ]
                },
            }
        elif method == "tools/call":
            params = msg.get("params", {})
            args = params.get("arguments", {})
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"echo: {args.get('message', '')}"}]
                },
            }
        else:
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(main())
