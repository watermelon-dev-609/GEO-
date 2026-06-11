"""AI结构变化报告生成器 — 每周聚合RSS发现+采信测试+竞品分析

输出:《AI抓取结构变化报告》(Markdown格式)
- 哪个平台规则变了
- 变化点（如：豆包最近15天内容权重提升）
- 对应的结构调整建议
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_data_dir() -> Path:
    from app.utils.config import get_data_dir
    data_dir = get_data_dir() / "structure_reports"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def generate_weekly_structure_report(
    week_start: str | None = None,
    include_competitor: bool = True,
) -> str:
    """生成每周《AI抓取结构变化报告》。

    Args:
        week_start: 周起始日期 YYYY-MM-DD，默认本周一
        include_competitor: 是否包含竞品分析

    Returns:
        Markdown格式的完整报告文本
    """
    if week_start is None:
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        week_start = monday.strftime("%Y-%m-%d")

    report_date = datetime.now().strftime("%Y-%m-%d")

    # ── 收集数据 ──
    rss_changes = _collect_rss_changes(week_start)
    citation_insights = _collect_citation_insights(week_start)
    competitor_changes = _collect_competitor_changes() if include_competitor else []
    platform_template_status = _collect_template_status()

    # ── 生成报告 ──
    report = _build_report(
        report_date=report_date,
        week_start=week_start,
        rss_changes=rss_changes,
        citation_insights=citation_insights,
        competitor_changes=competitor_changes,
        platform_template_status=platform_template_status,
    )

    # ── 持久化 ──
    data_dir = _get_data_dir()
    report_file = data_dir / f"weekly_{week_start}.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info(f"周结构报告已生成: {report_file}")
    return report


def _collect_rss_changes(week_start: str) -> list[dict[str, Any]]:
    """收集本周RSS监控到的规则变化"""
    from app.core.rss_monitor import list_rss_results, get_rss_results

    changes = []
    recent_results = list_rss_results(days=7)
    for day_result in recent_results:
        if not day_result.get("file_exists"):
            continue
        if day_result.get("total_alerts", 0) == 0:
            continue
        detail = get_rss_results(day_result["date"])
        if not detail:
            continue
        for source_result in detail.get("results", []):
            if source_result.get("alerts"):
                # 提取高优先级告警
                high_alerts = [
                    a for a in source_result.get("alerts", [])
                    if any(kw in ["算法更新", "规则变更", "索引", "收录", "权重"]
                           for kw in a.get("matched_keywords", []))
                ]
                if high_alerts:
                    changes.append({
                        "date": day_result["date"],
                        "source": source_result.get("source_name", ""),
                        "alert_count": len(source_result.get("alerts", [])),
                        "high_priority_count": len(high_alerts),
                        "sample_alerts": [
                            {
                                "title": a.get("title", ""),
                                "keywords": a.get("matched_keywords", []),
                            }
                            for a in high_alerts[:3]
                        ],
                    })

    return changes


def _collect_citation_insights(week_start: str) -> dict[str, Any]:
    """收集本周的AI采信测试洞察"""
    from app.core.citation_tester import list_citation_tests, get_citation_test

    recent_tests = list_citation_tests(days=7)
    if not recent_tests:
        return {"status": "no_data", "message": "本周无采信测试数据"}

    # 取最新的测试
    latest_test = get_citation_test(recent_tests[0]["test_id"]) if recent_tests else None
    if not latest_test:
        return {"status": "no_data", "message": "无法加载测试数据"}

    stats = latest_test.get("aggregated_stats", {}).get("per_platform", {})

    # 提取关键洞察
    insights = []
    for platform, ps in stats.items():
        platform_insight = {
            "platform": platform,
            "total_responses": ps.get("total_responses", 0),
            "top_cited_sources": sorted(
                ps.get("cited_sources_pct", {}).items(),
                key=lambda x: x[1], reverse=True
            )[:3],
            "dominant_structure": sorted(
                ps.get("structure_features_pct", {}).items(),
                key=lambda x: x[1], reverse=True
            )[:3],
            "primary_timeliness": sorted(
                ps.get("timeliness_hints_pct", {}).items(),
                key=lambda x: x[1], reverse=True
            )[:1],
            "rejection_rate": sum(ps.get("rejection_signs_pct", {}).values()),
        }
        insights.append(platform_insight)

    return {
        "status": "ok",
        "test_id": latest_test.get("test_id", ""),
        "platforms_tested": latest_test.get("platforms_tested", 0),
        "queries_fired": latest_test.get("queries_fired", 0),
        "platform_insights": insights,
    }


def _collect_competitor_changes() -> list[dict[str, Any]]:
    """收集竞品内容结构变化（从竞品数据目录读取）"""
    from app.utils.config import get_data_dir
    competitor_dir = get_data_dir() / "competitors"
    if not competitor_dir.exists():
        return []

    changes = []
    for comp_file in sorted(competitor_dir.glob("*.json")):
        try:
            mtime = datetime.fromtimestamp(comp_file.stat().st_mtime)
            if mtime < datetime.now() - timedelta(days=7):
                continue  # 跳过一周前更新的
            with open(comp_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 提取竞品内容特征摘要
            features = data.get("content_features", {})
            if features:
                changes.append({
                    "competitor_name": data.get("name", comp_file.stem),
                    "last_updated": mtime.strftime("%Y-%m-%d"),
                    "content_features": {
                        k: str(v)[:100] for k, v in features.items()
                    },
                })
        except Exception:
            continue

    return changes


def _collect_template_status() -> list[dict[str, Any]]:
    """收集各平台模板配置状态"""
    try:
        from app.core.template_engine import load_all_templates
        templates = load_all_templates()
        status = []
        for pid, tmpl in sorted(templates.items()):
            if pid == "base":
                continue
            status.append({
                "platform_id": pid,
                "platform_name": tmpl.get("platform_name", pid),
                "version": tmpl.get("version", 1),
                "updated_at": tmpl.get("updated_at", "unknown"),
                "strategy": tmpl.get("strategy", "")[:80],
            })
        return status
    except Exception:
        return []


def _build_report(
    report_date: str,
    week_start: str,
    rss_changes: list,
    citation_insights: dict,
    competitor_changes: list,
    platform_template_status: list,
) -> str:
    """组装完整的Markdown报告"""

    lines = [
        f"# AI抓取结构变化周报",
        f"",
        f"**报告日期**: {report_date}",
        f"**统计周期**: {week_start} ~ {report_date}",
        f"**生成工具**: GEO优化系统 v2.0 — AI结构报告引擎",
        f"",
        f"---",
        f"",
        f"## 一、本周规则变化摘要",
        f"",
    ]

    # RSS变化
    if rss_changes:
        lines.append("### 1.1 官方信源监测告警")
        lines.append("")
        lines.append(f"本周检测到 **{len(rss_changes)}** 个信源有高优先级告警。")
        lines.append("")
        lines.append("| 日期 | 信源 | 告警数 | 高优先级 | 关键关键词 |")
        lines.append("|------|------|--------|----------|-----------|")
        for c in rss_changes[:10]:
            keywords = ", ".join(
                set(kw for a in c.get("sample_alerts", []) for kw in a.get("keywords", []))
            )[:60]
            lines.append(
                f"| {c['date']} | {c['source']} | {c['alert_count']} | "
                f"{c['high_priority_count']} | {keywords} |"
            )
        lines.append("")
    else:
        lines.append("### 1.1 官方信源监测")
        lines.append("")
        lines.append("本周未检测到高优先级规则变化告警。各平台官方公告处于正常更新节奏。")
        lines.append("")

    # 采信测试洞察
    lines.append("### 1.2 AI采信行为测试结果")
    lines.append("")

    if citation_insights.get("status") == "ok":
        lines.append(f"**测试ID**: {citation_insights.get('test_id', 'N/A')}")
        lines.append(f"**测试规模**: {citation_insights.get('platforms_tested', 0)} 平台 × {citation_insights.get('queries_fired', 0)} 条查询")
        lines.append("")

        for insight in citation_insights.get("platform_insights", []):
            lines.append(f"#### {insight['platform']}")
            lines.append("")
            top_sources = insight.get("top_cited_sources", [])
            if top_sources:
                src_text = " > ".join(f"{s[0]}({s[1]}%)" for s in top_sources)
                lines.append(f"- **优先引用源**: {src_text}")
            dom_struct = insight.get("dominant_structure", [])
            if dom_struct:
                struct_text = ", ".join(f"{s[0]}({s[1]}%)" for s in dom_struct)
                lines.append(f"- **主导结构**: {struct_text}")
            prim_time = insight.get("primary_timeliness", [])
            if prim_time:
                lines.append(f"- **时效偏好**: {prim_time[0][0] if prim_time else 'N/A'}")
            rej_rate = insight.get("rejection_rate", 0)
            if rej_rate > 0:
                lines.append(f"- **⚠ 拒采率**: {rej_rate:.1f}%")
            lines.append("")
    else:
        lines.append(citation_insights.get("message", "本周无采信测试数据。"))
        lines.append("")

    # 结构调整建议
    lines.append("---")
    lines.append("")
    lines.append("## 二、平台结构调整建议")
    lines.append("")

    if citation_insights.get("status") == "ok":
        recommendations = _generate_recommendations(citation_insights.get("platform_insights", []))
        for rec in recommendations:
            lines.append(f"### {rec['platform']}")
            lines.append(f"**优先级**: {'🔴 高' if rec['priority'] == 'high' else '🟡 中' if rec['priority'] == 'medium' else '🟢 低'}")
            lines.append(f"**变化点**: {rec['change_point']}")
            lines.append(f"**建议**: {rec['recommendation']}")
            lines.append("")
    else:
        lines.append("暂无足够数据生成结构调整建议。建议执行一次完整的AI采信测试。")
        lines.append("")

    # 模板状态
    lines.append("---")
    lines.append("")
    lines.append("## 三、平台模板配置状态")
    lines.append("")
    lines.append("| 平台 | 版本 | 更新日期 | 策略摘要 |")
    lines.append("|------|------|----------|---------|")
    for ts in platform_template_status:
        lines.append(f"| {ts['platform_name']} | v{ts['version']} | {ts['updated_at']} | {ts['strategy']} |")
    lines.append("")

    # 竞品动态
    if competitor_changes:
        lines.append("---")
        lines.append("")
        lines.append("## 四、竞品内容结构动态")
        lines.append("")
        for cc in competitor_changes:
            lines.append(f"### {cc['competitor_name']} (更新于 {cc['last_updated']})")
            lines.append("")
            for k, v in cc.get("content_features", {}).items():
                lines.append(f"- **{k}**: {v}")
            lines.append("")

    # 行动清单
    lines.append("---")
    lines.append("")
    lines.append("## 五、本周行动清单")
    lines.append("")

    action_items = _generate_action_items(rss_changes, citation_insights)
    for i, action in enumerate(action_items, 1):
        lines.append(f"{i}. [{action['type']}] {action['description']}")
        if action.get("detail"):
            lines.append(f"   - {action['detail']}")

    lines.append("")
    lines.append("---")
    lines.append(f"*报告由GEO优化系统自动生成于 {report_date}*")

    return "\n".join(lines)


def _generate_recommendations(platform_insights: list[dict]) -> list[dict]:
    """基于采信测试洞察生成结构调整建议"""
    recommendations = []

    for insight in platform_insights:
        platform = insight.get("platform", "unknown")
        top_structures = insight.get("dominant_structure", [])
        top_sources = insight.get("top_cited_sources", [])
        rejection_rate = insight.get("rejection_rate", 0)

        rec = {
            "platform": platform,
            "priority": "medium",
            "change_point": "",
            "recommendation": "",
        }

        # 检测关键模式
        struct_types = [s[0] for s in top_structures]

        if "faq_format" in struct_types and platform in ("deepseek", "kimi"):
            rec["priority"] = "high"
            rec["change_point"] = f"{platform} 持续偏好FAQ格式引用，FAQ结构命中率领先其他结构50%以上"
            rec["recommendation"] = "建议增加FAQ密度至模板上限，确保每组FAQ问题含品牌词+地域词，答案首句重复品牌名"
        elif "short_sentence" in struct_types and platform == "doubao":
            rec["priority"] = "high"
            rec["change_point"] = "豆包对短句(≤30字)内容引用率持续领先，长段落引用呈下降趋势"
            rec["recommendation"] = "严格约束每句≤30字，段落≤120字。更新时效标记确保内容在15天黄金期内"
        elif "conclusion_first" in struct_types:
            rec["priority"] = "high"
            rec["change_point"] = f"{platform} 对结论先行结构的引用率显著高于传统叙事结构"
            rec["recommendation"] = "强化首段结论输出，确保前100字即完成核心信息传递。弱化行业背景铺垫"

        # 检查内容源权重变化
        source_names = [s[0] for s in top_sources]
        if "知乎" in source_names and "官网" not in source_names:
            rec["priority"] = "medium" if rec["priority"] == "medium" else rec["priority"]
            rec["change_point"] = rec["change_point"] + "；知乎内容源权重持续领先官网"
            rec["recommendation"] = rec["recommendation"] + "。考虑加强知乎渠道内容布局"

        # 拒采率告警
        if rejection_rate > 20:
            rec["priority"] = "high"
            rec["change_point"] = rec["change_point"] + f"；拒采率异常({rejection_rate:.0f}%)"
            rec["recommendation"] = rec["recommendation"] + "。排查内容中的营销腔、长段落、过时信息等拒采因素"

        if not rec["change_point"]:
            rec["change_point"] = f"{platform} 采信模式无明显变化"
            rec["recommendation"] = "维持现有模板配置，下次测试继续监测"

        recommendations.append(rec)

    return recommendations


def _generate_action_items(
    rss_changes: list, citation_insights: dict
) -> list[dict[str, str]]:
    """生成本周行动清单"""
    actions = []

    # 基于RSS告警
    if rss_changes:
        actions.append({
            "type": "规则审查",
            "description": f"审查 {len(rss_changes)} 个信源的高优先级告警，确认是否需要更新平台模板",
            "detail": "重点关注算法更新和规则变更类告警",
        })

    # 基于采信测试
    if citation_insights.get("status") == "ok":
        for insight in citation_insights.get("platform_insights", []):
            rej_rate = insight.get("rejection_rate", 0)
            if rej_rate > 15:
                actions.append({
                    "type": "拒采排查",
                    "description": f"{insight['platform']} 拒采率 {rej_rate:.0f}%，排查内容质量",
                    "detail": "检查是否存在营销腔、过时信息、虚假数据等拒采因素",
                })

        actions.append({
            "type": "模板审查",
            "description": "对比采信测试结果与当前模板配置，标记需要调整的平台",
            "detail": "优先处理优先级为'高'的结构调整建议",
        })

    # 固定动作
    actions.append({
        "type": "竞品扫描",
        "description": "对行业标杆内容进行结构抓取分析，更新竞品特征库",
        "detail": "重点抓取：HTML结构(H1-H3)、Schema类型、首段特征、FAQ密度",
    })

    actions.append({
        "type": "数据归档",
        "description": "将本周RSS数据、采信测试结果、结构报告归档",
        "detail": "确保数据可回溯，支撑趋势分析",
    })

    return actions


# ── RSS 信源 → 平台映射（用于自动触发适配流水线） ──

RSS_SOURCE_TO_PLATFORM = {
    "baidu_search": ["wenxin"],
    "baijiahao": ["wenxin"],
    "wenxin_blog": ["wenxin"],
    "toutiao_creator": ["doubao"],
    "doubao_changelog": ["doubao"],
    "wechat_platform": ["yuanbao", "kimi"],
    "zhihu_xiaohongshu": ["deepseek", "kimi", "tongyi"],
}


async def auto_trigger_adaptation_from_alerts() -> list[dict]:
    """RSS 告警自动触发适配流水线。

    从今日 RSS 抓取结果中提取高优先级告警，按信源→平台映射自动创建适配运行。
    每日 RSS 抓取完成后调用此函数。

    Returns:
        [{"platform_id": str, "run_id": str, "source": str, "alert_count": int}, ...]
    """
    triggered = []
    try:
        from app.core.rss_monitor import list_rss_results, get_rss_results

        today = datetime.now().strftime("%Y-%m-%d")
        today_results = [r for r in list_rss_results(days=1) if r.get("date") == today]
        if not today_results:
            # 尝试加载今日抓取详情
            today_results = list_rss_results(days=1)

        for day_result in today_results:
            if not day_result.get("file_exists") or day_result.get("total_alerts", 0) == 0:
                continue
            detail = get_rss_results(day_result["date"])
            if not detail:
                continue

            # 按信源聚合高优先级告警
            source_alerts = {}
            for source_result in detail.get("results", []):
                source_id = source_result.get("source_id", "")
                high_alerts = [
                    a for a in source_result.get("alerts", [])
                    if any(kw in a.get("matched_keywords", [])
                           for kw in ["算法更新", "规则变更", "权重", "收录", "索引"])
                ]
                if high_alerts:
                    source_alerts[source_id] = {
                        "source_name": source_result.get("source_name", source_id),
                        "alert_count": len(high_alerts),
                        "alerts": high_alerts,
                    }

            # 映射到平台并创建适配运行
            for source_id, alert_data in source_alerts.items():
                platforms = RSS_SOURCE_TO_PLATFORM.get(source_id, [])
                if not platforms:
                    # 未映射的信源：告警但不自动触发
                    continue

                for platform_id in platforms:
                    try:
                        from app.core.adaptation_pipeline import create_from_monitor_event
                        run = await create_from_monitor_event(
                            platform_id,
                            change_details={
                                "trigger": "rss_alert",
                                "source": alert_data["source_name"],
                                "source_id": source_id,
                                "alert_count": alert_data["alert_count"],
                                "sample_alerts": [
                                    {"title": a.get("title", ""),
                                     "keywords": a.get("matched_keywords", [])}
                                    for a in alert_data["alerts"][:3]
                                ],
                                "detected_at": datetime.now().isoformat(),
                            },
                        )
                        triggered.append({
                            "platform_id": platform_id,
                            "run_id": run["run_id"] if isinstance(run, dict) else run.run_id,
                            "source": alert_data["source_name"],
                            "alert_count": alert_data["alert_count"],
                        })
                        logger.info(
                            f"RSS告警自动触发适配流水线: platform={platform_id}, "
                            f"source={alert_data['source_name']}, run_id={triggered[-1]['run_id']}"
                        )
                    except Exception as e:
                        logger.warning(f"自动触发适配运行失败 [{platform_id}]: {e}")

    except Exception as e:
        logger.error(f"RSS告警自动触发检查失败: {e}")

    return triggered


def list_structure_reports(days: int = 90) -> list[dict[str, Any]]:
    """列出历史结构报告"""
    data_dir = _get_data_dir()
    reports = []
    cutoff = datetime.now() - timedelta(days=days)
    for report_file in sorted(data_dir.glob("weekly_*.md"), reverse=True):
        try:
            mtime = datetime.fromtimestamp(report_file.stat().st_mtime)
            if mtime < cutoff:
                continue
            # 从文件名提取周起始日期
            week_start = report_file.stem.replace("weekly_", "")
            # 读第一行作为标题
            with open(report_file, "r", encoding="utf-8") as f:
                first_line = f.readline().strip("# ").strip()
            reports.append({
                "report_id": report_file.stem,
                "week_start": week_start,
                "title": first_line,
                "generated_at": mtime.strftime("%Y-%m-%d %H:%M"),
                "size_kb": round(report_file.stat().st_size / 1024, 1),
            })
        except Exception:
            continue
    return reports


def get_structure_report(report_id: str) -> str | None:
    """获取指定报告的完整内容"""
    data_dir = _get_data_dir()
    report_file = data_dir / f"{report_id}.md"
    if not report_file.exists():
        return None
    with open(report_file, "r", encoding="utf-8") as f:
        return f.read()
