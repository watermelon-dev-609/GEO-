"""数据看板统计接口 — 聚合评测历史、生成趋势数据"""

import json
import logging
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter
from app.core.eval_history_store import load_all_sessions

logger = logging.getLogger(__name__)
router = APIRouter()

SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "samples"


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
    from datetime import datetime, timedelta
    sessions = load_all_sessions()
    scored = [s for s in sessions if s.get("overall_score") is not None]
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    recent = [s for s in scored if s.get("created_at", "")[:10] >= cutoff]
    return {"trend": _build_trend(recent)}


@router.get("/init")
async def init_sample_data():
    """首次使用：检查评测数据为空时加载示例数据"""
    sessions = load_all_sessions()
    if len(sessions) > 0:
        return {"initialized": False, "message": "已有评测数据"}

    sample_file = SAMPLES_DIR / "smart_agriculture_sample.json"
    if not sample_file.exists():
        return {"initialized": False, "message": "示例数据文件不存在"}

    with open(sample_file, "r", encoding="utf-8") as f:
        sample = json.load(f)

    sample_text = sample.get("sample_text", "")
    sample_eval = sample.get("sample_evaluation", {})

    # 构造评测历史条目并保存
    now = datetime.now().isoformat()
    entry = {
        "session_id": f"sample_smart_agriculture_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "sandtable_type": "smart_agriculture",
        "overall_score": sample_eval.get("overall_score", 78),
        "created_at": now,
        "evaluated_text": sample_text[:5000],
        "original_text": sample_text[:5000],
        "platforms": ["deepseek"],
        "mode": "sample",
        "phases": {
            "comprehensive": {
                "result": {
                    "dimension_scores": sample_eval.get("dimension_scores", {}),
                    "weak_points": sample_eval.get("weak_points", []),
                    "strengths": sample_eval.get("strengths", []),
                    "before_after_comparison": sample_eval.get("before_after_comparison", {}),
                }
            }
        },
    }

    # 直接写入评测历史目录
    from app.core.eval_history_store import _get_history_dir
    history_dir = _get_history_dir()
    filepath = history_dir / f"{entry['session_id']}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"示例数据已初始化: {filepath}")
    return {"initialized": True, "message": "示例数据已加载"}
