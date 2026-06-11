"""定时任务调度引擎 — 基于APScheduler"""

from __future__ import annotations
import logging
import time
import json
from pathlib import Path
from dataclasses import dataclass, field

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.base import JobLookupError

from app.utils.config import load_settings

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_jobs_meta: dict[str, dict] = {}
_jobs_file: Path | None = None


def _get_jobs_file() -> Path:
    global _jobs_file
    if _jobs_file is None:
        settings = load_settings()
        data_dir = settings.get("system", {}).get("data_dir", "./data")
        base = Path(data_dir)
        if not base.is_absolute():
            base = Path(__file__).resolve().parent.parent.parent / data_dir
        _jobs_file = base / "scheduler_jobs.json"
        _jobs_file.parent.mkdir(parents=True, exist_ok=True)
    return _jobs_file


def _save_jobs_meta():
    with open(_get_jobs_file(), "w", encoding="utf-8") as f:
        json.dump(_jobs_meta, f, ensure_ascii=False, indent=2)


def _load_jobs_meta():
    global _jobs_meta
    fp = _get_jobs_file()
    if fp.exists():
        try:
            with open(fp, "r", encoding="utf-8") as f:
                _jobs_meta = json.load(f)
        except Exception:
            _jobs_meta = {}


@dataclass
class JobInfo:
    id: str
    name: str
    type: str           # brand_monitor / weekly_report / monthly_report / platform_check / rss_daily_crawl / citation_weekly_test / structure_weekly_report
    trigger: str        # cron / interval
    trigger_value: str  # cron表达式 或 间隔分钟数
    enabled: bool = True
    last_run: str = ""
    next_run: str = ""
    run_count: int = 0


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
        _load_jobs_meta()
    return _scheduler


def _ensure_running():
    """确保调度器在事件循环中运行，并从持久化恢复任务

    每次 FastAPI startup 事件调用时：
    1. 重新创建调度器（避免跨进程 event loop 引用失效）
    2. 加载持久化任务元数据
    3. 恢复所有启用的任务
    """
    global _scheduler
    try:
        import asyncio
        asyncio.get_running_loop()
    except RuntimeError:
        return  # no event loop, nothing to do

    # 进程重启后重建调度器，避免旧 event loop 引用
    _scheduler = AsyncIOScheduler()
    _load_jobs_meta()
    sched = _scheduler

    if not sched.running:
        sched.start()
        logger.info("定时任务调度器已启动")

    # 每次 ensure 都尝试恢复尚未添加的持久化任务
    recovered = 0
    for job_id, meta in list(_jobs_meta.items()):
        if not meta.get("enabled", True):
            logger.info(f"跳过已禁用的定时任务: {meta.get('name', job_id)}")
            continue
        try:
            _add_job_from_meta(job_id, meta)
            recovered += 1
        except Exception as e:
            logger.warning(f"恢复定时任务失败 [{job_id}]: {e}")

    if recovered > 0:
        logger.info(f"已从持久化恢复 {recovered} 个定时任务")
    else:
        logger.info("无待恢复的定时任务")


def _add_job_from_meta(job_id: str, meta: dict):
    global _scheduler
    trigger_type = meta.get("trigger", "interval")
    trigger_value = meta.get("trigger_value", "1440")

    if trigger_type == "cron":
        parts = trigger_value.split()
        trigger = CronTrigger(
            minute=parts[0] if len(parts) > 0 else "0",
            hour=parts[1] if len(parts) > 1 else "9",
            day=parts[2] if len(parts) > 2 else "*",
            month=parts[3] if len(parts) > 3 else "*",
            day_of_week=parts[4] if len(parts) > 4 else "*",
        )
    else:
        trigger = IntervalTrigger(minutes=int(trigger_value))

    func_map = {
        "brand_monitor": _run_brand_monitor,
        "platform_check": _run_platform_check,
        "weekly_report": _run_weekly_report,
        "monthly_report": _run_monthly_report,
        "rss_daily_crawl": _run_rss_daily_crawl,
        "citation_weekly_test": _run_citation_weekly_test,
        "structure_weekly_report": _run_structure_weekly_report,
        "competitor_monitor": _run_competitor_monitor,
    }
    func = func_map.get(meta.get("type", ""), _run_brand_monitor)

    scheduler = get_scheduler()
    try:
        scheduler.add_job(func, trigger, id=job_id, replace_existing=True)
    except RuntimeError:
        # event loop closed (e.g. TestClient context switch) — recreate scheduler
        logger.info("调度器事件循环已变更，重新初始化")
        _scheduler = AsyncIOScheduler()
        _ensure_running()
        _scheduler.add_job(func, trigger, id=job_id, replace_existing=True)


def create_job(name: str, job_type: str, trigger: str, trigger_value: str) -> JobInfo:
    job_id = f"job_{int(time.time() * 1000)}"
    meta = {
        "name": name,
        "type": job_type,
        "trigger": trigger,
        "trigger_value": trigger_value,
        "enabled": True,
        "last_run": "",
        "run_count": 0,
    }
    _jobs_meta[job_id] = meta
    _save_jobs_meta()
    _add_job_from_meta(job_id, meta)
    return JobInfo(id=job_id, name=name, type=job_type, trigger=trigger, trigger_value=trigger_value)


def delete_job(job_id: str) -> bool:
    scheduler = get_scheduler()
    try:
        scheduler.remove_job(job_id)
    except JobLookupError:
        pass
    if job_id in _jobs_meta:
        del _jobs_meta[job_id]
        _save_jobs_meta()
        return True
    return False


def toggle_job(job_id: str, enabled: bool) -> bool:
    if job_id not in _jobs_meta:
        return False
    _jobs_meta[job_id]["enabled"] = enabled
    _save_jobs_meta()
    scheduler = get_scheduler()
    if enabled:
        _add_job_from_meta(job_id, _jobs_meta[job_id])
    else:
        try:
            scheduler.remove_job(job_id)
        except JobLookupError:
            pass
    return True


def list_jobs() -> list[JobInfo]:
    jobs = []
    scheduler = get_scheduler()
    for job_id, meta in list(_jobs_meta.items()):
        aps_job = None
        try:
            aps_job = scheduler.get_job(job_id)
        except Exception:
            pass
        next_run = ""
        if aps_job:
            try:
                nrt = getattr(aps_job, 'next_run_time', None)
                if nrt:
                    next_run = str(nrt)
            except Exception:
                pass
        jobs.append(JobInfo(
            id=job_id,
            name=meta.get("name", ""),
            type=meta.get("type", ""),
            trigger=meta.get("trigger", "interval"),
            trigger_value=meta.get("trigger_value", ""),
            enabled=meta.get("enabled", True),
            last_run=meta.get("last_run", ""),
            next_run=next_run,
            run_count=meta.get("run_count", 0),
        ))
    return jobs


# ── 任务执行函数 ──

async def _run_brand_monitor():
    """自动品牌收录监测"""
    logger.info("[Scheduler] 执行自动品牌收录监测...")
    try:
        from app.core.brand_checker import BrandChecker
        checker = BrandChecker()
        result = await checker.check_all_platforms()
        logger.info(f"[Scheduler] 品牌监测完成: {result.get('mention_rate', 0)}% 收录率")
        _update_job_run("brand_monitor")
        return result
    except Exception as e:
        logger.error(f"[Scheduler] 品牌监测失败: {e}")


async def _run_platform_check():
    """自动平台规则检查"""
    logger.info("[Scheduler] 执行自动平台规则检查...")
    try:
        from app.api.platform_monitor import init_platform_rules
        await init_platform_rules()
        _update_job_run("platform_check")
    except Exception as e:
        logger.error(f"[Scheduler] 平台规则检查失败: {e}")


async def _run_weekly_report():
    """自动周报生成"""
    logger.info("[Scheduler] 生成周报...")
    try:
        from app.core.auto_reporter import generate_weekly_report
        path = await generate_weekly_report()
        logger.info(f"[Scheduler] 周报已生成: {path}")
        _update_job_run("weekly_report")
    except Exception as e:
        logger.error(f"[Scheduler] 周报生成失败: {e}")


async def _run_monthly_report():
    """自动月报生成"""
    logger.info("[Scheduler] 生成月报...")
    try:
        from app.core.auto_reporter import generate_monthly_report
        path = await generate_monthly_report()
        logger.info(f"[Scheduler] 月报已生成: {path}")
        _update_job_run("monthly_report")
    except Exception as e:
        logger.error(f"[Scheduler] 月报生成失败: {e}")


async def _run_rss_daily_crawl():
    """每日RSS信源监控"""
    logger.info("[Scheduler] 执行每日RSS信源检查...")
    try:
        from app.core.rss_monitor import run_daily_crawl
        result = await run_daily_crawl()
        alerts = result.get("total_alerts", 0)
        if alerts > 0:
            logger.warning(f"[Scheduler] RSS检查发现 {alerts} 条关键词告警！")
            # ── v2.1.1: 自动触发适配流水线 ──
            try:
                from app.core.ai_structure_reporter import auto_trigger_adaptation_from_alerts
                triggered = await auto_trigger_adaptation_from_alerts()
                if triggered:
                    logger.info(
                        f"[Scheduler] RSS告警已自动触发 {len(triggered)} 条适配流水线: "
                        + ", ".join(f"{t['platform_id']}({t['run_id']})" for t in triggered)
                    )
                else:
                    logger.info("[Scheduler] RSS告警未匹配到目标平台，跳过适配触发")
            except Exception as e:
                logger.error(f"[Scheduler] RSS告警自动触发适配失败: {e}")
        else:
            logger.info(f"[Scheduler] RSS检查完成，无告警")
        _update_job_run("rss_daily_crawl")
        return result
    except Exception as e:
        logger.error(f"[Scheduler] RSS检查失败: {e}")


async def _run_citation_weekly_test():
    """每周AI采信行为测试"""
    logger.info("[Scheduler] 执行每周AI采信测试...")
    try:
        from app.core.citation_tester import run_citation_test
        result = await run_citation_test(query_count=25)
        logger.info(
            f"[Scheduler] 采信测试完成: "
            f"{result.get('queries_fired', 0)}/{result.get('queries_attempted', 0)} 成功"
        )
        _update_job_run("citation_weekly_test")
        return result
    except Exception as e:
        logger.error(f"[Scheduler] 采信测试失败: {e}")


async def _run_structure_weekly_report():
    """每周AI结构变化报告"""
    logger.info("[Scheduler] 生成每周AI结构变化报告...")
    try:
        from app.core.ai_structure_reporter import generate_weekly_structure_report
        report = generate_weekly_structure_report()
        logger.info(f"[Scheduler] 结构报告已生成 ({len(report)} 字符)")
        _update_job_run("structure_weekly_report")
        return report
    except Exception as e:
        logger.error(f"[Scheduler] 结构报告生成失败: {e}")


async def _run_competitor_monitor():
    """自动竞品监控 (3天周期)"""
    logger.info("[Scheduler] 执行自动竞品监控...")
    try:
        from app.core.competitor_monitor import run_competitor_monitor_cycle
        result = await run_competitor_monitor_cycle()
        status = result.get("status", "unknown")
        if status == "skipped":
            logger.info(f"[Scheduler] 竞品监控跳过: {result.get('reason', '')}")
        else:
            alerts = result.get("changes_from_previous", {}).get("alerts", [])
            if alerts:
                logger.warning(
                    f"[Scheduler] 竞品监控发现 {len(alerts)} 项变化: "
                    + "; ".join(a.get("summary", "") for a in alerts[:3])
                )
            logger.info(
                f"[Scheduler] 竞品监控完成: {result['competitors_probed']}竞品 x "
                f"{result['platforms_probed']}平台"
            )
        _update_job_run("competitor_monitor")
        return result
    except Exception as e:
        logger.error(f"[Scheduler] 竞品监控失败: {e}")


def _update_job_run(job_type: str):
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for job_id, meta in list(_jobs_meta.items()):
        if meta.get("type") == job_type:
            meta["last_run"] = now
            meta["run_count"] = meta.get("run_count", 0) + 1
    _save_jobs_meta()
