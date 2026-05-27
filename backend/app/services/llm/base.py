"""LLM统一适配层 — 抽象基类"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import AsyncIterator
from dataclasses import dataclass


@dataclass
class LLMMessage:
    role: str  # system / user / assistant
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict | None = None  # token usage info
    finish_reason: str | None = None


class BaseLLMAdapter(ABC):
    """LLM适配器抽象基类 — 所有平台适配器必须实现"""

    def __init__(self, api_key: str, model_name: str, base_url: str | None = None):
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        """同步（一次性）对话"""
        ...

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncIterator[str]:
        """流式对话，逐token返回"""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """检查API是否可用"""
        ...

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """平台标识"""
        ...


class LLMFactory:
    """LLM适配器工厂 — 根据配置自动选配"""

    _adapters: dict[str, BaseLLMAdapter] = {}

    @classmethod
    def register(cls, name: str, adapter_cls: type[BaseLLMAdapter]):
        cls._adapters[name] = adapter_cls

    @classmethod
    def create(cls, platform: str, api_key: str, model_name: str, base_url: str | None = None) -> BaseLLMAdapter:
        adapter_cls = cls._adapters.get(platform)
        if adapter_cls is None:
            raise ValueError(f"未注册的LLM平台: {platform}，已注册: {list(cls._adapters)}")
        return adapter_cls(api_key=api_key, model_name=model_name, base_url=base_url)

    @classmethod
    def list_platforms(cls) -> list[str]:
        return list(cls._adapters.keys())


# 延迟注册（避免循环导入，在子类模块中完成注册）
def _register_adapters():
    """在需要时导入并注册所有适配器"""
    from app.services.llm.openai_compat import OpenAICompatAdapter
    from app.services.llm.claude import ClaudeAdapter
    from app.services.llm.wenxin import WenxinAdapter

    LLMFactory.register("openai_compat", OpenAICompatAdapter)
    LLMFactory.register("claude", ClaudeAdapter)
    LLMFactory.register("wenxin", WenxinAdapter)


# 自动注册
_register_adapters()
