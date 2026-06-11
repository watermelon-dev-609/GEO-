"""AI评测API路由"""

import asyncio
import json
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.models.schemas import EvalStartRequest, CompareEvaluationsRequest, QuickBrandCheckRequest, LLMGenerateQuestionsRequest
from app.models.enums import AIPlatform, EvalPhase
from app.core.evaluator import AIEvaluator
from app.core.eval_session import EvalSession
from app.core.eval_dimensions import DimensionRegistry
from app.services.llm.base import LLMFactory
from app.utils.config import load_settings, load_api_keys, get_brand_variants

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
    # 短文本校验
    if not req.optimized_text or len(req.optimized_text.strip()) < 50:
        raise HTTPException(status_code=400, detail="输入文本过短（少于50字），无法进行有效评测")

    evaluator = _get_evaluator(with_llm=True)

    session = await EvalSession.create(sandtable_type=req.sandtable_type, mode=req.mode)
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
    try:
        st = SandtableType(req.sandtable_type) if isinstance(req.sandtable_type, str) else req.sandtable_type
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的沙盘类型: {req.sandtable_type}")
    try:
        roles = [UserRole(r) for r in req.user_roles] if req.user_roles else None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效的用户角色: {e}")

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
        except asyncio.CancelledError:
            await session.mark_cancelled()
            raise
        except GeneratorExit:
            await session.cancel()
            await session.mark_cancelled()
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
    session = await EvalSession.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    return session.to_dict()


@router.post("/cancel/{session_id}")
async def cancel_evaluation(session_id: str):
    """取消评测"""
    session = await EvalSession.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    await session.cancel()
    await session.mark_cancelled()
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
    memory_sessions = await EvalSession.list_all()
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
    session = await EvalSession.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"评测记录不存在: {session_id}")
    return session.to_dict()


@router.delete("/history/{session_id}")
async def delete_history(session_id: str):
    """删除评测历史"""
    from app.core.eval_history_store import delete_session as del_session

    # 也清理内存中的session
    await EvalSession.remove(session_id)

    if not del_session(session_id):
        raise HTTPException(status_code=404, detail=f"评测记录不存在: {session_id}")
    return {"status": "deleted", "session_id": session_id}


@router.post("/history/compare")
async def compare_evaluations(req: CompareEvaluationsRequest):
    """对比两次评测"""
    from app.core.eval_history_store import load_session
    ids = req.session_ids
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
        try:
            st = SandtableType(req.sandtable_type) if isinstance(req.sandtable_type, str) else req.sandtable_type
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的沙盘类型: {req.sandtable_type}")
        try:
            roles = [UserRole(r) for r in req.user_roles] if req.user_roles else None
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"无效的用户角色: {e}")

        # 使用用户选择的平台；未选择时默认 DeepSeek
        platforms = [AIPlatform(p) for p in req.platforms] if req.platforms else [AIPlatform.DEEPSEEK]
        result = await evaluator.evaluate(
            optimized_text=req.optimized_text,
            sandtable_type=st,
            original_text=req.original_text,
            platforms=platforms,
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
async def quick_brand_check(req: QuickBrandCheckRequest):
    """快速品牌曝光检测（无需LLM，纯向量计算）"""
    try:
        from app.services.embedding_svc import EmbeddingService

        text = req.text
        brand_keywords = req.brand_keywords
        if not brand_keywords:
            brand_keywords = get_brand_variants()

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


@router.post("/generate-questions")
async def generate_eval_questions(req: LLMGenerateQuestionsRequest):
    """基于优化文案，使用LLM生成针对性的评测问题供用户选择"""
    from app.services.llm.base import LLMMessage

    settings = load_settings()
    api_keys = load_api_keys()
    default_platform = settings.get("llm", {}).get("default_model", "deepseek")
    plat_cfg = settings.get("llm", {}).get("platforms", {}).get(default_platform, {})
    key_info = api_keys.get("platforms", {}).get(default_platform, {})

    api_key = key_info.get("api_key", "")
    if not api_key or "your-" in api_key:
        raise HTTPException(status_code=503, detail="LLM未配置，请先在侧边栏配置API Key")

    from app.models.enums import AIPlatform
    adapter_type = AIPlatform(default_platform).adapter_type
    llm = LLMFactory.create(
        platform=adapter_type, api_key=api_key,
        model_name=plat_cfg.get("model_name", ""),
        base_url=plat_cfg.get("base_url"),
    )

    from app.models.enums import SandtableType
    from app.utils.config import get_enterprise_name
    try:
        st_label = SandtableType(req.sandtable_type).label
    except ValueError:
        st_label = req.sandtable_type
    brand_variants = get_brand_variants()
    en = req.enterprise_name or (brand_variants[0] if brand_variants else get_enterprise_name())

    system_prompt = (
        "你是一个GEO评测问题生成专家。你的任务是根据给定的企业文案，生成模拟真实用户"
        "在AI平台上可能搜索的问题。问题应覆盖：品牌直问、场景需求、产品对比、技术细节等角度。"
        "每个问题应像真实用户会输入的自然语言查询，不要编造文案中不存在的信息。"
    )
    user_prompt = (
        f"以下是一段关于「{en}」在「{st_label}」领域的优化文案：\n\n"
        f"---\n{req.optimized_text[:3000]}\n---\n\n"
        f"请基于这段文案生成 {req.count} 个真实的用户搜索问题，覆盖不同查询意图。\n"
        f"要求：\n"
        f"1. 每个问题一行，用中文\n"
        f"2. 问题应该像真实用户在AI搜索框中输入的自然语言\n"
        f"3. 覆盖品牌直问、场景需求、产品对比、技术细节、价格咨询等角度\n"
        f"4. 只基于文案中已有的事实，不要编造\n\n"
        f"直接返回问题列表，每行一个问题，不要编号。"
    )

    try:
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]
        resp = await llm.chat(messages, temperature=0.7, max_tokens=1024)
        questions = [
            q.strip() for q in resp.content.strip().split('\n')
            if q.strip() and not q.strip().startswith('#') and len(q.strip()) >= 5
        ]
        # 限制数量
        questions = questions[:req.count]

        # 补充预设问题作为兜底
        if len(questions) < 5:
            from app.core.evaluator import ROLE_QUESTIONS
            from app.models.enums import UserRole
            fallback = []
            for role in [UserRole.B_END_PROCUREMENT, UserRole.GENERAL_CONSULTANT]:
                for q in ROLE_QUESTIONS.get(role, [])[:3]:
                    fallback.append(q.format(type=st_label))
            questions.extend(fallback[:req.count - len(questions)])

        return {
            "questions": list(dict.fromkeys(questions)),
            "generated_count": len(questions),
            "source": "llm_generated",
        }
    except Exception as e:
        logger.exception("LLM生成评测问题失败")
        raise HTTPException(status_code=500, detail=f"问题生成失败: {str(e)}")
