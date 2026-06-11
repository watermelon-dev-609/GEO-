# test_compliance.py — Unit tests for ComplianceChecker engine
#
# Tests cover:
# - All 6 forbidden word categories
# - Violation detection and context extraction
# - Risk level classification (none/low/medium/high)
# - check_quick() fast path
# - Custom blacklist
# - Edge cases (empty text, no violations)

from __future__ import annotations

import pytest
from app.core.compliance import (
    ComplianceChecker,
    ComplianceReport,
    Violation,
    AD_LAW_FORBIDDEN,
)


class TestComplianceCheckerInit:
    """Tests for ComplianceChecker initialization."""

    def test_default_init_has_all_categories(self):
        checker = ComplianceChecker()
        for cat in AD_LAW_FORBIDDEN:
            assert cat in checker.forbidden_words

    def test_custom_blacklist_added_as_category(self):
        checker = ComplianceChecker(custom_blacklist=["测试禁词", "违规词"])
        assert "自定义" in checker.forbidden_words
        assert checker.forbidden_words["自定义"] == ["测试禁词", "违规词"]

    def test_custom_blacklist_none_leaves_defaults(self):
        checker = ComplianceChecker(custom_blacklist=None)
        assert "自定义" not in checker.forbidden_words


class TestCheckBasic:
    """Tests for check() method basic functionality."""

    def test_empty_text_passes_with_zero_violations(self):
        checker = ComplianceChecker()
        report = checker.check("")
        assert report.passed is True
        assert report.violation_count == 0
        assert report.risk_level == "none"

    def test_clean_text_passes(self):
        checker = ComplianceChecker()
        report = checker.check("武汉微艺达智能科技有限公司提供专业的沙盘模型定制服务。")
        assert report.passed is True
        assert report.violation_count == 0

    def test_single_violation_detected(self):
        checker = ComplianceChecker()
        report = checker.check("这是最好的产品，提供第一的服务。")
        assert report.passed is False
        assert report.violation_count >= 1
        violations_words = [v["word"] for v in report.violations]
        assert "最好" in violations_words or "第一" in violations_words


class TestCheckCategories:
    """Tests that each forbidden word category is detected."""

    @pytest.mark.parametrize("word,category", [
        ("最好", "绝对化用语"),
        ("顶级", "绝对化用语"),
        ("第一品牌", "绝对化用语"),
        ("独一无二", "绝对化用语"),
        ("100%", "虚假承诺"),
        ("保证", "虚假承诺"),
        ("根治", "虚假承诺"),
        ("国家级", "国家级表述"),
        ("世界级", "国家级表述"),
    ])
    def test_category_matches(self, word, category):
        checker = ComplianceChecker()
        report = checker.check(f"这是一段包含{word}的测试文本。")
        assert report.passed is False
        found_categories = {v["category"] for v in report.violations if v["word"] == word}
        assert category in found_categories, f"Expected '{word}' to be in '{category}'"

    def test_authority_endorsement_words(self):
        checker = ComplianceChecker()
        report = checker.check("该产品获得政府推荐，并被央视推荐。")
        assert report.passed is False
        categories = {v["category"] for v in report.violations}
        assert "权威背书" in categories

    def test_financial_inducement_words(self):
        checker = ComplianceChecker()
        report = checker.check("零风险投资，稳赚不赔，高回报率。")
        assert report.passed is False
        categories = {v["category"] for v in report.violations}
        assert "金融诱导" in categories

    def test_time_limited_words(self):
        checker = ComplianceChecker()
        report = checker.check("最后一天特惠，限量100套。")
        assert report.passed is False
        categories = {v["category"] for v in report.violations}
        assert "时间限定" in categories


class TestRiskLevels:
    """Tests for risk level classification."""

    def test_no_violations_risk_none(self):
        checker = ComplianceChecker()
        report = checker.check("正常合规文本内容")
        assert report.risk_level == "none"

    def test_1_to_2_violations_risk_low(self):
        checker = ComplianceChecker()
        # 1-2 violations = low risk
        # Use custom blacklist to avoid overlap with built-in categories
        checker_single = ComplianceChecker(custom_blacklist=["测试词A", "测试词B"])
        report = checker_single.check("文本包含测试词A和测试词B共两个违规")
        assert report.violation_count == 2
        assert report.risk_level == "low"

    def test_3_to_7_violations_risk_medium(self):
        checker = ComplianceChecker()
        report = checker.check("最好 最大 最高 100%")
        assert report.risk_level == "medium"

    def test_8_or_more_violations_risk_high(self):
        checker = ComplianceChecker()
        text = "最 第一 唯一 独家 首个 首创 首选 顶级 极品 最佳"
        report = checker.check(text)
        assert report.risk_level == "high"


class TestCheckQuick:
    """Tests for check_quick() fast path."""

    def test_clean_text_returns_true(self):
        checker = ComplianceChecker()
        assert checker.check_quick("正常合规文本内容") is True

    def test_forbidden_word_returns_false(self):
        checker = ComplianceChecker()
        assert checker.check_quick("这是最好的产品") is False

    def test_empty_string_returns_true(self):
        checker = ComplianceChecker()
        assert checker.check_quick("") is True


class TestViolationContext:
    """Tests for violation context extraction."""

    def test_context_contains_surrounding_text(self):
        checker = ComplianceChecker()
        report = checker.check("武汉微艺达提供最好的沙盘模型定制服务。")
        violation = report.violations[0]
        assert "最好" in violation["context"]
        assert "context" in violation
        assert len(violation["context"]) > 0

    def test_position_is_correct(self):
        checker = ComplianceChecker()
        # Use a unique word to avoid substring overlap with other forbidden words
        checker_single = ComplianceChecker(custom_blacklist=["测试禁词XYZ"])
        report = checker_single.check("前缀文本一二三测试禁词XYZ后缀文本")
        violation = report.violations[0]
        # "前缀文本一二三" = 7 characters, so position = 7
        assert violation["position"] == 7
        assert "测试禁词XYZ" in violation["word"]

    def test_suggestion_provided(self):
        checker = ComplianceChecker()
        report = checker.check("这是最好的产品")
        violation = report.violations[0]
        assert "suggestion" in violation
        assert len(violation["suggestion"]) > 0


class TestComplianceReportDataclass:
    """Tests for ComplianceReport data class."""

    def test_to_dict_returns_expected_keys(self):
        report = ComplianceReport(passed=True, violation_count=0)
        d = report.to_dict()
        assert d["passed"] is True
        assert d["violation_count"] == 0
        assert d["risk_level"] == "none"
        assert isinstance(d["violations"], list)

    def test_to_dict_with_violations(self):
        report = ComplianceReport(
            passed=False,
            violation_count=2,
            violations=[{"word": "最好", "category": "绝对化用语"}],
            risk_level="low",
        )
        d = report.to_dict()
        assert d["passed"] is False
        assert d["violation_count"] == 2
        assert d["risk_level"] == "low"
        assert len(d["violations"]) == 1


class TestGetSuggestion:
    """Tests for _get_suggestion static method."""

    def test_known_category_returns_specific_suggestion(self):
        suggestion = ComplianceChecker._get_suggestion("绝对化用语", "最")
        assert "客观描述" in suggestion

    def test_unknown_category_returns_generic_suggestion(self):
        suggestion = ComplianceChecker._get_suggestion("未知类别", "测试词")
        assert "替换或删除" in suggestion
        assert "测试词" in suggestion


class TestEdgeCases:
    """Edge case tests for ComplianceChecker."""

    def test_repeated_violations_counted_separately(self):
        checker = ComplianceChecker()
        # Use a single-word custom blacklist to avoid substring overlap
        checker_single = ComplianceChecker(custom_blacklist=["禁词"])
        report = checker_single.check("禁词 禁词 禁词")
        assert report.violation_count == 3

    def test_english_text_does_not_crash(self):
        checker = ComplianceChecker()
        report = checker.check("This is the best product ever made.")
        assert report.passed is True
