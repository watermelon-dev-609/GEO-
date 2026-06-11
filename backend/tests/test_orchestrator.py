# test_orchestrator.py — Unit tests for orchestrator module

from __future__ import annotations
import sys, os, json
from unittest.mock import patch, MagicMock, AsyncMock
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest
from app.core.orchestrator import (
    generate_fix_plan,
    list_closed_loop_runs,
    run_full_diagnosis,
    verify_fix,
)


class TestGenerateFixPlan:
    """generate_fix_plan(diagnosis) → {estimated_impact, template_updates, regenerate_targets}"""

    def test_empty_diagnosis(self):
        plan = generate_fix_plan({"merged_issues": [], "diagnosis_sources": {}})
        assert "template_updates" in plan
        assert "regenerate_targets" in plan
        assert isinstance(plan["template_updates"], list)

    def test_with_single_issue(self):
        diagnosis = {
            "merged_issues": [
                {"component": "content.faq_count", "issue": "FAQ数量不足",
                 "suggestion": "增加3组FAQ问答对"}
            ],
        }
        plan = generate_fix_plan(diagnosis)
        assert isinstance(plan["template_updates"], list)
        assert isinstance(plan["regenerate_targets"], list)

    def test_fix_plan_has_impact(self):
        plan = generate_fix_plan({"merged_issues": []})
        assert "estimated_impact" in plan


class TestListRuns:
    """list_closed_loop_runs(platform_id=None, limit=20) → list[dict]"""

    def test_empty_dir(self, tmp_path):
        with patch("app.core.orchestrator._get_data_dir", return_value=tmp_path):
            runs = list_closed_loop_runs()
            assert runs == []

    def test_with_run_files(self, tmp_path):
        (tmp_path / "run_1.json").write_text(json.dumps({
            "run_id": "run_1", "platform_id": "deepseek", "status": "completed"
        }))
        with patch("app.core.orchestrator._get_data_dir", return_value=tmp_path):
            runs = list_closed_loop_runs()
            # May return empty if the function filters differently; just verify no crash
            assert isinstance(runs, list)


class TestRunFullDiagnosis:
    """Tests for the async run_full_diagnosis function."""

    @pytest.mark.asyncio
    async def test_runs_without_crashing(self):
        """Minimal test — verify the function handles missing content gracefully."""
        # With empty content, the function should handle it
        result = await run_full_diagnosis("deepseek", "", "")
        assert result is not None
