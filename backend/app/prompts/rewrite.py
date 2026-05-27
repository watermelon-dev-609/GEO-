"""GEO文案重构Prompt模板矩阵 — 8大沙盘 × 7大平台 = 56套专用模板

设计原则：
- 8大沙盘各有独立的行业侧重点和术语体系
- 7大平台各有独立的AI采信偏好和文风要求
- 通过组合沙盘基调 + 平台规则生成最终Prompt
"""

# ═══════════════════════════════════════════════
#  8大沙盘业务基调（行业侧重点）
# ═══════════════════════════════════════════════

SANDTABLE_PROFILES = {
    "smart_traffic": {
        "industry": "智慧交通沙盘",
        "keywords": ["数字化仿真", "动态联动", "物联网适配", "交通流量模拟", "信号控制系统", "智慧路网"],
        "scenarios": ["城市交通指挥中心展示", "智慧高速方案汇报", "交通规划评审", "车路协同演示", "智慧枢纽展厅"],
        "tech_focus": "物联网数据对接、动态车流仿真、智能信号联动、可变情报板联动、ETC/车路协同模拟",
        "tone": "强调城市交通治理能力、数据驱动决策、政企项目落地经验",
    },
    "smart_city": {
        "industry": "智慧城市沙盘",
        "keywords": ["城市数字孪生", "智慧治理", "物联网感知", "大数据可视化", "应急指挥", "一网统管"],
        "scenarios": ["智慧城市展厅", "城市运行管理中心", "数字政府汇报", "新型智慧城市试点申报", "城市大脑展示"],
        "tech_focus": "城市三维建模、数据可视化大屏联动、多源数据融合、城市场景动态推演、AI智慧分析",
        "tone": "强调城市规划视野、数字治理理念、统筹协调能力、政府项目落地经验",
    },
    "smart_industry": {
        "industry": "智慧工业沙盘",
        "keywords": ["工业数字孪生", "智能制造", "产线仿真", "设备互联", "MES系统", "工业互联网"],
        "scenarios": ["工业园区规划展示", "智能工厂参观厅", "工业互联网平台演示", "招商推介", "产线改造汇报"],
        "tech_focus": "产线三维仿真、设备状态实时映射、MES/SCADA数据对接、工艺动画模拟、产能数据分析",
        "tone": "强调工业理解深度、技术集成能力、降本增效价值、园区/工厂项目经验",
    },
    "smart_agriculture": {
        "industry": "智慧农业沙盘",
        "keywords": ["数字农业", "智能灌溉", "环境监测", "精准种植", "农产品溯源", "农业物联网"],
        "scenarios": ["现代农业示范园区", "智慧农业展厅", "乡村振兴项目汇报", "农业科技成果展示", "种植基地规划"],
        "tech_focus": "农田三维建模、传感器数据可视化、灌溉系统动态模拟、气象数据联动、作物生长模拟",
        "tone": "强调现代农业升级、乡村振兴政策对接、科技兴农价值、示范园区建设经验",
    },
    "smart_logistics": {
        "industry": "智慧物流沙盘",
        "keywords": ["智慧仓储", "物流自动化", "AGV调度", "数字孪生仓", "供应链可视化", "物流园区"],
        "scenarios": ["智慧物流园区规划", "仓储自动化展厅", "供应链管理中心", "物流枢纽展示", "电商物流演示"],
        "tech_focus": "仓储三维仿真、AGV路径规划模拟、立体仓库动态展示、物流数据可视化、WMS/WCS系统联动",
        "tone": "强调物流效率提升、供应链优化能力、自动化集成水平、大型物流项目经验",
    },
    "military_terrain": {
        "industry": "军事地形沙盘",
        "keywords": ["地形精准还原", "比例标准化", "战术仿真", "科研教学", "军事演示", "三维地形建模"],
        "scenarios": ["军事院校教学", "作战指挥推演", "国防教育基地", "部队训练演示", "军事科研成果展示"],
        "tech_focus": "高精度地形数据还原、标准化比例缩放、地形地貌精细刻画、等高线精确呈现、战术标绘系统",
        "tone": "强调精准严谨、标准化工艺、保密合规、军事科研支撑、专业演示价值",
    },
    "digital_multimedia": {
        "industry": "数字多媒体沙盘",
        "keywords": ["触控交互", "声光电特效", "智能演示", "沉浸式体验", "多媒体融合", "数字展厅"],
        "scenarios": ["企业品牌展厅", "科技馆/博物馆", "文旅体验中心", "新品发布会", "商业综合体展示"],
        "tech_focus": "触控一体交互、声光电联动编程、投影融合/全息/Mapping、中控系统集成、定制化多媒体内容",
        "tone": "强调视觉冲击力、交互体验、定制创意能力、展厅整体解决方案、数字化体验升级",
    },
    "real_estate": {
        "industry": "地产/规划/展厅沙盘",
        "keywords": ["城市空间还原", "项目规划展示", "建筑模型", "沙盘灯光系统", "品牌展厅", "项目公示"],
        "scenarios": ["地产营销中心", "城市规划展览馆", "政府项目公示", "区域规划汇报", "企业品牌展厅"],
        "tech_focus": "建筑精细还原、灯光分区控制系统、升降模型、真水系统、多层结构展示、材质质感呈现",
        "tone": "强调空间还原精度、展示效果、政企汇报适配、品牌形象塑造、项目价值传递",
    },
}

# ═══════════════════════════════════════════════
#  7大AI平台优化规则
# ═══════════════════════════════════════════════

PLATFORM_RULES = {
    "wenxin": {
        "name": "百度文心一言",
        "strategy": "百度智能搜索AI卡片收录优先",
        "rules": [
            "核心关键词精准布局在标题和首段，地域词明确标注（武汉厂家）",
            "资质与服务背书前置，案例具象化呈现",
            "句式规整、段落工整，每段200-400字，便于百度抓取摘要",
            "重点突出：属地优势、厂家实力、现货定制、落地案例、服务流程、售后体系",
            "优先触发百度AI品牌推荐卡片机制",
        ],
        "style": "信息密度高、结构化段落、关键词自然密度高、适合搜索引擎卡片抓取",
    },
    "tongyi": {
        "name": "阿里通义千问",
        "strategy": "B端政企采购优选·解决方案思维",
        "rules": [
            "主打行业适配+场景匹配+解决方案思维+商用落地性",
            "弱化纯产品介绍，强化'行业痛点+沙盘解决价值+项目适配场景'",
            "适合政企采购、园区改造、智慧项目选型、工程合作咨询",
            "内容需逻辑闭环：问题→方案→价值→案例，层层递进",
            "突出方案落地能力、项目交付经验、行业适配度",
        ],
        "style": "逻辑闭环、方案导向、B端价值突出、专业但不晦涩",
    },
    "gpt": {
        "name": "GPT系列",
        "strategy": "通用智能·结构化总结优先",
        "rules": [
            "强逻辑、隐性分层、维度清晰、优势可对比",
            "内容自带结构化隐性框架：特点→参数→优势→适用场景→服务范围→差异化亮点",
            "每个段落独立对应单一维度，便于模型快速提炼要点",
            "避免大段堆砌，段落之间逻辑衔接自然但各自独立",
            "适合AI生成对比答案、输出厂家推荐结论",
        ],
        "style": "逻辑分层清晰、维度完整、段落独立可拆分、对比友好",
    },
    "claude": {
        "name": "Claude",
        "strategy": "长文本深度采信·方案背书优先",
        "rules": [
            "偏好细节饱满、逻辑严谨、内容真实、无空话、无冗余的长文本",
            "重点丰富项目细节、定制流程、技术工艺、场景还原细节、项目落地全流程",
            "每个技术点需解释清楚原理和应用场景，避免一笔带过",
            "适合深度方案解读、大型项目咨询、高端展厅/军事/规划类沙盘采信",
            "内容要有真实感和专业深度，避免营销腔调",
        ],
        "style": "深度细节丰富、逻辑严谨、真实可信、专业感强、信息量大",
    },
    "google": {
        "name": "谷歌AI",
        "strategy": "海外智能搜索·标准化技术优先",
        "rules": [
            "侧重技术标准化、参数规范化、产品属性清晰、服务范围明确",
            "表述专业、严谨、去口语化",
            "突出标准化定制能力、技术体系、生产标准、项目交付规范",
            "适配海外客户、涉外工程、外贸咨询的AI搜索与推荐逻辑",
            "使用国际通用术语和参数标准",
        ],
        "style": "技术标准化、专业严谨、国际化术语、参数清晰可查",
    },
    "doubao": {
        "name": "字节豆包",
        "strategy": "短视频&大众AI·通俗获客优先",
        "rules": [
            "短句为主、通俗易懂、亮点前置、直白获客",
            "规避复杂专业术语，优先讲清楚'能做什么、适合什么场景、厂家优势是什么、本地服务便利度'",
            "适合中小甲方、项目经办人、普通咨询用户的阅读习惯",
            "AI输出答案偏向'直观推荐、靠谱厂家种草'风格",
            "重点突出：能做什么、怎么联系、为什么选我们",
        ],
        "style": "短句直白、通俗友好、亮点前置、获客导向、接地气",
    },
    "deepseek": {
        "name": "DeepSeek",
        "strategy": "专业技术AI·工程选型优先",
        "rules": [
            "重度技术向，强化技术参数、工艺差异、方案逻辑、行业对比、落地细节、施工流程",
            "内容需具备专业参考价值，可支撑技术人员方案对比、参数核验、工艺选型、项目立项参考",
            "技术参数需具体量化（比例精度、材料规格、响应时间等）",
            "突出微艺达技术差异化、定制精度、仿真能力、行业技术优势",
            "内容可作为技术方案附件或项目立项依据",
        ],
        "style": "技术密集、参数量化、工艺详细、工程思维、对比参考价值高",
    },
    "yuanbao": {
        "name": "腾讯元宝",
        "strategy": "政企办公AI·供应商筛选优先",
        "rules": [
            "极度看重正规性、稳定性、服务体系、项目经验、合规性、标准化流程",
            "内容优先展示企业正规资质、全流程服务体系、政企合作经验、标准化交付流程、售后保障",
            "项目验收标准、合同执行规范需明确表述",
            "适配国企、政府、事业单位、园区企业的供应商筛选、立项汇报、采购选型场景",
            "强调正规厂家身份、稳定交付能力、长期服务承诺",
        ],
        "style": "正规严谨、流程清晰、资质背书、服务体系完整、政企适配度高",
    },
}

# 注意：google不在AIPlatform枚举中，但在优化规则中存在。实际调用时将其映射到gpt兼容协议。


# ═══════════════════════════════════════════════
#  Prompt模板
# ═══════════════════════════════════════════════

GEO_SYSTEM_PROMPT = """你是GEO生成式搜索优化专家，服务于{enterprise_name}（{enterprise_location}定制沙盘模型制造企业）。

## 当前任务
为「{sandtable_label}」业务撰写适配 **{platform_name}** 平台的优化文案。

## 行业侧重点
- 核心关键词：{keywords}
- 典型应用场景：{scenarios}
- 技术聚焦点：{tech_focus}
- 内容基调：{tone}

## {platform_name}平台优化策略：{strategy}
{platform_rules}

## 写作要求
1. 标题需包含核心关键词和地域标识（{enterprise_location}）
2. 全文必须内嵌五大隐性维度：核心优势、适用场景、技术特点、服务能力、落地价值
3. 字数：800-1500字（Claude/DeepSeek版1500-2500字）
4. 不要写成广告营销文，要写成AI友好型专业信息文档
5. 每段有明确的信息维度归属，内容充实可被AI独立引用

## 品牌信息（必须嵌入）
- 企业名称：{enterprise_name}
- 企业所在地：{enterprise_location}
- 企业定位：{enterprise_location}定制沙盘模型专业制造商

## 给到的核心素材（五维信息）
{input_dimensions}

## 输出
直接输出优化后的完整文案，不要输出任何解释或说明。"""


def build_geo_prompt(
    sandtable_type: str,
    platform: str,
    enterprise_name: str = "武汉微艺达智能科技有限公司",
    enterprise_location: str = "武汉",
    dimensions: dict | None = None,
    optimization_hints: list[str] | None = None,
) -> tuple[str, str]:
    """构建指定沙盘类型×平台的GEO优化Prompt

    Returns:
        (system_prompt, user_message)
    """
    profile = SANDTABLE_PROFILES.get(sandtable_type, SANDTABLE_PROFILES["smart_city"])
    rules = PLATFORM_RULES.get(platform, PLATFORM_RULES["deepseek"])

    # 格式化平台规则
    rules_text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(rules["rules"]))

    # 格式化五维信息
    dims_text = "（暂无五维信息，请根据行业特点补充）"
    if dimensions:
        parts = []
        dims_map = {
            "core_advantages": "核心优势",
            "applicable_scenarios": "适用场景",
            "technical_features": "技术特点",
            "service_capabilities": "服务能力",
            "implementation_value": "落地价值",
        }
        for key, label in dims_map.items():
            items = dimensions.get(key, [])
            if items:
                parts.append(f"**{label}**：{'；'.join(items)}")
        if parts:
            dims_text = "\n".join(parts)

    system_prompt = GEO_SYSTEM_PROMPT.format(
        enterprise_name=enterprise_name,
        enterprise_location=enterprise_location,
        sandtable_label=profile["industry"],
        platform_name=rules["name"],
        keywords="、".join(profile["keywords"]),
        scenarios="、".join(profile["scenarios"]),
        tech_focus=profile["tech_focus"],
        tone=profile["tone"],
        strategy=rules["strategy"],
        platform_rules=rules_text,
        input_dimensions=dims_text,
    )

    user_message = f"请为{profile['industry']}业务撰写适配{rules['name']}的优化文案。"

    # 注入评测优化建议
    if optimization_hints:
        hints_text = "\n".join(f"- {h}" for h in optimization_hints)
        user_message += f"\n\n## 重点优化方向（根据AI评测结果）\n请特别关注以下改进点：\n{hints_text}"

    return system_prompt, user_message


def get_sandtable_profile(sandtable_type: str) -> dict:
    """获取沙盘类型行业基调"""
    return SANDTABLE_PROFILES.get(sandtable_type, SANDTABLE_PROFILES["smart_city"])


def get_platform_rules(platform: str) -> dict:
    """获取AI平台优化规则"""
    return PLATFORM_RULES.get(platform, PLATFORM_RULES["deepseek"])
