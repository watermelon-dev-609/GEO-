"""Anthropic Claude适配器"""

from __future__ import annotations
from typing import AsyncIterator
import httpx
from .base import BaseLLMAdapter, LLMMessage, LLMResponse


class ClaudeAdapter(BaseLLMAdapter):
    """Claude API适配器"""

    def __init__(self, api_key: str, model_name: str, base_url: str | None = None):
        super().__init__(api_key, model_name, base_url)
        self._base_url = (base_url or "https://api.anthropic.com").rstrip("/")
        self._api_version = "2023-06-01"

    @property
    def platform_name(self) -> str:
        return "claude"

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self._api_version,
            "content-type": "application/json",
        }

    def _build_payload(self, messages: list[LLMMessage], temperature: float, max_tokens: int, stream: bool, **kwargs) -> dict:
        system_msgs = [m for m in messages if m.role == "system"]
        conversation = [m for m in messages if m.role != "system"]

        payload = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in conversation],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            **kwargs,
        }
        if system_msgs:
            payload["system"] = "\n".join(m.content for m in system_msgs)
        return payload

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        payload = self._build_payload(messages, temperature, max_tokens, stream=False, **kwargs)
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._base_url}/v1/messages",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            content_blocks = data.get("content", [])
            text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
            return LLMResponse(
                content=text,
                model=data.get("model", self.model_name),
                usage=data.get("usage"),
                finish_reason=data.get("stop_reason"),
            )

    async def stream_chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncIterator[str]:
        payload = self._build_payload(messages, temperature, max_tokens, stream=True, **kwargs)
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/v1/messages",
                json=payload,
                headers=self._headers(),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        import json
                        try:
                            event = json.loads(data_str)
                            if event.get("type") == "content_block_delta":
                                delta = event.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")
                        except json.JSONDecodeError:
                            continue

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self._base_url}/v1/models",
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False
