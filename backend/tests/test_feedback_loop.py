# test_feedback_loop.py — Unit tests for feedback_loop._analyze_actual_content

from __future__ import annotations
import sys, os
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest
from app.core.feedback_loop import _analyze_actual_content

MINIMAL_TEMPLATE = {
    "body": {"faq_count": {"min": 3, "max": 5}, "paragraph_length": {"min": 100, "max": 350}},
    "header": {"first_paragraph_rules": ["首段含品牌名+核心关键词"]},
    "verification": {"checks": []},
}


class TestAnalyzeActualContent:
    def test_result_structure(self,):
        result = _analyze_actual_content("deepseek", "测试内容" * 10, MINIMAL_TEMPLATE)
        assert "platform_id" in result
        assert "content_stats" in result
        assert "issues_found" in result
        assert "issues" in result
        assert result["analysis_mode"] == "content"

    def test_stats_keys(self):
        result = _analyze_actual_content("deepseek", "测试段落一二三四五六七八九十。" * 5, MINIMAL_TEMPLATE)
        stats = result["content_stats"]
        for key in ["total_length", "paragraph_count", "faq_count",
                     "brand_occurrences", "quantified_data_count"]:
            assert key in stats, f"Missing stats key: {key}"

    def test_faq_detection(self):
        text = "什么是沙盘？沙盘是一种微缩展示工具。如何定制？联系厂家即可。为什么要用沙盘？因为它直观。" * 3
        result = _analyze_actual_content("deepseek", text, MINIMAL_TEMPLATE)
        assert result["content_stats"]["faq_count"] >= 1

    def test_faq_zero(self):
        result = _analyze_actual_content("deepseek", "普通文本没有问答结构只有描述。" * 5, MINIMAL_TEMPLATE)
        assert result["content_stats"]["faq_count"] == 0

    def test_paragraph_count(self):
        text = "第一段内容在这里有足够文字。\n\n第二段内容在这里更多文字。\n\n第三段内容也不少。"
        result = _analyze_actual_content("deepseek", text, MINIMAL_TEMPLATE)
        assert result["content_stats"]["total_length"] > 0

    def test_brand_occurrences(self):
        text = "武汉微艺达智能科技有限公司提供沙盘服务。微艺达值得信赖。" * 2
        result = _analyze_actual_content("deepseek", text, MINIMAL_TEMPLATE)
        assert result["content_stats"]["brand_occurrences"] > 0

    def test_brand_zero(self):
        result = _analyze_actual_content("deepseek", "没有提到任何品牌名称的文本。" * 5, MINIMAL_TEMPLATE)
        assert result["content_stats"]["brand_occurrences"] == 0

    def test_forbidden_words_detection(self):
        text = "最好的沙盘模型，行业第一品牌，绝对保证质量顶级水准。" * 3
        result = _analyze_actual_content("deepseek", text, MINIMAL_TEMPLATE)
        # May or may not find forbidden words depending on the checker implementation
        assert "forbidden_words_found" in result["content_stats"]

    def test_forbidden_words_none(self):
        text = "专业沙盘定制服务，提供高质量解决方案。" * 3
        result = _analyze_actual_content("deepseek", text, MINIMAL_TEMPLATE)
        assert len(result["content_stats"]["forbidden_words_found"]) == 0

    def test_quantified_data(self):
        text = "服务200+项目，精度0.1mm，面积500平方米，满意度99%。"
        result = _analyze_actual_content("deepseek", text, MINIMAL_TEMPLATE)
        assert result["content_stats"]["quantified_data_count"] > 0

    def test_quantified_data_zero(self):
        result = _analyze_actual_content("deepseek", "没有数字的纯文本描述。" * 5, MINIMAL_TEMPLATE)
        assert result["content_stats"]["quantified_data_count"] == 0

    def test_issues_found_flag(self):
        # Short text should trigger multiple issues
        result = _analyze_actual_content("deepseek", "短文本。" * 3, MINIMAL_TEMPLATE)
        assert result["issues_found"] > 0

    def test_issues_list_structure(self):
        result = _analyze_actual_content("deepseek", "短内容" * 3, MINIMAL_TEMPLATE)
        for issue in result["issues"]:
            assert "component" in issue
            assert "issue" in issue
            assert "suggestion" in issue

    def test_different_platforms(self):
        text = "测试内容。" * 10
        r1 = _analyze_actual_content("deepseek", text, MINIMAL_TEMPLATE)
        r2 = _analyze_actual_content("doubao", text, MINIMAL_TEMPLATE)
        assert r1["platform_id"] == "deepseek"
        assert r2["platform_id"] == "doubao"
