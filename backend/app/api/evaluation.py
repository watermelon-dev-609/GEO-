"""AI评测API路由"""

import asyncio
import json
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.models.schemas import EvalStartRequest
from app.models.enums import AIPlatform, EvalPhase
from app.core.evaluator import AIEvaluator
from app.core.eval_session import EvalSession
from app.core.eval_dimensions import DimensionRegistry
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


@router.post("/start")
async def start_evaluation(req: EvalStartRequest):
    """启动评测 — SSE 流式返回阶段事件"""
    evaluator = _get_evaluator(with_llm=True)

    session = EvalSession(sandtable_type=req.sandtable_type, mode=req.mode)
    session.evaluated_text = req.optimized_text
    session.original_text = req.original_text or ""
    session.platforms = req.platforms

    if not req.dimensions:
        all_dims = DimensionRegistry.list_all()
        has_llm = evaluator.llm is not None
        req.dimensions = [
            d.to_config(enabled=(not d.requires_llm or has_llm))
            for d in all_dims
        ]

    from app.models.enums import SandtableType, UserRole
    st = SandtableType(req.sandtable_type) if isinstance(req.sandtable_type, str) else req.sandtable_type
    roles = [UserRole(r) for r in req.user_roles] if req.user_roles else None

    async def event_generator():
        try:
            async for event_str in evaluator.evaluate_stream(
                session=session,
                optimized_text=req.optimized_text,
                sandtable_type=st,
                dimension_configs=req.dimensions,
                original_text=req.original_text,
                user_roles=roles,
                custom_questions=req.custom_questions,
            ):
                yield event_str
                await asyncio.sleep(0.01)
        except Exception as e:
            logger.exception(f"SSE stream error for session {session.session_id}")
            error_event = f"event: eval_error\ndata: {json.dumps({'session_id': session.session_id, 'error': str(e)}, ensure_ascii=False)}\n\n"
            yield error_event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Session-Id": session.session_id,
        },
    )


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """查询会话状态（断线恢复）"""
    session = EvalSession.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    return session.to_dict()


@router.post("/cancel/{session_id}")
async def cancel_evaluation(session_id: str):
    """取消评测"""
    session = EvalSession.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    session.cancel()
    session.mark_cancelled()
    return {"status": "cancelled", "session_id": session_id}


@router.get("/dimensions")
async def get_dimensions():
    """获取可选维度列表"""
    all_dims = DimensionRegistry.list_all()
    return {
        "dimensions": [d.to_config() for d in all_dims],
        "default_weight": 20.0,
    }


@router.get("/history")
async def get_history():
    """评测历史列表（合并磁盘+内存）"""
    from app.core.eval_history_store import load_all_sessions

    # 从磁盘加载
    disk_sessions = load_all_sessions()

    # 合并内存中的session（可能有未落盘的新会话）
    seen_ids = {s.get("session_id") for s in disk_sessions}
    memory_sessions = EvalSession.list_all()
    for s in memory_sessions:
        if s.session_id not in seen_ids and s.status in ("completed", "cancelled", "failed"):
            # 内存中的会话但磁盘没有，立即保存
            try:
                from app.core.eval_history_store import save_session
                save_session(s, getattr(s, 'evaluated_text', ''), getattr(s, 'original_text', ''))
            except Exception:
                pass

    # 重新加载（包括刚保存的）
    disk_sessions = load_all_sessions()
    return {
        "items": [
            {
                "session_id": s.get("session_id"),
                "status": s.get("status"),
                "overall_score": s.get("overall_score"),
                "sandtable_type": s.get("sandtable_type", ""),
                "mode": s.get("mode", "pipeline"),
                "created_at": s.get("created_at", ""),
            }
            for s in disk_sessions[:50]
        ]
    }


@router.get("/history/{session_id}")
async def get_history_detail(session_id: str):
    """历史评测详情"""
    session = EvalSession.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"评测记录不存在: {session_id}")
    return session.to_dict()


@router.delete("/history/{session_id}")
async def delete_history(session_id: str):
    """删除评测历史"""
    from app.core.eval_history_store import delete_session as del_session

    # 也清理内存中的session
    mem = EvalSession.get(session_id)
    if mem:
        import gc
        from app.core.eval_session import _sessions
        _sessions.pop(session_id, None)

    if not del_session(session_id):
        raise HTTPException(status_code=404, detail=f"评测记录不存在: {session_id}")
    return {"status": "deleted", "session_id": session_id}


@router.post("/history/compare")
async def compare_evaluations(req: dict):
    """对比两次评测"""
    from app.core.eval_history_store import load_session
    ids = req.get("session_ids", [])
    if len(ids) != 2:
        raise HTTPException(status_code=400, detail="请提供2个session_id")

    s1 = load_session(ids[0])
    s2 = load_session(ids[1])
    if not s1 or not s2:
        raise HTTPException(status_code=404, detail="其中一个评测记录不存在")

    # 提取维度分数
    def extract_scores(s):
        comp_phase = s.get("phases", {}).get("comprehensive", {})
        result = comp_phase.get("result", {}) if isinstance(comp_phase, dict) else {}
        return {
            "overall_score": s.get("overall_score", 0),
            "dimension_scores": result.get("dimension_scores", {}),
        }

    scores1 = extract_scores(s1)
    scores2 = extract_scores(s2)

    # 计算差异
    deltas = {}
    all_dims = set(list(scores1["dimension_scores"].keys()) + list(scores2["dimension_scores"].keys()))
    for dim in all_dims:
        v1 = scores1["dimension_scores"].get(dim, 0)
        v2 = scores2["dimension_scores"].get(dim, 0)
        deltas[dim] = round(v2 - v1, 1)

    return {
        "session_1": {"session_id": ids[0], "overall_score": scores1["overall_score"], "dimension_scores": scores1["dimension_scores"]},
        "session_2": {"session_id": ids[1], "overall_score": scores2["overall_score"], "dimension_scores": scores2["dimension_scores"]},
        "deltas": deltas,
        "overall_delta": round(scores2["overall_score"] - scores1["overall_score"], 1),
    }


# ── 保留兼容旧接口 ──

@router.post("/semantic")
async def evaluate_semantic(req: EvalStartRequest):
    """语义评测（同步模式，兼容旧接口）"""
    try:
        evaluator = _get_evaluator(with_llm=True)
        from app.models.enums import SandtableType, UserRole
        st = SandtableType(req.sandtable_type) if isinstance(req.sandtable_type, str) else req.sandtable_type
        roles = [UserRole(r) for r in req.user_roles] if req.user_roles else None

        result = await evaluator.evaluate(
            optimized_text=req.optimized_text,
            sandtable_type=st,
            original_text=req.original_text,
            platforms=[AIPlatform.DEEPSEEK],
            user_roles=roles,
            custom_questions=req.custom_questions,
        )

        from app.models.schemas import EvaluateResponse
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
    from app.core.evaluator import ROLE_QUESTIONS
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
