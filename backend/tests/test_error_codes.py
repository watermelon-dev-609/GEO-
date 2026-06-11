# test_error_codes.py — Unit tests for error_codes module
#
# Tests cover:
# - ERROR_CODES completeness and structure
# - get_error_info() lookup (valid and invalid codes)
# - get_error_code_by_category() (returns single error code string)
# - All categories present in mapping

from __future__ import annotations

import sys
import os

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.utils.error_codes import ERROR_CODES, get_error_info, get_error_code_by_category


class TestErrorCodesStructure:
    """Verify ERROR_CODES dictionary structure and completeness."""

    def test_error_codes_is_dict(self):
        assert isinstance(ERROR_CODES, dict)
        assert len(ERROR_CODES) >= 15

    def test_each_code_has_required_fields(self):
        for code, info in ERROR_CODES.items():
            assert "message" in info, f"{code} missing 'message'"
            assert "severity" in info, f"{code} missing 'severity'"
            assert "suggestion" in info, f"{code} missing 'suggestion'"
            assert isinstance(info["message"], str)
            assert len(info["message"]) > 0

    def test_severity_levels_are_valid(self):
        valid_severities = {"low", "medium", "high"}
        for code, info in ERROR_CODES.items():
            assert info["severity"] in valid_severities, \
                f"{code} has invalid severity: {info['severity']}"

    def test_code_prefixes(self):
        """Verify expected code ranges exist."""
        codes = set(ERROR_CODES.keys())
        assert "GEO_001" in codes  # network
        assert "GEO_010" in codes  # auth
        assert "GEO_020" in codes  # content
        assert "GEO_030" in codes  # generation
        assert "GEO_040" in codes  # system
        assert "GEO_050" in codes  # batch


class TestGetErrorInfo:
    """Tests for get_error_info()."""

    def test_known_code_returns_info(self):
        info = get_error_info("GEO_001")
        assert info is not None
        assert "message" in info
        assert "severity" in info
        assert info["message"] == "网络连接失败"

    def test_known_code_returns_copy_not_reference(self):
        info1 = get_error_info("GEO_001")
        info2 = get_error_info("GEO_001")
        info1["custom"] = "test"
        assert "custom" not in info2

    def test_unknown_code_returns_fallback(self):
        info = get_error_info("NONEXISTENT_CODE")
        assert info is not None
        assert "message" in info
        assert "未知错误" in info["message"]

    def test_empty_string_returns_fallback(self):
        info = get_error_info("")
        assert info is not None
        assert "severity" in info

    def test_content_short_code(self):
        info = get_error_info("GEO_020")
        assert "50" in info["message"] or "过短" in info["message"]

    def test_empty_response_code(self):
        info = get_error_info("GEO_030")
        assert "空" in info["message"]


class TestGetErrorCodeByCategory:
    """Tests for get_error_code_by_category() — returns a single error code string."""

    def test_known_category_returns_code(self):
        code = get_error_code_by_category("network")
        assert code == "GEO_001"

    def test_timeout_category(self):
        code = get_error_code_by_category("timeout")
        assert code == "GEO_002"

    def test_connection_category(self):
        code = get_error_code_by_category("connection")
        assert code == "GEO_003"

    def test_auth_category(self):
        code = get_error_code_by_category("auth")
        assert code == "GEO_010"

    def test_quota_category(self):
        code = get_error_code_by_category("quota")
        assert code == "GEO_011"

    def test_rate_limit_category(self):
        code = get_error_code_by_category("rate_limit")
        assert code == "GEO_012"

    def test_content_short_category(self):
        code = get_error_code_by_category("content_short")
        assert code == "GEO_020"

    def test_compliance_category(self):
        code = get_error_code_by_category("compliance")
        assert code == "GEO_022"

    def test_empty_response_category(self):
        code = get_error_code_by_category("empty_response")
        assert code == "GEO_030"

    def test_source_mismatch_category(self):
        code = get_error_code_by_category("source_mismatch")
        assert code == "GEO_033"

    def test_system_category(self):
        code = get_error_code_by_category("system")
        assert code == "GEO_040"

    def test_unknown_category_falls_back_to_geo_001(self):
        code = get_error_code_by_category("nonexistent_category_xyz")
        assert code == "GEO_001"
