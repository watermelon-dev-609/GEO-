# test_dimensions_shared.py — Unit tests for dimensions_shared module
#
# Tests cover:
# - Constants (DIMENSION_KEYS, EXTRA_KEYS, ALL_DIMENSION_KEYS, DIMENSION_LABELS)
# - empty_dimensions() / empty_dimensions_with_extras()
# - format_dimensions()
# - validate_dimensions()
# - DIMENSION_COVERAGE_KEYWORDS structure

from __future__ import annotations

import pytest
from app.core.dimensions_shared import (
    DIMENSION_KEYS,
    EXTRA_KEYS,
    ALL_DIMENSION_KEYS,
    DIMENSION_LABELS,
    DIMENSION_COVERAGE_KEYWORDS,
    empty_dimensions,
    empty_dimensions_with_extras,
    format_dimensions,
    validate_dimensions,
)


class TestConstants:
    """Verify constant values are correct and consistent."""

    def test_dimension_keys_has_five_entries(self):
        assert len(DIMENSION_KEYS) == 5
        assert "core_advantages" in DIMENSION_KEYS
        assert "applicable_scenarios" in DIMENSION_KEYS
        assert "technical_features" in DIMENSION_KEYS
        assert "service_capabilities" in DIMENSION_KEYS
        assert "implementation_value" in DIMENSION_KEYS

    def test_extra_keys(self):
        assert "key_phrases" in EXTRA_KEYS

    def test_all_keys_includes_dimension_and_extras(self):
        assert len(ALL_DIMENSION_KEYS) == 6
        for key in DIMENSION_KEYS:
            assert key in ALL_DIMENSION_KEYS
        for key in EXTRA_KEYS:
            assert key in ALL_DIMENSION_KEYS

    def test_dimension_labels_maps_all_keys(self):
        for key in DIMENSION_KEYS:
            assert key in DIMENSION_LABELS
            assert isinstance(DIMENSION_LABELS[key], str)
            assert len(DIMENSION_LABELS[key]) > 0

    def test_coverage_keywords_has_five_categories(self):
        assert len(DIMENSION_COVERAGE_KEYWORDS) == 5
        for label, keywords in DIMENSION_COVERAGE_KEYWORDS.items():
            assert isinstance(keywords, list)
            assert len(keywords) > 0


class TestEmptyDimensions:
    """Tests for empty dimension factory functions."""

    def test_empty_dimensions_returns_dict_with_five_keys(self):
        dims = empty_dimensions()
        assert isinstance(dims, dict)
        assert len(dims) == 5
        for key in DIMENSION_KEYS:
            assert key in dims
            assert dims[key] == []

    def test_empty_dimensions_with_extras_returns_six_keys(self):
        dims = empty_dimensions_with_extras()
        assert len(dims) == 6
        for key in ALL_DIMENSION_KEYS:
            assert key in dims
            assert dims[key] == []

    def test_empty_dimensions_are_independent_instances(self):
        dims1 = empty_dimensions()
        dims2 = empty_dimensions()
        dims1["core_advantages"].append("test")
        assert dims2["core_advantages"] == []


class TestFormatDimensions:
    """Tests for format_dimensions()."""

    def test_empty_dimensions_returns_placeholder(self):
        dims = empty_dimensions()
        result = format_dimensions(dims)
        assert "暂无五维信息" in result

    def test_partial_dimensions_formats_only_filled(self):
        dims = empty_dimensions()
        dims["core_advantages"] = ["高精度工艺", "快速交付"]
        result = format_dimensions(dims)
        assert "核心优势" in result
        assert "高精度工艺" in result
        assert "快速交付" in result

    def test_full_dimensions_formats_all_five(self):
        dims = {
            "core_advantages": ["优势A"],
            "applicable_scenarios": ["场景A"],
            "technical_features": ["技术A"],
            "service_capabilities": ["服务A"],
            "implementation_value": ["价值A"],
        }
        result = format_dimensions(dims)
        assert "核心优势" in result
        assert "适用场景" in result
        assert "技术特点" in result
        assert "服务能力" in result
        assert "落地价值" in result

    def test_custom_separator(self):
        dims = empty_dimensions()
        dims["core_advantages"] = ["A", "B", "C"]
        result = format_dimensions(dims, separator="|")
        assert "A|B|C" in result

    def test_empty_lists_are_skipped(self):
        dims = {
            "core_advantages": ["测试"],
            "applicable_scenarios": [],
            "technical_features": [],
            "service_capabilities": [],
            "implementation_value": [],
        }
        result = format_dimensions(dims)
        assert "核心优势" in result
        # Other dimensions with empty lists should not appear
        assert result.count("**") == 2  # opening and closing for one dimension

    def test_key_phrases_in_all_keys_but_not_in_dimension_keys(self):
        """key_phrases is in ALL_DIMENSION_KEYS but format_dimensions only iterates DIMENSION_KEYS."""
        dims = empty_dimensions_with_extras()
        dims["key_phrases"] = ["沙盘", "模型"]
        result = format_dimensions(dims)
        assert "暂无五维信息" in result  # no core dimension filled
        assert "沙盘" not in result  # key_phrases not formatted


class TestValidateDimensions:
    """Tests for validate_dimensions()."""

    def test_empty_dimensions_all_missing(self):
        dims = empty_dimensions()
        missing = validate_dimensions(dims)
        assert len(missing) == 5

    def test_full_dimensions_none_missing(self):
        dims = {
            "core_advantages": ["A"],
            "applicable_scenarios": ["B"],
            "technical_features": ["C"],
            "service_capabilities": ["D"],
            "implementation_value": ["E"],
        }
        missing = validate_dimensions(dims)
        assert missing == []

    def test_partial_dimensions_reports_correct_missing(self):
        dims = empty_dimensions()
        dims["core_advantages"] = ["A"]
        dims["applicable_scenarios"] = ["B"]
        missing = validate_dimensions(dims)
        assert len(missing) == 3
        assert "技术特点" in missing
        assert "服务能力" in missing
        assert "落地价值" in missing
        assert "核心优势" not in missing
        assert "适用场景" not in missing

    def test_empty_list_counts_as_missing(self):
        dims = empty_dimensions()
        dims["core_advantages"] = []  # empty list = missing
        missing = validate_dimensions(dims)
        assert "核心优势" in missing

    def test_unknown_keys_ignored(self):
        dims = empty_dimensions()
        dims["extra_field"] = ["something"]
        missing = validate_dimensions(dims)
        assert len(missing) == 5  # extra_field doesn't affect validation
