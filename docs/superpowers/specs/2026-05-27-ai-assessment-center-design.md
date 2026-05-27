# AI评测中心 — "开始评测"模块重构设计

**日期**: 2026-05-27
**项目**: GEO生成式搜索优化系统 v1.0.0 Personal
**范围**: AI评测中心"开始评测"功能模块 — 前端重做 + 后端增强

---

## 1. 目标

重构 AI评测中心的"开始评测"模块，支持：

- **两种模式共存**：流水线模式（从GEO优化工坊带入结果）+ 独立模式（手动输入/加载历史）
- **5阶段可中断评测**：生成问题 → 品牌召回 → 方案匹配 → LLM采信 → 结构化 → 差异化 → 综合评分
- **5维度可配置**：品牌召回率、方案匹配度、优势采信率、结构化程度、差异化程度，用户勾选+调权重
- **SSE实时推送**：每阶段独立事件，前端展示进度条+中间结果卡片

---

## 2. 整体架构

```
EvaluationCenter.vue (重写)
┌──────────────┐  ┌─────────────────────────────────┐
│ 配置面板 (左)  │  │ 进度/结果区 (右)                  │
│              │  │                                 │
│ 评测模式切换  │  │ 阶段进度条 + 中间结果卡片          │
│ 文本来源      │  │ 完成后: 雷达图 + 诊断 + 导出      │
│ 沙盘/平台/角色│  │                                 │
│ 维度勾选+权重 │  │                                 │
│ [开始][取消]  │  │                                 │
└──────────────┘  └─────────────────────────────────┘
       │                        ▲
       │ POST /evaluate/start   │ SSE events
       ▼                        │
┌──────────────────────────────────────────────────┐
│ Backend                                         │
│ ┌────────────────┐ ┌──────────────┐              │
│ │EvalSession     │ │DimensionReg  │              │
│ │(状态机/取消)    │ │(5维度注册表)  │              │
│ └────────────────┘ └──────────────┘              │
│ ┌────────────────┐                               │
│ │AIEvaluator(增强)│                               │
│ └────────────────┘                               │
└──────────────────────────────────────────────────┘
```

---

## 3. 评测流程（7阶段）

```
阶段1: 生成评测问题
  - 基于用户角色 + 自定义问题 + 沙盘类型模板
  - 去重、截断控制
  - 产出: 问题列表

阶段2: 品牌召回评测（无LLM）
  - 文本向量化 + FAISS索引
  - 品牌关键词命中率 + 语义相似度
  - 产出: brand_recall 分数 + 命中详情

阶段3: 方案匹配评测（无LLM）
  - 问题 vs 文本片段语义相似度
  - Top-K匹配分数汇总
  - 产出: solution_match 分数 + 匹配片段

阶段4: LLM采信评测（需LLM，可跳过）
  - 抽取代表性问题（最多5个）
  - LLM模拟AI引用评分 + 结果缓存
  - 产出: advantage_citation 分数 + 引用分析

阶段5: 结构化程度评测（需LLM，可跳过）
  - LLM评估标题层级、段落组织、列表使用
  - 产出: structure_quality 分数 + 结构诊断

阶段6: 差异化程度评测（需LLM，可跳过）
  - LLM评估与竞品的区分度、独特信息密度
  - 产出: differentiation 分数 + 差异分析

阶段7: 综合评分 + 诊断
  - 加权汇总（用户可配权重）
  - 短板诊断 + 迭代建议
  - 前后对比（有原始文案时）
  - 产出: overall_score + 完整报告
```

每个阶段独立触发 SSE 事件，前端实时更新。任意阶段可取消，保留已完成结果。

---

## 4. 评测维度（5维）

| 维度 | 英文Key | 需要LLM | 默认权重 | 说明 |
|------|---------|---------|----------|------|
| 品牌召回率 | brand_recall | 否 | 20% | 关键词命中 + 语义相似度 |
| 方案匹配度 | solution_match | 否 | 20% | 问题vs文本语义相关性 |
| 优势采信率 | advantage_citation | 是 | 20% | LLM模拟AI引用可能性 |
| 结构化程度 | structure_quality | 是 | 20% | 标题/段落/列表AI可提取性 |
| 差异化程度 | differentiation | 是 | 20% | 与竞品文本的区分度 |

默认全部勾选，权重均分（各20%，总计100%）。用户可取消勾选（跳过该维度）或调整权重滑块。取消勾选某维度后，其权重自动按比例分配给剩余已勾选维度；用户调整权重时前端实时校验总和=100%。无LLM配置时，3个需LLM的维度前端灰显不可选，品牌召回+方案匹配权重自动调整为各50%。

---

## 5. 核心数据模型

```python
class EvalPhase(str, Enum):
    GENERATING_QUESTIONS = "generating_questions"
    BRAND_RECALL = "brand_recall"
    SOLUTION_MATCH = "solution_match"
    ADVANTAGE_CITATION = "advantage_citation"
    STRUCTURE_QUALITY = "structure_quality"
    DIFFERENTIATION = "differentiation"
    COMPREHENSIVE = "comprehensive"

class EvalPhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"

class EvalDimensionConfig:
    key: str
    label: str
    requires_llm: bool
    weight: float       # 0-100
    enabled: bool

class EvalSessionState:
    session_id: str
    status: str          # running | completed | cancelled | failed
    phases: dict[EvalPhase, EvalPhaseStatus]
    phase_results: dict[EvalPhase, dict]
    overall_progress: float  # 0-100
    cancelled: bool

# SSE事件格式
class EvalSSEEvent:
    event: str           # phase_start | phase_progress | phase_complete | eval_complete | error
    data: {
        session_id: str
        phase: str
        status: str
        result: dict | None     # 阶段结果载荷
        progress: float         # 0-100
        message: str
    }
```

---

## 6. API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/evaluate/start` | 启动评测，返回 SSE 流 |
| GET | `/api/evaluate/session/{id}` | 查询会话状态（断线恢复） |
| POST | `/api/evaluate/cancel/{id}` | 取消评测 |
| GET | `/api/evaluate/dimensions` | 获取可选维度列表 |
| GET | `/api/evaluate/history` | 评测历史列表 |
| GET | `/api/evaluate/history/{id}` | 历史评测详情 |

SSE 事件流格式：

```
event: phase_start
data: {"session_id":"...","phase":"brand_recall","progress":15}

event: phase_complete
data: {"session_id":"...","phase":"brand_recall","status":"completed","result":{"average":78,"details":[...]},"progress":30}

event: eval_complete
data: {"session_id":"...","overall_score":76,"platform_results":[...],"weak_points":[...],"suggestions":[...],"progress":100}
```

取消流程：前端发送 POST /cancel → 后端设置 `cancelled = True` → 每个阶段开始前检查标志 → 已完成的阶段数据保留 → 通过 SSE 发送 cancelled 事件。

---

## 7. 前端设计

### 7.1 配置面板（左侧 360px）

- **评测模式**：Radio 切换 流程模式 / 独立模式
- **文本来源**：流程模式显示下拉+预览；独立模式显示大文本框+粘贴+加载历史按钮
- **沙盘类型**：8选1下拉
- **目标平台**：多选标签（7平台）
- **用户角色**：4选多 checkbox
- **评测维度**：5项 checkbox + 权重滑块（默认均分20%）
- **自定义问题**：textarea（一行一个）
- **对比原文**：可选折叠区
- **操作按钮**：[开始评测] 主按钮 + [取消评测] 次按钮

### 7.2 进度/结果区（右侧）

**进行中：**
- 总进度条（百分比）
- 每个阶段一行：状态图标 + 阶段名 + 分数（完成后显示）+ 展开按钮

**完成后：**
- 综合评分大数字
- 雷达图（5维度）
- Tab切换：平台详情 / 维度详情 / 前后对比 / 短板诊断 / 优化建议
- 操作：[导出报告] [重新评测]

---

## 8. 后端改造清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/core/eval_session.py` | **新增** | 会话状态机，管理阶段流转、取消信号、中间结果 |
| `backend/app/core/eval_dimensions.py` | **新增** | 5维度注册表，自描述+计算方法绑定 |
| `backend/app/core/evaluator.py` | 增强 | 支持分阶段执行、按维度配置计算、新增结构化+差异化评分 |
| `backend/app/api/evaluation.py` | 增强 | 新增6个端点，SSE流式响应 |
| `backend/app/prompts/evaluation.py` | 增强 | 新增结构化评估prompt、差异化评估prompt |
| `backend/app/models/schemas.py` | 增强 | 新增 EvalSession、DimensionConfig 等 schema |
| `backend/app/models/enums.py` | 增强 | 新增 EvalPhase、EvalPhaseStatus 枚举 |

**不改造：** EmbeddingService、VectorStore、LLM适配器、报告生成

---

## 9. 前端改造清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/src/views/EvaluationCenter.vue` | **重写** | 全新布局：配置面板+进度结果区 |
| `frontend/src/api/index.js` | 增强 | 新增 SSE 连接、cancel、history 等 API |
| `frontend/src/stores/geo.js` | 增强 | 新增 evalSession、evalProgress 等状态 |

---

## 10. 边界与约束

- 不使用 WebSocket，用 SSE + REST 取消端点
- 无 LLM 配置时，3个需LLM的维度自动跳过（前端灰显）
- 单次评测文本上限 50000 字符（与现有一致）
- LLM评测采样上限 5 个问题（控制 API 调用成本）
- 评测结果缓存（相同文本+问题 hash 命中直接返回）
- 会话内存存储（不持久化到数据库，重启丢失）
