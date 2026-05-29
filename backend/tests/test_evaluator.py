# test_evaluator.py — unit tests for AIEvaluator
# Requires: pytest, pytest-asyncio

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.enums import SandtableType, UserRole
from app.services.llm.base import LLMResponse


# ── helper: create an AIEvaluator instance with patched heavy dependencies ──

def _make_evaluator(llm_adapter=None):
    """Instantiate AIEvaluator with all heavy constructor dependencies mocked out."""
    with patch("app.core.evaluator.load_settings", return_value={}), \
         patch("app.core.evaluator.load_api_keys", return_value={}), \
         patch("app.core.evaluator.EmbeddingService", autospec=True), \
         patch("app.core.evaluator.VectorStore", autospec=True):
        from app.core.evaluator import AIEvaluator
        return AIEvaluator(llm_adapter=llm_adapter)


# ── _extract_score ──────────────────────────────────────────────────────────

class TestExtractScore:

    def setup_method(self):
        self.evaluator = _make_evaluator()

    def test_chinese_colon_format(self):
        assert self.evaluator._extract_score("评分：85") == 85.0

    def test_chinese_bare_colon_format(self):
        assert self.evaluator._extract_score("评分: 93") == 93.0

    def test_english_score_label(self):
        assert self.evaluator._extract_score("score: 72") == 72.0

    def test_english_score_label_with_colon_chinese(self):
        assert self.evaluator._extract_score("score： 47") == 47.0

    def test_chinese_fen_suffix(self):
        assert self.evaluator._extract_score("90分") == 90.0

    def test_slash_100_format(self):
        assert self.evaluator._extract_score("65/100") == 65.0

    def test_no_score_text_returns_default(self):
        assert self.evaluator._extract_score("这是一段没有任何评分的普通文本") == 60.0

    def test_empty_string_returns_default(self):
        assert self.evaluator._extract_score("") == 60.0

    def test_score_embedded_in_long_text(self):
        text = "综合来看，该文本在结构化程度方面表现良好。评分：88。其他方面也有不错的表现。"
        assert self.evaluator._extract_score(text) == 88.0


# ── _analyze_citation ───────────────────────────────────────────────────────

class TestAnalyzeCitation:

    def setup_method(self):
        self.evaluator = _make_evaluator()

    def test_answer_contains_source_entities(self):
        source = (
            "武汉微艺达智能科技有限公司专注沙盘模型定制，位于武汉。"
            "服务超过200个项目，采用高精度仿真技术，比例精度1:1000。"
        )
        answer = (
            "武汉微艺达智能科技有限公司是一家沙盘模型厂家，"
            "他们使用高精度仿真技术，比例精度1:1000。"
        )
        score = self.evaluator._analyze_citation(answer, source)
        # Multiple source entities should be found in the answer
        assert score > 0.3
        assert score <= 1.0

    def test_answer_has_no_overlap(self):
        source = "武汉微艺达智能科技有限公司专注沙盘模型定制。比例精度1:1000。"
        answer = "我不知道，没有相关信息。这是一家做食品的公司。"
        score = self.evaluator._analyze_citation(answer, source)
        assert score == 0.0

    def test_empty_source_returns_zero(self):
        score = self.evaluator._analyze_citation("anything", "")
        assert score == 0.0

    def test_empty_answer_returns_zero(self):
        source = "武汉微艺达智能科技有限公司"
        score = self.evaluator._analyze_citation("", source)
        assert score == 0.0

    def test_partial_overlap(self):
        source = "武汉微艺达智能科技有限公司沙盘模型定制。200+项目落地。"
        answer = "微艺达做过沙盘模型，有很多项目。"
        score = self.evaluator._analyze_citation(answer, source)
        assert score > 0.0
        assert score < 1.0


# ── _generate_questions ─────────────────────────────────────────────────────

class TestGenerateQuestions:

    def setup_method(self):
        self.evaluator = _make_evaluator()

    def test_with_valid_sandtable_and_single_role(self):
        questions = self.evaluator._generate_questions(
            sandtable_type=SandtableType.SMART_TRAFFIC,
            user_roles=[UserRole.B_END_PROCUREMENT],
            custom_questions=None,
        )
        assert len(questions) > 0
        # All questions should contain the sandtable label or its parts
        assert all("智慧交通" in q or "沙盘" in q for q in questions)

    def test_custom_questions_included(self):
        custom = ["自定义问题一", "自定义问题二"]
        questions = self.evaluator._generate_questions(
            sandtable_type=SandtableType.SMART_CITY,
            user_roles=[],
            custom_questions=custom,
        )
        assert "自定义问题一" in questions
        assert "自定义问题二" in questions
        assert len(questions) == 2

    def test_duplicate_dedup(self):
        custom = ["重复问题"]
        questions = self.evaluator._generate_questions(
            sandtable_type=SandtableType.SMART_INDUSTRY,
            user_roles=[],  # no role questions
            custom_questions=custom + custom,  # intentional duplicate
        )
        assert questions == ["重复问题"]

    def test_multiple_roles(self):
        questions = self.evaluator._generate_questions(
            sandtable_type=SandtableType.SMART_LOGISTICS,
            user_roles=[UserRole.TECHNICAL_SELECTION, UserRole.GENERAL_CONSULTANT],
            custom_questions=None,
        )
        # Should include questions from both roles
        assert len(questions) > 5

    def test_question_template_still_valid(self):
        """Verify {type} in question templates is replaced, not left as literal."""
        questions = self.evaluator._generate_questions(
            sandtable_type=SandtableType.MILITARY_TERRAIN,
            user_roles=[UserRole.B_END_PROCUREMENT],
            custom_questions=None,
        )
        for q in questions:
            assert "{type}" not in q


# ── _diagnose_v2 ────────────────────────────────────────────────────────────

class TestDiagnoseV2:

    def setup_method(self):
        self.evaluator = _make_evaluator()

    def test_all_good_no_weak_points(self):
        scores = {
            "brand_recall": 85,
            "solution_match": 80,
            "advantage_citation": 75,
            "structure_quality": 70,
            "differentiation": 65,
            "real_citation": 78,
            "source_consistency": 90,
        }
        weak, suggs = self.evaluator._diagnose_v2(scores, SandtableType.SMART_CITY)
        assert any("表现良好" in w for w in weak)
        assert any("持续监控" in s for s in suggs)

    def test_brand_recall_below_60_generates_weak_point(self):
        scores = {
            "brand_recall": 45,
            "solution_match": 80,
            "advantage_citation": 75,
            "structure_quality": 70,
            "differentiation": 65,
            "real_citation": 78,
            "source_consistency": 90,
        }
        weak, suggs = self.evaluator._diagnose_v2(scores, SandtableType.SMART_TRAFFIC)
        assert any("品牌召回" in w for w in weak)
        assert any("品牌名" in s or "微艺达" in s for s in suggs)

    def test_source_consistency_below_30_inserts_warning_at_position_0(self):
        scores = {
            "brand_recall": 85,
            "solution_match": 80,
            "advantage_citation": 75,
            "structure_quality": 70,
            "differentiation": 65,
            "real_citation": 78,
            "source_consistency": 25,
        }
        weak, suggs = self.evaluator._diagnose_v2(scores, SandtableType.SMART_INDUSTRY)
        # The source_consistency < 30 warning should be at position 0
        assert "信源一致性严重偏低" in weak[0]
        assert any("返回GEO工坊" in s for s in suggs)

    def test_multiple_dimensions_below_60(self):
        scores = {
            "brand_recall": 40,
            "solution_match": 55,
            "advantage_citation": 75,
            "structure_quality": 70,
            "differentiation": 65,
            "real_citation": 78,
            "source_consistency": 90,
        }
        weak, suggs = self.evaluator._diagnose_v2(scores, SandtableType.MILITARY_TERRAIN)
        assert any("品牌召回" in w for w in weak)
        assert any("方案匹配" in w for w in weak)


# ── _calculate_overall_v2 ──────────────────────────────────────────────────

class TestCalculateOverallV2:

    def setup_method(self):
        self.evaluator = _make_evaluator()

    def test_all_seven_dimensions_present(self):
        components = {
            "brand_recall": 80,
            "solution_match": 80,
            "advantage_citation": 80,
            "real_citation": 80,
            "structure_quality": 80,
            "differentiation": 80,
            "source_consistency": 80,
            "eeat_score": 80,
        }
        score = self.evaluator._calculate_overall_v2(components)
        assert score == 80.0

    def test_only_three_dimensions_present(self):
        components = {
            "brand_recall": 70,
            "solution_match": 80,
            "advantage_citation": 90,
        }
        score = self.evaluator._calculate_overall_v2(components)
        # 3 dims with 8-dim weights: 70*0.18 + 80*0.18 + 90*0.14 = 39.6
        assert 39 <= score <= 40

    def test_source_consistency_below_30_capped_at_50(self):
        components = {
            "brand_recall": 95,
            "solution_match": 95,
            "advantage_citation": 95,
            "real_citation": 95,
            "structure_quality": 95,
            "differentiation": 95,
            "source_consistency": 20,
        }
        score = self.evaluator._calculate_overall_v2(components)
        assert score <= 50.0

    def test_source_consistency_exactly_30_not_capped(self):
        components = {
            "brand_recall": 95,
            "solution_match": 95,
            "advantage_citation": 95,
            "real_citation": 95,
            "structure_quality": 95,
            "differentiation": 95,
            "source_consistency": 30,
        }
        score = self.evaluator._calculate_overall_v2(components)
        assert score > 50.0  # Should NOT be capped at exactly 30

    def test_all_zero_scores(self):
        components = {
            "brand_recall": 0,
            "solution_match": 0,
            "advantage_citation": 0,
            "real_citation": 0,
            "structure_quality": 0,
            "differentiation": 0,
            "source_consistency": 0,
        }
        score = self.evaluator._calculate_overall_v2(components)
        assert score == 0.0


# ── evaluate() — empty / short text boundary ────────────────────────────────

class TestEvaluateEmptyText:

    @pytest.mark.asyncio
    async def test_empty_text_returns_overall_zero(self):
        evaluator = _make_evaluator()
        result = await evaluator.evaluate(
            optimized_text="",
            sandtable_type=SandtableType.SMART_CITY,
        )
        assert result["overall_score"] == 0
        assert result["total_time_ms"] == 0
        assert result["questions_used"] == 0
        assert len(result["weak_points"]) >= 1
        assert any("过短" in w for w in result["weak_points"])

    @pytest.mark.asyncio
    async def test_text_shorter_than_50_chars_returns_overall_zero(self):
        evaluator = _make_evaluator()
        result = await evaluator.evaluate(
            optimized_text="短文本",
            sandtable_type=SandtableType.SMART_CITY,
        )
        assert result["overall_score"] == 0
        assert any("过短" in w for w in result["weak_points"])

    @pytest.mark.asyncio
    async def test_whitespace_only_text_returns_overall_zero(self):
        evaluator = _make_evaluator()
        result = await evaluator.evaluate(
            optimized_text="     \n  \n   ",
            sandtable_type=SandtableType.SMART_CITY,
        )
        assert result["overall_score"] == 0
