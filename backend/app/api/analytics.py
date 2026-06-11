"""数据看板统计接口 — 聚合评测历史、生成趋势数据"""

import logging
from datetime import datetime
from fastapi import APIRouter
from app.core.eval_history_store import load_all_sessions

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/overview")
async def get_analytics_overview():
    """聚合统计：评测总数、平均分、趋势、平台分布"""
    sessions = load_all_sessions()
    scored = [s for s in sessions if s.get("overall_score") is not None]

    total = len(scored)
    avg_score = round(sum(s["overall_score"] for s in scored) / total, 1) if total else 0

    # 沙盘分布
    sandtable_dist = {}
    for s in scored:
        st = s.get("sandtable_type", "unknown")
        sandtable_dist[st] = sandtable_dist.get(st, 0) + 1

    # 平台分布
    platform_dist = {}
    for s in sessions:
        for p in s.get("platforms", []):
            platform_dist[p] = platform_dist.get(p, 0) + 1

    # 趋势数据（按日期分组）
    trend_data = _build_trend(scored)

    # 维度平均分
    dim_avgs = _build_dimension_avgs(scored)

    # 改进率统计
    improved = 0
    regressed = 0
    for s in scored:
        comp = s.get("phases", {}).get("comprehensive", {}).get("result", {})
        comparison = comp.get("before_after_comparison")
        if comparison and comparison.get("improvement_percent", 0) > 0:
            improved += 1
        elif comparison and comparison.get("improvement_percent", 0) < 0:
            regressed += 1

    return {
        "overview": {
            "total_evaluations": len(sessions),
            "scored_evaluations": total,
            "average_score": avg_score,
            "improved_count": improved,
            "regressed_count": regressed,
            "improvement_rate": round(improved / max(total, 1) * 100, 1),
        },
        "sandtable_distribution": sandtable_dist,
        "platform_distribution": platform_dist,
        "trend": trend_data,
        "dimension_averages": dim_avgs,
    }


def _build_trend(scored_sessions: list) -> list:
    """按日期聚合趋势"""
    from collections import defaultdict
    by_date = defaultdict(list)
    for s in scored_sessions:
        created = s.get("created_at", "")
        date_key = created[:10] if created else "unknown"
        by_date[date_key].append(s["overall_score"])

    trend = []
    for date_key in sorted(by_date.keys())[-30:]:
        scores = by_date[date_key]
        trend.append({
            "date": date_key,
            "avg_score": round(sum(scores) / len(scores), 1),
            "count": len(scores),
        })
    return trend


def _build_dimension_avgs(scored_sessions: list) -> dict:
    """计算各维度平均分"""
    from collections import defaultdict
    dim_sums = defaultdict(float)
    dim_counts = defaultdict(int)
    for s in scored_sessions:
        comp = s.get("phases", {}).get("comprehensive", {}).get("result", {})
        dims = comp.get("dimension_scores", {})
        for key, val in dims.items():
            if val is not None and val > 0:
                dim_sums[key] += val
                dim_counts[key] += 1
    return {k: round(dim_sums[k] / dim_counts[k], 1) for k in dim_sums}


@router.get("/trend")
async def get_trend(days: int = 30):
    """获取趋势数据"""
    from datetime import datetime, timedelta, timezone
    sessions = load_all_sessions()
    scored = [s for s in sessions if s.get("overall_score") is not None]
    # 使用 UTC 时间与 created_at 的 ISO 格式保持一致，避免时区偏差导致过滤不准
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    recent = [s for s in scored if s.get("created_at", "")[:10] >= cutoff]
    return {"trend": _build_trend(recent)}


@router.get("/init")
async def init_sample_data():
    """首次使用：检查是否需要初始化"""
    sessions = load_all_sessions()
    if len(sessions) > 0:
        return {"initialized": False, "message": "已有评测数据"}

    return {"initialized": False, "message": "暂无评测数据，请通过评测中心创建首次评测"}


@router.get("/full-funnel")
async def get_full_funnel_analytics(days: int = 30):
    """获取全链路漏斗数据（集成流量+转化+AI引用）"""
    try:
        from app.core.conversion_attribution import calculate_full_funnel
        funnel = calculate_full_funnel(days=days)
        return {"status": "ok", **funnel}
    except Exception as e:
        logger.error(f"全链路漏斗计算失败: {e}")
        return {
            "status": "error",
            "message": f"漏斗计算失败: {str(e)}",
            "period_start": "",
            "period_end": "",
            "stages": [],
            "overall_conversion_rate_pct": 0.0,
        }
