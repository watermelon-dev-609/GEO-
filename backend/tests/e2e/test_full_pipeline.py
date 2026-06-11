# test_full_pipeline.py — E2E integration tests for the GEO pipeline

from __future__ import annotations
import sys, os, json
from unittest.mock import patch, MagicMock
_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest
from app.models.enums import SandtableType


class TestCleanDiagnosePipeline:
    """Clean → Diagnose chaining."""

    def test_pre_clean_removes_html(self):
        from app.core.cleaner import TextCleaner
        cleaner = TextCleaner.__new__(TextCleaner)
        result = cleaner._pre_clean("  <p>武汉微艺达提供智慧城市沙盘模型定制服务，精度0.1mm，服务200+项目。</p>  ")
        assert "<p>" not in result
        assert "武汉微艺达" in result

    def test_clean_then_diagnose(self):
        from app.core.cleaner import TextCleaner
        from app.core.diagnoser import ContentDiagnoser
        with patch("app.utils.config.load_settings", return_value={
            "system": {"enterprise_name": "测试企业", "enterprise_location": "武汉"}
        }):
            diagnoser = ContentDiagnoser(llm=None)

        cleaner = TextCleaner.__new__(TextCleaner)
        cleaned = cleaner._pre_clean("  <p>武汉微艺达提供智慧城市沙盘模型定制服务，精度0.1mm高精度。</p>  " * 3)
        assert len(cleaned) >= 50  # must pass diagnosis minimum

        result = diagnoser.diagnose_sync(cleaned)
        assert result["overall_score"] > 0


class TestJSONLDAllTypes:
    """All 8 sandtable types generate valid JSON-LD."""

    def test_all_types(self):
        from app.core.jsonld_gen import JSONLDGenerator
        gen = JSONLDGenerator()
        for st in SandtableType:
            result = gen.generate(
                sandtable_type=st,
                enterprise_info={"name": "测试企业", "url": "https://test.com"},
                product_info={"name": "测试产品"},
            )
            assert result["validation_passed"] is True
            ld = json.loads(result["json_ld_code"])
            assert "@graph" in ld
            assert len(ld["@graph"]) >= 2


class TestComplianceIntegration:
    """Compliance check on realistic text."""

    def test_clean_text_passes(self):
        from app.core.compliance import ComplianceChecker
        checker = ComplianceChecker()
        report = checker.check("武汉微艺达提供专业的沙盘模型定制服务，品质可靠值得信赖。")
        assert report.passed is True

    def test_problematic_text_fails(self):
        from app.core.compliance import ComplianceChecker
        checker = ComplianceChecker()
        report = checker.check("最好的沙盘模型，行业第一品牌。")
        assert report.passed is False
        assert report.violation_count > 0


class TestFullPipeline:
    """Complete 7-step pipeline simulation."""

    def test_full_pipeline(self):
        from app.core.cleaner import TextCleaner
        from app.core.diagnoser import ContentDiagnoser
        from app.core.jsonld_gen import JSONLDGenerator
        from app.core.compliance import ComplianceChecker
        from app.models.enums import SandtableType

        # Step 1: Import
        raw = "武汉微艺达智能科技有限公司提供智慧城市沙盘模型定制，精度0.1mm，服务200+项目。" * 3

        # Step 2: Clean
        cleaner = TextCleaner.__new__(TextCleaner)
        cleaned = cleaner._pre_clean(raw)
        assert len(cleaned) >= 50

        # Step 3: Diagnose
        with patch("app.utils.config.load_settings", return_value={
            "system": {"enterprise_name": "武汉微艺达智能科技有限公司", "enterprise_location": "武汉"}
        }):
            diagnoser = ContentDiagnoser(llm=None)
        diagnosis = diagnoser.diagnose_sync(cleaned)
        assert diagnosis["overall_score"] > 0

        # Step 4: Compliance
        checker = ComplianceChecker()
        compliance = checker.check(cleaned)
        assert isinstance(compliance.passed, bool)

        # Step 5: JSON-LD
        gen = JSONLDGenerator()
        jsonld = gen.generate(
            SandtableType.SMART_CITY,
            enterprise_info={"name": "武汉微艺达智能科技有限公司", "url": "https://weiyida.com"},
            product_info={"name": "智慧城市沙盘模型"},
        )
        assert jsonld["validation_passed"] is True

        # Step 6: Verify overall
        overall = diagnosis["overall_score"]
        assert 0 <= overall <= 100

        # Step 7: All passed
        assert len(cleaned) > 0
        assert compliance.violation_count >= 0
        assert jsonld["validation_passed"]
