"""BrandMentionChecker — 品牌AI收录检测引擎"""

from __future__ import annotations
import re
import logging
import hashlib
import asyncio
from datetime import datetime, timezone

from app.models.enums import AIPlatform, SandtableType
from app.services.llm.base import LLMFactory, LLMMessage
from app.utils.config import load_settings, load_api_keys, get_enterprise_name, get_brand_variants
from app.utils.retry import async_retry
from app.utils.cache import eval_cache

logger = logging.getLogger(__name__)

# ── 从评测引擎导入预设问题库 ──
from app.core.evaluator import ROLE_QUESTIONS
from app.models.enums import UserRole

# 查询分类 → 用户角色映射（品牌直问→采购/通用，场景问询→项目经理/技术）
CATEGORY_TO_ROLES = {
    "brand_direct": [UserRole.B_END_PROCUREMENT, UserRole.GENERAL_CONSULTANT],
    "scenario": [UserRole.PROJECT_MANAGER, UserRole.TECHNICAL_SELECTION],
    "product": [UserRole.TECHNICAL_SELECTION, UserRole.PROJECT_MANAGER],
}


class BrandMentionChecker:
    """品牌AI收录检测器"""

    def __init__(self):
        self.settings = load_settings()
        self.api_keys = load_api_keys()
        self.enterprise_name = get_enterprise_name()
        self.brand_variants = get_brand_variants()
        self._build_brand_patterns()

    def _build_brand_patterns(self):
        self._patterns = []
        for variant in self.brand_variants:
            if len(variant) >= 3:
                self._patterns.append((variant, re.compile(re.escape(variant))))

    def _detect_mention_regex(self, response: str) -> tuple[bool, float, str]:
        """正则检测品牌提及 → (found, confidence, context)"""
        for variant, pat in self._patterns:
            m = pat.search(response)
            if m:
                start = max(0, m.start() - 40)
                end = min(len(response), m.end() + 40)
                ctx = response[start:end]
                if len(variant) >= 6:
                    return True, 100.0, ctx
                return True, 80.0, ctx
        return False, 0.0, ""

    async def _detect_mention_llm(
        self, response: str, query: str, llm_adapter=None
    ) -> tuple[bool, float, str]:
        """LLM 语义验证品牌提及"""
        if not llm_adapter:
            return False, 0.0, ""
        from app.prompts.brand_monitor import BRAND_MENTION_DETECT_SYSTEM, BRAND_MENTION_DETECT_USER
        try:
            messages = [
                LLMMessage(role="system", content=BRAND_MENTION_DETECT_SYSTEM),
                LLMMessage(role="user", content=BRAND_MENTION_DETECT_USER.format(
                    enterprise_name=self.enterprise_name,
                    brand_variants=", ".join(self.brand_variants),
                    response=response[:2000],
                    query=query,
                )),
            ]
            resp = await async_retry(llm_adapter.chat, messages, temperature=0.1, max_tokens=256)
            content = resp.content
            mentioned = "MENTION: YES" in content.upper()
            score_match = re.search(r'SCORE:\s*(\d+)', content)
            if score_match:
                score = float(score_match.group(1))
            else:
                logger.warning(f"LLM brand mention response missing SCORE field: {content[:200]}")
                score = None  # 无法解析LLM输出时，不捏造分数，由调用方使用regex置信度
            reason_match = re.search(r'REASON:\s*(.+?)$', content, re.MULTILINE)
            context = reason_match.group(1).strip() if reason_match else content[:200]
            return mentioned, score, context
        except Exception as e:
            logger.warning(f"LLM brand mention detection failed: {e}")
            return False, 0.0, ""

    async def _detect_mention(
        self, response: str, query: str, llm_adapter=None
    ) -> dict:
        """三级混合检测"""
        regex_found, regex_conf, regex_ctx = self._detect_mention_regex(response)
        if regex_found and regex_conf >= 100:
            return {
                "brand_mentioned": True,
                "mention_score": regex_conf,
                "mention_context": regex_ctx,
                "check_method": "regex",
            }
        if regex_found and regex_conf >= 80:
            llm_found, llm_score, llm_ctx = await self._detect_mention_llm(response, query, llm_adapter)
            if llm_found:
                final_score = llm_score if llm_score is not None else regex_conf
                return {
                    "brand_mentioned": True,
                    "mention_score": max(regex_conf, final_score),
                    "mention_context": llm_ctx or regex_ctx,
                    "check_method": "hybrid",
                }
        if llm_adapter:
            llm_found, llm_score, llm_ctx = await self._detect_mention_llm(response, query, llm_adapter)
            return {
                "brand_mentioned": llm_found,
                "mention_score": llm_score if llm_score is not None else regex_conf,
                "mention_context": llm_ctx,
                "check_method": "llm",
            }
        return {
            "brand_mentioned": regex_found,
            "mention_score": regex_conf,
            "mention_context": regex_ctx,
            "check_method": "regex",
        }

    def _select_queries(
        self, sandtable_type: str, categories: list[str], max_per: int
    ) -> list[dict]:
        """从预设+自定义查询中选择查询"""
        selected = []
        sandtable_label = SandtableType(sandtable_type).label
        for cat in categories:
            roles = CATEGORY_TO_ROLES.get(cat, [UserRole.B_END_PROCUREMENT])
            for role in roles:
                templates = ROLE_QUESTIONS.get(role, [])
                for tmpl in templates[:max_per]:
                    query_text = tmpl.replace("{type}", sandtable_label)
                    selected.append({"text": query_text, "category": cat})
                if len([q for q in selected if q["category"] == cat]) >= max_per:
                    break
        return selected[:max_per * len(categories)]

    async def check_single_platform(
        self, platform: str, queries: list[dict], sandtable_type: str
    ) -> list[dict]:
        """单平台品牌收录检测"""
        api_keys = self.api_keys.get("platforms", {}).get(platform, {})
        api_key = api_keys.get("api_key", "")
        if not api_key or "your-" in api_key:
            return [{
                "platform": platform, "query": q["text"], "query_category": q["category"],
                "brand_mentioned": False, "mention_score": 0, "mention_context": "",
                "full_response": None, "check_method": "unavailable",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            } for q in queries]

        plat_cfg = self.settings.get("llm", {}).get("platforms", {}).get(platform, {})
        try:
            ail_platform = AIPlatform(platform)
            adapter_type = ail_platform.adapter_type
        except ValueError:
            adapter_type = "openai_compat"

        llm = LLMFactory.create(
            platform=adapter_type,
            api_key=api_key,
            model_name=plat_cfg.get("model_name", ""),
            base_url=plat_cfg.get("base_url"),
        )

        results = []
        for q in queries:
            cache_key = f"brand_check:{hashlib.md5((platform + q['text']).encode()).hexdigest()}"
            cached = eval_cache.get(cache_key)
            if cached is not None:
                results.append(cached)
                continue

            checked_at = datetime.now(timezone.utc).isoformat()
            try:
                messages = [LLMMessage(role="user", content=q["text"])]
                resp = await async_retry(llm.chat, messages, temperature=0.3, max_tokens=1024)
                detection = await self._detect_mention(resp.content, q["text"], llm)
                entry = {
                    "platform": platform,
                    "query": q["text"],
                    "query_category": q.get("category", "brand_direct"),
                    "brand_mentioned": detection["brand_mentioned"],
                    "mention_score": detection["mention_score"],
                    "mention_context": detection.get("mention_context", ""),
                    "full_response": resp.content[:500],
                    "check_method": detection.get("check_method", "regex"),
                    "checked_at": checked_at,
                }
            except Exception as e:
                logger.warning(f"Brand check failed for {platform}: {e}")
                entry = {
                    "platform": platform,
                    "query": q["text"],
                    "query_category": q.get("category", "brand_direct"),
                    "brand_mentioned": False,
                    "mention_score": 0,
                    "mention_context": f"Error: {e}",
                    "full_response": None,
                    "check_method": "error",
                    "checked_at": checked_at,
                }

            results.append(entry)
            eval_cache.set(cache_key, entry)

        return results

    async def check_all_platforms(
        self,
        platforms: list[str],
        query_categories: list[str],
        max_per_category: int,
        sandtable_type: str,
    ) -> dict:
        """全平台品牌收录检测"""
        from pathlib import Path
        import json

        if not platforms:
            platforms = [
                p for p in ["deepseek", "doubao", "tongyi", "wenxin", "kimi", "yuanbao", "xinghuo"]
                if p in self.api_keys.get("platforms", {})
            ]
            if not platforms:
                platforms = list(self.api_keys.get("platforms", {}).keys())
            if not platforms:
                platforms = ["deepseek"]

        queries = self._select_queries(sandtable_type, query_categories, max_per_category)
        if not queries:
            queries = self._select_queries(sandtable_type, ["brand_direct", "scenario"], max_per_category)

        session_id = f"mon_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        created_at = datetime.now(timezone.utc).isoformat()
        all_results = []
        platforms_checked = []
        delay = self.settings.get("brand_monitor", {}).get("platform_check_delay", 2)

        for i, platform in enumerate(platforms):
            if i > 0:
                await asyncio.sleep(delay)
            results = await self.check_single_platform(platform, queries, sandtable_type)
            all_results.extend(results)
            platforms_checked.append(platform)

        mentioned_count = sum(1 for r in all_results if r.get("brand_mentioned"))
        total_queries = len(all_results)
        mention_rate = round(mentioned_count / total_queries * 100, 1) if total_queries > 0 else 0.0

        from pathlib import Path as P
        data_dir = P(__file__).resolve().parent.parent.parent / "data" / "brand_mentions" / "sessions"
        data_dir.mkdir(parents=True, exist_ok=True)

        session = {
            "session_id": session_id,
            "created_at": created_at,
            "sandtable_type": sandtable_type,
            "platforms_checked": platforms_checked,
            "total_queries": total_queries,
            "mentioned_count": mentioned_count,
            "mention_rate": mention_rate,
            "results": all_results,
        }

        session_path = data_dir / f"{session_id}.json"
        with open(session_path, "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)

        return session
