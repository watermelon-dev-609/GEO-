"""JSON-LD结构化生成器 — Schema.org标准，按沙盘类型自动匹配"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from app.models.enums import SandtableType
from app.utils.config import get_enterprise_name, get_enterprise_location

# Schema.org类型映射
SCHEMA_MAPPING = {
    "smart_traffic": ["Product", "Service", "Organization"],
    "smart_city": ["Product", "Service", "Organization"],
    "smart_industry": ["Product", "Service", "Organization"],
    "smart_agriculture": ["Product", "Service", "Organization"],
    "smart_logistics": ["Product", "Service", "Organization"],
    "military_terrain": ["Product", "EducationalProduct", "Organization"],
    "digital_multimedia": ["Product", "SoftwareApplication", "CreativeWork"],
    "real_estate": ["Service", "RealEstateService", "Project", "Place"],
}

# 沙盘类型到Schema描述的映射
SCHEMA_DESCRIPTIONS = {
    "smart_traffic": "智慧交通沙盘 — 动态仿真、物联互通，适配城市交通治理与智慧路网展示",
    "smart_city": "智慧城市沙盘 — 数字孪生、一网统管，适配新型智慧城市与数字政府建设展示",
    "smart_industry": "智慧工业沙盘 — 智能制造、产线仿真，适配工业互联网与数字化工厂展示",
    "smart_agriculture": "智慧农业沙盘 — 数字农业、精准种植，适配现代农业示范与乡村振兴展示",
    "smart_logistics": "智慧物流沙盘 — 智慧仓储、供应链可视化，适配物流枢纽与自动化仓储展示",
    "military_terrain": "军事地形沙盘 — 地形精准还原、战术仿真，适配军事教学与作战推演",
    "digital_multimedia": "数字多媒体沙盘 — 触控交互、声光电特效，适配数字化展厅与沉浸式体验",
    "real_estate": "地产/规划/展厅沙盘 — 空间还原、项目展示，适配地产营销与城市规划汇报",
}


class JSONLDGenerator:
    """JSON-LD结构化代码生成器"""

    def __init__(self):
        self.context = "https://schema.org"
        self._now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def generate(
        self,
        sandtable_type: SandtableType,
        enterprise_info: dict,
        product_info: dict,
        include_faq: bool = True,
        include_breadcrumb: bool = True,
    ) -> dict:
        """生成完整的JSON-LD结构化数据"""
        schemas = SCHEMA_MAPPING.get(sandtable_type.value, ["Product", "Service", "Organization"])

        graph = []

        # 1. Organization（企业身份标记）
        graph.append(self._build_organization(enterprise_info))

        # 2. WebSite + SearchAction
        graph.append(self._build_website(enterprise_info))

        # 3. Product / Service（产品/服务标记）
        if "Product" in schemas:
            graph.append(self._build_product(sandtable_type, enterprise_info, product_info))
        if "Service" in schemas:
            graph.append(self._build_service(sandtable_type, enterprise_info, product_info))
        if "EducationalProduct" in schemas:
            graph.append(self._build_edu_product(sandtable_type, enterprise_info, product_info))
        if "SoftwareApplication" in schemas:
            graph.append(self._build_software_app(sandtable_type, enterprise_info, product_info))
        if "CreativeWork" in schemas:
            graph.append(self._build_creative_work(sandtable_type, enterprise_info, product_info))
        if "RealEstateService" in schemas:
            graph.append(self._build_real_estate_service(sandtable_type, enterprise_info, product_info))
        if "Project" in schemas:
            graph.append(self._build_project(sandtable_type, enterprise_info, product_info))

        # 4. BreadcrumbList（面包屑导航）
        if include_breadcrumb:
            graph.append(self._build_breadcrumb(sandtable_type, enterprise_info))

        # 5. FAQPage（常见问答）
        if include_faq:
            graph.append(self._build_faq(sandtable_type, enterprise_info))

        json_ld = {
            "@context": self.context,
            "@graph": graph,
        }

        # 合法性检验
        validation = self._validate(json_ld)

        return {
            "sandtable_type": sandtable_type,
            "json_ld_code": json.dumps(json_ld, ensure_ascii=False, indent=2),
            "schema_types_used": schemas,
            "validation_passed": validation,
        }

    def _build_organization(self, info: dict) -> dict:
        name = info.get("name", get_enterprise_name())
        url = info.get("url", "")
        logo = info.get("logo", "")
        description = info.get("description", f"{info.get('location', '武汉')}定制沙盘模型专业制造商")
        location = info.get("location", "武汉")

        org = {
            "@type": "Organization",
            "@id": f"{url.rstrip('/')}/#organization" if url else "#organization",
            "name": name,
            "description": description,
            "dateModified": self._now,
            "address": {
                "@type": "PostalAddress",
                "addressLocality": location,
                "addressCountry": "CN",
            },
            "contactPoint": {
                "@type": "ContactPoint",
                "contactType": "customer service",
                "telephone": info.get("phone", ""),
                "email": info.get("email", ""),
            },
        }
        if url:
            org["url"] = url
            org["sameAs"] = [url]
        if logo:
            org["logo"] = {"@type": "ImageObject", "url": logo}
        # 清理空值
        org = self._clean_empty(org)
        return org

    def _build_website(self, info: dict) -> dict:
        """WebSite + SearchAction schema"""
        url = info.get("url", "")
        name = info.get("name", get_enterprise_name())
        site = {
            "@type": "WebSite",
            "@id": f"{url.rstrip('/')}/#website" if url else "#website",
            "name": f"{name}官网",
            "description": info.get("description", ""),
            "inLanguage": "zh-CN",
        }
        if url:
            site["url"] = url
            site["potentialAction"] = {
                "@type": "SearchAction",
                "target": {
                    "@type": "EntryPoint",
                    "urlTemplate": f"{url.rstrip('/')}/search?q={{search_term_string}}",
                },
                "query-input": "required name=search_term_string",
            }
        return self._clean_empty(site)

    def _build_product(self, st: SandtableType, ent: dict, prod: dict) -> dict:
        product = {
            "@type": "Product",
            "name": prod.get("name", f"{st.label}"),
            "description": prod.get("description", SCHEMA_DESCRIPTIONS.get(st.value, "")),
            "brand": {"@type": "Brand", "name": ent.get("name", get_enterprise_name())},
            "category": prod.get("category", "定制沙盘模型"),
            "manufacturer": {"@type": "Organization", "name": ent.get("name", "")},
        }
        if prod.get("image"):
            product["image"] = prod["image"]
        product = self._clean_empty(product)
        return product

    def _build_service(self, st: SandtableType, ent: dict, prod: dict) -> dict:
        return {
            "@type": "Service",
            "name": prod.get("service_name", f"{st.label}定制服务"),
            "description": prod.get("service_description", SCHEMA_DESCRIPTIONS.get(st.value, "")),
            "provider": {"@type": "Organization", "name": ent.get("name", "")},
            "areaServed": {"@type": "Place", "name": ent.get("location", "全国")},
            "serviceType": prod.get("service_type", "沙盘定制"),
        }

    def _build_edu_product(self, st: SandtableType, ent: dict, prod: dict) -> dict:
        return {
            "@type": "EducationalProduct",
            "name": prod.get("name", f"{st.label}"),
            "description": prod.get("description", SCHEMA_DESCRIPTIONS.get(st.value, "")),
            "provider": {"@type": "Organization", "name": ent.get("name", "")},
            "educationalUse": prod.get("educational_use", "科研教学、军事演示、地形分析"),
        }

    def _build_software_app(self, st: SandtableType, ent: dict, prod: dict) -> dict:
        return {
            "@type": "SoftwareApplication",
            "name": prod.get("software_name", f"{st.label}交互控制系统"),
            "description": prod.get("software_description", "触控交互、声光电联动、中控系统"),
            "applicationCategory": "MultimediaApplication",
            "provider": {"@type": "Organization", "name": ent.get("name", "")},
        }

    def _build_creative_work(self, st: SandtableType, ent: dict, prod: dict) -> dict:
        return {
            "@type": "CreativeWork",
            "name": prod.get("name", f"{st.label}"),
            "description": prod.get("description", SCHEMA_DESCRIPTIONS.get(st.value, "")),
            "creator": {"@type": "Organization", "name": ent.get("name", "")},
            "genre": "数字多媒体展示",
        }

    def _build_real_estate_service(self, st: SandtableType, ent: dict, prod: dict) -> dict:
        return {
            "@type": "RealEstateService",
            "name": prod.get("name", f"{st.label}"),
            "description": prod.get("description", ""),
            "provider": {"@type": "Organization", "name": ent.get("name", "")},
        }

    def _build_project(self, st: SandtableType, ent: dict, prod: dict) -> dict:
        return {
            "@type": "Project",
            "name": prod.get("project_name", f"{ent.get('name', '')} - {st.label}项目"),
            "description": prod.get("project_description", SCHEMA_DESCRIPTIONS.get(st.value, "")),
            "agent": {"@type": "Organization", "name": ent.get("name", "")},
        }

    def _build_breadcrumb(self, st: SandtableType, ent: dict) -> dict:
        company = ent.get("name", get_enterprise_name())
        return {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "首页", "item": ent.get("url", "")},
                {"@type": "ListItem", "position": 2, "name": "产品中心", "item": f"{ent.get('url', '')}/products"},
                {"@type": "ListItem", "position": 3, "name": st.label, "item": ""},
            ],
        }

    def _build_faq(self, st: SandtableType, ent: dict) -> dict:
        company = ent.get("name", get_enterprise_name())
        location = ent.get("location", "武汉")

        faqs = {
            "smart_traffic": [
                ("智慧交通沙盘支持哪些数据对接方式？", f"{company}的智慧交通沙盘支持物联网数据实时对接、交通流量数据导入、信号控制系统联动，可实现真实交通场景的数字化模拟。"),
                ("定制一套智慧交通沙盘需要多长时间？", f"标准项目周期30-45个工作日，根据项目规模和复杂程度调整。{company}提供从方案设计到安装调试的全流程服务。"),
                ("智慧交通沙盘可以模拟哪些交通场景？", "可模拟城市主干道交通流、信号灯智能控制、公共交通调度、应急车辆优先通行、交通事故模拟等多种场景。"),
                ("交通沙盘的交互控制方式有哪些？", "支持触控屏操作、iPad无线控制、语音指令识别、传感器触发等多种交互方式，可灵活适配展厅使用需求。"),
                ("智慧交通沙盘适用于哪些客户类型？", "适用于交通管理部门、智慧城市展厅、交通科研院所、高校交通专业、智能交通企业展示等场景。"),
            ],
            "smart_city": [
                ("智慧城市沙盘能否对接城市大脑系统？", f"可以。{company}的数字孪生技术能够与城市大脑、大数据平台、IoT平台对接，实现城市场景的动态可视化呈现。"),
                ("智慧城市沙盘适合哪些场景？", "适用于城市运行管理中心、智慧城市展厅、数字政府汇报、新型智慧城市试点申报等场景。"),
                ("智慧城市沙盘包含哪些子系统？", "通常包含智慧交通、智慧安防、智慧照明、智慧环保、智慧管网、智慧社区等多个子系统的可视化展示。"),
                ("城市沙盘的数字孪生数据如何更新？", "通过数据接口可实现实时或定时的数据同步更新，支持对接政府数据开放平台和各类IoT传感器数据源。"),
                ("一个完整的智慧城市沙盘项目包含哪些环节？", "包含需求调研、概念设计、详细设计、沙盘制作、多媒体系统集成、软件平台开发、安装调试和培训验收等环节。"),
            ],
            "military_terrain": [
                ("军事地形沙盘的精度能达到什么水平？", f"{company}采用高精度地形数据，支持1:500至1:50000多种比例，等高线精度误差控制在毫米级，满足军事教学和科研需求。"),
                ("军事沙盘项目的保密性如何保障？", "公司建立有完善的保密管理制度，项目全流程签署保密协议，数据存储和传输均采用加密措施，符合军事单位合作要求。"),
                ("军事地形沙盘使用哪些材料？", "可根据需求选用ABS工程塑料、亚克力、金属、实木等多种材料，不同材料在精度、耐久性和成本上各有优势。"),
                ("地形数据可以从哪些来源获取？", "支持导入DEM数字高程模型、卫星遥感影像、无人机航拍数据、CAD地形图等多种数据源。"),
                ("军事沙盘能否集成战术推演系统？", "可以集成。我们开发的电子沙盘系统支持兵棋推演、态势标绘、路径规划等功能，可与沙盘模型联动展示。"),
            ],
            "smart_industry": [
                ("智慧工业沙盘能展示哪些生产环节？", "可展示从原材料入库、自动化加工、装配线流转、质量检测到成品出库的全流程生产环节。"),
                ("工业沙盘是否支持产线三维可视化？", "支持。通过配套的数字孪生软件，可在沙盘上叠加三维透明屏或投影，实现产线内部结构的动态可视化。"),
                (f"{st.label}的定制周期是多久？", f"标准工业沙盘项目周期为35-50个工作日，大型项目（50平方米以上）约为60-90个工作日。"),
                ("工业沙盘的控制系统如何操作？", "采用PLC+上位机的控制架构，支持触控面板、手机APP、语音控制等多种操作方式。"),
                ("智慧工业沙盘适用于哪些行业？", "适用于汽车制造、电子装配、食品加工、制药、物流仓储、能源化工等多个行业的数字化工厂展示。"),
            ],
            "smart_agriculture": [
                ("智慧农业沙盘可以展示哪些农业场景？", "可展示精准种植、智能灌溉、无人机植保、农产品溯源、智慧养殖、农业大数据平台等多种场景。"),
                ("农业沙盘如何体现智能化？", "通过传感器数据联动、LED灯光效果模拟、触摸查询系统等方式，展示农业物联网、AI病虫害识别等智能化应用。"),
                (f"{st.label}适用哪些展示场所？", "适用于农业科技示范园区、现代农业展厅、乡村振兴成果展示、农业企业品牌展馆等场所。"),
                ("数字农业沙盘的数据来源是什么？", "可对接农业物联网平台、气象数据、土壤墒情监测数据、无人机遥感数据等真实数据源。"),
                ("农业沙盘的水域和灌溉效果如何表现？", "采用动态水循环系统配合LED灯光模拟水流方向，结合透明材料表现水渠、蓄水池和滴灌管网。"),
            ],
            "smart_logistics": [
                ("智慧物流沙盘能展示哪些物流环节？", "可展示AGV自动搬运、智能仓储货架、自动分拣线、路径规划算法、最后一公里配送等物流全链条场景。"),
                ("物流沙盘的自动化设备如何驱动？", "内置微型电机、舵机和传感器，配合PLC控制系统实现AGV小车自动巡航、堆垛机升降、传送带运转等动态效果。"),
                ("物流沙盘的数据可视化如何实现？", "通过配套大屏展示WMS/WCS系统界面，实时模拟库存数据、订单处理量和物流效率指标。"),
                (f"{st.label}是否需要专门的安装环境？", f"{location}本地项目由{company}负责安装调试，外地项目提供上门安装服务，需预留220V电源和网络接口。"),
                ("物流沙盘适用于哪些展示场景？", "适用于智慧物流园区展厅、物流企业品牌馆、电商仓储展示中心、高校物流专业实训室等场景。"),
            ],
            "digital_multimedia": [
                ("数字多媒体沙盘有哪些交互方式？", "支持触控一体机、体感手势识别、声控语音交互、手机扫码互动、AR增强现实等多种交互方式。"),
                ("多媒体沙盘的声光电效果如何实现？", "采用多通道投影融合、LED点阵灯光、立体声音响、烟幕特效等多媒体技术，配合中央控制系统实现一键场景切换。"),
                ("数字沙盘的内容可以后期更新吗？", "可以。我们提供的后台管理系统支持客户自行更新文字、图片、视频等展示内容，无需专业人员操作。"),
                (f"{st.label}的投影系统如何配置？", "根据展厅空间和沙盘尺寸，配置短焦或超短焦激光投影机，支持单通道至多通道融合方案，分辨率可达4K。"),
                ("数字多媒体沙盘适用于哪些场合？", "适用于企业展厅、科技馆、城市规划展览馆、文旅景区、品牌发布会等需要沉浸式视觉体验的场合。"),
            ],
            "real_estate": [
                ("地产沙盘的比例和尺寸可以定制吗？", "完全可以根据项目的实际面积和展厅空间进行定制，常见比例有1:50、1:100、1:200等，支持非标比例定制。"),
                ("地产沙盘的建筑模型精度如何？", "建筑外立面精度控制在0.5mm以内，可还原建筑幕墙材质、阳台栏杆、空调百叶等细节，配套景观绿化高度还原。"),
                ("售楼处沙盘的交货周期是多久？", "标准项目20-35个工作日，含灯光系统安装调试。加急项目可压缩至15个工作日（需加收加急费用）。"),
                ("规划沙盘可以展示哪些规划要素？", "可展示用地性质分区、道路交通网络、公共服务设施布局、绿地水系、天际线控制和地下空间利用等规划要素。"),
                ("地产沙盘的售后维护服务有哪些？", f"{company}提供2年免费保修，终身维护服务。保修期内每年免费上门清洁保养一次，故障响应时间为{location}市区24小时内。"),
            ],
        }

        questions = faqs.get(st.value, [
            (f"{st.label}的定制流程是怎样的？", f"{company}提供从需求沟通、方案设计、模型制作到安装调试、售后维护的全流程服务，项目周期根据规模30-60个工作日。"),
            (f"{st.label}的价格是多少？", "根据沙盘尺寸、工艺复杂度、交互功能和多媒体配置的不同，价格从数万元到数百万元不等。"),
            (f"{company}的服务范围覆盖哪些地区？", f"总部位于{location}，服务覆盖全国各省市。已为超过500家客户提供沙盘定制服务。"),
            ("沙盘模型使用什么材料制作？", "根据产品类型选用ABS工程塑料、亚克力、实木、金属等多种材料，满足不同场景的精度和耐久性需求。"),
            ("如何获取定制方案和报价？", f"欢迎致电或在线留言，{company}的专业团队将在24小时内与您联系，根据需求提供免费方案设计和初步报价。"),
        ])

        return {
            "@type": "FAQPage",
            "@id": "#faq",
            "dateModified": self._now,
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": q,
                    "acceptedAnswer": {"@type": "Answer", "text": a},
                }
                for q, a in questions
            ],
        }

    def _validate(self, json_ld: dict) -> bool:
        """基础合法性校验"""
        try:
            # 检查必要字段
            if "@context" not in json_ld:
                return False
            if "@graph" not in json_ld:
                return False
            if not json_ld["@graph"]:
                return False
            # json.dumps能成功序列化
            json.dumps(json_ld, ensure_ascii=False)
            return True
        except Exception:
            return False

    def _clean_empty(self, d: dict) -> dict:
        """递归清理空值"""
        return {k: v for k, v in d.items() if v not in (None, "", [], {})}
