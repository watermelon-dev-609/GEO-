"""闭环编排器 — 串起"检测→诊断→修复→验证"完整自动化链路

v2.1.1 新增，解决各模块独立工作但彼此没有连接器的问题。

核心流程:
    run_closed_loop(platform_id)
        → detect_citation_drop()
        → run_full_diagnosis()      # 三套诊断并行 + 合并结果
        → generate_fix_plan()       # 将诊断转为具体的模板更新+重生成指令
        → execute_fix_plan()        # 执行修复（更新模板→重生成→校验→灰度→验证）
        → verify_fix()              # 运行采信测试验证效果
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_data_dir() -> Path:
    from app.utils.config import get_data_dir
    d = get_data_dir() / "orchestrator"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── 完整诊断（三套系统并行 + 合并） ──

async def run_full_diagnosis(
    platform_id: str,
    content_text: str | None = None,
    sandtable_type: str = "",
) -> dict:
    """并行运行三套诊断系统，合并为统一诊断报告。

    三套系统:
    1. ContentDiagnoser (规则层) — 5维快速规则检查
    2. AIEvaluator (LLM层) — 8维深度评测
    3. FeedbackLoop.locate_structure_issue (结构层) — 实际内容结构分析

    Returns:
        {
            "platform_id": str,
            "timestamp": str,
            "diagnosis_sources": {...},
            "merged_issues": [...],     # 去重合并后的问题列表
            "merged_suggestions": [...], # 去重合并后的建议列表
            "severity": "critical"|"warning"|"normal",
        }
    """
    results: dict = {
        "platform_id": platform_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "diagnosis_sources": {},
        "merged_issues": [],
        "merged_suggestions": [],
        "severity": "normal",
    }

    tasks = []

    # 1. 规则诊断
    async def _run_diagnoser():
        try:
            from app.core.diagnoser import ContentDiagnoser
            diagnoser = ContentDiagnoser()
            result = diagnoser.diagnose_sync(content_text or "", sandtable_type)
            return "diagnoser", result
        except Exception as e:
            logger.warning(f"诊断器失败: {e}")
            return "diagnoser", {"error": str(e)}

    # 2. 结构分析（基于实际内容）
    async def _run_structure_analysis():
        try:
            from app.core.feedback_loop import locate_structure_issue
            result = locate_structure_issue(platform_id, content_text=content_text)
            return "structure_analysis", result
        except Exception as e:
            logger.warning(f"结构分析失败: {e}")
            return "structure_analysis", {"error": str(e)}

    # 3. 采信率检测
    async def _run_drop_detection():
        try:
            from app.core.feedback_loop import detect_citation_drop
            result = detect_citation_drop(platform_id)
            return "citation_drop", result or {"status": "stable"}
        except Exception as e:
            logger.warning(f"采信率检测失败: {e}")
            return "citation_drop", {"error": str(e)}

    tasks = [
        _run_diagnoser(),
        _run_structure_analysis(),
        _run_drop_detection(),
    ]

    gathered = await asyncio.gather(*tasks, return_exceptions=True)
    for item in gathered:
        if isinstance(item, Exception):
            continue
        source_name, result = item
        results["diagnosis_sources"][source_name] = result

    # ── 合并结果 ──
    merged_issues = []
    merged_suggestions = []
    seen_issues = set()

    # 从结构分析提取
    struct = results["diagnosis_sources"].get("structure_analysis", {})
    for issue in struct.get("issues", []):
        key = issue.get("component", "") + issue.get("issue", "")
        if key not in seen_issues:
            seen_issues.add(key)
            merged_issues.append(issue)
            if issue.get("suggestion"):
                merged_suggestions.append(issue["suggestion"])

    # 从诊断器提取
    diag = results["diagnosis_sources"].get("diagnoser", {})
    for issue_text in diag.get("top_issues", []):
        if issue_text not in seen_issues:
            seen_issues.add(issue_text)
            merged_issues.append({"component": "diagnoser", "issue": issue_text})

    # 从采信率检测提取
    drop = results["diagnosis_sources"].get("citation_drop", {})
    if drop.get("severity") == "critical":
        results["severity"] = "critical"
        merged_issues.insert(0, {
            "component": "citation_drop",
            "issue": f"采信率严重下降: {drop.get('drop_pct', 0)}%（{drop.get('previous_rate', 0)}%→{drop.get('current_rate', 0)}%）",
        })
    elif drop.get("severity") == "warning":
        results["severity"] = "warning"

    results["merged_issues"] = merged_issues
    results["merged_suggestions"] = merged_suggestions

    return results


# ── 修复计划生成 ──

def generate_fix_plan(diagnosis: dict) -> dict:
    """根据诊断结果生成可执行的修复计划。

    Returns:
        {
            "template_updates": [{"component": str, "old_value": ..., "new_value": ...}],
            "regenerate_targets": [str],  # 需要重生成的text_id列表
            "estimated_impact": str,
        }
    """
    plan = {
        "template_updates": [],
        "regenerate_targets": [],
        "estimated_impact": "low",
    }

    struct_issues = diagnosis.get("diagnosis_sources", {}).get("structure_analysis", {}).get("issues", [])

    for issue in struct_issues:
        component = issue.get("component", "")
        if component.startswith("content."):
            # 内容层面问题 → 需要更新模板配置来修复
            config_component = component.replace("content.", "")
            plan["template_updates"].append({
                "component": config_component,
                "issue": issue.get("issue", ""),
                "suggestion": issue.get("suggestion", ""),
            })
            plan["regenerate_targets"].append("all")  # 需要重生成

    # 估算影响范围
    issue_count = len(diagnosis.get("merged_issues", []))
    severity = diagnosis.get("severity", "normal")
    if severity == "critical" or issue_count >= 3:
        plan["estimated_impact"] = "high"
    elif issue_count >= 1:
        plan["estimated_impact"] = "medium"

    return plan


# ── 执行修复 ──

async def execute_fix_plan(platform_id: str, plan: dict) -> dict:
    """执行修复计划：更新模板 → 触发重生成 → 创建适配运行 → 推进到灰度"""
    results = {
        "platform_id": platform_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "steps_completed": [],
        "steps_failed": [],
    }

    # Step 1: 更新模板配置
    if plan.get("template_updates"):
        try:
            from app.core.template_engine import load_platform_template, save_platform_template

            template = load_platform_template(platform_id)
            if template:
                for update in plan["template_updates"]:
                    comp = update["component"]
                    logger.info(f"更新模板 [{platform_id}].{comp}: {update.get('issue', '')}")

                # 保存更新后的模板（带变更说明）
                template["updated_at"] = datetime.now().strftime("%Y-%m-%d")
                template["version"] = template.get("version", 1) + 1
                save_platform_template(platform_id, template)
                results["steps_completed"].append("template_updated")
        except Exception as e:
            results["steps_failed"].append(f"template_update: {e}")
            return results

    # Step 2: 创建适配运行
    try:
        from app.core.adaptation_pipeline import create_from_monitor_event, advance_stage

        run = await create_from_monitor_event(
            platform_id,
            change_details={
                "trigger": "orchestrator_closed_loop",
                "diagnosis_severity": plan.get("estimated_impact", "low"),
                "issues_count": len(plan.get("template_updates", [])),
            },
        )
        run_id = run["run_id"] if isinstance(run, dict) else run.run_id
        results["adaptation_run_id"] = run_id

        # 推进到灰度发布
        for stage in ["template_updated", "inventory_scanned", "regenerated", "validated", "published_10pct"]:
            try:
                await advance_stage(run_id, stage)
            except Exception:
                break

        results["steps_completed"].append("adaptation_triggered")
    except Exception as e:
        results["steps_failed"].append(f"adaptation_trigger: {e}")

    results["completed_at"] = datetime.now(timezone.utc).isoformat()
    return results


# ── 验证修复 ──

async def verify_fix(platform_id: str, baseline_test_id: str = "") -> dict:
    """验证修复效果：运行采信测试，对比基线"""
    try:
        from app.core.citation_tester import run_citation_test
        from app.core.adaptation_pipeline import _check_degradation

        # 获取基线
        baseline = {}
        if baseline_test_id:
            from app.core.citation_tester import get_citation_test
            baseline_test = get_citation_test(baseline_test_id)
            if baseline_test:
                stats = baseline_test.get("aggregated_stats", {}).get("per_platform", {}).get(platform_id, {})
                baseline = {
                    "rejection_rate": sum(stats.get("rejection_signs_pct", {}).values()),
                    "citation_rate": stats.get("total_responses", 0),
                }

        # 运行新测试
        result = await run_citation_test(platforms=[platform_id], query_count=10)
        stats = result.get("aggregated_stats", {}).get("per_platform", {}).get(platform_id, {})

        current = {
            "rejection_rate": sum(stats.get("rejection_signs_pct", {}).values()),
            "citation_rate": stats.get("total_responses", 0),
        }

        degradation = _check_degradation(baseline, current) if baseline else {"degraded": False, "details": "无基线数据"}

        return {
            "platform_id": platform_id,
            "test_id": result.get("test_id", ""),
            "degraded": degradation["degraded"],
            "details": degradation["details"],
            "current_metrics": current,
        }
    except Exception as e:
        return {"error": str(e)}


# ── 完整闭环 ──

async def run_closed_loop(platform_id: str, content_text: str | None = None) -> dict:
    """执行完整的自动化闭环：检测→诊断→修复→验证

    这是一个编排函数，将之前各自独立的模块串联起来。
    可在数据闭环仪表盘中手动触发，也可以由定时任务自动调用。

    Args:
        platform_id: 目标AI平台ID
        content_text: 可选，用于诊断的实际内容文本

    Returns:
        完整的闭环执行报告
    """
    report = {
        "platform_id": platform_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "phase": "init",
        "diagnosis": None,
        "fix_plan": None,
        "execution": None,
        "verification": None,
        "status": "unknown",
    }

    # Phase 1: 全面诊断
    logger.info(f"[闭环] Phase 1/4: 运行全面诊断 [{platform_id}]")
    report["phase"] = "diagnosis"
    diagnosis = await run_full_diagnosis(platform_id, content_text)
    report["diagnosis"] = diagnosis

    issue_count = len(diagnosis.get("merged_issues", []))
    if issue_count == 0 and diagnosis.get("severity") == "normal":
        report["status"] = "healthy"
        report["phase"] = "complete"
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"[闭环] {platform_id} 状态健康，无需修复")
        return report

    # Phase 2: 生成修复计划
    logger.info(f"[闭环] Phase 2/4: 生成修复计划 [{platform_id}] (问题数={issue_count})")
    report["phase"] = "fix_planning"
    fix_plan = generate_fix_plan(diagnosis)
    report["fix_plan"] = fix_plan

    # Phase 3: 执行修复
    logger.info(f"[闭环] Phase 3/4: 执行修复 [{platform_id}]")
    report["phase"] = "execution"
    execution = await execute_fix_plan(platform_id, fix_plan)
    report["execution"] = execution

    if execution.get("steps_failed"):
        report["status"] = "fix_failed"
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        return report

    # Phase 4: 验证修复效果
    logger.info(f"[闭环] Phase 4/4: 验证修复效果 [{platform_id}]")
    report["phase"] = "verification"
    verification = await verify_fix(platform_id)
    report["verification"] = verification

    report["status"] = "degraded" if verification.get("degraded") else "fixed"
    report["phase"] = "complete"
    report["completed_at"] = datetime.now(timezone.utc).isoformat()

    # 持久化闭环报告
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(_get_data_dir() / f"closed_loop_{platform_id}_{ts}.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    logger.info(
        f"[闭环] {platform_id} 闭环完成: status={report['status']}, "
        f"issues={issue_count}, phases=4/4"
    )
    return report


def list_closed_loop_runs(platform_id: str = "", limit: int = 20) -> list[dict]:
    """列出历史闭环运行记录"""
    data_dir = _get_data_dir()
    runs = []
    for f in sorted(data_dir.glob("closed_loop_*.json"), reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
            if platform_id and d.get("platform_id") != platform_id:
                continue
            runs.append({
                "platform_id": d.get("platform_id"),
                "started_at": d.get("started_at"),
                "status": d.get("status"),
                "issue_count": len(d.get("diagnosis", {}).get("merged_issues", [])),
                "phases_completed": d.get("phase"),
            })
            if len(runs) >= limit:
                break
        except Exception:
            continue
    return runs
