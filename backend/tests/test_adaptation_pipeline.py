# test_adaptation_pipeline.py — Unit tests for adaptation pipeline

from __future__ import annotations
import sys, os, json
from unittest.mock import patch
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest
from app.core.adaptation_pipeline import (
    AdaptationRun, STAGES, STAGE_LABELS,
    _save_run, _get_data_dir,
    create_from_monitor_event,
)


class TestConstants:
    def test_11_stages(self):
        assert len(STAGES) == 11

    def test_all_stages_have_labels(self):
        for stage in STAGES:
            assert stage in STAGE_LABELS
            assert len(STAGE_LABELS[stage]) > 0

    def test_stage_order(self):
        assert STAGES[0] == "monitor_detected"
        assert STAGES[-1] == "post_test_7d"
        assert "published_10pct" in STAGES
        assert "published_100pct" in STAGES
        assert "post_test_3d" in STAGES


class TestAdaptationRun:
    def test_create_run(self):
        run = AdaptationRun("deepseek", "测试触发")
        assert run.platform_id == "deepseek"
        assert run.trigger_event == "测试触发"
        assert run.stage == "monitor_detected"
        assert run.status == "pending"
        assert run.run_id.startswith("adapt_")

    def test_to_dict_has_all_keys(self):
        run = AdaptationRun("wenxin", "event")
        d = run.to_dict()
        required_keys = [
            "run_id", "platform_id", "trigger_event", "stage", "status",
            "created_at", "articles_affected", "articles_regenerated",
            "stage_label",
        ]
        for key in required_keys:
            assert key in d, f"Missing: {key}"

    def test_to_dict_stage_label_matches(self):
        run = AdaptationRun("deepseek", "test")
        d = run.to_dict()
        assert d["stage_label"] == STAGE_LABELS["monitor_detected"]

    def test_stage_advance_reflected_in_dict(self):
        run = AdaptationRun("deepseek", "test")
        run.stage = "template_updated"
        d = run.to_dict()
        assert d["stage_label"] == STAGE_LABELS["template_updated"]
        assert d["stage"] == "template_updated"

    def test_unique_run_ids(self):
        r1 = AdaptationRun("a", "")
        r2 = AdaptationRun("b", "")
        assert r1.run_id != r2.run_id

    def test_rollback_fields_default(self):
        run = AdaptationRun("kimi", "")
        assert run.rollback_version_id == ""
        assert run.template_version_before == ""
        assert run.template_version_after == ""

    def test_validation_errors(self):
        run = AdaptationRun("deepseek", "")
        run.validation_errors.append("error1")
        run.validation_errors.append("error2")
        d = run.to_dict()
        assert len(d["validation_errors"]) == 2

    def test_articles_counters(self):
        run = AdaptationRun("doubao", "")
        run.articles_affected = 50
        run.articles_regenerated = 48
        run.articles_validated = 45
        run.articles_published = 40
        d = run.to_dict()
        assert d["articles_affected"] == 50
        assert d["articles_regenerated"] == 48
        assert d["articles_validated"] == 45
        assert d["articles_published"] == 40


class TestCreateFromMonitorEvent:
    @pytest.mark.asyncio
    async def test_create_run(self, tmp_path):
        data_dir = tmp_path / "adaptation_runs"
        data_dir.mkdir()
        with patch("app.core.adaptation_pipeline._get_data_dir", return_value=data_dir), \
             patch("app.core.template_engine.load_platform_template", return_value={"version": 3}):
            result = await create_from_monitor_event("deepseek", {"type": "test"})
            assert result["platform_id"] == "deepseek"
            assert result["stage"] == "monitor_detected"
            # File should exist
            files = list(data_dir.glob("*.json"))
            assert len(files) >= 1

    @pytest.mark.asyncio
    async def test_create_without_template(self, tmp_path):
        data_dir = tmp_path / "adaptation_runs"
        data_dir.mkdir()
        with patch("app.core.adaptation_pipeline._get_data_dir", return_value=data_dir), \
             patch("app.core.template_engine.load_platform_template", side_effect=Exception("no template")):
            result = await create_from_monitor_event("wenxin", None)
            assert result["platform_id"] == "wenxin"
            assert result["template_version_before"] == ""
