"""Ollama本地大模型适配器"""

from __future__ import annotations
import json
import logging
import aiohttp
from typing import AsyncIterator

from app.services.llm.base import BaseLLMAdapter, LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


class OllamaAdapter(BaseLLMAdapter):
    """Ollama API适配器 — 对接本地部署的大模型 (qwen2.5/llama3/deepseek-r1等)"""

    def __init__(self, api_key: str = "", model_name: str = "qwen2.5", base_url: str = "http://localhost:11434"):
        super().__init__(api_key, model_name, base_url)

    async def chat(self, messages: list[LLMMessage], temperature: float = 0.7, max_tokens: int = 4096) -> LLMResponse:
        url = f"{self.base_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": min(max_tokens, 4096),
            },
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"Ollama API错误 ({resp.status}): {text[:200]}")
                    data = await resp.json()
                    content = data.get("message", {}).get("content", "")
                    return LLMResponse(content=content)
        except aiohttp.ClientError as e:
            raise ConnectionError(f"无法连接Ollama服务 ({self.base_url}): 请确认Ollama已启动") from e

    async def stream_chat(self, messages: list[LLMMessage], temperature: float = 0.7, max_tokens: int = 4096) -> AsyncIterator[str]:
        url = f"{self.base_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": min(max_tokens, 4096),
            },
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"Ollama API错误 ({resp.status}): {text[:200]}")
                    async for line in resp.content:
                        line = line.decode("utf-8").strip()
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("message", {}).get("content", "")
                            if token:
                                yield token
                            if chunk.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue
        except aiohttp.ClientError as e:
            raise ConnectionError(f"无法连接Ollama服务 ({self.base_url}): 请确认Ollama已启动") from e

    async def is_available(self) -> bool:
        return True

    @property
    def platform_name(self) -> str:
        return "ollama"
