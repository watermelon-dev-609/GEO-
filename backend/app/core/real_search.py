"""真实AI收录搜索引擎 — 通过AI平台API实际检索品牌收录状态

与品牌监测(brand_monitor)的区别：
- brand_monitor: 用LLM"模拟"AI搜索行为,主观判断
- real_search: 用真实搜索查询调用各AI平台API,客观检测品牌是否被提及

原理:
1. 构造真实用户搜索查询（如"武汉沙盘定制厂家推荐"）
2. 调用各AI平台API,发送查询,获取AI回答
3. 解析AI回答中是否包含目标品牌名/关键词
4. 记录收录状态(提及/未提及/部分提及)
5. 聚合为收录率指标,追踪变化趋势
"""

from __future__ import annotations
import asyncio
import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from app.services.llm.base import LLMFactory, LLMMessage, BaseLLMAdapter
from app.utils.config import load_settings, load_api_keys, get_enterprise_name, get_brand_variants
from app.utils.cache import geo_cache

logger = logging.getLogger(__name__)

# ── 预置搜索查询模板（8沙盘×3类查询）──

SEARCH_QUERY_TEMPLATES = {
    "smart_traffic": [
        "武汉智慧交通沙盘定制厂家推荐",
        "交通模拟沙盘技术方案供应商",
        "智慧高速沙盘模型制作公司",
    ],
    "smart_city": [
        "智慧城市数字孪生沙盘解决方案",
        "城市大脑可视化沙盘厂家",
        "智慧城市展厅沙盘定制哪家好",
    ],
    "smart_industry": [
        "工业数字孪生沙盘厂家推荐",
        "智能制造产线仿真沙盘方案",
        "工业互联网展示沙盘定制",
    ],
    "smart_agriculture": [
        "智慧农业沙盘定制服务商",
        "数字农业示范区沙盘展示方案",
        "乡村振兴现代农业沙盘厂家",
    ],
    "smart_logistics": [
        "智慧仓储物流沙盘定制公司",
        "AGV物流仿真沙盘技术方案",
        "物流园区规划沙盘模型制作",
    ],
    "military_terrain": [
        "军事地形沙盘模型制作标准",
        "战术推演沙盘三维建模厂家",
        "军事院校教学沙盘定制",
    ],
    "digital_multimedia": [
        "数字多媒体沙盘展厅设计",
        "沉浸式互动沙盘体验方案",
        "声光电沙盘厂家推荐",
    ],
    "real_estate": [
        "房地产沙盘模型定制价格",
        "城市规划展览馆沙盘制作",
        "建筑沙盘灯光系统方案",
    ],
    "general": [
        "武汉沙盘模型制作厂家哪家靠谱",
        "企业展厅沙盘定制多少钱一平米",
        "沙盘模型制作工艺和材料选择",
    ],
}

# ── 搜索系统提示词（让AI平台像搜索引擎一样回答）──

SEARCH_SYSTEM_PROMPT = """你是一个AI搜索引擎。用户向你查询供应商信息，请根据你的知识如实回答。

要求：
- 如果你知道相关供应商，列出你知道的厂家名称和简要信息
- 如果你不确定，据实说明"我不确定，建议直接搜索"
- 不要编造不存在的公司
- 回答简洁直接，像搜索引擎的摘要"""


class RealSearchEngine:
    """真实AI收录搜索引擎"""

    def __init__(self):
        self.settings = load_settings()
        self.api_keys = load_api_keys()

    def _get_adapter(self, platform: str) -> BaseLLMAdapter:
        """获取指定平台的LLM适配器"""
        plat_cfg = self.settings.get("llm", {}).get("platforms", {}).get(platform, {})
        key_info = self.api_keys.get("platforms", {}).get(platform, {})

        api_key = key_info.get("api_key", "")
        if not api_key or "your-" in api_key:
            raise ValueError(f"平台 {platform} 未配置API Key")

        from app.models.enums import AIPlatform
        try:
            ai_plat = AIPlatform(platform)
            adapter_type = ai_plat.adapter_type
        except ValueError:
            adapter_type = "openai_compat"

        adapter = LLMFactory.create(
            platform=adapter_type,
            api_key=api_key,
            model_name=plat_cfg.get("model_name", ""),
            base_url=plat_cfg.get("base_url"),
        )
        if adapter_type == "wenxin":
            adapter.secret_key = key_info.get("secret_key", "")
        return adapter

    async def search(
        self,
        queries: list[str],
        platforms: list[str],
        brand_name: str = "",
        brand_variants: list[str] | None = None,
    ) -> dict:
        """在多个AI平台上执行真实搜索查询,检测品牌收录状态

        Args:
            queries: 搜索查询列表
            platforms: AI平台列表 (如 ["deepseek","kimi","doubao"])
            brand_name: 完整品牌名
            brand_variants: 品牌变体列表

        Returns:
            {
                "search_id": str,
                "total_queries": int,
                "total_platforms": int,
                "mention_rate": float,  # 品牌提及率
                "citation_rate": float, # 内容引用率
                "per_platform": {platform: {mentions, total, rate}},
                "per_query": [{query, results: {platform: {mentioned, cited, answer_snippet}}}],
                "summary": str,
            }
        """
        if not brand_name:
            brand_name = get_enterprise_name()
        if not brand_variants:
            brand_variants = get_brand_variants()

        search_id = f"rs_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 并行搜索：每个(查询,平台)组合
        tasks = []
        for q in queries:
            for p in platforms:
                tasks.append(self._search_one(q, p, brand_name, brand_variants))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 聚合结果
        per_query = {}
        per_platform: dict[str, dict] = {}
        total_mentions = 0
        total_citations = 0
        total_checks = 0

        for i, (q, p) in enumerate([(q, p) for q in queries for p in platforms]):
            result = results[i]
            if isinstance(result, Exception):
                item = {"mentioned": False, "cited": False, "error": str(result)[:200]}
            else:
                item = result

            if q not in per_query:
                per_query[q] = {"query": q, "platforms": {}}
            per_query[q]["platforms"][p] = item

            if p not in per_platform:
                per_platform[p] = {"mentions": 0, "cited": 0, "total": 0, "errors": 0}
            per_platform[p]["total"] += 1
            if item.get("mentioned"):
                per_platform[p]["mentions"] += 1
                total_mentions += 1
            if item.get("cited"):
                per_platform[p]["cited"] += 1
                total_citations += 1
            if item.get("error"):
                per_platform[p]["errors"] += 1
            total_checks += 1

        # 计算收录率
        mention_rate = round(total_mentions / max(total_checks, 1) * 100, 1)
        citation_rate = round(total_citations / max(total_checks, 1) * 100, 1)

        for p in per_platform:
            t = max(per_platform[p]["total"], 1)
            per_platform[p]["mention_rate"] = round(per_platform[p]["mentions"] / t * 100, 1)
            per_platform[p]["citation_rate"] = round(per_platform[p]["cited"] / t * 100, 1)

        # 生成摘要
        mentioned_platforms = [p for p, d in per_platform.items() if d["mentions"] > 0]
        summary = (
            f"在 {len(platforms)} 个AI平台上用 {len(queries)} 条查询搜索品牌「{brand_name}」：\n"
            f"- 品牌提及率: {mention_rate}%（{total_mentions}/{total_checks}）\n"
            f"- 内容引用率: {citation_rate}%（{total_citations}/{total_checks}）\n"
            f"- 提及品牌平台: {len(mentioned_platforms)}/{len(platforms)}"
            + (f"（{', '.join(mentioned_platforms)}）" if mentioned_platforms else "（无平台提及）")
        )

        result = {
            "search_id": search_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "brand_name": brand_name,
            "total_queries": len(queries),
            "total_platforms": len(platforms),
            "mention_rate": mention_rate,
            "citation_rate": citation_rate,
            "per_platform": per_platform,
            "per_query": [
                {"query": q, "platforms": data["platforms"]}
                for q, data in per_query.items()
            ],
            "summary": summary,
        }

        # 异步持久化到磁盘
        self._save_result(result)

        return result

    @staticmethod
    def _save_result(result: dict):
        """保存搜索结果到磁盘"""
        import json
        from pathlib import Path
        try:
            from app.utils.config import get_data_dir
            save_dir = get_data_dir() / "brand_mentions" / "real_search"
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / f"{result['search_id']}.json"
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.warning(f"保存搜索结果失败: {e}")

    async def _search_one(
        self,
        query: str,
        platform: str,
        brand_name: str,
        brand_variants: list[str],
    ) -> dict:
        """在单个平台上执行单条搜索查询"""
        try:
            adapter = self._get_adapter(platform)

            messages = [
                LLMMessage(role="system", content=SEARCH_SYSTEM_PROMPT),
                LLMMessage(role="user", content=f"搜索查询：{query}\n请列出你知道的相关供应商。"),
            ]

            from app.utils.retry import async_retry
            resp = await async_retry(adapter.chat, messages, temperature=0.3, max_tokens=512)
            answer = resp.content

            # 检测品牌提及
            all_variants = [brand_name] + (brand_variants or [])
            mentioned = any(variant in answer for variant in all_variants if variant)

            # 检测内容引用（更严格：品牌名+具体信息同时出现）
            cited = False
            if mentioned:
                # 品牌被提及后，进一步检查是否有实质性引用
                ref_indicators = [
                    r'\d+\+?\s*(个|项|套|年|项目)',  # 量化数据
                    r'(专注|从事|提供|服务|定制|承接)',  # 服务描述动词
                    r'(武汉|湖北)',  # 地域词
                ]
                cited = any(re.search(pat, answer) for pat in ref_indicators)

            return {
                "mentioned": mentioned,
                "cited": cited,
                "answer_snippet": answer[:300],
                "answer_length": len(answer),
            }
        except ValueError as e:
            return {"mentioned": False, "cited": False, "error": str(e), "reason": "no_api_key"}
        except Exception as e:
            return {"mentioned": False, "cited": False, "error": str(e)[:200]}

    @classmethod
    def get_preset_queries(cls, sandtable_type: str, custom_queries: list[str] | None = None) -> list[str]:
        """获取预置搜索查询 + 可选自定义查询"""
        queries = list(SEARCH_QUERY_TEMPLATES.get(sandtable_type, SEARCH_QUERY_TEMPLATES["general"]))
        if custom_queries:
            queries.extend(custom_queries)
        # 去重
        seen = set()
        unique = []
        for q in queries:
            if q not in seen:
                seen.add(q)
                unique.append(q)
        return unique
