"""文本清洗API路由"""

from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    CleaningRequest, CleaningResponse,
    InfoExtractionResponse, APIResponse,
)
from app.services.llm.base import LLMFactory, LLMMessage
from app.core.cleaner import TextCleaner
from app.utils.config import load_settings, load_api_keys
from app.models.enums import AIPlatform, SandtableType

router = APIRouter()


def _get_cleaner() -> TextCleaner:
    """获取清洗器实例 — 优先用 default_model，不可用则自动选择第一个已配置的平台"""
    settings = load_settings()
    api_keys = load_api_keys()

    # 收集所有已配置 Key 的平台
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

    # 优先用 default_model，否则用第一个可用的
    default_platform = settings.get("llm", {}).get("default_model", "")
    selected = None
    for plat_key, plat_cfg, key_info in available:
        if plat_key == default_platform:
            selected = (plat_key, plat_cfg, key_info)
            break
    if selected is None:
        selected = available[0]

    plat_key, plat_cfg, key_info = selected
    adapter_type = AIPlatform(plat_key).adapter_type
    adapter = LLMFactory.create(
        platform=adapter_type,
        api_key=key_info.get("api_key", ""),
        model_name=plat_cfg.get("model_name", ""),
        base_url=plat_cfg.get("base_url"),
    )
    if adapter_type == "wenxin":
        adapter.secret_key = key_info.get("secret_key", "")

    return TextCleaner(adapter)


@router.post("/clean", response_model=CleaningResponse)
async def clean_text(req: CleaningRequest):
    """文本标准化清洗"""
    try:
        cleaner = _get_cleaner()
        result = await cleaner.clean(
            content=req.content,
            sandtable_type=req.sandtable_type,
        )

        dimensions = None
        detected_type = req.sandtable_type

        if req.extract_dimensions:
            dims = await cleaner.extract_dimensions(result["cleaned_text"])
            dimensions = dims

        if not detected_type:
            detected_type = await cleaner.detect_type(req.content)

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
        dims = await cleaner.extract_dimensions(req.content)
        detected = req.sandtable_type or await cleaner.detect_type(req.content) or SandtableType.smart_traffic

        return InfoExtractionResponse(
            sandtable_type=detected,
            core_advantages=dims.get("core_advantages", []),
            applicable_scenarios=dims.get("applicable_scenarios", []),
            technical_features=dims.get("technical_features", []),
            service_capabilities=dims.get("service_capabilities", []),
            implementation_value=dims.get("implementation_value", []),
            key_phrases=dims.get("key_phrases", []),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"信息提取失败: {str(e)}")
