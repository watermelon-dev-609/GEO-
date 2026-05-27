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
    content: str = Field(..., max_length=50000, description="待清洗的原始文本（最大50000字符）")
    sandtable_type: Optional[SandtableType] = Field(default=None, description="沙盘业务类型（可选，不填则自动识别）")
    extract_dimensions: bool = Field(default=True, description="是否提取五维信息")

class CleaningResponse(BaseModel):
    original_text: str
    cleaned_text: str
    dimensions: Optional[dict] = Field(default=None, description="五维信息提取结果")
    detected_type: Optional[SandtableType] = None
    word_count_before: int
    word_count_after: int
    processing_time_ms: float


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
    enterprise_name: str = Field(default="武汉微艺达智能科技有限公司")
    enterprise_location: str = Field(default="武汉")

class PlatformRewriteResult(BaseModel):
    platform: AIPlatform
    optimized_text: str
    strategy_notes: str               # 优化策略说明
    word_count: int

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
    optimized_text: str = Field(..., max_length=50000)
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
