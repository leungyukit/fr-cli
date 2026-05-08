"""
ACP (Agent Client Protocol) 支持
参考 kimi-cli 实现的 ACP 集成
"""

import os
import json
import asyncio
import subprocess
from typing import Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum


class ACPMessageType(Enum):
    """ACP 消息类型"""
    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"
    STREAM = "stream"


@dataclass
class ACPMessage:
    """ACP 消息"""
    id: str
    type: ACPMessageType
    method: str
    params: Dict = None
    result: Any = None
    error: str = None


class ACPServer:
    """ACP 服务器 - 作为 Agent 服务端"""

    def __init__(self, name: str = "fr-cli"):
        self.name = name
        self.running = False
        self.port = 8765

    async def start(self, port: int = 8765):
        """启动 ACP 服务器"""
        self.port = port
        self.running = True
        
        try:
            import uvicorn
            from fastapi import FastAPI
            from fastapi.websockets import WebSocket
            
            app = FastAPI()

            @app.websocket("/acp")
            async def acp_endpoint(websocket: WebSocket):
                await websocket.accept()
                try:
                    while self.running:
                        data = await websocket.receive_text()
                        message = json.loads(data)
                        
                        # 处理 ACP 消息
                        response = await self.handle_message(message)
                        
                        if response:
                            await websocket.send_text(json.dumps(response))
                except Exception as e:
                    print(f"ACP 连接错误: {e}")

            config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
            server = uvicorn.Server(config)
            await server.serve()

        except ImportError:
            print("警告: 需要安装 uvicorn 和 fastapi 来启用 ACP 服务")
        except Exception as e:
            print(f"ACP 服务器错误: {e}")

    async def handle_message(self, message: Dict) -> Optional[Dict]:
        """处理 ACP 消息"""
        msg_type = message.get("type")
        
        if msg_type == "request":
            method = message.get("method")
            params = message.get("params", {})
            
            if method == "chat":
                result = await self.chat(params)
                return {"id": message.get("id"), "type": "response", "result": result}
            elif method == "tools":
                return {"id": message.get("id"), "type": "response", "result": self.get_tools()}
            
        return None

    async def chat(self, params: Dict) -> str:
        """处理聊天请求"""
        from fr_cli.core.core import ask
        message = params.get("message", "")
        try:
            result, _ = await asyncio.to_thread(ask, message)
            return result
        except:
            return "Error processing request"

    def get_tools(self) -> list:
        """获取可用工具列表"""
        return [
            {"name": "bash", "description": "Execute shell commands"},
            {"name": "read", "description": "Read file contents"},
            {"name": "write", "description": "Write file contents"},
            {"name": "search", "description": "Search files"}
        ]

    def stop(self):
        """停止 ACP 服务器"""
        self.running = False


class ACPClient:
    """ACP 客户端 - 连接其他 Agent"""

    def __init__(self, server_url: str):
        self.server_url = server_url
        self.ws = None

    async def connect(self):
        """连接到 ACP 服务器"""
        try:
            import websockets
            self.ws = await websockets.connect(f"{self.server_url}/acp")
            return True
        except Exception as e:
            print(f"ACP 连接失败: {e}")
            return False

    async def send_message(self, method: str, params: Dict = None) -> Optional[Dict]:
        """发送消息"""
        if not self.ws:
            return None

        message = {
            "id": str(asyncio.get_event_loop().time()),
            "type": "request",
            "method": method,
            "params": params or {}
        }

        await self.ws.send(json.dumps(message))
        response = await self.ws.recv()
        return json.loads(response)

    async def close(self):
        """关闭连接"""
        if self.ws:
            await self.ws.close()


def run_acp_mode():
    """运行 ACP 模式"""
    print("""
╔════════════════════════════════════════════════════╗
║         ACP (Agent Client Protocol) 模式           ║
╚════════════════════════════════════════════════════╝

fr-cli 将作为 ACP Agent 服务端运行，
可与 Zed, VS Code 等 ACP 兼容编辑器集成。

启动命令示例配置:

Zed: ~/.config/zed/settings.json
{
  "agent_servers": {
    "fr-cli": {
      "command": "fr",
      "args": ["acp"],
      "env": {}
    }
  }
}
""")
    server = ACPServer(name="fr-cli")
    asyncio.run(server.start())


# CLI 命令
def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "acp":
        run_acp_mode()
    else:
        print("使用: fr acp 启动 ACP 服务")


if __name__ == "__main__":
    main()