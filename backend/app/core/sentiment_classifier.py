"""情感+事实准确性分类器 — 对AI回复中的品牌提及进行情感分析和事实核查

设计原则:
- 规则+LLM双引擎: 先关键词规则快速扫描（毫秒级），边界case走LLM深度分析
- 不修改 brand_checker.py: 作为独立后处理层，叠加在品牌检测结果之上
- 降级策略: 无LLM时纯规则模式，功能不中断
"""

from __future__ import annotations
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.utils.config import load_settings, get_enterprise_name, get_brand_variants
from app.utils.cache import eval_cache
from app.utils.retry import async_retry

logger = logging.getLogger(__name__)


def _load_sentiment_config() -> dict[str, Any]:
    """加载舆情监控配置"""
    settings = load_settings()
    return settings.get("reputation", {})


def _default_negative_keywords() -> list[str]:
    """默认负面关键词库"""
    return [
        "骗", "假的", "不靠谱", "质量差", "坑", "贵", "不值", "后悔",
        "投诉", "曝光", "维权", "差评", "烂", "垃圾", "黑心",
        "不推荐", "不建议", "避坑", "踩坑", "千万别", "不要选",
        "忽悠", "虚假", "夸大", "名不副实", "徒有虚名",
    ]


def _default_positive_keywords() -> list[str]:
    """默认正面关键词库"""
    return [
        "推荐", "专业", "靠谱", "领先", "首选", "优秀", "优质",
        "值得信赖", "口碑好", "服务好", "质量好", "技术强",
        "性价比高", "好评", "满意度高", "经验丰富", "实力雄厚",
        "放心", "认可", "称赞", "标杆", "典范",
    ]


class SentimentClassifier:
    """品牌提及情感+事实准确性分类器"""

    def __init__(self):
        self.config = _load_sentiment_config()
        self.enterprise_name = get_enterprise_name()
        self.brand_variants = get_brand_variants()
        self.negative_keywords = self.config.get("negative_keywords", _default_negative_keywords())
        self.positive_keywords = self.config.get("positive_keywords", _default_positive_keywords())

    # ══════════════════════════════════════════════════════════════
    # 规则引擎: 关键词快速扫描
    # ══════════════════════════════════════════════════════════════

    def _rule_classify(self, response: str, query: str = "") -> dict[str, Any]:
        """基于关键词规则的快速情感+事实分类"""
        if not response or len(response.strip()) < 20:
            return {
                "polarity": "neutral",
                "confidence": 30.0,
                "factual_accuracy": "unverifiable",
                "factual_issues": [],
                "summary": "回复内容过短，无法准确判断",
                "method": "rule",
            }

        # ── 情感极性判断 ──
        neg_count = sum(1 for kw in self.negative_keywords if kw in response)
        pos_count = sum(1 for kw in self.positive_keywords if kw in response)

        # 检查品牌名附近的上下文
        brand_contexts = []
        for variant in self.brand_variants:
            if len(variant) < 3:
                continue
            for m in re.finditer(re.escape(variant), response):
                start = max(0, m.start() - 30)
                end = min(len(response), m.end() + 30)
                brand_contexts.append(response[start:end])

        # 在品牌上下文中的情感
        ctx_neg = sum(1 for ctx in brand_contexts for kw in self.negative_keywords if kw in ctx)
        ctx_pos = sum(1 for ctx in brand_contexts for kw in self.positive_keywords if kw in ctx)

        # 综合判断
        if neg_count > pos_count and neg_count >= 2:
            polarity = "negative"
            confidence = min(85.0, 50 + neg_count * 10)
        elif pos_count > neg_count and pos_count >= 2:
            polarity = "positive"
            confidence = min(85.0, 50 + pos_count * 10)
        elif ctx_neg > ctx_pos and ctx_neg >= 1:
            polarity = "negative"
            confidence = 55.0
        elif ctx_pos > ctx_neg and ctx_pos >= 1:
            polarity = "positive"
            confidence = 55.0
        else:
            polarity = "neutral"
            confidence = 60.0

        # ── 事实准确性判断 ──
        factual_issues = []
        accuracy = "unverifiable"

        # 检测夸大/绝对化表述
        exaggerated = re.findall(
            r'(全球第一|全国第一|行业第一|最厉害|最强|最专业|唯一|独家|绝对|100%|零差评|完美无缺)',
            response
        )
        # 检测无来源的量化声称
        unverified_claims = re.findall(
            r'(\d+[+]?\s*(?:年|家|个|项|万|亿|%)(?:经验|客户|项目|案例))',
            response
        )

        for claim in exaggerated:
            # 检查是否在品牌上下文中
            for ctx in brand_contexts:
                if claim in ctx:
                    factual_issues.append({
                        "claim": claim,
                        "is_accurate": False,
                        "evidence": "绝对化表述缺乏数据佐证",
                        "correction": f"将'{claim}'替换为具体的量化数据或第三方认证",
                    })

        if factual_issues:
            accuracy = "inaccurate"
        elif unverified_claims:
            accuracy = "partially_accurate"
            # 不做逐条标记，仅标记整体
        else:
            accuracy = "unverifiable"

        # ── 生成摘要 ──
        polarity_cn = {"positive": "正面", "neutral": "中性", "negative": "负面"}[polarity]
        summary = f"规则判定: 情感{polarity_cn}(置信度{confidence:.0f}%), 事实准确性: {accuracy}"

        return {
            "polarity": polarity,
            "confidence": confidence,
            "factual_accuracy": accuracy,
            "factual_issues": factual_issues[:5],
            "summary": summary,
            "method": "rule",
        }

    # ══════════════════════════════════════════════════════════════
    # LLM引擎: 深度情感+事实分析
    # ══════════════════════════════════════════════════════════════

    async def _llm_classify(
        self, response: str, query: str = "", llm_adapter=None
    ) -> dict[str, Any] | None:
        """使用LLM进行深度情感+事实分析"""
        if not llm_adapter:
            return None

        from app.prompts.brand_monitor import SENTIMENT_CLASSIFY_SYSTEM, SENTIMENT_CLASSIFY_USER

        try:
            from app.services.llm.base import LLMMessage

            messages = [
                LLMMessage(role="system", content=SENTIMENT_CLASSIFY_SYSTEM),
                LLMMessage(role="user", content=SENTIMENT_CLASSIFY_USER.format(
                    enterprise_name=self.enterprise_name,
                    brand_variants=", ".join(self.brand_variants),
                    response=response[:2500],
                    query=query,
                )),
            ]

            resp = await async_retry(llm_adapter.chat, messages, temperature=0.2, max_tokens=1024)
            return self._parse_llm_result(resp.content)
        except Exception as e:
            logger.warning(f"LLM情感分类失败: {e}")
            return None

    def _parse_llm_result(self, content: str) -> dict[str, Any] | None:
        """解析LLM分类结果"""
        try:
            json_match = re.search(r'```json\s*([\s\S]*?)```', content)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    data = json.loads(json_match.group(0))
                else:
                    return None

            return {
                "polarity": data.get("polarity", "neutral"),
                "confidence": float(data.get("confidence", 50)),
                "factual_accuracy": data.get("factual_accuracy", "unverifiable"),
                "factual_issues": data.get("factual_issues", []),
                "summary": data.get("summary", ""),
                "method": "llm",
            }
        except (json.JSONDecodeError, AttributeError, ValueError) as e:
            logger.warning(f"LLM分类结果解析失败: {e}")
            return None

    # ══════════════════════════════════════════════════════════════
    # 主入口: 混合分类
    # ══════════════════════════════════════════════════════════════

    async def classify(
        self,
        response: str,
        query: str = "",
        platform: str = "",
        llm_adapter=None,
    ) -> dict[str, Any]:
        """对AI回复进行情感+事实分类（规则优先，LLM补充）

        Args:
            response: AI平台的回复文本
            query: 触发的用户查询
            platform: 来源AI平台标识
            llm_adapter: LLM适配器（可选，用于深度分析）

        Returns:
            {
                "polarity": str,
                "confidence": float,
                "factual_accuracy": str,
                "factual_issues": [dict],
                "summary": str,
                "method": "rule"|"hybrid"|"llm",
                "classified_at": str,
            }
        """
        # 第一阶段: 规则快速扫描
        rule_result = self._rule_classify(response, query)

        # 第二阶段: 对于边界case，调用LLM深度分析
        needs_llm = (
            rule_result["confidence"] < 70 or
            rule_result["factual_accuracy"] == "unverifiable" or
            rule_result["polarity"] == "negative"  # 负面结果需LLM二次确认
        )

        if needs_llm and llm_adapter:
            llm_result = await self._llm_classify(response, query, llm_adapter)
            if llm_result:
                # 混合模式: 取两者中更确定的结果
                if llm_result["confidence"] > rule_result["confidence"]:
                    result = llm_result
                    result["method"] = "hybrid"
                    result["rule_polarity"] = rule_result["polarity"]
                else:
                    result = rule_result
                    result["method"] = "hybrid"
                    result["llm_polarity"] = llm_result["polarity"]
            else:
                result = rule_result
        else:
            result = rule_result

        result["classified_at"] = datetime.now(timezone.utc).isoformat()
        result["platform"] = platform

        return result

    def classify_sync(self, response: str, query: str = "") -> dict[str, Any]:
        """同步分类（仅规则模式，不需要LLM）"""
        result = self._rule_classify(response, query)
        result["classified_at"] = datetime.now(timezone.utc).isoformat()
        return result

    async def batch_classify(
        self,
        results: list[dict[str, Any]],
        llm_adapter=None,
    ) -> list[dict[str, Any]]:
        """批量对品牌监测结果进行情感分类

        Args:
            results: 品牌监测结果列表 (BrandMentionCheckResult格式)
            llm_adapter: LLM适配器

        Returns:
            每个结果附加 sentiment 字段的完整列表
        """
        enriched = []
        for r in results:
            response_text = r.get("full_response") or r.get("mention_context", "")
            query = r.get("query", "")
            platform = r.get("platform", "")

            if response_text and r.get("brand_mentioned"):
                sentiment = await self.classify(response_text, query, platform, llm_adapter)
            else:
                sentiment = {
                    "polarity": "neutral",
                    "confidence": 0,
                    "factual_accuracy": "unverifiable",
                    "factual_issues": [],
                    "summary": "品牌未被提及或无回复内容",
                    "method": "skip",
                    "classified_at": datetime.now(timezone.utc).isoformat(),
                }

            enriched.append({**r, "sentiment": sentiment})

        return enriched


# ── 严重度评估 ──

def assess_severity(
    sentiment: dict[str, Any],
    alert_thresholds: dict[str, int] | None = None,
) -> str:
    """根据情感分析结果评估舆情事件严重度

    Args:
        sentiment: classify() 返回的情感分析结果
        alert_thresholds: 配置的阈值（可选）

    Returns:
        "critical" | "high" | "medium" | "low"
    """
    thresholds = alert_thresholds or {"critical": 3, "high": 2, "medium": 1}

    polarity = sentiment.get("polarity", "neutral")
    accuracy = sentiment.get("factual_accuracy", "unverifiable")
    confidence = sentiment.get("confidence", 0)

    # 负面 + 不准确 → critical
    if polarity == "negative" and accuracy == "inaccurate" and confidence >= 60:
        return "critical"
    # 负面 + 准确（AI说的是事实但负面）→ high（需要公关回应）
    if polarity == "negative" and accuracy == "accurate":
        return "high"
    # 负面 + 部分不准确 → medium
    if polarity == "negative" and accuracy == "partially_accurate":
        return "medium"
    # 不准确但中性 → medium
    if accuracy == "inaccurate" and polarity == "neutral":
        return "medium"
    # 其余 → low
    if polarity == "negative":
        return "medium"
    if accuracy == "inaccurate":
        return "low"

    return "low"
