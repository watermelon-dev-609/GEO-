"""文本智能清洗引擎 — 基于LLM语义理解的清洗+信息提取"""

from __future__ import annotations
import hashlib
import json
import logging
import time
from app.models.enums import SandtableType
from app.services.llm.base import LLMMessage
from app.prompts.cleaning import (
    CLEANING_SYSTEM_PROMPT, CLEANING_USER_TEMPLATE,
    EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_TEMPLATE,
    TYPE_DETECTION_PROMPT, TYPE_DETECTION_USER,
)
from app.utils.retry import async_retry
from app.utils.cache import geo_cache
from app.utils.config import get_enterprise_name, get_enterprise_location

logger = logging.getLogger(__name__)


class TextCleaner:
    """文本智能清洗引擎"""

    def __init__(self, llm_adapter):
        self.llm = llm_adapter

    async def clean(
        self,
        content: str,
        sandtable_type: SandtableType | None = None,
    ) -> dict:
        """清洗文本并返回结果（带缓存）"""
        start = time.perf_counter()

        input_error = self._validate_input(content)
        if input_error:
            return {
                "original_text": content,
                "cleaned_text": input_error,
                "word_count_before": len(content),
                "word_count_after": len(input_error),
                "processing_time_ms": 0,
            }

        st_key = sandtable_type.value if sandtable_type else "auto"
        cache_key = f"clean:{st_key}:{hashlib.md5(content.encode()).hexdigest()}"
        cached = geo_cache.get(cache_key)
        if cached:
            return cached

        pre_cleaned = self._pre_clean(content)

        sandtable_label = sandtable_type.label if sandtable_type else "待自动识别"
        messages = [
            LLMMessage(role="system", content=CLEANING_SYSTEM_PROMPT),
            LLMMessage(role="user", content=CLEANING_USER_TEMPLATE.format(
                content=pre_cleaned,
                sandtable_type=sandtable_label,
            )),
        ]

        cleaned = await async_retry(
            self.llm.chat,
            messages,
            temperature=0.3,
            max_tokens=4096,
        )
        elapsed = (time.perf_counter() - start) * 1000

        result = {
            "original_text": content,
            "cleaned_text": cleaned.content.strip(),
            "word_count_before": len(content),
            "word_count_after": len(cleaned.content),
            "processing_time_ms": round(elapsed, 1),
        }
        geo_cache.set(cache_key, result)
        return result

    async def extract_dimensions(
        self,
        content: str,
        enterprise_name: str | None = None,
        enterprise_location: str | None = None,
    ) -> dict:
        """提取五维关键信息（带缓存）"""
        if enterprise_name is None:
            enterprise_name = get_enterprise_name()
        if enterprise_location is None:
            enterprise_location = get_enterprise_location()
        cache_key = f"extract:{hashlib.md5(content.encode()).hexdigest()}"
        cached = geo_cache.get(cache_key)
        if cached:
            return cached
        messages = [
            LLMMessage(role="system", content=EXTRACTION_SYSTEM_PROMPT),
            LLMMessage(role="user", content=EXTRACTION_USER_TEMPLATE.format(
                content=content,
                enterprise_name=enterprise_name,
                enterprise_location=enterprise_location,
            )),
        ]

        resp = await async_retry(
            self.llm.chat,
            messages,
            temperature=0.2,
            max_tokens=2048,
        )

        result = self._parse_extraction_json(resp.content)
        geo_cache.set(cache_key, result)
        return result

    async def detect_type(self, content: str) -> SandtableType | None:
        """自动识别沙盘业务类型（带缓存）"""
        cache_key = f"detect_type:{hashlib.md5(content[:2000].encode()).hexdigest()}"
        cached = geo_cache.get(cache_key)
        if cached is not None:
            return SandtableType(cached) if cached else None
        try:
            messages = [
                LLMMessage(role="user", content=TYPE_DETECTION_USER.format(content=content[:2000])),
            ]
            resp = await async_retry(self.llm.chat, messages, temperature=0.1, max_tokens=64)
            result = resp.content.strip()
            type_map = {t.label: t for t in SandtableType}
            detected = type_map.get(result)
            geo_cache.set(cache_key, detected.value if detected else None)
            return detected
        except Exception as e:
            logger.warning(f"业务类型自动识别失败: {e}")
            return None

    def _pre_clean(self, text: str) -> str:
        """基础预清洗（不依赖LLM）"""
        import re
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        # 移除过多空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 统一中文标点
        text = text.replace('　', ' ')
        # 移除零宽字符
        text = re.sub(r'[​‌‍‎‏﻿]', '', text)
        return text.strip()

    def _validate_input(self, text: str) -> str | None:
        """校验输入内容是否包含有效信息，无效返回错误信息"""
        import re
        stripped = re.sub(r'\s+', '', text)
        if len(stripped) < 10:
            return "输入内容过短，请提供至少10个有效字符的企业/产品描述"
        chinese_chars = len(re.findall(r'[一-鿿]', stripped))
        total_chars = len(stripped)
        if total_chars == 0 or chinese_chars / max(total_chars, 1) < 0.05:
            return "未检测到有效中文内容，请输入企业或产品的中文描述"
        xss_patterns = [
            r'<script[\s>]', r'javascript\s*:', r'onerror\s*=', r'onload\s*=',
            r'<iframe', r'<object', r'<embed',
        ]
        for pat in xss_patterns:
            if re.search(pat, text, re.IGNORECASE):
                return "检测到可疑代码注入，请提供正常的企业描述文本"
        return None

    def _parse_extraction_json(self, raw: str) -> dict:
        """解析LLM返回的五维信息JSON"""
        try:
            json_match = raw
            if "```json" in raw:
                json_match = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                json_match = raw.split("```")[1].split("```")[0]
            data = json.loads(json_match.strip())
            return {
                "core_advantages": data.get("core_advantages", []),
                "applicable_scenarios": data.get("applicable_scenarios", []),
                "technical_features": data.get("technical_features", []),
                "service_capabilities": data.get("service_capabilities", []),
                "implementation_value": data.get("implementation_value", []),
                "key_phrases": data.get("key_phrases", []),
            }
        except (json.JSONDecodeError, IndexError, KeyError):
            logger.warning("五维信息JSON解析失败，使用原始返回")
            return {
                "core_advantages": [],
                "applicable_scenarios": [],
                "technical_features": [],
                "service_capabilities": [],
                "implementation_value": [],
                "key_phrases": [],
                "_raw": raw,
            }
