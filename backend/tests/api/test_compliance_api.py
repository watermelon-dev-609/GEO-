# test_compliance_api.py — API route tests for compliance endpoints

from __future__ import annotations
import sys, os
_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest


class TestComplianceCheck:
    """Test POST /api/compliance/check"""

    def test_valid_request_returns_200(self, test_app):
        response = test_app.post("/api/compliance/check", json={
            "text": "武汉微艺达智能科技有限公司提供专业的沙盘模型定制服务。"
        })
        assert response.status_code == 200
        data = response.json()
        assert "passed" in data
        assert data["passed"] is True

    def test_with_forbidden_words(self, test_app):
        response = test_app.post("/api/compliance/check", json={
            "text": "这是最好的产品，行业第一品牌，绝对领先。"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["passed"] is False
        assert data["violation_count"] > 0
        assert "violations" in data
        assert "risk_level" in data

    def test_empty_text_rejected(self, test_app):
        """Empty text is rejected at Pydantic schema level (min_length constraint)."""
        response = test_app.post("/api/compliance/check", json={"text": ""})
        assert response.status_code == 422

    def test_missing_text_field(self, test_app):
        response = test_app.post("/api/compliance/check", json={})
        assert response.status_code == 422

    def test_high_risk_text(self, test_app):
        text = "最 第一 唯一 独家 首个 首创 首选 顶级 极品 最佳 100% 保证 国家级 全球领先"
        response = test_app.post("/api/compliance/check", json={"text": text})
        assert response.status_code == 200
        data = response.json()
        assert data["violation_count"] >= 8
        assert data["risk_level"] == "high"

    def test_risk_levels_present(self, test_app):
        response = test_app.post("/api/compliance/check", json={
            "text": "最好的产品，第一选择。"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["risk_level"] in ("none", "low", "medium", "high")


class TestRouteNotFound:
    """Test 404 handling."""

    def test_nonexistent_route(self, test_app):
        response = test_app.get("/api/nonexistent/endpoint")
        assert response.status_code == 404

    def test_compliance_wrong_method(self, test_app):
        response = test_app.get("/api/compliance/check")
        assert response.status_code == 405
