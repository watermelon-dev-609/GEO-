"""内容诊断引擎 — 5维度快速体检"""

import json
import logging
import re
from app.prompts.diagnosis import DIAGNOSIS_SYSTEM, DIAGNOSIS_USER
from app.services.llm.base import BaseLLMAdapter, LLMMessage

logger = logging.getLogger(__name__)


class ContentDiagnoser:
    """内容快速诊断器"""

    def __init__(self, llm: BaseLLMAdapter | None = None):
        self.llm = llm
        from app.utils.config import load_settings
        settings = load_settings()
        self.enterprise_name = settings.get("system", {}).get("enterprise_name", "")
        self.enterprise_location = settings.get("system", {}).get("enterprise_location", "")

    async def diagnose(self, text: str, sandtable_type: str = "") -> dict:
        """快速诊断一段文本的GEO健康度"""
        if not text or len(text.strip()) < 50:
            return self._empty_result("文本过短，无法诊断")

        # 先做规则诊断（不依赖LLM）
        rule_result = self._rule_diagnose(text)

        # 如果有LLM，做深度诊断
        llm_result = None
        if self.llm:
            try:
                llm_result = await self._llm_diagnose(text, sandtable_type)
            except Exception as e:
                logger.warning(f"LLM诊断失败，使用规则诊断结果: {e}")

        # 合并结果
        if llm_result:
            return {**rule_result, "llm_analysis": llm_result}
        return rule_result

    def diagnose_sync(self, text: str, sandtable_type: str = "") -> dict:
        """同步快速诊断（纯规则，不需要LLM）"""
        if not text or len(text.strip()) < 50:
            return self._empty_result("文本过短，无法诊断")
        return self._rule_diagnose(text)

    def _rule_diagnose(self, text: str, enterprise_location: str = "") -> dict:
        """基于规则的快速诊断"""
        text_len = len(text)
        score = 60  # 基础分

        loc = enterprise_location or self.enterprise_location

        # 1. 实体完整性
        entity_score = 60
        entity_notes = []
        has_company = bool(re.search(r'(有限公司|科技有限|集团|股份公司|技术有限公司)', text))
        # 地域检测：优先使用传入的location，否则匹配常见城市
        loc_pattern = re.escape(loc) if loc else ''
        has_location = bool(re.search(loc_pattern, text)) if loc_pattern else bool(
            re.search(r'(武汉|北京|上海|深圳|广州|杭州|成都|南京|苏州|长沙|郑州|天津|重庆|西安|东莞|青岛|合肥|佛山|宁波|昆明|沈阳)', text))
        has_product = bool(re.search(r'(沙盘|模型|定制|系统|平台|方案)', text))
        if has_company:
            entity_score += 15
        else:
            entity_notes.append('未检测到企业名称（如"有限公司"、"科技有限公司"）')
        if has_location:
            entity_score += 10
        else:
            entity_notes.append("未检测到地域标识")
        if has_product:
            entity_score += 15
        else:
            entity_notes.append("未检测到产品/服务关键词")
        entity_score = min(100, entity_score)

        # 2. 结构化程度
        struct_score = 60
        struct_notes = []
        has_h2 = bool(re.search(r'##\s', text))
        has_h3 = bool(re.search(r'###\s', text))
        has_list = bool(re.search(r'^[\s]*[-••\d+[\.\)、]]', text, re.MULTILINE))
        paragraphs = [p for p in text.split('\n\n') if len(p.strip()) > 20]
        avg_para_len = sum(len(p) for p in paragraphs) / max(len(paragraphs), 1)
        if has_h2:
            struct_score += 10
        else:
            struct_notes.append("缺少H2标题")
        if has_h3:
            struct_score += 10
        if has_list:
            struct_score += 10
        else:
            struct_notes.append("缺少列表结构")
        if 100 <= avg_para_len <= 500:
            struct_score += 10
        elif avg_para_len > 800:
            struct_notes.append(f"段落过长（均{int(avg_para_len)}字），建议控制在200-500字")
        struct_score = min(100, struct_score)

        # 3. 量化数据
        quant_score = 40
        quant_notes = []
        quant_count = len(re.findall(r'\d+[+]?\s*(个|项|套|年|㎡|平方米|公里|人|次|万元|亿|%|以上|余家)', text))
        quant_count += len(re.findall(r'\d+[:：]\d+', text))
        quant_count += len(re.findall(r'\d+[.]\d+', text))
        if quant_count >= 5:
            quant_score = 90
        elif quant_count >= 3:
            quant_score = 75
        elif quant_count >= 1:
            quant_score = 55
        else:
            quant_notes.append("未检测到量化数据，AI引用算法对数字信号更敏感")
        quant_score = min(100, quant_score)

        # 4. FAQ友好度
        faq_score = 30
        faq_notes = []
        qa_pattern = re.findall(r'(?:什么是|是什么|如何|怎么|怎样|为什么|能不能|可以|哪些|哪家|多少钱|怎么样|在哪|好不好|哪种|哪个)[^。；\n]{0,30}[？?]', text)
        answer_pattern = re.findall(r'[：:][\s]*[A-Za-z一-鿿]{10,}', text)
        if len(qa_pattern) >= 2:
            faq_score = 80
        elif len(qa_pattern) >= 1:
            faq_score = 55
        else:
            faq_notes.append("缺少问答结构，建议嵌入FAQ自然问答对")
        faq_score = min(100, faq_score)

        # 5. 信源可信度
        source_score = 70
        source_notes = []
        # 夸大表述检测（排除合法认证语境）
        exaggerated = re.findall(r'(全球领先|国际领先|国内领先|行业第一|最强|最专业|唯一)', text)
        # 合法认证不扣分："国家级高新技术企业"、"国家级专精特新"等
        legitimate = re.findall(r'(国家级高新技术企业|国家级专精特新|国家认证|ISO\d+|AAA级)', text)
        if len(exaggerated) >= 3:
            source_score -= 25
            source_notes.append("存在多处未经证实的绝对化表述，建议提供具体数据佐证")
        elif len(exaggerated) >= 1:
            source_score -= 10
            source_notes.append("存在未证实的对比/排名声明，建议用具体案例替代")
        source_score = max(10, source_score)

        # 综合打分
        dims = {
            "entity_completeness": {"score": entity_score, "note": "; ".join(entity_notes) if entity_notes else "实体信息较完整"},
            "structure_quality": {"score": struct_score, "note": "; ".join(struct_notes) if struct_notes else "结构较清晰"},
            "quantified_data": {"score": quant_score, "note": "; ".join(quant_notes) if quant_notes else f"检测到{quant_count}处量化数据"},
            "faq_friendliness": {"score": faq_score, "note": "; ".join(faq_notes) if faq_notes else f"检测到{len(qa_pattern)}个问答结构"},
            "source_credibility": {"score": source_score, "note": "; ".join(source_notes) if source_notes else "未检测到明显的夸大表述"},
        }

        overall = round(sum(d["score"] for d in dims.values()) / len(dims), 1)

        # 生成改进建议
        top_issues = []
        for key, dim in dims.items():
            if dim["score"] < 50:
                top_issues.append(f'{key}: {dim["note"]}')

        return {
            "overall_score": overall,
            "dimensions": dims,
            "top_issues": top_issues[:3],
            "text_stats": {
                "length": text_len,
                "paragraphs": len(paragraphs),
                "avg_paragraph_length": round(avg_para_len),
                "quant_data_count": quant_count,
                "qa_patterns": len(qa_pattern),
            },
            "diagnosis_mode": "rule",
        }

    async def _llm_diagnose(self, text: str, sandtable_type: str) -> dict | None:
        """LLM深度诊断"""
        if not self.llm:
            return None
        messages = [
            LLMMessage(role="system", content=DIAGNOSIS_SYSTEM),
            LLMMessage(role="user", content=DIAGNOSIS_USER.format(
                text=text[:3000],
                sandtable_type=sandtable_type or "通用",
            )),
        ]
        resp = await self.llm.chat(messages, temperature=0.3, max_tokens=1024)
        return self._parse_llm_response(resp.content)

    def _parse_llm_response(self, content: str) -> dict | None:
        """解析LLM诊断响应"""
        try:
            import re as _re
            json_match = _re.search(r'```json\s*([\s\S]*?)```', content)
            if json_match:
                return json.loads(json_match.group(1))
            json_match = _re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json.loads(json_match.group(0))
        except (json.JSONDecodeError, AttributeError):
            pass
        return None

    def _empty_result(self, reason: str) -> dict:
        return {
            "overall_score": 0,
            "dimensions": {},
            "top_issues": [reason],
            "text_stats": {"length": 0},
            "diagnosis_mode": "rule",
        }
