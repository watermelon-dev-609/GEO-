"""Pydantic请求/响应数据模型"""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from .enums import (
    SandtableType, AIPlatform, UserRole,
    EvalDimension, ContentFormat, ExportFormat,
    EvalPhase, EvalPhaseStatus,
)


# ── 通用 ──

class APIResponse(BaseModel):
    """统一API响应"""
    success: bool = True
    message: str = ""
    data: Optional[dict] = None


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ── 文本清洗 ──

class CleaningRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000, description="待清洗的原始文本（最大50000字符）")
    sandtable_type: Optional[SandtableType] = Field(default=None, description="沙盘业务类型（可选，不填则自动识别）")
    extract_dimensions: bool = Field(default=True, description="是否提取五维信息")
    rules_config: Optional[dict] = Field(default=None, description="清洗规则配置（可选，不传则使用全局配置）")

class CleaningResponse(BaseModel):
    original_text: str
    cleaned_text: str
    dimensions: Optional[dict] = Field(default=None, description="五维信息提取结果")
    detected_type: Optional[SandtableType] = None
    word_count_before: int
    word_count_after: int
    processing_time_ms: float


# ── 清洗规则配置 ──

class CleaningRuleItem(BaseModel):
    """单个清洗规则的配置"""
    key: str = Field(..., description="规则键名")
    label: str = Field(..., description="规则中文名")
    description: str = Field(default="", description="规则说明")
    enabled: bool = Field(default=True, description="是否启用")

class CleaningRulesResponse(BaseModel):
    """清洗规则配置响应"""
    rules: list[CleaningRuleItem]

class CleaningRulesUpdateRequest(BaseModel):
    """更新清洗规则配置"""
    rules: list[CleaningRuleItem] = Field(..., description="更新后的规则列表")


# ── GEO优化规则配置（按平台独立设置）──

class OptimizationRuleItem(BaseModel):
    """单个优化规则的配置"""
    key: str = Field(..., description="规则键名")
    label: str = Field(..., description="规则中文名")
    description: str = Field(default="", description="规则说明")
    enabled: bool = Field(default=True, description="是否启用")

class PlatformOptimizationRules(BaseModel):
    """单个平台的优化规则集合"""
    platform: str = Field(..., description="平台标识")
    rules: list[OptimizationRuleItem]

class OptimizationRulesResponse(BaseModel):
    """优化规则配置响应"""
    platforms: list[PlatformOptimizationRules]

class OptimizationRulesUpdateRequest(BaseModel):
    """更新某平台的优化规则"""
    platform: str = Field(..., description="平台标识")
    rules: list[OptimizationRuleItem] = Field(..., description="该平台的规则列表")


class InfoExtractionResponse(BaseModel):
    sandtable_type: SandtableType
    core_advantages: list[str]      # 核心优势
    applicable_scenarios: list[str]  # 适用场景
    technical_features: list[str]    # 技术特点
    service_capabilities: list[str]  # 服务能力
    implementation_value: list[str]  # 落地价值
    key_phrases: list[str]           # 关键词/短语


# ── GEO文案重构 ──

class RewriteRequest(BaseModel):
    cleaned_text: str = Field(..., max_length=50000, description="清洗后的文本（最大50000字符）")
    sandtable_type: SandtableType = Field(..., description="沙盘业务类型")
    platforms: list[AIPlatform] = Field(..., description="目标AI平台列表")
    dimensions: Optional[dict] = Field(default=None, description="五维信息（可选，用于强化）")
    optimization_hints: list[str] = Field(default_factory=list, description="优化提示（如评测建议）")
    inject_competitors: bool = Field(default=False, description="是否自动注入竞品差异化洞察")
    competitor_insights: Optional[str] = Field(default=None, description="竞品差异化洞察文本")
    optimization_rules: Optional[dict] = Field(default=None, description="优化规则配置（按平台，可选）")
    enterprise_name: str = Field(default="")
    enterprise_location: str = Field(default="")

class PlatformRewriteResult(BaseModel):
    platform: AIPlatform
    optimized_text: str
    strategy_notes: str               # 优化策略说明
    word_count: int
    error: str | None = Field(default=None, description="错误信息（API Key未配置/调用失败等）")

class RewriteResponse(BaseModel):
    sandtable_type: SandtableType
    results: list[PlatformRewriteResult]
    total_time_ms: float


# ── JSON-LD ──

class JSONLDRequest(BaseModel):
    sandtable_type: SandtableType = Field(...)
    enterprise_info: dict = Field(default_factory=dict, description="企业基本信息")
    product_info: dict = Field(default_factory=dict, description="产品/服务信息")
    include_faq: bool = Field(default=True)
    include_breadcrumb: bool = Field(default=True)

class JSONLDResponse(BaseModel):
    sandtable_type: SandtableType
    json_ld_code: str                 # 完整JSON-LD代码
    schema_types_used: list[str]      # 使用的Schema类型列表
    validation_passed: bool           # Schema合规性


# ── AI评测 ──

class EvaluateRequest(BaseModel):
    optimized_text: str = Field(..., min_length=1, max_length=50000)
    original_text: Optional[str] = Field(default=None, max_length=50000)
    sandtable_type: SandtableType = Field(...)
    platforms: list[AIPlatform] = Field(default_factory=list)
    user_roles: list[UserRole] = Field(default_factory=lambda: list(UserRole))
    custom_questions: list[str] = Field(default_factory=list)

class EvaluationScore(BaseModel):
    dimension: EvalDimension
    score: float = Field(ge=0, le=100)
    detail: str = ""

class PlatformEvalResult(BaseModel):
    platform: AIPlatform
    scores: list[EvaluationScore]
    overall_score: float = Field(ge=0, le=100)

class EvaluateResponse(BaseModel):
    overall_score: float
    platform_results: list[PlatformEvalResult]
    before_after_comparison: Optional[dict] = None  # 优化前后对比
    weak_points: list[str] = Field(default_factory=list)  # 短板诊断
    suggestions: list[str] = Field(default_factory=list)  # 迭代建议


# ── 报表 ──

class ReportRequest(BaseModel):
    evaluation_id: str = Field(...)
    format: ExportFormat = Field(default=ExportFormat.HTML)
    include_charts: bool = Field(default=True)

class ReportResponse(BaseModel):
    report_id: str
    format: ExportFormat
    file_path: str
    created_at: datetime


# ── 项目管理 ──

class ProjectRecord(BaseModel):
    id: str
    name: str
    sandtable_type: SandtableType
    status: str                # draft / cleaning / optimized / evaluated / exported
    created_at: datetime
    updated_at: datetime
    input_path: Optional[str] = None
    output_path: Optional[str] = None


# ── 配置 ──

class LLMConfigStatus(BaseModel):
    platform: AIPlatform
    configured: bool
    api_key_masked: str
    model_name: str
    base_url: Optional[str] = None

class LLMConfigUpdate(BaseModel):
    platform: AIPlatform
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    base_url: Optional[str] = None
    enabled: Optional[bool] = None

class SystemConfigResponse(BaseModel):
    llm_platforms: list[LLMConfigStatus]
    embedding_model: str
    data_dir: str
    version: str
    enterprise_name: str = Field(default="")
    enterprise_location: str = Field(default="")
    enterprise_website: str = Field(default="")

# ── 评测维度配置 ──

class EvalDimensionConfig(BaseModel):
    key: str = Field(..., description="维度key")
    label: str = Field(..., description="维度中文名")
    requires_llm: bool = Field(default=False)
    weight: float = Field(default=20.0, ge=0, le=100)
    enabled: bool = Field(default=True)

class EvalStartRequest(BaseModel):
    optimized_text: str = Field(..., min_length=1, max_length=50000)
    original_text: str | None = Field(default=None, max_length=50000)
    sandtable_type: str = Field(default="smart_traffic")
    platforms: list[str] = Field(default_factory=lambda: ["deepseek"])
    user_roles: list[str] = Field(default_factory=lambda: ["b_end_procurement"])
    custom_questions: list[str] = Field(default_factory=list)
    dimensions: list[EvalDimensionConfig] = Field(default_factory=list)
    mode: str = Field(default="pipeline")

class EvalPhaseResult(BaseModel):
    phase: EvalPhase
    status: EvalPhaseStatus
    result: dict | None = None
    error: str | None = None

class EvalSessionResponse(BaseModel):
    session_id: str
    status: str
    phases: dict
    overall_progress: float = 0.0
    overall_score: float | None = None
    created_at: str = ""

class EvalHistoryItem(BaseModel):
    session_id: str
    sandtable_type: str
    overall_score: float | None = None
    created_at: str = ""
    mode: str = "pipeline"


# ── 平台监测 ──

class PlatformRulesUpdateRequest(BaseModel):
    summary: str = Field(default="")
    details: list[str] = Field(default_factory=list)
    status: str = Field(default="normal")
    impact: str = Field(default="")
    response: str = Field(default="")


# ── 关键词库 ──

class KeywordAddRequest(BaseModel):
    word: str = Field(..., min_length=1, description="关键词文本")
    category: str = Field(default="scene")
    weight: str = Field(default="core")
    status: str = Field(default="pending")

class KeywordUpdateRequest(BaseModel):
    weight: str | None = Field(default=None)
    status: str | None = Field(default=None)
    word_new: str | None = Field(default=None, min_length=1)

class KeywordExpandRequest(BaseModel):
    seed: str = Field(default="")


# ── 竞品调研 ──

class CompetitorCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="竞品名称")
    website: str = Field(default="")
    industry: str = Field(default="")
    notes: str = Field(default="")
    platform_exposure: dict = Field(default_factory=dict)
    content_features: dict = Field(default_factory=dict)

class CompetitorUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    website: str | None = None
    industry: str | None = None
    notes: str | None = None
    platform_exposure: dict | None = None
    content_features: dict | None = None

class SnapshotAddRequest(BaseModel):
    date: str = Field(default="")
    platform: str = Field(default="")
    query: str = Field(default="")
    citation_found: bool = Field(default=False)
    citation_snippet: str = Field(default="")
    notes: str = Field(default="")

class CompetitorCompareRequest(BaseModel):
    competitor_ids: list[str] = Field(..., min_length=2, description="至少选择2个竞品")
    include_llm: bool = Field(default=False)
    sandtable_type: str = Field(default="")

class CompetitorReportRequest(BaseModel):
    competitor_ids: list[str] = Field(..., min_length=1, description="至少选择1个竞品")


# ── 报表 ──

class ReportGenerateFromDataRequest(BaseModel):
    format: str = Field(default="html")
    include_charts: bool = Field(default=True)


# ── 内容诊断 ──

class QuickDiagnosisRequest(BaseModel):
    text: str = Field(..., min_length=1, description="待诊断文本")
    sandtable_type: str = Field(default="")

class DeepDiagnosisRequest(BaseModel):
    text: str = Field(..., min_length=1, description="待诊断文本")
    sandtable_type: str = Field(default="")

class BatchDiagnosisRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, description="待诊断文本列表")
    sandtable_type: str = Field(default="")


# ── 评测 ──

class CompareEvaluationsRequest(BaseModel):
    session_ids: list[str] = Field(..., min_length=2, max_length=2, description="需恰好2个session_id")

class QuickBrandCheckRequest(BaseModel):
    text: str = Field(..., min_length=1, description="待检测文本")
    brand_keywords: list[str] = Field(default_factory=list, description="品牌关键词（默认从配置读取）")


class LLMGenerateQuestionsRequest(BaseModel):
    optimized_text: str = Field(..., min_length=50, description="优化后的文案")
    sandtable_type: str = Field(default="smart_traffic", description="沙盘类型")
    enterprise_name: str = Field(default="", description="企业名称")
    count: int = Field(default=8, ge=3, le=20, description="生成问题数量")


# ── JSON-LD ──

class JSONLDValidateRequest(BaseModel):
    json_ld: str = Field(..., min_length=1, description="JSON-LD代码字符串")


# ── 配置 ──

class LLMConfigUpdateRequest(BaseModel):
    platform: str = Field(..., min_length=1, description="平台标识")
    api_key: str = Field(..., min_length=1, description="API Key")
    secret_key: str = Field(default="")


# ── 品牌收录监测 ──

class BrandMonitorCheckRequest(BaseModel):
    platform: str = Field(default="", description="目标AI平台（空则用默认平台）")
    queries: list[str] = Field(default_factory=list, description="自定义查询列表")
    query_categories: list[str] = Field(default_factory=lambda: ["brand_direct", "scenario"], description="查询分类")
    max_queries_per_category: int = Field(default=3, ge=1, le=10, description="每分类最大查询数")
    sandtable_type: str = Field(default="smart_traffic", description="沙盘类型")

class BrandMonitorCheckAllRequest(BaseModel):
    platforms: list[str] = Field(default_factory=list, description="目标平台列表（空则全平台）")
    query_categories: list[str] = Field(default_factory=lambda: ["brand_direct", "scenario"], description="查询分类")
    max_queries_per_category: int = Field(default=3, ge=1, le=10)
    sandtable_type: str = Field(default="smart_traffic")

class BrandMentionCheckResult(BaseModel):
    platform: str
    query: str
    query_category: str
    brand_mentioned: bool
    mention_score: float = Field(ge=0, le=100)
    mention_context: str = ""
    full_response: str | None = None
    check_method: str = "regex"
    checked_at: str = ""

class BrandMonitorSession(BaseModel):
    session_id: str
    created_at: str
    sandtable_type: str = ""
    platforms_checked: list[str] = Field(default_factory=list)
    total_queries: int = 0
    mentioned_count: int = 0
    mention_rate: float = 0.0
    results: list[BrandMentionCheckResult] = Field(default_factory=list)

class MonitorOverviewResponse(BaseModel):
    last_check_at: str | None = None
    total_sessions: int = 0
    total_checks: int = 0
    total_mentioned: int = 0
    overall_mention_rate: float = 0.0
    by_platform: dict = Field(default_factory=dict)
    recent_results: list[BrandMentionCheckResult] = Field(default_factory=list)

class MonitorTrendDataPoint(BaseModel):
    date: str
    mention_rate: float
    total_checked: int
    total_mentioned: int
    by_platform: dict = Field(default_factory=dict)

class BrandMonitorQueryRequest(BaseModel):
    text: str = Field(..., min_length=1, description="查询文本")
    category: str = Field(default="brand_direct", description="查询分类")


# ── 批量处理 ──

class BatchTextItem(BaseModel):
    id: str = Field(default="", description="文本唯一标识（自动生成）")
    title: str = Field(default="", description="文本标题/名称")
    content: str = Field(..., min_length=1, max_length=50000, description="文本内容")

class BatchCleanRequest(BaseModel):
    texts: list[BatchTextItem] = Field(..., min_length=1, max_length=50, description="待清洗文本列表（1-50篇）")
    sandtable_type: str = Field(default="", description="沙盘类型（不填则逐篇自动识别）")
    extract_dimensions: bool = Field(default=True)

class BatchCleanResult(BaseModel):
    id: str
    title: str
    original_word_count: int
    cleaned_word_count: int
    detected_type: str = ""
    dimensions: dict | None = None
    status: str = "completed"  # completed / failed
    error: str = ""

class BatchOptimizeRequest(BaseModel):
    texts: list[BatchTextItem] = Field(..., min_length=1, max_length=30, description="待优化文本列表（1-30篇）")
    sandtable_type: str = Field(..., description="沙盘类型")
    platforms: list[str] = Field(..., min_length=1, description="目标AI平台")
    optimization_hints: list[str] = Field(default_factory=list)
    enterprise_name: str = Field(default="")
    enterprise_location: str = Field(default="")

class BatchEvalRequest(BaseModel):
    texts: list[BatchTextItem] = Field(..., min_length=1, max_length=30, description="待评测文案列表")
    sandtable_type: str = Field(..., description="沙盘类型")
    platforms: list[str] = Field(default_factory=list)
    user_roles: list[str] = Field(default_factory=lambda: ["b_end_procurement"])

class BatchExportRequest(BaseModel):
    text_ids: list[str] = Field(..., min_length=1, description="要导出的文本ID列表")
    export_items: list[str] = Field(default_factory=lambda: ["optimized_text", "evaluation_report"])
    format: str = Field(default="zip")

class BatchProgressResponse(BaseModel):
    task_id: str
    task_type: str  # clean / optimize / evaluate / export
    total: int
    completed: int
    failed: int
    items: list[dict] = Field(default_factory=list)  # [{id, title, status, progress}]
    overall_status: str = "running"  # running / completed / cancelled

class BatchDiagnoseRequest(BaseModel):
    texts: list[BatchTextItem] = Field(..., min_length=1, max_length=50, description="待诊断文本列表")
    sandtable_type: str = Field(default="")

class BatchDiagnoseResult(BaseModel):
    id: str
    title: str
    scores: dict = Field(default_factory=dict)  # {dimension: score}
    overall_score: float = 0.0
    weak_points: list[str] = Field(default_factory=list)

class ComplianceCheckRequest(BaseModel):
    text: str = Field(..., min_length=1, description="待检测文本")

class ComplianceCheckResult(BaseModel):
    passed: bool
    violation_count: int
    violations: list[dict] = Field(default_factory=list)  # [{word, category, position, suggestion}]
    risk_level: str = "none"  # none / low / medium / high

class UsageSummaryResponse(BaseModel):
    date: str
    total_calls: int
    estimated_tokens: int
    estimated_cost: float
    by_platform: dict = Field(default_factory=dict)
    quota_remaining: dict = Field(default_factory=dict)
    alerts: list[dict] = Field(default_factory=list)

class UsageAlertResponse(BaseModel):
    level: str  # warning / critical
    message: str
    triggered_at: str
    threshold_pct: float

class AuthLoginRequest(BaseModel):
    password: str = Field(..., min_length=1)

class AuthStatusResponse(BaseModel):
    authenticated: bool
    auth_enabled: bool
    session_expires_at: str = ""

class AuditLogEntry(BaseModel):
    timestamp: str
    method: str
    path: str
    client_ip: str
    status: int
    duration_ms: float
    action: str = ""

class ErrorCodeEntry(BaseModel):
    code: str
    message: str
    suggestion: str
    severity: str  # low / medium / high / critical

class TaskCancelRequest(BaseModel):
    task_id: str = Field(..., min_length=1)

class BatchTaskStatus(BaseModel):
    task_id: str
    task_type: str
    status: str
    progress: float = 0.0
    result: dict | None = None


# ══════════════════════════════════════════════════════════════
# 流量与转化追踪
# ══════════════════════════════════════════════════════════════

# ── 流量配置 ──

class TrafficSourceConfig(BaseModel):
    """流量数据源配置"""
    source: str = Field(..., description="数据源: ga4 / baidu_tongji")
    enabled: bool = False
    property_id: str = Field(default="", description="GA4媒体资源ID或百度统计site_id")
    credentials_info: dict = Field(default_factory=dict, description="认证信息（仅存引用路径，不存密钥明文）")
    fetch_interval_hours: int = Field(default=24, ge=1, le=168)


class TrafficSourceConfigUpdateRequest(BaseModel):
    """更新流量数据源配置"""
    source: str = Field(..., description="ga4 / baidu_tongji")
    enabled: bool | None = None
    property_id: str | None = None
    credentials_info: dict | None = None
    fetch_interval_hours: int | None = None


# ── 流量数据 ──

class TrafficDailySnapshot(BaseModel):
    """单日流量快照"""
    date: str
    source: str = "ga4"
    page_views: int = 0
    unique_visitors: int = 0
    sessions: int = 0
    bounce_rate_pct: float = 0.0
    avg_session_duration_sec: float = 0.0
    top_landing_pages: list[dict] = Field(default_factory=list)  # [{url, views}]
    top_referrers: list[dict] = Field(default_factory=list)       # [{source, views}]
    ai_referral_visits: int = Field(default=0, description="通过AI平台UTM来源的访问量")


class TrafficSummaryResponse(BaseModel):
    """流量汇总响应"""
    period_start: str
    period_end: str
    total_page_views: int = 0
    total_visitors: int = 0
    total_sessions: int = 0
    avg_bounce_rate_pct: float = 0.0
    ai_referral_visits: int = 0
    daily_snapshots: list[TrafficDailySnapshot] = Field(default_factory=list)
    by_source: dict = Field(default_factory=dict)  # {ga4: {views, visitors}, baidu: {...}}


class TrafficTrendPoint(BaseModel):
    """流量趋势数据点"""
    date: str
    page_views: int = 0
    unique_visitors: int = 0
    ai_referral_visits: int = 0
    bounce_rate_pct: float = 0.0


# ── 转化事件 ──

class ConversionEventCreate(BaseModel):
    """创建转化事件（Webhook接收）"""
    type: str = Field(default="form_submit", description="转化类型")
    value: float = Field(default=0.0, description="转化价值（元）")
    landing_page: str = Field(default="", description="落地页URL")
    referrer: str = Field(default="", description="引荐URL（含UTM参数）")
    source: str = Field(default="webhook", description="数据来源")
    keyword: str = Field(default="", description="关键词")
    campaign_id: str = Field(default="", description="关联推广计划ID")
    extra: dict = Field(default_factory=dict, description="附加信息")


class ConversionEvent(BaseModel):
    """转化事件（含服务端生成的字段）"""
    id: str
    timestamp: str
    type: str
    value: float = 0.0
    landing_page: str = ""
    referrer: str = ""
    source: str = ""
    ai_platform: str = Field(default="", description="归因到的AI平台")
    ai_query: str = Field(default="", description="关联的AI查询")
    utm_source: str = Field(default="", description="解析出的utm_source")
    utm_medium: str = Field(default="", description="解析出的utm_medium")
    utm_campaign: str = Field(default="", description="解析出的utm_campaign")
    keyword: str = ""
    campaign_id: str = ""
    extra: dict = Field(default_factory=dict)


class ConversionAttributionResponse(BaseModel):
    """转化归因响应"""
    total_conversions: int = 0
    total_value: float = 0.0
    by_source: dict = Field(default_factory=dict)  # {ai_referral: 12, organic: 8, ...}
    by_ai_platform: dict = Field(default_factory=dict)  # {doubao: 5, wenxin: 3, ...}
    by_type: dict = Field(default_factory=dict)  # {form_submit: 10, phone_call: 2}
    ai_attributed_count: int = Field(default=0, description="归因到AI引用的转化数")
    ai_attributed_value: float = Field(default=0.0, description="AI引用带来的转化价值")
    ai_citation_rate_pct: float = Field(default=0.0, description="AI引用转化占比")
    attribution_paths: list[dict] = Field(default_factory=list)


# ── 全链路漏斗 ──

class FunnelStage(BaseModel):
    """漏斗阶段"""
    stage_name: str  # ai_impressions / ai_citations / website_visits / conversions
    label: str       # AI曝光量 / AI引用量 / 网站访问量 / 转化量
    count: int
    rate_to_previous_pct: float = Field(default=0.0, description="从上阶段到本阶段的转化率(%)")


class FullFunnelResponse(BaseModel):
    """全链路漏斗响应"""
    period_start: str
    period_end: str
    stages: list[FunnelStage]
    overall_conversion_rate_pct: float = Field(default=0.0, description="AI曝光→转化 整体转化率")
    ai_impressions_total: int = 0
    ai_citations_total: int = 0
    website_visits_from_ai: int = 0
    conversions_from_ai: int = 0
    platform_breakdown: dict = Field(default_factory=dict)
    #  {doubao: {impressions, citations, visits, conversions}, ...}


# ── UTM推广计划 ──

class UTMCampaignCreate(BaseModel):
    """创建UTM推广计划"""
    name: str = Field(..., min_length=1, description="计划名称")
    utm_source: str = Field(default="", description="utm_source（默认使用platform_id）")
    utm_medium: str = Field(default="ai_referral", description="utm_medium")
    utm_campaign: str = Field(default="", description="utm_campaign（推广活动名称）")
    utm_term: str = Field(default="", description="utm_term（关键词）")
    utm_content: str = Field(default="", description="utm_content（内容变体）")
    landing_page_url: str = Field(..., min_length=1, description="目标落地页URL")
    platform_ids: list[str] = Field(default_factory=list, description="关联的AI平台列表")
    active: bool = True


class UTMCampaign(BaseModel):
    """UTM推广计划"""
    id: str
    name: str
    utm_source: str = ""
    utm_medium: str = "ai_referral"
    utm_campaign: str = ""
    utm_term: str = ""
    utm_content: str = ""
    landing_page_url: str
    platform_ids: list[str] = Field(default_factory=list)
    active: bool = True
    created_at: str = ""
    updated_at: str = ""


class UTMGeneratedLink(BaseModel):
    """生成的UTM链接"""
    campaign_id: str
    platform_id: str = ""
    full_url: str
    utm_params: dict = Field(default_factory=dict)
    short_url: str = ""


class UTMBatchGenerateRequest(BaseModel):
    """批量生成UTM链接请求"""
    landing_page_url: str = Field(..., min_length=1)
    utm_medium: str = Field(default="ai_referral")
    utm_campaign: str = Field(default="")
    platform_ids: list[str] = Field(default_factory=list, description="目标AI平台（空则全平台）")


# ── 配置（settings.yaml 新增段） ──

class TrafficSettingsConfig(BaseModel):
    """流量模块配置"""
    fetch_interval_hours: int = 24
    default_lookback_days: int = 30
    ga4_property_id: str = ""
    baidu_site_id: str = ""


class ConversionSettingsConfig(BaseModel):
    """转化模块配置"""
    attribution_window_days: int = 30
    default_attribution_model: str = "last_click"
    ai_referral_medium_tag: str = "ai_referral"


class UTMSettingsConfig(BaseModel):
    """UTM模块配置"""
    default_medium: str = "ai_referral"
    auto_generate_platforms: list[str] = Field(default_factory=lambda: ["wenxin", "doubao", "deepseek", "tongyi", "kimi"])
