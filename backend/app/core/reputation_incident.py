"""舆情事件管理引擎 — 事件全生命周期管理（创建→调查→响应→解决）

设计原则:
- 事件工单模式: 参考 adaptation_pipeline 的阶段设计，明确状态机
- JSON文件存储: 延续项目无数据库约定
- 与 sentiment_classifier 解耦: 接收情感分析结果作为输入
"""

from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from app.utils.config import get_data_dir, load_settings
from app.models.enums import IncidentStatus, IncidentSeverity

logger = logging.getLogger(__name__)


def _get_incidents_dir() -> Path:
    d = get_data_dir() / "reputation" / "incidents"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_corrections_dir() -> Path:
    d = get_data_dir() / "reputation" / "corrections"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ══════════════════════════════════════════════════════════════
# 事件CRUD
# ══════════════════════════════════════════════════════════════

def create_incident(
    platform: str,
    query: str,
    ai_response: str,
    sentiment: dict[str, Any] | None = None,
    brand_mentioned: bool = False,
    severity: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """创建舆情事件工单

    Args:
        platform: AI平台ID
        query: 触发的用户查询
        ai_response: AI回复摘录（最多500字）
        sentiment: 情感分析结果（来自 sentiment_classifier.classify()）
        brand_mentioned: 品牌是否被提及
        severity: 严重度（空则自动评估）
        extra: 额外信息

    Returns:
        完整事件dict
    """
    now = datetime.now(timezone.utc)
    incident_id = f"inc_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    # 自动评估严重度
    if not severity and sentiment:
        from app.core.sentiment_classifier import assess_severity
        severity = assess_severity(sentiment)
    if not severity:
        severity = "low"

    incident = {
        "incident_id": incident_id,
        "platform": platform,
        "query": query,
        "brand_mentioned": brand_mentioned,
        "sentiment": sentiment,
        "ai_response_snippet": ai_response[:500] if ai_response else "",
        "severity": severity,
        "status": "open",
        "created_at": now.isoformat(),
        "resolved_at": None,
        "correction_content": None,
        "correction_published": False,
        "timeline": [
            {
                "timestamp": now.isoformat(),
                "action": "created",
                "status": "open",
                "notes": f"自动创建 - 严重度: {severity}",
            }
        ],
        "notes": [],
        "extra": extra or {},
    }

    _save_incident(incident)
    logger.info(f"舆情事件已创建: {incident_id} (严重度={severity}, 平台={platform})")
    return incident


def get_incident(incident_id: str) -> dict[str, Any] | None:
    """获取事件详情"""
    fp = _get_incidents_dir() / f"{incident_id}.json"
    if not fp.exists():
        return None
    try:
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"读取事件失败 [{incident_id}]: {e}")
        return None


def update_incident_status(
    incident_id: str,
    new_status: str,
    notes: str = "",
) -> dict[str, Any]:
    """更新事件状态（含状态机校验）

    Args:
        incident_id: 事件ID
        new_status: 目标状态 (open/investigating/responding/resolved/dismissed)
        notes: 备注

    Returns:
        更新后的事件dict

    Raises:
        ValueError: 状态不存在或状态流转不合法
    """
    incident = get_incident(incident_id)
    if not incident:
        raise ValueError(f"事件不存在: {incident_id}")

    current = incident.get("status", "open")

    # 校验状态流转
    try:
        status_enum = IncidentStatus(current)
        allowed = status_enum.next_states
    except ValueError:
        allowed = []

    if new_status not in allowed and new_status != current:
        raise ValueError(
            f"状态流转不合法: {current} → {new_status}。允许的目标状态: {allowed}"
        )

    now = datetime.now(timezone.utc)
    incident["status"] = new_status

    # 结案时记录时间
    if new_status in ("resolved", "dismissed"):
        incident["resolved_at"] = now.isoformat()

    # 添加时间线
    action_map = {
        "investigating": "started_investigation",
        "responding": "started_response",
        "resolved": "resolved",
        "dismissed": "dismissed",
        "open": "reopened",
    }
    incident.setdefault("timeline", []).append({
        "timestamp": now.isoformat(),
        "action": action_map.get(new_status, "status_changed"),
        "status": new_status,
        "notes": notes or f"状态变更: {current} → {new_status}",
    })

    if notes:
        incident.setdefault("notes", []).append({
            "timestamp": now.isoformat(),
            "content": notes,
        })

    _save_incident(incident)
    logger.info(f"事件状态更新: {incident_id} → {new_status}")
    return incident


def resolve_incident(incident_id: str, resolution: str = "") -> dict[str, Any]:
    """结案事件"""
    return update_incident_status(incident_id, "resolved", resolution)


def dismiss_incident(incident_id: str, reason: str = "") -> dict[str, Any]:
    """忽略事件"""
    return update_incident_status(incident_id, "dismissed", reason)


def list_incidents(
    platform: str = "",
    severity: str = "",
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """列出舆情事件（支持多条件筛选）

    Args:
        platform: 按平台筛选
        severity: 按严重度筛选
        status: 按状态筛选
        date_from: 起始日期 ISO格式
        date_to: 结束日期 ISO格式
        limit: 返回条数上限
        offset: 偏移量
    """
    incidents_dir = _get_incidents_dir()
    incidents = []

    for fp in sorted(incidents_dir.glob("inc_*.json"), reverse=True):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                inc = json.load(f)
        except Exception:
            continue

        # 筛选
        if platform and inc.get("platform") != platform:
            continue
        if severity and inc.get("severity") != severity:
            continue
        if status and inc.get("status") != status:
            continue
        if date_from and inc.get("created_at", "")[:10] < date_from[:10]:
            continue
        if date_to and inc.get("created_at", "")[:10] > date_to[:10]:
            continue

        incidents.append(inc)

    return incidents[offset:offset + limit]


def get_incident_timeline(incident_id: str) -> list[dict[str, Any]]:
    """获取事件时间线"""
    incident = get_incident(incident_id)
    if not incident:
        return []
    return incident.get("timeline", [])


def set_correction_content(incident_id: str, correction_text: str) -> dict[str, Any]:
    """为事件设置纠正内容"""
    incident = get_incident(incident_id)
    if not incident:
        raise ValueError(f"事件不存在: {incident_id}")

    incident["correction_content"] = correction_text
    now = datetime.now(timezone.utc)
    incident.setdefault("timeline", []).append({
        "timestamp": now.isoformat(),
        "action": "correction_generated",
        "status": incident["status"],
        "notes": "已生成纠正内容",
    })

    _save_incident(incident)
    return incident


def mark_correction_published(incident_id: str) -> dict[str, Any]:
    """标记纠正内容已发布"""
    incident = get_incident(incident_id)
    if not incident:
        raise ValueError(f"事件不存在: {incident_id}")

    incident["correction_published"] = True
    now = datetime.now(timezone.utc)
    incident.setdefault("timeline", []).append({
        "timestamp": now.isoformat(),
        "action": "correction_published",
        "status": incident["status"],
        "notes": "纠正内容已发布",
    })

    _save_incident(incident)
    return incident


# ══════════════════════════════════════════════════════════════
# 自动扫描
# ══════════════════════════════════════════════════════════════

async def auto_scan_and_create(
    sandtable_type: str = "general",
    platforms: list[str] | None = None,
    auto_create: bool = True,
) -> dict[str, Any]:
    """自动扫描最新品牌监测结果，为负面/不实提及创建事件

    流程:
    1. 加载最新的品牌监测 session
    2. 对每条品牌提及进行情感分类
    3. 对负面/不实结果自动创建事件

    Returns:
        {
            "scan_id": str,
            "scanned_count": int,
            "issues_found": int,
            "incidents_created": int,
            "details": [...],
        }
    """
    from app.core.sentiment_classifier import SentimentClassifier, assess_severity
    from app.core.brand_checker import BrandMentionChecker

    now = datetime.now(timezone.utc)
    scan_id = f"scan_{now.strftime('%Y%m%d_%H%M%S')}"

    # 加载最新品牌监测结果
    checker = BrandMentionChecker()
    session = await checker.check_all_platforms(
        platforms=platforms or [],
        query_categories=["brand_direct", "scenario"],
        max_per_category=3,
        sandtable_type=sandtable_type,
    )

    results = session.get("results", [])
    if not results:
        return {
            "scan_id": scan_id,
            "scanned_count": 0,
            "issues_found": 0,
            "incidents_created": 0,
            "details": [],
            "message": "没有可分析的品牌监测数据",
        }

    # 情感分类
    classifier = SentimentClassifier()
    llm_adapter = _get_default_llm()

    enriched = await classifier.batch_classify(results, llm_adapter)

    # 识别问题
    issues = []
    incidents_created = 0

    for item in enriched:
        sentiment = item.get("sentiment", {})
        polarity = sentiment.get("polarity", "neutral")
        accuracy = sentiment.get("factual_accuracy", "unverifiable")

        # 判定是否需要创建事件
        is_issue = (
            polarity == "negative" or
            accuracy in ("inaccurate", "partially_accurate")
        )

        if is_issue:
            severity = assess_severity(sentiment)
            issues.append({
                "platform": item.get("platform"),
                "query": item.get("query"),
                "polarity": polarity,
                "accuracy": accuracy,
                "severity": severity,
                "summary": sentiment.get("summary", ""),
            })

            if auto_create:
                try:
                    create_incident(
                        platform=item.get("platform", ""),
                        query=item.get("query", ""),
                        ai_response=item.get("full_response") or item.get("mention_context", ""),
                        sentiment=sentiment,
                        brand_mentioned=item.get("brand_mentioned", False),
                        severity=severity,
                    )
                    incidents_created += 1
                except Exception as e:
                    logger.warning(f"自动创建事件失败: {e}")

    scan_report = {
        "scan_id": scan_id,
        "scanned_at": now.isoformat(),
        "scanned_count": len(enriched),
        "issues_found": len(issues),
        "incidents_created": incidents_created,
        "details": issues,
    }

    # 持久化
    scan_dir = get_data_dir() / "reputation" / "scans"
    scan_dir.mkdir(parents=True, exist_ok=True)
    with open(scan_dir / f"{scan_id}.json", "w", encoding="utf-8") as f:
        json.dump(scan_report, f, ensure_ascii=False, indent=2)

    logger.info(
        f"舆情扫描完成: {scan_id} "
        f"(扫描{len(enriched)}条, 发现{len(issues)}个问题, 创建{incidents_created}个事件)"
    )
    return scan_report


# ══════════════════════════════════════════════════════════════
# 统计
# ══════════════════════════════════════════════════════════════

def get_reputation_stats() -> dict[str, Any]:
    """获取舆情统计概览"""
    incidents = list_incidents(limit=500)

    total = len(incidents)
    open_count = sum(1 for i in incidents if i["status"] in ("open", "investigating", "responding"))
    critical_count = sum(1 for i in incidents if i["severity"] == "critical")

    # 本月已解决
    this_month = datetime.now().strftime("%Y-%m")
    resolved_this_month = sum(
        1 for i in incidents
        if i["status"] == "resolved"
        and (i.get("resolved_at", "") or "").startswith(this_month)
    )

    # 情感统计
    def _sent_polarity(incident: dict) -> str:
        s = incident.get("sentiment")
        if not s or not isinstance(s, dict):
            return "unknown"
        return s.get("polarity", "unknown")

    positive_count = sum(1 for i in incidents if _sent_polarity(i) == "positive")
    negative_count = sum(1 for i in incidents if _sent_polarity(i) == "negative")
    neutral_count = sum(1 for i in incidents if _sent_polarity(i) == "neutral")
    total_with_sentiment = max(positive_count + negative_count + neutral_count, 1)

    positive_rate = round(positive_count / total_with_sentiment * 100, 1)
    negative_rate = round(negative_count / total_with_sentiment * 100, 1)

    # 按平台统计
    by_platform: dict[str, dict] = {}
    for i in incidents:
        p = i.get("platform", "unknown")
        if p not in by_platform:
            by_platform[p] = {"total": 0, "open": 0, "critical": 0, "resolved": 0}
        by_platform[p]["total"] += 1
        if i["status"] in ("open", "investigating", "responding"):
            by_platform[p]["open"] += 1
        if i["severity"] == "critical":
            by_platform[p]["critical"] += 1
        if i["status"] == "resolved":
            by_platform[p]["resolved"] += 1

    # 按严重度统计
    by_severity: dict[str, int] = {}
    for i in incidents:
        sev = i.get("severity", "low")
        by_severity[sev] = by_severity.get(sev, 0) + 1

    # 最近事件
    recent = sorted(incidents, key=lambda x: x.get("created_at", ""), reverse=True)[:10]

    return {
        "total_incidents": total,
        "open_incidents": open_count,
        "critical_incidents": critical_count,
        "resolved_this_month": resolved_this_month,
        "positive_rate": positive_rate,
        "negative_rate": negative_rate,
        "by_platform": by_platform,
        "by_severity": by_severity,
        "recent_incidents": [
            {
                "incident_id": i["incident_id"],
                "platform": i.get("platform"),
                "query": i.get("query", ""),
                "severity": i.get("severity"),
                "status": i.get("status"),
                "created_at": i.get("created_at"),
                "sentiment_summary": (i.get("sentiment") or {}).get("summary", ""),
            }
            for i in recent
        ],
    }


def get_sentiment_trend(days: int = 30) -> list[dict[str, Any]]:
    """获取情感趋势数据（按天聚合）"""
    incidents = list_incidents(limit=1000)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    by_date: dict[str, dict] = {}
    for i in incidents:
        created = i.get("created_at", "")[:10]
        if created < cutoff[:10]:
            continue

        if created not in by_date:
            by_date[created] = {
                "date": created,
                "total": 0,
                "positive": 0,
                "neutral": 0,
                "negative": 0,
                "critical": 0,
                "by_platform": {},
            }

        by_date[created]["total"] += 1

        polarity = (i.get("sentiment") or {}).get("polarity", "neutral")
        if polarity in ("positive", "neutral", "negative"):
            by_date[created][polarity] += 1

        if i.get("severity") == "critical":
            by_date[created]["critical"] += 1

        platform = i.get("platform", "unknown")
        by_date[created]["by_platform"][platform] = \
            by_date[created]["by_platform"].get(platform, 0) + 1

    return sorted(by_date.values(), key=lambda x: x["date"])


# ══════════════════════════════════════════════════════════════
# 辅助
# ══════════════════════════════════════════════════════════════

def _save_incident(incident: dict[str, Any]):
    """持久化事件到JSON文件"""
    fp = _get_incidents_dir() / f"{incident['incident_id']}.json"
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(incident, f, ensure_ascii=False, indent=2, default=str)


def _get_default_llm():
    """获取默认LLM适配器（用于情感分析）"""
    try:
        from app.services.llm.base import LLMFactory
        from app.utils.config import load_settings, load_api_keys

        settings = load_settings()
        api_keys = load_api_keys()

        # 优先使用配置的情感分析专用模型
        reputation_cfg = settings.get("reputation", {})
        llm_model = reputation_cfg.get("sentiment_llm_model", "")

        if not llm_model:
            llm_model = settings.get("llm", {}).get("default_model", "deepseek")

        plat_cfg = settings.get("llm", {}).get("platforms", {}).get(llm_model, {})
        key_info = api_keys.get("platforms", {}).get(llm_model, {}) or api_keys.get(llm_model, {})
        api_key = key_info.get("api_key", "")
        if not api_key or "your-" in str(api_key).lower():
            return None

        return LLMFactory.create(
            platform=plat_cfg.get("adapter_type", "openai_compat") if "adapter_type" in plat_cfg
            else _get_adapter_type(llm_model),
            api_key=api_key,
            model_name=plat_cfg.get("model_name", ""),
            base_url=plat_cfg.get("base_url"),
        )
    except Exception as e:
        logger.warning(f"获取默认LLM失败: {e}")
        return None


def _get_adapter_type(platform: str) -> str:
    """根据平台名推断适配器类型"""
    adapter_map = {
        "wenxin": "wenxin",
        "claude": "claude",
        "ollama": "ollama",
        "lmstudio": "lmstudio",
    }
    return adapter_map.get(platform, "openai_compat")
