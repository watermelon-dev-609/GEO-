"""GEO文案重构API路由 — 批量重构 + SSE流式"""

import json
import time
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.models.schemas import (
    RewriteRequest, RewriteResponse, APIResponse,
    OptimizationRuleItem, PlatformOptimizationRules,
    OptimizationRulesResponse, OptimizationRulesUpdateRequest,
    PublishAdaptRequest,
)
from app.models.enums import SandtableType, AIPlatform
from app.core.rewriter import GEORewriter
from app.utils.config import load_settings, save_settings

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


# ── 字数硬截断（API层兜底，不依赖rewriter模块更新）──

_PLATFORM_MAX_CHARS = {
    AIPlatform.DEEPSEEK: 2300,
    AIPlatform.KIMI: 2300,
    AIPlatform.CLAUDE: 2600,
    AIPlatform.DOUBAO: 1300,
    AIPlatform.WENXIN: 1600,
    AIPlatform.TONGYI: 1600,
    AIPlatform.XINGHUO: 1600,
    AIPlatform.YUANBAO: 1600,
}


def _get_api_max_chars(platform: AIPlatform) -> int:
    return _PLATFORM_MAX_CHARS.get(platform, 2000)


def _truncate_at_boundary(text: str, max_chars: int) -> str:
    """在段落/句子边界截断文本"""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    # 优先段落边界
    last_para = truncated.rfind('\n\n')
    if last_para > max_chars * 0.7:
        return truncated[:last_para].rstrip()
    # 其次句子边界
    for punct in ['。', '！', '？']:
        last = truncated.rfind(punct)
        if last > max_chars * 0.6:
            return truncated[:last + 1]
    return truncated.rstrip()


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
            optimization_rules=req.optimization_rules,
            enterprise_name=req.enterprise_name,
            enterprise_location=req.enterprise_location,
            query_intent=req.query_intent,
            diversity_seed=req.diversity_seed,
        )

        # API层字数硬截断兜底（LLM经常忽略prompt中的字数约束）
        for r in results:
            if r.optimized_text and not r.error:
                limit = _get_api_max_chars(r.platform)
                if len(r.optimized_text) > limit:
                    r.optimized_text = _truncate_at_boundary(r.optimized_text, limit)
                    r.word_count = len(r.optimized_text)

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
                    optimization_rules=req.optimization_rules,
                    enterprise_name=req.enterprise_name,
                    enterprise_location=req.enterprise_location,
                    query_intent=req.query_intent,
                    diversity_seed=req.diversity_seed,
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


# ── 优化规则配置（按平台独立设置）──

@router.get("/optimization-rules", response_model=OptimizationRulesResponse)
async def get_optimization_rules():
    """获取所有平台的优化规则配置"""
    settings = load_settings()
    opt_cfg = settings.get("optimization", {}).get("platforms", {})
    platforms = []
    for plat_key, plat_cfg in opt_cfg.items():
        rules = []
        plat_rules = plat_cfg.get("rules", {}) if isinstance(plat_cfg, dict) else {}
        for rule_key, rule_cfg in plat_rules.items():
            if isinstance(rule_cfg, dict):
                rules.append(OptimizationRuleItem(
                    key=rule_key,
                    label=rule_cfg.get("label", rule_key),
                    description=rule_cfg.get("description", ""),
                    enabled=rule_cfg.get("enabled", True),
                ))
        if rules:
            platforms.append(PlatformOptimizationRules(platform=plat_key, rules=rules))
    return OptimizationRulesResponse(platforms=platforms)


# ── 发布平台适配 ──

@router.get("/publish-platforms")
async def list_publish_platforms():
    """列出所有可用的发布适配平台（公众号/小红书/官网/头条/搜狐/知乎/百家号）"""
    from app.core.publish_adapter import PublishAdapter
    return PublishAdapter.list_platforms()


@router.post("/publish-adapt", response_model=dict)
async def adapt_for_publish(req: "PublishAdaptRequest"):
    """将GEO优化文案适配为各发布平台即用格式

    支持平台: wechat_mp(公众号), xiaohongshu(小红书), official_site(官网),
             toutiao(头条), sohu(搜狐号), zhihu(知乎), baijiahao(百家号)
    """
    from app.core.publish_adapter import PublishAdapter, PUBLISH_PLATFORMS

    invalid = [p for p in req.target_platforms if p not in PUBLISH_PLATFORMS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"不支持的发布平台: {', '.join(invalid)}")

    try:
        adapter = PublishAdapter()
        results = await adapter.adapt(
            optimized_text=req.optimized_text,
            target_platforms=req.target_platforms,
            enterprise_name=req.enterprise_name or "",
            original_text=req.original_text,
        )

        items = []
        for plat_key, data in results.items():
            items.append({
                "platform": plat_key,
                "platform_name": data["platform_name"],
                "icon": data["icon"],
                "text": data["text"],
                "word_count": data["word_count"],
            })

        return {"results": items}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发布适配失败: {str(e)}")


@router.put("/optimization-rules", response_model=PlatformOptimizationRules)
async def update_optimization_rules(req: OptimizationRulesUpdateRequest):
    """更新指定平台的优化规则配置并持久化"""
    try:
        settings = load_settings()
        if "optimization" not in settings:
            settings["optimization"] = {}
        if "platforms" not in settings["optimization"]:
            settings["optimization"]["platforms"] = {}
        # 构建该平台的新规则
        new_rules = {}
        for item in req.rules:
            new_rules[item.key] = {
                "enabled": item.enabled,
                "label": item.label,
                "description": item.description,
            }
        settings["optimization"]["platforms"][req.platform] = {"rules": new_rules}
        save_settings(settings)
        return PlatformOptimizationRules(platform=req.platform, rules=req.rules)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存优化规则失败: {str(e)}")
