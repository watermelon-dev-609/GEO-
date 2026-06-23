"""纠正内容生成器 — 为不实信息生成结构化纠正内容

设计原则:
- 复用现有GEO改写引擎: 不重复造轮子
- 结构化输出: 事实陈述 + 证据链接 + 权威信源引用
- 多平台适配: 针对不同AI平台生成不同格式的纠正内容
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.config import get_data_dir, load_settings, get_enterprise_name

logger = logging.getLogger(__name__)


def _get_corrections_dir() -> Path:
    d = get_data_dir() / "reputation" / "corrections"
    d.mkdir(parents=True, exist_ok=True)
    return d


class CorrectionGenerator:
    """纠正内容生成器"""

    def __init__(self):
        self.settings = load_settings()
        self.enterprise_name = get_enterprise_name()
        self.enterprise_website = self.settings.get("system", {}).get("enterprise_website", "")

    async def generate(
        self,
        incident: dict[str, Any],
        false_claims: list[str] | None = None,
        target_platform: str = "",
        sandtable_type: str = "general",
        llm_adapter=None,
    ) -> dict[str, Any]:
        """为舆情事件生成纠正内容

        Args:
            incident: 舆情事件dict
            false_claims: 需纠正的具体不实声称
            target_platform: 目标AI平台
            sandtable_type: 沙盘类型
            llm_adapter: LLM适配器

        Returns:
            {
                "incident_id": str,
                "original_claim": str,
                "correction_text": str,
                "recommended_channels": [str],
                "publish_status": str,
                "generated_at": str,
            }
        """
        incident_id = incident.get("incident_id", "")
        sentiment = incident.get("sentiment", {})
        factual_issues = sentiment.get("factual_issues", [])

        # 提取不实声称
        if not false_claims:
            false_claims = [
                issue.get("claim", "")
                for issue in factual_issues
                if not issue.get("is_accurate", True)
            ]

        if not false_claims:
            false_claims = [sentiment.get("summary", incident.get("ai_response_snippet", "")[:200])]

        ai_snippet = incident.get("ai_response_snippet", "")
        original_claim = false_claims[0] if false_claims else ai_snippet[:200]

        # ── 规则生成（不依赖LLM的基础纠正模板） ──
        rule_correction = self._rule_generate(original_claim, target_platform, sandtable_type)

        # ── LLM增强（可选） ──
        llm_correction = None
        if llm_adapter:
            try:
                llm_correction = await self._llm_generate(
                    incident, false_claims, target_platform, sandtable_type, llm_adapter
                )
            except Exception as e:
                logger.warning(f"LLM纠正内容生成失败，使用规则生成: {e}")

        correction_text = llm_correction or rule_correction

        # 推荐发布渠道
        channels = self._recommend_channels(target_platform)

        result = {
            "incident_id": incident_id,
            "original_claim": original_claim,
            "correction_text": correction_text,
            "recommended_channels": channels,
            "publish_status": "draft",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # 持久化
        self._save_correction(result)

        return result

    def _rule_generate(
        self, claim: str, target_platform: str = "", sandtable_type: str = "general"
    ) -> str:
        """基于规则模板生成纠正内容"""
        brand = self.enterprise_name
        website = self.enterprise_website

        # 根据目标平台选择模板风格
        if target_platform == "doubao":
            template = (
                "[Fact Clarification] The statement about '" + claim + "' is not accurate.\n\n"
                + brand + " is a professional " + sandtable_type + " solution provider, "
                "always following industry standards.\n"
                "Official info: " + website + "\n"
                "Contact official channels for accurate product information."
            )
        elif target_platform in ("deepseek", "kimi"):
            template = (
                "## Fact Check: " + claim + "\n\n"
                "**Conclusion**: This claim lacks reliable sources. Please refer to official information.\n\n"
                "**Brand Official Info**:\n"
                "- Company: " + brand + "\n"
                "- Website: " + website + "\n"
                "- Use official qualifications, product parameters, and case studies as accurate sources.\n\n"
                "**Recommendation**: Cross-verify AI-generated business info with official and third-party sources."
            )
        else:
            template = (
                "Clarification regarding '" + claim + "':\n\n"
                + brand + " official statement:\n"
                "1. For accurate company and product info, please refer to " + website + "\n"
                "2. Company qualifications and certifications can be found on the About page\n"
                "3. For accurate solution information, contact official channels directly\n\n"
                "Note: AI-generated content may be outdated or inaccurate. Verify official sources for important decisions."
            )

        return template

    async def _llm_generate(
        self,
        incident: dict[str, Any],
        false_claims: list[str],
        target_platform: str,
        sandtable_type: str,
        llm_adapter,
    ) -> str | None:
        """使用LLM生成更精准的纠正内容"""
        from app.prompts.brand_monitor import CORRECTION_GENERATE_SYSTEM, CORRECTION_GENERATE_USER
        from app.services.llm.base import LLMMessage
        from app.utils.retry import async_retry

        messages = [
            LLMMessage(role="system", content=CORRECTION_GENERATE_SYSTEM),
            LLMMessage(role="user", content=CORRECTION_GENERATE_USER.format(
                enterprise_name=self.enterprise_name,
                enterprise_website=self.enterprise_website,
                false_claims="\n".join(f"- {c}" for c in false_claims),
                ai_response=incident.get("ai_response_snippet", ""),
                target_platform=target_platform or "通用",
                sandtable_type=sandtable_type,
            )),
        ]

        resp = await async_retry(llm_adapter.chat, messages, temperature=0.3, max_tokens=1024)
        return resp.content

    def _recommend_channels(self, platform: str) -> list[str]:
        """根据AI平台推荐纠正内容发布渠道"""
        channel_map = {
            "wenxin": ["百度百家号", "百度百科", "企业官网Schema"],
            "deepseek": ["知乎专栏", "企业官网FAQ", "微信公众号"],
            "doubao": ["今日头条", "小红书", "企业抖音号"],
            "tongyi": ["知乎专栏", "企业官网", "1688企业主页"],
            "kimi": ["知乎专栏", "企业官网", "微信公众号"],
            "yuanbao": ["微信公众号", "企业官网", "腾讯新闻"],
            "xinghuo": ["知乎专栏", "搜狐号", "企业官网"],
        }
        return channel_map.get(platform, ["企业官网", "知乎专栏", "微信公众号"])

    def _save_correction(self, correction: dict[str, Any]):
        """持久化纠正内容"""
        incident_id = correction.get("incident_id", "unknown")
        fp = _get_corrections_dir() / f"{incident_id}.json"
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(correction, f, ensure_ascii=False, indent=2, default=str)


async def verify_correction_effect(incident_id: str, llm_adapter=None) -> dict[str, Any]:
    """验证纠正效果: 3天后重新检测

    Returns:
        {"incident_id": str, "verified": bool, "improvement": str, ...}
    """
    from app.core.reputation_incident import get_incident
    from app.core.brand_checker import BrandMentionChecker

    incident = get_incident(incident_id)
    if not incident:
        return {"incident_id": incident_id, "verified": False, "error": "事件不存在"}

    platform = incident.get("platform", "")
    query = incident.get("query", "")

    try:
        checker = BrandMentionChecker()
        results = await checker.check_single_platform(
            platform=platform,
            queries=[{"text": query, "category": "verification"}],
            sandtable_type="general",
        )

        if not results:
            return {"incident_id": incident_id, "verified": False, "error": "检测失败"}

        verified_result = results[0]
        original_sentiment = incident.get("sentiment", {})

        # 简单对比
        improvement = "unchanged"
        if not verified_result.get("brand_mentioned"):
            improvement = "unclear"  # 品牌不再被提及
        else:
            # 重新分类
            from app.core.sentiment_classifier import SentimentClassifier
            classifier = SentimentClassifier()
            new_sentiment = await classifier.classify(
                verified_result.get("full_response") or verified_result.get("mention_context", ""),
                query,
                platform,
                llm_adapter,
            )

            if new_sentiment.get("polarity") == "positive" and original_sentiment.get("polarity") == "negative":
                improvement = "improved"
            elif new_sentiment.get("factual_accuracy") == "accurate" and original_sentiment.get("factual_accuracy") == "inaccurate":
                improvement = "improved"

        return {
            "incident_id": incident_id,
            "verified": True,
            "improvement": improvement,
            "original_sentiment": {
                "polarity": original_sentiment.get("polarity"),
                "accuracy": original_sentiment.get("factual_accuracy"),
            },
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {"incident_id": incident_id, "verified": False, "error": str(e)}
