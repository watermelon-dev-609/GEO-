# test_cache.py — Unit tests for LocalCache

from __future__ import annotations
import sys, os, time
_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from unittest.mock import patch
import pytest
from app.utils.cache import LocalCache


@pytest.fixture
def cache_dir(tmp_path):
    """LocalCache using a temp directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    with patch("app.utils.cache.get_data_dir", return_value=data_dir):
        yield data_dir


class TestLocalCache:
    def test_set_and_get(self, cache_dir):
        c = LocalCache(namespace="test", ttl_seconds=3600)
        c.set("key1", {"data": "value1"})
        result = c.get("key1")
        assert result == {"data": "value1"}

    def test_get_missing_key(self, cache_dir):
        c = LocalCache(namespace="test", ttl_seconds=3600)
        result = c.get("nonexistent")
        assert result is None

    def test_ttl_expiry(self, cache_dir):
        c = LocalCache(namespace="test", ttl_seconds=0)  # expires immediately
        c.set("key1", "value")
        time.sleep(0.01)
        result = c.get("key1")
        assert result is None

    def test_delete(self, cache_dir):
        c = LocalCache(namespace="test", ttl_seconds=3600)
        c.set("key1", "value")
        c.delete("key1")
        assert c.get("key1") is None

    def test_delete_nonexistent(self, cache_dir):
        c = LocalCache(namespace="test", ttl_seconds=3600)
        c.delete("nonexistent")  # should not raise

    def test_clear(self, cache_dir):
        c = LocalCache(namespace="test", ttl_seconds=3600)
        c.set("k1", "v1")
        c.set("k2", "v2")
        count = c.clear()
        assert count >= 2  # each key creates 2 files (.cache + .meta.json)
        assert c.get("k1") is None
        assert c.get("k2") is None

    def test_stats(self, cache_dir):
        c = LocalCache(namespace="test", ttl_seconds=3600)
        c.set("k1", "v1")
        stats = c.stats()
        assert stats["namespace"] == "test"
        assert "entries" in stats
        assert "total_size_bytes" in stats

    def test_namespace_isolation(self, cache_dir):
        c1 = LocalCache(namespace="ns1", ttl_seconds=3600)
        c2 = LocalCache(namespace="ns2", ttl_seconds=3600)
        c1.set("key", "value1")
        c2.set("key", "value2")
        assert c1.get("key") == "value1"
        assert c2.get("key") == "value2"

    def test_complex_data_types(self, cache_dir):
        c = LocalCache(namespace="test", ttl_seconds=3600)
        data = {"list": [1, 2, 3], "nested": {"a": {"b": "c"}}, "num": 42}
        c.set("complex", data)
        result = c.get("complex")
        assert result == data

    def test_md5_key_hashing(self, cache_dir):
        c = LocalCache(namespace="test", ttl_seconds=3600)
        # Keys with special characters
        c.set("中文key/with:special*chars?", "value")
        result = c.get("中文key/with:special*chars?")
        assert result == "value"


class TestAsyncCache:
    @pytest.mark.asyncio
    async def test_async_set_and_get(self, cache_dir):
        c = LocalCache(namespace="test", ttl_seconds=3600)
        await c.async_set("akey", {"data": 123})
        result = await c.async_get("akey")
        assert result == {"data": 123}

    @pytest.mark.asyncio
    async def test_async_delete(self, cache_dir):
        c = LocalCache(namespace="test", ttl_seconds=3600)
        await c.async_set("akey", "value")
        await c.async_delete("akey")
        result = await c.async_get("akey")
        assert result is None
