"""OpenAI兼容协议适配器 — 覆盖GPT/DeepSeek/豆包/通义千问/元宝"""

from __future__ import annotations
from typing import AsyncIterator
import httpx
from .base import BaseLLMAdapter, LLMMessage, LLMResponse


class OpenAICompatAdapter(BaseLLMAdapter):
    """OpenAI协议兼容适配器（覆盖5个平台）"""

    def __init__(self, api_key: str, model_name: str, base_url: str | None = None):
        super().__init__(api_key, model_name, base_url)
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    @property
    def platform_name(self) -> str:
        return "openai_compat"

    def _build_payload(self, messages: list[LLMMessage], temperature: float, max_tokens: int, stream: bool, **kwargs) -> dict:
        return {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            **kwargs,
        }

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

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
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            return LLMResponse(
                content=choice["message"]["content"],
                model=data.get("model", self.model_name),
                usage=data.get("usage"),
                finish_reason=choice.get("finish_reason"),
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
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        import json
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                        except json.JSONDecodeError:
                            continue

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False
