"""GEO文案重构API路由 — 批量重构 + SSE流式"""

import json
import time
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.models.schemas import RewriteRequest, RewriteResponse, APIResponse
from app.models.enums import SandtableType, AIPlatform
from app.core.rewriter import GEORewriter

router = APIRouter()


def _load_competitor_summary(sandtable_type: str) -> str | None:
    """加载指定沙盘类型的竞品对比摘要"""
    import json
    from pathlib import Path
    comp_dir = Path("data/competitors")
    if not comp_dir.exists():
        return None
    comp_files = sorted(comp_dir.glob("*.json"))
    if not comp_files:
        return None
    try:
        with open(comp_files[-1], "r", encoding="utf-8") as f:
            latest = json.load(f)
        name = latest.get("name", "未知竞品")
        features = latest.get("content_features", {})
        if not features:
            return None
        summary = f"竞品「{name}」内容特征：\n"
        for key, val in features.items():
            summary += f"- {key}: {val}\n"
        summary += "\n请在生成文案时体现与以上竞品的差异化优势。"
        return summary
    except Exception:
        return None


@router.post("/rewrite", response_model=RewriteResponse)
async def rewrite_text(req: RewriteRequest):
    """批量GEO文案重构（多平台并行）"""
    try:
        start = time.perf_counter()
        rewriter = GEORewriter()

        competitor_insights = req.competitor_insights
        if req.inject_competitors and not competitor_insights:
            competitor_insights = _load_competitor_summary(req.sandtable_type.value)

        results = await rewriter.rewrite(
            cleaned_text=req.cleaned_text,
            sandtable_type=req.sandtable_type,
            platforms=req.platforms,
            dimensions=req.dimensions,
            optimization_hints=req.optimization_hints or None,
            competitor_insights=competitor_insights,
            enterprise_name=req.enterprise_name,
            enterprise_location=req.enterprise_location,
        )
        elapsed = (time.perf_counter() - start) * 1000
        return RewriteResponse(
            sandtable_type=req.sandtable_type,
            results=results,
            total_time_ms=round(elapsed, 1),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文案重构失败: {str(e)}")


@router.post("/rewrite/stream")
async def rewrite_stream(req: RewriteRequest):
    """流式GEO文案重构（SSE，单平台）"""
    try:
        rewriter = GEORewriter()

        # 只取第一个平台做流式（前端可切换）
        platform = req.platforms[0] if req.platforms else AIPlatform.DEEPSEEK

        competitor_insights = req.competitor_insights
        if req.inject_competitors and not competitor_insights:
            competitor_insights = _load_competitor_summary(req.sandtable_type.value)

        async def event_stream():
            try:
                async for chunk in rewriter.stream_rewrite(
                    cleaned_text=req.cleaned_text,
                    sandtable_type=req.sandtable_type,
                    platform=platform,
                    dimensions=req.dimensions,
                    optimization_hints=req.optimization_hints or None,
                    competitor_insights=competitor_insights,
                    enterprise_name=req.enterprise_name,
                    enterprise_location=req.enterprise_location,
                ):
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            except ValueError as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"流式生成失败: {str(e)}")


@router.get("/profiles/{sandtable_type}")
async def get_sandtable_profile(sandtable_type: SandtableType):
    """获取沙盘类型行业基调"""
    from app.prompts.rewrite import get_sandtable_profile
    return get_sandtable_profile(sandtable_type.value)


@router.get("/platform-rules/{platform}")
async def get_platform_rules(platform: str):
    """获取AI平台优化规则"""
    from app.prompts.rewrite import get_platform_rules
    rules = get_platform_rules(platform)
    if not rules:
        raise HTTPException(status_code=404, detail=f"未找到平台规则: {platform}")
    return rules
