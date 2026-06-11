# CLAUDE.md — GEO生成式搜索优化系统

## 项目定位

为**武汉微艺达智能科技有限公司**定制的轻量化GEO优化平台。8类沙盘模型（智慧交通/城市/工业/农业/物流/军事地形/数字多媒体/地产）× 11大AI平台的内容采信优化系统。

**四门策略**: 优先抓取 → 优先理解 → 优先引用 → 优先推荐

**核心差异化**: 无数据库（纯JSON文件存储）、单机运行（Python 3.10+ / Node.js 18+）、80套Prompt矩阵（8沙盘×10平台）、8维SSE流式评测、**动态模板引擎（YAML配置热更新）**、**AI采信行为自动化测试**、**适配流水线（灰度发布+回滚）**、**数据闭环仪表盘**、**清洗/优化规则可配置开关**、**转化追踪与UTM归因**

## 启动

```bash
cd backend && python run.py          # → localhost:8000
cd frontend && npx vite --port 5173  # → localhost:5173
```

环境变量: `HF_MIRROR=https://hf-mirror.com`（国内必设）、`KMP_DUPLICATE_LIB_OK=TRUE`（Windows必设）。API密钥通过 `backend/.env` → `config/api_keys.yaml`（`${VAR}`占位符）注入。

## 技术栈

**后端**: FastAPI + Pydantic v2 + httpx + sentence-transformers/FAISS + PyYAML + APScheduler
**前端**: Vue 3 (Composition API) + Vite 6 + Element Plus + Pinia + Axios/Fetch SSE + ECharts
**存储**: 纯JSON文件，路径 `backend/data/`，无数据库依赖

## 目录与路由

```
backend/app/
├── main.py              # FastAPI入口，22个路由前缀注册，4个startup事件
├── api/                 # 22个路由模块（155+端点）
│   ├── cleaning.py, geo_rewrite.py, jsonld.py, evaluation.py, reports.py  # 核心流水线
│   ├── analytics.py, diagnosis.py, platform_monitor.py, keywords.py       # 策略模块
│   ├── competitors.py, templates.py, brand_monitor.py                     # 策略模块
│   ├── batch.py, compliance_api.py, usage.py, auth.py, logs.py            # v2.0
│   ├── audit.py, scheduler_api.py, versions.py, seo.py                   # v2.0
│   ├── template_engine.py  # v2.1 模板引擎CRUD（10端点）
│   ├── adaptation.py       # v2.1 适配流水线（9端点）
│   ├── feedback.py         # v2.1 数据闭环（6端点）
│   ├── traffic.py          # v2.1 流量配置与拉取（GA4/百度统计）
│   └── utm.py, conv_api.py # v2.2 UTM推广计划 + 转化归因（8端点）
├── core/                # 业务引擎（26+模块）
│   ├── cleaner.py, rewriter.py, evaluator.py   # 核心流水线引擎
│   ├── diagnoser.py, jsonld_gen.py, reporter.py # 辅助引擎
│   ├── brand_checker.py, dimensions_shared.py   # 品牌检测 + 共享维度
│   ├── compliance.py, usage_monitor.py, auth.py, audit_logger.py  # v2.0 安全/合规
│   ├── scheduler.py, auto_reporter.py, anomaly_detector.py        # v2.0 自动化
│   ├── version_manager.py, seo_connector.py                       # v2.0 版本/SEO
│   ├── template_engine.py     # v2.1 动态模板引擎（YAML加载/缓存/校验/版本管理/回滚/Diff）
│   ├── rss_monitor.py         # v2.1 RSS信源监控（7信源+关键词告警）
│   ├── citation_tester.py     # v2.1 AI采信行为测试（26问题×5平台）
│   ├── ai_structure_reporter.py  # v2.1 每周结构变化报告生成器
│   ├── adaptation_pipeline.py    # v2.1 适配流水线编排器
│   ├── feedback_loop.py          # v2.1 数据闭环引擎（指标/下降检测/迭代建议）
│   ├── template_watcher.py       # v2.1 watchdog文件监控（实时YAML变更检测+缓存秒级刷新）
│   ├── competitor_monitor.py     # v2.1 竞品自动监控引擎（3天周期+内容探测+规则反推）
│   ├── conversion_attribution.py # v2.2 转化归因引擎（Webhook记录/UTM匹配/漏斗计算）
│   ├── traffic_connector.py      # v2.2 流量数据连接器（GA4/Baidu Tongji API）
│   └── utm_generator.py          # v2.2 UTM参数生成与解析
├── models/enums.py      # SandtableType(8), AIPlatform(11), UserRole(4), EvalDimension(8), EvalPhase(10)
├── models/schemas.py    # 70+ Pydantic v2请求/响应模型
├── services/llm/        # LLM适配器工厂（10个平台，5种适配器）
│   ├── base.py          # LLMFactory注册表 (openai_compat / claude / wenxin / ollama / lmstudio)
│   ├── openai_compat.py # DeepSeek/Kimi/通义/豆包/元宝/星火 (OpenAI兼容协议)
│   ├── wenxin.py        # 文心一言 (OAuth2.0 + IAM认证)
│   ├── claude.py        # Anthropic Claude (Messages API)
│   ├── ollama.py        # Ollama本地部署 (localhost:11434)
│   └── lmstudio.py      # LM Studio本地部署 (localhost:1234)
├── prompts/             # Prompt模板
│   ├── rewrite.py       # 80套改写Prompt（动态加载YAML模板，热更新）
│   ├── evaluation.py    # 8维评测Prompt
│   ├── cleaning.py      # 文本清洗Prompt
│   ├── diagnosis.py     # 内容诊断Prompt
│   └── brand_monitor.py # 品牌监测Prompt
└── utils/               # config.py, cache.py, retry.py, error_codes.py, text_splitter.py

data/
├── platform_templates/  # v2.1 11平台YAML模板配置（base + wenxin/tongyi/doubao/...）
├── template_versions/   # v2.1 模板历史版本存档
├── rss_monitor/         # v2.1 RSS抓取结果
├── citation_tests/      # v2.1 AI采信测试结果
├── structure_reports/   # v2.1 每周结构变化报告
├── adaptation_runs/     # v2.1 适配流水线运行记录
├── feedback_metrics/    # v2.1 每周指标数据
├── evaluations/ platform_rules/ competitors/ keywords/ templates/ cache/
├── output/ brand_mentions/ usage/ audit/ versions/ seo/
└── scheduler_jobs.json reports/ logs/
```

```
frontend/src/
├── views/   # 18页面：Dashboard, ImportView, GEOWorkshop, EvaluationCenter, ExportView,
│            #   StrategyCenter, ContentTemplates, BrandMonitor, BatchView(v2),
│            #   LoginView(v2), LogViewer(v2), AuditLogViewer(v2), SchedulerView(v2),
│            #   SEOIntegration(v2), TemplateEngine(v2.1), AdaptationPipeline(v2.1),
│            #   FeedbackDashboard(v2.1), UTMCampaignManager(v2.2),
│   │            #   FullFunnelDashboard(v2.2), NotFound(404)
├── components/ # 8组件：LayoutShell, GlobalSearch, ErrorTroubleshoot,
│               #   DisclaimerBanner, VersionHistory, DiffViewer,
│               #   CompetitorGapChart, KeywordGroupTree
├── api/index.js  # Axios实例 + SSE工厂 + 90+ API函数
├── stores/geo.js # Pinia状态管理 + sessionStorage持久化
└── router/index.js # 18路由懒加载 + /:pathMatch(.*)* 404
```

## 关键约束（编码时必须遵守）

1. **全8类沙盘兼容**: 任何新功能必须覆盖全部8种SandtableType
2. **配置禁止硬编码**: 平台规则从YAML加载（`data/platform_templates/`），企业名/地域/LLM参数从 `settings.yaml` 读取
3. **API密钥安全**: 用 `${VAR}` 占位符 + `.env`，禁止代码中硬编码
4. **Pydantic v2**: 所有API参数用BaseModel（`| None` 非 `Optional[str]`）
5. **错误提示含detail**: `ElMessage.error('操作失败: ' + (e.response?.data?.detail || e.message))`
6. **SSE不中断**: 纯ASGI中间件（非BaseHTTPMiddleware），异常转SSE事件不抛断
7. **原子写入**: 文件写入用tempfile + os.replace（防并发损坏）
8. **缓存键用md5**: 禁止 `hash()`，用 `hashlib.md5(text.encode()).hexdigest()`
9. **v-html先转义**: `escapeHtml()` 后可用
10. **删除必有确认**: `ElMessageBox.confirm`
11. **Windows兼容**: `print()` 禁止非ASCII（用logging），路径用正斜杠

## 关键逻辑与边界

### 模板引擎（v2.1 核心变革）
- 平台规则从 `rewrite.py` 硬编码 → `data/platform_templates/{platform}.yaml` 配置化
- 60s TTL缓存热更新，改YAML无需重启
- YAML不存在时自动退到 `LEGACY_PLATFORM_RULES` 硬编码
- 结构化组件分解：header/body/data/schema/footer/verification/weights
- 支持模板版本管理：每次PUT自动存档 → 可Diff → 可一键回滚
- `build_geo_prompt()` 优先从 `template_engine.load_platform_rules()` 加载

### 评测引擎
- 空文本(<50字符) → overall_score=0
- source_consistency<30 → overall硬上限50（防幻觉6层防线核心门禁）
- 8维权重: brand_recall(20) + solution_match(20) + advantage_citation(15) + real_citation(15) + structure_quality(10) + differentiation(10) + source_consistency(10) + eeat_score(—)
- 评测temperature分级: source_consistency=0.2, advantage_citation/structure_quality/differentiation/eeat=0.3, real_citation=0.5

### 改写引擎
- 80 Prompt矩阵(8沙盘×10平台)，每平台独立规则集
- 后处理校验: 企业名存在性、地域标识、量化数据regex、五维覆盖度、字数波动
- 信源忠实原则: 严禁编造量化数据/客户案例/认证证书
- **v2.1**: 规则优先从YAML加载，支持热更新

### 规则感知层（v2.1 新增）
- 7大RSS信源监控：百度搜索/百家号/文心博客/头条/豆包/微信/知乎小红书
- 关键词告警：抓取/索引/收录/权重/算法更新
- AI采信测试：26条行业问题 × 5大AI平台 × 4维分析（被引站点/结构特征/时效偏好/拒采模式）
- 每周自动生成《AI抓取结构变化报告》（Markdown含行动清单）

### 适配流水线（v2.1 新增）
- 11阶段流水线：监控发现→需求→模板更新→存量扫描→重生成→校验→抽检→灰度10%→全量→3天测试→7天测试
- 支持灰度发布（10%→100%）和一键回滚
- 自动校验：首段/H标签/FAQ/Schema/禁词/合规

### 数据闭环（v2.1 新增）
- 4核心指标：AI采信率/结构命中率/时效衰减率/违规拒采率
- 采信率下降检测 → 自动回溯监控报告 → 定位结构问题 → 生成迭代建议

### 11大AI平台
| 平台 | 适配器 | 2026.06规则摘要 |
|------|--------|---------------|
| 文心一言 | wenxin | 百家号>搜狐>官网>知乎, 首段70%引用, Schema=Article+Product |
| 通义千问 | openai_compat | 头条>知乎>公众号>官网, 地域关键词前置 |
| DeepSeek | openai_compat | 知乎>公众号>官网>搜狐, FAQ 5-8组, RAG自包含单元 |
| 豆包 | openai_compat | 头条/知乎>小红书>公众号>官网, ≤30字, 15天黄金期 |
| 元宝 | openai_compat | 公众号>官网>知乎>搜狐, 6步合作流程 |
| Kimi | openai_compat | 知乎>公众号>官网>搜狐, FAQ 3-5组, 实体≥5次 |
| 讯飞星火 | openai_compat | 知乎>搜狐>官网>公众号, 技术→场景→价值闭环 |
| Claude | claude | 知乎>公众号>官网>搜狐, 观点→论证→证据→结论 |
| OpenAI GPT | openai_compat | 五维框架, 段落自包含 |
| Ollama | ollama | 本地 localhost:11434, 完全离线 |
| LM Studio | lmstudio | 本地 localhost:1234, OpenAI兼容, 完全离线 |

### 数据持久化
`data/`目录(20+): evaluations, platform_rules, competitors, keywords, templates, cache, output, brand_mentions, usage, audit, versions, seo, logs, reports, scheduler_jobs.json, platform_templates(v2.1), template_versions(v2.1), rss_monitor(v2.1), citation_tests(v2.1), structure_reports(v2.1), adaptation_runs(v2.1), feedback_metrics(v2.1)

## 当前状态

### 已完成（8轮迭代）
- **v1.0 核心**: 文本清洗→GEO改写→JSON-LD→AI评测→报表导出 全链路
- **v1.0 扩展**: 平台监测/竞品调研/关键词库/内容规范/数据看板
- **v1.0 修复**: 安全加固(XSS/APIkey/md5/SSE超时)、18个Pydantic迁移、15+bug修复
- **v2.0 批量**: 批量清洗/优化(SSE)/评测(SSE)/导出(ZIP)/诊断，BatchView页面
- **v2.0 安全**: 合规检测(50+禁词)、用量监控(配额告警)、密码鉴权、审计日志(纯ASGI)
- **v2.0 自动化**: APScheduler定时引擎、周报/月报、收录率异常检测
- **v2.0 增强**: 竞品拆解+雷达图、关键词分组+效果追踪、版本管理(存档/对比/回滚)、SEO集成
- **v2.0 体验**: Cmd+K全局搜索、错误排查弹窗(19错误码)、免责声明、私有化部署(Ollama/LM Studio)
- **v2.1 动态规则引擎**: 平台模板YAML外置化、60s热更新、模板版本管理+Diff+回滚
- **v2.1 规则感知**: 7信源RSS监控+关键词告警、AI采信行为自动化测试、每周结构变化报告
- **v2.1 适配流水线**: 11阶段自动化适配（扫描→重生成→校验→灰度→全量→回滚）
- **v2.1 数据闭环**: 4核心指标仪表盘、采信下降自动检测+回溯+诊断+迭代建议
- **v2.1 全链路实时更新**: watchdog文件监控(替换TTL轮询)、YAML变更→适配自动触发、RSS哈希对比+三级告警(major/moderate/micro)、灰度10%实操(选文+重生成)、竞品自动监控引擎(3天周期+规则反推)
- **v2.2 规则可配置**: 清洗规则5条独立开关、GEO优化规则按平台独立配置(5平台×4-5条)、转化追踪(UTM推广计划/Webhook转化上报/全链路漏斗)、企业官网默认落地页配置

### 待修复（P0）
| 条目 | 位置 |
|------|------|
| ~~并发竞态: sessions dict/JSON写入无锁~~ ✅ 已修复 (asyncio.Lock + threading.Lock + tempfile原子写入) |
| ~~CSV导出逗号转义~~ ✅ 已修复 (csv.QUOTE_NONNUMERIC) |
| ~~analytics days参数未生效~~ ✅ 非Bug (所有评测数据为同日，参数正常工作) |

### 现存技术债
- ~~Claude适配器存在但AIPlatform无条目~~ ✅ 已修复
- ~~五维信息硬编码在5+文件中~~ ✅ 已提取 `dimensions_shared.py`
- ~~PLATFORM_RULES硬编码在Python中~~ ✅ v2.1已外置为YAML配置
- ~~模板缓存TTL轮询(60s)~~ ✅ v2.1已替换为watchdog文件系统事件秒级刷新
- 前端常量(SANDTABLE_TYPES等)4文件重复
- APScheduler绑定单事件循环，进程重启后持久化任务从 `scheduler_jobs.json` 自动恢复
- 评测temperature分级已实施 (source_consistency=0.2, advantage/structure/differentiation/eeat=0.3, real_citation=0.5)
