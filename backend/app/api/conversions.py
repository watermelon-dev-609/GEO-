"""转化归因 API — 转化事件记录、归因分析、全链路漏斗"""

import logging
from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import ConversionEventCreate
from app.core.conversion_attribution import (
    record_conversion, load_conversion_events, delete_conversion_event,
    get_attribution, calculate_full_funnel,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 转化事件 ──

@router.post("/event")
async def create_conversion_event(data: ConversionEventCreate):
    """记录一条转化事件（Webhook端点）

    外部系统（网站、CRM）可调用此端点将转化事件推送到GEO平台。
    系统会自动解析referrer中的UTM参数并匹配AI平台归因。

    示例请求体：
    ```json
    {
        "type": "form_submit",
        "value": 5000.0,
        "landing_page": "https://example.com/contact?utm_source=doubao&utm_medium=ai_referral",
        "referrer": "https://doubao.com/...",
        "source": "webhook"
    }
    ```
    """
    event = record_conversion(data.model_dump())
    return {"status": "ok", "event": event}


@router.get("/events")
async def list_events(days: int = Query(default=30, ge=1, le=365)):
    """列出最近的转化事件"""
    events = load_conversion_events(days=days)
    return {"status": "ok", "events": events, "total": len(events)}


@router.delete("/event/{event_id}")
async def delete_event(event_id: str):
    """删除转化事件"""
    if not delete_conversion_event(event_id):
        raise HTTPException(status_code=404, detail=f"转化事件不存在: {event_id}")
    return {"status": "ok", "message": f"转化事件 {event_id} 已删除"}


# ── 归因分析 ──

@router.get("/attribution")
async def get_conversion_attribution(
    days: int = Query(default=30, ge=1, le=365),
    model: str = Query(default="last_click", description="归因模型: last_click/first_click/linear/time_decay/position_based"),
):
    """获取转化归因分析

    返回按来源、AI平台、转化类型分组的归因数据。
    """
    valid_models = ("last_click", "first_click", "linear", "time_decay", "position_based")
    if model not in valid_models:
        raise HTTPException(status_code=400, detail=f"不支持的归因模型: {model}。支持: {', '.join(valid_models)}")

    attribution = get_attribution(days=days, model=model)
    return {"status": "ok", **attribution}


# ── 全链路漏斗 ──

@router.get("/funnel")
async def get_full_funnel(days: int = Query(default=30, ge=1, le=365)):
    """获取全链路转化漏斗数据

    漏斗阶段：AI曝光 → AI引用 → 网站访问 → 转化

    Returns:
        {
            period_start, period_end,
            stages: [{stage_name, label, count, rate_to_previous_pct}],
            overall_conversion_rate_pct,
            platform_breakdown: {doubao: {impressions, citations, visits, conversions}, ...}
        }
    """
    funnel = calculate_full_funnel(days=days)
    return {"status": "ok", **funnel}


@router.get("/trend")
async def get_conversion_trend(days: int = Query(default=30, ge=1, le=365)):
    """获取转化趋势数据（按日聚合）"""
    events = load_conversion_events(days=days)
    if not events:
        return {"status": "ok", "trend": [], "total": 0}

    # 按日聚合
    by_date: dict[str, dict] = {}
    for e in events:
        date_key = e.get("timestamp", "")[:10]
        if date_key not in by_date:
            by_date[date_key] = {
                "date": date_key,
                "total": 0,
                "ai_attributed": 0,
                "total_value": 0.0,
            }
        by_date[date_key]["total"] += 1
        if e.get("is_ai_referral") or e.get("ai_platform"):
            by_date[date_key]["ai_attributed"] += 1
        by_date[date_key]["total_value"] += e.get("value", 0)

    trend = sorted(by_date.values(), key=lambda x: x["date"])

    return {
        "status": "ok",
        "trend": trend,
        "total": len(events),
        "dates": len(trend),
    }


@router.get("/by-ai-platform")
async def get_conversions_by_ai_platform(days: int = Query(default=30, ge=1, le=365)):
    """按AI平台分组的转化数据"""
    events = load_conversion_events(days=days)
    ai_events = [e for e in events if e.get("is_ai_referral") or e.get("ai_platform")]

    by_platform: dict[str, dict] = {}
    for e in ai_events:
        plat = e.get("ai_platform", "unknown")
        if plat not in by_platform:
            by_platform[plat] = {
                "platform": plat,
                "conversions": 0,
                "total_value": 0.0,
                "types": {},
            }
        by_platform[plat]["conversions"] += 1
        by_platform[plat]["total_value"] += e.get("value", 0)
        conv_type = e.get("type", "custom")
        by_platform[plat]["types"][conv_type] = by_platform[plat]["types"].get(conv_type, 0) + 1

    result = sorted(by_platform.values(), key=lambda x: x["conversions"], reverse=True)

    return {
        "status": "ok",
        "platforms": result,
        "total_ai_conversions": len(ai_events),
        "total_non_ai_conversions": len(events) - len(ai_events),
    }
