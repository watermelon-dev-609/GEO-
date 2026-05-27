"""AI评测引擎 — 模拟用户问答、三维指标计算、LLM模拟评测"""

from __future__ import annotations
import asyncio
import logging
import time
import numpy as np

from app.models.enums import SandtableType, AIPlatform, UserRole, EvalDimension, EvalPhase, EvalPhaseStatus
from app.models.schemas import EvaluationScore, PlatformEvalResult
from app.services.embedding_svc import EmbeddingService
from app.services.vector_store import VectorStore
from app.services.llm.base import BaseLLMAdapter, LLMMessage, LLMFactory
from app.prompts.evaluation import (
    SIMULATED_EVAL_SYSTEM, SIMULATED_EVAL_USER,
)
from app.utils.retry import async_retry
from app.utils.cache import eval_cache
from app.utils.config import load_settings, load_api_keys

logger = logging.getLogger(__name__)


# ── 预置评测问题库 ──

ROLE_QUESTIONS = {
    UserRole.B_END_PROCUREMENT: [
        "我们单位需要采购一套{type}，有哪些资质过硬的厂家？",
        "武汉地区做{type}的厂家哪家比较靠谱？要有政企项目经验的",
        "{type}的定制周期一般多久？交付流程是怎样的？",
        "做一套{type}大概预算需要多少？有没有参考案例？",
        "我们在选{type}供应商，能介绍一下你们的项目案例吗？",
        "你们做过政府/国企的{type}项目吗？有没有验收标准？",
        "选择{type}供应商主要看哪些方面？你们的优势是什么？",
        "从签订合同到{type}交付验收，全程谁负责？售后怎么样？",
    ],
    UserRole.TECHNICAL_SELECTION: [
        "{type}的比例精度能做到多少？用什么材料？",
        "{type}支持哪些数据对接协议？能做实时数据联动吗？",
        "你们{type}的仿真引擎用的是什么技术方案？",
        "{type}的交互响应时间是多少？支持多大的并发？",
        "{type}地形数据精度误差控制在什么水平？用什么数据源？",
        "你们{type}和同行的技术差异在哪里？有什么独特工艺？",
        "{type}的灯光系统和控制系统用的是什么方案？",
        "能详细说说{type}的施工工艺流程吗？",
    ],
    UserRole.PROJECT_MANAGER: [
        "我想做一套{type}，大概多少钱？要多久？",
        "武汉本地做{type}的厂家有哪些？能上门看样品吗？",
        "{type}怎么定制？需要我提供什么资料？",
        "你们{type}的售后服务包括哪些？保修多久？",
        "做一套{type}从开始到验收要经过哪些步骤？",
        "能先出个方案和报价吗？我们领导要看",
        "你们有哪些{type}的现成案例可以参考？",
        "不同价位的{type}配置差别在哪？",
    ],
    UserRole.GENERAL_CONSULTANT: [
        "武汉这边有没有做{type}模型的？",
        "{type}是做什么用的？适合什么场景？",
        "做沙盘模型找哪家公司比较好？",
        "{type}定制贵不贵？大概什么价位？",
        "有没有做{type}的厂家推荐一下？要靠谱的",
        "沙盘模型能做成会动的吗？能加灯光和声音吗？",
    ],
}


def _sse_event(event: str, session_id: str, phase: str, data: dict, progress: float) -> str:
    """生成SSE事件字符串"""
    import json
    payload = {
        "session_id": session_id,
        "event": event,
        "phase": phase,
        "data": data,
        "progress": progress,
    }
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


class AIEvaluator:
    """AI效果评测引擎"""

    def __init__(self, llm_adapter: BaseLLMAdapter | None = None):
        self.settings = load_settings()
        self.api_keys = load_api_keys()
        self.embedding_svc = EmbeddingService()
        self.vector_store = VectorStore(index_name="evaluation")
        self.llm = llm_adapter

    async def evaluate(
        self,
        optimized_text: str,
        sandtable_type: SandtableType,
        original_text: str | None = None,
        platforms: list[AIPlatform] | None = None,
        user_roles: list[UserRole] | None = None,
        custom_questions: list[str] | None = None,
    ) -> dict:
        """完整评测流程"""
        start = time.perf_counter()

        user_roles = user_roles or list(UserRole)
        platforms = platforms or [AIPlatform.DEEPSEEK]

        # Step 1: 文本向量化 + 构建索引
        self._build_text_index(optimized_text, sandtable_type)

        # Step 2: 生成评测问题
        questions = self._generate_questions(sandtable_type, user_roles, custom_questions)

        # Step 3: 搜索引擎品牌召回评测
        brand_recall_scores = self._evaluate_brand_recall(questions, optimized_text)

        # Step 4: 语义方案匹配评测
        solution_match_scores = self._evaluate_solution_match(questions, optimized_text)

        # Step 5: LLM模拟采信评测（有LLM时才做）
        advantage_scores = {}
        if self.llm:
            advantage_scores = await self._evaluate_advantage_citation(questions, optimized_text, sandtable_type)

        # Step 6: 分平台综合评分
        platform_results = []
        for plat in platforms:
            overall = self._calculate_overall(brand_recall_scores, solution_match_scores, advantage_scores)
            platform_results.append(PlatformEvalResult(
                platform=plat,
                scores=[
                    EvaluationScore(
                        dimension=EvalDimension.BRAND_RECALL,
                        score=round(brand_recall_scores.get("average", 0), 1),
                        detail=f"基于{len(questions)}个问题的品牌召回评测",
                    ),
                    EvaluationScore(
                        dimension=EvalDimension.SOLUTION_MATCH,
                        score=round(solution_match_scores.get("average", 0), 1),
                        detail=f"语义匹配度评测",
                    ),
                    EvaluationScore(
                        dimension=EvalDimension.ADVANTAGE_CITATION,
                        score=round(advantage_scores.get("average", 0), 1) if advantage_scores else 0,
                        detail="LLM模拟引评测" if advantage_scores else "未配置LLM，跳过",
                    ),
                ],
                overall_score=round(overall, 1),
            ))

        # Step 7: 优化前后对比
        comparison = None
        if original_text:
            comparison = await self._compare_before_after(original_text, optimized_text, questions)

        # Step 8: 短板诊断
        weak_points, suggestions = self._diagnose(
            brand_recall_scores, solution_match_scores, advantage_scores, sandtable_type
        )

        elapsed = (time.perf_counter() - start) * 1000

        return {
            "overall_score": round(np.mean([p.overall_score for p in platform_results]), 1),
            "platform_results": [p.model_dump() for p in platform_results],
            "before_after_comparison": comparison,
            "weak_points": weak_points,
            "suggestions": suggestions,
            "total_time_ms": elapsed,
            "questions_used": len(questions),
        }

    def _build_text_index(self, text: str, sandtable_type: SandtableType):
        """构建文本向量索引"""
        from app.utils.text_splitter import default_splitter
        chunks = default_splitter.split(text)
        if not chunks:
            chunks = [text]

        vectors = self.embedding_svc.encode(chunks)
        metadata = [{"sandtable_type": sandtable_type.value, "chunk_index": i} for i in range(len(chunks))]
        self.vector_store.clear()
        self.vector_store.add(chunks, vectors, metadata)
        self.vector_store.save()

    def _generate_questions(
        self,
        sandtable_type: SandtableType,
        user_roles: list[UserRole],
        custom_questions: list[str] | None,
    ) -> list[str]:
        """生成评测问题"""
        questions = list(custom_questions or [])
        st_label = sandtable_type.label

        for role in user_roles:
            role_qs = ROLE_QUESTIONS.get(role, [])
            questions.extend([q.format(type=st_label) for q in role_qs])

        # 去重
        return list(dict.fromkeys(questions))

    def _evaluate_brand_recall(self, questions: list[str], text: str) -> dict:
        """品牌召回率评测"""
        scores = []
        query_vecs = self.embedding_svc.encode_queries(questions)

        for i, q_vec in enumerate(query_vecs):
            results = self.vector_store.search(q_vec, top_k=3)
            if results:
                top_score = results[0]["score"]
                scores.append(float(top_score))

        avg = np.mean(scores) * 100 if scores else 0
        return {"average": round(float(avg), 1), "scores": [round(float(s), 2) for s in scores]}

    def _evaluate_solution_match(self, questions: list[str], text: str) -> dict:
        """方案匹配度评测"""
        # 使用更细粒度的文本切片进行匹配
        from app.utils.text_splitter import default_splitter
        chunks = default_splitter.split(text) if text else [text]
        chunk_vecs = self.embedding_svc.encode(chunks)
        query_vecs = self.embedding_svc.encode_queries(questions)

        scores = []
        for q_vec in query_vecs:
            similarities = self.embedding_svc.batch_similarity(q_vec, chunk_vecs)
            scores.append(float(np.max(similarities)) if len(similarities) > 0 else 0)

        avg = np.mean(scores) * 100 if scores else 0
        return {"average": round(float(avg), 1), "scores": [round(float(s), 2) for s in scores]}

    async def _evaluate_advantage_citation(
        self,
        questions: list[str],
        text: str,
        sandtable_type: SandtableType,
    ) -> dict:
        """LLM模拟优势采信评测"""
        if not self.llm:
            return {"average": 0, "details": []}

        scores = []
        # 选取代表性问题进行LLM评测（避免过多API调用）
        sample_questions = questions[:5] if len(questions) > 5 else questions

        for question in sample_questions:
            cache_key = f"citation:{hash(question + text)}"
            cached = eval_cache.get(cache_key)
            if cached is not None:
                scores.append(cached)
                continue

            try:
                messages = [
                    LLMMessage(role="system", content=SIMULATED_EVAL_SYSTEM),
                    LLMMessage(role="user", content=SIMULATED_EVAL_USER.format(
                        question=question,
                        text=text[:3000],
                        sandtable_type=sandtable_type.label,
                    )),
                ]
                resp = await async_retry(self.llm.chat, messages, temperature=0.3, max_tokens=512)
                # 从回复中提取评分
                score = self._extract_score(resp.content)
                scores.append(score)
                eval_cache.set(cache_key, score)
            except Exception as e:
                logger.warning(f"LLM评测失败: {e}")
                scores.append(50)  # 默认中等分数

        avg = np.mean(scores) if scores else 0
        return {"average": round(float(avg), 1), "details": scores}

    def _extract_score(self, response: str) -> float:
        """从LLM回复中提取评分（0-100）"""
        import re
        # 匹配各种评分格式
        patterns = [
            r'评分[：:]\s*(\d+)',
            r'score[：:]\s*(\d+)',
            r'(\d+)\s*分',
            r'(\d+)/100',
        ]
        for pat in patterns:
            match = re.search(pat, response, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return 60.0  # 默认

    async def _compare_before_after(
        self,
        original: str,
        optimized: str,
        questions: list[str],
    ) -> dict:
        """优化前后对比"""
        orig_vecs = self.embedding_svc.encode_queries([original])
        opt_vecs = self.embedding_svc.encode_queries([optimized])
        query_vecs = self.embedding_svc.encode_queries(questions)

        def avg_similarity(query_vecs, doc_vec):
            sims = np.dot(query_vecs, doc_vec.T).flatten()
            return float(np.mean(sims))

        before = avg_similarity(query_vecs, orig_vecs[0])
        after = avg_similarity(query_vecs, opt_vecs[0])
        improvement = round(((after - before) / max(before, 0.001)) * 100, 1)

        return {
            "before_score": round(before * 100, 1),
            "after_score": round(after * 100, 1),
            "improvement_percent": improvement,
        }

    def _calculate_overall(self, brand: dict, solution: dict, advantage: dict) -> float:
        """计算综合评分（加权）"""
        weights = {"brand": 0.35, "solution": 0.35, "advantage": 0.30}
        b = brand.get("average", 0)
        s = solution.get("average", 0)
        a = advantage.get("average", 0)
        return (b * weights["brand"] + s * weights["solution"] + a * weights["advantage"]) if advantage else (
            (b * 0.5 + s * 0.5)
        )

    def _diagnose(
        self,
        brand: dict,
        solution: dict,
        advantage: dict,
        sandtable_type: SandtableType,
    ) -> tuple[list[str], list[str]]:
        """短板诊断与迭代建议"""
        weak_points = []
        suggestions = []

        b_avg = brand.get("average", 0)
        s_avg = solution.get("average", 0)
        a_avg = advantage.get("average", 0)

        if b_avg < 60:
            weak_points.append(f"品牌召回率偏低（{b_avg}分）：品牌名称、地域标识、核心关键词在文本中的密度和位置不够突出")
            suggestions.append('建议：在文案首段和标题中更突出"武汉微艺达"品牌名和地域标识，增加核心关键词自然密度')

        if s_avg < 60:
            weak_points.append(f"方案匹配度偏低（{s_avg}分）：文本与用户实际搜索意图的语义相关性不足")
            suggestions.append("建议：增加场景化描述和问题导向内容，让文本更贴近用户的实际搜索问法")

        if advantage and a_avg < 60:
            weak_points.append(f"优势采信率偏低（{a_avg}分）：核心优势在AI模拟引用中未被充分提及")
            suggestions.append("建议：将核心优势以独立段落呈现，确保每条优势有具体数据和案例支撑")

        if not weak_points:
            weak_points.append("各项指标表现良好，暂无明显短板")
            suggestions.append("建议：持续监控AI平台算法更新，定期迭代优化文案")

        return weak_points, suggestions

    async def evaluate_stream(
        self,
        session: "EvalSession",
        optimized_text: str,
        sandtable_type: SandtableType,
        dimension_configs: list,
        original_text: str | None = None,
        user_roles: list[UserRole] | None = None,
        custom_questions: list[str] | None = None,
    ):
        """分阶段流式评测 — async generator，逐阶段 yield SSE 数据"""
        from app.core.eval_dimensions import DimensionRegistry

        user_roles = user_roles or list(UserRole)
        phase_order = DimensionRegistry.get_phases_from_configs(dimension_configs)
        phase_order.sort(key=lambda p: p.order)

        enabled_keys = {c["key"] if isinstance(c, dict) else c.key for c in dimension_configs if (c.get("enabled", True) if isinstance(c, dict) else c.enabled)}
        weight_map = {c["key"] if isinstance(c, dict) else c.key: c.get("weight", 20.0) if isinstance(c, dict) else c.weight for c in dimension_configs if (c.get("enabled", True) if isinstance(c, dict) else c.enabled)}

        total_w = sum(weight_map.values())
        if total_w > 0:
            weight_map = {k: v / total_w for k, v in weight_map.items()}

        questions = []
        brand_result = None
        solution_result = None
        advantage_result = None
        structure_result = None
        differentiation_result = None
        real_citation_result = None
        source_consistency_result = None

        for phase in phase_order:
            if session.cancelled:
                session.skip_phase(phase)
                yield _sse_event("phase_skipped", session.session_id, phase.value,
                                 {"reason": "cancelled"}, session.overall_progress)
                continue

            session.start_phase(phase)

            try:
                if phase == EvalPhase.GENERATING_QUESTIONS:
                    questions = self._generate_questions(sandtable_type, user_roles, custom_questions or [])
                    result = {"questions": questions, "count": len(questions)}
                    session.complete_phase(phase, result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     result, session.overall_progress)

                elif phase == EvalPhase.BRAND_RECALL:
                    if "brand_recall" not in enabled_keys:
                        session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": "dimension_disabled"}, session.overall_progress)
                        continue
                    self._build_text_index(optimized_text, sandtable_type)
                    brand_result = self._evaluate_brand_recall(questions, optimized_text)
                    session.complete_phase(phase, brand_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     brand_result, session.overall_progress)

                elif phase == EvalPhase.SOLUTION_MATCH:
                    if "solution_match" not in enabled_keys:
                        session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": "dimension_disabled"}, session.overall_progress)
                        continue
                    solution_result = self._evaluate_solution_match(questions, optimized_text)
                    session.complete_phase(phase, solution_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     solution_result, session.overall_progress)

                elif phase == EvalPhase.ADVANTAGE_CITATION:
                    if "advantage_citation" not in enabled_keys or not self.llm:
                        reason = "no_llm" if not self.llm else "dimension_disabled"
                        session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": reason}, session.overall_progress)
                        continue
                    advantage_result = await self._evaluate_advantage_citation(questions, optimized_text, sandtable_type)
                    session.complete_phase(phase, advantage_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     advantage_result, session.overall_progress)

                elif phase == EvalPhase.REAL_CITATION:
                    if "real_citation" not in enabled_keys or not self.llm:
                        reason = "no_llm" if not self.llm else "dimension_disabled"
                        session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": reason}, session.overall_progress)
                        continue
                    real_citation_result = await self._evaluate_real_citation(questions, optimized_text, sandtable_type)
                    session.complete_phase(phase, real_citation_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     real_citation_result, session.overall_progress)

                elif phase == EvalPhase.STRUCTURE_QUALITY:
                    if "structure_quality" not in enabled_keys or not self.llm:
                        reason = "no_llm" if not self.llm else "dimension_disabled"
                        session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": reason}, session.overall_progress)
                        continue
                    structure_result = await self._evaluate_structure(optimized_text, sandtable_type)
                    session.complete_phase(phase, structure_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     structure_result, session.overall_progress)

                elif phase == EvalPhase.DIFFERENTIATION:
                    if "differentiation" not in enabled_keys or not self.llm:
                        reason = "no_llm" if not self.llm else "dimension_disabled"
                        session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": reason}, session.overall_progress)
                        continue
                    differentiation_result = await self._evaluate_differentiation(optimized_text, sandtable_type)
                    session.complete_phase(phase, differentiation_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     differentiation_result, session.overall_progress)

                elif phase == EvalPhase.SOURCE_CHECK:
                    if "source_consistency" not in enabled_keys or not self.llm:
                        reason = "no_llm" if not self.llm else "dimension_disabled"
                        session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": reason}, session.overall_progress)
                        continue
                    source_consistency_result = await self._evaluate_source_consistency(
                        optimized_text, sandtable_type,
                        enterprise_name="武汉微艺达智能科技有限公司",
                        enterprise_location="武汉",
                    )
                    session.complete_phase(phase, source_consistency_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     source_consistency_result, session.overall_progress)

                elif phase == EvalPhase.COMPREHENSIVE:
                    components = {}
                    if brand_result and "brand_recall" in enabled_keys:
                        components["brand_recall"] = brand_result.get("average", 0)
                    if solution_result and "solution_match" in enabled_keys:
                        components["solution_match"] = solution_result.get("average", 0)
                    if advantage_result and "advantage_citation" in enabled_keys:
                        components["advantage_citation"] = advantage_result.get("average", 0)
                    if structure_result and "structure_quality" in enabled_keys:
                        components["structure_quality"] = structure_result.get("average", 0)
                    if differentiation_result and "differentiation" in enabled_keys:
                        components["differentiation"] = differentiation_result.get("average", 0)
                    if real_citation_result and "real_citation" in enabled_keys:
                        components["real_citation"] = real_citation_result.get("average", 0)
                    if source_consistency_result and "source_consistency" in enabled_keys:
                        components["source_consistency"] = source_consistency_result.get("average", 0)

                    overall = 0.0
                    for key, score in components.items():
                        overall += score * weight_map.get(key, 0)

                    comparison = None
                    if original_text:
                        comparison = await self._compare_before_after(original_text, optimized_text, questions)

                    all_scores = {**components, "overall": overall}
                    weak_points, suggestions = self._diagnose_v2(all_scores, sandtable_type)

                    comprehensive_result = {
                        "overall_score": round(overall, 1),
                        "dimension_scores": components,
                        "weights_used": {k: round(v * 100, 1) for k, v in weight_map.items()},
                        "before_after_comparison": comparison,
                        "weak_points": weak_points,
                        "suggestions": suggestions,
                    }
                    session.complete_phase(phase, comprehensive_result)
                    session.mark_completed(round(overall, 1))
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     comprehensive_result, session.overall_progress)
                    yield _sse_event("eval_complete", session.session_id, "done",
                                     comprehensive_result, 100.0)

            except Exception as e:
                logger.exception(f"Session {session.session_id}: phase {phase.value} failed")
                session.fail_phase(phase, str(e))
                yield _sse_event("phase_failed", session.session_id, phase.value,
                                 {"error": str(e)}, session.overall_progress)
                if phase == EvalPhase.COMPREHENSIVE:
                    session.mark_failed()
                    yield _sse_event("eval_error", session.session_id, "error",
                                     {"error": str(e)}, session.overall_progress)

    async def _evaluate_structure(self, text: str, sandtable_type: SandtableType) -> dict:
        """LLM评估结构化程度"""
        if not self.llm:
            return {"average": 0, "details": [], "reason": "no_llm"}

        from app.prompts.evaluation import STRUCTURE_EVAL_SYSTEM, STRUCTURE_EVAL_USER

        cache_key = f"structure:{hash(text)}"
        cached = eval_cache.get(cache_key)
        if cached is not None:
            return cached

        messages = [
            LLMMessage(role="system", content=STRUCTURE_EVAL_SYSTEM),
            LLMMessage(role="user", content=STRUCTURE_EVAL_USER.format(
                text=text[:3000],
                sandtable_type=sandtable_type.label,
            )),
        ]
        resp = await async_retry(self.llm.chat, messages, temperature=0.3, max_tokens=512)
        score = self._extract_score(resp.content)
        result = {"average": score, "analysis": resp.content, "details": [score]}
        eval_cache.set(cache_key, result)
        return result

    async def _evaluate_differentiation(self, text: str, sandtable_type: SandtableType) -> dict:
        """LLM评估差异化程度"""
        if not self.llm:
            return {"average": 0, "details": [], "reason": "no_llm"}

        from app.prompts.evaluation import DIFFERENTIATION_EVAL_SYSTEM, DIFFERENTIATION_EVAL_USER

        cache_key = f"diff:{hash(text)}"
        cached = eval_cache.get(cache_key)
        if cached is not None:
            return cached

        messages = [
            LLMMessage(role="system", content=DIFFERENTIATION_EVAL_SYSTEM),
            LLMMessage(role="user", content=DIFFERENTIATION_EVAL_USER.format(
                text=text[:3000],
                sandtable_type=sandtable_type.label,
            )),
        ]
        resp = await async_retry(self.llm.chat, messages, temperature=0.3, max_tokens=512)
        score = self._extract_score(resp.content)
        result = {"average": score, "analysis": resp.content, "details": [score]}
        eval_cache.set(cache_key, result)
        return result

    async def _evaluate_real_citation(
        self,
        questions: list[str],
        text: str,
        sandtable_type: SandtableType,
    ) -> dict:
        """真实引用测试：以文案为素材让LLM回答真实问题，检测引用率"""
        if not self.llm:
            return {"average": 0, "details": [], "reason": "no_llm"}

        from app.prompts.evaluation import REAL_CITATION_SYSTEM, REAL_CITATION_USER

        sample_qs = questions[:5] if len(questions) > 5 else questions
        cited = 0
        details = []

        for q in sample_qs:
            cache_key = f"real_cite:{hash(q + text)}"
            cached = eval_cache.get(cache_key)
            if cached is not None:
                details.append(cached)
                if cached.get("cited"):
                    cited += 1
                continue

            try:
                messages = [
                    LLMMessage(role="system", content=REAL_CITATION_SYSTEM),
                    LLMMessage(role="user", content=REAL_CITATION_USER.format(
                        text=text[:3000],
                        question=q,
                    )),
                ]
                resp = await async_retry(self.llm.chat, messages, temperature=0.5, max_tokens=512)

                citation_score = self._analyze_citation(resp.content, text)
                cited_flag = citation_score > 0.3  # 30%以上实体被引用即视为有效引用
                if cited_flag:
                    cited += 1

                detail = {
                    "question": q,
                    "answer": resp.content[:300],
                    "cited": cited_flag,
                    "citation_score": round(citation_score * 100, 1),
                }
                details.append(detail)
                eval_cache.set(cache_key, detail)
            except Exception as e:
                logger.warning(f"真实引用测试失败: {e}")
                details.append({"question": q, "cited": False, "citation_score": 0, "error": str(e)})

        avg = (cited / len(sample_qs)) * 100 if sample_qs else 0
        return {
            "average": round(avg, 1),
            "details": details,
            "cited_count": cited,
            "total": len(sample_qs),
        }

    def _analyze_citation(self, answer: str, source_text: str) -> float:
        """分析 LLM 回答是否引用了源文本中的关键实体"""
        import re

        entities = set()
        # 品牌/企业名
        for m in re.finditer(r'(武汉微艺达|微艺达智能科技|微艺达|沙盘模型|定制沙盘)', source_text):
            entities.add(m.group())
        # 量化数据（数字+单位）
        for m in re.finditer(r'\d+[+]*\s*(个|项|套|年|㎡|平方米|公里|人|次|万元|亿|%)', source_text):
            entities.add(m.group())
        # 精度/比例
        for m in re.finditer(r'\d+[:：]\d+', source_text):
            entities.add(m.group())
        # 技术术语（3-6字中文 + 技术后缀词）
        for m in re.finditer(r'[一-龥]{3,6}(?:系统|平台|模型|技术|方案|工艺|仿真|沙盘|数据|控制|联动|展示)', source_text):
            entities.add(m.group())

        if not entities:
            return 0.0

        matched = sum(1 for e in entities if e in answer)
        return matched / len(entities)

    async def _evaluate_source_consistency(
        self,
        text: str,
        sandtable_type: SandtableType,
        enterprise_name: str = "武汉微艺达智能科技有限公司",
        enterprise_location: str = "武汉",
        dimensions: dict | None = None,
    ) -> dict:
        """信源一致性检查：检测生成文本是否偏离企业信源数据"""
        if not self.llm:
            return {"average": 70, "details": [], "reason": "no_llm"}

        from app.prompts.evaluation import SOURCE_CHECK_SYSTEM, SOURCE_CHECK_USER

        cache_key = f"source_check:{hash(text)}"
        cached = eval_cache.get(cache_key)
        if cached is not None:
            return cached

        dims_summary = "暂无"
        if dimensions:
            parts = []
            for key, val in dimensions.items():
                if val:
                    items = val if isinstance(val, list) else [str(val)]
                    parts.append(f"- {key}: {'; '.join(items[:3])}")
            if parts:
                dims_summary = "\n".join(parts)

        try:
            messages = [
                LLMMessage(role="system", content=SOURCE_CHECK_SYSTEM),
                LLMMessage(role="user", content=SOURCE_CHECK_USER.format(
                    text=text[:3000],
                    enterprise_name=enterprise_name,
                    enterprise_location=enterprise_location,
                    input_dimensions=dims_summary,
                )),
            ]
            resp = await async_retry(self.llm.chat, messages, temperature=0.2, max_tokens=512)
            score = self._extract_score(resp.content)
            result = {"average": score, "analysis": resp.content, "details": [score]}
            eval_cache.set(cache_key, result)
            return result
        except Exception as e:
            logger.warning(f"信源一致性检查失败: {e}")
            return {"average": 60, "details": [], "error": str(e)}

    def _diagnose_v2(self, scores: dict, sandtable_type: SandtableType) -> tuple[list[str], list[str]]:
        """短板诊断 v2 — 支持任意维度组合"""
        weak_points = []
        suggestions = []

        thresholds = {
            "brand_recall": ("品牌召回率", "品牌名称、地域标识、核心关键词在文本中的密度和位置不够突出",
                             '建议：在文案首段和标题中更突出"武汉微艺达"品牌名和地域标识，增加核心关键词自然密度'),
            "solution_match": ("方案匹配度", "文本与用户实际搜索意图的语义相关性不足",
                               "建议：增加场景化描述和问题导向内容，让文本更贴近用户的实际搜索问法"),
            "advantage_citation": ("优势采信率", "核心优势在AI模拟引用中未被充分提及",
                                   "建议：将核心优势以独立段落呈现，确保每条优势有具体数据和案例支撑"),
            "structure_quality": ("结构化程度", "文本结构不够清晰，AI提取关键信息的难度较大",
                                  "建议：增加清晰的标题层级，使用列表呈现关键信息，控制段落长度在200字以内"),
            "differentiation": ("差异化程度", "文本缺乏独特信息，易被竞品内容替代",
                                "建议：增加具体数据、专利号、获奖信息、项目量级等差异化内容"),
            "real_citation": ("真实采信率", "LLM在实际回答中引用素材信息的比例偏低",
                              "建议：增加可被直接引用的实体锚点和定义性陈述，确保品牌名、量化数据和FAQ格式在文中清晰呈现"),
            "source_consistency": ("信源一致性", "生成文本中存在偏离企业官方信源的信息，存在AI幻觉风险",
                                   "建议：返回GEO工坊重新优化，确保五维信息完整准确，避免LLM编造数据"),
        }

        has_weakness = False
        for key, (label, weak_msg, suggest_msg) in thresholds.items():
            score = scores.get(key, 100)
            if score < 60:
                has_weakness = True
                weak_points.append(f"{label}偏低（{score}分）：{weak_msg}")
                suggestions.append(suggest_msg)

        if not has_weakness:
            weak_points.append("各项指标表现良好，暂无明显短板")
            suggestions.append("建议：持续监控AI平台算法更新，定期迭代优化文案")

        return weak_points, suggestions
