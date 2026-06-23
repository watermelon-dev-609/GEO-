# conftest.py — pytest fixtures and configuration for GEO optimizer unit tests
# Requires: pytest, pytest-asyncio
#
# Usage:
#   cd backend && pytest tests/ -v
#   cd backend && pytest tests/ -v --cov=app --cov-report=term

from __future__ import annotations

import sys
import os
import tempfile
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import pytest
import numpy as np

# Ensure the backend directory is on sys.path so that "app.*" imports work
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)


# =============================================================================
# LLM Mocks (existing, preserved)
# =============================================================================

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


# =============================================================================
# Config Mocks — avoid real YAML / .env file I/O
# =============================================================================

# Default canned settings matching the real settings.yaml structure
DEFAULT_MOCK_SETTINGS = {
    "system": {
        "enterprise_name": "武汉微艺达智能科技有限公司",
        "enterprise_location": "武汉",
        "data_dir": "./data",
    },
    "embedding": {
        "model_name": "BAAI/bge-large-zh-v1.5",
        "device": "cpu",
        "dimension": 1024,
        "batch_size": 8,
        "cache_dir": "./data/cache/models",
        "hf_endpoint": "https://hf-mirror.com",
    },
    "brand_monitor": {
        "brand_variants": [],
    },
    "reputation": {
        "auto_scan_enabled": True,
        "incident_auto_create": True,
        "fact_check_enabled": True,
        "negative_keywords": ["骗", "假的", "不靠谱", "质量差", "坑", "不推荐", "虚假"],
        "positive_keywords": ["推荐", "专业", "靠谱", "领先", "优质"],
        "alert_threshold": {"critical": 3, "high": 2, "medium": 1},
    },
    "llm": {
        "default_platform": "deepseek",
        "default_model": "deepseek-chat",
    },
    "auth": {
        "enabled": False,
        "password_hash": "",
    },
    "usage": {
        "daily_limit": 1000,
        "monthly_limit": 10000,
    },
}

DEFAULT_MOCK_API_KEYS = {
    "deepseek": {"api_key": "sk-test-deepseek", "base_url": "https://api.deepseek.com/v1"},
    "kimi": {"api_key": "sk-test-kimi", "base_url": "https://api.moonshot.cn/v1"},
    "doubao": {"api_key": "sk-test-doubao", "base_url": "https://ark.cn-beijing.volces.com/api/v3"},
}


@pytest.fixture
def mock_settings():
    """Canned settings dict used by mock_config patches."""
    return dict(DEFAULT_MOCK_SETTINGS)


@pytest.fixture
def mock_api_keys():
    """Canned API keys dict used by mock_config patches."""
    return dict(DEFAULT_MOCK_API_KEYS)


@pytest.fixture
def mock_config(mock_settings, mock_api_keys):
    """Unified config mock — patches load_settings, load_api_keys, and convenience getters.

    Returns a dict with {settings, api_keys} for tests to mutate per-test.
    """
    settings = dict(mock_settings)
    api_keys = dict(mock_api_keys)

    def _load_settings():
        return settings

    def _load_api_keys():
        return api_keys

    def _get_enterprise_name():
        return settings.get("system", {}).get("enterprise_name", "武汉微艺达智能科技有限公司")

    def _get_enterprise_location():
        return settings.get("system", {}).get("enterprise_location", "武汉")

    def _get_brand_variants():
        name = _get_enterprise_name()
        loc = _get_enterprise_location()
        return [name, f"{loc}{name}", name.replace("有限公司", "").replace("责任公司", "")]

    def _get_data_dir():
        return Path(tempfile.mkdtemp(prefix="geo_test_data_"))

    patches = [
        patch("app.utils.config.load_settings", side_effect=_load_settings),
        patch("app.utils.config.load_api_keys", side_effect=_load_api_keys),
        patch("app.utils.config.get_enterprise_name", side_effect=_get_enterprise_name),
        patch("app.utils.config.get_enterprise_location", side_effect=_get_enterprise_location),
        patch("app.utils.config.get_brand_variants", side_effect=_get_brand_variants),
        patch("app.utils.config.get_data_dir", side_effect=_get_data_dir),
    ]

    for p in patches:
        p.start()

    yield {"settings": settings, "api_keys": api_keys}

    for p in patches:
        p.stop()


# =============================================================================
# Cache Mocks — avoid real file-system cache I/O
# =============================================================================

@pytest.fixture
def mock_geo_cache():
    """Mock the global geo_cache instance (2h TTL for rewrite results)."""
    cache = MagicMock()
    cache.get = MagicMock(return_value=None)  # cache miss by default
    cache.set = MagicMock()
    cache.delete = MagicMock()
    cache.clear = MagicMock(return_value=0)
    cache.stats = MagicMock(return_value={"namespace": "geo_rewrite", "entries": 0})
    cache.async_get = AsyncMock(return_value=None)
    cache.async_set = AsyncMock()
    cache.async_delete = AsyncMock()
    return cache


@pytest.fixture
def mock_eval_cache():
    """Mock the global eval_cache instance (1h TTL for evaluation results)."""
    cache = MagicMock()
    cache.get = MagicMock(return_value=None)
    cache.set = MagicMock()
    cache.delete = MagicMock()
    cache.clear = MagicMock(return_value=0)
    cache.async_get = AsyncMock(return_value=None)
    cache.async_set = AsyncMock()
    cache.async_delete = AsyncMock()
    return cache


@pytest.fixture
def mock_embed_cache():
    """Mock the global embed_cache instance (24h TTL for embeddings)."""
    cache = MagicMock()
    cache.get = MagicMock(return_value=None)
    cache.set = MagicMock()
    cache.delete = MagicMock()
    cache.clear = MagicMock(return_value=0)
    return cache


@pytest.fixture
def mock_all_caches(mock_geo_cache, mock_eval_cache, mock_embed_cache):
    """Patch all three global cache instances at once.

    Usage in test:
        def test_something(mock_all_caches):
            geo_cache, eval_cache, embed_cache = mock_all_caches
            geo_cache.get.return_value = some_cached_value
    """
    with patch("app.core.rewriter.geo_cache", mock_geo_cache), \
         patch("app.core.cleaner.geo_cache", mock_geo_cache), \
         patch("app.core.evaluator.eval_cache", mock_eval_cache), \
         patch("app.utils.cache.geo_cache", mock_geo_cache), \
         patch("app.utils.cache.eval_cache", mock_eval_cache), \
         patch("app.utils.cache.embed_cache", mock_embed_cache):
        yield (mock_geo_cache, mock_eval_cache, mock_embed_cache)


# =============================================================================
# Embedding Service Mock — avoid loading sentence-transformers model
# =============================================================================

@pytest.fixture
def mock_embedding_service():
    """Returns a MagicMock that acts like EmbeddingService.

    All encode methods return predictable numpy arrays.  Tests can override
    return values for specific scenarios.
    """
    svc = MagicMock()
    # Default: return 1024-dim normalized vectors
    svc.dimension = 1024
    svc.batch_size = 8

    def _default_encode(texts):
        if not texts:
            return np.array([])
        # Return predictable vectors: each text gets a unique deterministic vector
        vecs = []
        for i, t in enumerate(str(t)[:50]):
            seed = sum(ord(c) * (j + 1) for j, c in enumerate(str(t)[:50]))
            rng = np.random.RandomState(abs(seed) % (2 ** 31))
            v = rng.randn(1024).astype(np.float32)
            v = v / (np.linalg.norm(v) + 1e-8)
            vecs.append(v)
        return np.array(vecs)

    svc.encode = MagicMock(side_effect=_default_encode)
    svc.encode_single = MagicMock(side_effect=lambda t: _default_encode([t])[0] if t else np.zeros(1024))
    svc.encode_queries = MagicMock(side_effect=_default_encode)
    svc.encode_query = MagicMock(side_effect=lambda q: _default_encode([q])[0] if q else np.zeros(1024))
    svc.similarity = MagicMock(side_effect=lambda a, b: float(np.dot(a, b)))
    svc.batch_similarity = MagicMock(side_effect=lambda q, d: np.dot(d, q))
    svc.is_available = MagicMock(return_value=True)
    svc.model = MagicMock()
    return svc


# =============================================================================
# Vector Store Mock — avoid FAISS / NumPy file I/O
# =============================================================================

@pytest.fixture
def mock_vector_store():
    """Returns a MagicMock that acts like VectorStore.

    Stores vectors in-memory (no file I/O).  Tests can inspect stored data
    via `store._texts`, `store._metadata`, etc.
    """
    store = MagicMock()
    store.index_name = "test-index"
    store.dimension = 1024
    store.size = 0
    store._texts = []
    store._metadata = []
    store._vectors = []

    def _add(texts, vectors, metadata=None):
        store._texts.extend(texts)
        store._vectors.append(vectors.copy() if hasattr(vectors, 'copy') else vectors)
        if metadata:
            store._metadata.extend(metadata)
        else:
            store._metadata.extend([{}] * len(texts))
        store.size = len(store._texts)

    def _search(query_vector, top_k=5):
        if store.size == 0:
            return []
        # Simple dot-product search over stored vectors
        results = []
        for i, v in enumerate(store._vectors):
            if len(v.shape) == 1:
                score = float(np.dot(query_vector.flatten(), v.flatten()))
            else:
                score = float(np.dot(query_vector.flatten(), v.flatten()))
            results.append({
                "text": store._texts[i] if i < len(store._texts) else "",
                "score": score,
                "metadata": store._metadata[i] if i < len(store._metadata) else {},
                "index": i,
            })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _clear():
        store._texts = []
        store._metadata = []
        store._vectors = []
        store.size = 0

    store.add = MagicMock(side_effect=_add)
    store.search = MagicMock(side_effect=_search)
    store.save = MagicMock()
    store.load = MagicMock(return_value=True)
    store.clear = MagicMock(side_effect=_clear)
    return store


# =============================================================================
# Temp Data Directory — isolated filesystem for data-dependent tests
# =============================================================================

@pytest.fixture
def tmp_data_dir(tmp_path):
    """Provides a temporary data/ directory structure mirroring the real one.

    Use for tests that need real file I/O (JSON storage, YAML templates, etc.).
    Returns the Path to the temp data directory.
    """
    data_dir = tmp_path / "data"
    subdirs = [
        "evaluations", "platform_rules", "competitors", "keywords",
        "templates", "cache", "output", "brand_mentions", "sessions",
        "usage", "audit", "versions", "seo", "logs", "reports", "charts",
        "input", "samples", "platform_templates", "template_versions",
        "rss_monitor", "citation_tests", "structure_reports",
        "adaptation_runs", "feedback_metrics", "orchestrator",
        "reputation/incidents", "reputation/corrections", "reputation/scans",
        "cache/models", "cache/geo_rewrite", "cache/embeddings", "cache/evaluation",
    ]
    for sub in subdirs:
        (data_dir / sub).mkdir(parents=True, exist_ok=True)

    # Patch get_data_dir to return this temp dir
    with patch("app.utils.config.get_data_dir", return_value=data_dir), \
         patch("app.utils.cache.get_data_dir", return_value=data_dir), \
         patch("app.core.eval_history_store.get_data_dir", return_value=data_dir), \
         patch("app.core.evaluator.get_data_dir", return_value=data_dir):
        yield data_dir


# =============================================================================
# Autouse fixture — ensure clean config state for every test
# =============================================================================

@pytest.fixture(autouse=True)
def _reset_config_state():
    """Reset config cache before each test to prevent isolation issues."""
    from app.utils.config import invalidate_config_cache
    invalidate_config_cache()
    yield
    invalidate_config_cache()


# =============================================================================
# FastAPI TestClient — for API route tests
# =============================================================================

@pytest.fixture
def test_app(mock_config):
    """Returns a FastAPI TestClient instance with configs mocked.

    Usage:
        def test_my_endpoint(test_app):
            response = test_app.post("/api/cleaning/clean", json={...})
            assert response.status_code == 200
    """
    from fastapi.testclient import TestClient
    from app.main import app
    # Invalidate any cached config before creating TestClient
    from app.utils.config import invalidate_config_cache
    invalidate_config_cache()
    return TestClient(app)


# =============================================================================
# Async test helper — run coroutines in sync tests
# =============================================================================

@pytest.fixture
def run_async():
    """Helper to run async functions in sync test contexts.

    Usage:
        def test_something(run_async):
            result = run_async(some_async_function())
    """
    import asyncio
    def _run(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    return _run
