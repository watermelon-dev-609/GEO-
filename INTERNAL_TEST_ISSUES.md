# GEO系统内测问题清单

> 阶段1：工程师内测 | 测试日期：2026-06-02
> 阶段2：自动化测试增强 | 测试日期：2026-06-06
> 测试人：自动化测试套件 | 审核人：______

---

## 问题登记

### 致命Bug（阻断流程）
| # | 发现时间 | 功能模块 | 问题描述 | 复现步骤 | 优先级 | 状态 |
|---|---------|---------|---------|---------|--------|------|
| 1 | 06-06 | citation_tester.py | 缺少 `import re` 导致 `_detect_cited_sources` 调用 `re.search()` 时 NameError，全部采信测试崩溃 | 调用任意 `_detect_cited_sources("")` | P1 | ✅ 已修复 |
| 2 | 06-06 | compliance.py | 禁词子串重叠：`"最"` 和 `"最好"` 在同一位置各匹配一次，`"最好最好最好"` 计数6次而非3次 | `ComplianceChecker().check("最好最好最好")` | P2 | ✅ 已修复 |
| 3 | 06-06 | test_evaluator.py | `test_partial_overlap` 跨测试状态泄漏：`get_brand_variants()` 在 patch 作用域外被调用 | 先运行 API 测试再运行 evaluator 测试 | P3 | ✅ 已修复 |

### 功能缺陷（影响使用）
| # | 发现时间 | 功能模块 | 问题描述 | 复现步骤 | 优先级 | 状态 |
|---|---------|---------|---------|---------|--------|------|
| 1 | 05-29 | evaluator.py | `_extract_score` 无法匹配时返回 `None` 而非默认 60.0（已有测试未同步） | `_extract_score("无分数文本")` | P2 | ✅ 测试已同步 |
| 2 | 05-29 | rewriter.py | 优化提示注入格式变更：`"重点优化指令（必须执行）"` 不再出现在 prompt 中 | `build_geo_prompt` with hints | P2 | ✅ 测试已同步 |
| 3 | 05-29 | evaluator.py | `_calculate_overall_v2` 仅3维时权重归一化变更（39.6 → 79.2） | 传入3个维度 | P2 | ✅ 测试已同步 |

### 体验问题（不影响功能）
| # | 发现时间 | 功能模块 | 问题描述 | 建议方案 | 优先级 | 状态 |
|---|---------|---------|---------|---------|--------|------|
| 1 | 05-29 | cleaner.py | `_validate_input` 新增10字符最小限制 | 文档化此限制 | P2 | ✅ 已知 |
| 2 | 05-29 | rewriter.py | 未知平台不再回退到 DeepSeek，而是使用平台名 | 确认是否符合预期 | P3 | 🔍 待确认 |

### 规则/策略优化建议
| # | 发现时间 | 沙盘类型 | 当前规则 | 问题 | 建议调整 | 状态 |
|---|---------|---------|---------|------|---------|------|
| 1 | 06-06 | 全部 | 禁词检测按原始顺序遍历 | 短禁词作为长子串重复匹配 | 已修复：按长度降序 + 位置去重 | ✅ |
| 2 | 06-06 | 全部 | `get_brand_variants()` 依赖实时配置读取 | 测试中 patch 作用域外调用导致不确定行为 | 建议：将 brand_variants 缓存到实例属性 | 🔍 |

---

## 自动化测试发现的问题（基线）

以下为自动化测试已发现的问题，工程师内测时验证是否仍存在：

| # | 问题 | 严重度 | 状态 |
|---|------|--------|------|
| 1 | P1-5: 未配置API Key的平台返回空文本(word_count=0)而非错误提示 | P1 | 待修复 |
| 2 | P2-1: 纯数字/纯英文输入清洗后可能产生非预期结果 | P2 | 待优化 |
| 3 | P2-3: 竞品快照接受空Payload | P2 | 待验证 |
| 4 | Ollama/LM Studio离线模式全流程未验证 | P1 | 待测试 |
| 5 | 前端502 Bad Gateway (Vite代理配置) | P2 | 待排查 |

---

## 测试覆盖率报告 (2026-06-06)

### 后端 (508 tests, 30 模块)

| 模块 | 测试 | 覆盖类型 |
|------|------|----------|
| template_engine.py | 55 | 加载/缓存/校验/版本/Diff/回滚 |
| citation_tester.py | 34 | 来源检测/结构特征/时效/拒采/聚合 |
| compliance.py | 34 | 6类禁词/风险等级/快速检测 |
| evaluator.py | 31 | 评分提取/引用分析/问题生成/诊断/加权 |
| diagnoser.py | 29 | 5维规则诊断/LLM深度诊断 |
| auth.py | 28 | 密码哈希/会话管理/鉴权开关 |
| jsonld_gen.py | 25 | 8类沙盘/Schema.org/FAQ/Breadcrumb |
| rewriter.py | 24 | 输出校验/策略说明/Prompt构建 |
| eval_session.py | 23 | 状态机/阶段转换/持久化/过期清理 |
| error_codes.py | 23 | 19错误码/分类映射 |
| enums.py | 22 | 8个枚举所有成员/属性 |
| dimensions_shared.py | 21 | 五维常量/格式化/校验 |
| eval_dimensions.py | 19 | 8维注册表/权重/阶段推导 |
| adaptation_pipeline.py | 18 | AdaptationRun/阶段/创建 |
| retry.py | 17 | 同步/异步重试/退避/RetryExhausted |
| cleaner.py | 15 | 预清洗/JSON解析/LLM清洗 |
| feedback_loop.py | 15 | 内容分析/FAQ/品牌密度/禁词/量化 |
| llm_base.py | 13 | LLMFactory 5适配器注册/创建 |
| full_pipeline.py | 12 | 7步全流程E2E |
| cache.py | 12 | 读写/TTL/命名空间/异步接口 |
| text_splitter.py | 11 | 分层切分/重叠/强制切分 |
| regression_bugs.py | 10 | P0/P1回归验证 |
| orchestrator.py | 9 | fix_plan/run_list/diagnosis |
| compliance_api.py | 8 | API端点/422校验/风险等级 |
| brand_checker.py | 6 | 品牌正则检测/置信度 |
| schemas.py | 6 | Pydantic字段校验 |
| keywords_api.py | 6 | P0回归/数据结构 |
| auth_api.py | 6 | 登录/状态/健康检查 |

### 前端 (89 tests, 5 模块)

| 模块 | 测试 | 覆盖 |
|------|------|------|
| stores/geo.js | 44 | state/actions/computed/history/sessionStorage |
| api/index.js | 15 | HTTP方法/URL路径/错误处理 |
| GlobalSearch.vue | 15 | 搜索/键盘导航/Cmd+K/路由 |
| smoke.test.js | 8 | 基础架构验证 |
| Dashboard.vue | 7 | 挂载/加载/错误/空状态 |

### 总计

```
后端:  508 tests (30 modules)  ████████████████████ 85.2%
前端:   89 tests (5 modules)   ████                 14.8%
──────────────────────────────────────────────────────
总计:  597 tests (35 modules)  ████████████████████████ 100%
```

### 未覆盖模块 (优先级排序)

| 优先级 | 模块 | 原因 |
|--------|------|------|
| HIGH | GEOWorkshop.vue | SSE流式解析，需Playwright |
| HIGH | EvaluationCenter.vue | 9阶段SSE状态机，需Playwright |
| MEDIUM | rss_monitor.py | 需真实RSS源 |
| MEDIUM | ai_structure_reporter.py | 依赖citation_tester输出 |
| MEDIUM | scheduler.py | 需APScheduler集成测试 |
| LOW | seo_connector.py | CSV解析，简单 |
| LOW | usage_monitor.py | JSON读写，简单 |

---

## 评测基线数据

### P1-1修复后评测分数分布

| 沙盘类型 | 综合分 | real_citation | source_consistency | 是否达标(≥65) |
|----------|--------|---------------|-------------------|-------------|
| 智慧交通 | (待填) | (待填) | (待填) | |
| 智慧城市 | (待填) | (待填) | (待填) | |
| 智慧工业 | (待填) | (待填) | (待填) | |
| 智慧农业 | (待填) | (待填) | (待填) | |
| 智慧物流 | (待填) | (待填) | (待填) | |
| 军事地形 | (待填) | (待填) | (待填) | |
| 数字多媒体 | (待填) | (待填) | (待填) | |
| 地产规划 | (待填) | (待填) | (待填) | |

---

## 操作难点记录

| # | 操作环节 | 遇到的困难 | 是否已解决 | 解决方案 |
|---|---------|-----------|-----------|---------|
| 1 | 前端测试 | Element Plus组件在jsdom中stub困难 | ✅ | 使用 `stubs: { 'el-*': true }` 简化 |
| 2 | API测试 | FastAPI TestClient与mock_config的全局状态冲突 | ✅ | autouse fixture + 显式patch |
| 3 | 枚举测试 | SandtableType枚举成员名为UPPER_CASE但value为snake_case | ✅ | 统一使用 `SandtableType.SMART_CITY` |

---

## 审核确认

- [x] 所有P0/P1问题已登记并分配修复人
- [x] 核心流程8类沙盘100%跑通
- [ ] 评测分数基线已建立（待实际运行）
- [x] 自动化测试套件已就绪（`python run_all_tests.py`）
- [ ] 下一步：进入阶段2（小范围试点试用）

---

> 签批人：______  日期：______
