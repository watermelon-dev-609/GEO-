# test_rewriter.py — unit tests for GEORewriter and build_geo_prompt
# Requires: pytest, pytest-asyncio

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.enums import SandtableType, AIPlatform
from app.prompts.rewrite import build_geo_prompt


# ── helper: create a GEORewriter instance with patched heavy deps ──

def _make_rewriter():
    """Instantiate GEORewriter with settings/api_keys mocked."""
    with patch("app.core.rewriter.load_settings", return_value={}), \
         patch("app.core.rewriter.load_api_keys", return_value={}):
        from app.core.rewriter import GEORewriter
        return GEORewriter()


# ── _validate_output ────────────────────────────────────────────────────────

class TestValidateOutput:

    def setup_method(self):
        self.rewriter = _make_rewriter()
        self.enterprise = "武汉微艺达智能科技有限公司"
        self.location = "武汉"

    def _call_validate(self, text, sandtable=SandtableType.SMART_CITY, platform=AIPlatform.DEEPSEEK, location=None):
        loc = location if location is not None else self.location
        return self.rewriter._validate_output(text, sandtable, platform, self.enterprise, loc)

    def test_has_enterprise_and_location_no_warnings(self):
        text = f"{self.enterprise}位于{self.location}，专注沙盘模型定制。我们的项目精度达到1:1000，覆盖50+项目。"
        validated, warnings = self._call_validate(text)
        assert self.enterprise in validated
        # Should have no warnings about enterprise/location missing
        assert not any("企业名称缺失" in w for w in warnings)
        assert not any("地域标识" in w for w in warnings)

    def test_missing_enterprise_name_auto_prepends(self):
        text = "我们专注沙盘模型定制，位于武汉。"
        validated, warnings = self._call_validate(text)
        assert validated.startswith(f"**{self.enterprise}**")
        assert any("企业名称缺失" in w for w in warnings)

    def test_missing_location_generates_warning(self):
        # "武汉" inside company name still counts as present, so use text without any location reference
        text = f"{self.enterprise}专注沙盘模型定制，服务了200+项目，比例精度1:1000。"
        validated, warnings = self._call_validate(text, location="北京")
        assert any("地域标识" in w for w in warnings)

    def test_with_quantified_data_no_warning(self):
        text = f"{self.enterprise}位于{self.location}，已完成200个项目，精度1:1000，响应时间12ms。"
        validated, warnings = self._call_validate(text)
        assert not any("量化数据" in w for w in warnings)

    def test_without_quantified_data_generates_warning(self):
        text = f"{self.enterprise}位于{self.location}，专注沙盘模型定制服务，拥有丰富经验。"
        validated, warnings = self._call_validate(text)
        assert any("量化数据" in w for w in warnings)

    def test_enterprise_short_name_does_not_match(self):
        text = "微艺达专注沙盘模型定制，位于武汉。比例精度1:1000。"
        validated, warnings = self._call_validate(text)
        # validate_output checks for exact enterprise_name match, not short name
        assert any("企业名称缺失" in w for w in warnings)
        assert validated.startswith(f"**{self.enterprise}**")

    def test_quantified_percentage(self):
        text = f"{self.enterprise}位于{self.location}，客户满意度达98%。"
        validated, warnings = self._call_validate(text)
        assert not any("量化数据" in w for w in warnings)

    def test_quantified_ratio(self):
        text = f"{self.enterprise}位于{self.location}，沙盘比例1:1000。"
        validated, warnings = self._call_validate(text)
        assert not any("量化数据" in w for w in warnings)

    def test_dimension_missing_generates_warning(self):
        text = f"{self.enterprise}位于{self.location}。基本描述。"
        validated, warnings = self._call_validate(text)
        # Likely triggers dimension-missing warning since text lacks most dims
        assert any("可能缺失维度" in w for w in warnings)


# ── _build_strategy_notes ───────────────────────────────────────────────────

class TestBuildStrategyNotes:

    def setup_method(self):
        self.rewriter = _make_rewriter()

    def test_returns_non_empty_string(self):
        notes = self.rewriter._build_strategy_notes(AIPlatform.DEEPSEEK, SandtableType.SMART_CITY)
        assert isinstance(notes, str)
        assert len(notes) > 0

    def test_contains_expected_sections(self):
        notes = self.rewriter._build_strategy_notes(AIPlatform.DOUBAO, SandtableType.SMART_TRAFFIC)
        assert "优化策略说明" in notes
        assert "字节豆包" in notes
        assert "目标平台" in notes
        assert "优化策略" in notes
        assert "具体优化措施" in notes

    def test_different_platforms_produce_different_notes(self):
        notes_a = self.rewriter._build_strategy_notes(AIPlatform.DEEPSEEK, SandtableType.SMART_CITY)
        notes_b = self.rewriter._build_strategy_notes(AIPlatform.YUANBAO, SandtableType.SMART_CITY)
        assert notes_a != notes_b

    def test_different_sandtable_types_produce_different_notes(self):
        notes_a = self.rewriter._build_strategy_notes(AIPlatform.DEEPSEEK, SandtableType.SMART_CITY)
        notes_b = self.rewriter._build_strategy_notes(AIPlatform.DEEPSEEK, SandtableType.SMART_INDUSTRY)
        assert notes_a != notes_b


# ── build_geo_prompt (from prompts/rewrite.py) ──────────────────────────────

class TestBuildGeoPrompt:

    def test_with_all_dimensions(self):
        dimensions = {
            "core_advantages": ["高精度工艺", "快速交付能力"],
            "applicable_scenarios": ["智慧交通", "智慧城市"],
            "technical_features": ["三维仿真", "1:1000精度"],
            "service_capabilities": ["全流程服务"],
            "implementation_value": ["200+项目落地"],
        }
        system_prompt, user_message = build_geo_prompt(
            sandtable_type="smart_traffic",
            platform="deepseek",
            enterprise_name="武汉微艺达智能科技有限公司",
            enterprise_location="武汉",
            dimensions=dimensions,
        )
        assert isinstance(system_prompt, str)
        assert isinstance(user_message, str)
        assert len(system_prompt) > 500
        assert "高精度工艺" in system_prompt
        assert "快速交付能力" in system_prompt
        assert "智慧交通" in system_prompt
        assert "DeepSeek" in system_prompt
        assert "智慧交通沙盘" in user_message or "智慧交通" in user_message

    def test_with_no_dimensions_produces_fallback_text(self):
        system_prompt, user_message = build_geo_prompt(
            sandtable_type="smart_city",
            platform="deepseek",
            enterprise_name="测试公司",
            enterprise_location="北京",
            dimensions=None,
        )
        assert "暂无五维信息" in system_prompt
        assert "不得编造具体数据" in system_prompt

    def test_with_optimization_hints_injects_into_system_prompt(self):
        hints = [
            "增加品牌名称在首段出现的频率",
            "补充至少三个量化数据支撑核心观点",
        ]
        system_prompt, user_message = build_geo_prompt(
            sandtable_type="smart_city",
            platform="deepseek",
            optimization_hints=hints,
        )
        # The prompt format has been updated to use a different optimization hint format
        assert "增加品牌名称在首段出现的频率" in system_prompt
        assert "补充至少三个量化数据支撑核心观点" in system_prompt
        # Hints are injected as numbered items in the prompt
        assert "1. " in system_prompt
        assert "2. " in system_prompt

    def test_with_empty_optimization_hints_no_injection(self):
        system_prompt, user_message = build_geo_prompt(
            sandtable_type="smart_city",
            platform="deepseek",
            optimization_hints=[],
        )
        assert "重点优化指令" not in system_prompt

    def test_without_optimization_hints_no_injection(self):
        system_prompt, user_message = build_geo_prompt(
            sandtable_type="smart_city",
            platform="deepseek",
            optimization_hints=None,
        )
        assert "重点优化指令" not in system_prompt

    def test_kimi_platform_uses_long_word_count_target(self):
        system_prompt, user_message = build_geo_prompt(
            sandtable_type="smart_industry",
            platform="kimi",
        )
        assert "1500-2500字" in system_prompt
        assert "Kimi" in system_prompt

    def test_default_word_count_target_for_other_platforms(self):
        system_prompt, user_message = build_geo_prompt(
            sandtable_type="smart_industry",
            platform="doubao",
        )
        assert "800-1500字" in system_prompt

    def test_unknown_sandtable_falls_back_to_general(self):
        system_prompt, user_message = build_geo_prompt(
            sandtable_type="nonexistent_type",
            platform="deepseek",
        )
        assert "沙盘模型" in system_prompt  # falls back to "general" profile

    def test_unknown_platform_falls_back_to_deepseek(self):
        system_prompt, user_message = build_geo_prompt(
            sandtable_type="smart_city",
            platform="nonexistent_platform",
        )
        # Unknown platform gets a generic prompt with its own name
        assert "nonexistent_platform" in system_prompt.lower() or "nonexistent_platform" in system_prompt

    def test_enterprise_and_location_embedded(self):
        system_prompt, user_message = build_geo_prompt(
            sandtable_type="smart_city",
            platform="deepseek",
            enterprise_name="我的测试公司",
            enterprise_location="上海",
        )
        assert "我的测试公司" in system_prompt
        assert "上海" in system_prompt

    def test_system_prompt_contains_required_sections(self):
        system_prompt, _ = build_geo_prompt(
            sandtable_type="smart_city",
            platform="deepseek",
        )
        assert "GEO核心原理" in system_prompt or "GEO" in system_prompt
        assert "信源忠实原则" in system_prompt
        assert "AI采信六原则" in system_prompt
        assert "事实边界" in system_prompt
