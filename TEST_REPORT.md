# GEO 生成式搜索优化系统 — 综合测试报告

**测试日期**: 2026-05-29
**测试范围**: 全业务链路 / 全功能模块 / 安全与规范 / 容错与并发
**系统版本**: 第四轮迭代后

---

## 一、测试概览

| 项目 | 数值 |
|------|------|
| 被测 API 端点 | 57 |
| 直接测试覆盖端点 | 28 |
| 代码静态分析文件 | 15+ |
| 发现 P0 崩溃级 Bug | **3** |
| 发现 P1 严重缺陷 | **5** |
| 发现 P2 一般缺陷 | **4** |
| 发现 P3 体验优化 | **5** |

---

## 二、P0 — 崩溃级 Bug（必须立即修复）

### P0-1: 关键词添加端点 NameError 崩溃

- **位置**: `backend/app/api/keywords.py:126`
- **现象**: `POST /api/keywords/{sandtable_type}` 始终返回 500 Internal Server Error
- **原因**: 第 126 行引用 `category` 变量但未定义，应为 `req.category`
- **影响**: **关键词库完全无法添加新词**，核心功能阻断
- **复现**: `curl -X POST /api/keywords/smart_traffic -d '{"word":"测试","category":"brand","weight":"8","status":"pending"}'`

### P0-2: 报表生成端点 NameError 崩溃

- **位置**: `backend/app/api/reports.py:72`
- **现象**: `POST /api/reports/generate-from-data` 始终返回 500
- **原因**: 第 72 行引用 `report_format` 变量但未定义，应为 `data.format`
- **影响**: **数据报表生成功能完全不可用**
- **复现**: 调用 generate-from-data 端点即崩溃

### P0-3: 信息提取端点 AttributeError 崩溃

- **位置**: `backend/app/api/cleaning.py` extract 端点处理函数
- **现象**: `POST /api/cleaning/extract` 始终返回 500
- **原因**: `SandtableType.smart_traffic` — 枚举值通过属性访问而非构造器 `SandtableType("smart_traffic")`
- **影响**: **五维信息提取功能不可用**，影响改写前的内容分析链路
- **复现**: `curl -X POST /api/cleaning/extract -d '{"content":"武汉微艺达专注智慧交通沙盘"}'`

---

## 三、P1 — 严重缺陷（影响功能正确性）

### P1-1: 评测信源一致性持续为 0

- **位置**: `backend/app/core/evaluator.py` source_consistency 评测逻辑
- **现象**: 最近 24 条评测的 source_consistency 平均仅 17.6 分，大量评测该维度为 0 分，触发 overall ≤ 50 硬阈值
- **影响**: 平均综合得分仅 49.0 分，几乎所有评测都被锁死在 50 分以下，评测区分度丧失
- **需要排查**: LLM 调用是否成功返回、评分 Prompt 是否合理、得分解析是否有 Bug

### P1-2: 企业名称硬编码在 8+ 处

- **位置**: `backend/app/core/evaluator.py:146,150,513,528,649,744,774,828`
- **现象**: `enterprise_name="武汉微艺达智能科技有限公司"` 以字面量形式散布在评测引擎各处
- **影响**: 更换企业客户需修改 8+ 处源代码，且 `config.py:get_enterprise_name()` 已存在但未被使用

### P1-3: 流式改写跳过输出校验

- **位置**: `backend/app/core/rewriter.py:178-245`
- **现象**: `stream_rewrite()` 方法不调用 `_validate_output()`，而批量改写 `_rewrite_one()` 会调用
- **影响**: SSE 流式改写输出未经过企业名存在性、量化数据、字数波动等校验，可能输出不合规内容

### P1-4: 文心一言 Token 永不过期

- **位置**: `backend/app/services/llm/wenxin.py:22-38`
- **现象**: 百度 OAuth Access Token 缓存后永不过期，不检测 401 响应也不自动刷新
- **影响**: 服务运行超过 30 天后文心一言调用全部失败（401），需手动重启

### P1-5: 多个 LLM 平台静默失败

- **位置**: 后端 LLM 调用链路
- **现象**: 豆包、文心一言、通义千问三个平台改写返回空文本（word_count=0），仅 DeepSeek 和 Kimi 正常
- **影响**: 56 套 Prompt 矩阵中仅约 16 套实际可用（2 平台 × 8 沙盘），其他平台可能因 API Key 未配置或调用失败而无提示
- **建议**: 无 API Key 时返回明确错误而非空文本

---

## 四、P2 — 一般缺陷（功能边界/数据质量）

### P2-1: 文本清洗对无意义输入产生幻觉

- **现象**: 输入纯数字 `"1234567890"` 时，清洗引擎（基于 LLM）编造出完整的企业描述
- **影响**: 恶意或无意义输入可能污染后续改写/评测数据
- **建议**: 增加输入有效性预检（如中文字符占比、实体识别），不达标时拒绝处理而非编造

### P2-2: 平台监测对无效 ID 返回假数据

- **现象**: `GET /api/platform-monitor/platforms/nonexistent` 返回 200 + 空平台数据，而非 404
- **影响**: 前端无法区分"平台数据为空"和"平台不存在"

### P2-3: 竞品快照接受空 Payload

- **现象**: `POST /api/competitors/{id}/snapshot` 接受 `{}` 空对象，创建 platform/query 均为空串的幽灵快照
- **影响**: 竞品时间线被无意义记录污染，对比分析数据质量下降

### P2-4: 边缘输入无法识别沙盘类型

- **现象**: XSS 注入、Emoji、极短文本等输入清洗后 `detected_type=None`
- **影响**: 下游改写/评测缺少沙盘类型上下文
- **建议**: 类型检测失败时回退到用户手动指定，而非静默返回 None

---

## 五、P3 — 体验优化（非阻塞）

### P3-1: 评测维度权重两处维护

- **位置**: `evaluator.py:_calculate_overall_v2` + `eval_dimensions.py:DEFAULT_WEIGHTS`
- **风险**: 修改权重时需同步两处，不一致会导致流式/非流式评测结果分歧

### P3-2: 缓存读取无锁

- **位置**: `backend/app/utils/cache.py:34-49`
- **现象**: `get()` 方法读写文件不加 `_write_lock`，Windows 上 `os.replace()` 非完全原子，并发时可能读到截断文件

### P3-3: EscapeHtml 依赖浏览器 DOM

- **位置**: `frontend/src/views/GEOWorkshop.vue:434`
- **现象**: `escapeHtml()` 使用 `document.createElement`，SSR 或测试环境会抛异常

### P3-4: 前端 StrategyCenter.vue 逼近 1400 行

- **风险**: 超过 500 行编码规范上限近 3 倍，维护困难
- **建议**: 拆分 Tab 内容为独立组件

### P3-5: 前端 502 Bad Gateway

- **现象**: Vite 开发服务器（5173/5174）代理后端请求返回 502
- **排查方向**: Vite 代理配置或后端重启后连接池未恢复

---

## 六、验证通过项

### 核心流水线

| 功能 | 状态 | 备注 |
|------|------|------|
| 文本清洗 (clean) | **PASS** | 正常提取并清洗文本 |
| 文本清洗 (extract) | **FAIL** | P0-3 崩溃 |
| GEO 改写 - DeepSeek | **PASS** | FAQ 格式正确，字数 2269，RAG 分块良好 |
| GEO 改写 - Kimi | **PASS** | military_terrain 沙盘适配正确，字数 1195 |
| GEO 改写 - 豆包 | **FAIL** | 返回空文本（可能是 API Key 问题） |
| GEO 改写 - 文心一言 | **FAIL** | 返回空文本 |
| GEO 改写 - 通义千问 | **FAIL** | 返回空文本 |
| JSON-LD - smart_traffic | **PASS** | Schema: Product+Service+Organization |
| JSON-LD - military_terrain | **PASS** | Schema: Product+EducationalProduct+Organization |
| JSON-LD - digital_multimedia | **PASS** | Schema: Product+SoftwareApplication+CreativeWork |
| JSON-LD - real_estate | **PASS** | Schema: Service+RealEstateService+Project+Place |
| JSON-LD 校验 | **PASS** | 所有类型 validation_passed=True |
| 7 维评测 SSE | **PASS** | 11 events, 9 phases 全链路推送正常 |
| 内容诊断 | **PASS** | 5 维评分合理（overall 63.0） |
| 报表预览 | **PASS** | 生成 211KB HTML 报告 |
| 报表生成 | **FAIL** | P0-2 崩溃 |

### 策略中心模块

| 功能 | 状态 | 备注 |
|------|------|------|
| 平台规则列表 | **PASS** | 12 平台正常返回 |
| 平台规则详情 | **PASS** | 但无效 ID 不返回 404 (P2-2) |
| 关键词列表 | **PASS** | 按分类/沙盘正确分组 |
| 关键词添加 | **FAIL** | P0-1 崩溃 |
| 关键词 LLM 扩展 | **PASS** | 扩展结果正常返回 |
| 关键词 CSV 导出 | **PASS** | 格式正确 |
| 竞品列表 | **PASS** | 3 个竞品正常加载 |
| 竞品 CRUD | **PASS** | 创建/读取正常 |
| 竞品快照 | **PASS** | 但接受空 payload (P2-3) |

### 安全与容错

| 测试项 | 状态 | 备注 |
|------|------|------|
| XSS 注入检测 | **PASS** | 正确识别并拒绝 |
| SQL 注入防护 | **PASS** | Pydantic 校验层拦截 |
| 空输入校验 | **PASS** | 422 返回 field required |
| Emoji/Unicode 处理 | **PASS** | 正常处理不崩溃 |
| 5 并发读取 | **PASS** | 0.26s 全部 200 OK |
| Pydantic 参数校验 | **PASS** | 28/28 端点已迁移 |
| API Key 隔离 | **PASS** | .env + ${VAR} 机制正常 |

### 幻觉抑制体系

| 防线 | 状态 | 备注 |
|------|------|------|
| L1 源数据清洗 | **PASS** | 五维提取正常 |
| L2 Prompt 硬约束 | **PASS** | 改写输出包含信源忠实声明 |
| L3 事实边界 | **PASS** | DeepSeek 输出未编造虚假客户名 |
| L4 后处理校验 | **PARTIAL** | 批量改写校验正常，流式改写跳过 (P1-3) |
| L5 评测硬阈值 | **PASS** | source_consistency<30 → overall≤50 正确触发 |
| L6 诊断警告 | **PASS** | 硬阈值触发时输出风险标注 |

---

## 七、统计数据

| 指标 | 数值 |
|------|------|
| 评测总数 | 24 |
| 综合平均分 | 49.0 |
| 品牌召回均分 | 56.6 |
| 方案匹配均分 | 57.0 |
| 优势引用均分 | 61.9 |
| 结构质量均分 | 83.4 |
| 差异化均分 | 65.1 |
| 真实采信均分 | 26.8 |
| E-E-A-T 均分 | 56.4 |
| 信源一致性均分 | **17.6** |
| 可用 LLM 平台 | 2/7 (DeepSeek, Kimi) |
| 沙盘适配覆盖 | 4/8 类型已测试 JSON-LD |

---

## 八、修复优先级建议

### 立即修复（阻塞上线）

1. **keywords.py:126** — `category` → `req.category`
2. **reports.py:72** — `report_format` → `data.format`
3. **cleaning.py extract** — `SandtableType.smart_traffic` → `SandtableType("smart_traffic")`

### 上线前修复（影响核心体验）

4. 排查并修复 source_consistency 评测逻辑（持续为 0 的问题）
5. 将硬编码企业名统一迁移至 `config.get_enterprise_name()`
6. 流式改写补全 `_validate_output` 调用
7. 无 API Key 的平台返回明确错误而非空文本

### 迭代优化（不影响上线）

8. 文本清洗增加输入有效性预检
9. 平台监测/竞品快照补全参数校验
10. 缓存并发读加锁
11. StrategyCenter.vue 拆分组件
