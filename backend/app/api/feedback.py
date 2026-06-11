"""数据闭环 API — 指标查询、采信下降检测、迭代建议"""

import logging
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/metrics/current")
async def get_current_metrics(platform_id: str = ""):
    """获取当前周指标"""
    try:
        from app.core.feedback_loop import calculate_weekly_metrics
        pid = platform_id if platform_id else None
        result = calculate_weekly_metrics(pid)
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取指标失败: {e}")


@router.get("/metrics/{platform_id}")
async def get_platform_metrics(platform_id: str):
    """获取指定平台当前指标"""
    try:
        from app.core.feedback_loop import calculate_weekly_metrics
        result = calculate_weekly_metrics(platform_id)
        platform_data = result.get("platforms", {}).get(platform_id, {})
        return {"status": "ok", "platform_id": platform_id, "metrics": platform_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取平台指标失败: {e}")


@router.get("/metrics/{platform_id}/trend")
async def get_metrics_trend(platform_id: str, weeks: int = 12):
    """获取指标趋势数据"""
    try:
        from app.core.feedback_loop import get_metrics_history
        history = get_metrics_history(platform_id, weeks)
        return {"status": "ok", "platform_id": platform_id, "weeks": weeks, "history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取趋势失败: {e}")


@router.get("/citation-drop/{platform_id}")
async def check_citation_drop(platform_id: str):
    """检测采信率是否下降"""
    try:
        from app.core.feedback_loop import detect_citation_drop
        result = detect_citation_drop(platform_id)
        if result is None:
            return {"status": "ok", "platform_id": platform_id, "dropping": False, "message": "采信率稳定"}
        return {"status": "ok", "platform_id": platform_id, "dropping": True, "details": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检测失败: {e}")


@router.post("/diagnose/{platform_id}")
async def diagnose_platform(platform_id: str):
    """运行完整诊断 + 迭代建议"""
    try:
        from app.core.feedback_loop import (
            generate_iteration_recommendation, save_iteration_recommendation
        )
        result = generate_iteration_recommendation(platform_id)
        save_iteration_recommendation(result)
        return {"status": "ok", "platform_id": platform_id, "recommendation": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"诊断失败: {e}")


@router.get("/iteration-history")
async def get_iteration_history(limit: int = 20):
    """获取迭代历史"""
    try:
        from app.core.feedback_loop import get_iteration_history
        history = get_iteration_history(limit)
        return {"status": "ok", "total": len(history), "history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取迭代历史失败: {e}")


# ── v2.1.1 闭环编排 API ──

@router.post("/closed-loop/{platform_id}")
async def trigger_closed_loop(platform_id: str, content_text: str = ""):
    """触发完整闭环：检测→诊断→修复→验证

    这是串联所有模块的核心编排端点。
    """
    try:
        from app.core.orchestrator import run_closed_loop
        text = content_text if content_text.strip() else None
        result = await run_closed_loop(platform_id, text)
        return {"status": "ok", "report": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"闭环执行失败: {e}")


@router.get("/closed-loop/history")
async def get_closed_loop_history(platform_id: str = "", limit: int = 20):
    """获取闭环运行历史"""
    try:
        from app.core.orchestrator import list_closed_loop_runs
        runs = list_closed_loop_runs(platform_id, limit)
        return {"status": "ok", "total": len(runs), "runs": runs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取闭环历史失败: {e}")


@router.post("/full-diagnosis/{platform_id}")
async def trigger_full_diagnosis(platform_id: str, content_text: str = ""):
    """运行全面诊断（三套系统并行+合并）"""
    try:
        from app.core.orchestrator import run_full_diagnosis
        text = content_text if content_text.strip() else None
        result = await run_full_diagnosis(platform_id, text)
        return {"status": "ok", "diagnosis": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"全面诊断失败: {e}")
