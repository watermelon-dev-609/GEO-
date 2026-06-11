"""文本清洗API路由"""

import asyncio
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    CleaningRequest, CleaningResponse,
    InfoExtractionResponse, APIResponse,
    CleaningRuleItem, CleaningRulesResponse, CleaningRulesUpdateRequest,
)
from app.services.llm.base import LLMFactory, LLMMessage
from app.core.cleaner import TextCleaner
from app.utils.config import load_settings, load_api_keys, save_settings, invalidate_config_cache
from app.models.enums import AIPlatform, SandtableType

router = APIRouter()
_cleaner_instance: TextCleaner | None = None
_cleaner_adapter_key: str | None = None


def _get_cleaner() -> TextCleaner:
    """获取清洗器实例 — 优先用 default_model，不可用则自动选择第一个已配置的平台。
    实例被缓存，仅当配置变更时重建。"""
    global _cleaner_instance, _cleaner_adapter_key

    settings = load_settings()
    api_keys = load_api_keys()

    platforms_cfg = settings.get("llm", {}).get("platforms", {})
    available = []
    for plat_key, plat_cfg in platforms_cfg.items():
        key_info = api_keys.get("platforms", {}).get(plat_key, {})
        api_key = key_info.get("api_key", "")
        if api_key and "your-" not in api_key:
            available.append((plat_key, plat_cfg, key_info))

    if not available:
        raise HTTPException(
            status_code=400,
            detail="暂未配置任何AI平台的API Key，请在侧边栏「配置API Key」中配置"
        )

    default_platform = settings.get("llm", {}).get("default_model", "")
    selected = None
    for plat_key, plat_cfg, key_info in available:
        if plat_key == default_platform:
            selected = (plat_key, plat_cfg, key_info)
            break
    if selected is None:
        selected = available[0]

    plat_key, plat_cfg, key_info = selected
    cache_key = f"{plat_key}:{key_info.get('api_key', '')[:8]}"

    if _cleaner_instance is not None and _cleaner_adapter_key == cache_key:
        return _cleaner_instance

    adapter_type = AIPlatform(plat_key).adapter_type
    if _cleaner_instance is not None and hasattr(_cleaner_instance.llm, 'close'):
        try:
            asyncio.ensure_future(_cleaner_instance.llm.close())
        except Exception:
            pass

    adapter = LLMFactory.create(
        platform=adapter_type,
        api_key=key_info.get("api_key", ""),
        model_name=plat_cfg.get("model_name", ""),
        base_url=plat_cfg.get("base_url"),
    )
    if adapter_type == "wenxin":
        adapter.secret_key = key_info.get("secret_key", "")

    _cleaner_instance = TextCleaner(adapter)
    _cleaner_adapter_key = cache_key
    return _cleaner_instance


@router.post("/clean", response_model=CleaningResponse)
async def clean_text(req: CleaningRequest):
    """文本标准化清洗"""
    try:
        cleaner = _get_cleaner()
        result = await cleaner.clean(
            content=req.content,
            sandtable_type=req.sandtable_type,
            rules_config=req.rules_config,
        )

        dimensions = None
        detected_type = req.sandtable_type

        if req.extract_dimensions or not detected_type:
            tasks = []
            if req.extract_dimensions:
                tasks.append(cleaner.extract_dimensions(result["cleaned_text"]))
            else:
                tasks.append(asyncio.sleep(0))
            if not detected_type:
                tasks.append(cleaner.detect_type(req.content))
            else:
                tasks.append(asyncio.sleep(0))

            gathered = await asyncio.gather(*tasks, return_exceptions=True)
            idx = 0
            if req.extract_dimensions:
                dim_result = gathered[idx]
                if isinstance(dim_result, Exception):
                    raise dim_result
                dimensions = dim_result
                idx += 1
            else:
                idx += 1
            if not detected_type:
                type_result = gathered[idx]
                if not isinstance(type_result, Exception):
                    detected_type = type_result

        return CleaningResponse(
            original_text=result["original_text"],
            cleaned_text=result["cleaned_text"],
            dimensions=dimensions,
            detected_type=detected_type,
            word_count_before=result["word_count_before"],
            word_count_after=result["word_count_after"],
            processing_time_ms=result["processing_time_ms"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文本清洗失败: {str(e)}")


@router.post("/extract", response_model=InfoExtractionResponse)
async def extract_info(req: CleaningRequest):
    """单独提取五维关键信息"""
    try:
        cleaner = _get_cleaner()
        dims, detected = await asyncio.gather(
            cleaner.extract_dimensions(req.content),
            cleaner.detect_type(req.content),
            return_exceptions=True,
        )
        if isinstance(dims, Exception):
            raise dims
        if isinstance(detected, Exception) or detected is None:
            detected = SandtableType("smart_traffic")

        from app.core.dimensions_shared import ALL_DIMENSION_KEYS
        return InfoExtractionResponse(
            sandtable_type=detected,
            **{key: dims.get(key, []) for key in ALL_DIMENSION_KEYS},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"信息提取失败: {str(e)}")


@router.get("/rules", response_model=CleaningRulesResponse)
async def get_cleaning_rules():
    """获取当前清洗规则配置"""
    settings = load_settings()
    cleaning_cfg = settings.get("cleaning", {}).get("rules", {})
    rules = []
    for key, cfg in cleaning_cfg.items():
        if isinstance(cfg, dict):
            rules.append(CleaningRuleItem(
                key=key,
                label=cfg.get("label", key),
                description=cfg.get("description", ""),
                enabled=cfg.get("enabled", True),
            ))
    # 如果配置中没有规则（首次使用），返回默认规则
    if not rules:
        from app.prompts.cleaning import _RULE_DETAILS, _DEFAULT_RULE_ORDER
        rules = [
            CleaningRuleItem(
                key=k,
                label=k,
                description=_RULE_DETAILS.get(k, ""),
                enabled=True,
            )
            for k in _DEFAULT_RULE_ORDER
        ]
    return CleaningRulesResponse(rules=rules)


@router.put("/rules", response_model=CleaningRulesResponse)
async def update_cleaning_rules(req: CleaningRulesUpdateRequest):
    """更新清洗规则配置并持久化到 settings.yaml"""
    try:
        settings = load_settings()
        # 构建新的 cleaning.rules 配置
        new_rules = {}
        for item in req.rules:
            new_rules[item.key] = {
                "enabled": item.enabled,
                "label": item.label,
                "description": item.description,
            }
        # 更新 settings 中的 cleaning 段
        if "cleaning" not in settings:
            settings["cleaning"] = {}
        settings["cleaning"]["rules"] = new_rules
        # 原子写入
        save_settings(settings)
        return CleaningRulesResponse(rules=req.rules)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存清洗规则配置失败: {str(e)}")
