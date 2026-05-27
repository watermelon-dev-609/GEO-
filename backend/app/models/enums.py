"""业务枚举定义 — 8大沙盘类型 + 7大AI平台 + 相关业务常量"""

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
        }
        return labels[self.value]

    @property
    def category(self) -> str:
        """业务大类：智慧行业 / 军事 / 数字媒体 / 地产"""
        cat = {
            "smart_traffic": "smart_industry_group",
            "smart_city": "smart_industry_group",
            "smart_industry": "smart_industry_group",
            "smart_agriculture": "smart_industry_group",
            "smart_logistics": "smart_industry_group",
            "military_terrain": "military",
            "digital_multimedia": "digital_media",
            "real_estate": "real_estate",
        }
        return cat[self.value]


class AIPlatform(str, Enum):
    """七大AI平台"""
    GPT = "gpt"                   # OpenAI GPT系列
    CLAUDE = "claude"             # Anthropic Claude
    WENXIN = "wenxin"             # 百度文心一言
    TONGYI = "tongyi"             # 阿里通义千问
    DEEPSEEK = "deepseek"         # DeepSeek
    DOUBAO = "doubao"             # 字节豆包
    YUANBAO = "yuanbao"           # 腾讯元宝

    @property
    def label(self) -> str:
        labels = {
            "gpt": "GPT系列（通用智能·结构化总结优先）",
            "claude": "Claude（长文本深度采信·方案背书优先）",
            "wenxin": "文心一言（国内搜索流量核心·卡片收录优先）",
            "tongyi": "通义千问（阿里系·B端政企采购优选）",
            "deepseek": "DeepSeek（专业技术AI·工程选型优先）",
            "doubao": "字节豆包（短视频&大众AI·通俗获客优先）",
            "yuanbao": "腾讯元宝（政企办公AI·供应商筛选优先）",
        }
        return labels[self.value]

    @property
    def adapter_type(self) -> str:
        """映射到LLM适配器类型"""
        mapping = {
            "gpt": "openai_compat",
            "claude": "claude",
            "wenxin": "wenxin",
            "tongyi": "openai_compat",
            "deepseek": "openai_compat",
            "doubao": "openai_compat",
            "yuanbao": "openai_compat",
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
    BRAND_RECALL = "brand_recall"           # 品牌召回率
    SOLUTION_MATCH = "solution_match"       # 方案匹配度
    ADVANTAGE_CITATION = "advantage_citation"  # 优势采信率


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
    SOURCE_CHECK = "source_check"
    COMPREHENSIVE = "comprehensive"

    @property
    def label(self) -> str:
        labels = {
            "generating_questions": "生成评测问题",
            "brand_recall": "品牌召回率",
            "solution_match": "方案匹配度",
            "advantage_citation": "优势采信率",
            "real_citation": "真实采信率",
            "structure_quality": "结构化程度",
            "differentiation": "差异化程度",
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
            "advantage_citation": 3,
            "real_citation": 4,
            "structure_quality": 5,
            "differentiation": 6,
            "source_check": 7,
            "comprehensive": 8,
        }
        return order_map[self.value]


class EvalPhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"
