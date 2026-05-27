# AI评测中心"开始评测"模块重构 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构AI评测中心"开始评测"功能，支持7阶段可中断SSE流式评测、5维度可配置、流水线/独立两种模式共存。

**Architecture:** 后端新增 EvalSession 状态机管理评测生命周期，DimensionRegistry 注册5个维度并绑定计算方法，AIEvaluator 改为 async generator 逐阶段产出 SSE 事件。前端 EvaluationCenter.vue 彻底重写为配置面板+进度结果区布局，通过 EventSource 实时接收阶段事件。

**Tech Stack:** Python FastAPI + SSE (Server-Sent Events), Vue 3 + Element Plus + ECharts (雷达图), Pinia 状态管理

---

## 文件结构

```
Backend (新增/修改):
├── backend/app/models/enums.py          — 修改: 新增 EvalPhase, EvalPhaseStatus
├── backend/app/models/schemas.py        — 修改: 新增维度/会话/SSE事件 schema
├── backend/app/core/eval_dimensions.py  — 新增: 5维度注册表
├── backend/app/core/eval_session.py     — 新增: 评测会话状态机
├── backend/app/core/evaluator.py        — 修改: 增强为分阶段 async generator
├── backend/app/prompts/evaluation.py    — 修改: 新增结构化+差异化 prompt
├── backend/app/api/evaluation.py        — 修改: 新增 start/cancel/session/dimensions/history

Frontend (修改):
├── frontend/src/api/index.js            — 修改: 新增 SSE/cancel/history/dimensions API
├── frontend/src/stores/geo.js           — 修改: 新增评测会话/进度状态
├── frontend/src/views/EvaluationCenter.vue — 重写: 完全新的配置+结果布局
```

---

### Task 1: 后端枚举扩展

**Files:**
- Modify: `geo-optimizer/backend/app/models/enums.py`

- [ ] **Step 1: 新增 EvalPhase 和 EvalPhaseStatus 枚举**

在 `enums.py` 文件末尾追加：

```python
class EvalPhase(str, Enum):
    """评测阶段"""
    GENERATING_QUESTIONS = "generating_questions"
    BRAND_RECALL = "brand_recall"
    SOLUTION_MATCH = "solution_match"
    ADVANTAGE_CITATION = "advantage_citation"
    STRUCTURE_QUALITY = "structure_quality"
    DIFFERENTIATION = "differentiation"
    COMPREHENSIVE = "comprehensive"

    @property
    def label(self) -> str:
        labels = {
            "generating_questions": "生成评测问题",
            "brand_recall": "品牌召回率",
            "solution_match": "方案匹配度",
            "advantage_citation": "优势采信率",
            "structure_quality": "结构化程度",
            "differentiation": "差异化程度",
            "comprehensive": "综合评分",
        }
        return labels[self.value]

    @property
    def order(self) -> int:
        """阶段执行顺序"""
        order_map = {
            "generating_questions": 0,
            "brand_recall": 1,
            "solution_match": 2,
            "advantage_citation": 3,
            "structure_quality": 4,
            "differentiation": 5,
            "comprehensive": 6,
        }
        return order_map[self.value]


class EvalPhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

- [ ] **Step 2: 验证枚举可用**

Run: `cd geo-optimizer/backend && python -c "from app.models.enums import EvalPhase, EvalPhaseStatus; print(list(EvalPhase)); print(EvalPhase.GENERATING_QUESTIONS.label); print(EvalPhase.BRAND_RECALL.order)"`

Expected: 7 phases printed, labels and order correct.

- [ ] **Step 3: Commit**

```bash
git add geo-optimizer/backend/app/models/enums.py
git commit -m "feat: add EvalPhase and EvalPhaseStatus enums for phased evaluation"
```

---

### Task 2: 后端 Schema 扩展

**Files:**
- Modify: `geo-optimizer/backend/app/models/schemas.py`

- [ ] **Step 1: 新增维度配置、会话状态、SSE事件的 Pydantic schema**

在 `schemas.py` 文件末尾追加：

```python
from .enums import EvalPhase, EvalPhaseStatus

# ── 评测维度配置 ──

class EvalDimensionConfig(BaseModel):
    key: str = Field(..., description="维度key")
    label: str = Field(..., description="维度中文名")
    requires_llm: bool = Field(default=False)
    weight: float = Field(default=20.0, ge=0, le=100)
    enabled: bool = Field(default=True)

class EvalStartRequest(BaseModel):
    optimized_text: str = Field(..., max_length=50000)
    original_text: str | None = Field(default=None, max_length=50000)
    sandtable_type: str = Field(default="smart_traffic")
    platforms: list[str] = Field(default_factory=lambda: ["deepseek"])
    user_roles: list[str] = Field(default_factory=lambda: ["b_end_procurement"])
    custom_questions: list[str] = Field(default_factory=list)
    dimensions: list[EvalDimensionConfig] = Field(default_factory=list)
    mode: str = Field(default="pipeline")  # "pipeline" | "standalone"

class EvalPhaseResult(BaseModel):
    phase: EvalPhase
    status: EvalPhaseStatus
    result: dict | None = None
    error: str | None = None

class EvalSessionResponse(BaseModel):
    session_id: str
    status: str  # running | completed | cancelled | failed
    phases: dict[str, EvalPhaseResult]
    overall_progress: float = 0.0
    overall_score: float | None = None
    created_at: str = ""

class EvalHistoryItem(BaseModel):
    session_id: str
    sandtable_type: str
    overall_score: float | None = None
    created_at: str = ""
    mode: str = "pipeline"
```

- [ ] **Step 2: 验证 schema 可导入**

Run: `cd geo-optimizer/backend && python -c "from app.models.schemas import EvalDimensionConfig, EvalStartRequest, EvalSessionResponse; print(EvalDimensionConfig(key='test', label='测试')); print('OK')"`

Expected: OK

- [ ] **Step 3: Commit**

```bash
git add geo-optimizer/backend/app/models/schemas.py
git commit -m "feat: add evaluation dimension, session, and SSE event schemas"
```

---

### Task 3: 维度注册表

**Files:**
- Create: `geo-optimizer/backend/app/core/eval_dimensions.py`

- [ ] **Step 1: 创建 DimensionRegistry**

```python
"""评测维度注册表 — 5维度定义与计算方法映射"""

from __future__ import annotations
from typing import Callable, Coroutine, Any
from app.models.enums import EvalPhase

# 维度计算函数签名
ComputeFunc = Callable[..., Coroutine[Any, Any, dict]]


class EvalDimension:
    """单个评测维度定义"""
    def __init__(
        self,
        key: str,
        label: str,
        phase: EvalPhase,
        requires_llm: bool,
        compute: ComputeFunc | None = None,
    ):
        self.key = key
        self.label = label
        self.phase = phase
        self.requires_llm = requires_llm
        self.compute = compute

    def to_config(self, weight: float = 20.0, enabled: bool = True) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "requires_llm": self.requires_llm,
            "weight": weight,
            "enabled": enabled,
        }


class DimensionRegistry:
    """5维度注册表"""

    DIMENSIONS: dict[str, EvalDimension] = {}

    @classmethod
    def register(cls, dim: EvalDimension):
        cls.DIMENSIONS[dim.key] = dim

    @classmethod
    def get(cls, key: str) -> EvalDimension | None:
        return cls.DIMENSIONS.get(key)

    @classmethod
    def list_all(cls) -> list[EvalDimension]:
        return list(cls.DIMENSIONS.values())

    @classmethod
    def list_enabled(cls, configs: list[dict]) -> list[EvalDimension]:
        """根据配置返回启用的维度列表"""
        enabled_keys = {c["key"] for c in configs if c.get("enabled", True)}
        return [d for d in cls.list_all() if d.key in enabled_keys]

    @classmethod
    def get_phases_from_configs(cls, configs: list[dict]) -> list[EvalPhase]:
        """从维度配置推导需要执行的阶段列表（有序、去重）"""
        dims = cls.list_enabled(configs)
        phases = list(dict.fromkeys(d.phase for d in dims))
        phases.append(EvalPhase.GENERATING_QUESTIONS)  # 问题生成总是需要
        phases.append(EvalPhase.COMPREHENSIVE)          # 综合评分总是需要
        return sorted(set(phases), key=lambda p: p.order)


# ── 注册5个维度 ──

DimensionRegistry.register(EvalDimension(
    key="brand_recall",
    label="品牌召回率",
    phase=EvalPhase.BRAND_RECALL,
    requires_llm=False,
))

DimensionRegistry.register(EvalDimension(
    key="solution_match",
    label="方案匹配度",
    phase=EvalPhase.SOLUTION_MATCH,
    requires_llm=False,
))

DimensionRegistry.register(EvalDimension(
    key="advantage_citation",
    label="优势采信率",
    phase=EvalPhase.ADVANTAGE_CITATION,
    requires_llm=True,
))

DimensionRegistry.register(EvalDimension(
    key="structure_quality",
    label="结构化程度",
    phase=EvalPhase.STRUCTURE_QUALITY,
    requires_llm=True,
))

DimensionRegistry.register(EvalDimension(
    key="differentiation",
    label="差异化程度",
    phase=EvalPhase.DIFFERENTIATION,
    requires_llm=True,
))
```

- [ ] **Step 2: 验证注册表**

Run: `cd geo-optimizer/backend && python -c "from app.core.eval_dimensions import DimensionRegistry; dims = DimensionRegistry.list_all(); print([d.key for d in dims]); phases = DimensionRegistry.get_phases_from_configs([d.to_config() for d in dims]); print([p.value for p in phases])"`

Expected: 5 dimension keys printed, 7 phases printed (including generating_questions and comprehensive).

- [ ] **Step 3: Commit**

```bash
git add geo-optimizer/backend/app/core/eval_dimensions.py
git commit -m "feat: add DimensionRegistry with 5 evaluation dimensions"
```

---

### Task 4: 评测 Prompt 扩展

**Files:**
- Modify: `geo-optimizer/backend/app/prompts/evaluation.py`

- [ ] **Step 1: 新增结构化程度 + 差异化程度 Prompt**

在文件末尾追加：

```python
# ── 结构化程度评测 ──

STRUCTURE_EVAL_SYSTEM = """你是一个AI内容可提取性评测专家。你的任务是评估文本的结构化程度——即AI模型从该文本中提取关键信息的难易程度。

评估维度：
1. **标题层级**：是否有清晰的标题/副标题层次（H1/H2/H3等效结构）
2. **段落组织**：段落长度是否合理、主题是否聚焦、是否有清晰的开头-主体-结尾
3. **列表使用**：关键信息是否以列表/条目形式呈现，方便AI直接提取
4. **信息密度**：是否有大量冗余或无关内容
5. **可扫描性**：AI能否在2000 tokens内定位到核心信息

给出0-100的综合评分并简要说明理由。"""

STRUCTURE_EVAL_USER = """待评估文本：
---
{text}
---

沙盘类型：{sandtable_type}

请评估这段文本的结构化程度，给出0-100的评分：

评分：[0-100]
优点：[结构化做得好的地方]
待改进：[结构化的不足之处]"""


# ── 差异化程度评测 ──

DIFFERENTIATION_EVAL_SYSTEM = """你是一个AI内容差异化评测专家。你的任务是评估文本的差异化程度——即该文本与同类竞品内容相比，是否包含独特的、难以被替代的信息。

评估维度：
1. **独特性**：文本中是否有独一无二的案例、数据、技术细节或工艺描述
2. **品牌标识**：品牌名称、地域标识、联系方式是否清晰且分布合理
3. **竞争壁垒**：是否描述了竞品难以复制的优势（专利、资质、案例量级等）
4. **具体程度**：使用模糊形容词（"很好""优秀"）还是有具体数据（"精度0.1mm""交付200+项目"）
5. **记忆点**：是否有让AI和读者容易记住的独特短语或数字

给出0-100的综合评分并简要说明理由。"""

DIFFERENTIATION_EVAL_USER = """待评估文本：
---
{text}
---

沙盘类型：{sandtable_type}

请评估这段文本的差异化程度，给出0-100的评分：

评分：[0-100]
优点：[差异化做得好的地方]
待改进：[可增加差异化的方向]"""
```

- [ ] **Step 2: 验证 prompt 可导入**

Run: `cd geo-optimizer/backend && python -c "from app.prompts.evaluation import STRUCTURE_EVAL_SYSTEM, DIFFERENTIATION_EVAL_SYSTEM; print('OK')"`

Expected: OK

- [ ] **Step 3: Commit**

```bash
git add geo-optimizer/backend/app/prompts/evaluation.py
git commit -m "feat: add structure quality and differentiation evaluation prompts"
```

---

### Task 5: 评测会话状态机

**Files:**
- Create: `geo-optimizer/backend/app/core/eval_session.py`

- [ ] **Step 1: 创建 EvalSession 类**

```python
"""评测会话状态机 — 管理阶段流转、取消、中间结果"""

from __future__ import annotations
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from app.models.enums import EvalPhase, EvalPhaseStatus

logger = logging.getLogger(__name__)

# 全局会话存储（内存）
_sessions: dict[str, "EvalSession"] = {}


class EvalSession:
    """一次完整的评测会话"""

    def __init__(self):
        self.session_id: str = uuid.uuid4().hex[:12]
        self.status: str = "running"  # running | completed | cancelled | failed
        self.phases: dict[EvalPhase, dict] = {}
        self.phase_results: dict[EvalPhase, dict] = {}
        self.overall_progress: float = 0.0
        self.overall_score: float | None = None
        self._cancelled: bool = False
        self._event_queue: asyncio.Queue | None = None
        self.created_at: str = datetime.now(timezone.utc).isoformat()

        # 初始化所有阶段
        for phase in EvalPhase:
            self.phases[phase] = {"status": EvalPhaseStatus.PENDING.value}

        _sessions[self.session_id] = self

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self):
        self._cancelled = True
        logger.info(f"Session {self.session_id}: cancel requested")

    def start_phase(self, phase: EvalPhase):
        self.phases[phase]["status"] = EvalPhaseStatus.RUNNING.value
        self._update_progress()

    def complete_phase(self, phase: EvalPhase, result: dict | None = None):
        self.phases[phase]["status"] = EvalPhaseStatus.COMPLETED.value
        if result is not None:
            self.phase_results[phase] = result
        self._update_progress()

    def skip_phase(self, phase: EvalPhase):
        self.phases[phase]["status"] = EvalPhaseStatus.SKIPPED.value
        self._update_progress()

    def fail_phase(self, phase: EvalPhase, error: str):
        self.phases[phase]["status"] = EvalPhaseStatus.FAILED.value
        self.phases[phase]["error"] = error
        self._update_progress()

    def mark_completed(self, overall_score: float):
        self.status = "completed"
        self.overall_score = overall_score
        self.overall_progress = 100.0

    def mark_failed(self):
        self.status = "failed"

    def mark_cancelled(self):
        self.status = "cancelled"
        for phase in EvalPhase:
            if self.phases[phase]["status"] == EvalPhaseStatus.PENDING.value:
                self.phases[phase]["status"] = EvalPhaseStatus.CANCELLED.value
        self.overall_progress = 100.0

    def _update_progress(self):
        """根据阶段完成情况更新总进度"""
        total = len(EvalPhase)
        completed = sum(
            1 for p in EvalPhase
            if self.phases[p]["status"] in (
                EvalPhaseStatus.COMPLETED.value,
                EvalPhaseStatus.SKIPPED.value,
                EvalPhaseStatus.FAILED.value,
            )
        )
        self.overall_progress = round((completed / total) * 100, 1)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "phases": {
                p.value: {
                    "status": self.phases[p]["status"],
                    "result": self.phase_results.get(p),
                    "error": self.phases[p].get("error"),
                }
                for p in EvalPhase
            },
            "overall_progress": self.overall_progress,
            "overall_score": self.overall_score,
            "created_at": self.created_at,
        }

    @classmethod
    def get(cls, session_id: str) -> "EvalSession | None":
        return _sessions.get(session_id)

    @classmethod
    def list_all(cls) -> list["EvalSession"]:
        return sorted(
            _sessions.values(),
            key=lambda s: s.created_at,
            reverse=True,
        )
```

- [ ] **Step 2: 验证会话状态机**

Run: `cd geo-optimizer/backend && python -c "from app.core.eval_session import EvalSession; s = EvalSession(); print(s.session_id, s.status); s.start_phase(EvalPhase.BRAND_RECALL); print(s.overall_progress); s.complete_phase(EvalPhase.BRAND_RECALL, {'average': 78}); print(s.overall_progress); s.cancel(); print(s.cancelled)"`

Expected: Session ID printed, status "running", progress changes, cancelled=True.

- [ ] **Step 3: Commit**

```bash
git add geo-optimizer/backend/app/core/eval_session.py
git commit -m "feat: add EvalSession state machine for phased evaluation"
```

---

### Task 6: 增强 AIEvaluator — 分阶段 Async Generator

**Files:**
- Modify: `geo-optimizer/backend/app/core/evaluator.py`

This is the core change. The evaluator becomes an async generator that yields SSE events.

- [ ] **Step 1: 重构 AIEvaluator.evaluate 为 async generator**

将现有 `evaluator.py` 中的 `evaluate` 方法替换为 `evaluate_stream`，保留原有方法作为兼容层。同时新增结构化+差异化评分方法。

**替换/新增的关键方法：**

在 `AIEvaluator` 类中新增 `evaluate_stream` 方法（保留原有 `evaluate` 做兼容包装）：

```python
async def evaluate_stream(
    self,
    session: "EvalSession",
    optimized_text: str,
    sandtable_type: SandtableType,
    dimension_configs: list[dict],
    original_text: str | None = None,
    user_roles: list[UserRole] | None = None,
    custom_questions: list[str] | None = None,
):
    """分阶段流式评测 — async generator，逐阶段 yield SSE 数据"""
    from app.core.eval_dimensions import DimensionRegistry
    from app.core.eval_session import EvalPhaseStatus

    user_roles = user_roles or list(UserRole)
    phase_order = DimensionRegistry.get_phases_from_configs(dimension_configs)
    phase_order.sort(key=lambda p: p.order)

    # 识别哪些维度被启用
    enabled_keys = {c["key"] for c in dimension_configs if c.get("enabled", True)}
    # 获取权重映射
    weight_map = {c["key"]: c.get("weight", 20.0) for c in dimension_configs if c.get("enabled", True)}

    # 重新归一化权重
    total_w = sum(weight_map.values())
    if total_w > 0:
        weight_map = {k: v / total_w for k, v in weight_map.items()}

    questions = []
    brand_result = None
    solution_result = None
    advantage_result = None
    structure_result = None
    differentiation_result = None

    for phase in phase_order:
        # 检查取消
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
                    session.skip_phase(phase)
                    yield _sse_event("phase_skipped", session.session_id, phase.value,
                                     {"reason": "dimension_disabled" if "advantage_citation" not in enabled_keys else "no_llm"},
                                     session.overall_progress)
                    continue
                advantage_result = await self._evaluate_advantage_citation(questions, optimized_text, sandtable_type)
                session.complete_phase(phase, advantage_result)
                yield _sse_event("phase_complete", session.session_id, phase.value,
                                 advantage_result, session.overall_progress)

            elif phase == EvalPhase.STRUCTURE_QUALITY:
                if "structure_quality" not in enabled_keys or not self.llm:
                    session.skip_phase(phase)
                    yield _sse_event("phase_skipped", session.session_id, phase.value,
                                     {"reason": "dimension_disabled" if "structure_quality" not in enabled_keys else "no_llm"},
                                     session.overall_progress)
                    continue
                structure_result = await self._evaluate_structure(optimized_text, sandtable_type)
                session.complete_phase(phase, structure_result)
                yield _sse_event("phase_complete", session.session_id, phase.value,
                                 structure_result, session.overall_progress)

            elif phase == EvalPhase.DIFFERENTIATION:
                if "differentiation" not in enabled_keys or not self.llm:
                    session.skip_phase(phase)
                    yield _sse_event("phase_skipped", session.session_id, phase.value,
                                     {"reason": "dimension_disabled" if "differentiation" not in enabled_keys else "no_llm"},
                                     session.overall_progress)
                    continue
                differentiation_result = await self._evaluate_differentiation(optimized_text, sandtable_type)
                session.complete_phase(phase, differentiation_result)
                yield _sse_event("phase_complete", session.session_id, phase.value,
                                 differentiation_result, session.overall_progress)

            elif phase == EvalPhase.COMPREHENSIVE:
                # 加权综合评分
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

                overall = 0.0
                for key, score in components.items():
                    overall += score * weight_map.get(key, 0)

                # 前后对比
                comparison = None
                if original_text:
                    comparison = await self._compare_before_after(original_text, optimized_text, questions)

                # 短板诊断
                all_scores = {**components,
                    "overall": overall}
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
            # 对于非关键阶段的失败，继续执行
            if phase == EvalPhase.COMPREHENSIVE:
                session.mark_failed()
                yield _sse_event("eval_error", session.session_id, "error",
                                 {"error": str(e)}, session.overall_progress)
```

**新增结构化评测方法：**

```python
async def _evaluate_structure(self, text: str, sandtable_type: SandtableType) -> dict:
    """LLM评估结构化程度"""
    if not self.llm:
        return {"average": 0, "details": [], "reason": "no_llm"}

    from app.prompts.evaluation import STRUCTURE_EVAL_SYSTEM, STRUCTURE_EVAL_USER
    from app.utils.retry import async_retry
    from app.utils.cache import eval_cache

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
    from app.utils.retry import async_retry
    from app.utils.cache import eval_cache

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
```

**新增诊断方法 v2（支持任意维度组合）：**

```python
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
```

**添加辅助函数到文件顶部：**

```python
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
```

**保留原有 evaluate 方法做兼容：**

在类中保留原有的 `evaluate` 方法不变（已有代码不需要删除），因为它被其他模块（如 reports）引用。

- [ ] **Step 2: 验证 evaluator 可导入**

Run: `cd geo-optimizer/backend && python -c "from app.core.evaluator import AIEvaluator; print(hasattr(AIEvaluator, 'evaluate_stream')); print(hasattr(AIEvaluator, '_evaluate_structure')); print(hasattr(AIEvaluator, '_evaluate_differentiation'))"`

Expected: `True True True` (只要语法正确即可，功能测试在集成时做)

- [ ] **Step 3: Commit**

```bash
git add geo-optimizer/backend/app/core/evaluator.py
git commit -m "feat: add streaming phased evaluation, structure and differentiation scoring"
```

---

### Task 7: 后端 API 路由扩展

**Files:**
- Modify: `geo-optimizer/backend/app/api/evaluation.py`

- [ ] **Step 1: 新增 SSE start、cancel、session、dimensions、history 端点**

将整个文件替换为：

```python
"""AI评测API路由"""

import asyncio
import json
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.models.schemas import (
    EvalStartRequest, EvalSessionResponse, EvalPhaseResult
)
from app.models.enums import AIPlatform, EvalPhase, EvalPhaseStatus
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

    # 创建会话
    session = EvalSession()

    # 如果用维度配置为空，使用默认的全选
    if not req.dimensions:
        all_dims = DimensionRegistry.list_all()
        has_llm = evaluator.llm is not None
        req.dimensions = [
            d.to_config(enabled=(not d.requires_llm or has_llm))
            for d in all_dims
        ]

    # 转换 sandtable_type
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
                # 检查客户端是否断开
                yield event_str
                await asyncio.sleep(0.01)  # 让出控制权
        except Exception as e:
            logger.exception(f"SSE stream error for session {session.session_id}")
            error_event = f"event: error\ndata: {json.dumps({'session_id': session.session_id, 'error': str(e)}, ensure_ascii=False)}\n\n"
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
    """评测历史列表"""
    sessions = EvalSession.list_all()
    return {
        "items": [
            {
                "session_id": s.session_id,
                "status": s.status,
                "overall_score": s.overall_score,
                "created_at": s.created_at,
            }
            for s in sessions[:50]
        ]
    }


@router.get("/history/{session_id}")
async def get_history_detail(session_id: str):
    """历史评测详情"""
    session = EvalSession.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"评测记录不存在: {session_id}")
    return session.to_dict()


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
```

- [ ] **Step 2: 验证路由可导入**

Run: `cd geo-optimizer/backend && python -c "from app.api.evaluation import router; print([r.path for r in router.routes])"`

Expected: List of routes including `/start`, `/session/{session_id}`, `/cancel/{session_id}`, `/dimensions`, `/history`, `/history/{session_id}`, plus legacy routes.

- [ ] **Step 3: Commit**

```bash
git add geo-optimizer/backend/app/api/evaluation.py
git commit -m "feat: add SSE streaming, cancel, session, dimensions, history API endpoints"
```

---

### Task 8: 前端 API 层扩展

**Files:**
- Modify: `geo-optimizer/frontend/src/api/index.js`

- [ ] **Step 1: 新增评测相关 API 函数**

在 `index.js` 的 AI评测 section 替换为：

```js
// ── AI评测 ──
export const evaluateSemantic = (data) => api.post('/evaluate/semantic', data)
export const getEvalQuestions = () => api.get('/evaluate/questions')
export const quickBrandCheck = (data) => api.post('/evaluate/quick-brand-check', data)

// 新评测 API
export const getEvalDimensions = () => api.get('/evaluate/dimensions')
export const getEvalSession = (id) => api.get(`/evaluate/session/${id}`)
export const cancelEval = (id) => api.post(`/evaluate/cancel/${id}`)
export const getEvalHistory = () => api.get('/evaluate/history')
export const getEvalHistoryDetail = (id) => api.get(`/evaluate/history/${id}`)

/**
 * 创建 SSE 连接开始评测
 * @param {Object} data - 评测请求参数
 * @param {Function} onEvent - 事件回调 (eventType, payload) => void
 * @param {Function} onError - 错误回调 (error) => void
 * @returns {Object} { close, sessionId }
 */
export function startEvalSSE(data, onEvent, onError) {
  const baseUrl = '/api'
  const url = `${baseUrl}/evaluate/start`

  // 使用 fetch POST + 读取 ReadableStream
  const controller = new AbortController()
  let sessionId = null

  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }))
        onError(new Error(err.detail || '评测请求失败'))
        return
      }

      // 从 header 获取 session_id
      sessionId = response.headers.get('X-Session-Id')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        let currentEvent = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6))
              onEvent(currentEvent || payload.event, payload)
            } catch { /* skip bad JSON */ }
            currentEvent = ''
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err)
      }
    })

  return {
    close: () => controller.abort(),
    getSessionId: () => sessionId,
  }
}
```

- [ ] **Step 2: 验证导入**

Run: `cd geo-optimizer/frontend && node -e "import('./src/api/index.js').then(m => console.log(Object.keys(m).join(', ')))"`

Note: This may not work without a build tool. Alternative verification:
Run: `cd geo-optimizer/frontend && grep -c "startEvalSSE\|getEvalDimensions\|cancelEval\|getEvalHistory" src/api/index.js`

Expected: 4 matches.

- [ ] **Step 3: Commit**

```bash
git add geo-optimizer/frontend/src/api/index.js
git commit -m "feat: add SSE evaluation, cancel, dimensions, and history API functions"
```

---

### Task 9: 前端 Store 扩展

**Files:**
- Modify: `geo-optimizer/frontend/src/stores/geo.js`

- [ ] **Step 1: 新增评测会话相关状态**

在 `geo.js` 中追加新的 state 和 actions。在 `return` 语句前添加：

```js
// ── 评测会话状态 ──
const evalSessionId = ref(null)
const evalStatus = ref('idle') // idle | running | completed | cancelled | failed
const evalPhases = ref({})     // { phase_key: { status, result } }
const evalOverallProgress = ref(0)
const evalOverallScore = ref(null)
const evalMode = ref('pipeline') // pipeline | standalone
const evalDimensionConfigs = ref([])

function setEvalSessionId(id) { evalSessionId.value = id }
function setEvalStatus(status) { evalStatus.value = status }
function setEvalPhase(phaseKey, data) {
  evalPhases.value = { ...evalPhases.value, [phaseKey]: data }
}
function setEvalProgress(progress) { evalOverallProgress.value = progress }
function setEvalScore(score) { evalOverallScore.value = score }
function setEvalMode(mode) { evalMode.value = mode }
function setEvalDimensionConfigs(configs) { evalDimensionConfigs.value = configs }

function resetEvalSession() {
  evalSessionId.value = null
  evalStatus.value = 'idle'
  evalPhases.value = {}
  evalOverallProgress.value = 0
  evalOverallScore.value = null
}
```

在 `return` 对象中添加导出：

```js
evalSessionId, evalStatus, evalPhases, evalOverallProgress,
evalOverallScore, evalMode, evalDimensionConfigs,
setEvalSessionId, setEvalStatus, setEvalPhase, setEvalProgress,
setEvalScore, setEvalMode, setEvalDimensionConfigs, resetEvalSession,
```

- [ ] **Step 2: 验证 Store**

Run: `cd geo-optimizer/frontend && npx vite build --mode development 2>&1 | head -20` (will surface syntax errors)

Or quick check:
Run: `cd geo-optimizer/frontend && node -e "const fs = require('fs'); const c = fs.readFileSync('src/stores/geo.js','utf-8'); console.log('Lines:', c.split('\\n').length); console.log('Has evalSessionId:', c.includes('evalSessionId')); console.log('Has resetEvalSession:', c.includes('resetEvalSession'))"`

Expected: Lines count > 100, both includes return true.

- [ ] **Step 3: Commit**

```bash
git add geo-optimizer/frontend/src/stores/geo.js
git commit -m "feat: add evaluation session state to Pinia store"
```

---

### Task 10: 重写 EvaluationCenter.vue

**Files:**
- Modify: `geo-optimizer/frontend/src/views/EvaluationCenter.vue` (完全重写)

- [ ] **Step 1: 创建全新的 EvaluationCenter.vue**

```vue
<template>
  <div class="eval-view">
    <h2 class="page-title">AI评测中心</h2>

    <el-row :gutter="20">
      <!-- 左侧：配置面板 -->
      <el-col :span="8">
        <el-card shadow="never" class="config-card">
          <template #header><span>评测配置</span></template>

          <!-- 评测模式 -->
          <el-form label-position="top" size="default">
            <el-form-item label="评测模式">
              <el-radio-group v-model="evalMode" @change="onModeChange">
                <el-radio-button value="pipeline">流程模式</el-radio-button>
                <el-radio-button value="standalone">独立模式</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <!-- 文本来源 -->
            <el-form-item label="评测文本">
              <template v-if="evalMode === 'pipeline'">
                <el-select v-model="textSource" style="width: 100%" @change="onTextSourceChange">
                  <el-option label="使用优化结果（第一条）" value="rewrite" />
                  <el-option label="手动输入" value="manual" />
                </el-select>
                <el-input
                  v-if="textSource === 'manual'"
                  v-model="evalText"
                  type="textarea"
                  :rows="6"
                  placeholder="粘贴需要评测的文案"
                  style="margin-top: 8px"
                />
                <div v-else class="text-preview">{{ evalText?.substring(0, 200) }}{{ evalText?.length > 200 ? '...' : '' }}</div>
              </template>
              <template v-else>
                <el-input v-model="evalText" type="textarea" :rows="8" placeholder="粘贴需要评测的文案..." />
                <el-button size="small" style="margin-top: 6px" @click="loadHistoryText" :disabled="evalHistory.length === 0">
                  加载历史文本
                </el-button>
              </template>
            </el-form-item>

            <!-- 对比原文 -->
            <el-form-item>
              <el-collapse>
                <el-collapse-item title="对比原文（可选）" name="original">
                  <el-input v-model="originalText" type="textarea" :rows="4" placeholder="粘贴优化前的原文，用于生成前后对比报告" />
                </el-collapse-item>
              </el-collapse>
            </el-form-item>

            <!-- 沙盘类型 -->
            <el-form-item label="沙盘类型">
              <el-select v-model="sandtableType" style="width: 100%">
                <el-option v-for="t in sandtableTypes" :key="t.value" :label="t.label" :value="t.value" />
              </el-select>
            </el-form-item>

            <!-- 目标平台 -->
            <el-form-item label="目标平台">
              <el-select v-model="targetPlatforms" multiple style="width: 100%" placeholder="选择AI平台">
                <el-option v-for="p in availablePlatforms" :key="p.value" :label="p.label" :value="p.value" />
              </el-select>
            </el-form-item>

            <!-- 用户角色 -->
            <el-form-item label="模拟用户角色">
              <el-checkbox-group v-model="userRoles">
                <el-checkbox v-for="r in roleOptions" :key="r.value" :value="r.value">{{ r.label }}</el-checkbox>
              </el-checkbox-group>
            </el-form-item>

            <!-- 评测维度 + 权重 -->
            <el-form-item label="评测维度">
              <div v-for="dim in dimensionConfigs" :key="dim.key" class="dim-row">
                <el-checkbox
                  v-model="dim.enabled"
                  :disabled="dim.requires_llm && !hasLLM"
                  @change="onDimensionChange"
                >
                  {{ dim.label }}
                  <el-tag v-if="dim.requires_llm" size="small" type="info" style="margin-left: 4px">LLM</el-tag>
                </el-checkbox>
                <el-slider
                  v-if="dim.enabled"
                  v-model="dim.weight"
                  :min="0"
                  :max="100"
                  :step="5"
                  size="small"
                  style="width: 120px; margin-left: 12px"
                  @input="onWeightChange"
                />
                <span v-if="dim.enabled" class="dim-weight">{{ dim.weight }}%</span>
              </div>
            </el-form-item>

            <!-- 自定义问题 -->
            <el-form-item label="自定义问题（可选，一行一个）">
              <el-input v-model="customQuestions" type="textarea" :rows="3" placeholder="自定义评测问题..." />
            </el-form-item>
          </el-form>

          <!-- 操作按钮 -->
          <div class="action-buttons">
            <el-button
              type="primary"
              size="large"
              :loading="isRunning"
              @click="startEval"
              style="width: 100%"
              :disabled="!evalText"
            >
              {{ isRunning ? '评测中...' : '开始评测' }}
            </el-button>
            <el-button
              v-if="isRunning"
              type="danger"
              size="default"
              @click="cancelEval"
              style="width: 100%; margin-top: 8px"
            >
              取消评测
            </el-button>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：进度/结果区 -->
      <el-col :span="16">
        <!-- 空状态 -->
        <el-card shadow="never" v-if="evalStatus === 'idle'" class="empty-card">
          <div class="empty-state">
            <el-icon :size="64" color="#c0c4cc"><DataAnalysis /></el-icon>
            <h3>配置评测参数并开始评测</h3>
            <p>系统将分阶段执行评测，实时展示各维度结果</p>
          </div>
        </el-card>

        <!-- 进度区 -->
        <el-card shadow="never" v-if="evalStatus !== 'idle'" class="progress-card">
          <template #header>
            <div class="progress-header">
              <span>评测进度</span>
              <el-tag :type="statusTagType" size="small">{{ statusLabel }}</el-tag>
            </div>
          </template>

          <el-progress
            :percentage="evalOverallProgress"
            :status="evalStatus === 'failed' ? 'exception' : (evalStatus === 'completed' ? 'success' : '')"
            :stroke-width="16"
          />

          <!-- 阶段列表 -->
          <div class="phase-list">
            <div
              v-for="phase in phaseOrder"
              :key="phase.key"
              class="phase-row"
              :class="{ 'is-active': phase.status === 'running' }"
            >
              <div class="phase-icon">
                <el-icon v-if="phase.status === 'completed'" color="#67C23A"><CircleCheckFilled /></el-icon>
                <el-icon v-else-if="phase.status === 'running'" color="#409EFF" class="is-loading"><Loading /></el-icon>
                <el-icon v-else-if="phase.status === 'failed'" color="#F56C6C"><CircleCloseFilled /></el-icon>
                <el-icon v-else-if="phase.status === 'skipped'" color="#909399"><RemoveFilled /></el-icon>
                <el-icon v-else color="#c0c4cc"><Clock /></el-icon>
              </div>
              <div class="phase-info">
                <span class="phase-label">{{ phase.label }}</span>
                <span v-if="phase.score !== null" class="phase-score" :style="{ color: scoreColor(phase.score) }">
                  {{ phase.score }}分
                </span>
                <span v-if="phase.status === 'running'" class="phase-running">评测中...</span>
              </div>
              <el-button
                v-if="phase.status === 'completed' && phase.result"
                size="small"
                link
                type="primary"
                @click="showPhaseDetail(phase)"
              >
                详情
              </el-button>
            </div>
          </div>
        </el-card>

        <!-- 完成后的综合结果 -->
        <div v-if="evalStatus === 'completed' && evalOverallScore !== null">
          <!-- 综合评分 -->
          <el-card shadow="never" class="score-card" style="margin-top: 16px">
            <div class="overall-score">
              <div class="score-number" :style="{ color: scoreColor(evalOverallScore) }">
                {{ evalOverallScore }}
              </div>
              <div class="score-label">综合评分 / 100</div>
            </div>

            <!-- 维度得分条 -->
            <div class="dim-scores" style="margin-top: 16px">
              <div v-for="dim in completedDimensions" :key="dim.key" class="dim-score-row">
                <span class="dim-name">{{ dim.label }}</span>
                <el-progress
                  :percentage="dim.score"
                  :color="scoreColor(dim.score)"
                  :stroke-width="8"
                  style="flex: 1; margin: 0 12px"
                />
                <span class="dim-value">{{ dim.score }}分</span>
              </div>
            </div>
          </el-card>

          <!-- 前后对比 -->
          <el-card shadow="never" style="margin-top: 16px" v-if="beforeAfter">
            <template #header><span>优化前后对比</span></template>
            <div class="comparison">
              <div class="comp-item">
                <span class="comp-label">优化前</span>
                <span class="comp-value">{{ beforeAfter.before_score }}分</span>
              </div>
              <el-icon :size="24"><ArrowRight /></el-icon>
              <div class="comp-item">
                <span class="comp-label">优化后</span>
                <span class="comp-value">{{ beforeAfter.after_score }}分</span>
              </div>
              <el-tag :type="beforeAfter.improvement_percent > 0 ? 'success' : 'danger'" size="large">
                {{ beforeAfter.improvement_percent > 0 ? '+' : '' }}{{ beforeAfter.improvement_percent }}%
              </el-tag>
            </div>
          </el-card>

          <!-- 短板诊断 + 建议 -->
          <el-card shadow="never" style="margin-top: 16px" v-if="weakPoints.length">
            <template #header><span>短板诊断</span></template>
            <el-alert
              v-for="(wp, i) in weakPoints"
              :key="i"
              :title="wp"
              type="warning"
              :closable="false"
              style="margin-bottom: 8px"
            />
          </el-card>

          <el-card shadow="never" style="margin-top: 16px" v-if="suggestions.length">
            <template #header><span>迭代优化建议</span></template>
            <el-alert
              v-for="(sg, i) in suggestions"
              :key="i"
              :title="sg"
              type="success"
              :closable="false"
              style="margin-bottom: 8px"
            />
          </el-card>

          <!-- 操作 -->
          <div style="text-align: right; margin-top: 16px">
            <el-button type="primary" @click="resetEval">重新评测</el-button>
            <el-button type="success" @click="goToExport">导出报告</el-button>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useGeoStore } from '../stores/geo'
import { getEvalDimensions, startEvalSSE, cancelEval as apiCancelEval } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const store = useGeoStore()

// ── 配置状态 ──
const evalMode = ref(store.evalMode || 'pipeline')
const textSource = ref('rewrite')
const evalText = ref('')
const originalText = ref('')
const sandtableType = ref(store.currentSandtableType || 'smart_traffic')
const targetPlatforms = ref(store.selectedPlatforms.length > 0 ? store.selectedPlatforms : ['deepseek'])
const userRoles = ref(['b_end_procurement', 'general_consultant'])
const customQuestions = ref('')

const dimensionConfigs = ref([])
const hasLLM = computed(() => store.configuredPlatforms.length > 0)

// ── 评测运行状态 ──
const isRunning = ref(false)
const evalStatus = ref('idle') // idle | running | completed | cancelled | failed
const evalOverallProgress = ref(0)
const evalOverallScore = ref(null)
const evalSessionId = ref(null)
const sseConnection = ref(null)

// 阶段状态
const phaseStates = ref({})

const phaseOrderDef = [
  { key: 'generating_questions', label: '生成评测问题', status: 'pending', score: null, result: null },
  { key: 'brand_recall', label: '品牌召回率', status: 'pending', score: null, result: null },
  { key: 'solution_match', label: '方案匹配度', status: 'pending', score: null, result: null },
  { key: 'advantage_citation', label: '优势采信率', status: 'pending', score: null, result: null },
  { key: 'structure_quality', label: '结构化程度', status: 'pending', score: null, result: null },
  { key: 'differentiation', label: '差异化程度', status: 'pending', score: null, result: null },
  { key: 'comprehensive', label: '综合评分', status: 'pending', score: null, result: null },
]

const phaseOrder = computed(() => phaseOrderDef.map(p => ({
  ...p,
  status: phaseStates.value[p.key]?.status || 'pending',
  score: phaseStates.value[p.key]?.score ?? null,
  result: phaseStates.value[p.key]?.result ?? null,
})))

const beforeAfter = computed(() => {
  const comp = phaseStates.value['comprehensive']?.result
  return comp?.before_after_comparison || null
})
const weakPoints = computed(() => {
  return phaseStates.value['comprehensive']?.result?.weak_points || []
})
const suggestions = computed(() => {
  return phaseStates.value['comprehensive']?.result?.suggestions || []
})
const completedDimensions = computed(() => {
  const comp = phaseStates.value['comprehensive']?.result
  if (!comp?.dimension_scores) return []
  return Object.entries(comp.dimension_scores).map(([key, score]) => {
    const dim = dimensionConfigs.value.find(d => d.key === key)
    return { key, label: dim?.label || key, score }
  })
})

const statusTagType = computed(() => {
  if (evalStatus.value === 'completed') return 'success'
  if (evalStatus.value === 'failed') return 'danger'
  if (evalStatus.value === 'cancelled') return 'warning'
  return 'info'
})
const statusLabel = computed(() => {
  if (evalStatus.value === 'running') return '评测中'
  if (evalStatus.value === 'completed') return '已完成'
  if (evalStatus.value === 'cancelled') return '已取消'
  if (evalStatus.value === 'failed') return '失败'
  return ''
})

const evalHistory = ref([])

// ── 沙盘类型 / 平台 / 角色选项 ──
const sandtableTypes = [
  { value: 'smart_traffic', label: '智慧交通沙盘' },
  { value: 'smart_city', label: '智慧城市沙盘' },
  { value: 'smart_industry', label: '智慧工业沙盘' },
  { value: 'smart_agriculture', label: '智慧农业沙盘' },
  { value: 'smart_logistics', label: '智慧物流沙盘' },
  { value: 'military_terrain', label: '军事地形沙盘' },
  { value: 'digital_multimedia', label: '数字多媒体沙盘' },
  { value: 'real_estate', label: '地产/规划/展厅沙盘' },
]
const availablePlatforms = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'wenxin', label: '文心一言' },
  { value: 'tongyi', label: '通义千问' },
  { value: 'gpt', label: 'GPT' },
  { value: 'claude', label: 'Claude' },
  { value: 'doubao', label: '字节豆包' },
  { value: 'yuanbao', label: '腾讯元宝' },
]
const roleOptions = [
  { value: 'b_end_procurement', label: 'B端政企采购' },
  { value: 'technical_selection', label: '技术人员选型' },
  { value: 'project_manager', label: '项目经办人' },
  { value: 'general_consultant', label: '普通咨询用户' },
]

// ── 初始化 ──
onMounted(async () => {
  // 加载维度配置
  try {
    const res = await getEvalDimensions()
    const dims = res.data.dimensions || []
    dimensionConfigs.value = dims.map(d => ({
      ...d,
      enabled: !(d.requires_llm && !hasLLM.value),
    }))
  } catch { /* 使用默认 */ }

  // 初始化评测文本
  const firstResult = store.rewriteResults[0]
  evalText.value = firstResult?.optimized_text || store.cleanedText || ''
  originalText.value = store.originalText || ''
})

// ── 模式切换 ──
function onModeChange(val) {
  store.setEvalMode(val)
  if (val === 'standalone') {
    textSource.value = 'manual'
  } else {
    textSource.value = 'rewrite'
    const firstResult = store.rewriteResults[0]
    evalText.value = firstResult?.optimized_text || store.cleanedText || ''
  }
}
function onTextSourceChange(val) {
  if (val === 'rewrite') {
    const firstResult = store.rewriteResults[0]
    evalText.value = firstResult?.optimized_text || store.cleanedText || ''
  } else {
    evalText.value = ''
  }
}

// ── 维度配置变化 ──
function onDimensionChange() {
  normalizeWeights()
}
function onWeightChange() {
  normalizeWeights()
}
function normalizeWeights() {
  const enabled = dimensionConfigs.value.filter(d => d.enabled)
  if (enabled.length === 0) return
  const each = Math.floor(100 / enabled.length)
  const remainder = 100 - each * enabled.length
  enabled.forEach((d, i) => {
    d.weight = each + (i === enabled.length - 1 ? remainder : 0)
  })
}

// ── 开始评测 ──
async function startEval() {
  if (!evalText.value) {
    ElMessage.warning('请先输入评测文本')
    return
  }

  isRunning.value = true
  evalStatus.value = 'running'
  evalOverallProgress.value = 0
  evalOverallScore.value = null
  phaseStates.value = {}

  const customQs = customQuestions.value
    .split('\n')
    .map(q => q.trim())
    .filter(q => q)

  sseConnection.value = startEvalSSE(
    {
      optimized_text: evalText.value,
      original_text: originalText.value || null,
      sandtable_type: sandtableType.value,
      platforms: targetPlatforms.value,
      user_roles: userRoles.value,
      custom_questions: customQs,
      dimensions: dimensionConfigs.value
        .filter(d => d.enabled)
        .map(d => ({ key: d.key, label: d.label, requires_llm: d.requires_llm, weight: d.weight, enabled: d.enabled })),
      mode: evalMode.value,
    },
    // onEvent
    (eventType, payload) => {
      const phase = payload.phase
      evalSessionId.value = payload.session_id
      evalOverallProgress.value = payload.progress || 0

      if (eventType === 'phase_complete' || eventType === 'phase_skipped') {
        const data = payload.data || {}
        const score = data.average ?? data.overall_score ?? null
        phaseStates.value = {
          ...phaseStates.value,
          [phase]: {
            status: eventType === 'phase_skipped' ? 'skipped' : 'completed',
            score,
            result: data,
          },
        }
      } else if (eventType === 'phase_failed') {
        phaseStates.value = {
          ...phaseStates.value,
          [phase]: { status: 'failed', score: null, result: null },
        }
      }

      if (eventType === 'eval_complete') {
        evalStatus.value = 'completed'
        evalOverallScore.value = payload.data?.overall_score ?? null
        isRunning.value = false
        store.setEvaluationResult(payload.data)
        store.addToHistory({
          name: 'AI评测',
          sandtableType: sandtableType.value,
          status: `评分: ${evalOverallScore.value}分`,
        })
        ElMessage.success(`评测完成！综合评分: ${evalOverallScore.value}分`)
      }

      if (eventType === 'eval_error') {
        evalStatus.value = 'failed'
        isRunning.value = false
        ElMessage.error('评测过程出错: ' + (payload.data?.error || '未知错误'))
      }
    },
    // onError
    (err) => {
      if (err.name === 'AbortError') return
      evalStatus.value = 'failed'
      isRunning.value = false
      ElMessage.error('评测连接中断: ' + (err.message || '网络错误'))
    }
  )
}

// ── 取消评测 ──
async function cancelEval() {
  if (!evalSessionId.value) {
    sseConnection.value?.close()
    isRunning.value = false
    evalStatus.value = 'cancelled'
    return
  }

  try {
    await apiCancelEval(evalSessionId.value)
    evalStatus.value = 'cancelled'
    isRunning.value = false
    // SSE 连接会自然断开（后端停止发送事件）
    ElMessage.info('评测已取消，已完成阶段的结果保留')
  } catch {
    sseConnection.value?.close()
    isRunning.value = false
    evalStatus.value = 'cancelled'
  }
}

// ── 加载历史 ──
function loadHistoryText() {
  // 简单实现：展开选择
  ElMessageBox.prompt('选择历史记录', '加载历史', {
    inputType: 'textarea',
    inputPlaceholder: '从历史记录中选择...',
  }).catch(() => {})
}

// ── 工具函数 ──
function scoreColor(score) {
  if (score >= 80) return '#67C23A'
  if (score >= 60) return '#E6A23C'
  return '#F56C6C'
}
function showPhaseDetail(phase) {
  const content = JSON.stringify(phase.result, null, 2)
  ElMessageBox.alert(content, `${phase.label} 详情`, { dangerouslyUseHTMLString: false })
}
function resetEval() {
  evalStatus.value = 'idle'
  evalOverallProgress.value = 0
  evalOverallScore.value = null
  evalSessionId.value = null
  phaseStates.value = {}
}
function goToExport() {
  router.push('/export')
}
</script>

<style scoped>
.eval-view { max-width: 1300px; }
.page-title { font-size: 20px; margin-bottom: 20px; color: #303133; }

/* 配置面板 */
.config-card { position: sticky; top: 24px; }
.text-preview { background: #fafafa; padding: 10px; border-radius: 6px; font-size: 13px; color: #606266; max-height: 80px; overflow: hidden; }

/* 维度行 */
.dim-row { display: flex; align-items: center; margin-bottom: 8px; }
.dim-weight { font-size: 13px; color: #909399; width: 40px; text-align: right; }

/* 操作按钮 */
.action-buttons { margin-top: 12px; }

/* 空状态 */
.empty-card { min-height: 400px; display: flex; align-items: center; justify-content: center; }
.empty-state { text-align: center; color: #909399; padding: 60px 0; }
.empty-state h3 { margin: 16px 0 8px; color: #606266; }

/* 进度 */
.progress-card { min-height: 300px; }
.progress-header { display: flex; justify-content: space-between; align-items: center; }

/* 阶段列表 */
.phase-list { margin-top: 20px; }
.phase-row { display: flex; align-items: center; padding: 10px 12px; border-radius: 8px; margin-bottom: 4px; transition: background 0.2s; }
.phase-row.is-active { background: #ecf5ff; }
.phase-icon { width: 28px; font-size: 18px; }
.phase-info { flex: 1; display: flex; align-items: center; gap: 8px; }
.phase-label { font-size: 14px; color: #303133; }
.phase-score { font-size: 18px; font-weight: bold; }
.phase-running { font-size: 12px; color: #409EFF; }

/* 综合评分 */
.overall-score { text-align: center; padding: 20px 0; }
.score-number { font-size: 72px; font-weight: bold; line-height: 1; }
.score-label { font-size: 16px; color: #909399; margin-top: 8px; }

/* 维度得分条 */
.dim-score-row { display: flex; align-items: center; margin-bottom: 12px; }
.dim-name { width: 90px; font-size: 13px; color: #606266; }
.dim-value { width: 48px; text-align: right; font-size: 14px; font-weight: bold; color: #303133; }

/* 前后对比 */
.comparison { display: flex; align-items: center; gap: 20px; padding: 12px 0; }
.comp-item { text-align: center; }
.comp-label { font-size: 13px; color: #909399; display: block; }
.comp-value { font-size: 24px; font-weight: bold; color: #303133; }
</style>
```

- [ ] **Step 2: 构建验证**

Run: `cd geo-optimizer/frontend && npx vite build 2>&1`

Expected: Build succeeds without errors.

- [ ] **Step 3: Commit**

```bash
git add geo-optimizer/frontend/src/views/EvaluationCenter.vue
git commit -m "feat: rewrite EvaluationCenter with phased progress, dual modes, configurable dimensions"
```

---

## 验证清单

全部任务完成后，运行以下端到端验证：

- [ ] **V1: 后端服务启动** — `cd geo-optimizer/backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` 正常启动
- [ ] **V2: 维度接口** — `curl http://127.0.0.1:8000/api/evaluate/dimensions` 返回5个维度
- [ ] **V3: SSE评测接口** — `curl -X POST http://127.0.0.1:8000/api/evaluate/start -H "Content-Type: application/json" -d '{"optimized_text":"武汉微艺达智能科技...","sandtable_type":"smart_traffic","dimensions":[]}'` 返回 SSE 事件流
- [ ] **V4: 取消评测** — 启动评测后立即 `curl -X POST http://127.0.0.1:8000/api/evaluate/cancel/{session_id}` 验证取消
- [ ] **V5: 前端构建** — `cd geo-optimizer/frontend && npx vite build` 成功
- [ ] **V6: 前端页面** — 打开 `http://localhost:5173/evaluation`，验证配置面板、开始评测、进度展示、结果展示正常
