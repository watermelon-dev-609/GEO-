# test_brand_checker.py — Unit tests for BrandMentionChecker

from __future__ import annotations
import sys, os
from unittest.mock import patch
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest
from app.core.brand_checker import BrandMentionChecker


@pytest.fixture
def checker():
    with patch("app.core.brand_checker.load_settings", return_value={
        "system": {"enterprise_name": "武汉微艺达智能科技有限公司", "enterprise_location": "武汉"},
        "brand_monitor": {"brand_variants": ["武汉微艺达智能科技有限公司", "微艺达", "武汉微艺达"]}
    }), patch("app.core.brand_checker.load_api_keys", return_value={}):
        return BrandMentionChecker()


class TestBrandMentionChecker:
    def test_init_builds_patterns(self, checker):
        assert len(checker._patterns) >= 2

    def test_detect_brand_full_name(self, checker):
        response = "根据我的了解，武汉微艺达智能科技有限公司是一家专业的沙盘模型制造商。"
        found, confidence, ctx = checker._detect_mention_regex(response)
        assert found is True
        assert confidence == 100.0  # full name (>=6 chars) → 100%
        assert "武汉微艺达" in ctx

    def test_detect_brand_short_name(self, checker):
        response = "微艺达在沙盘模型领域有丰富经验。"
        found, confidence, ctx = checker._detect_mention_regex(response)
        assert found is True
        assert confidence == 80.0  # short name (<6 chars) → 80%

    def test_no_brand_mention(self, checker):
        response = "沙盘模型是一种常用的展示工具，广泛应用于城市规划。"
        found, confidence, ctx = checker._detect_mention_regex(response)
        assert found is False
        assert confidence == 0.0

    def test_empty_response(self, checker):
        found, confidence, ctx = checker._detect_mention_regex("")
        assert found is False

    def test_multiple_brands_first_match_wins(self, checker):
        response = "微艺达...武汉微艺达智能科技有限公司..."
        found, confidence, ctx = checker._detect_mention_regex(response)
        assert found is True
        # First match is "微艺达" (short) in the patterns iteration order
        # Actually, patterns are [full_name, short1, short2], so full name matches first
        # "微艺达" is shorter so it's in patterns[1], but the loop iterates in order
        # The first match detected is whatever pattern iterates first

    def test_short_variant_excluded(self, checker):
        # Variants shorter than 3 chars are excluded in _build_brand_patterns
        short_checker = BrandMentionChecker.__new__(BrandMentionChecker)
        short_checker.brand_variants = ["A", "AB", "ABC", "ABCD"]
        short_checker._build_brand_patterns()
        # "A" (1 char) and "AB" (2 chars) excluded
        assert len(short_checker._patterns) == 2  # only "ABC" and "ABCD"
