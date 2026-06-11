"""GEO文案重构引擎 — 批量调度LLM、流式生成、后处理校验"""

from __future__ import annotations
import asyncio
import hashlib
import logging
import time
from typing import AsyncIterator
from dataclasses import dataclass

from app.models.enums import SandtableType, AIPlatform
from app.models.schemas import PlatformRewriteResult
from app.services.llm.base import BaseLLMAdapter, LLMMessage, LLMFactory
from app.prompts.rewrite import build_geo_prompt, get_sandtable_profile, get_platform_rules
from app.utils.retry import async_retry


def _get_platform_max_tokens(platform: AIPlatform) -> int:
    """根据平台字数目标计算 max_tokens（输出截断控制）

    中文约1.5 token/字，按字数上限×1.8 留安全余量。
    这是硬截断——LLM 输出达到此长度会自动停止。
    """
    limits = {
        AIPlatform.DEEPSEEK: 4000,   # 2200字×1.8≈3960
        AIPlatform.KIMI: 4000,       # 2200字×1.8≈3960
        AIPlatform.CLAUDE: 4500,     # 2500字×1.8=4500
        AIPlatform.DOUBAO: 2200,     # 1200字×1.8≈2160
        AIPlatform.WENXIN: 2700,     # 1500字×1.8=2700
        AIPlatform.TONGYI: 2700,
        AIPlatform.XINGHUO: 2700,
        AIPlatform.YUANBAO: 2700,
        AIPlatform.OPENAI: 4096,     # 通用
        AIPlatform.OLLAMA: 4096,
        AIPlatform.LMSTUDIO: 4096,
    }
    return limits.get(platform, 4096)


def _get_platform_max_chars(platform: AIPlatform) -> int:
    """平台字数硬上限（用于输出截断兜底）"""
    limits = {
        AIPlatform.DEEPSEEK: 2300,
        AIPlatform.KIMI: 2300,
        AIPlatform.CLAUDE: 2600,
        AIPlatform.DOUBAO: 1300,
        AIPlatform.WENXIN: 1600,
        AIPlatform.TONGYI: 1600,
        AIPlatform.XINGHUO: 1600,
        AIPlatform.YUANBAO: 1600,
    }
    return limits.get(platform, 2000)


def _truncate_to_platform_limit(text: str, platform: AIPlatform) -> str:
    """字数超限时在最近的段落/句子边界截断"""
    max_chars = _get_platform_max_chars(platform)
    if len(text) <= max_chars:
        return text

    # 尝试在段落边界截断（\n\n）
    truncated = text[:max_chars]
    last_para = truncated.rfind('\n\n')
    if last_para > max_chars * 0.7:  # 段落边界在70%位置之后才用
        return truncated[:last_para].rstrip()

    # 尝试在句子边界截断（。！？）
    for punct in ['。', '！', '？']:
        last_sent = truncated.rfind(punct)
        if last_sent > max_chars * 0.6:
            return truncated[:last_sent + 1]

    return truncated.rstrip()
from app.utils.cache import geo_cache
from app.utils.config import load_settings, load_api_keys, get_enterprise_name, get_enterprise_location

logger = logging.getLogger(__name__)


@dataclass
class RewriteTask:
    """单次重构任务"""
    platform: AIPlatform
    adapter: BaseLLMAdapter


class GEORewriter:
    """GEO文案重构引擎"""

    def __init__(self):
        self.settings = load_settings()
        self.api_keys = load_api_keys()

    def _get_adapter(self, platform: AIPlatform) -> BaseLLMAdapter:
        """获取指定平台的LLM适配器"""
        plat_key = platform.value
        key_info = self.api_keys.get("platforms", {}).get(plat_key, {})
        plat_cfg = self.settings.get("llm", {}).get("platforms", {}).get(plat_key, {})

        api_key = key_info.get("api_key", "")
        if not api_key or "your-" in api_key:
            raise ValueError(f"平台 {platform.label} 未配置API Key，请在 config/api_keys.yaml 中配置")

        adapter = LLMFactory.create(
            platform=platform.adapter_type,
            api_key=api_key,
            model_name=plat_cfg.get("model_name", ""),
            base_url=plat_cfg.get("base_url"),
        )
        if platform.adapter_type == "wenxin":
            adapter.secret_key = key_info.get("secret_key", "")
        return adapter

    async def rewrite(
        self,
        cleaned_text: str,
        sandtable_type: SandtableType,
        platforms: list[AIPlatform],
        dimensions: dict | None = None,
        optimization_hints: list[str] | None = None,
        competitor_insights: str | None = None,
        optimization_rules: dict | None = None,
        enterprise_name: str | None = None,
        enterprise_location: str | None = None,
    ) -> list[PlatformRewriteResult]:
        """批量重构：对多个平台并行生成优化文案"""
        if not enterprise_name:
            enterprise_name = get_enterprise_name()
        if not enterprise_location:
            enterprise_location = get_enterprise_location()
        start = time.perf_counter()
        tasks = []

        # 如果没有显式传入竞品洞察，尝试自动加载
        if competitor_insights is None:
            competitor_insights = self._auto_load_competitor_insights(sandtable_type)

        for platform in platforms:
            cache_key = f"{sandtable_type.value}:{platform.value}:{hashlib.md5(cleaned_text.encode()).hexdigest()}"
            cached = geo_cache.get(cache_key)
            if cached:
                tasks.append(self._return_cached(cached, platform))
            else:
                tasks.append(self._rewrite_one(
                    cleaned_text, sandtable_type, platform,
                    dimensions, optimization_hints, competitor_insights,
                    optimization_rules,
                    enterprise_name, enterprise_location, cache_key,
                ))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"{platforms[i].label} 生成失败: {result}")
                output.append(PlatformRewriteResult(
                    platform=platforms[i],
                    optimized_text="",
                    strategy_notes=f"生成失败: {str(result)}",
                    word_count=0,
                    error=str(result),
                ))
            else:
                output.append(result)

        return output

    async def _rewrite_one(
        self,
        cleaned_text: str,
        sandtable_type: SandtableType,
        platform: AIPlatform,
        dimensions: dict | None,
        optimization_hints: list[str] | None,
        competitor_insights: str | None,
        optimization_rules: dict | None,
        enterprise_name: str,
        enterprise_location: str,
        cache_key: str,
    ) -> PlatformRewriteResult:
        """对单个平台生成优化文案"""
        try:
            adapter = self._get_adapter(platform)
        except ValueError as e:
            return PlatformRewriteResult(
                platform=platform,
                optimized_text="",
                strategy_notes=str(e),
                word_count=0,
                error=str(e),
            )

        system_prompt, user_message = build_geo_prompt(
            sandtable_type=sandtable_type.value,
            platform=platform.value,
            enterprise_name=enterprise_name,
            enterprise_location=enterprise_location,
            dimensions=dimensions,
            optimization_hints=optimization_hints,
            competitor_insights=competitor_insights,
            optimization_rules=optimization_rules,
        )

        # 五维信息也补充到user_message中
        dims_text = ""
        if dimensions:
            dims_text = "\n\n## 参考素材（五维关键信息）\n"
            for key, val in dimensions.items():
                if val:
                    dims_text += f"- {key}: {'; '.join(val)}\n"
        full_user = f"{user_message}\n\n原始文案：\n{cleaned_text}{dims_text}"

        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=full_user),
        ]

        max_tokens = _get_platform_max_tokens(platform)
        resp = await async_retry(adapter.chat, messages, temperature=0.7, max_tokens=max_tokens)

        # 后处理校验
        validated_text, warnings = self._validate_output(
            resp.content, sandtable_type, platform, enterprise_name, enterprise_location
        )

        strategy = self._build_strategy_notes(platform, sandtable_type)
        if warnings:
            strategy += "\n\n⚠️ 内容质量提醒：\n" + "\n".join(f"- {w}" for w in warnings)

        result = PlatformRewriteResult(
            platform=platform,
            optimized_text=validated_text,
            strategy_notes=strategy,
            word_count=len(validated_text),
        )

        # 写入缓存
        geo_cache.set(cache_key, result.model_dump())

        return result

    async def stream_rewrite(
        self,
        cleaned_text: str,
        sandtable_type: SandtableType,
        platform: AIPlatform,
        dimensions: dict | None = None,
        optimization_hints: list[str] | None = None,
        competitor_insights: str | None = None,
        optimization_rules: dict | None = None,
        enterprise_name: str | None = None,
        enterprise_location: str | None = None,
    ) -> AsyncIterator[dict]:
        """流式生成单平台文案（SSE）"""
        if not enterprise_name:
            enterprise_name = get_enterprise_name()
        if not enterprise_location:
            enterprise_location = get_enterprise_location()
        adapter = self._get_adapter(platform)

        system_prompt, user_message = build_geo_prompt(
            sandtable_type=sandtable_type.value,
            platform=platform.value,
            enterprise_name=enterprise_name,
            enterprise_location=enterprise_location,
            dimensions=dimensions,
            optimization_hints=optimization_hints,
            competitor_insights=competitor_insights,
            optimization_rules=optimization_rules,
        )

        dims_text = ""
        if dimensions:
            dims_text = "\n\n## 参考素材（五维关键信息）\n"
            for key, val in dimensions.items():
                if val:
                    val_items = val if isinstance(val, list) else [str(val)]
                    dims_text += f"- {key}: {'; '.join(val_items)}\n"

        full_user = f"{user_message}\n\n原始文案：\n{cleaned_text}{dims_text}"

        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=full_user),
        ]

        # 先发送平台和策略信息
        profile = get_sandtable_profile(sandtable_type.value)
        rules = get_platform_rules(platform.value)
        yield {
            "type": "meta",
            "platform": platform.value,
            "platform_name": rules["name"],
            "strategy": rules["strategy"],
            "sandtable_label": profile["industry"],
        }

        # 流式输出正文
        full_text = ""
        max_tokens = _get_platform_max_tokens(platform)
        async for token in adapter.stream_chat(messages, temperature=0.7, max_tokens=max_tokens):
            full_text += token
            yield {"type": "token", "content": token}

        # 后处理校验
        validated_text, warnings = self._validate_output(
            full_text, sandtable_type, platform, enterprise_name, enterprise_location
        )

        # 完成后输出策略说明
        strategy = self._build_strategy_notes(platform, sandtable_type)
        if warnings:
            strategy += "\n\n⚠️ 内容质量提醒：\n" + "\n".join(f"- {w}" for w in warnings)

        yield {
            "type": "done",
            "full_text": validated_text,
            "word_count": len(validated_text),
            "strategy_notes": strategy,
        }

    async def _return_cached(self, cached_data: dict, platform: AIPlatform) -> PlatformRewriteResult:
        """返回缓存结果"""
        return PlatformRewriteResult(**cached_data)

    def _auto_load_competitor_insights(self, sandtable_type: SandtableType) -> str | None:
        """自动加载最新竞品对比摘要作为差异化洞察"""
        import json
        from pathlib import Path
        from app.utils.config import get_data_dir
        comp_dir = get_data_dir() / "competitors"
        if not comp_dir.exists():
            return None
        comp_files = sorted(comp_dir.glob("*.json"))
        if not comp_files:
            return None
        try:
            with open(comp_files[-1], "r", encoding="utf-8") as f:
                latest = json.load(f)
            name = latest.get("name", "未知竞品")
            sandtable = latest.get("sandtable_type", "")
            features = latest.get("content_features", {})
            if not features:
                return None
            insights = f"竞品「{name}」（{sandtable}）内容特征分析：\n"
            for key, val in features.items():
                insights += f"- {key}: {val}\n"
            insights += "\n请在生成文案时主动体现与以上竞品的差异化优势。"
            return insights
        except Exception as e:
            logger.warning(f"加载竞品洞察失败: {e}")
            return None

    def _validate_output(
        self,
        text: str,
        sandtable_type: SandtableType,
        platform: AIPlatform,
        enterprise_name: str,
        enterprise_location: str = "",
    ) -> tuple[str, list[str]]:
        """输出校验 — 检查关键信息完整性，不达标自动补充

        校验项：
        1. 企业名称是否完整出现（缺失则自动补充到文首）
        2. 地域标识是否存在
        3. 量化数据是否达标（数字+单位模式）
        4. 五维信息是否全覆盖
        5. 无冗余、无堆砌、无违规表述
        """
        import re
        warnings = []

        # 校验项1：企业名称是否完整出现（缺失则自动补充）
        if enterprise_name not in text:
            text = f"**{enterprise_name}**\n\n{text}"
            warnings.append("企业名称缺失，已自动补充到文首")

        # 校验项2：地域标识是否存在
        if enterprise_location and enterprise_location not in text:
            warnings.append(f"地域标识'{enterprise_location}'未在文中出现")

        # 校验项3：量化数据是否达标（数字+单位模式，如"200个项目""1:1000""15年"）
        quant_patterns = [
            r'\d+[+]?\s*(个|项|套|年|㎡|平方米|公里|人|次|万元|亿)',
            r'\d+[:：]\d+',  # 比例
            r'\d+%',         # 百分比
            r'\d+\.\d+\s*(mm|cm|m|km)',  # 精度单位
        ]
        has_quantified = any(re.search(p, text) for p in quant_patterns)
        if not has_quantified:
            warnings.append("文中未检测到量化数据（数字+单位），AI引用算法对数字信号敏感度更高")

        # 校验项4：五维信息是否全覆盖
        from app.core.dimensions_shared import DIMENSION_COVERAGE_KEYWORDS
        missing = []
        for dim, keywords in DIMENSION_COVERAGE_KEYWORDS.items():
            if not any(kw in text for kw in keywords):
                missing.append(dim)
        if missing:
            warnings.append(f"可能缺失维度: {', '.join(missing)}")

        if warnings:
            logger.warning(f"[{sandtable_type.label} × {platform.label}] 输出校验警告: {'; '.join(warnings)}")

        # 校验项5：字数上限硬截断（LLM 经常忽略 prompt 中的字数约束，此处兜底）
        text = _truncate_to_platform_limit(text, platform)

        return text, warnings

    def _build_strategy_notes(self, platform: AIPlatform, sandtable_type: SandtableType) -> str:
        """生成优化策略说明"""
        rules = get_platform_rules(platform.value)
        profile = get_sandtable_profile(sandtable_type.value)

        notes = f"## 优化策略说明\n\n"
        notes += f"**目标平台**：{rules['name']}\n"
        notes += f"**优化策略**：{rules['strategy']}\n"
        notes += f"**文风要求**：{rules['style']}\n"
        notes += f"**业务类型**：{profile['industry']}\n"
        notes += f"**内容基调**：{profile['tone']}\n\n"
        notes += "**具体优化措施**：\n"
        for i, rule in enumerate(rules['rules'], 1):
            notes += f"{i}. {rule}\n"

        return notes
