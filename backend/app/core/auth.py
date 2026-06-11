"""简易鉴权模块 — 单用户密码保护 + 会话管理"""

from __future__ import annotations
import hashlib
import secrets
import time
import threading
import logging

from app.utils.config import load_settings

logger = logging.getLogger(__name__)


class SessionManager:
    """内存会话管理"""

    def __init__(self, ttl: int = 7200):
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._ttl = ttl

    def create(self) -> str:
        token = secrets.token_hex(32)
        with self._lock:
            self._sessions[token] = {"created_at": time.time()}
        return token

    def validate(self, token: str) -> bool:
        with self._lock:
            session = self._sessions.get(token)
            if not session:
                return False
            if time.time() - session["created_at"] > self._ttl:
                del self._sessions[token]
                return False
            return True

    def revoke(self, token: str):
        with self._lock:
            self._sessions.pop(token, None)

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._sessions)


_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        settings = load_settings()
        ttl = settings.get("auth", {}).get("session_ttl", 7200)
        _session_manager = SessionManager(ttl=ttl)
    return _session_manager


def hash_password(password: str) -> str:
    """SHA-256 密码哈希"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    """验证密码"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest() == stored_hash


def is_auth_enabled() -> bool:
    """检查是否启用了鉴权"""
    settings = load_settings()
    return settings.get("auth", {}).get("enabled", False)


def get_stored_password_hash() -> str | None:
    """获取配置中的密码哈希"""
    settings = load_settings()
    return settings.get("auth", {}).get("password_hash")
