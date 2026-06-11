"""UTM参数生成器 — 创建/管理推广计划，为AI平台生成追踪链接

核心功能：
- 创建UTM推广计划（关联AI平台）
- 生成平台专属UTM追踪链接
- 从URL中解析UTM参数（供转化归因使用）
- 批量生成：一次为所有平台生成带UTM的链接

使用场景：
    GEO工坊优化完内容后 → 自动为内容中的链接添加UTM参数
    → 用户通过AI引用点击链接 → UTM参数被网站分析工具捕获
    → 转化归因引擎匹配UTM参数到AI平台
"""

from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

from app.utils.config import get_data_dir

logger = logging.getLogger(__name__)

# AI平台 → UTM source映射
_AI_PLATFORM_UTM_SOURCES = {
    "wenxin": "wenxin_yiyan",
    "tongyi": "tongyi_qianwen",
    "deepseek": "deepseek",
    "doubao": "doubao",
    "yuanbao": "yuanbao",
    "kimi": "kimi",
    "xinghuo": "xinghuo",
    "claude": "claude",
    "openai": "openai",
}


def _get_utm_dir() -> Path:
    d = get_data_dir() / "utm_campaigns"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_utm_source(platform_id: str) -> str:
    """获取AI平台对应的utm_source值"""
    return _AI_PLATFORM_UTM_SOURCES.get(platform_id, platform_id)


# ══════════════════════════════════════════════════════════════
# 推广计划 CRUD
# ══════════════════════════════════════════════════════════════

def create_campaign(data: dict[str, Any]) -> dict[str, Any]:
    """创建新的UTM推广计划

    Args:
        data: {name, utm_source, utm_medium, utm_campaign, utm_term, utm_content,
               landing_page_url, platform_ids[], active}

    Returns:
        完整campaign dict（含id和created_at）
    """
    campaign_id = f"utm_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc).isoformat()

    campaign = {
        "id": campaign_id,
        "name": data.get("name", ""),
        "utm_source": data.get("utm_source", ""),
        "utm_medium": data.get("utm_medium", "ai_referral"),
        "utm_campaign": data.get("utm_campaign", ""),
        "utm_term": data.get("utm_term", ""),
        "utm_content": data.get("utm_content", ""),
        "landing_page_url": data.get("landing_page_url", ""),
        "platform_ids": data.get("platform_ids", []),
        "active": data.get("active", True),
        "created_at": now,
        "updated_at": now,
    }

    _save_campaign(campaign)
    logger.info(f"UTM推广计划已创建: {campaign_id} ({campaign['name']})")
    return campaign


def get_campaign(campaign_id: str) -> dict[str, Any] | None:
    """获取单个推广计划"""
    fp = _get_utm_dir() / f"{campaign_id}.json"
    if not fp.exists():
        return None
    with open(fp, "r", encoding="utf-8") as f:
        return json.load(f)


def list_campaigns(active_only: bool = False) -> list[dict[str, Any]]:
    """列出所有推广计划"""
    campaigns = []
    for fp in sorted(_get_utm_dir().glob("utm_*.json"), reverse=True):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            if active_only and not data.get("active", True):
                continue
            campaigns.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return campaigns


def update_campaign(campaign_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """更新推广计划"""
    campaign = get_campaign(campaign_id)
    if campaign is None:
        return None

    updatable_fields = [
        "name", "utm_source", "utm_medium", "utm_campaign",
        "utm_term", "utm_content", "landing_page_url",
        "platform_ids", "active",
    ]
    for field in updatable_fields:
        if field in data:
            campaign[field] = data[field]

    campaign["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_campaign(campaign)
    return campaign


def delete_campaign(campaign_id: str) -> bool:
    """删除推广计划"""
    fp = _get_utm_dir() / f"{campaign_id}.json"
    if fp.exists():
        fp.unlink()
        logger.info(f"UTM推广计划已删除: {campaign_id}")
        return True
    return False


def _save_campaign(campaign: dict[str, Any]) -> None:
    """持久化推广计划（原子写入）"""
    import tempfile
    fp = _get_utm_dir() / f"{campaign['id']}.json"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False, dir=_get_utm_dir()
    ) as tmp:
        json.dump(campaign, tmp, ensure_ascii=False, indent=2)
    Path(tmp.name).replace(fp)


# ══════════════════════════════════════════════════════════════
# UTM链接生成
# ══════════════════════════════════════════════════════════════

def generate_utm_link(campaign_id: str, platform_id: str = "") -> dict[str, Any]:
    """为指定推广计划+平台生成UTM追踪链接

    Args:
        campaign_id: 推广计划ID
        platform_id: AI平台ID（如"doubao"），空则使用计划的utm_source

    Returns:
        {campaign_id, platform_id, full_url, utm_params, short_url}
    """
    campaign = get_campaign(campaign_id)
    if campaign is None:
        return {"campaign_id": campaign_id, "platform_id": platform_id,
                "full_url": "", "utm_params": {}, "short_url": "",
                "error": "推广计划不存在"}

    landing_url = campaign.get("landing_page_url", "")
    if not landing_url:
        return {"campaign_id": campaign_id, "platform_id": platform_id,
                "full_url": "", "utm_params": {}, "short_url": "",
                "error": "未设置落地页URL"}

    # 确定utm_source：平台专用 > 计划设定
    utm_source = (
        _get_utm_source(platform_id) if platform_id
        else campaign.get("utm_source", "")
    )

    utm_params = {
        "utm_source": utm_source,
        "utm_medium": campaign.get("utm_medium", "ai_referral"),
    }

    if campaign.get("utm_campaign"):
        utm_params["utm_campaign"] = campaign["utm_campaign"]
    if campaign.get("utm_term"):
        utm_params["utm_term"] = campaign["utm_term"]
    if campaign.get("utm_content"):
        utm_params["utm_content"] = campaign["utm_content"]

    # 从平台ID添加内容变体标记
    if platform_id and not campaign.get("utm_content"):
        utm_params["utm_content"] = f"geo_optimized_{platform_id}"

    # 构建完整URL
    parsed = urlparse(landing_url)
    existing_params = parse_qs(parsed.query, keep_blank_values=True)
    # 合并UTM参数（UTM参数优先覆盖）
    merged_params = {k: [v] for k, v in utm_params.items()}
    for k, v in existing_params.items():
        if k not in merged_params:
            merged_params[k] = v

    query_string = urlencode(merged_params, doseq=True)
    full_url = urlunparse((
        parsed.scheme, parsed.netloc, parsed.path,
        parsed.params, query_string, parsed.fragment,
    ))

    return {
        "campaign_id": campaign_id,
        "platform_id": platform_id,
        "full_url": full_url,
        "utm_params": utm_params,
        "short_url": "",  # 后续可集成短链接服务
    }


def batch_generate_utm(landing_page_url: str, utm_medium: str = "ai_referral",
                       utm_campaign: str = "", platform_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """批量生成UTM链接：为每个AI平台生成一条带UTM的链接

    Args:
        landing_page_url: 目标落地页
        utm_medium: 媒介类型
        utm_campaign: 推广活动名称
        platform_ids: 目标平台列表（空则生成全部10个AI平台的链接）

    Returns:
        [{platform_id, full_url, utm_params}, ...]
    """
    if platform_ids is None or len(platform_ids) == 0:
        platform_ids = list(_AI_PLATFORM_UTM_SOURCES.keys())

    # 创建临时推广计划
    temp_campaign = {
        "id": f"utm_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "name": f"批量生成-{utm_campaign or 'GEO优化'}",
        "utm_source": "",
        "utm_medium": utm_medium,
        "utm_campaign": utm_campaign,
        "utm_term": "",
        "utm_content": "",
        "landing_page_url": landing_page_url,
        "platform_ids": platform_ids,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_campaign(temp_campaign)

    links = []
    for pid in platform_ids:
        link = generate_utm_link(temp_campaign["id"], platform_id=pid)
        links.append(link)

    logger.info(f"批量生成UTM链接: {len(links)}个平台 (campaign={temp_campaign['id']})")
    return links


# ══════════════════════════════════════════════════════════════
# UTM解析（供转化归因使用）
# ══════════════════════════════════════════════════════════════

def parse_utm_from_url(url: str) -> dict[str, str]:
    """从URL中提取UTM参数

    Args:
        url: 完整URL或referrer

    Returns:
        {utm_source, utm_medium, utm_campaign, utm_term, utm_content}
    """
    if not url:
        return {}

    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query, keep_blank_values=True)
    except Exception:
        # 尝试直接作为query string解析
        params = parse_qs(url, keep_blank_values=True)

    utm_fields = {}
    for key in ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]:
        values = params.get(key, [])
        utm_fields[key] = values[0] if values else ""

    return utm_fields


def match_utm_to_ai_platform(utm_source: str) -> str:
    """根据utm_source反查AI平台ID

    Args:
        utm_source: UTM source参数值

    Returns:
        匹配的AI平台ID，无匹配则返回空字符串
    """
    if not utm_source:
        return ""
    utm_lower = utm_source.lower()
    for platform_id, source_val in _AI_PLATFORM_UTM_SOURCES.items():
        if utm_lower == source_val or utm_lower == platform_id:
            return platform_id
    return ""


def is_ai_referral(utm_medium: str) -> bool:
    """判断UTM medium是否为AI引用"""
    if not utm_medium:
        return False
    return utm_medium.lower() in ("ai_referral", "geo_referral", "ai_citation")
