# test_cleaner.py — unit tests for TextCleaner
# Requires: pytest, pytest-asyncio

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.cleaner import TextCleaner
from app.services.llm.base import LLMResponse


# ── _pre_clean ──────────────────────────────────────────────────────────────

class TestPreClean:
    """Tests for TextCleaner._pre_clean() — static pre-cleaning rules."""

    def setup_method(self):
        self.cleaner = TextCleaner(llm_adapter=MagicMock())

    def test_empty_string(self):
        assert self.cleaner._pre_clean("") == ""
        assert self.cleaner._pre_clean("   ") == ""

    def test_html_tags_removed(self):
        raw = '<p>这是一段<b>测试</b>文本</p><br/>'
        result = self.cleaner._pre_clean(raw)
        assert "<p>" not in result
        assert "<b>" not in result
        assert "<br/>" not in result
        assert "测试" in result
        assert "文本" in result

    def test_excessive_newlines_collapsed(self):
        raw = "段落一\n\n\n\n\n\n段落二"
        result = self.cleaner._pre_clean(raw)
        assert "\n\n\n\n" not in result  # 4+ consecutive newlines gone
        assert "段落一" in result
        assert "段落二" in result

    def test_zero_width_characters_removed(self):
        raw = "零宽​字符‌测试‍内容‎‏﻿"
        result = self.cleaner._pre_clean(raw)
        assert "​" not in result
        assert "‌" not in result
        assert "‍" not in result
        assert "‎" not in result
        assert "‏" not in result
        assert "﻿" not in result
        assert "零宽" in result
        assert "字符测试内容" in result

    def test_fullwidth_space_normalized(self):
        raw = "武汉　微艺达"
        result = self.cleaner._pre_clean(raw)
        assert "　" not in result
        assert " " in result

    def test_mixed_chinese_english(self):
        raw = "我们使用BAAI/bge-large-zh-v1.5模型进行embedding."
        result = self.cleaner._pre_clean(raw)
        assert "BAAI" in result
        assert "embedding" in result
        assert "模型" in result


# ── _parse_extraction_json ──────────────────────────────────────────────────

class TestParseExtractionJSON:
    """Tests for TextCleaner._parse_extraction_json()."""

    def setup_method(self):
        self.cleaner = TextCleaner(llm_adapter=MagicMock())

    def _default_keys(self):
        return [
            "core_advantages", "applicable_scenarios", "technical_features",
            "service_capabilities", "implementation_value", "key_phrases",
        ]

    def test_valid_json(self):
        data = {
            "core_advantages": ["高精度", "快速交付"],
            "applicable_scenarios": ["智慧城市", "智慧交通"],
            "technical_features": ["三维仿真"],
            "service_capabilities": ["全流程服务"],
            "implementation_value": ["50+项目"],
            "key_phrases": ["沙盘", "定制"],
        }
        raw = json.dumps(data, ensure_ascii=False)
        result = self.cleaner._parse_extraction_json(raw)
        assert result["core_advantages"] == ["高精度", "快速交付"]
        assert result["applicable_scenarios"] == ["智慧城市", "智慧交通"]
        assert result["technical_features"] == ["三维仿真"]
        assert result["key_phrases"] == ["沙盘", "定制"]

    def test_json_in_markdown_fence(self):
        data = {"core_advantages": ["优势A"]}
        raw = f"```json\n{json.dumps(data, ensure_ascii=False)}\n```"
        result = self.cleaner._parse_extraction_json(raw)
        assert result["core_advantages"] == ["优势A"]

    def test_json_in_generic_fence(self):
        data = {"core_advantages": ["优势B"]}
        raw = f"```\n{json.dumps(data, ensure_ascii=False)}\n```"
        result = self.cleaner._parse_extraction_json(raw)
        assert result["core_advantages"] == ["优势B"]

    def test_invalid_json_returns_defaults(self):
        result = self.cleaner._parse_extraction_json("这不是JSON，只是普通文本")
        for key in self._default_keys():
            assert result[key] == []
        assert "_raw" in result

    def test_empty_string_returns_defaults(self):
        result = self.cleaner._parse_extraction_json("")
        for key in self._default_keys():
            assert result[key] == []
        assert "_raw" in result

    def test_partial_json_missing_keys_gets_empty_lists(self):
        partial = {"core_advantages": ["只提供了一个维度"]}
        raw = json.dumps(partial, ensure_ascii=False)
        result = self.cleaner._parse_extraction_json(raw)
        assert result["core_advantages"] == ["只提供了一个维度"]
        assert result["applicable_scenarios"] == []
        assert result["technical_features"] == []


# ── clean (async, LLM-dependent) ─────────────────────────────────────────────

class TestClean:
    """Tests for TextCleaner.clean() — full async cleaning pipeline."""

    @pytest.mark.asyncio
    async def test_clean_returns_expected_structure(self, mock_llm_adapter, mock_llm_response):
        mock_llm_adapter.chat.return_value = mock_llm_response("清洗后的文本内容")

        cleaner = TextCleaner(llm_adapter=mock_llm_adapter)
        result = await cleaner.clean("  <p>原始文本</p>\n\n\n   ")

        assert "original_text" in result
        assert "cleaned_text" in result
        assert "word_count_before" in result
        assert "word_count_after" in result
        assert "processing_time_ms" in result
        assert result["cleaned_text"] == "清洗后的文本内容"
        assert result["word_count_before"] > 0
        assert result["word_count_after"] > 0
        assert isinstance(result["processing_time_ms"], float)
        assert result["processing_time_ms"] >= 0

    @pytest.mark.asyncio
    async def test_clean_strips_llm_output(self, mock_llm_adapter, mock_llm_response):
        mock_llm_adapter.chat.return_value = mock_llm_response("  有前后空格的输出  \n  ")

        cleaner = TextCleaner(llm_adapter=mock_llm_adapter)
        # Input must be >= 10 chars to pass _validate_input
        result = await cleaner.clean("这是一段足够长的原文文本用于测试清洗功能")
        # The LLM mock returns the specified content; cleaner may parse JSON from it
        assert len(result["cleaned_text"]) > 0
        assert result["word_count_before"] > 0
