"""五维信息共享常量 — 全项目统一引用，消除硬编码重复

五维信息是企业/产品内容的核心结构化描述维度，贯穿清洗、改写、评测全流程。
"""

from __future__ import annotations

# 五维信息维度键名（与 LLM prompt JSON schema 对齐）
DIMENSION_KEYS = [
    "core_advantages",       # 核心优势
    "applicable_scenarios",  # 适用场景
    "technical_features",    # 技术特点
    "service_capabilities",  # 服务能力
    "implementation_value",  # 落地价值
]

# 额外维度
EXTRA_KEYS = [
    "key_phrases",           # 关键词/短语
]

# 所有维度键（五维 + 额外）
ALL_DIMENSION_KEYS = DIMENSION_KEYS + EXTRA_KEYS

# 维度中文标签映射
DIMENSION_LABELS: dict[str, str] = {
    "core_advantages": "核心优势",
    "applicable_scenarios": "适用场景",
    "technical_features": "技术特点",
    "service_capabilities": "服务能力",
    "implementation_value": "落地价值",
    "key_phrases": "关键词/短语",
}

# 维度校验关键词（用于改写后处理检查五维覆盖度）
DIMENSION_COVERAGE_KEYWORDS: dict[str, list[str]] = {
    "核心优势": ["优势", "领先", "能力", "特点", "差异化"],
    "适用场景": ["场景", "适用", "应用", "用途", "用于"],
    "技术特点": ["技术", "工艺", "参数", "精度", "系统"],
    "服务能力": ["服务", "流程", "交付", "售后", "响应"],
    "落地价值": ["案例", "项目", "落地", "客户", "实施"],
}


def empty_dimensions() -> dict[str, list[str]]:
    """返回空的五维信息字典"""
    return {key: [] for key in DIMENSION_KEYS}


def empty_dimensions_with_extras() -> dict[str, list[str]]:
    """返回空的五维信息字典（含 key_phrases）"""
    return {key: [] for key in ALL_DIMENSION_KEYS}


def format_dimensions(dimensions: dict, separator: str = "；") -> str:
    """将五维信息字典格式化为可读文本

    Args:
        dimensions: 五维信息字典
        separator: 列表项分隔符

    Returns:
        格式化后的中文文本
    """
    parts = []
    for key in DIMENSION_KEYS:
        items = dimensions.get(key, [])
        if items:
            label = DIMENSION_LABELS.get(key, key)
            parts.append(f"**{label}**：{separator.join(str(i) for i in items)}")
    return "\n".join(parts) if parts else "（暂无五维信息）"


def validate_dimensions(dimensions: dict) -> list[str]:
    """校验五维信息完整性，返回缺失维度列表"""
    missing = []
    for key in DIMENSION_KEYS:
        items = dimensions.get(key, [])
        if not items:
            missing.append(DIMENSION_LABELS.get(key, key))
    return missing
