# test_llm_base.py — Unit tests for LLM adapter base classes

from __future__ import annotations
import sys, os
_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest
from app.services.llm.base import LLMMessage, LLMResponse, BaseLLMAdapter, LLMFactory


class TestLLMMessage:
    def test_create_message(self):
        msg = LLMMessage(role="system", content="You are helpful.")
        assert msg.role == "system"
        assert msg.content == "You are helpful."

    def test_user_message(self):
        msg = LLMMessage(role="user", content="Hello")
        assert msg.role == "user"


class TestLLMResponse:
    def test_basic_response(self):
        resp = LLMResponse(content="test", model="gpt-4")
        assert resp.content == "test"
        assert resp.model == "gpt-4"

    def test_with_usage(self):
        resp = LLMResponse(content="ok", model="test", usage={"tokens": 10}, finish_reason="stop")
        assert resp.usage == {"tokens": 10}
        assert resp.finish_reason == "stop"

    def test_defaults(self):
        resp = LLMResponse(content="", model="")
        assert resp.usage is None
        assert resp.finish_reason is None


class TestLLMFactory:
    def test_registered_adapters(self):
        platforms = LLMFactory.list_platforms()
        assert "openai_compat" in platforms
        assert "claude" in platforms
        assert "wenxin" in platforms
        assert "ollama" in platforms
        assert "lmstudio" in platforms
        assert len(platforms) >= 5

    def test_create_known_platform(self):
        adapter = LLMFactory.create("ollama", "key", "model", "http://localhost:11434")
        assert adapter is not None
        assert adapter.api_key == "key"
        assert adapter.model_name == "model"

    def test_create_unknown_platform(self):
        with pytest.raises(ValueError, match="未注册的LLM平台"):
            LLMFactory.create("nonexistent", "key", "model")

    def test_create_claude(self):
        adapter = LLMFactory.create("claude", "sk-test", "claude-3")
        assert adapter.platform_name == "claude"

    def test_create_wenxin(self):
        adapter = LLMFactory.create("wenxin", "key", "ernie-bot")
        assert adapter.platform_name == "wenxin"

    def test_create_openai_compat(self):
        adapter = LLMFactory.create("openai_compat", "sk-test", "deepseek-chat", "https://api.deepseek.com/v1")
        assert adapter.platform_name == "openai_compat"
        assert adapter.base_url == "https://api.deepseek.com/v1"

    def test_create_lmstudio(self):
        adapter = LLMFactory.create("lmstudio", "local", "local-model", "http://localhost:1234/v1")
        assert adapter.platform_name == "lmstudio"
