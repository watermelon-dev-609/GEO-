# test_enums.py — Validation tests for all 8 business enums

from __future__ import annotations
import sys, os
_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest
from app.models.enums import (
    SandtableType, AIPlatform, UserRole, EvalDimension,
    ContentFormat, ExportFormat, EvalPhase, EvalPhaseStatus,
)


class TestSandtableType:
    def test_9_members(self):
        assert len(SandtableType) == 9

    def test_all_have_labels(self):
        for st in SandtableType:
            assert st.label is not None
            assert len(st.label) > 0

    def test_all_have_categories(self):
        cats = {st.category for st in SandtableType}
        assert "smart_industry_group" in cats
        assert "military" in cats
        assert "digital_media" in cats
        assert "real_estate" in cats
        assert "general" in cats

    def test_smart_types_share_category(self):
        for st in [SandtableType.SMART_TRAFFIC, SandtableType.SMART_CITY,
                    SandtableType.SMART_INDUSTRY, SandtableType.SMART_AGRICULTURE,
                    SandtableType.SMART_LOGISTICS]:
            assert st.category == "smart_industry_group"

    def test_values_unique(self):
        vals = [st.value for st in SandtableType]
        assert len(vals) == len(set(vals))


class TestAIPlatform:
    def test_11_members(self):
        assert len(AIPlatform) == 11

    def test_all_have_labels(self):
        for p in AIPlatform:
            assert p.label is not None

    def test_all_have_adapter_type(self):
        for p in AIPlatform:
            at = p.adapter_type
            assert at in ("wenxin", "openai_compat", "claude", "ollama", "lmstudio")

    def test_most_use_openai_compat(self):
        compat = [p for p in AIPlatform if p.adapter_type == "openai_compat"]
        assert len(compat) >= 6  # deepseek, kimi, tongyi, doubao, yuanbao, xinghuo, openai

    def test_wenxin_has_own_adapter(self):
        assert AIPlatform.WENXIN.adapter_type == "wenxin"

    def test_claude_has_own_adapter(self):
        assert AIPlatform.CLAUDE.adapter_type == "claude"


class TestUserRole:
    def test_4_members(self):
        assert len(UserRole) == 4

    def test_all_have_labels(self):
        for role in UserRole:
            assert role.label is not None


class TestEvalDimension:
    def test_10_members(self):
        assert len(EvalDimension) == 10  # 8 original + semantic_alignment + rag_retrievability


class TestContentFormat:
    def test_6_members(self):
        assert len(ContentFormat) == 6


class TestExportFormat:
    def test_6_members(self):
        assert len(ExportFormat) == 6


class TestEvalPhase:
    def test_12_members(self):
        assert len(EvalPhase) == 12  # 10 original + semantic_alignment + rag_retrievability

    def test_all_have_labels(self):
        for p in EvalPhase:
            assert p.label is not None

    def test_unique_orders(self):
        orders = [p.order for p in EvalPhase]
        assert len(orders) == len(set(orders))
        assert min(orders) == 0
        assert max(orders) == 11

    def test_order_sequence(self):
        assert EvalPhase.GENERATING_QUESTIONS.order == 0
        assert EvalPhase.COMPREHENSIVE.order == 11


class TestEvalPhaseStatus:
    def test_6_members(self):
        assert len(EvalPhaseStatus) == 6

    def test_expected_values(self):
        assert EvalPhaseStatus.PENDING.value == "pending"
        assert EvalPhaseStatus.RUNNING.value == "running"
        assert EvalPhaseStatus.COMPLETED.value == "completed"
        assert EvalPhaseStatus.SKIPPED.value == "skipped"
        assert EvalPhaseStatus.FAILED.value == "failed"
        assert EvalPhaseStatus.CANCELLED.value == "cancelled"
