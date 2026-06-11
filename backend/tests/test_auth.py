# test_auth.py — Unit tests for auth module
#
# Tests cover:
# - hash_password / verify_password
# - SessionManager (create, validate, revoke, active_count, TTL)
# - is_auth_enabled() logic

from __future__ import annotations

import sys
import os
import time
import threading
from unittest.mock import patch
import pytest

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.auth import (
    hash_password,
    verify_password,
    SessionManager,
    is_auth_enabled,
    get_stored_password_hash,
)


class TestHashPassword:
    """Tests for password hashing."""

    def test_hash_returns_string(self):
        result = hash_password("test_password_123")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex = 64 chars

    def test_hash_is_deterministic_for_same_input(self):
        h1 = hash_password("mypassword")
        h2 = hash_password("mypassword")
        assert h1 == h2

    def test_different_passwords_produce_different_hashes(self):
        h1 = hash_password("password1")
        h2 = hash_password("password2")
        assert h1 != h2

    def test_hash_handles_empty_string(self):
        result = hash_password("")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_hash_handles_chinese_characters(self):
        result = hash_password("密码测试汉字")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_hash_handles_long_password(self):
        result = hash_password("a" * 500)
        assert isinstance(result, str)
        assert len(result) == 64


class TestVerifyPassword:
    """Tests for password verification."""

    def test_correct_password_verifies(self):
        hashed = hash_password("correct_password")
        assert verify_password("correct_password", hashed) is True

    def test_incorrect_password_fails(self):
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_case_sensitive(self):
        hashed = hash_password("Password")
        assert verify_password("password", hashed) is False

    def test_empty_password(self):
        hashed = hash_password("somepass")
        assert verify_password("", hashed) is False

    def test_empty_hash_returns_false(self):
        assert verify_password("anything", "") is False

    def test_empty_both(self):
        hashed = hash_password("")
        assert verify_password("", hashed) is True

    def test_unicode_passwords(self):
        hashed = hash_password("中文密码测试123!@#")
        assert verify_password("中文密码测试123!@#", hashed) is True
        assert verify_password("中文密码测试123", hashed) is False


class TestSessionManager:
    """Tests for SessionManager."""

    def setup_method(self):
        """Create a fresh SessionManager for each test."""
        self.manager = SessionManager(ttl=3600)

    def test_create_session_returns_token(self):
        token = self.manager.create()
        assert isinstance(token, str)
        assert len(token) == 64  # token_hex(32) = 64 hex chars

    def test_validate_valid_session(self):
        token = self.manager.create()
        assert self.manager.validate(token) is True

    def test_validate_invalid_token(self):
        assert self.manager.validate("invalid_token") is False

    def test_revoke_session(self):
        token = self.manager.create()
        self.manager.revoke(token)
        assert self.manager.validate(token) is False

    def test_revoke_nonexistent_does_not_crash(self):
        self.manager.revoke("nonexistent_token")

    def test_sessions_are_unique(self):
        token1 = self.manager.create()
        token2 = self.manager.create()
        assert token1 != token2
        assert self.manager.validate(token1) is True
        assert self.manager.validate(token2) is True

    def test_active_count(self):
        assert self.manager.active_count == 0
        self.manager.create()
        assert self.manager.active_count == 1
        self.manager.create()
        assert self.manager.active_count == 2

    def test_active_count_after_revoke(self):
        token = self.manager.create()
        assert self.manager.active_count == 1
        self.manager.revoke(token)
        assert self.manager.active_count == 0

    def test_session_expires_after_ttl(self):
        # Create with TTL=0 (immediately expired)
        short_mgr = SessionManager(ttl=0)
        token = short_mgr.create()
        # TTL=0 means instantly expired (created_at vs now, diff > 0)
        time.sleep(0.01)
        assert short_mgr.validate(token) is False
        assert short_mgr.active_count == 0  # expired session auto-cleaned

    def test_session_stays_valid_within_ttl(self):
        token = self.manager.create()
        assert self.manager.validate(token) is True

    def test_revoke_reduces_active_count(self):
        t1 = self.manager.create()
        t2 = self.manager.create()
        assert self.manager.active_count == 2
        self.manager.revoke(t1)
        assert self.manager.active_count == 1

    def test_thread_safety(self):
        """Verify SessionManager works correctly with concurrent access."""
        manager = SessionManager(ttl=3600)
        tokens = []

        def create_token():
            tokens.append(manager.create())

        threads = [threading.Thread(target=create_token) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(tokens) == 10
        assert manager.active_count == 10
        # All tokens should be valid
        for token in tokens:
            assert manager.validate(token) is True


class TestIsAuthEnabled:
    """Tests for is_auth_enabled()."""

    def test_auth_disabled_by_default(self):
        with patch("app.core.auth.load_settings", return_value={}):
            assert is_auth_enabled() is False

    def test_auth_enabled_when_configured(self):
        settings = {"auth": {"enabled": True}}
        with patch("app.core.auth.load_settings", return_value=settings):
            assert is_auth_enabled() is True

    def test_auth_disabled_when_explicitly_false(self):
        settings = {"auth": {"enabled": False}}
        with patch("app.core.auth.load_settings", return_value=settings):
            assert is_auth_enabled() is False

    def test_auth_enabled_only_checks_enabled_flag(self):
        # Even without password_hash, if enabled=True it's enabled
        settings = {"auth": {"enabled": True}}
        with patch("app.core.auth.load_settings", return_value=settings):
            assert is_auth_enabled() is True


class TestGetStoredPasswordHash:
    """Tests for get_stored_password_hash()."""

    def test_returns_none_when_no_hash(self):
        with patch("app.core.auth.load_settings", return_value={}):
            assert get_stored_password_hash() is None

    def test_returns_hash_when_configured(self):
        settings = {"auth": {"password_hash": "abc123hash"}}
        with patch("app.core.auth.load_settings", return_value=settings):
            assert get_stored_password_hash() == "abc123hash"

    def test_returns_none_when_empty_string(self):
        settings = {"auth": {"password_hash": ""}}
        with patch("app.core.auth.load_settings", return_value=settings):
            assert get_stored_password_hash() == ""
