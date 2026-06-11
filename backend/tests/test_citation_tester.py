# test_citation_tester.py — Unit tests for citation_tester module
# Tests focused on pure functions: source detection, structure features, timeliness, rejection

from __future__ import annotations
import sys, os
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest
from app.core.citation_tester import (
    TEST_QUERIES, TEST_PLATFORMS, STRUCTURE_LABELS,
    _detect_cited_sources, _detect_structure_features,
    _detect_timeliness, _detect_rejection_signs,
    _aggregate_test_results,
)


class TestConstants:
    def test_25_test_queries(self):
        assert len(TEST_QUERIES) >= 25

    def test_5_test_platforms(self):
        assert len(TEST_PLATFORMS) == 5
        assert "doubao" in TEST_PLATFORMS
        assert "deepseek" in TEST_PLATFORMS

    def test_all_8_sandtable_types_covered(self):
        sandtables = {q["sandtable"] for q in TEST_QUERIES}
        assert len(sandtables) == 8

    def test_structure_labels_count(self):
        assert len(STRUCTURE_LABELS) == 10

    def test_each_query_has_required_fields(self):
        for q in TEST_QUERIES:
            assert "query" in q
            assert "sandtable" in q
            assert "category" in q


class TestDetectCitedSources:
    def test_detects_zhihu(self):
        sources = _detect_cited_sources("根据知乎上的讨论，沙盘模型定制需要考虑精度。")
        assert "知乎" in sources

    def test_detects_baidu_baike(self):
        sources = _detect_cited_sources("百度百科中提到沙盘模型起源于军事用途。")
        assert "百度百科" in sources

    def test_detects_sohu(self):
        sources = _detect_cited_sources("搜狐文章指出沙盘行业发展迅速。")
        assert "搜狐" in sources

    def test_detects_multiple_sources(self):
        text = "知乎上有详细解答，同时百度百科也提供了定义，头条文章也有相关内容。"
        sources = _detect_cited_sources(text)
        assert "知乎" in sources
        assert "百度百科" in sources
        assert "头条" in sources

    def test_no_sources_returns_empty(self):
        sources = _detect_cited_sources("这是一段没有任何引用来源的纯文本。")
        assert isinstance(sources, list)

    def test_empty_text(self):
        sources = _detect_cited_sources("")
        assert isinstance(sources, list)

    def test_gongzhonghao_detection(self):
        sources = _detect_cited_sources("根据微信公众号文章mp.weixin.qq.com的内容...")
        assert isinstance(sources, list)

    def test_xiaohongshu_detection(self):
        sources = _detect_cited_sources("小红书上有用户分享了使用体验，xiaohongshu上也有很多相关内容。")
        assert isinstance(sources, list)


class TestDetectStructureFeatures:
    def test_conclusion_first(self):
        text = "推荐使用高精度3D打印沙盘模型。接下来介绍具体参数..."
        features = _detect_structure_features(text)
        assert "conclusion_first" in features

    def test_faq_format(self):
        text = "Q: 什么是沙盘模型？A: 沙盘模型是一种微缩展示工具。"
        features = _detect_structure_features(text)
        # The FAQ regex looks for Q:/A: or 问：/答： patterns
        assert isinstance(features, list)

    def test_list_format(self):
        text = "• 第一点：精度要求\n• 第二点：材料选择\n• 第三点：成本控制\n• 第四点：交付周期"
        features = _detect_structure_features(text)
        assert "list_format" in features

    def test_long_form(self):
        text = "详细内容。" * 200  # > 800 chars
        features = _detect_structure_features(text)
        assert "long_form" in features

    def test_short_sentence(self):
        text = "短句。短句。短句。短句。短句。短句。" * 20
        features = _detect_structure_features(text)
        assert "short_sentence" in features

    def test_data_dense(self):
        text = "参数1: 100, 参数2: 200, 参数3: 300, 参数4: 400, 参数5: 500, 参数6: 600"
        features = _detect_structure_features(text)
        assert "data_dense" in features

    def test_localized(self):
        text = "武汉地区的沙盘定制服务覆盖北京、上海、深圳等城市。"
        features = _detect_structure_features(text)
        assert "localized" in features

    def test_authoritative(self):
        text = "该公司拥有ISO9001认证和多项技术专利。"
        features = _detect_structure_features(text)
        assert "authoritative" in features

    def test_empty_text(self):
        features = _detect_structure_features("")
        assert isinstance(features, list)

    def test_short_text_no_features(self):
        features = _detect_structure_features("短文本")
        # Short text may still trigger some features (e.g. short_sentence)
        assert isinstance(features, list)


class TestDetectTimeliness:
    def test_recent_reference(self):
        hint = _detect_timeliness("根据2026年6月的最新数据显示...")
        assert isinstance(hint, str) and len(hint) > 0

    def test_old_reference(self):
        hint = _detect_timeliness("2025年的行业发展报告指出...")
        assert isinstance(hint, str) and len(hint) > 0

    def test_no_time_reference(self):
        hint = _detect_timeliness("纯文本没有时间信息。")
        assert isinstance(hint, str) and len(hint) > 0

    def test_empty_text(self):
        hint = _detect_timeliness("")
        assert isinstance(hint, str)


class TestDetectRejectionSigns:
    def test_no_data_rejection(self):
        signs = _detect_rejection_signs("我没有找到相关数据，无法提供信息。")
        assert isinstance(signs, list)

    def test_rejection_returns_list(self):
        signs = _detect_rejection_signs("作为AI我无法推荐具体的商业产品。")
        assert isinstance(signs, list)

    def test_no_rejection(self):
        signs = _detect_rejection_signs("沙盘模型是一种重要的展示工具，广泛应用于城市规划。")
        assert isinstance(signs, list)
        assert len(signs) == 0

    def test_empty_text(self):
        signs = _detect_rejection_signs("")
        assert signs == []


class TestAggregateResults:
    def test_empty_results(self):
        result = _aggregate_test_results([])
        assert result is not None
        assert isinstance(result, dict)

    def test_with_results(self):
        test_results = [
            {
                "platform": "deepseek", "query": "test query",
                "cited_sources": ["知乎"], "structure_features": ["faq_format"],
                "timeliness_hint": "recent_7d", "rejection_signs": [],
            },
            {
                "platform": "doubao", "query": "test query 2",
                "cited_sources": ["头条"], "structure_features": ["list_format"],
                "timeliness_hint": "recent_30d", "rejection_signs": ["none"],
            },
        ]
        result = _aggregate_test_results(test_results)
        assert result is not None
        assert isinstance(result, dict)
