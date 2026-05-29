"""百度文心一言适配器"""

from __future__ import annotations
from typing import AsyncIterator
import httpx
from .base import BaseLLMAdapter, LLMMessage, LLMResponse


class WenxinAdapter(BaseLLMAdapter):
    """文心一言API适配器（百度千帆平台）"""

    def __init__(self, api_key: str, model_name: str, base_url: str | None = None, secret_key: str = ""):
        super().__init__(api_key, model_name, base_url)
        self.secret_key = secret_key
        self._base_url = (base_url or "https://aip.baidubce.com").rstrip("/")
        self._access_token: str | None = None

    @property
    def platform_name(self) -> str:
        return "wenxin"

    async def _get_access_token(self, force_refresh: bool = False) -> str:
        """获取百度OAuth access_token"""
        if self._access_token and not force_refresh:
            return self._access_token
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/oauth/2.0/token",
                params={
                    "grant_type": "client_credentials",
                    "client_id": self.api_key,
                    "client_secret": self.secret_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data.get("access_token", "")
            return self._access_token

    def _model_endpoint(self) -> str:
        """模型到API endpoint的映射"""
        endpoints = {
            "ernie-4.0-turbo": "completions_pro",
            "ernie-4.0": "completions_pro",
            "ernie-3.5": "completions",
            "ernie-bot": "completions",
            "ernie-speed": "ernie_speed",
        }
        model_key = self.model_name.split("/")[-1] if "/" in self.model_name else self.model_name
        for key, ep in endpoints.items():
            if key in model_key:
                return ep
        return "completions"

    async def _request(self, messages: list[LLMMessage], temperature: float, stream: bool, max_tokens: int = 4096, _retry_token: bool = True) -> dict:
        token = await self._get_access_token()
        endpoint = self._model_endpoint()
        url = f"{self._base_url}/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/{endpoint}?access_token={token}"

        payload = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": stream,
            "max_output_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 401 and _retry_token:
                token = await self._get_access_token(force_refresh=True)
                url = f"{self._base_url}/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/{endpoint}?access_token={token}"
                resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        data = await self._request(messages, temperature, stream=False, max_tokens=max_tokens)
        return LLMResponse(
            content=data.get("result", ""),
            model=self.model_name,
            usage=data.get("usage"),
            finish_reason="stop" if data.get("is_end", True) else None,
        )

    async def stream_chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncIterator[str]:
        token = await self._get_access_token()
        endpoint = self._model_endpoint()
        url = f"{self._base_url}/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/{endpoint}?access_token={token}"

        payload = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": True,
            "max_output_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.send(client.build_request("POST", url, json=payload), stream=True)
            if resp.status_code == 401:
                token = await self._get_access_token(force_refresh=True)
                url = f"{self._base_url}/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/{endpoint}?access_token={token}"
                resp = await client.send(client.build_request("POST", url, json=payload), stream=True)
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    import json
                    try:
                        chunk = json.loads(data_str)
                        if "result" in chunk and chunk["result"]:
                            yield chunk["result"]
                    except json.JSONDecodeError:
                        continue

    async def is_available(self) -> bool:
        try:
            await self._get_access_token()
            return bool(self._access_token)
        except Exception:
            return False
