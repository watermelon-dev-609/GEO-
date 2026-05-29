# CLAUDE.md — GEO生成式搜索优化轻量化系统

## 1. 项目基础信息

### 名称
GEO生成式搜索优化系统（轻量化版）— Generative Engine Optimization Platform

### 背景
为**武汉微艺达智能科技有限公司**定制的轻量化GEO优化平台。该公司主营8大类沙盘模型定制（智慧交通、智慧城市、智慧工业、智慧农业、智慧物流、军事地形、数字多媒体、地产/规划/展厅），需要通过AI生成式搜索（如豆包、DeepSeek、通义千问等）获取品牌曝光和客户线索。

### 核心目标：四门策略
1. **优先抓取** — AI爬虫优先发现和索引企业内容
2. **优先理解** — AI正确提取企业实体、产品、技术信息
3. **优先引用** — AI在生成答案时优先引用企业内容
4. **优先推荐** — AI主动向用户推荐企业产品/服务

### 产品定位与核心价值

**一句话定义**: 国内首款 AI 生成式搜索轻量化 GEO 采信优化系统，对标大模型 AI 收录/引用/推荐机制，区别于传统 SEO 工具。

**GEO 与 SEO 的本质区别**:
- SEO 优化搜索引擎排名（百度/Google），通过关键词堆砌、外链建设、TDK 标签优化
- GEO 优化 AI 大模型生成结果（豆包/DeepSeek/通义千问等），通过结构化内容、实体锚定、语义权威性让 AI 优先引用企业信息

**核心差异化壁垒**:
- **AI 采信六原则驱动的 Prompt 矩阵**: 56 套精确适配（8 类沙盘 × 7 大 AI 平台），每套 Prompt 针对特定平台的检索/引用机制定制
- **7 维评测引擎**: 品牌召回→方案匹配→优势引用→真实采信→结构质量→差异化→信源一致性，全链路量化 AI 采信效果
- **全链路 SSE 流式**: 从文本清洗到 AI 评测，所有 LLM 调用支持实时流式推送

**行业唯一性**: 8 类沙盘模型定制行业（智慧交通/城市/工业/农业/物流/军事地形/数字多媒体/地产规划）× 7 大 AI 平台的精确适配矩阵，无同类竞品。

**轻量化优势**: 无数据库依赖（纯 JSON 文件存储）、单机可运行（仅需 Python 3.10+ + Node.js 18+）、中小企业可私有化部署、无需云服务。

### 核心技术链路
```
文本导入 → 智能清洗(TextCleaner) → GEO重构(GEORewriter) → JSON-LD生成 → AI评测 → 成果导出
```

### 运行环境
- **OS**: Windows 11 / Linux
- **Python**: 3.10+
- **Node.js**: 18+
- **后端端口**: 8000 (FastAPI + uvicorn)
- **前端端口**: 5173 (Vite, 若占用则自动切换5174)

### 启动方式
```bash
# 后端
cd backend && python run.py

# 前端
cd frontend && npx vite --port 5173
```

### 重要环境变量
- `HF_MIRROR` / `HF_ENDPOINT` — HuggingFace 镜像（国内环境需设置 `https://hf-mirror.com`）
- `KMP_DUPLICATE_LIB_OK=TRUE` — 解决 PyTorch + scikit-learn OpenMP DLL 冲突
- API密钥通过 `backend/.env` 注入，模板在 `backend/.env.example`

---

## 2. 技术架构

### 技术栈

**后端**:
- FastAPI (异步Web框架)
- Pydantic v2 (数据校验)
- sentence-transformers + FAISS (语义向量检索)
- PyTorch (Embedding 模型推理)
- httpx (LLM API 调用)
- PyYAML (配置管理)

**前端**:
- Vue 3 (Composition API + `<script setup>`)
- Vite 6 (构建工具)
- Element Plus (UI组件库)
- Pinia (状态管理)
- Vue Router 4 (路由)
- Axios + Fetch SSE (API通信)

**AI模型**:
- Embedding: `BAAI/bge-large-zh-v1.5` (约1.3GB，首次运行自动下载)
- LLM平台: DeepSeek(默认), Kimi(moonshot-v1-8k), 通义千问, 豆包, 文心一言, 元宝, 讯飞星火

### 目录结构

```
geo-optimizer/
├── backend/
│   ├── run.py                     # 启动入口（Uvicorn）
│   ├── .env                       # 真实API密钥（gitignore保护）
│   ├── .env.example               # 密钥模板
│   ├── config/
│   │   ├── settings.yaml          # 主配置（企业信息、LLM参数）
│   │   └── api_keys.yaml          # API密钥模板（${VAR}占位符，由.env填充）
│   ├── templates/
│   │   ├── copy/                  # 沙盘文案模板（4/8种已有）
│   │   └── jsonld/                # JSON-LD参考模板（2/8种已有）
│   ├── data/
│   │   ├── cache/                 # 运行时缓存（gitignore）
│   │   ├── output/                # 生成输出
│   │   ├── evaluations/           # 评测历史JSON
│   │   ├── platform_rules/        # 平台规则数据
│   │   ├── competitors/           # 竞品数据
│   │   ├── keywords/              # 关键词库
│   │   └── templates/             # 内容模板
│   └── app/
│       ├── main.py                # FastAPI入口（路由挂载、中间件、启动事件）
│       ├── api/
│       │   ├── cleaning.py        # 文本清洗 API
│       │   ├── geo_rewrite.py     # GEO文案重构 API（含SSE流式）
│       │   ├── jsonld.py          # JSON-LD生成 API
│       │   ├── evaluation.py      # AI评测 API（SSE流式评测）
│       │   ├── reports.py         # 数据报表 API
│       │   ├── analytics.py       # 数据看板统计 API
│       │   ├── diagnosis.py       # 内容诊断 API
│       │   ├── platform_monitor.py # 平台规则监测 API
│       │   ├── keywords.py        # 关键词库 API
│       │   └── competitors.py     # 竞品调研 API
│       ├── core/
│       │   ├── cleaner.py         # TextCleaner：文本清洗引擎
│       │   ├── rewriter.py        # GEORewriter：批量调度+缓存+后处理
│       │   ├── jsonld_gen.py      # JSON-LD结构化生成器
│       │   ├── evaluator.py       # AIEvaluator：多阶段评测引擎
│       │   ├── eval_dimensions.py # DimensionRegistry：7维度注册+权重管理
│       │   ├── eval_session.py    # EvalSession：SSE流式评测会话管理
│       │   ├── eval_history_store.py # 评测历史JSON持久化
│       │   ├── diagnoser.py       # ContentDiagnoser：5维规则引擎+LLM深度诊断
│       │   ├── reporter.py        # ReportGenerator：HTML/PDF报表生成
│       │   ├── text_splitter.py   # 文本分段工具
│       │   └── template_manager.py # 模板管理器
│       ├── models/
│       │   ├── enums.py           # 枚举：SandtableType, AIPlatform, UserRole, EvalDimension 等
│       │   └── schemas.py         # Pydantic模型：全部请求/响应Schema
│       ├── services/
│       │   ├── embedding_svc.py   # EmbeddingService：向量编码
│       │   ├── vector_store.py    # VectorStore：FAISS/NumPy向量索引
│       │   └── llm/
│       │       ├── base.py        # LLMFactory + LLMMessage
│       │       ├── openai_compat.py # OpenAI兼容适配器(DeepSeek/Kimi/通义/豆包/元宝)
│       │       ├── claude.py      # Claude适配器（完整但AIPlatform无Claude条目，暂不可达）
│       │       └── wenxin.py      # 文心一言适配器（百度API特殊处理）
│       ├── prompts/
│       │   ├── rewrite.py         # GEO_SYSTEM_PROMPT + 沙盘/平台Profile + build_geo_prompt()
│       │   ├── evaluation.py      # 评测Prompt模板
│       │   └── diagnosis.py       # 诊断Prompt + 平台摘要Prompt
│       └── utils/
│           ├── config.py          # 配置加载 + .env解析 + ${VAR}占位符替换
│           ├── cache.py           # LocalCache：文件系统KV缓存
│           └── retry.py           # async_retry：指数退避重试
└── frontend/
    ├── index.html
    ├── vite.config.ts
    └── src/
        ├── main.js                # Vue应用入口 + 全局ElementPlus图标注册
        ├── App.vue                # 根组件
        ├── api/
        │   └── index.js           # Axios实例 + 全部API函数 + SSE连接
        ├── router/
        │   └── index.js           # Vue Router配置（懒加载路由）
        ├── stores/
        │   └── geo.js             # Pinia Store：全局状态 + sessionStorage持久化
        ├── components/
        │   └── LayoutShell.vue    # 主布局（侧边栏+流水线指示器+LLM配置弹窗）
        └── views/
            ├── Dashboard.vue      # 仪表盘（快速操作+数据看板+覆盖矩阵）
            ├── ImportView.vue     # 文案导入（粘贴/上传/快速诊断三Tab）
            ├── GEOWorkshop.vue    # GEO优化工坊（批量/流式改写）
            ├── EvaluationCenter.vue # AI评测中心（SSE流式评测+历史管理）
            ├── ExportView.vue     # 成果导出（6项导出+报告预览）
            ├── StrategyCenter.vue # 策略中心（平台监测+竞品调研+关键词库三Tab）
            └── ContentTemplates.vue # 内容规范（写作模板+审核标准+规范导出）
```

### API路由总览（10个前缀，57个端点）

| 前缀 | 标签 | 端点 | 说明 |
|------|------|------|------|
| `/api/cleaning` | 文本清洗 | POST /clean, /extract | 文本清洗+五维信息提取 |
| `/api/geo` | GEO重构 | POST /rewrite, /rewrite/stream, GET /profiles/{type}, /platform-rules/{p} | 批量/流式改写 |
| `/api/jsonld` | JSON-LD | POST /generate, /validate, GET /templates | 结构化代码生成 |
| `/api/evaluate` | AI评测 | POST /start(SSE), /dimensions, /session/{id}, /cancel, /history, /history/{id}, /history/compare, /quick-brand-check | 流式评测+历史管理 |
| `/api/reports` | 报表 | POST /preview, /generate, /generate-from-data, GET /export/{id}, /history | 报表生成导出 |
| `/api/analytics` | 数据看板 | GET /overview, /trend | 聚合统计 |
| `/api/diagnosis` | 内容诊断 | POST /quick, /deep, /batch | 健康体检 |
| `/api/platform-monitor` | 平台监测 | GET /platforms, /platforms/{id}, POST /platforms/{id}, POST /platforms/{id}/llm-summary | 12平台规则管理 |
| `/api/keywords` | 关键词库 | GET /types, GET /{type}, POST /{type}, DELETE /{type}/{cat}/{word}, PUT /{type}/{cat}/{word}, POST /{type}/expand, GET /{type}/export | CRUD+LLM扩展 |
| `/api/competitors` | 竞品调研 | GET /, GET /{id}, POST /, PUT /{id}, DELETE /{id}, POST /{id}/snapshot, POST /compare, POST /report | CRUD+快照+对比 |

### 数据流
```
用户输入文本
  ↓ TextCleaner (cleaner.py)                    ──→ 四门策略·优先抓取
清洗后文本 + 五维信息(core_advantages/applicable_scenarios/technical_features/service_capabilities/implementation_value)
  ↓ GEORewriter (rewriter.py)                   ──→ 四门策略·优先理解
56 Prompt矩阵(8沙盘×7平台) → LLM批量生成 → 后处理校验 → PlatformRewriteResult[]
  ↓ JSONLDGenerator (jsonld_gen.py)             ──→ 四门策略·优先抓取
Schema.org @graph (Organization + Product/Service + BreadcrumbList + FAQPage + WebSite)
  ↓ AIEvaluator (evaluator.py)                  ──→ 四门策略·优先引用
7阶段评测 → 品牌召回+方案匹配+优势引用+真实采信+结构质量+差异化+信源一致性
  ↓ ReportGenerator (reporter.py)               ──→ 四门策略·优先推荐
HTML/PDF报告 + 改进建议 → 反馈至改写Prompt (optimization_hints)
  ↑ 竞品差异注入 (competitors.py → rewriter.py)
```

### GEO 业务闭环逻辑

每一步技术动作直接锚定四门 GEO 核心策略，形成"收录→引用→推荐"的 AI 采信闭环：

| 策略目标 | 技术实现 | 核心模块 | AI 收录/引用/推荐逻辑 |
|----------|----------|----------|----------------------|
| **优先抓取** | 文本清洗 + JSON-LD 结构化 | cleaner.py / jsonld_gen.py | Schema.org 结构化标记让 AI 爬虫识别企业实体、产品类型、服务范围，提升索引优先级 |
| **优先理解** | GEO 文案重构 + 平台适配 | rewriter.py / rewrite.py | 56 Prompt 矩阵让 LLM 按各 AI 平台的检索机制（RAG/卡片/FAQ）生成被优先提取的内容 |
| **优先引用** | 7 维评测 + 信源一致性校验 | evaluator.py | 量化评测 AI 答案中的品牌召回率、方案匹配度、优势引用程度，硬阈值反幻觉（source_consistency<30→overall≤50） |
| **优先推荐** | 竞品对抗 + 差异化注入 + 持续优化 | competitors.py / rewriter.py | 竞品对比分析 → 差异化特征注入改写 Prompt → 评测反馈闭环（optimization_hints 自动追加） |

### 核心隐藏能力

以下能力已在代码中完整实现但原文档未充分暴露：

**AI 幻觉强抑制体系**（详见第 8 章）: 6 层防线从 Prompt 硬约束到后处理校验到评测硬阈值，确保 AI 生成内容不编造量化数据、客户案例、认证证书。

**多 LLM 平台差异化定制**: 非通用改写模板。7 大平台各有独立 Prompt 规则集（`rewrite.py:76-187`），针对各平台的检索机制定制：
- DeepSeek: RAG FAQ 问答格式 + 200-300 字自包含 chunk
- 豆包: 短句（≤30 字）、消费级语感、口语化
- 元宝: 政企采购流程文档、资质/案例/流程
- Kimi: 长文深度分析（1500-2500 字）
- 文心一言: 百度卡片友好、"地名+产品+厂家"标题格式
- 通义千问: 结构化 + 技术参数表
- 讯飞星火: 教育/科研场景、技术深度优先

**轻量化无数据库架构**: 纯 JSON 文件存储体系，无 MySQL/PostgreSQL/Redis 依赖。评测历史、平台规则、竞品数据、关键词库均以 JSON 文件持久化。缓存使用 Pickle + JSON meta 文件系统 KV（`cache.py`，TTL 懒淘汰）。已知风险：当前无文件锁保护，并发写入可能数据竞争（见待办 P0-1）。

**竞品对抗 GEO 优化**（详见第 9 章）: 竞品 CRUD + 快照 + LLM 对比分析 + Markdown 报告 + 差异化特征注入改写 Prompt。

**全链路 SSE 流式**: 改写（`geo_rewrite.py` SSE）和评测（`evaluation.py` SSE）均支持实时流式推送。前端 `startEvalSSE()` 使用 `fetch` + `ReadableStream` + `AbortSignal.any` 实现超时和手动取消。

### API 工程规范

**全接口异步**: 所有 API 端点使用 `async def`，LLM 调用通过 `httpx` 异步客户端，避免阻塞事件循环。

**全参数校验**: 所有请求/响应使用 Pydantic v2 BaseModel（57 个端点中 57 个已迁移），禁止裸 `dict` 参数。Field 验证统一使用 `min_length`、`ge`、`le`。可选字段必须标注 `| None`。

**全异常捕获**: API 层 raise `HTTPException`（含 detail 信息）；核心引擎层 `logger.warning`/`logger.error` + 返回安全默认值；SSE 生成器内部异常转为 `event: eval_error` / `event: phase_failed` SSE 事件（不中断连接）；永不静默吞异常（至少 `logger.exception`）。

**隐性操作日志**: 评测会话自动落盘（`eval_session.py` mark_completed/mark_cancelled → `eval_history_store.save_session()`）；缓存 TTL 懒淘汰（访问时检查过期 → 删除）；模型下载级联（4 步 fallback：本地路径 → 本地缓存 → ModelScope → HF 镜像）。

---

## 3. 编码规范

### Python (后端)

**命名**:
- 类名: `PascalCase` (如 `ContentDiagnoser`, `JSONLDGenerator`)
- 函数/方法: `snake_case` (如 `_rule_diagnose`, `build_geo_prompt`)
- 私有方法: `_` 前缀 (如 `_pre_clean`, `_extract_score`)
- 常量: `UPPER_SNAKE_CASE` (如 `DEFAULT_WEIGHTS`, `SCHEMA_MAPPING`)
- 模块: `snake_case` 全小写无下划线连接 (如 `jsonld_gen`, `eval_history_store`)

**导入顺序**: `__future__` → 标准库 → 第三方库 → 本地模块（空行分隔）

**类型标注**: 必须使用 `from __future__ import annotations` + Python 3.10+ 联合类型语法 (`str | None` 非 `Optional[str]`)

**Pydantic**: 所有API请求/响应必须使用 Pydantic v2 BaseModel（禁止裸 `req: dict`）; Field 验证用 `min_length`, `ge`, `le`; 可选字段明确标注 `| None`

**错误处理**: API层 raise `HTTPException`; 核心引擎层记录 logger.warning/error + 返回安全默认值; 永不静默吞异常（至少 `logger.exception`）

**禁用规则**:
- 禁用 `hash()` 做缓存键 → 必须用 `hashlib.md5(text.encode()).hexdigest()`
- 禁用裸 `dict` 作为API参数 → 必须用 Pydantic 模型
- 禁用 `print()` 输出非ASCII字符（Windows GBK环境会崩溃）→ 用 `logging`
- 禁止 `api_keys.yaml` 包含真实密钥 → 用 `${VAR}` 占位符 + `.env`

### JavaScript/Vue (前端)

**命名**:
- 组件: `PascalCase` (如 `StrategyCenter.vue`, `LayoutShell.vue`)
- 函数/变量: `camelCase` (如 `loadKeywords`, `isExporting`)
- 常量: `UPPER_SNAKE_CASE` (如 `SANDBTABLE_TYPES`)
- ref命名: 语义化描述 (如 `isCleaning`, `hasCopy`, `evalHistoryLoading`)

**Vue规范**:
- 使用 `<script setup>` + Composition API
- 模板中 `v-if` 必须在可能为 null 的嵌套属性前加守卫 (`v-if="analytics && analytics.overview"`)
- `v-html` 使用前必须对内容做 HTML 转义 (escapeHtml)
- 所有异步操作需要 loading 状态 + 错误提示 (ElMessage.error)
- 删除操作必须有 `ElMessageBox.confirm` 确认对话框
- 禁止使用浏览器原生 `prompt()` → 用 `ElMessageBox.prompt`

**API错误处理模板**:
```js
try {
  const res = await someApiCall(params)
  // handle success
} catch (e) {
  ElMessage.error('操作失败: ' + (e.response?.data?.detail || e.message))
}
```

**禁用规则**:
- 禁止 `console.error` 替代用户提示 → 必须用 `ElMessage.error`
- 禁止 `catch {}` 空块（吞错误）→ 至少区分 cancel 和 API 错误
- 禁止 `fetch` 无 timeout → 必须加 `AbortSignal.timeout`
- 禁止 `hash()` 做缓存键

### 通用

**注释原则**: 默认不写注释。只有 WHY（隐藏约束/微妙不变量/特定bug workaround/会令读者惊讶的行为）值得注释。不解释 WHAT（代码自解释）。

**文件大小**: 单个 `.vue` 文件不超过 500 行（StrategyCenter 已接近上限，后续功能需拆分组件）

### AI 生成内容强制约束

以下约束为工程级强制规范，违反即视为不合格：

1. **事实保真**: 严禁编造量化数据（如"服务过200+客户"）、客户案例（无来源的甲方名称）、资质认证（未取得的ISO/资质）、排名比较（"行业领先"无数据支撑）。所有输出只能使用五维输入中已有的事实。
2. **全 8 类沙盘兼容**: 任何新功能（API 端点、Prompt 模板、Schema 映射、前端页面）必须覆盖全部 8 种沙盘类型，禁止单场景开发。
3. **AI 采信六原则遵守**: 所有改写输出必须满足实体锚定、定义优先、量化事实、FAQ 结构、层级结构化、信息增量六项原则（详见第 6 章）。
4. **配置统一托管**: 禁止在代码中硬编码企业名称、地域、平台参数、API 端点 URL。统一从 `settings.yaml` 读取，通过 `config.py:load_settings()` 注入。
5. **安全底线**: API 密钥必须通过 `${VAR}` 占位符 + `.env` 注入，禁止任何形式的密钥硬编码；`v-html` 必须经 `escapeHtml()` 先行转义。

### 国内部署规范

1. **模型下载优先国内镜像**: `HF_ENDPOINT` 默认 `https://hf-mirror.com`（`main.py:12-14` 模块级注入），禁止在代码中写死 `https://huggingface.co` 官方域名。
2. **所有 API 端点兼容国内网络**: LLM 请求超时 ≥120s（`openai_compat.py` chat=120s, stream=300s），重试 3 次指数退避（`retry.py`）。
3. **Windows 编码兼容**: `KMP_DUPLICATE_LIB_OK=TRUE` 必须设置在 `run.py` 顶层（PyTorch + scikit-learn OpenMP DLL 冲突）；`print()` 禁止输出非 ASCII 字符（Windows GBK 环境崩溃）→ 用 `logging`；建议设置 `PYTHONIOENCODING=utf-8` 环境变量。
4. **离线兜底**: 模型加载 4 步级联（本地路径 → 本地缓存 → ModelScope → HF 镜像），详见第 7 章。

---

## 4. 已完成功能 + 待办 + 现存问题

### 第一轮：核心流水线（已完成）
- [x] TextCleaner: 文本清洗 + 五维信息提取 + 沙盘自动识别
- [x] GEORewriter: 56 Prompt矩阵(8×7) + 批量并行 + 流式SSE + 缓存
- [x] JSONLDGenerator: Schema.org @graph + 8种沙盘类型Schema映射
- [x] AIEvaluator: 7阶段SSE流式评测 + 评测历史持久化
- [x] ReportGenerator: HTML/PDF报表生成
- [x] Vue3前端: Dashboard + Import + Workshop + Evaluation + Export 五页面流程

### 第二轮：评测系统审查与修复（已完成）
- [x] solution_match: 句级语义相似度（re.split句子 → top-3均值）
- [x] real_citation: average使用连续值非二元
- [x] 空文本校验（<50字符返回错误）
- [x] source_consistency 硬底限制（<30分 → overall max 50）
- [x] 维度默认权重（DEFAULT_WEIGHTS 7维总和100）
- [x] 改写Prompt增加"信源忠实原则"硬约束
- [x] Differentiation评估基准从行业惯常水平出发

### 第三轮：五大功能模块扩展（已完成）
- [x] 平台规则监测（12平台 CRUD + 变更时间线 + LLM摘要）
- [x] 竞品调研（CRUD + 快照 + LLM对比 + Markdown报告导出）
- [x] 关键词库（3分类 × 8沙盘 + LLM扩展 + CSV导出）
- [x] 内容规范（写作模板 + 审核标准 + 规范导出）
- [x] 数据看板（Overview聚合 + Trend趋势 + Dashboard统计卡片）

### 第四轮：安全与正确性修复（已完成）
- [x] **C1**: API密钥暴露 → `.env` + `${VAR}` 占位符 + `.env.example`
- [x] **C2**: `hash()` → `hashlib.md5()` (rewriter.py 1处 + evaluator.py 5处)
- [x] **XSS**: `v-html` → `escapeHtml()` 先行 + markdown增强
- [x] **SSE超时**: `AbortSignal.timeout` + `AbortSignal.any`
- [x] **Dashboard**: null守卫 + NaN检查 + scoreTrendIcon null + 加载态
- [x] **Diagnoser**: 实体检测/FAQ/夸大检测正则修正 + 地域参数化
- [x] **JSON-LD**: `@id` + `sameAs` + `WebSite` + FAQ 5-15问答 + `dateModified`
- [x] **StrategyCenter**: 15+处错误详情 + 空状态 + `prompt()`→Dialog + 竞态修复
- [x] **EvaluationCenter**: deleteHistoryItem catch 区分 cancel vs API错误
- [x] **18 Pydantic模型**: 全部裸dict端点 → 类型安全的Request Schema

### 第五轮：综合测试与 Bug 修复（2026-05-29 已完成）
- [x] 全业务链路综合测试（28/57 端点直接测试，15+ 文件静态分析）
- [x] **P0-1**: `keywords.py:126` NameError `category` → `req.category`
- [x] **P0-2**: `reports.py:72` NameError `report_format` → `data.format`
- [x] **P0-3**: `cleaning.py:144` AttributeError `SandtableType.smart_traffic` → `SandtableType("smart_traffic")`
- [x] **P1-1**: `evaluator.py` 8+ 处硬编码企业名 → `get_enterprise_name()` / `get_enterprise_location()`
- [x] **P1-2**: `rewriter.py` 流式改写跳过 `_validate_output` → 补齐校验
- [x] **P1-3**: `wenxin.py` Token 不刷新 → 401 自动重试 + `force_refresh`
- [x] **P2-1**: 文本清洗对无意义输入产生幻觉 → `_validate_input()` 中文占比/XSS 预检
- [x] **P2-2**: 平台监测无效ID返回假数据 → 404
- [x] **P2-3**: 竞品快照空payload → `platform` 为空时返回 422
- [x] `evaluator.py` DEFAULT_WEIGHTS → 统一从 `eval_dimensions.py` 读取
- [x] `cache.py` `get()` 无锁 → 加 `_write_lock`
- [x] `GEOWorkshop.vue` `escapeHtml` DOM依赖 → 纯字符串替换
- [x] 新增 `restart.bat` — 一键启停脚本（自动清理旧进程 + 启动前后端）

### 待办任务（结构化优先级）

#### P0 — 必须上线前修复（稳定性/正确性阻塞项）

| 条目 | 类别 | 位置 | 影响 | 建议方案 |
|------|------|------|------|----------|
| 并发竞态修复 | 稳定性 | `eval_session.py:13,38`, `eval_history_store.py:31`, `main.py:237` | 并发请求下 `_sessions` dict 和 JSON 文件写入数据竞争，可能导致数据丢失或损坏 | `_sessions` 加 `asyncio.Lock`；文件写入使用 tempfile + 原子 rename |
| CSV 导出逗号转义 | 稳定性 | `keywords.py:266` | 关键词含逗号时 CSV 列错位，导出数据不可用 | 字段用双引号包裹，内部双引号转义为 `""`, 或使用 `csv` 标准库 |
| `analytics.py` days 参数生效 | 正确性 | `analytics.py` | `GET /api/analytics/trend?days=N` 的 days 参数未实际过滤数据范围 | 在趋势查询中应用 days 过滤 |

#### P1 — 上线前应修复（功能正确性 + 体验）

| 条目 | 类别 | 位置 | 影响 | 建议方案 |
|------|------|------|------|----------|
| `reporter.py` PDF 生成改进 | 正确性 | `reporter.py` | weasyprint 缺失时静默失败 | 检测可用性，不可用时返回明确错误 + HTML 兜底 |
| 评测维度权重从 config 读取 | 正确性 | `evaluator.py` | 权重调整需改 eval_dimensions.py 代码 | 权重从 `settings.yaml:evaluation.weights` 读取 |
| 前端全局空态/加载/错误状态补全 | 体验 | 多个 .vue | 约 15 处缺少状态组件 | 逐页面排查补全 |
| GEOWorkshop 流式 fetch 检查 HTTP 错误码 | 体验 | `GEOWorkshop.vue` | SSE 4xx/5xx 错误详情未提取 | 在 `!response.ok` 分支中读取 `response.json()` |
| 内容模板后端持久化 | 正确性 | `ContentTemplates.vue` | 数据仅存 localStorage | 新增 templates CRUD API |
| ExportView iframe 安全 + 多文件下载 | 体验 | `ExportView.vue` | iframe 无 sandbox；多文件逐个弹窗 | 加 sandbox；JSZip 打包 |

#### P2 — 迭代增强（产品竞争力）

| 条目 | 类别 | 位置 | 影响 | 建议方案 |
|------|------|------|------|----------|
| 新增 E-E-A-T 评估维度 | 迭代 | `evaluator.py`, `eval_dimensions.py` | Google E-E-A-T（Experience/Expertise/Authoritativeness/Trustworthiness）是 AI 生成式搜索的采信核心信号，当前缺失 | 新增 `eeat_score` 为第 8 评测维度，Prompt 中注入企业资质/年限/案例作为权威信号 |
| 改写 Prompt 注入竞品差异 | 迭代 | `rewrite.py:343-353`, `competitors.py` | 当前改写不感知竞品，生成内容与竞品同质化 | 在 `build_geo_prompt()` 中注入竞品对比摘要（`optimization_hints` 机制已有，补齐竞品数据源） |
| 社交平台改写规则 | 迭代 | `rewrite.py:76-187` | 小红书/抖音等社交平台有完全不同的内容形态（笔记/短视频脚本），当前 7 平台均为 LLM 平台 | 新增 `xiaohongshu` / `douyin` 平台规则到 `PLATFORM_RULES`，特征：话题标签、emoji、口语化短文案 |
| 诊断→改写自动反馈回路 | 迭代 | `diagnoser.py` → `rewriter.py` | 诊断和改写是两个独立操作，用户需手动将诊断结果填入改写 hints | 诊断完成后自动生成 `optimization_hints` JSON，一键带入 GEOWorkshop |

#### P3 — 长期优化（技术债清理）

| 条目 | 类别 | 位置 | 影响 | 建议方案 |
|------|------|------|------|----------|
| 前端常量去重 | 优化 | `Dashboard.vue`, `GEOWorkshop.vue`, `StrategyCenter.vue`, `ContentTemplates.vue` | `SANDTABLE_TYPES` / `scoreColor` / `copyText` 在 4 个文件重复定义，不一致风险 | 抽取至 `src/constants.js`，统一 import |
| 路由 Suspense + 404 + scrollBehavior | 优化 | `router/index.js` | 懒加载组件无 Suspense fallback（白屏）；未匹配路由无 404；路由切换无滚动恢复 | `RouterView` 外层包 `<Suspense>` + loading 骨架；添加 `/:pathMatch(.*)*` 通配 404 路由；`scrollBehavior` 配置 |
| 颜色无障碍支持 | 优化 | 全局 CSS + 各 .vue | 评测分数、趋势箭头等仅靠颜色区分（红=差/绿=好），色觉障碍用户无法识别 | 颜色之外增加图标/文字标注（↑/↓ + "良好"/"需改进"） |
| 离线检测 + ErrorBoundary | 优化 | `App.vue`, 全局 | 无网络时操作静默失败；Vue 组件崩溃白屏 | `navigator.onLine` + `online`/`offline` 事件监听 + ElMessage 离线提示；全局 `onErrorCaptured` ErrorBoundary |
| 沙盘模板补齐 | 优化 | `templates/copy/` | 8 种沙盘类型中 4 种无参考文案模板，改写 Prompt 缺少行业语料 | 补齐 military_terrain、digital_multimedia、real_estate、smart_agriculture 4 类模板 |

### 现存临时方案/技术债
- **Claude适配器**: `claude.py` 完整实现但 `AIPlatform` 枚举无Claude条目→永远不可达
- **五维信息模型刚性**: 5个维度硬编码在cleaner/rewriter/evaluator等5+文件中
- **Windows GBK**: `print()` Unicode字符在中文Windows崩溃→已替换为ASCII
- **HuggingFace镜像**: 国内需手动设 `HF_MIRROR=https://hf-mirror.com`
- **评测temperature=0.3**: 边界50-70分段区分力弱，未校准
- **30%引用阈值**: 无实证校准数据
- **向量检索**: 单文本索引，未模拟竞品竞争环境

---

## 5. 会话协作规则

### 核心约定
1. **启动项目**: 运行后端 `python run.py`（端口8000） + 前端 `npx vite --port 5173`（若被占则5174）
2. **切换目录**: 所有命令使用绝对路径，base = `c:\Users\Administrator\Desktop\GEO生成式搜索优化轻量化技术方案\geo-optimizer`
3. **语法检查**: 修改Python后运行 `python -c "import py_compile; py_compile.compile('file.py', doraise=True)"`
4. **代码编辑**: 优先 Edit 工具（精确替换），其次 Write（新文件/完整重写）；修改前必先 Read
5. **前后端重启**: 后端改代码后自动reload；前端改代码后HMR自动更新；新增路由/依赖需手动重启

### 命令约定
- Shell 使用 bash 语法（正斜杠路径，`/dev/null` 非 `NUL`）
- 并行独立任务用多个 Bash 调用（单消息中并行）
- 后续任务用 `&&` 串联
- 后台任务用 `run_in_background: true`

### 排查优先级
1. 先检查文件是否存在 → Glob
2. 再检查内容 → Grep
3. 然后阅读 → Read
4. 最后执行 → Bash

### 质量标准
- 所有用户可见的API错误必须显示 server detail（非 "操作失败" 通用消息）
- 所有删除/不可逆操作必须有确认对话框
- 所有异步操作必须有 loading 态 + 错误态
- 默认不写注释（除非 WHY 非显而易见）
- 不引入不必要的抽象（三个相似行优于过早抽取）

### 禁止操作
- 不执行 `git` 命令（除非用户明确要求）
- 不修改 `config/api_keys.yaml` 中的真实密钥（已移至 `.env`）
- 不在 Vue 模板中使用 `v-html` 而不先 HTML 转义
- 不静默吞异常

### AI 开发专属约束

1. **全沙盘覆盖**: 所有代码迭代必须覆盖 8 类沙盘业态。新增 Prompt 模板、Schema 映射、API 参数时必须验证 8 种 `SandtableType` 均能正常工作。禁止仅针对单一沙盘类型开发。
2. **四门策略锚定**: 所有功能开发必须明确服务于"抓取→理解→引用→推荐"四门策略中至少一门。无业务目标的功能不引入。
3. **国内镜像优先**: 禁止在代码中写死 `https://huggingface.co` 官方域名。所有模型下载/HF Hub 调用必须通过 `HF_ENDPOINT` 环境变量或 `settings.yaml:embedding.hf_endpoint` 配置。
4. **配置禁止硬编码**: 企业名、地域、LLM base_url、模型名等参数必须从 `settings.yaml` 读取，通过 `config.py:load_settings()` 注入。参考实现：`api_keys.yaml` 的 `${VAR}` 占位符模式。
5. **上下文溢出归档规范**: 每次功能迭代完成后必须同步更新 CLAUDE.md：
   - 新增功能 → 追加到"已完成功能"对应轮次
   - 修复 Bug → 从"待办任务"移至"已完成功能"并标注轮次
   - 新发现技术债 → 追加到"现存临时方案/技术债"
   - 新增关键配置 → 更新对应章节的配置说明

### 长期迭代上下文管理

- **CLAUDE.md 为项目唯一真相源**: 所有架构决策、编码规范、待办优先级、技术债以此文件为准。口头约定不具效力。
- **功能新增后**: 更新"已完成功能"清单（第 4 章），标注轮次和日期。
- **Bug 修复后**: 从"待办任务"表格移至"已完成功能"对应轮次。
- **新发现的技术债**: 追加到第 4 章"现存临时方案/技术债"，标注发现日期。
- **配置变更**: 同步更新第 1 章环境变量、第 2 章 settings.yaml 示例、第 7 章部署清单。
- **文档膨胀控制**: CLAUDE.md 不超过 1000 行。接近上限时，将"已完成功能"历史轮次和"平台特性"细节移至 `docs/` 目录，本文档保留摘要 + 链接。

---

## 6. 历史约定与特殊逻辑

### 评测引擎边界规则
- 空文本（<50字符）直接返回 overall_score=0，不走评测流程
- source_consistency < 30 时 overall 硬上限 50.0（防幻觉）
- `_diagnose`(旧) 和 `_diagnose_v2`(新) 并存——新功能用v2，旧路径未迁移

### 改写引擎边界规则
- 信源忠实原则（硬约束）：严禁编造量化数据、客户案例、认证证书
- 事实边界：只能使用五维输入中已有的事实，不得扩展
- 后处理校验：企业名必须在文本中（否则warning）；优化后字数变化>90%触发warning
- 企业名检测允许简称匹配（如"微艺达"匹配"武汉微艺达"）

### 平台特性
- **DeepSeek**: RAG检索优先、FAQ问答格式召回率最高、200-300字自包含chunk
- **豆包**: 短句（≤30字）、消费级语感、口语化
- **元宝**: 政企采购流程化文档、注重资质/案例/流程
- **Kimi**: 长文生成（1500-2500字）、深度分析偏好
- **文心一言**: 百度卡片友好、标题遵循"地名+产品+厂家"格式
- **通义千问**: 结构化+技术参数表偏好
- **讯飞星火**: 教育/科研场景、技术深度优先

### 沙盘类型与Schema映射
- smart_traffic/smart_city/smart_industry/smart_agriculture/smart_logistics → Product + Service + Organization
- military_terrain → Product + EducationalProduct + Organization
- digital_multimedia → Product + SoftwareApplication + CreativeWork
- real_estate → Service + RealEstateService + Project + Place

### 数据持久化
- 评测历史: `data/evaluations/{session_id}.json` (Pickle序列化)
- 平台规则: `data/platform_rules/{platform_id}.json`
- 竞品数据: `data/competitors/{comp_id}.json`
- 关键词库: `data/keywords/{sandtable_type}.json`
- 前端状态: `sessionStorage` (Pinia store 300ms防抖自动保存)
- 缓存: `data/cache/` (文件系统KV，TTL由cache.py控制)

### 评测维度默认权重
| 维度 | 权重 |
|------|------|
| brand_recall (品牌召回) | 20 |
| solution_match (方案匹配) | 20 |
| advantage_citation (优势引用) | 15 |
| real_citation (真实采信) | 15 |
| structure_quality (结构质量) | 10 |
| differentiation (差异化程度) | 10 |
| source_consistency (信源一致性) | 10 |

### 诊断五维（独立于评测七维）
- entity_completeness (实体完整性)
- structure_quality (结构化程度)
- quantified_data (量化数据)
- faq_friendliness (FAQ友好度)
- source_credibility (信源可信度)

### AI采信六原则（嵌入改写Prompt）
1. 实体锚定 — 企业名/地域/产品名完整清晰
2. 定义优先 — 专业概念给出权威定义
3. 量化事实 — 所有能力用数字支撑
4. FAQ结构 — 嵌入自然问答对
5. 层级结构化 — H2/H3 + 列表
6. 信息增量 — 本地化细节 + 行业独特信息

### 已知不完美但有意保留
- `LayoutShell.vue:172` 直接使用 `axios.post` 绕过了配置的api实例（因为需要特殊配置）
- `_diagnose`/`_diagnose_v2` 双路径（历史兼容，渐进迁移中）
- 前端 `sandtableTypes`/`availablePlatforms` 常量在4个文件重复（计划抽取为共享常量）
- CORS来源硬编码在 `main.py:80`（包括5173和5174两个前端端口）

---

## 7. 国内部署与环境适配

### HuggingFace 镜像适配体系

国内访问 HuggingFace 官方域名的常见问题：DNS 污染导致下载超时、跨境带宽限制导致 1.3GB 模型下载中断、403 Forbidden、TCP 连接重置。本项目已集成完整镜像适配方案。

**当前实现**:
- `main.py:12-14`: 模块级 `os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")` + `HF_HUB_ENDPOINT`，在 sentence-transformers 等任何 HF 库 import 之前执行
- `embedding_svc.py:59`: 显式 `snapshot_download(endpoint=...)` 指向 HF_ENDPOINT
- `embedding_svc.py:84-85`: settings.yaml `hf_endpoint` fallback（当环境变量不存在时）
- `embedding_svc.py:109-114`: ModelScope 作为 HF 镜像的备选下载源

**四种镜像使用方案**:

```bash
# 方案一：环境变量临时配置（当前会话有效）
export HF_ENDPOINT=https://hf-mirror.com
python run.py

# 方案二：环境变量永久配置（推荐生产环境）
# Linux: echo 'export HF_ENDPOINT=https://hf-mirror.com' >> ~/.bashrc
# Windows: setx HF_ENDPOINT "https://hf-mirror.com"

# 方案三：huggingface-cli 下载（离线后使用）
huggingface-cli download BAAI/bge-large-zh-v1.5 \
  --local-dir ./data/cache/models/bge-large-zh-v1.5 \
  --endpoint https://hf-mirror.com

# 方案四：hfd 高速下载（aria2c 多线程加速）
# pip install hfd
# hfd BAAI/bge-large-zh-v1.5 --tool aria2c -x 4 --endpoint https://hf-mirror.com
```

**gated model 国内下载兜底**: 对于需授权的模型（gated/private），HF 镜像可能无权代理。兜底方案：先通过 ModelScope（`modelscope.cn`）搜索同名模型 → `snapshot_download` from modelscope → 失败则回退 HF 镜像 + `token` 参数。此级联已在 `embedding_svc.py:109-129` 实现。

### 系统编码与兼容兜底

```bash
# 解决中文路径/日志乱码（Windows 必须）
export PYTHONIOENCODING=utf-8

# 防企业代理/防火墙拦截模型下载请求
export NO_PROXY=localhost,127.0.0.1,hf-mirror.com,modelscope.cn

# 解决 PyTorch + scikit-learn OpenMP DLL 冲突（Windows 必须，已在 run.py:9 设置）
export KMP_DUPLICATE_LIB_OK=TRUE
```

**Windows 专项**:
- `KMP_DUPLICATE_LIB_OK=TRUE`: 解决 PyTorch libiomp5md.dll 与 scikit-learn libiomp5md.dll 冲突，不设置会导致进程崩溃（segfault）。`run.py:9` 已模块级注入。
- `PYTHONIOENCODING=utf-8`: 解决中文 print/logging 输出在 GBK 终端乱码崩溃。
- `print()` 禁用非 ASCII: Windows cmd 默认 GBK 编码，`print("中文")` 直接抛出 UnicodeEncodeError。项目已全局替换为 `logging`。

### 模型下载离线兜底

模型加载 4 步级联（`embedding_svc.py:69-157`）：

1. **本地路径检查** (line 99-102): `settings.yaml:embedding.local_model_path` 配置项，若目录存在直接加载
2. **本地缓存搜索** (line 105-106): `_find_local_model()` 遍历 `cache_dir` 查找含 `pytorch_model.bin` 或 `model.safetensors` 的目录，兼容 ModelScope 命名（`.` → `___`）
3. **ModelScope 下载** (line 109-114): 尝试 `modelscope.snapshot_download`，国内免代理高速下载
4. **HF 镜像下载** (line 117-129): `huggingface_hub.snapshot_download(endpoint=HF_ENDPOINT)`，失败则抛出含手动下载指引的 RuntimeError

首次运行时 `startup_embedding_check()`（`main.py:111-126`）触发模型预热。**失败非致命** — 服务器正常启动，仅向量相关功能降级不可用。

手动离线部署流程：
```bash
# 1. 在有网络的机器上下载模型
huggingface-cli download BAAI/bge-large-zh-v1.5 \
  --local-dir ./bge-large-zh-v1.5 \
  --endpoint https://hf-mirror.com

# 2. 拷贝到目标服务器
scp -r ./bge-large-zh-v1.5 user@server:/path/to/geo-optimizer/backend/data/cache/models/

# 3. 在 settings.yaml 中配置本地路径
# embedding.local_model_path: "./data/cache/models/bge-large-zh-v1.5"

# 4. 启动时自动检测本地模型（local_files_only=True）
python run.py
```

### 国内服务器部署清单

**环境要求**:
- OS: CentOS 7+ / Ubuntu 18.04+ / Windows Server 2016+ / Windows 11
- Python: 3.10+
- Node.js: 18+
- 磁盘: ≥5GB 空闲（含 1.3GB 模型文件）
- 内存: ≥4GB（PyTorch CPU 推理）

**部署步骤**:
```bash
# 1. 克隆/拷贝项目
cd /opt/geo-optimizer

# 2. 安装 Python 依赖
cd backend && pip install -r requirements.txt

# 3. 配置 API 密钥
cp .env.example .env
# 编辑 .env，填入至少一个平台的 API Key（推荐 DeepSeek）

# 4. 设置国内镜像（永久）
export HF_ENDPOINT=https://hf-mirror.com
export PYTHONIOENCODING=utf-8
# 或写入 ~/.bashrc / /etc/environment

# 5. 首次启动（自动下载模型，约 3-10 分钟）
python run.py
# 日志会显示: "正在预加载向量模型（首次运行可能需下载约1.3GB模型文件）..."

# 6. 前端部署
cd ../frontend && npm install && npm run build
# 静态文件在 dist/ 目录，挂载到 nginx 或直接 npx vite preview
```

**验证部署**:
```bash
# 后端健康检查
curl http://127.0.0.1:8000/api/analytics/overview

# 前端访问
# 开发模式: http://localhost:5173
# 生产模式: nginx 反向代理 dist/ → http://your-server-ip
```

### 内网/离线环境注意事项

- 无互联网时：提前在有网机器下载模型 → 离线拷贝 + `local_model_path` 配置 → 启动时 `local_files_only=True`
- 企业代理拦截：设置 `NO_PROXY` 排除镜像站和 LLM API 域名
- LLM API 调用：所有 LLM 平台的 API 调用均为出站 HTTPS（443 端口），确保防火墙放行 `api.deepseek.com`、`api.moonshot.cn` 等域名
- 前端 Vite 开发代理：`vite.config.ts` 将 `/api` 代理到 `http://127.0.0.1:8000`，生产环境需 nginx `proxy_pass`

---

## 8. AI 幻觉抑制体系

### 6 层防线架构

| 层级 | 机制 | 位置 | 说明 |
|------|------|------|------|
| **L1 源数据清洗** | 五维信息提取 | `cleaner.py` | 从原始文本提取核心优势/适用场景/技术特征/服务能力/落地价值，作为后续改写的事实锚点 |
| **L2 Prompt 硬约束** | 信源忠实原则 | `rewrite.py:210-217` | 严禁编造：量化数据、客户名称/项目案例、未授权服务能力、行业排名/对比、资质认证 |
| **L3 事实边界** | 五维输入限定 | `rewrite.py:252-267` | 只能使用 L1 提取的五维事实数据，不得扩展。企业名/地域不可变更，经营范围不可扩大 |
| **L4 后处理校验** | 5 项程序化检测 | `rewriter.py:233-291` | ①企业名存在性（否则自动 prepend）②地域标识检测 ③量化数据 regex 匹配（4 种模式）④五维信息覆盖度 ⑤字数波动（>90% 触发 warning） |
| **L5 评测硬阈值** | source_consistency 门禁 | `evaluator.py:544-547, 727-776` | LLM 独立评分 5 子维度（实体一致性/数据真实性/能力边界/客户真实性/排名可信度），<30 分时 overall 硬上限 50.0 |
| **L6 诊断警告注入** | 零号位 warning | `evaluator.py:813-816` | source_consistency 低于 30 时，在 `weak_points` 数组第 0 位注入高风险警告："信源一致性严重偏低，存在 AI 编造风险" |

### 关键阈值与参数

| 参数 | 值 | 位置 | 说明 |
|------|-----|------|------|
| 空文本最小长度 | 50 字符 | `evaluator.py`, `settings.yaml:text_processing.min_cleaned_length` | 低于此值直接返回 overall_score=0 |
| source_consistency 硬底 | < 30 → overall ≤ 50 | `evaluator.py:544-547` | 防幻觉的核心门禁 |
| LLM 幻觉检测温度 | 0.2 | `evaluator.py` source_check 调用 | 低温度降低评测 LLM 自身随机性 |
| 量化数据 regex | 4 种模式 | `rewriter.py:263-271` | 数字+单位、比例、百分比、精度单位 |
| 字数波动 warning 阈值 | >90% | `rewriter.py` | 改写后字数与原始文本差异超过 90% 触发 |
| 真实引用阈值 | 30% | `evaluator.py:667` | 实体重叠率低于 30% 视为引用无效 |
| 企业名匹配 | 精确+简称 | `rewriter.py` | "微艺达" 可匹配 "武汉微艺达智能科技有限公司" |

### 幻觉抑制设计原则

1. **多层纵深防御**: 不依赖单一防线。L1-L3 从源头限制 LLM 输出范围，L4-L5 从结果端检测并量化，L6 将检测结果反馈给用户。
2. **程序化 + LLM 双重校验**: L4 用正则和字符串匹配（确定性、零成本），L5-L6 用 LLM 语义评判（灵活性、覆盖边界情况）。
3. **硬限制优于软警告**: L5 的 `overall ≤ 50` 硬门禁直接改变评分，使幻觉内容无法通过评测"及格线"，比单纯警告更有效。
4. **温度梯度控制**: 改写 LLM 使用较高温度（creative），但幻觉检测 LLM 使用低温度（0.2），减少评测侧自身的不确定性。

---

## 9. 竞品对抗 GEO 优化体系

### 模块架构

竞品调研模块（`competitors.py` + 前端 `StrategyCenter.vue` 竞品调研 Tab）提供完整的竞品分析到差异化注入的闭环：

```
竞品CRUD (competitors.py:41-105)
  ↓ 竞品快照 (competitors.py:108-129)
记录竞品在某AI平台上的引用状态（时间/平台/查询词/引用片段）
  ↓ LLM对比分析 (competitors.py:132-168)
≥2个竞品 → 结构化对比矩阵 → LLM 生成分析/优劣势/机会/建议（JSON解析 + fallback）
  ↓ 差异化注入 (rewrite.py:343-353 + rewriter.py)
竞品分析结果 → optimization_hints → 改写 Prompt 自动追加"重点优化指令"
  ↓ 差异评估基线 (evaluation.py:79-105)
7维评测中 differentiation 维度以行业惯常水平为基线（非绝对理想），量化差异化程度
```

### 核心能力

| 能力 | API 端点 | 说明 |
|------|----------|------|
| 竞品 CRUD | `GET/POST/PUT/DELETE /api/competitors/` | JSON 文件存储（`data/competitors/{comp_id}.json`），auto-generated ID |
| 竞品快照 | `POST /api/competitors/{id}/snapshot` | 记录特定时间/平台/查询词的引用状态，含 `citation_found` bool + 片段 |
| LLM 对比 | `POST /api/competitors/compare` | 构建竞品矩阵 → LLM 输出 JSON（分析/优劣势/机会/建议），正则提取 JSON + fallback 纯文本 |
| 报告导出 | `POST /api/competitors/report` | Markdown 格式报告：基本信息 + AI 平台曝光表 + 内容特征表 + 最近 5 个快照 |
| 差异化注入 | 改写流程自动化 | 评测结果作为 `optimization_hints` 注入下一轮改写 Prompt（`rewrite.py:343-353`，"重点优化指令（必须执行）" header） |

### 竞品对抗策略

1. **AI 平台覆盖矩阵**: 跟踪竞品在各大 AI 平台的引用状态，识别覆盖盲区。
2. **内容差异化**: LLM 对比分析竞品内容特征（技术深度/案例丰富度/结构化程度），定位差异点。
3. **改写 Prompt 注入**: 差异化特征通过 `optimization_hints` 机制注入改写 Prompt，LLM 强制遵守（"必须执行"）。
4. **差异化评估**: 评测 differentiation 维度以行业基线为参照，评估差异化程度而非绝对质量。
5. **持续监控**: 快照系统支持时间线追踪，检测竞品优化动作和市场变化。
