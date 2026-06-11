"""UTM追踪 API — 推广计划管理、链接生成、批量生成"""

import logging
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    UTMCampaignCreate, UTMCampaign, UTMGeneratedLink, UTMBatchGenerateRequest,
)
from app.core.utm_generator import (
    create_campaign, get_campaign, list_campaigns,
    update_campaign, delete_campaign,
    generate_utm_link, batch_generate_utm,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 推广计划 CRUD ──

@router.post("/campaigns")
async def create_utm_campaign(data: UTMCampaignCreate):
    """创建新的UTM推广计划"""
    campaign = create_campaign(data.model_dump())
    return {"status": "ok", "campaign": campaign}


@router.get("/campaigns")
async def list_utm_campaigns(active_only: bool = False):
    """列出所有UTM推广计划"""
    campaigns = list_campaigns(active_only=active_only)
    return {"status": "ok", "campaigns": campaigns, "total": len(campaigns)}


@router.get("/campaigns/{campaign_id}")
async def get_utm_campaign(campaign_id: str):
    """获取单个推广计划详情"""
    campaign = get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail=f"推广计划不存在: {campaign_id}")
    return {"status": "ok", "campaign": campaign}


@router.put("/campaigns/{campaign_id}")
async def update_utm_campaign(campaign_id: str, data: UTMCampaignCreate):
    """更新推广计划"""
    updated = update_campaign(campaign_id, data.model_dump())
    if updated is None:
        raise HTTPException(status_code=404, detail=f"推广计划不存在: {campaign_id}")
    return {"status": "ok", "campaign": updated}


@router.delete("/campaigns/{campaign_id}")
async def delete_utm_campaign(campaign_id: str):
    """删除推广计划"""
    if not delete_campaign(campaign_id):
        raise HTTPException(status_code=404, detail=f"推广计划不存在: {campaign_id}")
    return {"status": "ok", "message": f"推广计划 {campaign_id} 已删除"}


# ── 链接生成 ──

@router.post("/campaigns/{campaign_id}/generate")
async def generate_link(campaign_id: str, platform_id: str = ""):
    """为指定推广计划生成UTM追踪链接

    Args:
        campaign_id: 推广计划ID
        platform_id: 目标AI平台ID（空则使用计划的默认utm_source）
    """
    campaign = get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail=f"推广计划不存在: {campaign_id}")

    # 如果指定了平台，生成该平台专属链接
    if platform_id:
        link = generate_utm_link(campaign_id, platform_id=platform_id)
        if link.get("error"):
            raise HTTPException(status_code=400, detail=link["error"])
        return {"status": "ok", "link": link}

    # 否则为所有关联平台生成链接
    platform_ids = campaign.get("platform_ids", [])
    links = []
    if platform_ids:
        for pid in platform_ids:
            link = generate_utm_link(campaign_id, platform_id=pid)
            if not link.get("error"):
                links.append(link)
    else:
        # 无关联平台则生成默认链接
        link = generate_utm_link(campaign_id)
        if link.get("error"):
            raise HTTPException(status_code=400, detail=link["error"])
        links.append(link)

    return {"status": "ok", "links": links, "total": len(links)}


@router.post("/batch-generate")
async def batch_generate(data: UTMBatchGenerateRequest):
    """批量生成UTM链接：一次为所有AI平台生成追踪链接

    典型用法：输入落地页URL，自动为wenxin/doubao/deepseek等平台各生成一条UTM链接。
    """
    if not data.landing_page_url:
        raise HTTPException(status_code=400, detail="landing_page_url 不能为空")

    platform_ids = data.platform_ids if data.platform_ids else []
    links = batch_generate_utm(
        landing_page_url=data.landing_page_url,
        utm_medium=data.utm_medium,
        utm_campaign=data.utm_campaign,
        platform_ids=platform_ids,
    )

    return {
        "status": "ok",
        "links": links,
        "total": len(links),
        "landing_page_url": data.landing_page_url,
    }
