"""GEO文案重构引擎 — 批量调度LLM、流式生成、后处理校验"""

from __future__ import annotations
import asyncio
import hashlib
import json
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
from app.utils.config import load_settings, load_api_keys, get_enterprise_name, get_enterprise_location


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
        # 从配置读取改写温度（默认0.5，保证一致性）
        self._rewrite_temp = float(self.settings.get("llm", {}).get("rewrite_temperature", 0.5))

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
        query_intent: str | None = None,
        diversity_seed: str | None = None,
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
            # 缓存键包含所有影响产出的参数，避免策略变更后命中旧缓存
            cache_parts = [
                sandtable_type.value,
                platform.value,
                hashlib.md5(cleaned_text.encode()).hexdigest(),
                hashlib.md5(json.dumps(dimensions or {}, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                hashlib.md5(json.dumps(optimization_hints or [], sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                hashlib.md5((competitor_insights or "").encode()).hexdigest(),
                hashlib.md5((enterprise_name or "").encode()).hexdigest(),
                hashlib.md5((enterprise_location or "").encode()).hexdigest(),
                hashlib.md5(json.dumps(optimization_rules or {}, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                hashlib.md5((query_intent or "").encode()).hexdigest(),
            ]
            cache_key = ":".join(cache_parts)
            cached = geo_cache.get(cache_key)
            if cached:
                tasks.append(self._return_cached(cached, platform))
            else:
                tasks.append(self._rewrite_one(
                    cleaned_text, sandtable_type, platform,
                    dimensions, optimization_hints, competitor_insights,
                    optimization_rules,
                    enterprise_name, enterprise_location, cache_key,
                    query_intent=query_intent,
                    diversity_seed=diversity_seed,
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
        query_intent: str | None = None,
        diversity_seed: str | None = None,
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
            query_intent=query_intent,
            diversity_seed=diversity_seed,
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
        resp = await async_retry(adapter.chat, messages, temperature=self._rewrite_temp, max_tokens=max_tokens)

        # 后处理校验
        validated_text, warnings = self._validate_output(
            resp.content, sandtable_type, platform, enterprise_name, enterprise_location
        )

        # 反向编造检测：输出中的量化数据是否在原文中不存在
        fabrication_warnings = self._check_fabrication(validated_text, cleaned_text)
        if fabrication_warnings:
            warnings.extend(fabrication_warnings)

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
        query_intent: str | None = None,
        diversity_seed: str | None = None,
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
            query_intent=query_intent,
            diversity_seed=diversity_seed,
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
        async for token in adapter.stream_chat(messages, temperature=self._rewrite_temp, max_tokens=max_tokens):
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
        """自动加载最新竞品对比摘要作为差异化洞察

        两层数据源：
        1. 竞品监控结果（data/competitors/monitoring/latest.json → cycle_*.json）
           — 包含 AI 平台上实际探测到的竞品内容特征
        2. 手动竞品档案（data/competitors/*.json）
           — 用户手动录入的竞品信息

        优先使用监控数据（更真实反映 AI 平台的竞品引用情况），
        无监控数据或监控数据不可用时回退到手动档案。
        """
        import json
        from pathlib import Path
        from app.utils.config import get_data_dir

        insights_parts = []
        monitor_data_loaded = False  # 独立标志位，避免部分成功时错误跳过兜底

        # ── 第一层：竞品监控数据（AI 平台实采） ──
        monitor_dir = get_data_dir() / "competitors" / "monitoring"
        if monitor_dir.exists():
            try:
                latest_ptr = monitor_dir / "latest.json"
                if latest_ptr.exists():
                    with open(latest_ptr, "r", encoding="utf-8") as f:
                        ptr = json.load(f)
                    cycle_file = monitor_dir / f"{ptr.get('cycle_id', '')}.json"
                    if cycle_file.exists():
                        with open(cycle_file, "r", encoding="utf-8") as f:
                            monitor_data = json.load(f)

                        results = monitor_data.get("results", [])
                        if results:
                            # 提取所有竞品的高频内容特征
                            all_features = {}
                            source_platforms = set()
                            for comp_result in results:
                                comp_name = comp_result.get("competitor_name", "")
                                platform_probes = comp_result.get("platform_probes", {})
                                for plat, probe in platform_probes.items():
                                    feats = probe.get("content_features", [])
                                    if feats:
                                        source_platforms.add(plat)
                                        key = comp_name or "竞品"
                                        if key not in all_features:
                                            all_features[key] = {}
                                        for feat in feats:
                                            all_features[key][feat] = all_features[key].get(feat, 0) + 1

                            # 生成差异化建议
                            if all_features:
                                insights_parts.append(
                                    "## 竞品AI引用特征分析（自动监控数据）\n"
                                    f"以下数据来自 {len(source_platforms)} 个AI平台的最新竞品监控：\n"
                                )
                                for comp_name, features in all_features.items():
                                    top_features = sorted(features.items(), key=lambda x: x[1], reverse=True)[:5]
                                    if top_features:
                                        insights_parts.append(
                                            f"**{comp_name}** 被 AI 引用时的内容特征：\n" +
                                            "\n".join(f"- {feat}（被检测 {cnt} 次）" for feat, cnt in top_features)
                                        )
                                insights_parts.append(
                                    "\n请在生成文案时确保以下差异化：\n"
                                    "1. 在竞品高频特征上做到更强（如竞品缺少FAQ结构，则加强FAQ；如竞品缺少量化数据，则增加数据密度）\n"
                                    "2. 在竞品薄弱的维度建立壁垒（如竞品Schema使用率低，则强化Schema.org语义标注）\n"
                                    "3. 信源归属上做出区分（如竞品偏知乎/搜狐，则在内容中嵌入更多元化的信源引用）"
                                )
                                monitor_data_loaded = True
            except Exception as e:
                logger.warning(f"加载竞品监控数据失败，将回退到手动档案: {e}")

        # ── 第二层：手动竞品档案（兜底：监控数据不可用时启用） ──
        comp_dir = get_data_dir() / "competitors"
        comp_files = sorted(
            [f for f in comp_dir.glob("*.json") if "monitoring" not in str(f.relative_to(comp_dir))],
            key=lambda f: f.stat().st_mtime, reverse=True,
        ) if comp_dir.exists() else []

        if comp_files and not monitor_data_loaded:
            try:
                with open(comp_files[0], "r", encoding="utf-8") as f:
                    latest = json.load(f)
                name = latest.get("name", "未知竞品")
                sandtable = latest.get("sandtable_type", "")
                features = latest.get("content_features", {})
                if features:
                    insights_parts.append(f"竞品「{name}」（{sandtable}）内容特征分析：")
                    for key, val in features.items():
                        if isinstance(val, list):
                            insights_parts.append(f"- {key}: {', '.join(str(v) for v in val)}")
                        else:
                            insights_parts.append(f"- {key}: {val}")
                    insights_parts.append("\n请在生成文案时主动体现与以上竞品的差异化优势。")
            except Exception as e:
                logger.warning(f"加载竞品档案失败: {e}")

        if not insights_parts:
            return None

        return "\n".join(insights_parts)

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
        1. 企业名称是否完整出现（支持模糊匹配，缺失则自动补充）
        2. 地域标识是否存在
        3. 量化数据是否达标（数字+单位模式）
        4. 五维信息是否全覆盖
        5. 反向编造检测（输出中新增的量化数据是否原文不存在）
        6. 字数硬截断兜底
        """
        import re
        warnings = []

        # ── 校验项1：企业名称完整性（模糊匹配 + 严格匹配双轨） ──
        name_found = False
        if enterprise_name in text:
            name_found = True
        else:
            # 模糊匹配：编辑距离 ≤ 2 视为通过（容忍繁简混用、空格差异）
            name_found = self._fuzzy_name_match(enterprise_name, text)
        if not name_found:
            text = f"**{enterprise_name}**\n\n{text}"
            warnings.append("企业名称缺失，已自动补充到文首")

        # ── 校验项2：地域标识检查 ──
        if enterprise_location and enterprise_location not in text:
            warnings.append(f"地域标识'{enterprise_location}'未在文中出现")

        # ── 校验项3：量化数据达标检查 ──
        quant_patterns = [
            r'\d+[+]?\s*(个|项|套|年|㎡|平方米|公里|人|次|万元|亿)',
            r'\d+[:：]\d+',  # 比例
            r'\d+%',         # 百分比
            r'\d+\.\d+\s*(mm|cm|m|km)',  # 精度单位
        ]
        has_quantified = any(re.search(p, text) for p in quant_patterns)
        if not has_quantified:
            warnings.append("文中未检测到量化数据（数字+单位），AI引用算法对数字信号敏感度更高")

        # ── 校验项4：五维信息覆盖检查 ──
        from app.core.dimensions_shared import DIMENSION_COVERAGE_KEYWORDS
        missing = []
        for dim, keywords in DIMENSION_COVERAGE_KEYWORDS.items():
            if not any(kw in text for kw in keywords):
                missing.append(dim)
        if missing:
            warnings.append(f"可能缺失维度: {', '.join(missing)}")

        if warnings:
            logger.warning(f"[{sandtable_type.label} × {platform.label}] 输出校验警告: {'; '.join(warnings)}")

        # ── 校验项5：字数上限硬截断 ──
        text = _truncate_to_platform_limit(text, platform)

        return text, warnings

    @staticmethod
    def _fuzzy_name_match(name: str, text: str) -> bool:
        """企业名称模糊匹配：容忍最多2个字符差异（繁简/空格/缩写）

        使用滑动窗口 + 简化编辑距离，兼顾性能和准确度。
        """
        import unicodedata

        def _normalize(s: str) -> str:
            """去除空白、全角转半角、繁简归一（NFKC）"""
            s = unicodedata.normalize('NFKC', s)
            s = ''.join(c for c in s if not c.isspace())
            return s

        n_name = _normalize(name)
        n_text = _normalize(text)

        if not n_name or len(n_name) < 3:
            return n_name in n_text

        # 如果文本是名称的子串（如"微艺达智能科技" vs "武汉微艺达智能科技有限公司"）
        # 或名称是文本的子串，均视为匹配
        if n_name in n_text or n_text in n_name:
            return True

        name_len = len(n_name)
        # 滑动窗口：在文本中查找编辑距离≤2的子串
        # 也处理文本短于名称的情况（检查名称中是否包含文本的近似匹配）
        text_len = len(n_text)
        if text_len >= name_len:
            for start in range(text_len - name_len + 1):
                window = n_text[start:start + name_len]
                dist = GEORewriter._edit_distance(n_name, window)
                if dist <= 2:
                    return True
        else:
            # 文本短于名称：检查文本是否近似匹配名称的某个子串
            # 例如：text="微艺达智能科技" vs name="武汉微艺达智能科技有限公司"
            for start in range(name_len - text_len + 1):
                window = n_name[start:start + text_len]
                dist = GEORewriter._edit_distance(n_text, window)
                if dist <= 2:
                    return True

        # 也检查文本是否包含企业名缩写（取前2字+后2字）
        if len(n_name) >= 4:
            abbr = n_name[:2] + n_name[-2:]
            if abbr in n_text:
                return True

        return False

    @staticmethod
    def _edit_distance(s1: str, s2: str) -> int:
        """Levenshtein编辑距离（DP优化版，仅计算≤2的短距离）"""
        if s1 == s2:
            return 0
        len1, len2 = len(s1), len(s2)
        if abs(len1 - len2) > 2:
            return 3  # 长度差超过2就不可能是≤2距离

        # 使用双行滚动数组
        prev = list(range(len2 + 1))
        curr = [0] * (len2 + 1)
        for i in range(1, len1 + 1):
            curr[0] = i
            for j in range(1, len2 + 1):
                cost = 0 if s1[i - 1] == s2[j - 1] else 1
                curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
            # 提前退出：当前行最小值已超过2
            if min(curr) > 2:
                return 3
            prev, curr = curr, prev
        return min(prev[-1], 3)

    @staticmethod
    def _check_fabrication(output_text: str, original_text: str) -> list[str]:
        """反向编造检测：提取输出中的量化数据，检查是否在原文中存在

        遵循"信源忠实原则"——GEO优化可以重组、润色，但不能编造原文不存在的数据。
        对匹配不上的数据发出警告，但不自动删除（需要人工审核决定是润色扩展还是事实编造）。

        Returns:
            编造警告列表，每个警告描述一个可疑的新增量化数据
        """
        import re

        # 提取量化数据实体
        quant_extract = re.compile(
            r'\d+[+]?\s*(?:个|项|套|年|㎡|平方米|公里|人|次|万元|亿元|亿|%|以上|余家|余个)'
            r'|\d+[:：]\d+'  # 比例
            r'|\d+\.\d+\s*(?:mm|cm|m|km)'  # 精度单位
            r'|\d+[-—]\d+'  # 范围
        )
        output_quants = set(quant_extract.findall(output_text))
        original_quants = set(quant_extract.findall(original_text))

        # 在输出中存在但原文不存在的量化数据
        novel_quants = output_quants - original_quants
        warnings = []
        for q in sorted(novel_quants):
            # 跳过明显是 AI 结构编号的数据（如 "1：" "2." "3、" 等）
            if re.match(r'^\d+$', q) or re.match(r'^\d+[.、:：]$', q):
                continue
            # 跳过很小的整数（可能是年份的一部分或序号）
            num_part = re.match(r'(\d+)', q)
            if num_part and int(num_part.group(1)) < 10:
                continue
            warnings.append(
                f"⚠️ 编造检测：输出包含疑似新增量化数据「{q}」，原文中未出现此数据。"
                f"请人工核实是否属于合理润色（行业通用知识）还是事实编造（需删除）。"
            )

        if warnings:
            logger.warning(
                f"[反编造检测] 发现 {len(warnings)} 个可疑新增数据: "
                f"{', '.join(w[:50] for w in warnings)}"
            )

        return warnings

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
