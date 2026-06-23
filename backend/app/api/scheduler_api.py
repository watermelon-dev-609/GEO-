"""定时任务管理API"""

import logging
from fastapi import APIRouter, HTTPException, Query
from app.core.scheduler import get_scheduler, create_job, delete_job, toggle_job, list_jobs
from app.core.anomaly_detector import detect_anomalies
from app.core.citation_tester import get_latest_drift_report, list_citation_tests

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/jobs")
async def get_jobs():
    """获取所有定时任务"""
    try:
        jobs = list_jobs()
        return {"jobs": [j.__dict__ for j in jobs]}
    except Exception as e:
        logger.exception("获取定时任务列表失败")
        return {"jobs": [], "error": str(e)}


@router.post("/jobs")
async def add_job(
    name: str = Query(..., description="任务名称"),
    job_type: str = Query(..., description="任务类型: brand_monitor/platform_check/weekly_report/monthly_report/rss_daily_crawl/citation_weekly_test/structure_weekly_report/competitor_monitor"),
    trigger: str = Query(default="interval", description="触发器: interval/cron"),
    trigger_value: str = Query(default="1440", description="间隔分钟数 或 cron表达式"),
):
    """创建定时任务"""
    valid_types = {"brand_monitor", "platform_check", "weekly_report", "monthly_report",
                   "rss_daily_crawl", "citation_weekly_test", "structure_weekly_report",
                   "competitor_monitor"}
    if job_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"无效任务类型: {job_type}，可选: {valid_types}")
    try:
        job = create_job(name, job_type, trigger, trigger_value)
        return {"status": "ok", "job": job.__dict__}
    except Exception as e:
        logger.exception("创建定时任务失败")
        raise HTTPException(status_code=500, detail=f"创建失败: {e}")


@router.delete("/jobs/{job_id}")
async def remove_job(job_id: str):
    """删除定时任务"""
    try:
        if delete_job(job_id):
            return {"status": "ok"}
        raise HTTPException(status_code=404, detail="任务不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("删除定时任务失败")
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@router.put("/jobs/{job_id}")
async def enable_disable_job(job_id: str, enabled: bool = Query(...)):
    """启停定时任务"""
    try:
        if toggle_job(job_id, enabled):
            return {"status": "ok", "enabled": enabled}
        raise HTTPException(status_code=404, detail="任务不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("启停定时任务失败")
        raise HTTPException(status_code=500, detail=f"操作失败: {e}")


@router.get("/anomalies")
async def get_anomalies():
    """获取异常告警"""
    try:
        alerts = detect_anomalies()
        return {"alerts": alerts, "count": len(alerts)}
    except Exception as e:
        logger.exception("获取异常告警失败")
        return {"alerts": [], "count": 0, "error": str(e)}


@router.get("/citation-drift")
async def citation_drift_report():
    """AI平台采信行为漂移检测报告

    对比最近两次 citation test 结果，检测各 AI 平台的结构特征偏好、来源偏好、
    时效偏好是否发生显著变化。变化超过阈值时生成告警+建议更新对应 YAML 规则。
    每周自动运行一次（citation_weekly_test 定时任务），也可手动触发。
    """
    try:
        report = get_latest_drift_report()
        return report
    except Exception as e:
        logger.exception("获取漂移检测报告失败")
        return {"alerts": [], "total_alerts": 0, "error": str(e)}


@router.get("/citation-tests")
async def list_tests(days: int = 90):
    """列出最近的AI采信测试记录"""
    try:
        tests = list_citation_tests(days=days)
        return {"tests": tests, "count": len(tests)}
    except Exception as e:
        logger.exception("获取采信测试列表失败")
        return {"tests": [], "count": 0, "error": str(e)}


@router.get("/status")
async def scheduler_status():
    """调度器状态"""
    try:
        sched = get_scheduler()
        jobs = list_jobs()
        return {"running": sched.running, "job_count": len(jobs)}
    except Exception as e:
        logger.exception("获取调度器状态失败")
        return {"running": False, "job_count": 0, "error": str(e)}
