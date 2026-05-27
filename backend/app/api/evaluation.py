"""AI评测API路由"""

from fastapi import APIRouter, HTTPException
import logging
from app.models.schemas import EvaluateRequest, EvaluateResponse
from app.models.enums import AIPlatform
from app.core.evaluator import AIEvaluator, ROLE_QUESTIONS
from app.services.llm.base import LLMFactory
from app.utils.config import load_settings, load_api_keys

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_evaluator(with_llm: bool = True):
    """获取评测器实例"""
    settings = load_settings()
    api_keys = load_api_keys()

    llm = None
    if with_llm:
        default_platform = settings.get("llm", {}).get("default_model", "deepseek")
        plat_cfg = settings.get("llm", {}).get("platforms", {}).get(default_platform, {})
        key_info = api_keys.get("platforms", {}).get(default_platform, {})

        api_key = key_info.get("api_key", "")
        if api_key and "your-" not in api_key:
            adapter_type = AIPlatform(default_platform).adapter_type
            llm = LLMFactory.create(
                platform=adapter_type,
                api_key=api_key,
                model_name=plat_cfg.get("model_name", ""),
                base_url=plat_cfg.get("base_url"),
            )
            if adapter_type == "wenxin":
                llm.secret_key = key_info.get("secret_key", "")

    return AIEvaluator(llm_adapter=llm)


@router.post("/semantic", response_model=EvaluateResponse)
async def evaluate_semantic(req: EvaluateRequest):
    """语义评测 + LLM模拟评测"""
    try:
        evaluator = _get_evaluator(with_llm=True)

        result = await evaluator.evaluate(
            optimized_text=req.optimized_text,
            sandtable_type=req.sandtable_type,
            original_text=req.original_text,
            platforms=req.platforms or [AIPlatform.DEEPSEEK],
            user_roles=req.user_roles,
            custom_questions=req.custom_questions,
        )

        return EvaluateResponse(
            overall_score=result["overall_score"],
            platform_results=result["platform_results"],
            before_after_comparison=result.get("before_after_comparison"),
            weak_points=result.get("weak_points", []),
            suggestions=result.get("suggestions", []),
        )
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("评测过程中发生未预料的错误")
        raise HTTPException(status_code=500, detail="评测服务暂时不可用，请稍后重试")


@router.get("/questions")
async def get_preset_questions():
    """获取预置评测问题集"""
    return {
        role.value: {
            "label": role.label,
            "questions": [q.format(type="[沙盘类型]") for q in qs],
        }
        for role, qs in ROLE_QUESTIONS.items()
    }


@router.post("/quick-brand-check")
async def quick_brand_check(req: dict):
    """快速品牌曝光检测（无需LLM，纯向量计算）"""
    try:
        from app.services.embedding_svc import EmbeddingService

        text = req.get("text", "")
        brand_keywords = req.get("brand_keywords", [
            "武汉微艺达",
            "微艺达智能科技",
            "武汉沙盘定制",
            "沙盘模型厂家",
        ])

        emb_svc = EmbeddingService()
        text_vec = emb_svc.encode_single(text)
        kw_vecs = emb_svc.encode(brand_keywords)

        scores = {}
        for kw, kw_vec in zip(brand_keywords, kw_vecs):
            scores[kw] = round(float(emb_svc.similarity(text_vec, kw_vec)) * 100, 1)

        return {
            "brand_keyword_scores": scores,
            "average_score": round(sum(scores.values()) / len(scores), 1),
        }
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="品牌检测服务暂时不可用，请稍后重试")
