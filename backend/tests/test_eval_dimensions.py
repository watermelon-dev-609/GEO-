# test_eval_dimensions.py — Unit tests for DimensionRegistry and EvalDimension

from __future__ import annotations

import sys
import os

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.eval_dimensions import (
    EvalDimension,
    DimensionRegistry,
    DEFAULT_WEIGHTS,
)
from app.models.enums import EvalPhase


class TestEvalDimension:
    """Tests for EvalDimension class."""

    def test_create_dimension(self):
        dim = EvalDimension(
            key="test_dim",
            label="测试维度",
            phase=EvalPhase.BRAND_RECALL,
            requires_llm=False,
        )
        assert dim.key == "test_dim"
        assert dim.label == "测试维度"
        assert dim.phase == EvalPhase.BRAND_RECALL
        assert dim.requires_llm is False
        assert dim.compute is None

    def test_to_config_with_defaults(self):
        dim = EvalDimension(key="test", label="Test", phase=EvalPhase.BRAND_RECALL, requires_llm=True)
        config = dim.to_config()
        assert config["key"] == "test"
        assert config["label"] == "Test"
        assert config["requires_llm"] is True
        assert "weight" in config
        assert config["enabled"] is True

    def test_to_config_with_custom_weight(self):
        dim = EvalDimension(key="test", label="Test", phase=EvalPhase.BRAND_RECALL, requires_llm=False)
        config = dim.to_config(weight=25.0, enabled=False)
        assert config["weight"] == 25.0
        assert config["enabled"] is False


class TestDimensionRegistry:
    """Tests for DimensionRegistry."""

    def test_registered_8_dimensions(self):
        dims = DimensionRegistry.list_all()
        assert len(dims) == 8

    def test_get_known_dimension(self):
        dim = DimensionRegistry.get("brand_recall")
        assert dim is not None
        assert dim.key == "brand_recall"
        assert dim.label == "品牌召回率"

    def test_get_unknown_dimension(self):
        dim = DimensionRegistry.get("nonexistent")
        assert dim is None

    def test_list_all_returns_copies(self):
        dims1 = DimensionRegistry.list_all()
        dims2 = DimensionRegistry.list_all()
        assert len(dims1) == len(dims2)

    def test_default_weights_sum_to_100(self):
        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 100.0) < 0.5

    def test_all_registered_have_default_weights(self):
        for dim in DimensionRegistry.list_all():
            assert dim.key in DEFAULT_WEIGHTS, f"Missing default weight for {dim.key}"

    def test_list_enabled_all(self):
        configs = [
            {"key": "brand_recall", "enabled": True},
            {"key": "solution_match", "enabled": True},
        ]
        enabled = DimensionRegistry.list_enabled(configs)
        assert len(enabled) == 2

    def test_list_enabled_filters_disabled(self):
        configs = [
            {"key": "brand_recall", "enabled": True},
            {"key": "solution_match", "enabled": False},
            {"key": "advantage_citation", "enabled": True},
        ]
        enabled = DimensionRegistry.list_enabled(configs)
        keys = [d.key for d in enabled]
        assert "brand_recall" in keys
        assert "solution_match" not in keys
        assert "advantage_citation" in keys

    def test_list_enabled_defaults_to_true(self):
        """If 'enabled' is not specified, default to True."""
        configs = [{"key": "brand_recall"}]
        enabled = DimensionRegistry.list_enabled(configs)
        assert len(enabled) == 1

    def test_list_enabled_empty(self):
        enabled = DimensionRegistry.list_enabled([])
        assert enabled == []

    def test_get_phases_from_configs(self):
        configs = [
            {"key": "brand_recall", "enabled": True},
            {"key": "solution_match", "enabled": True},
        ]
        phases = DimensionRegistry.get_phases_from_configs(configs)
        # Should include BRAND_RECALL, SOLUTION_MATCH, plus GENERATING_QUESTIONS and COMPREHENSIVE
        assert EvalPhase.BRAND_RECALL in phases
        assert EvalPhase.SOLUTION_MATCH in phases
        assert EvalPhase.GENERATING_QUESTIONS in phases
        assert EvalPhase.COMPREHENSIVE in phases

    def test_get_phases_sorted_by_order(self):
        configs = [
            {"key": "source_consistency", "enabled": True},
            {"key": "brand_recall", "enabled": True},
        ]
        phases = DimensionRegistry.get_phases_from_configs(configs)
        orders = [p.order for p in phases]
        assert orders == sorted(orders)

    def test_get_phases_no_duplicates(self):
        configs = [
            {"key": "brand_recall", "enabled": True},
            {"key": "solution_match", "enabled": True},
        ]
        phases = DimensionRegistry.get_phases_from_configs(configs)
        assert len(phases) == len(set(phases))


class TestDimensionWeights:
    """Tests for DEFAULT_WEIGHTS."""

    def test_weights_positive(self):
        for w in DEFAULT_WEIGHTS.values():
            assert w > 0

    def test_critical_dimensions_have_higher_weight(self):
        # brand_recall and solution_match are the heaviest
        assert DEFAULT_WEIGHTS["brand_recall"] >= DEFAULT_WEIGHTS["differentiation"]
        assert DEFAULT_WEIGHTS["solution_match"] >= DEFAULT_WEIGHTS["structure_quality"]
