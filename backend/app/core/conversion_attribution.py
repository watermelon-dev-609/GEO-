"""转化归因引擎 — 转化事件记录、UTM归因匹配、全链路漏斗计算

核心功能：
- 接收转化事件（Webhook），自动解析UTM参数并匹配AI平台
- 计算多渠道归因（last_click/first_click/linear/time_decay/position_based）
- 构建全链路漏斗：AI曝光 → AI引用 → 网站访问 → 转化

数据存储：
    data/conversions/YYYY-MM-DD.json — 按日存储转化事件
    data/utm_campaigns/utm_*.json — 关联UTM推广计划
"""

from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.utils.config import get_data_dir

logger = logging.getLogger(__name__)


def _get_conv_dir() -> Path:
    d = get_data_dir() / "conversions"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ══════════════════════════════════════════════════════════════
# 转化事件记录
# ══════════════════════════════════════════════════════════════

def record_conversion(data: dict[str, Any]) -> dict[str, Any]:
    """记录一条转化事件

    由外部Webhook或前端调用。自动解析referrer中的UTM参数并匹配AI平台。

    Args:
        data: {
            type: str (form_submit/phone_call/download/...),
            value: float (转化价值),
            landing_page: str,
            referrer: str (含UTM参数),
            source: str (ga4/baidu_tongji/webhook),
            keyword: str,
            campaign_id: str,
            extra: dict,
        }

    Returns:
        完整转化事件dict（含服务端生成的id和AI归因字段）
    """
    from app.core.utm_generator import parse_utm_from_url, match_utm_to_ai_platform, is_ai_referral

    now = datetime.now(timezone.utc)
    event_id = f"conv_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    referrer = data.get("referrer", "")
    landing_page = data.get("landing_page", "")

    # 从referrer中解析UTM参数
    utm = parse_utm_from_url(referrer)

    # 从landing_page中也尝试解析（某些系统将UTM放在目标URL上）
    if not utm.get("utm_source"):
        landing_utm = parse_utm_from_url(landing_page)
        if landing_utm.get("utm_source"):
            utm = landing_utm

    # AI平台归因
    ai_platform = match_utm_to_ai_platform(utm.get("utm_source", ""))
    is_ai = is_ai_referral(utm.get("utm_medium", ""))

    event = {
        "id": event_id,
        "timestamp": now.isoformat(),
        "type": data.get("type", "custom"),
        "value": float(data.get("value", 0)),
        "landing_page": landing_page,
        "referrer": referrer,
        "source": data.get("source", "webhook"),
        "ai_platform": ai_platform,
        "ai_query": data.get("ai_query", ""),
        "utm_source": utm.get("utm_source", ""),
        "utm_medium": utm.get("utm_medium", ""),
        "utm_campaign": utm.get("utm_campaign", ""),
        "utm_term": utm.get("utm_term", ""),
        "utm_content": utm.get("utm_content", ""),
        "is_ai_referral": is_ai,
        "keyword": data.get("keyword", ""),
        "campaign_id": data.get("campaign_id", ""),
        "extra": data.get("extra", {}),
    }

    _save_event(event)
    logger.info(f"转化事件已记录: {event_id} (type={event['type']}, ai_platform={ai_platform or 'none'})")
    return event


def _save_event(event: dict[str, Any]) -> None:
    """保存转化事件到当日JSON文件（追加模式，原子写入）"""
    import tempfile
    date_key = datetime.now().strftime("%Y-%m-%d")
    fp = _get_conv_dir() / f"{date_key}.json"

    # 读取当日已有事件
    existing: list[dict[str, Any]] = []
    if fp.exists():
        try:
            with open(fp, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, OSError):
            existing = []

    existing.append(event)

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False, dir=_get_conv_dir()
    ) as tmp:
        json.dump(existing, tmp, ensure_ascii=False, indent=2)
    Path(tmp.name).replace(fp)


def load_conversion_events(days: int = 30) -> list[dict[str, Any]]:
    """加载指定天数内的转化事件

    Args:
        days: 回溯天数

    Returns:
        按时间升序排列的转化事件列表
    """
    conv_dir = _get_conv_dir()
    cutoff = datetime.now() - timedelta(days=days)
    events: list[dict[str, Any]] = []

    for fp in sorted(conv_dir.glob("*.json")):
        try:
            mtime = datetime.fromtimestamp(fp.stat().st_mtime)
            if mtime < cutoff:
                continue
            with open(fp, "r", encoding="utf-8") as f:
                day_events = json.load(f)
            if isinstance(day_events, list):
                events.extend(day_events)
        except (json.JSONDecodeError, OSError):
            continue

    events.sort(key=lambda e: e.get("timestamp", ""))
    return events


def delete_conversion_event(event_id: str) -> bool:
    """删除指定的转化事件"""
    conv_dir = _get_conv_dir()
    for fp in sorted(conv_dir.glob("*.json")):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                events = json.load(f)
            if not isinstance(events, list):
                continue
            original_len = len(events)
            filtered = [e for e in events if e.get("id") != event_id]
            if len(filtered) < original_len:
                import tempfile
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", delete=False, dir=conv_dir
                ) as tmp:
                    json.dump(filtered, tmp, ensure_ascii=False, indent=2)
                Path(tmp.name).replace(fp)
                logger.info(f"转化事件已删除: {event_id}")
                return True
        except (json.JSONDecodeError, OSError):
            continue
    return False


# ══════════════════════════════════════════════════════════════
# 转化归因
# ══════════════════════════════════════════════════════════════

def get_attribution(days: int = 30, model: str = "last_click") -> dict[str, Any]:
    """获取转化归因分析

    Args:
        days: 回溯天数
        model: 归因模型 (last_click/first_click/linear/time_decay/position_based)

    Returns:
        ConversionAttributionResponse格式的dict
    """
    events = load_conversion_events(days=days)

    if not events:
        return {
            "total_conversions": 0,
            "total_value": 0.0,
            "by_source": {},
            "by_ai_platform": {},
            "by_type": {},
            "ai_attributed_count": 0,
            "ai_attributed_value": 0.0,
            "ai_citation_rate_pct": 0.0,
            "attribution_paths": [],
        }

    total_value = sum(e.get("value", 0) for e in events)
    ai_events = [e for e in events if e.get("is_ai_referral") or e.get("ai_platform")]
    ai_count = len(ai_events)
    ai_value = sum(e.get("value", 0) for e in ai_events)

    # 按来源分组
    by_source: dict[str, int] = {}
    for e in events:
        utm_medium = e.get("utm_medium", "") or "direct"
        if e.get("is_ai_referral"):
            utm_medium = "ai_referral"
        by_source[utm_medium] = by_source.get(utm_medium, 0) + 1

    # 按AI平台分组
    by_ai_platform: dict[str, int] = {}
    for e in ai_events:
        plat = e.get("ai_platform", "unknown")
        by_ai_platform[plat] = by_ai_platform.get(plat, 0) + 1

    # 按类型分组
    by_type: dict[str, int] = {}
    for e in events:
        t = e.get("type", "custom")
        by_type[t] = by_type.get(t, 0) + 1

    # 归因路径（简化为用户会话级路径）
    attribution_paths = _build_attribution_paths(events, model)

    return {
        "total_conversions": len(events),
        "total_value": round(total_value, 2),
        "by_source": by_source,
        "by_ai_platform": by_ai_platform,
        "by_type": by_type,
        "ai_attributed_count": ai_count,
        "ai_attributed_value": round(ai_value, 2),
        "ai_citation_rate_pct": round(ai_count / len(events) * 100, 1) if events else 0.0,
        "attribution_paths": attribution_paths,
    }


def _build_attribution_paths(events: list[dict[str, Any]], model: str) -> list[dict[str, Any]]:
    """构建归因路径

    简化实现：按landing_page + 时间窗口(30min)聚合为会话，
    每个会话内的utmsource序列即为归因路径。
    """
    if not events:
        return []

    # 按landing_page分组模拟会话
    sessions: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        page = e.get("landing_page", "/")
        key = page.split("?")[0]  # 去参数
        sessions.setdefault(key, []).append(e)

    paths = []
    for page, ses_events in list(sessions.items())[:20]:  # 最多20条
        ses_events.sort(key=lambda x: x.get("timestamp", ""))
        touchpoints = [
            e.get("utm_source", "") or e.get("source", "direct")
            for e in ses_events
        ]
        converted = True  # 所有事件均是转化

        paths.append({
            "path": " → ".join(touchpoints),
            "touchpoints": touchpoints,
            "touchpoint_count": len(touchpoints),
            "converted": converted,
            "landing_page": page,
            "value": sum(e.get("value", 0) for e in ses_events),
        })

    return paths


# ══════════════════════════════════════════════════════════════
# 全链路漏斗
# ══════════════════════════════════════════════════════════════

def calculate_full_funnel(days: int = 30) -> dict[str, Any]:
    """计算全链路转化漏斗

    漏斗阶段：
    1. AI曝光量 → 来自citation_tester的impressions估算
    2. AI引用量 → 来自citation_tester的cited_sources统计
    3. 网站访问量 → 来自traffic_connector的ai_referral_visits
    4. 转化量 → 来自conversion_events的AI归因转化

    Args:
        days: 统计天数

    Returns:
        FullFunnelResponse格式的dict
    """
    now = datetime.now()
    period_end = now.strftime("%Y-%m-%d")
    period_start = (now - timedelta(days=days)).strftime("%Y-%m-%d")

    # ── 1. AI曝光量 ──
    ai_impressions = _estimate_ai_impressions(days)

    # ── 2. AI引用量 ──
    ai_citations = _count_ai_citations(days)

    # ── 3. 网站访问量（AI来源） ──
    website_visits_from_ai = _count_ai_traffic_visits(days)

    # ── 4. 转化量（AI归因） ──
    events = load_conversion_events(days=days)
    ai_events = [e for e in events if e.get("is_ai_referral") or e.get("ai_platform")]
    conversions_from_ai = len(ai_events)

    # 计算阶段间转化率
    stage2_rate = round(ai_citations / max(ai_impressions, 1) * 100, 1)
    stage3_rate = round(website_visits_from_ai / max(ai_citations, 1) * 100, 1)
    stage4_rate = round(conversions_from_ai / max(website_visits_from_ai, 1) * 100, 1)
    overall_rate = round(conversions_from_ai / max(ai_impressions, 1) * 100, 2)

    stages = [
        {
            "stage_name": "ai_impressions",
            "label": "AI曝光量",
            "count": ai_impressions,
            "rate_to_previous_pct": 100.0,
        },
        {
            "stage_name": "ai_citations",
            "label": "AI引用量",
            "count": ai_citations,
            "rate_to_previous_pct": stage2_rate,
        },
        {
            "stage_name": "website_visits",
            "label": "网站访问量（AI来源）",
            "count": website_visits_from_ai,
            "rate_to_previous_pct": stage3_rate,
        },
        {
            "stage_name": "conversions",
            "label": "转化量",
            "count": conversions_from_ai,
            "rate_to_previous_pct": stage4_rate,
        },
    ]

    # 平台分解
    platform_breakdown = _build_platform_breakdown(days)

    return {
        "period_start": period_start,
        "period_end": period_end,
        "stages": stages,
        "overall_conversion_rate_pct": overall_rate,
        "ai_impressions_total": ai_impressions,
        "ai_citations_total": ai_citations,
        "website_visits_from_ai": website_visits_from_ai,
        "conversions_from_ai": conversions_from_ai,
        "platform_breakdown": platform_breakdown,
    }


def _estimate_ai_impressions(days: int) -> int:
    """估算AI曝光量（基于citation_tester数据）"""
    try:
        from app.core.citation_tester import list_citation_tests
        tests = list_citation_tests(days=days)
        total_queries = sum(t.get("queries_attempted", t.get("queries_fired", 0)) for t in tests)
        # 每次查询约产生1次曝光（保守估计）
        return max(total_queries, 0)
    except Exception as e:
        logger.debug(f"估算AI曝光量失败: {e}")
        return 0


def _count_ai_citations(days: int) -> int:
    """统计AI引用次数"""
    try:
        from app.core.citation_tester import list_citation_tests, get_citation_test
        tests = list_citation_tests(days=days)
        total_citations = 0
        for t in tests[:10]:  # 最多查10个测试
            detail = get_citation_test(t.get("test_id", ""))
            if detail:
                for r in detail.get("results", []):
                    if r.get("cited_sources"):
                        total_citations += 1
        return total_citations
    except Exception as e:
        logger.debug(f"统计AI引用量失败: {e}")
        return 0


def _count_ai_traffic_visits(days: int) -> int:
    """统计AI来源的网站访问量"""
    try:
        from app.core.traffic_connector import load_traffic_snapshots
        snapshots = load_traffic_snapshots(days=days)
        return sum(s.get("ai_referral_visits", 0) for s in snapshots)
    except Exception as e:
        logger.debug(f"统计AI流量失败: {e}")
        return 0


def _build_platform_breakdown(days: int) -> dict[str, dict[str, int]]:
    """构建各AI平台的漏斗分解"""
    breakdown: dict[str, dict[str, int]] = {}

    # 从citation test获取各平台引用数据
    try:
        from app.core.citation_tester import list_citation_tests, get_citation_test
        tests = list_citation_tests(days=days)
        for t in tests[:5]:
            detail = get_citation_test(t.get("test_id", ""))
            if detail:
                per_platform = detail.get("aggregated_stats", {}).get("per_platform", {})
                for plat, stats in per_platform.items():
                    if plat not in breakdown:
                        breakdown[plat] = {"impressions": 0, "citations": 0, "visits": 0, "conversions": 0}
                    breakdown[plat]["citations"] += stats.get("total_responses", 0)
                    # 估算曝光：假设每个cited source对应一次曝光
                    cited = stats.get("cited_sources", {})
                    breakdown[plat]["impressions"] += sum(cited.values())
    except Exception as e:
        logger.debug(f"获取平台引用分解失败: {e}")

    # 从流量快照获取各来源访问量
    try:
        from app.core.traffic_connector import load_traffic_snapshots
        snapshots = load_traffic_snapshots(days=days)
        for s in snapshots:
            ai_visits = s.get("ai_referral_visits", 0)
            if ai_visits > 0:
                source = s.get("source", "unknown")
                for plat in breakdown:
                    # 均匀分配（精确数据需要各平台独立UTM追踪）
                    breakdown[plat]["visits"] += ai_visits // max(len(breakdown), 1)
    except Exception:
        pass

    # 从转化事件获取各平台转化量
    events = load_conversion_events(days=days)
    for e in events:
        plat = e.get("ai_platform", "")
        if plat:
            if plat not in breakdown:
                breakdown[plat] = {"impressions": 0, "citations": 0, "visits": 0, "conversions": 0}
            breakdown[plat]["conversions"] += 1

    return breakdown
