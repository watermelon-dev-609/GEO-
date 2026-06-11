# test_diagnoser.py — Unit tests for ContentDiagnoser engine
#
# Tests cover:
# - Rule-based diagnosis (5 dimensions: entity, structure, quantified, FAQ, source)
# - Empty/short text handling
# - sync diagnose_sync()
# - async diagnose() with and without LLM
# - _parse_llm_response() JSON parsing

from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.diagnoser import ContentDiagnoser


SAMPLE_LONG_TEXT = """## 公司简介

武汉微艺达智能科技有限公司成立于2015年，位于武汉市东湖高新区。

公司专注于沙盘模型定制服务，已为200+个项目提供智慧交通、智慧城市沙盘解决方案。

## 服务能力

我们的沙盘模型采用高精度3D打印技术，精度可达0.1mm，支持动态仿真。

## 常见问题

什么是智慧交通沙盘？智慧交通沙盘是通过物联网技术实现交通流仿真...
如何定制沙盘模型？客户可根据需求定制尺寸、风格、功能。

公司拥有ISO9001质量认证，是国家高新技术企业。"""


@pytest.fixture
def diagnoser():
    """Fresh ContentDiagnoser with mocked config."""
    with patch("app.utils.config.load_settings", return_value={
        "system": {"enterprise_name": "武汉微艺达智能科技有限公司", "enterprise_location": "武汉"}
    }):
        return ContentDiagnoser(llm=None)


@pytest.fixture
def diagnoser_with_llm(mock_llm_adapter):
    """ContentDiagnoser with mock LLM."""
    with patch("app.utils.config.load_settings", return_value={
        "system": {"enterprise_name": "武汉微艺达智能科技有限公司", "enterprise_location": "武汉"}
    }):
        return ContentDiagnoser(llm=mock_llm_adapter)


class TestEmptyAndShort:
    """Tests for empty/short text handling."""

    def test_empty_text_returns_zero(self, diagnoser):
        result = diagnoser.diagnose_sync("")
        assert result["overall_score"] == 0
        assert result["top_issues"] == ["文本过短，无法诊断"]

    def test_short_text_under_50_chars(self, diagnoser):
        result = diagnoser.diagnose_sync("短文本")
        assert result["overall_score"] == 0
        assert "文本过短" in result["top_issues"][0]

    def test_whitespace_only(self, diagnoser):
        result = diagnoser.diagnose_sync("   \n  \t  ")
        assert result["overall_score"] == 0

    def test_exactly_50_chars_passes(self, diagnoser):
        text = "A" * 50
        result = diagnoser.diagnose_sync(text)
        assert result["overall_score"] > 0


class TestRuleDiagnose:
    """Tests for _rule_diagnose() method."""

    def test_returns_all_five_dimensions(self, diagnoser):
        result = diagnoser.diagnose_sync(SAMPLE_LONG_TEXT)
        dims = result["dimensions"]
        assert "entity_completeness" in dims
        assert "structure_quality" in dims
        assert "quantified_data" in dims
        assert "faq_friendliness" in dims
        assert "source_credibility" in dims

    def test_returns_text_stats(self, diagnoser):
        result = diagnoser.diagnose_sync(SAMPLE_LONG_TEXT)
        stats = result["text_stats"]
        assert "length" in stats
        assert stats["length"] > 0
        assert "paragraphs" in stats
        assert "quant_data_count" in stats

    def test_overall_score_between_0_and_100(self, diagnoser):
        result = diagnoser.diagnose_sync(SAMPLE_LONG_TEXT)
        assert 0 <= result["overall_score"] <= 100

    def test_entity_completeness_detects_company(self, diagnoser):
        result = diagnoser.diagnose_sync(SAMPLE_LONG_TEXT)
        entity = result["dimensions"]["entity_completeness"]
        assert entity["score"] >= 85  # has company + location + product keywords

    def test_entity_missing_company_detected(self, diagnoser):
        text = "沙盘模型定制服务，提供高精度3D打印。" * 3  # no company name
        result = diagnoser.diagnose_sync(text)
        entity = result["dimensions"]["entity_completeness"]
        assert entity["score"] < 85  # should be lower without company

    def test_structure_detects_h2(self, diagnoser):
        result = diagnoser.diagnose_sync(SAMPLE_LONG_TEXT)
        struct = result["dimensions"]["structure_quality"]
        assert struct["score"] >= 70  # has H2 headers

    def test_structure_missing_h2(self, diagnoser):
        text = "这是一段没有任何标题标记的纯文本内容。段落很长很长很长很长。" * 5
        result = diagnoser.diagnose_sync(text)
        struct = result["dimensions"]["structure_quality"]
        # No H2 headers → base score, may still get points from paragraph length
        assert struct["score"] <= 80

    def test_quantified_data_detected(self, diagnoser):
        result = diagnoser.diagnose_sync(SAMPLE_LONG_TEXT)
        quant = result["dimensions"]["quantified_data"]
        # SAMPLE has 200+项目, 0.1mm, etc.
        assert result["text_stats"]["quant_data_count"] >= 2

    def test_quantified_data_missing(self, diagnoser):
        text = "我们提供优质的沙盘模型定制服务，团队经验丰富，品质值得信赖。" * 3
        result = diagnoser.diagnose_sync(text)
        quant = result["dimensions"]["quantified_data"]
        assert quant["score"] <= 55  # missing quant data

    def test_faq_detected(self, diagnoser):
        result = diagnoser.diagnose_sync(SAMPLE_LONG_TEXT)
        faq = result["dimensions"]["faq_friendliness"]
        assert result["text_stats"]["qa_patterns"] > 0

    def test_source_credibility_exaggerated(self, diagnoser):
        text = "全球领先的沙盘模型制造商，行业第一品牌，最专业的定制服务。" * 2
        result = diagnoser.diagnose_sync(text)
        source = result["dimensions"]["source_credibility"]
        assert source["score"] < 70  # penalized for exaggerated claims

    def test_source_credibility_clean(self, diagnoser):
        text = "专业沙盘模型定制服务商，提供多种规格的沙盘模型和解决方案。" * 3
        result = diagnoser.diagnose_sync(text)
        source = result["dimensions"]["source_credibility"]
        assert source["score"] >= 70  # no exaggerated claims

    def test_top_issues_below_50_flag(self, diagnoser):
        text = "简单的沙盘模型描述而已没有详细信息。" * 3  # need 50+ chars
        result = diagnoser.diagnose_sync(text)
        low_dims = [
            k for k, v in result["dimensions"].items()
            if v["score"] < 50
        ]
        assert len(result["top_issues"]) <= min(len(low_dims), 3)

    def test_diagnosis_mode_is_rule(self, diagnoser):
        result = diagnoser.diagnose_sync(SAMPLE_LONG_TEXT)
        assert result["diagnosis_mode"] == "rule"


class TestLLMDiagnose:
    """Tests for async diagnose() with LLM."""

    @pytest.mark.asyncio
    async def test_llm_result_merged(self, diagnoser_with_llm, mock_llm_response):
        diag = diagnoser_with_llm
        diag.llm.chat.return_value = mock_llm_response(
            '```json\n{"overall_assessment": "good", "suggestions": ["improve SEO"]}\n```'
        )
        result = await diag.diagnose(SAMPLE_LONG_TEXT)
        assert "llm_analysis" in result
        assert result["llm_analysis"]["overall_assessment"] == "good"

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_rule(self, diagnoser_with_llm):
        diag = diagnoser_with_llm
        diag.llm.chat.side_effect = Exception("LLM API error")
        result = await diag.diagnose(SAMPLE_LONG_TEXT)
        # Should still return rule-based result
        assert "llm_analysis" not in result
        assert result["diagnosis_mode"] == "rule"
        assert result["overall_score"] > 0

    @pytest.mark.asyncio
    async def test_short_text_short_circuits_even_with_llm(self, diagnoser_with_llm):
        diag = diagnoser_with_llm
        result = await diag.diagnose("短文本")
        assert result["overall_score"] == 0
        # LLM should NOT have been called
        diag.llm.chat.assert_not_called()


class TestParseLLMResponse:
    """Tests for _parse_llm_response()."""

    def test_valid_json_in_fence(self, diagnoser):
        content = '```json\n{"score": 85, "issues": ["a", "b"]}\n```'
        result = diagnoser._parse_llm_response(content)
        assert result["score"] == 85
        assert result["issues"] == ["a", "b"]

    def test_valid_json_bare(self, diagnoser):
        content = '{"score": 90, "note": "good"}'
        result = diagnoser._parse_llm_response(content)
        assert result["score"] == 90

    def test_invalid_json_returns_none(self, diagnoser):
        result = diagnoser._parse_llm_response("not json at all")
        assert result is None

    def test_empty_string_returns_none(self, diagnoser):
        result = diagnoser._parse_llm_response("")
        assert result is None

    def test_plain_text_with_json_object(self, diagnoser):
        content = '这里有一些分析文字 {"score": 75}'
        result = diagnoser._parse_llm_response(content)
        assert result["score"] == 75


class TestDiagnoseSync:
    """Tests for diagnose_sync (pure rule-based)."""

    def test_no_llm_needed(self, diagnoser):
        result = diagnoser.diagnose_sync(SAMPLE_LONG_TEXT)
        assert result["overall_score"] > 0
        assert "llm_analysis" not in result

    def test_returns_top_issues_sorted(self, diagnoser):
        text = "简单的描述。"
        result = diagnoser.diagnose_sync(text)
        assert isinstance(result["top_issues"], list)
        assert len(result["top_issues"]) <= 3

    def test_paragraph_stats(self, diagnoser):
        result = diagnoser.diagnose_sync(SAMPLE_LONG_TEXT)
        stats = result["text_stats"]
        assert stats["paragraphs"] >= 2
        assert stats["avg_paragraph_length"] > 0
