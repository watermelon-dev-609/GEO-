"""LM Studio本地大模型适配器"""

from __future__ import annotations
import logging
from typing import AsyncIterator
from app.services.llm.base import BaseLLMAdapter, LLMMessage, LLMResponse
from app.services.llm.openai_compat import OpenAICompatAdapter

logger = logging.getLogger(__name__)


class LMStudioAdapter(BaseLLMAdapter):
    """LM Studio适配器 — OpenAI兼容接口 (http://localhost:1234/v1)"""

    def __init__(self, api_key: str = "lm-studio", model_name: str = "local-model", base_url: str = "http://localhost:1234/v1"):
        super().__init__(api_key, model_name, base_url)
        self._openai_adapter = OpenAICompatAdapter(
            api_key=api_key,
            model_name=model_name,
            base_url=base_url,
        )

    async def chat(self, messages: list[LLMMessage], temperature: float = 0.7, max_tokens: int = 4096) -> LLMResponse:
        try:
            return await self._openai_adapter.chat(messages, temperature, max_tokens)
        except Exception as e:
            raise ConnectionError(
                f"无法连接LM Studio服务 ({self.base_url}): 请确认LM Studio已启动并加载模型"
            ) from e

    async def stream_chat(self, messages: list[LLMMessage], temperature: float = 0.7, max_tokens: int = 4096) -> AsyncIterator[str]:
        try:
            async for token in self._openai_adapter.stream_chat(messages, temperature, max_tokens):
                yield token
        except Exception as e:
            raise ConnectionError(
                f"无法连接LM Studio服务 ({self.base_url}): 请确认LM Studio已启动并加载模型"
            ) from e

    async def is_available(self) -> bool:
        return True

    @property
    def platform_name(self) -> str:
        return "lmstudio"
