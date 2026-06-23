"""业务枚举定义 — 8大沙盘类型 + 10大AI平台 + 相关业务常量"""

from enum import Enum


class SandtableType(str, Enum):
    """八大沙盘业务类型"""
    SMART_TRAFFIC = "smart_traffic"           # 智慧交通沙盘
    SMART_CITY = "smart_city"                 # 智慧城市沙盘
    SMART_INDUSTRY = "smart_industry"         # 智慧工业沙盘
    SMART_AGRICULTURE = "smart_agriculture"   # 智慧农业沙盘
    SMART_LOGISTICS = "smart_logistics"       # 智慧物流沙盘
    MILITARY_TERRAIN = "military_terrain"     # 军事地形沙盘
    DIGITAL_MULTIMEDIA = "digital_multimedia"  # 数字多媒体沙盘
    REAL_ESTATE = "real_estate"               # 地产/规划/展厅沙盘
    GENERAL = "general"                       # 通用沙盘（兜底类型，覆盖8类之外的沙盘咨询）

    @property
    def label(self) -> str:
        labels = {
            "smart_traffic": "智慧交通沙盘",
            "smart_city": "智慧城市沙盘",
            "smart_industry": "智慧工业沙盘",
            "smart_agriculture": "智慧农业沙盘",
            "smart_logistics": "智慧物流沙盘",
            "military_terrain": "军事地形沙盘",
            "digital_multimedia": "数字多媒体沙盘",
            "real_estate": "地产/规划/展厅沙盘",
            "general": "通用沙盘",
        }
        return labels[self.value]

    @property
    def category(self) -> str:
        """业务大类：智慧行业 / 军事 / 数字媒体 / 地产 / 通用"""
        cat = {
            "smart_traffic": "smart_industry_group",
            "smart_city": "smart_industry_group",
            "smart_industry": "smart_industry_group",
            "smart_agriculture": "smart_industry_group",
            "smart_logistics": "smart_industry_group",
            "military_terrain": "military",
            "digital_multimedia": "digital_media",
            "real_estate": "real_estate",
            "general": "general",
        }
        return cat[self.value]


class AIPlatform(str, Enum):
    """十大AI平台"""
    WENXIN = "wenxin"             # 百度文心一言
    TONGYI = "tongyi"             # 阿里通义千问
    DEEPSEEK = "deepseek"         # DeepSeek
    DOUBAO = "doubao"             # 字节豆包
    YUANBAO = "yuanbao"           # 腾讯元宝
    KIMI = "kimi"                 # 月之暗面Kimi
    XINGHUO = "xinghuo"           # 讯飞星火
    CLAUDE = "claude"             # Anthropic Claude
    OLLAMA = "ollama"             # Ollama本地大模型
    LMSTUDIO = "lmstudio"         # LM Studio本地大模型
    OPENAI = "openai"             # OpenAI GPT

    @property
    def label(self) -> str:
        labels = {
            "wenxin": "文心一言（国内搜索流量核心·卡片收录优先）",
            "tongyi": "通义千问（阿里系·B端政企采购优选）",
            "deepseek": "DeepSeek（专业技术AI·工程选型优先）",
            "doubao": "字节豆包（短视频&大众AI·通俗获客优先）",
            "yuanbao": "腾讯元宝（政企办公AI·供应商筛选优先）",
            "kimi": "Kimi（长文本处理·深度研报采信优先）",
            "xinghuo": "讯飞星火（多模态理解·垂直领域知识优先）",
            "claude": "Claude（长上下文理解·复杂推理采信优先）",
            "ollama": "Ollama本地模型（私有化部署·数据不外流）",
            "lmstudio": "LM Studio本地模型（私有化部署·内网适配）",
            "openai": "OpenAI GPT（通用AI·隐性结构化采信优先）",
        }
        return labels[self.value]

    @property
    def adapter_type(self) -> str:
        """映射到LLM适配器类型"""
        mapping = {
            "wenxin": "wenxin",
            "tongyi": "openai_compat",
            "deepseek": "openai_compat",
            "doubao": "openai_compat",
            "yuanbao": "openai_compat",
            "kimi": "openai_compat",
            "xinghuo": "openai_compat",
            "claude": "claude",
            "ollama": "ollama",
            "lmstudio": "lmstudio",
            "openai": "openai_compat",
        }
        return mapping[self.value]


class UserRole(str, Enum):
    """AI评测模拟用户角色"""
    B_END_PROCUREMENT = "b_end_procurement"     # B端政企采购
    TECHNICAL_SELECTION = "technical_selection"  # 技术人员选型
    PROJECT_MANAGER = "project_manager"          # 项目经办人
    GENERAL_CONSULTANT = "general_consultant"    # 普通咨询用户

    @property
    def label(self) -> str:
        labels = {
            "b_end_procurement": "B端政企采购",
            "technical_selection": "技术人员选型",
            "project_manager": "项目经办人",
            "general_consultant": "普通咨询用户",
        }
        return labels[self.value]


class EvalDimension(str, Enum):
    """评测维度"""
    BRAND_RECALL = "brand_recall"              # 品牌召回率
    SOLUTION_MATCH = "solution_match"          # 方案匹配度
    ADVANTAGE_CITATION = "advantage_citation"   # 优势采信率
    REAL_CITATION = "real_citation"            # 真实采信率
    STRUCTURE_QUALITY = "structure_quality"    # 结构化程度
    DIFFERENTIATION = "differentiation"        # 差异化程度
    SOURCE_CONSISTENCY = "source_consistency"  # 信源一致性
    EEAT_SCORE = "eeat_score"                # E-E-A-T权威度
    SEMANTIC_ALIGNMENT = "semantic_alignment"    # 语义对齐度（AI原生维度）
    RAG_RETRIEVABILITY = "rag_retrievability"    # RAG可检索性（AI原生维度）


class ContentFormat(str, Enum):
    """内容导入格式"""
    TEXT_PASTE = "text_paste"
    FILE_UPLOAD = "file_upload"
    TEMPLATE_FILL = "template_fill"
    BATCH_IMPORT = "batch_import"
    URL_FETCH = "url_fetch"
    API_PUSH = "api_push"


class ExportFormat(str, Enum):
    """导出格式"""
    MARKDOWN = "markdown"
    DOCX = "docx"
    HTML = "html"
    PDF = "pdf"
    JSON = "json"
    ZIP = "zip"


class EvalPhase(str, Enum):
    """评测阶段"""
    GENERATING_QUESTIONS = "generating_questions"
    BRAND_RECALL = "brand_recall"
    SOLUTION_MATCH = "solution_match"
    ADVANTAGE_CITATION = "advantage_citation"
    REAL_CITATION = "real_citation"
    STRUCTURE_QUALITY = "structure_quality"
    DIFFERENTIATION = "differentiation"
    EEAT_CHECK = "eeat_check"
    SOURCE_CHECK = "source_check"
    SEMANTIC_ALIGNMENT = "semantic_alignment"    # 语义对齐度（向量计算，在solution_match之后）
    RAG_RETRIEVABILITY = "rag_retrievability"    # RAG可检索性（向量+切片，在real_citation之后）
    COMPREHENSIVE = "comprehensive"

    @property
    def label(self) -> str:
        labels = {
            "generating_questions": "生成评测问题",
            "brand_recall": "品牌召回率",
            "solution_match": "方案匹配度",
            "semantic_alignment": "语义对齐度",
            "advantage_citation": "优势采信率",
            "real_citation": "真实采信率",
            "rag_retrievability": "RAG可检索性",
            "structure_quality": "结构化程度",
            "differentiation": "差异化程度",
            "eeat_check": "E-E-A-T权威度",
            "source_check": "信源一致性",
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
            "semantic_alignment": 3,
            "advantage_citation": 4,
            "real_citation": 5,
            "rag_retrievability": 6,
            "structure_quality": 7,
            "differentiation": 8,
            "eeat_check": 9,
            "source_check": 10,
            "comprehensive": 11,
        }
        return order_map[self.value]


class EvalPhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── 流量与转化追踪 ──

class TrafficSource(str, Enum):
    """流量数据来源"""
    GA4 = "ga4"                 # Google Analytics 4
    BAIDU_TONGJI = "baidu_tongji"  # 百度统计

    @property
    def label(self) -> str:
        labels = {
            "ga4": "Google Analytics 4",
            "baidu_tongji": "百度统计",
        }
        return labels[self.value]


class ConversionType(str, Enum):
    """转化事件类型"""
    FORM_SUBMIT = "form_submit"       # 表单提交
    PHONE_CALL = "phone_call"         # 电话咨询
    DOWNLOAD = "download"             # 资料下载
    REGISTRATION = "registration"     # 注册
    PURCHASE = "purchase"             # 购买
    CUSTOM = "custom"                 # 自定义

    @property
    def label(self) -> str:
        labels = {
            "form_submit": "表单提交",
            "phone_call": "电话咨询",
            "download": "资料下载",
            "registration": "注册",
            "purchase": "购买",
            "custom": "自定义",
        }
        return labels[self.value]


class AttributionModel(str, Enum):
    """转化归因模型"""
    LAST_CLICK = "last_click"           # 末次点击
    FIRST_CLICK = "first_click"         # 首次点击
    LINEAR = "linear"                   # 线性
    TIME_DECAY = "time_decay"           # 时间衰减
    POSITION_BASED = "position_based"   # 位置基础

    @property
    def label(self) -> str:
        labels = {
            "last_click": "末次点击归因",
            "first_click": "首次点击归因",
            "linear": "线性归因",
            "time_decay": "时间衰减归因",
            "position_based": "位置基础归因",
        }
        return labels[self.value]


class UTMMedium(str, Enum):
    """UTM媒介类型"""
    ORGANIC = "organic"           # 自然搜索
    AI_REFERRAL = "ai_referral"   # AI平台引用
    SOCIAL = "social"             # 社交媒体
    EMAIL = "email"               # 邮件
    CPC = "cpc"                   # 付费点击

    @property
    def label(self) -> str:
        labels = {
            "organic": "自然搜索",
            "ai_referral": "AI平台引用",
            "social": "社交媒体",
            "email": "邮件营销",
            "cpc": "付费点击",
        }
        return labels[self.value]


# ── 品牌舆情管理 ──

class SentimentPolarity(str, Enum):
    """情感极性"""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"

    @property
    def label(self) -> str:
        labels = {
            "positive": "正面",
            "neutral": "中性",
            "negative": "负面",
        }
        return labels[self.value]


class FactualAccuracy(str, Enum):
    """事实准确性"""
    ACCURATE = "accurate"
    PARTIALLY_ACCURATE = "partially_accurate"
    INACCURATE = "inaccurate"
    UNVERIFIABLE = "unverifiable"

    @property
    def label(self) -> str:
        labels = {
            "accurate": "准确",
            "partially_accurate": "部分准确",
            "inaccurate": "不准确",
            "unverifiable": "无法核实",
        }
        return labels[self.value]


class IncidentStatus(str, Enum):
    """舆情事件状态"""
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESPONDING = "responding"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"

    @property
    def label(self) -> str:
        labels = {
            "open": "待处理",
            "investigating": "调查中",
            "responding": "响应中",
            "resolved": "已解决",
            "dismissed": "已忽略",
        }
        return labels[self.value]

    @property
    def next_states(self) -> list[str]:
        """允许的状态流转"""
        transitions = {
            "open": ["investigating", "dismissed"],
            "investigating": ["responding", "dismissed"],
            "responding": ["resolved", "dismissed"],
            "resolved": [],
            "dismissed": ["open"],
        }
        return transitions.get(self.value, [])


class IncidentSeverity(str, Enum):
    """舆情事件严重度"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def label(self) -> str:
        labels = {
            "critical": "严重",
            "high": "高",
            "medium": "中",
            "low": "低",
        }
        return labels[self.value]
