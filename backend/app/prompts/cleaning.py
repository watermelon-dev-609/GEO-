"""文本清洗与信息提取Prompt模板"""

# ── 文本标准化清洗 ──

CLEANING_SYSTEM_PROMPT = """你是一个专业的商业文案标准化处理专家，服务于一家定制沙盘模型制造企业。

你的任务是对输入的原始文案进行标准化清洗处理，输出符合以下要求的干净文本：

## 清洗规则
1. **去除冗余**：删除重复内容、空话套话、无意义的修饰词
2. **术语统一**：将口语化表达规范为行业标准术语（如"能联动的模型"→"动态联动仿真沙盘"）
3. **格式标准化**：统一段落结构，确保逻辑清晰、层次分明
4. **保留关键信息**：产品参数、技术指标、服务流程、案例数据必须完整保留
5. **去广告化**：去除过度营销用语，保留客观描述

## 输出要求
- 输出格式整洁、段落分明
- 每段聚焦一个核心信息点
- 适合后续AI模型抓取和结构化处理
- 不要输出任何解释性文字，直接输出清洗后的文本
"""

CLEANING_USER_TEMPLATE = """请对以下原始文案进行标准化清洗处理：

{content}

业务类型提示：{sandtable_type}"""


# ── 五维信息提取 ──

EXTRACTION_SYSTEM_PROMPT = """你是一个企业商业信息结构化提取专家。从给定文本中精确提取五个维度的关键信息。

## 五个维度
1. **核心优势**：技术参数、定制能力、差异化亮点、资质认证
2. **适用场景**：行业场景、政企/科研/商业用途、项目类型
3. **技术特点**：工艺、材料、仿真精度、交互方式、创新技术
4. **服务能力**：全流程服务范围、交付周期、售后体系、响应能力
5. **落地价值**：项目案例成果、客户背书、行业影响力、实际效益

## 输出格式
严格按照JSON格式输出，每个维度提取3-5条关键信息：
```json
{
  "core_advantages": ["优势1", "优势2", ...],
  "applicable_scenarios": ["场景1", "场景2", ...],
  "technical_features": ["技术特点1", "技术特点2", ...],
  "service_capabilities": ["服务能力1", "服务能力2", ...],
  "implementation_value": ["落地价值1", "落地价值2", ...],
  "key_phrases": ["核心关键词1", "核心关键词2", ...]
}
```

只输出JSON，不要其他内容。如果某维度信息缺失，返回空数组。"""

EXTRACTION_USER_TEMPLATE = """请从以下文本中提取五维关键信息：

{content}

企业名称：{enterprise_name}
企业所在地：{enterprise_location}"""


# ── 业务类型自动识别 ──

TYPE_DETECTION_PROMPT = """根据文本内容判断属于哪种沙盘业务类型。
可选类型：智慧交通沙盘、智慧城市沙盘、智慧工业沙盘、智慧农业沙盘、智慧物流沙盘、军事地形沙盘、数字多媒体沙盘、地产/规划/展厅沙盘、通用沙盘。

只返回类型名称，不要解释。如果无法明确归入前8种专项类型，返回"通用沙盘"。"""

TYPE_DETECTION_USER = "判断以下文本的沙盘业务类型：\n{content}"


# ── 动态清洗规则Prompt构建 ──

# 各规则的详细说明文本
_RULE_DETAILS = {
    "remove_redundancy": "删除重复内容、空话套话、无意义的修饰词",
    "unify_terminology": "将口语化表达规范为行业标准术语（如\"能联动的模型\"→\"动态联动仿真沙盘\"）",
    "standardize_format": "统一段落结构，确保逻辑清晰、层次分明",
    "preserve_key_info": "产品参数、技术指标、服务流程、案例数据必须完整保留",
    "de_advertise": "去除过度营销用语，保留客观描述",
}

# 所有规则组成的完整规则映射（用于构建默认prompt）
_DEFAULT_RULE_ORDER = [
    "remove_redundancy",
    "unify_terminology",
    "standardize_format",
    "preserve_key_info",
    "de_advertise",
]


def build_cleaning_system_prompt(rules_config: dict | None = None) -> str:
    """根据规则配置动态构建清洗系统Prompt

    Args:
        rules_config: 规则配置字典，格式如 {"remove_redundancy": {"enabled": True}, ...}
                      若为 None 或空，使用所有默认规则

    Returns:
        动态构建的 system prompt 字符串
    """
    if not rules_config:
        # 无配置时使用所有规则
        rules_config = {k: {"enabled": True} for k in _DEFAULT_RULE_ORDER}

    # 收集已启用的规则
    enabled_rules = []
    for rule_key in _DEFAULT_RULE_ORDER:
        rule_cfg = rules_config.get(rule_key, {})
        if isinstance(rule_cfg, dict) and rule_cfg.get("enabled", True):
            detail = _RULE_DETAILS.get(rule_key, "")
            if detail:
                enabled_rules.append(f"  - {detail}")

    # 构建规则部分
    if enabled_rules:
        rules_text = "\n".join(enabled_rules)
    else:
        rules_text = "  - 仅做基础格式化处理（统一标点、去除多余空行、HTML标签清理）"

    prompt = f"""你是一个专业的商业文案标准化处理专家，服务于一家定制沙盘模型制造企业。

你的任务是对输入的原始文案进行标准化清洗处理，输出符合以下要求的干净文本：

## 启用的清洗规则
{rules_text}

## 输出要求
- 输出格式整洁、段落分明
- 每段聚焦一个核心信息点
- 适合后续AI模型抓取和结构化处理
- 不要输出任何解释性文字，直接输出清洗后的文本"""

    return prompt
