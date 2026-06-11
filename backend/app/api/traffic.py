"""流量分析 API — 流量源配置、数据拉取、汇总查询"""

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import (
    TrafficSourceConfig, TrafficSourceConfigUpdateRequest,
    TrafficSummaryResponse, TrafficTrendPoint,
)
from app.core.traffic_connector import (
    _get_config, save_config,
    load_traffic_snapshots, get_traffic_summary,
    fetch_and_store_traffic,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 配置 ──

@router.get("/config")
async def get_traffic_config():
    """获取流量数据源配置"""
    config = _get_config()
    sources = config.get("sources", {})

    result = {}
    for src_id in ("ga4", "baidu_tongji"):
        src_cfg = sources.get(src_id, {})
        result[src_id] = {
            "source": src_id,
            "enabled": src_cfg.get("enabled", False),
            "property_id": src_cfg.get("property_id", ""),
            "credentials_set": bool(src_cfg.get("credentials_json") or src_cfg.get("api_key")),
            "fetch_interval_hours": src_cfg.get("fetch_interval_hours", 24),
        }

    return {"status": "ok", "sources": result}


@router.post("/config")
async def save_traffic_config(data: TrafficSourceConfigUpdateRequest):
    """更新流量数据源配置"""
    config = _get_config()
    sources = config.setdefault("sources", {})

    src_cfg = sources.get(data.source, {})
    if data.enabled is not None:
        src_cfg["enabled"] = data.enabled
    if data.property_id is not None:
        src_cfg["property_id"] = data.property_id
    if data.credentials_info is not None:
        src_cfg.update(data.credentials_info)
    if data.fetch_interval_hours is not None:
        src_cfg["fetch_interval_hours"] = data.fetch_interval_hours

    sources[data.source] = src_cfg
    config["sources"] = sources
    save_config(config)

    logger.info(f"流量源配置已更新: {data.source} (enabled={src_cfg.get('enabled', False)})")
    return {"status": "ok", "message": f"流量源 {data.source} 配置已保存"}


# ── 数据拉取 ──

@router.post("/fetch/{source}")
async def trigger_fetch(source: str, date: str = Query(default="", description="日期 YYYY-MM-DD，空则拉取昨天")):
    """手动触发流量数据拉取"""
    if source not in ("ga4", "baidu_tongji"):
        raise HTTPException(status_code=400, detail=f"不支持的数据源: {source}。仅支持 ga4 / baidu_tongji")

    config = _get_config()
    src_cfg = config.get("sources", {}).get(source, {})
    if not src_cfg.get("enabled", False):
        raise HTTPException(status_code=400, detail=f"数据源 {source} 未启用，请先在配置中启用")

    if not date:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    snapshot = await fetch_and_store_traffic(source, date)

    if snapshot.get("error"):
        return {"status": "warning", "message": f"数据拉取完成，但存在问题", "snapshot": snapshot}

    return {"status": "ok", "message": f"{source} 流量数据已拉取 ({date})", "snapshot": snapshot}


# ── 查询 ──

@router.get("/summary")
async def get_summary(days: int = Query(default=30, ge=1, le=365)):
    """获取流量汇总（最近N天）"""
    summary = get_traffic_summary(days=days)
    return {"status": "ok", **summary}


@router.get("/daily/{date}")
async def get_daily_snapshot(date: str):
    """获取指定日期的流量快照"""
    snapshots = load_traffic_snapshots(days=1, source="")
    # 精确匹配日期
    for s in snapshots:
        if s.get("date") == date:
            return {"status": "ok", "snapshot": s}
    return {"status": "ok", "snapshot": None, "message": f"未找到 {date} 的流量数据"}


@router.get("/trend")
async def get_traffic_trend(days: int = Query(default=30, ge=1, le=365)):
    """获取流量趋势数据"""
    snapshots = load_traffic_snapshots(days=days)
    trend = []
    for s in snapshots:
        trend.append({
            "date": s.get("date", ""),
            "page_views": s.get("page_views", 0),
            "unique_visitors": s.get("unique_visitors", 0),
            "ai_referral_visits": s.get("ai_referral_visits", 0),
            "bounce_rate_pct": s.get("bounce_rate_pct", 0.0),
        })
    return {"status": "ok", "trend": trend, "count": len(trend)}


@router.get("/sources")
async def get_traffic_sources(days: int = Query(default=30, ge=1, le=365)):
    """对比流量来源分布"""
    summary = get_traffic_summary(days=days)
    return {
        "status": "ok",
        "by_source": summary.get("by_source", {}),
        "ai_referral_visits": summary.get("ai_referral_visits", 0),
        "total_page_views": summary.get("total_page_views", 0),
    }
