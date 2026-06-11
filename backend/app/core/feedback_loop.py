"""数据闭环引擎 — 核心指标计算、采信率下降检测、迭代建议生成

核心指标（每周统计）:
- AI 采信率: 内容在5大AI中的被引用次数 / 总检索次数
- 结构命中率: 新模板内容被AI引用时匹配预期结构特征的比例
- 时效衰减率: 内容发布后7/15/30/90天的引用率变化
- 违规拒采率: 因广告/堆砌/虚假数据被AI拒采的比例

迭代逻辑:
    采信率下降 → 回溯监控报告 → 定位结构问题 → 更新模板建议 → 重测
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_data_dir() -> Path:
    from app.utils.config import get_data_dir
    d = get_data_dir() / "feedback_metrics"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── 指标计算 ──

def calculate_weekly_metrics(platform_id: str | None = None) -> dict[str, Any]:
    """计算本周各平台的核心指标

    Returns:
        {
            "week_start": str,
            "platforms": {
                "doubao": {citation_rate, structure_hit_rate, time_decay, rejection_rate, ...},
                ...
            },
            "summary": {...},
        }
    """
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    week_start = monday.strftime("%Y-%m-%d")

    platforms = [platform_id] if platform_id else ["doubao", "wenxin", "tongyi", "deepseek", "kimi"]

    platform_metrics = {}
    for pid in platforms:
        metrics = _calc_platform_metrics(pid, week_start)
        if metrics:
            platform_metrics[pid] = metrics

    # 汇总
    if platform_metrics:
        avg_citation = sum(m["citation_rate"] for m in platform_metrics.values()) / len(platform_metrics)
        avg_rejection = sum(m["rejection_rate"] for m in platform_metrics.values()) / len(platform_metrics)
    else:
        avg_citation = 0
        avg_rejection = 0

    result = {
        "week_start": week_start,
        "calculated_at": today.isoformat(),
        "platforms": platform_metrics,
        "summary": {
            "avg_citation_rate": round(avg_citation, 1),
            "avg_rejection_rate": round(avg_rejection, 1),
            "platforms_with_data": len(platform_metrics),
            "platforms_dropping": sum(
                1 for m in platform_metrics.values() if m.get("citation_trend") == "down"
            ),
            **__extend_traffic_conversion_summary(),
        },
    }

    # 持久化
    _save_metrics(week_start, result)

    return result


def __extend_traffic_conversion_summary() -> dict:
    """扩展汇总数据，包含流量和转化指标"""
    try:
        from app.core.traffic_connector import get_traffic_summary
        traffic = get_traffic_summary(days=7)
    except Exception:
        traffic = {"ai_referral_visits": 0, "total_page_views": 0}
    try:
        from app.core.conversion_attribution import get_attribution
        conv = get_attribution(days=7)
    except Exception:
        conv = {"ai_attributed_count": 0, "total_conversions": 0, "ai_citation_rate_pct": 0.0}
    return {
        "ai_traffic_visits": traffic.get("ai_referral_visits", 0),
        "ai_attributed_conversions": conv.get("ai_attributed_count", 0),
        "ai_conversion_rate_pct": conv.get("ai_citation_rate_pct", 0.0),
        "total_conversions": conv.get("total_conversions", 0),
    }


def _calc_platform_metrics(platform_id: str, week_start: str) -> dict | None:
    """从采信测试数据计算单个平台的指标"""
    try:
        from app.core.citation_tester import list_citation_tests, get_citation_test

        tests = list_citation_tests(days=7)
        if not tests:
            return None

        latest = get_citation_test(tests[0]["test_id"])
        if not latest:
            return None

        stats = latest.get("aggregated_stats", {}).get("per_platform", {}).get(platform_id, {})
        if not stats:
            return None

        total = stats.get("total_responses", 0)
        if total == 0:
            return None

        # 采信率 = 有引用来源的响应数 / 总响应数
        cited_count = sum(
            1 for r in latest.get("results", [])
            if r.get("platform") == platform_id and r.get("cited_sources")
        )
        citation_rate = round(cited_count / total * 100, 1) if total > 0 else 0

        # 结构命中率 = 匹配预期结构的响应数 / 总响应数
        structure_hits = sum(
            1 for r in latest.get("results", [])
            if r.get("platform") == platform_id and len(r.get("structure_features", [])) >= 2
        )
        structure_hit_rate = round(structure_hits / total * 100, 1)

        # 拒采率
        rejection_pct = stats.get("rejection_signs_pct", {})
        rejection_rate = round(sum(rejection_pct.values()), 1)

        # 趋势（和上周对比）
        prev_metrics = _get_previous_week_metrics(platform_id)
        citation_trend = "stable"
        if prev_metrics:
            prev_rate = prev_metrics.get("citation_rate", 0)
            if citation_rate < prev_rate * 0.9:
                citation_trend = "down"
            elif citation_rate > prev_rate * 1.1:
                citation_trend = "up"

        return {
            "citation_rate": citation_rate,
            "structure_hit_rate": structure_hit_rate,
            "rejection_rate": rejection_rate,
            "citation_trend": citation_trend,
            "total_responses": total,
            "top_structure": sorted(
                stats.get("structure_features_pct", {}).items(),
                key=lambda x: x[1], reverse=True
            )[:3],
            "top_sources": sorted(
                stats.get("cited_sources_pct", {}).items(),
                key=lambda x: x[1], reverse=True
            )[:3],
        }
    except Exception as e:
        logger.warning(f"计算 {platform_id} 指标失败: {e}")
        return None


def _save_metrics(week_start: str, data: dict):
    with open(_get_data_dir() / f"{week_start}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_previous_week_metrics(platform_id: str) -> dict | None:
    """获取上周指标"""
    today = datetime.now()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_week = last_monday.strftime("%Y-%m-%d")
    fp = _get_data_dir() / f"{last_week}.json"
    if not fp.exists():
        return None
    try:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("platforms", {}).get(platform_id)
    except Exception:
        return None


# ── 采信率下降检测 ──

def detect_citation_drop(platform_id: str, threshold: float = 0.10) -> dict | None:
    """检测平台采信率是否显著下降

    Returns:
        None 如果没有显著下降
        {platform_id, current_rate, previous_rate, drop_pct, severity, ...}
    """
    current = _calc_platform_metrics(platform_id, datetime.now().strftime("%Y-%m-%d"))
    if not current:
        return None

    prev = _get_previous_week_metrics(platform_id)
    if not prev:
        return None

    current_rate = current.get("citation_rate", 0)
    prev_rate = prev.get("citation_rate", 0)

    if prev_rate == 0:
        return None

    drop = (prev_rate - current_rate) / prev_rate

    if drop >= threshold:
        severity = "critical" if drop >= 0.25 else "warning"
        return {
            "platform_id": platform_id,
            "current_rate": current_rate,
            "previous_rate": prev_rate,
            "drop_pct": round(drop * 100, 1),
            "severity": severity,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

    return None


# ── 回溯定位 ──

def backtrack_to_monitor_report(platform_id: str, drop_date: str | None = None) -> dict:
    """采信率下降时，回溯监控报告找可能原因"""
    try:
        from app.core.ai_structure_reporter import list_structure_reports, get_structure_report

        reports = list_structure_reports(days=14)
        relevant = []

        for r in reports:
            content = get_structure_reporter(r["report_id"])
            if content and platform_id in content:
                # 提取相关段落
                lines = content.split("\n")
                capture = False
                captured = []
                for line in lines:
                    if platform_id in line:
                        capture = True
                    if capture:
                        captured.append(line)
                        if len(captured) > 5:
                            break
                    if capture and line.startswith("##"):
                        break
                if captured:
                    relevant.append({
                        "report_id": r["report_id"],
                        "week": r.get("week_start", ""),
                        "relevant_lines": captured,
                    })

        return {
            "platform_id": platform_id,
            "reports_found": len(relevant),
            "relevant_reports": relevant[:3],
        }
    except Exception as e:
        return {"error": str(e)}


def locate_structure_issue(
    platform_id: str,
    monitor_report: dict | None = None,
    content_text: str | None = None,
) -> dict:
    """定位具体结构问题。

    Args:
        platform_id: 平台ID
        monitor_report: 监控报告（可选）
        content_text: 实际生成的内容文本。提供时基于实际内容分析；
                      不提供时回退到模板配置检查。

    Returns:
        {"platform_id": str, "issues_found": int, "issues": [...], "analysis_mode": "content"|"template"}
    """
    try:
        from app.core.template_engine import load_platform_template
        import re

        template = load_platform_template(platform_id)
        if not template:
            return {"platform_id": platform_id, "issues_found": 0, "issues": [], "analysis_mode": "template"}

        issues = []
        body = template.get("body", {})
        header = template.get("header", {})

        # ── 基于实际内容分析（优先） ──
        if content_text and len(content_text.strip()) >= 100:
            return _analyze_actual_content(platform_id, content_text, template)

        # ── 回退：基于模板配置检查 ──
        metrics = _calc_platform_metrics(platform_id, datetime.now().strftime("%Y-%m-%d"))
        if metrics:
            top_structures = [s[0] for s in metrics.get("top_structure", [])]

            if "faq_format" in top_structures:
                faq = body.get("faq_count", {})
                if faq.get("min", 0) < 3:
                    issues.append({
                        "component": "body.faq_count",
                        "issue": "FAQ数量不足（模板配置）",
                        "current": faq,
                        "suggestion": "建议 min 至少设为3，并确保实际生成内容满足此要求",
                    })

            if "short_sentence" in top_structures:
                para = body.get("paragraph_length", {})
                if para.get("max", 400) > 150:
                    issues.append({
                        "component": "body.paragraph_length",
                        "issue": "段落长度偏大，平台偏好短句（模板配置）",
                        "current": para,
                        "suggestion": "建议 max 降至150字，并确保实际生成内容满足此要求",
                    })

            if "conclusion_first" in top_structures:
                first_rules = header.get("first_paragraph_rules", [])
                if not any("结论先行" in r or "利益前置" in r for r in first_rules):
                    issues.append({
                        "component": "header.first_paragraph_rules",
                        "issue": "缺少结论先行规则（模板配置）",
                        "suggestion": "添加'结论先行，首段1-2句说清核心价值'",
                    })

        return {
            "platform_id": platform_id,
            "issues_found": len(issues),
            "issues": issues,
            "analysis_mode": "template",
        }
    except Exception as e:
        return {"error": str(e)}


def _analyze_actual_content(platform_id: str, text: str, template: dict) -> dict:
    """基于实际生成内容分析结构问题，使用平台专属阈值"""
    import re

    issues = []
    body = template.get("body", {})
    header = template.get("header", {})
    verification = template.get("verification", {})

    # ── 1. FAQ 数量检查 ──
    qa_pattern = re.findall(
        r'(?:什么是|是什么|如何|怎么|怎样|为什么|能不能|可以|哪些|哪家|多少钱|怎么样|在哪|好不好|哪种|哪个|有没有|会不会)[^。；\n]{0,80}[？?]',
        text
    )
    # 也匹配 **Q:** 格式
    qa_markdown = re.findall(r'\*\*Q[：:]\s*', text)
    actual_faq_count = max(len(qa_pattern), len(qa_markdown))

    faq_config = body.get("faq_count", {})
    faq_min = faq_config.get("min", 3)
    if actual_faq_count < faq_min:
        issues.append({
            "component": "content.faq_count",
            "issue": f"实际FAQ数量不足：文本中仅检测到 {actual_faq_count} 组问答（要求≥{faq_min}）",
            "current_value": actual_faq_count,
            "required_value": faq_min,
            "suggestion": f"增加至少 {faq_min - actual_faq_count} 组 FAQ 问答对，每组问题包含长尾关键词，答案首句包含品牌名",
        })

    # ── 2. 段落长度检查 ──
    paragraphs = [p.strip() for p in re.split(r'\n\n+', text) if len(p.strip()) >= 20]
    para_config = body.get("paragraph_length", {})
    para_max = para_config.get("max", 350)
    para_min = para_config.get("min", 40)

    long_paragraphs = []
    for i, p in enumerate(paragraphs):
        p_len = len(p)
        if p_len > para_max:
            long_paragraphs.append({"index": i, "length": p_len, "excerpt": p[:80] + "..."})
    if long_paragraphs:
        issues.append({
            "component": "content.paragraph_length",
            "issue": f"{len(long_paragraphs)}/{len(paragraphs)} 个段落超过平台上限（>{para_max}字）",
            "current_value": [lp["length"] for lp in long_paragraphs[:5]],
            "required_value": f"≤{para_max}字",
            "suggestion": f"将超长段落拆分为 {para_min}-{para_max} 字的短段落，每个段落聚焦一个信息点",
        })

    # ── 3. 句长检查（豆包等平台硬约束） ──
    special_rule = body.get("special_rule", "")
    if "30" in str(special_rule) or platform_id == "doubao":
        sentences = re.split(r'[。！；\n]', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        long_sentences = [s for s in sentences if len(s) > 30]
        long_ratio = len(long_sentences) / max(len(sentences), 1)
        if long_ratio > 0.20:
            issues.append({
                "component": "content.sentence_length",
                "issue": f"超长句占比 {long_ratio:.0%}（{len(long_sentences)}/{len(sentences)} 句>30字），超过平台上限20%",
                "current_value": f"{long_ratio:.0%}",
                "required_value": "≤20%",
                "suggestion": "将超过30字的句子用句号断开，确保全文中80%以上句子≤30字",
            })

    # ── 4. 品牌实体密度检查（Kimi等平台要求） ──
    from app.utils.config import get_enterprise_name, get_enterprise_location
    brand_name = get_enterprise_name()
    if brand_name:
        brand_count = text.count(brand_name)
        brand_min = 5 if platform_id in ("kimi", "claude") else 3
        if brand_count < brand_min:
            issues.append({
                "component": "content.brand_density",
                "issue": f"品牌名 '{brand_name}' 仅出现 {brand_count} 次（要求≥{brand_min}次）",
                "current_value": brand_count,
                "required_value": f"≥{brand_min}",
                "suggestion": f"在每个 H2 段落首句和 FAQ 答案首句中自然嵌入品牌全称",
            })

    # ── 5. 首段规则检查 ──
    first_para = paragraphs[0] if paragraphs else text[:300]
    first_rules = header.get("first_paragraph_rules", [])

    if platform_id == "doubao":
        # 豆包：首段30字结论先行
        first_sentence = first_para.split("。")[0] if "。" in first_para else first_para[:60]
        if len(first_sentence) > 40:
            issues.append({
                "component": "content.first_paragraph",
                "issue": f"首句 {len(first_sentence)} 字，超过豆包建议的≤30字结论先行",
                "current_value": f"{len(first_sentence)}字",
                "suggestion": "首句压缩至30字内，直接回答'能帮你做什么'",
            })

    if platform_id in ("deepseek", "tongyi"):
        # DeepSeek/通义：首段含企业名+核心技术参数
        has_brand = brand_name and brand_name in first_para[:200]
        has_tech_param = bool(re.search(r'\d+[:：]\d+|\d+[\.]?\d*\s*(ms|mm|m²|㎡|%)', first_para[:200]))
        if not (has_brand and has_tech_param):
            missing = []
            if not has_brand:
                missing.append("企业全称")
            if not has_tech_param:
                missing.append("核心技术参数")
            issues.append({
                "component": "content.first_paragraph",
                "issue": f"首段缺少: {', '.join(missing)}（平台要求首段含品牌名+技术参数）",
                "suggestion": "首段格式：'{产品名} — 比例精度：1:500，响应时间：<50ms。{企业全称}提供...'",
            })

    # ── 6. 禁词检查 ──
    forbidden_words = verification.get("forbidden_words", [])
    found_forbidden = []
    for word in forbidden_words:
        if word in text:
            found_forbidden.append(word)
    if found_forbidden:
        issues.append({
            "component": "content.forbidden_words",
            "issue": f"检测到平台禁词: {', '.join(found_forbidden)}",
            "current_value": found_forbidden,
            "suggestion": f"替换禁词为具体量化表述，如'行业领先'→'累计交付200+项目'",
        })

    # ── 7. 量化数据密度检查 ──
    quant_count = len(re.findall(r'\d+[+]?\s*(?:个|项|套|年|㎡|平方米|公里|人|次|万元|亿|%|以上|余家)', text))
    quant_count += len(re.findall(r'\d+[:：]\d+', text))
    data_config = template.get("data", {})
    quant_required = len(data_config.get("quantified_requirements", []))
    if quant_required == 0:
        quant_required = 3  # base.yaml 默认要求
    if quant_count < quant_required:
        issues.append({
            "component": "content.quantified_data",
            "issue": f"量化数据不足：检测到 {quant_count} 处（要求≥{quant_required}处）",
            "current_value": quant_count,
            "required_value": f"≥{quant_required}",
            "suggestion": "为每个技术能力点补充至少1个量化指标，使用'参数名：数值（单位）'标准格式",
        })

    return {
        "platform_id": platform_id,
        "issues_found": len(issues),
        "issues": issues,
        "analysis_mode": "content",
        "content_stats": {
            "total_length": len(text),
            "paragraph_count": len(paragraphs),
            "faq_count": actual_faq_count,
            "brand_occurrences": text.count(brand_name) if brand_name else 0,
            "quantified_data_count": quant_count,
            "forbidden_words_found": found_forbidden,
        },
    }


# ── 迭代建议 ──

def generate_iteration_recommendation(platform_id: str) -> dict:
    """生成完整的迭代建议

    1. 检查采信率下降
    2. 回溯监控报告
    3. 定位结构问题
    4. 推荐模板更新
    """
    # 检测下降
    drop = detect_citation_drop(platform_id)
    if not drop:
        return {
            "platform_id": platform_id,
            "action": "no_action",
            "message": f"{platform_id} 采信率稳定，无需迭代",
            "citation_status": "stable",
        }

    # 回溯
    backtrack = backtrack_to_monitor_report(platform_id)

    # 定位
    structure = locate_structure_issue(platform_id, backtrack)

    # 组装建议
    action_steps = []
    if structure.get("issues"):
        for issue in structure["issues"]:
            action_steps.append({
                "type": "template_update",
                "component": issue["component"],
                "description": issue["issue"],
                "suggestion": issue["suggestion"],
            })

    action_steps.append({
        "type": "regenerate",
        "description": "批量重新生成该平台所有优化文案",
    })

    action_steps.append({
        "type": "retest",
        "description": "发布后3天和7天执行采信测试验证效果",
    })

    return {
        "platform_id": platform_id,
        "action": "iteration_required",
        "severity": drop["severity"],
        "citation_status": "dropping",
        "drop_details": drop,
        "backtrack_summary": f"找到 {backtrack.get('reports_found', 0)} 份相关报告",
        "structure_issues": structure.get("issues", []),
        "action_steps": action_steps,
    }


# ── 历史查询 ──

def get_metrics_history(platform_id: str, weeks: int = 12) -> list[dict]:
    """获取指定平台的历史指标趋势"""
    data_dir = _get_data_dir()
    history = []

    for _ in range(weeks):
        monday = datetime.now() - timedelta(days=datetime.now().weekday() + _ * 7)
        week_key = monday.strftime("%Y-%m-%d")
        fp = data_dir / f"{week_key}.json"
        if fp.exists():
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                pm = data.get("platforms", {}).get(platform_id, {})
                if pm:
                    history.append({
                        "week_start": week_key,
                        "citation_rate": pm.get("citation_rate", 0),
                        "structure_hit_rate": pm.get("structure_hit_rate", 0),
                        "rejection_rate": pm.get("rejection_rate", 0),
                        "citation_trend": pm.get("citation_trend", "stable"),
                    })
            except Exception:
                continue

    return history


def get_iteration_history(limit: int = 20) -> list[dict]:
    """获取迭代建议历史"""
    data_dir = _get_data_dir()
    history = []
    for fp in sorted(data_dir.glob("iteration_*.json"), reverse=True)[:limit]:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                history.append(json.load(f))
        except Exception:
            continue
    return history


def save_iteration_recommendation(recommendation: dict):
    """保存迭代建议"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(_get_data_dir() / f"iteration_{ts}.json", "w", encoding="utf-8") as f:
        json.dump(recommendation, f, ensure_ascii=False, indent=2)
