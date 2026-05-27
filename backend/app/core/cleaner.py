"""文本智能清洗引擎 — 基于LLM语义理解的清洗+信息提取"""

from __future__ import annotations
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
        """清洗文本并返回结果"""
        start = time.perf_counter()

        # Step 1: 预清洗（HTML标签、特殊字符等基础清理）
        pre_cleaned = self._pre_clean(content)

        # Step 2: LLM语义清洗
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

        return {
            "original_text": content,
            "cleaned_text": cleaned.content.strip(),
            "word_count_before": len(content),
            "word_count_after": len(cleaned.content),
            "processing_time_ms": round(elapsed, 1),
        }

    async def extract_dimensions(
        self,
        content: str,
        enterprise_name: str = "武汉微艺达智能科技有限公司",
        enterprise_location: str = "武汉",
    ) -> dict:
        """提取五维关键信息"""
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

        return self._parse_extraction_json(resp.content)

    async def detect_type(self, content: str) -> SandtableType | None:
        """自动识别沙盘业务类型"""
        try:
            messages = [
                LLMMessage(role="user", content=TYPE_DETECTION_USER.format(content=content[:2000])),
            ]
            resp = await async_retry(self.llm.chat, messages, temperature=0.1, max_tokens=64)
            result = resp.content.strip()
            type_map = {t.label: t for t in SandtableType}
            return type_map.get(result)
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
