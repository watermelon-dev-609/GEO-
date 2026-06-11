"""API用量监控路由"""

import time
from fastapi import APIRouter, Query
from app.core.usage_monitor import UsageMonitor

router = APIRouter()


@router.get("/summary")
async def usage_summary(date: str | None = Query(default=None, description="日期 YYYY-MM-DD")):
    """获取用量摘要"""
    monitor = UsageMonitor()
    return monitor.get_summary(date)


@router.get("/history")
async def usage_history(days: int = Query(default=7, ge=1, le=90)):
    """获取历史用量趋势"""
    monitor = UsageMonitor()
    return monitor.get_history(days)


@router.get("/alerts")
async def usage_alerts():
    """获取配额告警"""
    monitor = UsageMonitor()
    quota = monitor.check_quota()
    return quota
