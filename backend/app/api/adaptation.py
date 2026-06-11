"""适配流水线 API"""

import logging
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/runs")
async def list_runs(platform_id: str = "", status: str = "", limit: int = 20):
    """列出适配运行记录"""
    try:
        from app.core.adaptation_pipeline import list_runs as _list
        runs = _list(platform_id, status, limit)
        return {"status": "ok", "total": len(runs), "runs": runs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取运行列表失败: {e}")


@router.post("/runs")
async def create_run(platform_id: str, trigger_event: str = ""):
    """创建适配运行"""
    try:
        from app.core.adaptation_pipeline import create_from_monitor_event
        import json
        details = None
        if trigger_event:
            try:
                details = json.loads(trigger_event)
            except Exception:
                details = {"raw": trigger_event}
        result = await create_from_monitor_event(platform_id, details)
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建运行失败: {e}")


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    """获取适配运行详情"""
    try:
        from app.core.adaptation_pipeline import get_run
        run = get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"运行不存在: {run_id}")
        return {"status": "ok", "run": run}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取运行失败: {e}")


@router.post("/runs/{run_id}/advance")
async def advance_run(run_id: str, target_stage: str = ""):
    """推进适配运行到下一阶段"""
    try:
        from app.core.adaptation_pipeline import advance_stage
        ts = target_stage if target_stage else None
        result = await advance_stage(run_id, ts)
        if not result:
            raise HTTPException(status_code=404, detail=f"运行不存在: {run_id}")
        return {"status": "ok", "run": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"推进阶段失败: {e}")


@router.post("/runs/{run_id}/scan")
async def scan_inventory(run_id: str):
    """扫描存量内容"""
    try:
        from app.core.adaptation_pipeline import scan_inventory as _scan, get_run
        run = get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"运行不存在: {run_id}")
        result = await _scan(run["platform_id"], run_id)
        # 自动推进阶段
        from app.core.adaptation_pipeline import advance_stage
        await advance_stage(run_id, "inventory_scanned")
        return {"status": "ok", **result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"扫描失败: {e}")


@router.post("/runs/{run_id}/validate")
async def validate_content(run_id: str, text: str = ""):
    """校验内容质量"""
    try:
        from app.core.adaptation_pipeline import auto_validate, get_run
        run = get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"运行不存在: {run_id}")
        result = await auto_validate(text, run["platform_id"])
        return {"status": "ok", **result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"校验失败: {e}")


@router.post("/runs/{run_id}/publish")
async def publish_run(run_id: str, strategy: str = "grayscale_10"):
    """发布内容（全量/灰度10%/灰度100%）"""
    try:
        from app.core.adaptation_pipeline import advance_stage, get_run
        run = get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"运行不存在: {run_id}")

        if strategy == "grayscale_10":
            await advance_stage(run_id, "published_10pct")
        elif strategy == "grayscale_100":
            await advance_stage(run_id, "published_100pct")
        else:
            await advance_stage(run_id, "published_100pct")

        run = get_run(run_id)
        return {"status": "ok", "strategy": strategy, "stage": run["stage"] if run else "unknown"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发布失败: {e}")


@router.post("/runs/{run_id}/rollback")
async def rollback_run(run_id: str):
    """一键回滚适配运行"""
    try:
        from app.core.adaptation_pipeline import rollback_run as _rollback
        result = await _rollback(run_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return {"status": "ok", "message": "已回滚", "run": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回滚失败: {e}")


@router.post("/runs/{run_id}/post-test")
async def post_test(run_id: str, days: int = 3):
    """发布后采信测试"""
    try:
        from app.core.adaptation_pipeline import post_publish_test, advance_stage
        result = await post_publish_test(run_id, days)
        stage_key = f"post_test_{days}d"
        await advance_stage(run_id, stage_key)
        return {"status": "ok", **result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发布后测试失败: {e}")
