"""竞品自动监控引擎 — 3天周期自动化竞品内容采集与规则反推

核心流程：
1. 从 data/competitors/ 加载已注册的竞品
2. 对每个竞品，在启用的 AI 平台上用竞品相关 query 探测
3. 解析 AI 响应中的竞品引用证据（被引站点、内容特征、信源归属）
4. 反推竞品在平台上的有效内容策略（规则假设）
5. 与上一周期对比，检测竞品策略变化
6. 持久化结果到 data/competitors/monitoring/

约束：
- 如果没有配置 API 密钥，优雅降级（返回 skipped 状态）
- 使用 LLMFactory 适配器，支持所有已配置平台
- 对每个竞品-平台组合限流（避免触发 API 频率限制）
"""

import json
import logging
import hashlib
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── 配置加载 ──

def _load_monitor_config() -> dict[str, Any]:
    """加载竞品监控配置"""
    try:
        from app.utils.config import load_settings
        return load_settings().get("competitor_monitor", {})
    except Exception:
        return {}


def _get_data_dir() -> Path:
    """获取竞品监控数据目录"""
    config = _load_monitor_config()
    storage = config.get("storage_dir", "./data/competitors/monitoring")
    p = Path(storage)
    if not p.is_absolute():
        from app.utils.config import ROOT_DIR
        p = ROOT_DIR / storage
    p.mkdir(parents=True, exist_ok=True)
    return p


def _get_competitors_dir() -> Path:
    """获取竞品数据目录"""
    from app.utils.config import get_data_dir
    d = get_data_dir() / "competitors"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── 竞品数据加载 ──

def _load_competitors() -> list[dict[str, Any]]:
    """加载所有已注册的竞品"""
    comp_dir = _get_competitors_dir()
    competitors = []
    for f in sorted(comp_dir.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            # 跳过监控历史数据
            if "monitoring" in str(f.relative_to(comp_dir)):
                continue
            if data.get("name"):
                competitors.append({
                    "id": f.stem,
                    "name": data.get("name", ""),
                    "website": data.get("website", ""),
                    "industry": data.get("industry", ""),
                    "keywords": data.get("keywords", []),
                    "description": data.get("description", ""),
                })
        except Exception:
            continue
    return competitors


# ── 平台探测 ──

async def probe_competitor_on_platform(
    competitor: dict[str, Any], platform: str
) -> dict[str, Any]:
    """在指定 AI 平台上探测竞品的引用情况。

    使用 LLM 向平台发送搜索式查询，解析响应中是否引用了竞品内容。

    Args:
        competitor: 竞品信息 {name, website, industry, keywords, ...}
        platform: AI 平台 ID（如 "wenxin", "deepseek"）

    Returns:
        {
            "platform": str,
            "cited": bool,
            "citation_snippet": str,
            "content_features": [str],
            "source_attribution": str,
            "confidence": float,
            "error": str | None,
        }
    """
    config = _load_monitor_config()
    timeout = config.get("scrape_timeout", 30)

    result = {
        "platform": platform,
        "cited": False,
        "citation_snippet": "",
        "content_features": [],
        "source_attribution": "",
        "confidence": 0.0,
        "error": None,
    }

    # 构建探测查询
    comp_name = competitor.get("name", "")
    comp_industry = competitor.get("industry", "")
    comp_keywords = competitor.get("keywords", [])

    queries = [
        f"{comp_name} {comp_industry} 解决方案",
        f"{comp_name} 怎么样",
        f"{comp_name} 有什么优势",
    ]
    if comp_keywords:
        queries.insert(0, f"{comp_name} {' '.join(comp_keywords[:3])}")

    try:
        from app.services.llm.base import LLMFactory, LLMMessage
        from app.utils.config import load_settings, load_api_keys
        from app.models.enums import AIPlatform

        settings = load_settings()
        api_keys = load_api_keys()

        # 获取平台配置
        plat_cfg = settings.get("llm", {}).get("platforms", {}).get(platform, {})
        if not plat_cfg:
            result["error"] = f"平台 {platform} 未在配置中找到"
            return result

        key_info = api_keys.get("platforms", {}).get(platform, {})
        api_key = key_info.get("api_key", "")
        if not api_key or "your-" in str(api_key).lower():
            result["error"] = f"平台 {platform} 未配置API密钥"
            return result

        # 获取适配器类型
        try:
            ai_platform_enum = AIPlatform(platform)
            adapter_type = ai_platform_enum.adapter_type
        except ValueError:
            # 对于不在枚举中的平台，默认使用 openai_compat
            adapter_type = "openai_compat"

        # 创建 LLM 适配器
        llm = LLMFactory.create(
            platform=adapter_type,
            api_key=api_key,
            model_name=plat_cfg.get("model_name", ""),
            base_url=plat_cfg.get("base_url"),
        )

        # 只使用第一个查询进行探测（避免过多API调用）
        query = queries[0]

        # 发送查询
        response = await llm.chat(
            messages=[LLMMessage(role="user", content=query)],
            temperature=0.3,
            max_tokens=800,
            timeout=timeout,
        )

        content = response.content if hasattr(response, 'content') else str(response)

        if not content:
            result["error"] = "空响应"
            return result

        # 分析响应中是否包含竞品引用
        result["citation_snippet"] = content[:300]

        # 检测竞品名是否出现在响应中
        if comp_name and comp_name in content:
            result["cited"] = True
            result["confidence"] = 0.7
        else:
            # 检查竞品域名
            comp_website = competitor.get("website", "")
            if comp_website and comp_website.replace("https://", "").replace("http://", "").rstrip("/") in content:
                result["cited"] = True
                result["confidence"] = 0.6

        # 检测内容特征
        features = []
        feature_checks = {
            "FAQ": ("FAQ" in content or "常见问题" in content or "问：" in content),
            "structured_data": ("Schema" in content or "结构化" in content),
            "quantified": any(c.isdigit() for c in content[:200]),
            "authoritative_sourcing": ("官网" in content or "官方" in content),
            "list_format": content.count("\n- ") >= 2 or content.count("\n1. ") >= 2,
        }
        for feat_name, detected in feature_checks.items():
            if detected:
                features.append(feat_name)
        result["content_features"] = features

        # 检测信源归属
        sources = ["官网", "公众号", "知乎", "头条", "百家号", "搜狐"]
        for src in sources:
            if src in content:
                result["source_attribution"] = src
                break

        if result["cited"]:
            result["confidence"] += len(features) * 0.05
            result["confidence"] = min(result["confidence"], 0.95)

    except Exception as e:
        logger.debug(f"竞品探测失败 [{competitor.get('name')} @ {platform}]: {e}")
        result["error"] = str(e)

    return result


# ── 规则反推 ──

def reverse_engineer_rules(probe_results: list[dict]) -> dict[str, Any]:
    """从探测结果反推竞品有效内容策略。

    聚合跨平台探测结果，检测竞品在哪些平台被引用、
    哪些内容特征与引用率相关，生成规则假设。

    Args:
        probe_results: 单竞品跨平台探测结果列表

    Returns:
        {
            "citation_rate": float,
            "top_platforms": [str],
            "effective_patterns": [str],
            "rule_hypotheses": [{hypothesis, confidence, evidence}],
        }
    """
    total = len(probe_results)
    if total == 0:
        return {"citation_rate": 0, "top_platforms": [], "effective_patterns": [],
                "rule_hypotheses": []}

    cited_count = sum(1 for r in probe_results if r.get("cited"))
    citation_rate = cited_count / total if total > 0 else 0

    # 按引用置信度排序的平台
    top_platforms = sorted(
        [r for r in probe_results if r.get("cited")],
        key=lambda x: x.get("confidence", 0),
        reverse=True,
    )

    # 聚合内容特征
    feature_counts: dict[str, int] = {}
    for r in probe_results:
        for feat in r.get("content_features", []):
            feature_counts[feat] = feature_counts.get(feat, 0) + 1

    effective_patterns = sorted(feature_counts, key=feature_counts.get, reverse=True)

    # 生成规则假设
    hypotheses = []
    for plat_result in top_platforms[:3]:
        platform = plat_result.get("platform", "")
        features = plat_result.get("content_features", [])
        source = plat_result.get("source_attribution", "")

        if features:
            hypotheses.append({
                "hypothesis": f"竞品在 {platform} 平台被引用，特征: {', '.join(features)}" +
                              (f"，信源: {source}" if source else ""),
                "confidence": plat_result.get("confidence", 0),
                "evidence": {
                    "platform": platform,
                    "features": features,
                    "source": source,
                    "snippet": plat_result.get("citation_snippet", "")[:200],
                },
            })

    return {
        "citation_rate": round(citation_rate, 2),
        "top_platforms": [p.get("platform", "") for p in top_platforms],
        "effective_patterns": effective_patterns,
        "rule_hypotheses": hypotheses,
    }


# ── 监控周期执行 ──

async def run_competitor_monitor_cycle() -> dict[str, Any]:
    """执行一次完整的竞品监控周期。

    1. 加载竞品列表
    2. 对每个竞品在启用的平台上探测
    3. 反推规则
    4. 与上一周期对比
    5. 持久化结果

    Returns:
        完整的监控周期报告
    """
    config = _load_monitor_config()
    if not config.get("enabled", False):
        return {
            "status": "skipped",
            "reason": "disabled",
            "message": "竞品自动监控在配置中被禁用",
        }

    competitors = _load_competitors()
    if not competitors:
        return {
            "status": "skipped",
            "reason": "no_competitors",
            "message": "没有已注册的竞品，请先在竞品调研页面添加竞品",
        }

    # 检查哪些平台有可用的 API 密钥
    try:
        from app.utils.config import load_settings, load_api_keys
        settings = load_settings()
        api_keys = load_api_keys()
        available_platforms = []
        for plat_key, plat_cfg in settings.get("llm", {}).get("platforms", {}).items():
            if not plat_cfg.get("enabled", True):
                continue
            key_info = api_keys.get("platforms", {}).get(plat_key, {})
            api_key = key_info.get("api_key", "")
            if api_key and "your-" not in str(api_key).lower() and api_key != "YOUR_API_KEY":
                available_platforms.append(plat_key)
    except Exception:
        available_platforms = []

    platforms_to_probe = config.get("platforms_to_probe", [])
    enabled_platforms = [p for p in platforms_to_probe if p in available_platforms]

    if not enabled_platforms:
        return {
            "status": "skipped",
            "reason": "no_llm_configured",
            "message": "没有配置API密钥的AI平台，无法执行竞品探测",
            "available_platforms": available_platforms,
            "configured_platforms": available_platforms,
        }

    started_at = datetime.now(timezone.utc)
    cycle_id = f"comp_mon_{started_at.strftime('%Y%m%d_%H%M%S')}"

    logger.info(
        f"竞品监控周期开始: {cycle_id} "
        f"({len(competitors)}竞品 x {len(enabled_platforms)}平台)"
    )

    # 对每个竞品在每个平台上探测
    results = []
    for competitor in competitors:
        platform_probes = {}
        for platform in enabled_platforms:
            try:
                probe = await probe_competitor_on_platform(competitor, platform)
                platform_probes[platform] = probe
                # 限流：每个探测之间间隔1秒
                await asyncio.sleep(1)
            except Exception as e:
                logger.warning(f"竞品探测失败 [{competitor['name']} @ {platform}]: {e}")
                platform_probes[platform] = {
                    "platform": platform, "cited": False, "error": str(e),
                    "citation_snippet": "", "content_features": [],
                    "source_attribution": "", "confidence": 0,
                }

        # 反推规则
        probes_list = list(platform_probes.values())
        insights = reverse_engineer_rules(probes_list)

        results.append({
            "competitor_id": competitor["id"],
            "competitor_name": competitor["name"],
            "platform_probes": platform_probes,
            "aggregated_insights": insights,
        })

    # ── 跨竞品分析 ──
    all_patterns: dict[str, int] = {}
    for r in results:
        for p in r["aggregated_insights"].get("effective_patterns", []):
            all_patterns[p] = all_patterns.get(p, 0) + 1

    cross_insights = {
        "common_patterns": sorted(all_patterns, key=all_patterns.get, reverse=True),
        "divergent_strategies": [],
        "recommended_actions": [],
    }

    # 生成建议
    if "FAQ" in cross_insights["common_patterns"]:
        cross_insights["recommended_actions"].append(
            "竞品普遍使用FAQ结构获得引用，建议增强FAQ深度"
        )
    if "structured_data" in cross_insights["common_patterns"]:
        cross_insights["recommended_actions"].append(
            "结构化数据(Schema)是竞品共有的引用特征，建议完善JSON-LD"
        )

    # ── 与上一周期对比 ──
    previous = _load_previous_cycle()
    changes = _compare_cycles(previous, results) if previous else {
        "is_first_run": True,
        "new_patterns_detected": [],
        "pattern_drift": [],
        "alerts": [],
    }

    # ── 构建完整报告 ──
    report = {
        "cycle_id": cycle_id,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "competitors_probed": len(competitors),
        "platforms_probed": len(enabled_platforms),
        "results": results,
        "cross_competitor_insights": cross_insights,
        "previous_cycle_id": previous.get("cycle_id", "") if previous else "",
        "changes_from_previous": changes,
    }

    # ── 持久化 ──
    data_dir = _get_data_dir()
    output_file = data_dir / f"{started_at.strftime('%Y-%m-%d')}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 更新 latest.json 指针
    latest_file = data_dir / "latest.json"
    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump({"cycle_id": cycle_id, "date": started_at.strftime("%Y-%m-%d")}, f)

    logger.info(
        f"竞品监控周期完成: {cycle_id} "
        f"({len(competitors)}竞品, {len(enabled_platforms)}平台, "
        f"{len(changes.get('alerts', []))}项变化)"
    )
    return report


# ── 周期对比 ──

def _load_previous_cycle() -> dict | None:
    """加载上一周期的监控结果"""
    data_dir = _get_data_dir()
    latest_file = data_dir / "latest.json"
    if not latest_file.exists():
        return None

    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            latest = json.load(f)

        date_str = latest.get("date", "")
        if not date_str:
            return None

        cycle_file = data_dir / f"{date_str}.json"
        if not cycle_file.exists():
            return None

        # 确保不加载当前周期
        today = datetime.now().strftime("%Y-%m-%d")
        if date_str == today:
            # 查找更早的周期
            for i in range(1, 30):
                prev_date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                prev_file = data_dir / f"{prev_date}.json"
                if prev_file.exists():
                    with open(prev_file, "r", encoding="utf-8") as f:
                        return json.load(f)
            return None

        with open(cycle_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _compare_cycles(previous: dict, current_results: list[dict]) -> dict[str, Any]:
    """对比两个周期的竞品监控结果，检测变化。

    Returns:
        {
            "is_first_run": bool,
            "new_patterns_detected": [str],
            "pattern_drift": [str],
            "alerts": [{summary, severity, details}],
        }
    """
    if not previous:
        return {"is_first_run": True, "new_patterns_detected": [], "pattern_drift": [], "alerts": []}

    prev_results = previous.get("results", [])
    prev_map = {r["competitor_id"]: r for r in prev_results}
    curr_map = {r["competitor_id"]: r for r in current_results}

    new_patterns = []
    drift = []
    alerts = []

    for cid, curr in curr_map.items():
        prev = prev_map.get(cid)
        if prev is None:
            new_patterns.append(f"新增竞品: {curr['competitor_name']}")
            continue

        # 对比引用率
        prev_rate = prev.get("aggregated_insights", {}).get("citation_rate", 0)
        curr_rate = curr.get("aggregated_insights", {}).get("citation_rate", 0)

        if abs(curr_rate - prev_rate) > 0.3:
            direction = "上升" if curr_rate > prev_rate else "下降"
            drift.append(
                f"{curr['competitor_name']} 引用率 {direction}: "
                f"{prev_rate:.0%} -> {curr_rate:.0%}"
            )
            severity = "major" if abs(curr_rate - prev_rate) > 0.5 else "moderate"
            alerts.append({
                "summary": f"{curr['competitor_name']} 引用率显著{direction}",
                "severity": severity,
                "details": f"引用率从 {prev_rate:.0%} {direction}至 {curr_rate:.0%}",
            })

        # 对比有效模式
        prev_patterns = set(prev.get("aggregated_insights", {}).get("effective_patterns", []))
        curr_patterns = set(curr.get("aggregated_insights", {}).get("effective_patterns", []))
        gained = curr_patterns - prev_patterns
        lost = prev_patterns - curr_patterns

        if gained:
            new_patterns.append(f"{curr['competitor_name']} 新增特征: {', '.join(gained)}")
        if lost:
            drift.append(f"{curr['competitor_name']} 特征退化: {', '.join(lost)}")

    # 检测已移除的竞品
    for cid in prev_map:
        if cid not in curr_map:
            drift.append(f"竞品已移除: {prev_map[cid]['competitor_name']}")

    return {
        "is_first_run": False,
        "new_patterns_detected": new_patterns,
        "pattern_drift": drift,
        "alerts": alerts,
    }


# ── 历史查询 ──

def get_monitoring_history(days: int = 30) -> list[dict[str, Any]]:
    """获取最近N天的监控历史摘要。

    Returns:
        [{date, cycle_id, competitors_probed, platforms_probed, total_alerts}, ...]
    """
    data_dir = _get_data_dir()
    history = []
    for i in range(days):
        date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        cycle_file = data_dir / f"{date_str}.json"
        if cycle_file.exists():
            try:
                with open(cycle_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                history.append({
                    "date": date_str,
                    "cycle_id": data.get("cycle_id", ""),
                    "competitors_probed": data.get("competitors_probed", 0),
                    "platforms_probed": data.get("platforms_probed", 0),
                    "total_alerts": len(data.get("changes_from_previous", {}).get("alerts", [])),
                })
            except Exception:
                history.append({"date": date_str, "error": "文件损坏"})
        else:
            history.append({"date": date_str, "no_data": True})
    return history


def compare_cycles(cycle1_id: str, cycle2_id: str) -> dict[str, Any]:
    """对比两个监控周期的完整差异。

    Args:
        cycle1_id: 第一个周期ID
        cycle2_id: 第二个周期ID

    Returns:
        {cycle1, cycle2, diff_summary, per_competitor_diff}
    """
    data_dir = _get_data_dir()

    def _find_cycle(cycle_id: str) -> dict | None:
        for f in sorted(data_dir.glob("*.json")):
            if f.name in ("latest.json",):
                continue
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                if data.get("cycle_id") == cycle_id:
                    return data
            except Exception:
                continue
        return None

    data1 = _find_cycle(cycle1_id)
    data2 = _find_cycle(cycle2_id)

    if not data1:
        return {"error": f"周期不存在: {cycle1_id}"}
    if not data2:
        return {"error": f"周期不存在: {cycle2_id}"}

    # 生成对比摘要
    diff = _compare_cycles(data1, data2.get("results", []))

    return {
        "cycle1": {"id": cycle1_id, "date": data1.get("started_at", ""), "competitors": data1.get("competitors_probed", 0)},
        "cycle2": {"id": cycle2_id, "date": data2.get("started_at", ""), "competitors": data2.get("competitors_probed", 0)},
        "diff_summary": diff,
    }
