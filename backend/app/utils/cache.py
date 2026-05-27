"""本地文件缓存 — 零依赖、纯文件系统缓存"""

import json
import pickle
import hashlib
import time
from pathlib import Path
from typing import Optional, Any
from app.utils.config import get_data_dir


class LocalCache:
    """轻量化本地缓存"""

    def __init__(self, namespace: str = "default", ttl_seconds: int = 3600):
        self.namespace = namespace
        self.ttl = ttl_seconds
        self.cache_dir = get_data_dir() / "cache" / namespace
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_path(self, key: str) -> Path:
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.cache"

    def _meta_path(self, key_path: Path) -> Path:
        return key_path.with_suffix(".meta.json")

    def get(self, key: str) -> Optional[Any]:
        """读取缓存，过期返回None"""
        kp = self._key_path(key)
        mp = self._meta_path(kp)
        if not kp.exists() or not mp.exists():
            return None
        try:
            with open(mp, "r") as f:
                meta = json.load(f)
            if time.time() - meta["ts"] > self.ttl:
                self.delete(key)
                return None
            with open(kp, "rb") as f:
                return pickle.load(f)
        except (OSError, pickle.PickleError, json.JSONDecodeError):
            return None

    def set(self, key: str, value: Any) -> None:
        """写入缓存"""
        kp = self._key_path(key)
        mp = self._meta_path(kp)
        with open(kp, "wb") as f:
            pickle.dump(value, f)
        with open(mp, "w") as f:
            json.dump({"ts": time.time(), "key": key}, f)

    def delete(self, key: str) -> None:
        kp = self._key_path(key)
        mp = self._meta_path(kp)
        for p in (kp, mp):
            if p.exists():
                p.unlink()

    def clear(self) -> int:
        """清空命名空间所有缓存，返回清除数量"""
        count = 0
        for f in self.cache_dir.glob("*"):
            f.unlink()
            count += 1
        return count

    def stats(self) -> dict:
        """缓存统计"""
        files = list(self.cache_dir.glob("*.cache"))
        total_size = sum(f.stat().st_size for f in files)
        return {
            "namespace": self.namespace,
            "entries": len(files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "ttl_seconds": self.ttl,
        }


# 全局缓存实例
geo_cache = LocalCache(namespace="geo_rewrite", ttl_seconds=7200)
embed_cache = LocalCache(namespace="embeddings", ttl_seconds=86400)
eval_cache = LocalCache(namespace="evaluation", ttl_seconds=3600)
