# conftest.py — pytest fixtures and configuration for GEO optimizer unit tests
# Requires: pytest, pytest-asyncio

from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock
import pytest

# Ensure the backend directory is on sys.path so that "app.*" imports work
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)


@pytest.fixture
def mock_llm_response():
    """Factory fixture — returns a helper to create LLMResponse-like objects on the fly."""

    from app.services.llm.base import LLMResponse

    def _make(content: str = "", model: str = "test-model") -> LLMResponse:
        return LLMResponse(content=content, model=model, usage=None, finish_reason="stop")

    return _make


@pytest.fixture
def mock_llm_adapter(mock_llm_response):
    """Returns a MagicMock that acts like BaseLLMAdapter.

    The `chat()` async method returns a configurable LLMResponse.  Tests can override
    `adapter.chat.return_value` or `adapter.chat.side_effect` as needed.
    """
    adapter = MagicMock()
    adapter.chat = AsyncMock(return_value=mock_llm_response("default mock content"))
    adapter.stream_chat = AsyncMock(return_value=None)
    adapter.is_available = AsyncMock(return_value=True)
    adapter.platform_name = "test-platform"
    adapter.model_name = "test-model"
    return adapter
