"""GEO文案重构引擎 — 批量调度LLM、流式生成、后处理校验"""

from __future__ import annotations
import asyncio
import logging
import time
from typing import AsyncIterator
from dataclasses import dataclass

from app.models.enums import SandtableType, AIPlatform
from app.models.schemas import PlatformRewriteResult
from app.services.llm.base import BaseLLMAdapter, LLMMessage, LLMFactory
from app.prompts.rewrite import build_geo_prompt, get_sandtable_profile, get_platform_rules
from app.utils.retry import async_retry
from app.utils.cache import geo_cache
from app.utils.config import load_settings, load_api_keys

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
        enterprise_name: str = "武汉微艺达智能科技有限公司",
        enterprise_location: str = "武汉",
    ) -> list[PlatformRewriteResult]:
        """批量重构：对多个平台并行生成优化文案"""
        start = time.perf_counter()
        tasks = []

        for platform in platforms:
            cache_key = f"{sandtable_type.value}:{platform.value}:{hash(cleaned_text)}"
            cached = geo_cache.get(cache_key)
            if cached:
                tasks.append(self._return_cached(cached, platform))
            else:
                tasks.append(self._rewrite_one(
                    cleaned_text, sandtable_type, platform,
                    dimensions, optimization_hints, enterprise_name, enterprise_location, cache_key,
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
            )

        system_prompt, user_message = build_geo_prompt(
            sandtable_type=sandtable_type.value,
            platform=platform.value,
            enterprise_name=enterprise_name,
            enterprise_location=enterprise_location,
            dimensions=dimensions,
            optimization_hints=optimization_hints,
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

        resp = await async_retry(adapter.chat, messages, temperature=0.7, max_tokens=4096)

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
        enterprise_name: str = "武汉微艺达智能科技有限公司",
        enterprise_location: str = "武汉",
    ) -> AsyncIterator[dict]:
        """流式生成单平台文案（SSE）"""
        adapter = self._get_adapter(platform)

        system_prompt, user_message = build_geo_prompt(
            sandtable_type=sandtable_type.value,
            platform=platform.value,
            enterprise_name=enterprise_name,
            enterprise_location=enterprise_location,
            dimensions=dimensions,
            optimization_hints=optimization_hints,
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
        async for token in adapter.stream_chat(messages, temperature=0.7, max_tokens=4096):
            full_text += token
            yield {"type": "token", "content": token}

        # 完成后输出策略说明
        strategy = self._build_strategy_notes(platform, sandtable_type)
        yield {
            "type": "done",
            "full_text": full_text,
            "word_count": len(full_text),
            "strategy_notes": strategy,
        }

    async def _return_cached(self, cached_data: dict, platform: AIPlatform) -> PlatformRewriteResult:
        """返回缓存结果"""
        return PlatformRewriteResult(**cached_data)

    def _validate_output(
        self,
        text: str,
        sandtable_type: SandtableType,
        platform: AIPlatform,
        enterprise_name: str,
        enterprise_location: str = "武汉",
    ) -> tuple[str, list[str]]:
        """后处理校验 — 检查关键信息完整性，返回 (修正后文本, 警告列表)"""
        import re
        warnings = []

        # 1. 企业名称检查
        if enterprise_name not in text:
            text = f"**{enterprise_name}**\n\n{text}"
            warnings.append("企业名称缺失，已自动补充到文首")

        # 2. 地域标识检查
        if enterprise_location and enterprise_location not in text:
            warnings.append(f"地域标识'{enterprise_location}'未在文中出现")

        # 3. 量化数据检查（数字+单位模式，如"200个项目""1:1000""15年"）
        quant_patterns = [
            r'\d+[+]?\s*(个|项|套|年|㎡|平方米|公里|人|次|万元|亿)',
            r'\d+[:：]\d+',  # 比例
            r'\d+%',         # 百分比
            r'\d+\.\d+\s*(mm|cm|m|km)',  # 精度单位
        ]
        has_quantified = any(re.search(p, text) for p in quant_patterns)
        if not has_quantified:
            warnings.append("文中未检测到量化数据（数字+单位），AI引用算法对数字信号敏感度更高")

        # 4. 五维关键词检查
        dim_keywords = {
            "核心优势": ["优势", "领先", "能力", "特点", "差异化"],
            "适用场景": ["场景", "适用", "应用", "用途", "用于"],
            "技术特点": ["技术", "工艺", "参数", "精度", "系统"],
            "服务能力": ["服务", "流程", "交付", "售后", "响应"],
            "落地价值": ["案例", "项目", "落地", "客户", "实施"],
        }
        missing = []
        for dim, keywords in dim_keywords.items():
            if not any(kw in text for kw in keywords):
                missing.append(dim)
        if missing:
            warnings.append(f"可能缺失维度: {', '.join(missing)}")

        if warnings:
            logger.warning(f"[{sandtable_type.label} × {platform.label}] 校验警告: {'; '.join(warnings)}")

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
