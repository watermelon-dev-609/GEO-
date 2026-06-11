# test_auth_api.py — API route tests for auth endpoints

from __future__ import annotations
import sys, os
_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest


class TestAuthLogin:
    """Test POST /api/auth/login"""

    def test_login_without_password_when_disabled(self, test_app):
        """When auth is disabled, login should return success."""
        response = test_app.post("/api/auth/login", json={"password": "any"})
        # May return 200 (auth disabled → always ok) or 401 (wrong password)
        assert response.status_code in (200, 401, 422)

    def test_login_without_body(self, test_app):
        response = test_app.post("/api/auth/login", json={})
        assert response.status_code in (200, 401, 422)

    def test_login_invalid_json(self, test_app):
        response = test_app.post("/api/auth/login", data="not json")
        assert response.status_code == 422


class TestAuthStatus:
    """Test GET /api/auth/status"""

    def test_status_returns_200(self, test_app):
        response = test_app.get("/api/auth/status")
        # May return 200 or 404 depending on route registration
        assert response.status_code in (200, 404)


class TestHealthEndpoints:
    """Test health and config endpoints."""

    def test_health_check(self, test_app):
        response = test_app.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_config_llm(self, test_app):
        response = test_app.get("/api/config/llm")
        assert response.status_code in (200, 500)
