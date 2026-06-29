"""百度文心一言客户端(HTTP + Access Token)"""
import json
from typing import Iterator

from fr_cli.core.llm.base import BaseLLMClient


class WenxinLLMClient(BaseLLMClient):
    """百度文心一言客户端"""

    def __init__(self, api_key: str, secret_key: str = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.secret_key = secret_key or api_key
        self._access_token = None
        self._token_expires_at = 0

    def _get_access_token(self):
        """获取 Access Token(自动续期)"""
        import time
        if self._access_token and time.time() < self._token_expires_at - 300:
            return self._access_token

        import requests
        token_url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.secret_key,
        }
        response = requests.post(token_url, params=params, timeout=30)
        data = response.json()

        if "access_token" in data:
            self._access_token = data["access_token"]
            self._token_expires_at = time.time() + data.get("expires_in", 2592000)
            return self._access_token
        else:
            raise Exception(f"获取文心 Access Token 失败: {data}")

    def stream_chat(self, model: str, messages: list,
                    max_tokens: int = 4096, timeout: int = None) -> Iterator[dict]:
        """文心流式对话"""
        import requests

        access_token = self._get_access_token()
        url = (f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/"
               f"chat/completions?access_token={access_token}")

        headers = {"Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }

        response = requests.post(
            url, json=payload, headers=headers,
            stream=True, timeout=timeout or self.DEFAULT_TIMEOUT,
        )

        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data:'):
                    data_str = line[5:].strip()
                    if data_str and data_str != '[DONE]':
                        try:
                            data = json.loads(data_str)
                            content = ""
                            if 'choices' in data and len(data['choices']) > 0:
                                delta = data['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                            yield {"content": content, "usage": None}
                        except json.JSONDecodeError:
                            pass
