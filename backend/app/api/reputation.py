"""品牌舆情管理 API — 舆情事件管理、情感分析、纠正内容生成"""

from __future__ import annotations
import logging

from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import (
    ReputationStatsResponse, SentimentClassifyRequest,
    IncidentStatusUpdateRequest, ReputationScanRequest,
)
from app.core.reputation_incident import (
    list_incidents, get_incident, get_incident_timeline,
    create_incident, update_incident_status,
    get_reputation_stats, get_sentiment_trend,
    auto_scan_and_create, set_correction_content, mark_correction_published,
)
from app.core.sentiment_classifier import SentimentClassifier
from app.core.correction_generator import CorrectionGenerator, verify_correction_effect

logger = logging.getLogger(__name__)

router = APIRouter()


# ══════════════════════════════════════════════════════════════
# 事件管理
# ══════════════════════════════════════════════════════════════

@router.get("/incidents")
async def get_incidents(
    platform: str = Query(default="", description="按平台筛选"),
    severity: str = Query(default="", description="按严重度筛选"),
    status: str = Query(default="", description="按状态筛选"),
    date_from: str = Query(default="", description="起始日期"),
    date_to: str = Query(default="", description="结束日期"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """获取舆情事件列表（支持多条件筛选）"""
    incidents = list_incidents(
        platform=platform,
        severity=severity,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    total = len(list_incidents(
        platform=platform, severity=severity, status=status,
        date_from=date_from, date_to=date_to, limit=500, offset=0,
    ))
    return {"items": incidents, "total": total, "limit": limit, "offset": offset}


@router.get("/incidents/{incident_id}")
async def get_incident_detail(incident_id: str):
    """获取事件详情+时间线"""
    incident = get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"事件不存在: {incident_id}")
    timeline = get_incident_timeline(incident_id)
    return {"incident": incident, "timeline": timeline}


@router.post("/incidents")
async def create_incident_manual(
    platform: str = Query(..., description="AI平台"),
    query: str = Query(..., description="触发查询"),
    ai_response: str = Query(default="", description="AI回复摘录"),
    severity: str = Query(default="low", description="严重度"),
    notes: str = Query(default="", description="备注"),
):
    """手动创建舆情事件"""
    try:
        incident = create_incident(
            platform=platform,
            query=query,
            ai_response=ai_response,
            severity=severity,
        )
        if notes:
            update_incident_status(incident["incident_id"], incident["status"], notes)
        return incident
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建事件失败: {str(e)}")


@router.put("/incidents/{incident_id}/status")
async def update_incident(incident_id: str, req: IncidentStatusUpdateRequest):
    """更新事件状态"""
    try:
        incident = update_incident_status(incident_id, req.status, req.notes)
        return incident
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新事件失败: {str(e)}")


# ══════════════════════════════════════════════════════════════
# 情感分析 & 扫描
# ══════════════════════════════════════════════════════════════

@router.post("/classify")
async def classify_sentiment(req: SentimentClassifyRequest):
    """对指定AI回复进行情感+事实分类"""
    if not req.brand_name:
        from app.utils.config import get_enterprise_name
        req.brand_name = get_enterprise_name()

    classifier = SentimentClassifier()

    # 获取LLM适配器（用于深度分析）
    llm = _get_default_llm()

    try:
        result = await classifier.classify(
            response=req.response,
            query=req.query,
            platform=req.platform,
            llm_adapter=llm,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"情感分类失败: {str(e)}")


@router.post("/scan")
async def run_scan(req: ReputationScanRequest):
    """手动触发舆情扫描（基于最新品牌监测数据）"""
    try:
        report = await auto_scan_and_create(
            sandtable_type=req.sandtable_type,
            platforms=req.platforms if req.platforms else None,
            auto_create=req.auto_create_incidents,
        )
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"舆情扫描失败: {str(e)}")


# ══════════════════════════════════════════════════════════════
# 纠正内容
# ══════════════════════════════════════════════════════════════

@router.post("/correct")
async def generate_correction(
    incident_id: str = Query(..., description="事件ID"),
    target_platform: str = Query(default="", description="目标AI平台"),
    sandtable_type: str = Query(default="general", description="沙盘类型"),
):
    """为事件生成纠正内容"""
    incident = get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"事件不存在: {incident_id}")

    llm = _get_default_llm()
    generator = CorrectionGenerator()

    try:
        correction = await generator.generate(
            incident=incident,
            target_platform=target_platform or incident.get("platform", ""),
            sandtable_type=sandtable_type,
            llm_adapter=llm,
        )

        # 将纠正内容关联到事件
        set_correction_content(incident_id, correction.get("correction_text", ""))

        return correction
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"纠正内容生成失败: {str(e)}")


@router.post("/correct/{incident_id}/publish")
async def publish_correction(incident_id: str):
    """发布纠正内容"""
    incident = get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"事件不存在: {incident_id}")

    if not incident.get("correction_content"):
        raise HTTPException(status_code=400, detail="尚未生成纠正内容，请先调用 /correct")

    try:
        updated = mark_correction_published(incident_id)
        return {
            "incident_id": incident_id,
            "published": True,
            "correction_content": updated.get("correction_content", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发布失败: {str(e)}")


@router.get("/correct/{incident_id}/verify")
async def verify_correction(incident_id: str):
    """验证纠正效果（重新检测AI平台上的品牌收录情况）"""
    llm = _get_default_llm()
    try:
        result = await verify_correction_effect(incident_id, llm)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"验证失败: {str(e)}")


# ══════════════════════════════════════════════════════════════
# 统计 & 趋势
# ══════════════════════════════════════════════════════════════

@router.get("/stats")
async def get_stats():
    """舆情统计概览"""
    return get_reputation_stats()


@router.get("/sentiment-trend")
async def get_trend(days: int = Query(default=30, ge=7, le=365)):
    """情感趋势数据（按天聚合）"""
    return {"days": days, "data_points": get_sentiment_trend(days)}


# ══════════════════════════════════════════════════════════════
# 辅助
# ══════════════════════════════════════════════════════════════

def _get_default_llm():
    """获取默认LLM适配器"""
    try:
        from app.services.llm.base import LLMFactory
        from app.utils.config import load_settings, load_api_keys

        settings = load_settings()
        api_keys = load_api_keys()

        llm_model = settings.get("reputation", {}).get("sentiment_llm_model", "")
        if not llm_model:
            llm_model = settings.get("llm", {}).get("default_model", "deepseek")

        plat_cfg = settings.get("llm", {}).get("platforms", {}).get(llm_model, {})
        if not plat_cfg:
            # 遍历寻找第一个配置了API Key的平台
            for pk, cfg in settings.get("llm", {}).get("platforms", {}).items():
                key_info = api_keys.get("platforms", {}).get(pk, {})
                if key_info.get("api_key") and "your-" not in str(key_info.get("api_key", "")):
                    plat_cfg = cfg
                    break

        if not plat_cfg:
            return None

        adapter = plat_cfg.get("adapter_type", "openai_compat") if "adapter_type" in plat_cfg else "openai_compat"
        key_info = api_keys.get("platforms", {}).get(llm_model, {}) or api_keys.get(llm_model, {})
        api_key = key_info.get("api_key", "")
        if not api_key or "your-" in str(api_key).lower():
            return None

        return LLMFactory.create(
            platform=adapter,
            api_key=api_key,
            model_name=plat_cfg.get("model_name", ""),
            base_url=plat_cfg.get("base_url"),
        )
    except Exception as e:
        logger.warning(f"获取默认LLM失败: {e}")
        return None
