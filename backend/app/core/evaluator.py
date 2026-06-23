"""AI评测引擎 — 模拟用户问答、三维指标计算、LLM模拟评测"""

from __future__ import annotations
import asyncio
import hashlib
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
    EEAT_EVAL_SYSTEM, EEAT_EVAL_USER,
)
from app.utils.retry import async_retry
from app.utils.cache import eval_cache
from app.utils.config import load_settings, load_api_keys, get_enterprise_name, get_enterprise_location, get_brand_variants

logger = logging.getLogger(__name__)


# ── 预置评测问题库 ──
# 模拟不同用户角色向AI平台提问的查询模板，用于评测引擎测试
# 问题均为模拟查询，非企业真实客户提问

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
        # 从配置读取评测温度参数
        eval_cfg = self.settings.get("evaluation", {})
        temp_cfg = eval_cfg.get("temperature", {})
        self._temp_advantage = temp_cfg.get("advantage_citation", 0.3)
        self._temp_structure = temp_cfg.get("structure_quality", 0.3)
        self._temp_differentiation = temp_cfg.get("differentiation", 0.3)
        self._temp_eeat = temp_cfg.get("eeat", 0.3)
        self._temp_real_citation = temp_cfg.get("real_citation", 0.5)
        self._temp_source = temp_cfg.get("source_consistency", 0.2)

    async def evaluate(
        self,
        optimized_text: str,
        sandtable_type: SandtableType,
        original_text: str | None = None,
        platforms: list[AIPlatform] | None = None,
        user_roles: list[UserRole] | None = None,
        custom_questions: list[str] | None = None,
        diagnosis_result: dict | None = None,
    ) -> dict:
        """完整评测流程

        Args:
            diagnosis_result: 可选，来自 ContentDiagnoser 的规则诊断结果，
                             用于交叉引用和增强短板定位
        """
        start = time.perf_counter()

        # 空文本/过短文本校验
        if not optimized_text or len(optimized_text.strip()) < 50:
            return {
                "overall_score": 0,
                "platform_results": [],
                "before_after_comparison": None,
                "weak_points": ["输入文本过短（少于50字），无法进行有效评测"],
                "suggestions": ["请提供完整的企业/产品文案后重新评测"],
                "total_time_ms": 0,
                "questions_used": 0,
            }

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

        # Step 4.5: 语义对齐度评测（AI原生维度，纯向量计算）
        semantic_alignment_scores = self._evaluate_semantic_alignment(questions, optimized_text)

        # Step 5-9: LLM评测维度（有LLM时才做）
        advantage_scores = {}
        structure_scores = {}
        differentiation_scores = {}
        real_citation_scores = {}
        eeat_scores = {}
        source_consistency_scores = {}
        if self.llm:
            advantage_scores = await self._evaluate_advantage_citation(questions, optimized_text, sandtable_type)
            structure_scores = await self._evaluate_structure(optimized_text, sandtable_type)
            differentiation_scores = await self._evaluate_differentiation(optimized_text, sandtable_type)
            real_citation_scores = await self._evaluate_real_citation(questions, optimized_text, sandtable_type)
            eeat_scores = await self._evaluate_eeat(
                optimized_text, sandtable_type,
                enterprise_name=get_enterprise_name(),
            )
            source_consistency_scores = await self._evaluate_source_consistency(
                optimized_text, sandtable_type,
                enterprise_name=get_enterprise_name(),
                enterprise_location=get_enterprise_location(),
                original_text=original_text,
            )

        # Step 9.5: RAG可检索性评测（AI原生维度，纯向量+切片计算）
        rag_retrievability_scores = self._evaluate_rag_retrievability(questions, optimized_text, get_enterprise_name())

        # Step 10: 分平台综合评分（10维加权）
        components = {
            "brand_recall": brand_recall_scores.get("average", 0),
            "solution_match": solution_match_scores.get("average", 0),
            "semantic_alignment": semantic_alignment_scores.get("average", 0),
            "advantage_citation": advantage_scores.get("average", 0),
            "real_citation": real_citation_scores.get("average", 0),
            "rag_retrievability": rag_retrievability_scores.get("average", 0),
            "structure_quality": structure_scores.get("average", 0),
            "differentiation": differentiation_scores.get("average", 0),
            "eeat_score": eeat_scores.get("average"),
            "source_consistency": source_consistency_scores.get("average"),
        }
        overall = self._calculate_overall_v2(components)

        platform_results = []
        for plat in platforms:
            platform_results.append(PlatformEvalResult(
                platform=plat,
                scores=[
                    EvaluationScore(dimension=EvalDimension.BRAND_RECALL, score=round(components["brand_recall"], 1), detail=f"基于{len(questions)}个问题的品牌召回评测"),
                    EvaluationScore(dimension=EvalDimension.SOLUTION_MATCH, score=round(components["solution_match"], 1), detail="语义匹配度评测"),
                    EvaluationScore(dimension=EvalDimension.ADVANTAGE_CITATION, score=round(components["advantage_citation"], 1), detail="LLM模拟采信评测" if self.llm else "未配置LLM，跳过"),
                    EvaluationScore(dimension=EvalDimension.STRUCTURE_QUALITY, score=round(components["structure_quality"], 1), detail="LLM结构化评测" if self.llm else "未配置LLM，跳过"),
                    EvaluationScore(dimension=EvalDimension.DIFFERENTIATION, score=round(components["differentiation"], 1), detail="LLM差异化评测" if self.llm else "未配置LLM，跳过"),
                    EvaluationScore(dimension=EvalDimension.REAL_CITATION, score=round(components["real_citation"], 1), detail="LLM真实引用评测" if self.llm else "未配置LLM，跳过"),
                    EvaluationScore(dimension=EvalDimension.EEAT_SCORE, score=round(components["eeat_score"], 1), detail="LLM E-E-A-T权威度评测" if self.llm else "未配置LLM，跳过"),
                    EvaluationScore(dimension=EvalDimension.SOURCE_CONSISTENCY, score=round(components["source_consistency"], 1), detail="LLM信源一致性评测" if self.llm else "未配置LLM，跳过"),
                ],
                overall_score=round(overall, 1),
            ))

        # Step 10: 优化前后对比
        comparison = None
        if original_text:
            comparison = await self._compare_before_after(original_text, optimized_text, questions)

        # Step 11: 短板诊断（平台感知 + 诊断器交叉引用）
        primary_platform = platforms[0] if platforms else AIPlatform.DEEPSEEK
        weak_points, suggestions = self._diagnose_v2(
            components, sandtable_type, platform_id=primary_platform.value,
            diagnosis_result=diagnosis_result,
        )

        elapsed = (time.perf_counter() - start) * 1000

        return {
            "overall_score": round(overall, 1),
            "platform_results": [p.model_dump() for p in platform_results],
            "before_after_comparison": comparison,
            "weak_points": weak_points,
            "suggestions": suggestions,
            "diagnosis_cross_ref": _cross_ref_diagnosis(diagnosis_result, components) if diagnosis_result else None,
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
        """方案匹配度评测 — 句级细粒度语义匹配（区别于品牌召回的段落级检索）"""
        import re
        if not text or not text.strip():
            return {"average": 0, "scores": []}

        # 句级切分：按句号、分号、问号、感叹号、换行拆分
        sentences = re.split(r'[。；;！!？?\n]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) >= 10]
        if not sentences:
            sentences = [text.strip()]

        sent_vecs = self.embedding_svc.encode(sentences)
        query_vecs = self.embedding_svc.encode_queries(questions)

        scores = []
        for q_vec in query_vecs:
            similarities = self.embedding_svc.batch_similarity(q_vec, sent_vecs)
            # 取 top-3 句子相似度均值，比单句 max 更稳定
            top_n = sorted(similarities, reverse=True)[:3]
            score = float(np.mean(top_n)) if top_n else 0
            scores.append(score)

        avg = np.mean(scores) * 100 if scores else 0
        return {"average": round(float(avg), 1), "scores": [round(float(s), 2) for s in scores]}

    def _evaluate_semantic_alignment(self, questions: list[str], text: str) -> dict:
        """语义对齐度评测 — 文档级语义向量与行业 query 集的余弦相似度

        衡量内容在 AI 语义空间中与目标用户查询的对齐程度。
        与 solution_match 的区别：solution_match 是句子级精匹配，
        semantic_alignment 是文档级整体语义对齐，模拟 AI 平台的
        embedding-based retrieval 决策。
        """
        if not text or not text.strip():
            return {"average": 0, "scores": []}

        # 文档级编码：整篇文本作为一个语义单元
        text_vec = self.embedding_svc.encode([text])[0]
        # 行业 query 编码（与检索时的 question encoding 一致）
        query_vecs = self.embedding_svc.encode_queries(questions)

        # 文档向量与所有 query 向量的余弦相似度
        similarities = self.embedding_svc.batch_similarity(text_vec, query_vecs)
        scores = [float(s) for s in similarities]

        avg = np.mean(scores) * 100 if scores else 0
        return {"average": round(float(avg), 1), "scores": [round(float(s), 2) for s in scores]}

    def _evaluate_rag_retrievability(
        self, questions: list[str], text: str, enterprise_name: str = ""
    ) -> dict:
        """RAG可检索性评测 — 模拟 RAG 场景检查内容的可检索性和自包含性

        1. 将文本切片为 200-300 字的 RAG 单元
        2. 检索：用问题检索 top-3 chunk，计算平均检索相似度
        3. 自包含性：检查每个 chunk 是否包含企业名 + 关键信息（独立可引用）
        """
        import re
        from app.utils.text_splitter import default_splitter

        if not text or not text.strip():
            return {"average": 0, "scores": [], "chunk_self_contained_ratio": 0}

        # 切分为 RAG 友好的 chunk (200-300 字)
        chunks = default_splitter.split(text)
        if not chunks:
            chunks = [text]

        # 编码 chunk 并检索
        chunk_vecs = self.embedding_svc.encode(chunks)
        query_vecs = self.embedding_svc.encode_queries(questions)

        retrieval_scores = []
        for q_vec in query_vecs:
            sims = self.embedding_svc.batch_similarity(q_vec, chunk_vecs)
            top3 = sorted(sims, reverse=True)[:3]
            retrieval_scores.append(float(np.mean(top3)))

        avg_retrieval = np.mean(retrieval_scores) * 100 if retrieval_scores else 0

        # 自包含性检查：每个 chunk 是否独立可被引用
        self_contained_count = 0
        for chunk in chunks:
            score = 0
            # 检查1：包含企业名（实体锚定）
            if enterprise_name and enterprise_name in chunk:
                score += 0.4
            # 检查2：包含量化数据
            if re.search(r'\d+个|\d+项|\d+套|\d+年|\d+%|\d+\.\d+\s*(mm|cm|m|km)', chunk):
                score += 0.3
            # 检查3：长度适合 RAG 检索（150-400 字）
            chunk_len = len(chunk)
            if 150 <= chunk_len <= 400:
                score += 0.3
            elif 80 <= chunk_len <= 600:
                score += 0.15
            if score >= 0.5:
                self_contained_count += 1

        chunk_ratio = self_contained_count / len(chunks) if chunks else 0

        # 综合得分 = 检索相似度(50%) + 自包含chunk占比(50%)
        avg = avg_retrieval * 0.5 + chunk_ratio * 100 * 0.5

        return {
            "average": round(float(avg), 1),
            "scores": [round(float(s), 2) for s in retrieval_scores],
            "chunk_self_contained_ratio": round(float(chunk_ratio), 2),
            "total_chunks": len(chunks),
            "self_contained_chunks": self_contained_count,
        }

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
            cache_key = f"citation:{hashlib.md5((question + text).encode()).hexdigest()}"
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
                resp = await async_retry(self.llm.chat, messages, temperature=self._temp_advantage, max_tokens=512)
                # 从回复中提取评分
                score = self._extract_score(resp.content)
                if score is not None:
                    scores.append(score)
                    eval_cache.set(cache_key, score)
            except Exception as e:
                logger.warning(f"LLM评测失败，跳过该问题: {e}")
                # 不注入假分数，跳过失败的问题让结果基于实际成功评测的数据

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
        logger.warning(f"_extract_score 无法从LLM回复中提取评分，原始回复前120字符: {response[:120]}")
        return None  # 无法解析时不捏造分数

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

    def _calculate_overall_v2(self, components: dict) -> float:
        """计算综合评分（8维加权，与流式评测一致，权重统一从 DimensionRegistry 读取）"""
        from app.core.eval_dimensions import DEFAULT_WEIGHTS
        weights = {k: v / 100.0 for k, v in DEFAULT_WEIGHTS.items()}

        # 仅使用有实际值的维度计算（排除 None，即未评测的维度）
        available = {k: v for k, v in components.items() if v is not None}
        if not available:
            return 0.0

        total_weight = sum(weights.get(k, 0) for k in available)
        if total_weight == 0:
            return 0.0

        overall = sum(available.get(k, 0) * (weights.get(k, 0) / total_weight) for k in available)

        source_consistency = components.get("source_consistency")
        if source_consistency is not None and source_consistency < 30:
            overall = min(overall, 50.0)

        return overall

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

        # 空文本/过短文本校验
        if not optimized_text or len(optimized_text.strip()) < 50:
            yield _sse_event("eval_error", session.session_id, "error",
                             {"error": "输入文本过短（少于50字），无法进行有效评测"}, 0)
            return

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
        eeat_result = None
        real_citation_result = None
        source_consistency_result = None

        for phase in phase_order:
            if session.cancelled:
                await session.skip_phase(phase)
                yield _sse_event("phase_skipped", session.session_id, phase.value,
                                 {"reason": "cancelled"}, session.overall_progress)
                continue

            await session.start_phase(phase)

            try:
                if phase == EvalPhase.GENERATING_QUESTIONS:
                    questions = self._generate_questions(sandtable_type, user_roles, custom_questions or [])
                    result = {"questions": questions, "count": len(questions)}
                    await session.complete_phase(phase, result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     result, session.overall_progress)

                elif phase == EvalPhase.BRAND_RECALL:
                    if "brand_recall" not in enabled_keys:
                        await session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": "dimension_disabled"}, session.overall_progress)
                        continue
                    self._build_text_index(optimized_text, sandtable_type)
                    brand_result = self._evaluate_brand_recall(questions, optimized_text)
                    await session.complete_phase(phase, brand_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     brand_result, session.overall_progress)

                elif phase == EvalPhase.SOLUTION_MATCH:
                    if "solution_match" not in enabled_keys:
                        await session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": "dimension_disabled"}, session.overall_progress)
                        continue
                    solution_result = self._evaluate_solution_match(questions, optimized_text)
                    await session.complete_phase(phase, solution_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     solution_result, session.overall_progress)

                elif phase == EvalPhase.SEMANTIC_ALIGNMENT:
                    if "semantic_alignment" not in enabled_keys:
                        await session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": "dimension_disabled"}, session.overall_progress)
                        continue
                    semantic_result = self._evaluate_semantic_alignment(questions, optimized_text)
                    await session.complete_phase(phase, semantic_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     semantic_result, session.overall_progress)

                elif phase == EvalPhase.ADVANTAGE_CITATION:
                    if "advantage_citation" not in enabled_keys or not self.llm:
                        reason = "no_llm" if not self.llm else "dimension_disabled"
                        await session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": reason}, session.overall_progress)
                        continue
                    advantage_result = await self._evaluate_advantage_citation(questions, optimized_text, sandtable_type)
                    await session.complete_phase(phase, advantage_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     advantage_result, session.overall_progress)

                elif phase == EvalPhase.REAL_CITATION:
                    if "real_citation" not in enabled_keys or not self.llm:
                        reason = "no_llm" if not self.llm else "dimension_disabled"
                        await session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": reason}, session.overall_progress)
                        continue
                    real_citation_result = await self._evaluate_real_citation(questions, optimized_text, sandtable_type)
                    await session.complete_phase(phase, real_citation_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     real_citation_result, session.overall_progress)

                elif phase == EvalPhase.RAG_RETRIEVABILITY:
                    if "rag_retrievability" not in enabled_keys:
                        await session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": "dimension_disabled"}, session.overall_progress)
                        continue
                    rag_result = self._evaluate_rag_retrievability(questions, optimized_text, enterprise_name)
                    await session.complete_phase(phase, rag_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     rag_result, session.overall_progress)

                elif phase == EvalPhase.STRUCTURE_QUALITY:
                    if "structure_quality" not in enabled_keys or not self.llm:
                        reason = "no_llm" if not self.llm else "dimension_disabled"
                        await session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": reason}, session.overall_progress)
                        continue
                    structure_result = await self._evaluate_structure(optimized_text, sandtable_type)
                    await session.complete_phase(phase, structure_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     structure_result, session.overall_progress)

                elif phase == EvalPhase.DIFFERENTIATION:
                    if "differentiation" not in enabled_keys or not self.llm:
                        reason = "no_llm" if not self.llm else "dimension_disabled"
                        await session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": reason}, session.overall_progress)
                        continue
                    differentiation_result = await self._evaluate_differentiation(optimized_text, sandtable_type)
                    await session.complete_phase(phase, differentiation_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     differentiation_result, session.overall_progress)

                elif phase == EvalPhase.EEAT_CHECK:
                    if "eeat_score" not in enabled_keys or not self.llm:
                        reason = "no_llm" if not self.llm else "dimension_disabled"
                        await session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": reason}, session.overall_progress)
                        continue
                    eeat_result = await self._evaluate_eeat(
                        optimized_text, sandtable_type,
                        enterprise_name=get_enterprise_name(),
                    )
                    await session.complete_phase(phase, eeat_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     eeat_result, session.overall_progress)

                elif phase == EvalPhase.SOURCE_CHECK:
                    if "source_consistency" not in enabled_keys or not self.llm:
                        reason = "no_llm" if not self.llm else "dimension_disabled"
                        await session.skip_phase(phase)
                        yield _sse_event("phase_skipped", session.session_id, phase.value,
                                         {"reason": reason}, session.overall_progress)
                        continue
                    source_consistency_result = await self._evaluate_source_consistency(
                        optimized_text, sandtable_type,
                        enterprise_name=get_enterprise_name(),
                        enterprise_location=get_enterprise_location(),
                        original_text=original_text,
                    )
                    await session.complete_phase(phase, source_consistency_result)
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     source_consistency_result, session.overall_progress)

                elif phase == EvalPhase.COMPREHENSIVE:
                    components = {}
                    if brand_result and "brand_recall" in enabled_keys:
                        components["brand_recall"] = brand_result.get("average", 0)
                    if solution_result and "solution_match" in enabled_keys:
                        components["solution_match"] = solution_result.get("average", 0)
                    if semantic_result and "semantic_alignment" in enabled_keys:
                        components["semantic_alignment"] = semantic_result.get("average", 0)
                    if advantage_result and "advantage_citation" in enabled_keys:
                        components["advantage_citation"] = advantage_result.get("average", 0)
                    if real_citation_result and "real_citation" in enabled_keys:
                        components["real_citation"] = real_citation_result.get("average", 0)
                    if rag_result and "rag_retrievability" in enabled_keys:
                        components["rag_retrievability"] = rag_result.get("average", 0)
                    if structure_result and "structure_quality" in enabled_keys:
                        components["structure_quality"] = structure_result.get("average", 0)
                    if differentiation_result and "differentiation" in enabled_keys:
                        components["differentiation"] = differentiation_result.get("average", 0)
                    if eeat_result and "eeat_score" in enabled_keys:
                        components["eeat_score"] = eeat_result.get("average", 0)
                    if source_consistency_result and "source_consistency" in enabled_keys:
                        components["source_consistency"] = source_consistency_result.get("average", 0)

                    overall = 0.0
                    for key, score in components.items():
                        overall += score * weight_map.get(key, 0)

                    # 信源一致性硬门槛：信源不可靠时综合分封顶50分
                    source_consistency_score = components.get("source_consistency", 100)
                    if source_consistency_score < 30:
                        overall = min(overall, 50.0)

                    comparison = None
                    if original_text:
                        comparison = await self._compare_before_after(original_text, optimized_text, questions)

                    all_scores = {**components, "overall": overall}
                    weak_points, suggestions = self._diagnose_v2(
                        all_scores, sandtable_type,
                        platform_id=session.platform_id if hasattr(session, 'platform_id') else None,
                    )

                    comprehensive_result = {
                        "overall_score": round(overall, 1),
                        "dimension_scores": components,
                        "weights_used": {k: round(v * 100, 1) for k, v in weight_map.items()},
                        "before_after_comparison": comparison,
                        "weak_points": weak_points,
                        "suggestions": suggestions,
                    }
                    await session.complete_phase(phase, comprehensive_result)
                    await session.mark_completed(round(overall, 1))
                    yield _sse_event("phase_complete", session.session_id, phase.value,
                                     comprehensive_result, session.overall_progress)
                    yield _sse_event("eval_complete", session.session_id, "done",
                                     comprehensive_result, 100.0)

            except Exception as e:
                logger.exception(f"Session {session.session_id}: phase {phase.value} failed")
                await session.fail_phase(phase, str(e))
                yield _sse_event("phase_failed", session.session_id, phase.value,
                                 {"error": str(e)}, session.overall_progress)
                if phase == EvalPhase.COMPREHENSIVE:
                    await session.mark_failed()
                    yield _sse_event("eval_error", session.session_id, "error",
                                     {"error": str(e)}, session.overall_progress)

    async def _evaluate_structure(self, text: str, sandtable_type: SandtableType) -> dict:
        """LLM评估结构化程度"""
        if not self.llm:
            return {"average": 0, "details": [], "reason": "no_llm"}

        from app.prompts.evaluation import STRUCTURE_EVAL_SYSTEM, STRUCTURE_EVAL_USER

        cache_key = f"structure:{hashlib.md5(text.encode()).hexdigest()}"
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
        resp = await async_retry(self.llm.chat, messages, temperature=self._temp_structure, max_tokens=512)
        score = self._extract_score(resp.content)
        if score is None:
            score = 0.0
        result = {"average": score, "analysis": resp.content, "details": [score]}
        eval_cache.set(cache_key, result)
        return result

    async def _evaluate_differentiation(self, text: str, sandtable_type: SandtableType) -> dict:
        """LLM评估差异化程度"""
        if not self.llm:
            return {"average": 0, "details": [], "reason": "no_llm"}

        from app.prompts.evaluation import DIFFERENTIATION_EVAL_SYSTEM, DIFFERENTIATION_EVAL_USER

        cache_key = f"diff:{hashlib.md5(text.encode()).hexdigest()}"
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
        resp = await async_retry(self.llm.chat, messages, temperature=self._temp_differentiation, max_tokens=512)
        score = self._extract_score(resp.content)
        if score is None:
            score = 0.0
        result = {"average": score, "analysis": resp.content, "details": [score]}
        eval_cache.set(cache_key, result)
        return result

    async def _evaluate_eeat(
        self,
        text: str,
        sandtable_type: SandtableType,
        enterprise_name: str | None = None,
    ) -> dict:
        """LLM评估E-E-A-T权威度"""
        if enterprise_name is None:
            enterprise_name = get_enterprise_name()
        if not self.llm:
            return {"average": None, "details": [], "reason": "no_llm"}

        cache_key = f"eeat:{hashlib.md5(text.encode()).hexdigest()}"
        cached = eval_cache.get(cache_key)
        if cached is not None:
            return cached

        messages = [
            LLMMessage(role="system", content=EEAT_EVAL_SYSTEM),
            LLMMessage(role="user", content=EEAT_EVAL_USER.format(
                text=text[:3000],
                sandtable_type=sandtable_type.label,
                enterprise_name=enterprise_name,
            )),
        ]
        resp = await async_retry(self.llm.chat, messages, temperature=self._temp_eeat, max_tokens=512)
        score = self._extract_score(resp.content)
        if score is None:
            score = 0.0
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
            cache_key = f"real_cite:{hashlib.md5((q + text).encode()).hexdigest()}"
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
                resp = await async_retry(self.llm.chat, messages, temperature=self._temp_real_citation, max_tokens=512)

                citation_score = self._analyze_citation(resp.content, text)
                # B2B工业内容的引用通常以技术参数/量化数据为主，而非逐字复制品牌名
                # 将有效引用阈值设为 0.2（原 0.3 对工业B2B内容过严）
                cited_flag = citation_score > 0.2
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

        citation_scores = [d.get("citation_score", 0) for d in details]
        avg = sum(citation_scores) / len(citation_scores) if citation_scores else 0
        return {
            "average": round(float(avg), 1),
            "details": details,
            "cited_count": cited,
            "total": len(sample_qs),
        }

    def _analyze_citation(self, answer: str, source_text: str) -> float:
        """分析 LLM 回答中引用的实体是否来自源文本（精度检查，非召回检查）

        原逻辑问题：从源文本提取全部实体，检查单个回答覆盖了多少 → 单个回答永远只能覆盖
        一小部分实体，导致分数系统性偏低（~21分）。

        修正逻辑：从 LLM 回答中提取实体，检查其中多少能在源文本中找到 → 衡量回答的
        "信源忠实度"而非"覆盖度"。如果 LLM 编造了源文本中没有的数据/企业名，会被扣分。
        """
        import re

        # 从回答中提取实体（而非从源文本）
        def _extract_from(text: str):
            core = set()
            data = set()
            tech = set()

            # 核心实体：品牌/企业名
            for m in re.finditer(r'[一-鿿]{2,8}(?:公司|科技|智能|有限公司)', text):
                core.add(m.group())
            brand_variants = get_brand_variants()
            if brand_variants:
                escaped = [re.escape(v) for v in brand_variants]
                brand_pattern = '|'.join(escaped)
                for m in re.finditer(brand_pattern, text):
                    core.add(m.group())

            # 数据实体：量化指标
            for m in re.finditer(r'\d+\+?\s*(?:个|项|套|年|㎡|平方米|公里|人|次|万元|亿|%|以上|余家)', text):
                data.add(m.group())
            for m in re.finditer(r'\d+\+?\s*[一-鿿]{1,4}', text):
                data.add(m.group())
            for m in re.finditer(r'\d+[:：]\d+', text):
                data.add(m.group())

            # 技术实体：术语/产品名
            for m in re.finditer(r'[一-鿿]{2,8}(?:系统|平台|模型|技术|方案|工艺|仿真|沙盘|数据|控制|联动|展示|服务|定制|设计|制造|厂家)', text):
                tech.add(m.group())

            return core, data, tech

        answer_core, answer_data, answer_tech = _extract_from(answer)

        all_answer_entities = answer_core | answer_data | answer_tech
        if not all_answer_entities:
            # 回答中没有可识别实体 → 退化为字符级重叠检查
            source_chars = set(source_text)
            answer_chars = set(answer)
            if not source_chars or not answer_chars:
                return 0.0
            return len(source_chars & answer_chars) / max(len(answer_chars), 1)

        # 加权计分：回答中的实体有多少能在源文本中找到（精度检查）
        core_matched = sum(1 for e in answer_core if e in source_text)
        data_matched = sum(1 for e in answer_data if e in source_text)
        tech_matched = sum(1 for e in answer_tech if e in source_text)

        core_weight = len(answer_core) * 3
        data_weight = len(answer_data) * 2
        tech_weight = len(answer_tech) * 1
        total_weight = core_weight + data_weight + tech_weight

        if total_weight == 0:
            return 0.0

        weighted_matched = core_matched * 3 + data_matched * 2 + tech_matched * 1
        score = weighted_matched / total_weight

        # 源文本中有对应品牌实体 → 加分（说明回答引用了正确的企业信息）
        if answer_core and core_matched >= len(answer_core) * 0.5:
            score = max(score, 0.5)

        return score

    async def _evaluate_source_consistency(
        self,
        text: str,
        sandtable_type: SandtableType,
        enterprise_name: str | None = None,
        enterprise_location: str | None = None,
        dimensions: dict | None = None,
        original_text: str | None = None,
    ) -> dict:
        """信源一致性检查：检测生成文本是否偏离企业信源数据"""
        if enterprise_name is None:
            enterprise_name = get_enterprise_name()
        if enterprise_location is None:
            enterprise_location = get_enterprise_location()
        if not self.llm:
            return {"average": None, "details": [], "reason": "no_llm"}

        # 无原始文案时，信源一致性检测不可靠——发出警告
        if not original_text or len(original_text.strip()) < 20:
            return {
                "average": None,
                "details": [],
                "reason": "no_original_text",
                "warning": "⚠️ 未提供原始文案，无法进行信源一致性检测。评测将跳过此维度。建议提供优化前的原文以启用防幻觉校验。",
            }

        from app.prompts.evaluation import SOURCE_CHECK_SYSTEM, SOURCE_CHECK_USER

        cache_key = f"source_check:{hashlib.md5((text + (original_text or '')).encode()).hexdigest()}"
        cached = eval_cache.get(cache_key)
        if cached is not None:
            return cached

        # 构建信源概要：企业信息 + 五维信息 + 原始文案（最重要的事实基准）
        dims_summary = f"企业名称：{enterprise_name}\n所在地：{enterprise_location}"
        if dimensions:
            parts = []
            for key, val in dimensions.items():
                if val:
                    items = val if isinstance(val, list) else [str(val)]
                    parts.append(f"- {key}: {'; '.join(items[:3])}")
            if parts:
                dims_summary += "\n" + "\n".join(parts)

        # 原始文案是事实基准的最重要参照
        original_ref = ""
        if original_text:
            original_ref = f"\n\n## 原始素材（事实基准——优化文案中的所有事实性信息应来源于此）\n{original_text[:2000]}"

        try:
            messages = [
                LLMMessage(role="system", content=SOURCE_CHECK_SYSTEM),
                LLMMessage(role="user", content=SOURCE_CHECK_USER.format(
                    text=text[:3000],
                    enterprise_name=enterprise_name,
                    enterprise_location=enterprise_location,
                    input_dimensions=dims_summary,
                    original_reference=original_ref,
                )),
            ]
            resp = await async_retry(self.llm.chat, messages, temperature=self._temp_source, max_tokens=512)
            score = self._extract_score(resp.content)
            if score is not None:
                score = max(0.0, min(100.0, float(score)))
            result = {"average": score, "analysis": resp.content[:500], "details": [score] if score is not None else []}
            eval_cache.set(cache_key, result)
            return result
        except Exception as e:
            logger.warning(f"信源一致性检查失败: {e}")
            return {"average": None, "details": [], "error": str(e)}

    def _diagnose_v2(
        self,
        scores: dict,
        sandtable_type: SandtableType,
        platform_id: str | None = None,
        diagnosis_result: dict | None = None,
    ) -> tuple[list[str], list[str]]:
        """短板诊断 v2 — 平台感知 + 诊断器交叉引用

        Args:
            scores: 各维度得分
            sandtable_type: 沙盘类型
            platform_id: 目标平台ID（如 deepseek/doubao/kimi），用于平台差异化建议
            diagnosis_result: 可选，ContentDiagnoser 的规则诊断结果，用于交叉验证
        """
        weak_points = []
        suggestions = []

        # ── 平台差异化阈值和建议 ──
        platform = platform_id or "base"

        # 平台专属及格线：不同平台对同一维度的容忍度不同
        _thresholds = {
            "brand_recall": 60,
            "solution_match": 60,
            "advantage_citation": 60,
            "structure_quality": 55 if platform == "doubao" else 60,  # 豆包：短句结构容忍度高
            "differentiation": 60,
            "real_citation": 55,  # B2B工业内容预期基准（已从60下调，对齐实际LLM引用行为）
            "source_consistency": 60,
            "eeat_score": 55 if platform in ("kimi", "claude") else 60,  # Kimi/Claude对权威度最敏感
        }

        # 平台专属建议模板
        _suggestions = {
            "brand_recall": {
                "deepseek": f'在全文每个自包含RAG单元（200-300字）中嵌入"{get_enterprise_name()}"品牌名和"{get_enterprise_location()}"地域词',
                "doubao": f'在首句和每段开头突出"{get_enterprise_name()}"，使用简短直接的品牌表述',
                "kimi": f'在标题、每个H2首句、FAQ答案首句中重复"{get_enterprise_name()}"全称，确保全文≥5次',
                "base": f'在文案首段和标题中更突出"{get_enterprise_name()}"品牌名和地域标识',
            },
            "structure_quality": {
                "deepseek": "按每200-300字一个自包含信息单元重组内容，确保每个单元有独立的问题+答案+数据",
                "doubao": "将长段落拆分为短段落（≤120字），每句≤30字，使用列表代替叙述段落",
                "kimi": "采用'背景→分析→结论→依据'四层递进结构，每层首句含品牌名",
                "base": "增加清晰的标题层级（H2/H3），使用列表呈现关键信息，控制段落长度",
            },
            "advantage_citation": {
                "deepseek": "每条优势配'参数名：数值（单位）'标准格式的技术指标，便于RAG检索匹配",
                "doubao": "每条优势用≤30字先说结论（对客户的好处），再用≤50字给数据支撑",
                "kimi": "每条优势配合2-3句支撑细节+1个量化数据，形成完整的论证链",
                "base": "将核心优势以独立段落呈现，确保每条优势有具体数据和案例支撑",
            },
            "eeat_score": {
                "deepseek": "补充技术资质认证编号、第三方检测报告引用、项目验收标准等可验证权威信号",
                "doubao": "增加客户好评、项目实拍、本地服务承诺等接地气的信任信号",
                "kimi": "增加资质认证详情（颁发机构+有效期）、行业排名引用、学术论文引用等权威背书",
                "base": "增加企业年限/项目数量（Experience）、技术工艺深度（Expertise）、资质认证（Authoritativeness）",
            },
        }

        # ── 遍历各维度 ──
        dim_labels = {
            "brand_recall": "品牌召回率",
            "solution_match": "方案匹配度",
            "advantage_citation": "优势采信率",
            "structure_quality": "结构化程度",
            "differentiation": "差异化程度",
            "real_citation": "真实采信率",
            "source_consistency": "信源一致性",
            "eeat_score": "E-E-A-T权威度",
        }

        has_weakness = False
        for key, label in dim_labels.items():
            score = scores.get(key, 100)
            threshold = _thresholds.get(key, 60)
            if score < threshold:
                has_weakness = True
                # 优先使用平台专属建议，否则用通用建议
                platform_suggestions = _suggestions.get(key, {})
                suggest = platform_suggestions.get(platform, platform_suggestions.get("base", f"建议提升{label}"))
                weak_points.append(f"{label}偏低（{score}分，及格线{threshold}分）")
                suggestions.append(f"[{platform}] {suggest}")

        # ── 诊断器交叉引用 ──
        cross_ref = _cross_ref_diagnosis(diagnosis_result, scores)
        if cross_ref:
            if cross_ref.get("confirmed"):
                for item in cross_ref["confirmed"]:
                    weak_points.append(f"🔗 诊断器交叉确认: {item}")
            if cross_ref.get("contradictions"):
                for item in cross_ref["contradictions"]:
                    weak_points.append(f"⚠ 诊断器与评测结果矛盾: {item}")

        if not has_weakness:
            weak_points.append("各项指标表现良好，暂无明显短板")
            suggestions.append(f"[{platform}] 持续监控AI平台算法更新，定期迭代优化文案")

        # ── 信源一致性严重警告 ──
        source_score = scores.get("source_consistency", 100)
        if source_score is not None and source_score < 30:
            weak_points.insert(0,
                f"🚨 信源一致性严重偏低（{source_score}分）：优化后文案包含大量信源数据中不存在的信息，"
                "存在AI编造风险，当前评测得分的参考价值有限"
            )
            suggestions.insert(0,
                f"[{platform}] 返回GEO工坊重新优化，确保五维信息完整准确，"
                "不要编造量化数据/客户案例/认证证书"
            )

        # ── 平台特有问题 ──
        if platform == "doubao":
            if scores.get("structure_quality", 100) < 70:
                suggestions.append("[豆包专属] 确认全文80%以上句子≤30字，避免任何营销腔表述")
        elif platform == "deepseek":
            if scores.get("structure_quality", 100) < 70:
                suggestions.append("[DeepSeek专属] 确认FAQs≥5组，所有技术参数使用'参数名：数值（单位）'格式")
        elif platform == "kimi":
            brand_score = scores.get("brand_recall", 100)
            if brand_score < 70:
                suggestions.append("[Kimi专属] 品牌名全文至少出现5次，数据不可泛化（'多年'→具体年数）")

        return weak_points, suggestions


def _cross_ref_diagnosis(diagnosis_result: dict | None, eval_scores: dict) -> dict | None:
    """将诊断器结果与评测结果交叉引用，发现一致性和矛盾"""
    if not diagnosis_result:
        return None

    dims = diagnosis_result.get("dimensions", {})
    if not dims:
        return None

    confirmed = []
    contradictions = []

    # 映射：诊断器维度 → 评测引擎维度
    mapping = {
        "entity_completeness": "brand_recall",
        "structure_quality": "structure_quality",
        "quantified_data": "differentiation",
        "faq_friendliness": "real_citation",
        "source_credibility": "source_consistency",
    }

    for diag_key, eval_key in mapping.items():
        diag_dim = dims.get(diag_key, {})
        diag_score = diag_dim.get("score", 100)
        eval_score = eval_scores.get(eval_key, 100)

        if diag_score < 60 and eval_score < 60:
            confirmed.append(
                f"{diag_key}: 诊断器({diag_score}分)和评测引擎({eval_score}分)一致认为偏低 — "
                f"{diag_dim.get('note', '')}"
            )
        elif diag_score < 40 and eval_score > 70:
            contradictions.append(
                f"{diag_key}: 诊断器评分低({diag_score}分)但评测引擎评分高({eval_score}分)，"
                "可能存在规则诊断遗漏或LLM评测偏差，建议人工复核"
            )
        elif diag_score > 70 and eval_score < 40:
            contradictions.append(
                f"{diag_key}: 诊断器评分高({diag_score}分)但评测引擎评分低({eval_score}分)，"
                "LLM评测可能检测到了规则诊断无法覆盖的深层问题"
            )

    return {
        "confirmed": confirmed,
        "contradictions": contradictions,
        "diagnosis_overall": diagnosis_result.get("overall_score", "N/A"),
    }
