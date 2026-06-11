# test_competitor_monitor.py — Unit tests for competitor_monitor module (v2.1)
#
# Tests cover:
# - Configuration loading (_load_monitor_config)
# - Competitor data loading (_load_competitors)
# - Rule reverse engineering (reverse_engineer_rules)
# - Cycle comparison (_compare_cycles)
# - Graceful degradation (no LLM configured, no competitors)
# - Monitoring history (get_monitoring_history)
# - Cycle comparison (compare_cycles)

from __future__ import annotations

import sys
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.competitor_monitor import (
    reverse_engineer_rules,
    _compare_cycles,
    get_monitoring_history,
    _load_monitor_config,
)


class TestReverseEngineerRules:
    """Tests for rule reverse-engineering from probe results."""

    def test_empty_results(self):
        """Empty probe results produce zero citation rate."""
        result = reverse_engineer_rules([])
        assert result["citation_rate"] == 0
        assert result["top_platforms"] == []
        assert result["rule_hypotheses"] == []

    def test_all_cited(self):
        """All platforms citing produces 1.0 citation rate."""
        probes = [
            {"platform": "wenxin", "cited": True, "confidence": 0.8,
             "content_features": ["FAQ", "structured_data"],
             "source_attribution": "官网", "citation_snippet": "test1"},
            {"platform": "deepseek", "cited": True, "confidence": 0.9,
             "content_features": ["FAQ", "quantified"],
             "source_attribution": "知乎", "citation_snippet": "test2"},
            {"platform": "doubao", "cited": True, "confidence": 0.7,
             "content_features": ["structured_data"],
             "source_attribution": "", "citation_snippet": "test3"},
        ]
        result = reverse_engineer_rules(probes)
        assert result["citation_rate"] == 1.0
        # Top platforms sorted by confidence
        assert result["top_platforms"][0] == "deepseek"
        assert result["top_platforms"][1] == "wenxin"

    def test_mixed_results(self):
        """Mixed cited/not-cited produces fractional citation rate."""
        probes = [
            {"platform": "wenxin", "cited": True, "confidence": 0.8,
             "content_features": ["FAQ"], "source_attribution": "",
             "citation_snippet": "test1"},
            {"platform": "deepseek", "cited": False, "confidence": 0.0,
             "content_features": [], "source_attribution": "",
             "citation_snippet": ""},
        ]
        result = reverse_engineer_rules(probes)
        assert result["citation_rate"] == 0.5

    def test_effective_patterns_sorted(self):
        """Effective patterns are sorted by frequency."""
        probes = [
            {"platform": "a", "cited": True, "confidence": 0.5,
             "content_features": ["FAQ", "structured_data", "quantified"],
             "source_attribution": "", "citation_snippet": ""},
            {"platform": "b", "cited": True, "confidence": 0.5,
             "content_features": ["FAQ", "quantified"],
             "source_attribution": "", "citation_snippet": ""},
            {"platform": "c", "cited": True, "confidence": 0.5,
             "content_features": ["FAQ"],
             "source_attribution": "", "citation_snippet": ""},
        ]
        result = reverse_engineer_rules(probes)
        # FAQ appears 3 times, quantified 2 times, structured_data 1 time
        assert result["effective_patterns"][0] == "FAQ"

    def test_hypotheses_generated_for_top_platforms(self):
        """Rule hypotheses are generated for top 3 cited platforms."""
        probes = [
            {"platform": "wenxin", "cited": True, "confidence": 0.9,
             "content_features": ["FAQ", "structured_data"],
             "source_attribution": "官网", "citation_snippet": "s1"},
            {"platform": "deepseek", "cited": True, "confidence": 0.8,
             "content_features": ["quantified"],
             "source_attribution": "知乎", "citation_snippet": "s2"},
        ]
        result = reverse_engineer_rules(probes)
        assert len(result["rule_hypotheses"]) >= 2

    def test_uncited_platforms_excluded_from_top(self):
        """Uncited platforms are not in top_platforms."""
        probes = [
            {"platform": "cited_plat", "cited": True, "confidence": 0.5,
             "content_features": [], "source_attribution": "",
             "citation_snippet": ""},
            {"platform": "uncited_plat", "cited": False, "confidence": 0.0,
             "content_features": [], "source_attribution": "",
             "citation_snippet": ""},
        ]
        result = reverse_engineer_rules(probes)
        assert "uncited_plat" not in result["top_platforms"]


class TestCompareCycles:
    """Tests for cycle comparison logic."""

    def test_is_first_run_when_no_previous(self):
        """Returns is_first_run=True when there is no previous cycle."""
        current = [
            {"competitor_id": "c1", "competitor_name": "竞品A",
             "aggregated_insights": {"citation_rate": 0.5, "effective_patterns": ["FAQ"]}},
        ]
        result = _compare_cycles({}, current)
        assert result["is_first_run"] is True

    def test_detects_new_patterns(self):
        """Newly appearing patterns are detected."""
        previous = {
            "results": [
                {"competitor_id": "c1", "competitor_name": "竞品A",
                 "aggregated_insights": {"citation_rate": 0.3, "effective_patterns": ["FAQ"]}},
            ],
        }
        current = [
            {"competitor_id": "c1", "competitor_name": "竞品A",
             "aggregated_insights": {"citation_rate": 0.3, "effective_patterns": ["FAQ", "structured_data"]}},
        ]
        result = _compare_cycles(previous, current)
        assert len(result["new_patterns_detected"]) >= 1
        assert any("structured_data" in p for p in result["new_patterns_detected"])

    def test_detects_citation_rate_drop(self):
        """Significant citation rate drop generates alert."""
        previous = {
            "results": [
                {"competitor_id": "c1", "competitor_name": "竞品A",
                 "aggregated_insights": {"citation_rate": 0.9, "effective_patterns": ["FAQ"]}},
            ],
        }
        current = [
            {"competitor_id": "c1", "competitor_name": "竞品A",
             "aggregated_insights": {"citation_rate": 0.4, "effective_patterns": ["FAQ"]}},
        ]
        result = _compare_cycles(previous, current)
        assert len(result["alerts"]) >= 1
        assert any("引用率" in a["summary"] for a in result["alerts"])

    def test_detects_pattern_drift(self):
        """Lost patterns are detected as drift."""
        previous = {
            "results": [
                {"competitor_id": "c1", "competitor_name": "竞品A",
                 "aggregated_insights": {"citation_rate": 0.5, "effective_patterns": ["FAQ", "quantified"]}},
            ],
        }
        current = [
            {"competitor_id": "c1", "competitor_name": "竞品A",
             "aggregated_insights": {"citation_rate": 0.5, "effective_patterns": ["FAQ"]}},
        ]
        result = _compare_cycles(previous, current)
        assert len(result["pattern_drift"]) >= 1
        assert any("quantified" in d for d in result["pattern_drift"])

    def test_detects_new_competitor(self):
        """New competitor appearing in current cycle is flagged."""
        previous = {
            "results": [
                {"competitor_id": "c1", "competitor_name": "竞品A",
                 "aggregated_insights": {"citation_rate": 0.5, "effective_patterns": []}},
            ],
        }
        current = [
            {"competitor_id": "c1", "competitor_name": "竞品A",
             "aggregated_insights": {"citation_rate": 0.5, "effective_patterns": []}},
            {"competitor_id": "c2", "competitor_name": "竞品B",
             "aggregated_insights": {"citation_rate": 0.7, "effective_patterns": []}},
        ]
        result = _compare_cycles(previous, current)
        assert any("竞品B" in p for p in result["new_patterns_detected"])


class TestMonitoringHistory:
    """Tests for monitoring history retrieval."""

    def test_returns_list(self):
        """get_monitoring_history always returns a list."""
        history = get_monitoring_history(days=3)
        assert isinstance(history, list)
        assert len(history) == 3  # One entry per day

    def test_entries_have_date(self):
        """Each history entry has a date field."""
        history = get_monitoring_history(days=1)
        assert len(history) == 1
        assert "date" in history[0]


class TestConfigLoading:
    """Tests for configuration loading."""

    def test_load_monitor_config_returns_dict(self):
        """_load_monitor_config always returns a dict."""
        config = _load_monitor_config()
        assert isinstance(config, dict)

    def test_config_has_expected_keys(self):
        """Config contains expected v2.1 keys from settings.yaml."""
        config = _load_monitor_config()
        # Keys from settings.yaml competitor_monitor section
        assert "enabled" in config
        assert "cycle_days" in config
        assert "platforms_to_probe" in config
