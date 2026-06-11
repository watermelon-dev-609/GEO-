"""自动化适配流水线 — 监控发现变化 → 更新模板 → 扫描存量 → 批量重生成 → 校验 → 灰度发布

流程阶段:
    monitor_detected → structure_requirement → template_updated →
    inventory_scanned → regenerated → validated →
    spot_checked → published(grayscale_10) → published(grayscale_100)

支持: 全量发布 / 灰度10%发布 / 一键回滚 / 3天/7天发布后测试
"""

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── 阶段定义 ──

STAGES = [
    "monitor_detected",
    "structure_requirement",
    "template_updated",
    "inventory_scanned",
    "regenerated",
    "validated",
    "spot_checked",
    "published_10pct",
    "published_100pct",
    "post_test_3d",
    "post_test_7d",
]

STAGE_LABELS = {
    "monitor_detected": "监控发现变化",
    "structure_requirement": "结构调整需求",
    "template_updated": "模板已更新",
    "inventory_scanned": "存量已扫描",
    "regenerated": "内容已重生成",
    "validated": "自动校验通过",
    "spot_checked": "人工抽检(5%)",
    "published_10pct": "灰度发布(10%)",
    "published_100pct": "全量发布(100%)",
    "post_test_3d": "3天发布后测试",
    "post_test_7d": "7天发布后测试",
}


# ── 数据路径 ──

def _get_data_dir() -> Path:
    from app.utils.config import get_data_dir
    d = get_data_dir() / "adaptation_runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── 适配运行记录 ──

class AdaptationRun:
    """一次完整的适配运行"""

    def __init__(self, platform_id: str, trigger_event: str = ""):
        self.run_id = f"adapt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.platform_id = platform_id
        self.trigger_event = trigger_event
        self.stage = "monitor_detected"
        self.status = "pending"  # pending / in_progress / completed / failed / rolled_back
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.completed_at = ""
        self.articles_affected = 0
        self.articles_regenerated = 0
        self.articles_validated = 0
        self.articles_published = 0
        self.rollback_version_id = ""
        self.template_version_before = ""
        self.template_version_after = ""
        self.validation_errors: list[str] = []
        self.notes: list[str] = []

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "platform_id": self.platform_id,
            "trigger_event": self.trigger_event,
            "stage": self.stage,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "articles_affected": self.articles_affected,
            "articles_regenerated": self.articles_regenerated,
            "articles_validated": self.articles_validated,
            "articles_published": self.articles_published,
            "rollback_version_id": self.rollback_version_id,
            "template_version_before": self.template_version_before,
            "template_version_after": self.template_version_after,
            "validation_errors": self.validation_errors,
            "notes": self.notes,
            "stage_label": STAGE_LABELS.get(self.stage, self.stage),
        }


# ── 持久化 ──

def _load_run(run_id: str) -> dict | None:
    fp = _get_data_dir() / f"{run_id}.json"
    if not fp.exists():
        return None
    with open(fp, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_run(run: AdaptationRun):
    with open(_get_data_dir() / f"{run.run_id}.json", "w", encoding="utf-8") as f:
        json.dump(run.to_dict(), f, ensure_ascii=False, indent=2)


# ── 流水线操作 ──

async def create_from_monitor_event(platform_id: str, change_details: dict | None = None) -> dict:
    """从监控事件创建适配运行"""
    trigger = json.dumps(change_details, ensure_ascii=False)[:200] if change_details else "手动触发"
    run = AdaptationRun(platform_id, trigger)

    # 记录当前模板版本
    try:
        from app.core.template_engine import load_platform_template
        tmpl = load_platform_template(platform_id)
        run.template_version_before = f"v{tmpl.get('version', 1)}"
    except Exception:
        pass

    _save_run(run)
    logger.info(f"适配运行已创建: {run.run_id} (平台={platform_id})")
    return run.to_dict()


async def trigger_from_yaml_change(platform_id: str, changed_file: str,
                                     old_hash: str = "", new_hash: str = "") -> dict | None:
    """当 watchdog 检测到 YAML 模板变更时自动触发适配流水线。

    触发条件：
    1. 平台模板文件存在且有效
    2. 该平台没有正在进行的适配运行（避免重复触发）

    Args:
        platform_id: 平台ID（从文件名解析，如 "wenxin"）
        changed_file: 变更的文件路径
        old_hash: 变更前的文件哈希（可选）
        new_hash: 变更后的文件哈希（可选）

    Returns:
        适配运行记录 dict，如果跳过则返回 None
    """
    # 检查是否有正在进行的运行
    existing = list_runs(platform_id=platform_id, status="in_progress", limit=1)
    if existing:
        logger.info(
            f"平台 {platform_id} 已有进行中的适配运行 {existing[0].get('run_id', '?')}，跳过自动触发"
        )
        return None

    # 验证平台模板存在
    try:
        from app.core.template_engine import load_platform_template
        tmpl = load_platform_template(platform_id)
        if tmpl.get("_source") == "empty_fallback":
            logger.warning(f"无法为 {platform_id} 触发适配：模板不存在")
            return None
    except Exception as e:
        logger.warning(f"无法为 {platform_id} 触发适配：{e}")
        return None

    # 创建适配运行
    change_details = {
        "source": "watchdog_yaml_change",
        "platform_id": platform_id,
        "changed_file": changed_file,
        "old_hash": old_hash,
        "new_hash": new_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    run = await create_from_monitor_event(platform_id, change_details)
    logger.info(f"Watchdog 自动触发适配流水线: {run['run_id']} (平台={platform_id})")
    return run


async def advance_stage(run_id: str, target_stage: str | None = None) -> dict | None:
    """将适配运行推进到下一个阶段（或指定阶段）

    关键阶段行为：
    - published_10pct: 存储基线指标（用于后续对比）
    - post_test_3d/7d: 实际运行采信测试 + 对比基线 + 自动回滚（若降级）
    """
    data = _load_run(run_id)
    if not data:
        return None

    current_idx = STAGES.index(data["stage"]) if data["stage"] in STAGES else 0
    if target_stage and target_stage in STAGES:
        next_idx = STAGES.index(target_stage)
    else:
        next_idx = min(current_idx + 1, len(STAGES) - 1)

    next_stage = STAGES[next_idx]
    data["stage"] = next_stage
    data["status"] = "in_progress"

    # ── 灰度发布时存储基线 + 实际执行灰度重生成 ──
    if next_stage in ("published_10pct", "published_100pct"):
        try:
            baseline = await _capture_baseline(data["platform_id"])
            data["baseline_metrics"] = baseline
            data["notes"].append(f"[{next_stage}] 基线已存储: 采信率={baseline.get('citation_rate', 'N/A')}%")
        except Exception as e:
            logger.warning(f"存储基线失败: {e}")
            data["notes"].append(f"[{next_stage}] 基线存储失败: {e}")

        # ── 灰度10%：实际选取文章并重生成 ──
        if next_stage == "published_10pct":
            try:
                selection = _select_grayscale_articles(data["platform_id"], 0.10)
                data["grayscale_selection"] = selection
                data["notes"].append(
                    f"[published_10pct] 选中 {selection['selected_count']}/{selection['total_articles']} 篇"
                    f"({selection['percentage']*100:.0f}%), "
                    f"覆盖 {len(selection['sandtable_coverage'])} 种沙盘类型"
                )

                if selection["selected_count"] > 0:
                    regen_result = await _trigger_grayscale_regeneration(
                        data["platform_id"],
                        selection["selected_ids"][:10],  # 灰度上限10篇
                        run_id,
                    )
                    data["grayscale_regen"] = regen_result
                    data["notes"].append(
                        f"[published_10pct] 灰度重生成: "
                        f"{regen_result['succeeded']}/{regen_result['attempted']} 成功"
                    )
                else:
                    data["notes"].append("[published_10pct] 无符合条件的存量文章，跳过灰度重生成")
            except Exception as e:
                logger.error(f"灰度10%执行失败: {e}")
                data["notes"].append(f"[published_10pct] 灰度执行异常: {e}")

        # ── 全量发布：重生成剩余90% ──
        elif next_stage == "published_100pct":
            try:
                selection = _select_grayscale_articles(data["platform_id"], 0.90)
                data["full_rollout_selection"] = selection
                data["notes"].append(
                    f"[published_100pct] 选中 {selection['selected_count']}/{selection['total_articles']} 篇"
                )

                if selection["selected_count"] > 0:
                    regen_result = await _trigger_grayscale_regeneration(
                        data["platform_id"],
                        selection["selected_ids"][:50],  # 全量上限50篇
                        run_id,
                    )
                    data["full_rollout_regen"] = regen_result
                    data["notes"].append(
                        f"[published_100pct] 全量重生成: "
                        f"{regen_result['succeeded']}/{regen_result['attempted']} 成功"
                    )
                else:
                    data["notes"].append("[published_100pct] 无符合条件的存量文章，跳过全量重生成")
            except Exception as e:
                logger.error(f"全量发布执行失败: {e}")
                data["notes"].append(f"[published_100pct] 全量执行异常: {e}")

    # ── 发布后验证：运行真实采信测试 + 对比基线 ──
    if next_stage in ("post_test_3d", "post_test_7d"):
        days = 3 if next_stage == "post_test_3d" else 7
        try:
            test_result = await post_publish_test(run_id, days=days)
            data["notes"].append(
                f"[{next_stage}] 采信测试完成: test_id={test_result.get('test_id', 'N/A')}, "
                f"拒采率={test_result.get('citation_insights', {}).get('rejection_rate', 'N/A')}%"
            )

            # 对比基线，检测是否降级
            baseline = data.get("baseline_metrics", {})
            if baseline and test_result.get("citation_insights"):
                degradation = _check_degradation(baseline, test_result["citation_insights"])
                if degradation["degraded"]:
                    data["notes"].append(
                        f"[{next_stage}] ⚠ 检测到采信指标降级: {degradation['details']}"
                    )
                    # 自动回滚
                    if degradation.get("severity") == "critical":
                        logger.warning(
                            f"适配运行 {run_id}: {next_stage} 检测到严重降级，自动触发回滚"
                        )
                        await rollback_run(run_id)
                        data = _load_run(run_id)  # 重新加载回滚后的数据
                        if data:
                            data["notes"].append(
                                f"[{next_stage}] 已自动回滚至 {data.get('template_version_before', 'unknown')}"
                            )
                else:
                    data["notes"].append(f"[{next_stage}] 采信指标正常，无降级")
        except Exception as e:
            logger.error(f"发布后测试失败 [{run_id}]: {e}")
            data["notes"].append(f"[{next_stage}] 测试异常: {e}")

    if next_idx >= len(STAGES) - 1:
        data["status"] = "completed"
        data["completed_at"] = datetime.now(timezone.utc).isoformat()

    with open(_get_data_dir() / f"{run_id}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"适配运行 {run_id}: {STAGES[current_idx]} → {next_stage}")
    return data


def _select_grayscale_articles(platform_id: str, percentage: float = 0.10) -> dict[str, Any]:
    """从存量文章中按比例选取用于灰度发布的样本。

    选取策略：
    - 从 data/output/ 中查找引用该平台的文章
    - 按时间新鲜度 + 多样性抖动评分排序
    - 每种沙盘类型至少选取1篇（保证覆盖度）
    - 使用固定随机种子（可复现）

    Args:
        platform_id: 目标平台ID
        percentage: 选取比例（0.0 ~ 1.0）

    Returns:
        {total_articles, selected_count, percentage, selected_ids, sandtable_coverage}
    """
    import random
    from app.utils.config import get_data_dir

    random.seed(42)  # 固定种子，保证可复现

    output_dir = get_data_dir() / "output"
    if not output_dir.exists():
        return {
            "total_articles": 0, "selected_count": 0, "percentage": percentage,
            "selected_ids": [], "sandtable_coverage": {},
        }

    # 收集引用该平台的文章
    articles = []
    for f in output_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            text_content = json.dumps(data, ensure_ascii=False)
            if platform_id in text_content or f"platform_{platform_id}" in text_content:
                articles.append({
                    "id": f.stem,
                    "path": str(f.relative_to(output_dir)),
                    "mtime": f.stat().st_mtime,
                    "sandtable_type": data.get("sandtable_type", "unknown"),
                })
        except Exception:
            continue

    if not articles:
        return {
            "total_articles": 0, "selected_count": 0, "percentage": percentage,
            "selected_ids": [], "sandtable_coverage": {},
        }

    # 按时间新鲜度 + 多样性抖动评分
    max_mtime = max(a["mtime"] for a in articles)
    for a in articles:
        recency_score = a["mtime"] / max(max_mtime, 1)
        diversity_jitter = random.uniform(0, 0.3)
        a["score"] = recency_score + diversity_jitter

    articles.sort(key=lambda x: x["score"], reverse=True)

    # 按沙盘类型分组，每种至少选1篇
    by_type: dict[str, list] = {}
    for a in articles:
        by_type.setdefault(a["sandtable_type"], []).append(a)

    selected = []
    selected_ids_set: set[str] = set()

    # 第一轮：每种类型选最优1篇
    for stype, group in by_type.items():
        if group:
            selected.append(group[0])
            selected_ids_set.add(group[0]["id"])

    # 第二轮：从剩余文章中按评分补齐到目标数量
    target_count = max(1, int(len(articles) * percentage))
    for a in articles:
        if len(selected) >= target_count:
            break
        if a["id"] not in selected_ids_set:
            selected.append(a)
            selected_ids_set.add(a["id"])

    # 统计沙盘覆盖度
    sandtable_coverage: dict[str, int] = {}
    for a in selected:
        st = a["sandtable_type"]
        sandtable_coverage[st] = sandtable_coverage.get(st, 0) + 1

    return {
        "total_articles": len(articles),
        "selected_count": len(selected),
        "percentage": percentage,
        "selected_ids": [a["id"] for a in selected],
        "sandtable_coverage": sandtable_coverage,
    }


async def _trigger_grayscale_regeneration(platform_id: str, article_ids: list[str],
                                           run_id: str) -> dict[str, Any]:
    """对选中的灰度文章执行实际重生成。

    对每篇文章：
    1. 从 output/ 加载原始数据
    2. 调用 rewrite_text() 以更新后的平台模板重生成
    3. 保存重生成版本为 {id}_v2.json

    Args:
        platform_id: 目标平台
        article_ids: 待重生成的文章ID列表
        run_id: 适配运行ID（用于追踪）

    Returns:
        {attempted, succeeded, failed, details: [{article_id, status, error?}]}
    """
    from app.utils.config import get_data_dir

    output_dir = get_data_dir() / "output"
    results = {"attempted": len(article_ids), "succeeded": 0, "failed": 0, "details": []}

    for aid in article_ids:
        src_file = output_dir / f"{aid}.json"
        if not src_file.exists():
            results["failed"] += 1
            results["details"].append({"article_id": aid, "status": "not_found"})
            continue

        try:
            data = json.loads(src_file.read_text(encoding="utf-8"))
            original_text = data.get("cleaned_text") or data.get("original_text", "")
            sandtable_type = data.get("sandtable_type", "smart_city")

            if not original_text:
                results["failed"] += 1
                results["details"].append({"article_id": aid, "status": "empty_text"})
                continue

            # 使用新的平台模板重生成
            from app.core.rewriter import GEORewriter
            from app.models.enums import SandtableType, AIPlatform
            try:
                stype = SandtableType(sandtable_type)
            except ValueError:
                stype = SandtableType.SMART_CITY
            try:
                plat = AIPlatform(platform_id)
            except ValueError:
                continue

            rewriter = GEORewriter()
            regen_results = await rewriter.rewrite(
                cleaned_text=original_text,
                sandtable_type=stype,
                platforms=[plat],
                enterprise_name=data.get("enterprise_name", ""),
                enterprise_location=data.get("enterprise_location", ""),
            )

            # 取第一个（也是唯一一个）平台的结果
            optimized_text = ""
            if regen_results:
                r = regen_results[0]
                optimized_text = r.optimized_text or ""
                if not optimized_text and getattr(r, 'error', None):
                    results["details"][-1]["error"] = getattr(r, 'error')

            # 保存重生成版本
            regen_file = output_dir / f"{aid}_v2.json"
            regen_data = {
                **data,
                "regenerated_for": platform_id,
                "regenerated_at": datetime.now(timezone.utc).isoformat(),
                "adaptation_run_id": run_id,
                "regenerated_text": optimized_text,
            }
            with open(regen_file, "w", encoding="utf-8") as f:
                json.dump(regen_data, f, ensure_ascii=False, indent=2)

            results["succeeded"] += 1
            results["details"].append({"article_id": aid, "status": "regenerated"})
        except Exception as e:
            logger.error(f"灰度重生成失败 [{aid}]: {e}")
            results["failed"] += 1
            results["details"].append({"article_id": aid, "status": "failed", "error": str(e)})

    logger.info(
        f"灰度重生成完成: {results['succeeded']}/{results['attempted']} 成功 "
        f"(平台={platform_id}, run={run_id})"
    )
    return results


async def _capture_baseline(platform_id: str) -> dict:
    """捕获适配前的基线指标"""
    try:
        from app.core.citation_tester import run_citation_test
        result = await run_citation_test(platforms=[platform_id], query_count=5)
        stats = result.get("aggregated_stats", {}).get("per_platform", {}).get(platform_id, {})

        return {
            "test_id": result.get("test_id", ""),
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "citation_rate": sum(
                1 for r in result.get("results", []) if r.get("cited_sources")
            ) / max(len(result.get("results", [])), 1) * 100,
            "structure_features": stats.get("structure_features_pct", {}),
            "cited_sources": stats.get("cited_sources_pct", {}),
            "rejection_rate": sum(stats.get("rejection_signs_pct", {}).values()),
        }
    except Exception as e:
        logger.error(f"捕获基线失败 [{platform_id}]: {e}")
        return {"error": str(e)}


def _check_degradation(baseline: dict, current: dict) -> dict:
    """对比基线和当前指标，检测降级"""
    details = []
    degraded = False
    severity = "none"

    # 检查拒采率上升
    base_rejection = baseline.get("rejection_rate", 0)
    curr_rejection = current.get("rejection_rate", 0)
    if curr_rejection > base_rejection + 15:
        degraded = True
        severity = "critical"
        details.append(f"拒采率从 {base_rejection:.0f}% 升至 {curr_rejection:.0f}%（+{curr_rejection-base_rejection:.0f}%）")

    # 检查采信率下降
    base_citation = baseline.get("citation_rate", 0)
    if base_citation > 0:
        curr_citation = current.get("citation_rate", 0) if "citation_rate" in current else base_citation
        if curr_citation < base_citation * 0.7:
            degraded = True
            if severity != "critical":
                severity = "warning"
            details.append(f"采信率从 {base_citation:.0f}% 降至 {curr_citation:.0f}%")

    return {
        "degraded": degraded,
        "severity": severity,
        "details": "; ".join(details) if details else "无降级",
    }


async def scan_inventory(platform_id: str, run_id: str = "") -> dict:
    """扫描存量内容，标记需要调整的稿件

    读取 data/output/ 目录下的所有优化结果，标记那些使用了该平台的稿件。
    """
    from app.utils.config import get_data_dir
    output_dir = get_data_dir() / "output"
    if not output_dir.exists():
        return {"total": 0, "affected": 0, "article_ids": []}

    files = list(output_dir.glob("*.md")) + list(output_dir.glob("*.json"))
    affected = []

    for f in files:
        try:
            content = f.read_text(encoding="utf-8")[:5000]
            if platform_id in content or platform_id in f.stem:
                affected.append({
                    "text_id": f.stem,
                    "file": str(f.relative_to(output_dir)),
                    "size": f.stat().st_size,
                })
        except Exception:
            continue

    result = {
        "total": len(files),
        "affected": len(affected),
        "article_ids": [a["text_id"] for a in affected],
        "details": affected[:50],
    }

    # 更新运行记录
    if run_id:
        data = _load_run(run_id)
        if data:
            data["articles_affected"] = len(affected)
            _save_run_from_dict(data)

    logger.info(f"存量扫描完成: {result['affected']}/{result['total']} 篇需要调整 (平台={platform_id})")
    return result


async def auto_validate(text: str, platform_id: str) -> dict:
    """自动校验重生成内容的质量

    检查: 首段规范 / H标签层级 / FAQ存在 / Schema提示 / 禁词
    """
    import re
    errors = []
    warnings = []

    template = {}
    try:
        from app.core.template_engine import load_platform_template
        template = load_platform_template(platform_id)
    except Exception:
        pass

    verification = template.get("verification", {})

    # 1. 首段检查
    first_para = text.split("\n\n")[0] if "\n\n" in text else text[:300]
    if len(first_para) < 50:
        errors.append("首段过短(<50字)")
    elif len(first_para) > 400:
        warnings.append("首段过长(>400字)")

    # 2. H标签检查
    h2_count = len(re.findall(r"^##\s", text, re.MULTILINE))
    h3_count = len(re.findall(r"^###\s", text, re.MULTILINE))
    if h2_count == 0:
        errors.append("缺少H2标题")
    if h3_count == 0:
        warnings.append("缺少H3子标题")

    # 3. FAQ检查
    faq_pattern = re.findall(r"[问Q][：:].+[？?]", text)
    if template.get("body", {}).get("faq_count", {}).get("min", 0) > 0 and len(faq_pattern) < 2:
        warnings.append(f"FAQ不足(当前{len(faq_pattern)}组)")

    # 4. 禁词检查
    forbidden = verification.get("forbidden_words", [])
    found_forbidden = [w for w in forbidden if w in text]
    if found_forbidden:
        errors.append(f"发现禁词: {', '.join(found_forbidden)}")

    # 5. 合规检查
    try:
        from app.core.compliance import ComplianceChecker
        checker = ComplianceChecker()
        report = checker.check(text)
        if not report.passed:
            errors.append(f"合规问题: {report.violation_count}处违规")
    except Exception:
        pass

    passed = len(errors) == 0
    return {
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
        "score": max(0, 100 - len(errors) * 20 - len(warnings) * 5),
    }


async def post_publish_test(run_id: str, days: int = 3) -> dict:
    """发布后采信验证（3天/7天）"""
    data = _load_run(run_id)
    if not data:
        return {"error": "run_not_found"}

    try:
        from app.core.citation_tester import run_citation_test
        # 针对该平台运行5条核心测试
        result = await run_citation_test(
            platforms=[data["platform_id"]],
            query_count=5,
        )
        stats = result.get("aggregated_stats", {}).get("per_platform", {}).get(data["platform_id"], {})

        return {
            "run_id": run_id,
            "days": days,
            "test_id": result.get("test_id", ""),
            "citation_insights": {
                "top_sources": stats.get("cited_sources_pct", {}),
                "structure_features": stats.get("structure_features_pct", {}),
                "rejection_rate": sum(stats.get("rejection_signs_pct", {}).values()),
            },
        }
    except Exception as e:
        logger.error(f"发布后测试失败: {e}")
        return {"error": str(e)}


async def rollback_run(run_id: str) -> dict:
    """一键回滚：恢复旧模板版本"""
    data = _load_run(run_id)
    if not data:
        return {"error": "run_not_found"}

    platform_id = data["platform_id"]
    version_before = data.get("template_version_before", "")

    if version_before:
        try:
            from app.core.template_engine import rollback_template, get_template_history
            history = get_template_history(platform_id)
            # 回滚到适配前的版本
            for h in history:
                if f"v{h['version_num']}" == version_before:
                    rollback_template(platform_id, h["version_id"])
                    break
        except Exception as e:
            logger.error(f"回滚模板失败: {e}")

    data["status"] = "rolled_back"
    data["completed_at"] = datetime.now(timezone.utc).isoformat()
    _save_run_from_dict(data)

    logger.info(f"适配运行已回滚: {run_id}")
    return data


def _save_run_from_dict(data: dict):
    with open(_get_data_dir() / f"{data['run_id']}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_runs(platform_id: str = "", status: str = "", limit: int = 20) -> list[dict]:
    """列出适配运行记录"""
    data_dir = _get_data_dir()
    runs = []
    for f in sorted(data_dir.glob("adapt_*.json"), reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
            if platform_id and d.get("platform_id") != platform_id:
                continue
            if status and d.get("status") != status:
                continue
            runs.append(d)
            if len(runs) >= limit:
                break
        except Exception:
            continue
    return runs


def get_run(run_id: str) -> dict | None:
    """获取适配运行详情"""
    return _load_run(run_id)
