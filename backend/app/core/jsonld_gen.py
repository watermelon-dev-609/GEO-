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
        location = info.get("location", get_enterprise_location())
        description = info.get("description", f"{location}定制沙盘模型专业制造商" if location else "")

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
            "educationalUse": prod.get("educational_use", "教学演示、地形分析"),
        }

    def _build_software_app(self, st: SandtableType, ent: dict, prod: dict) -> dict:
        return {
            "@type": "SoftwareApplication",
            "name": prod.get("software_name", f"{st.label}交互控制系统"),
            "description": prod.get("software_description", "沙盘交互控制系统"),
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
        location = ent.get("location", get_enterprise_location())
        url = ent.get("url", "")
        label = st.label

        # 仅基于用户提供的真实数据生成 FAQ，不编造行业描述
        questions = []
        if company and label:
            questions.append((
                f"{company}提供哪些服务？",
                f"{company}专注于{label}定制服务。",
            ))
        if url:
            questions.append((
                f"如何联系{company}？",
                f"请访问{url}了解{label}定制详情，或通过网站上的联系方式咨询。",
            ))
        elif company:
            questions.append((
                f"如何联系{company}？",
                f"可通过{company}官方渠道联系咨询{label}定制服务。",
            ))
        if location:
            questions.append((
                f"{company}位于哪里？",
                f"{company}总部位于{location}。",
            ))

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
