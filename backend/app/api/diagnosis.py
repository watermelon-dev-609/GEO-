"""内容快速诊断 API"""

import logging
from fastapi import APIRouter, HTTPException
from app.core.diagnoser import ContentDiagnoser
from app.models.schemas import QuickDiagnosisRequest, DeepDiagnosisRequest, BatchDiagnosisRequest

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_diagnoser(with_llm: bool = True):
    """获取诊断器实例"""
    from app.services.llm.base import LLMFactory
    from app.utils.config import load_settings, load_api_keys
    from app.models.enums import AIPlatform

    settings = load_settings()
    api_keys = load_api_keys()
    llm = None

    if with_llm:
        default_platform = settings.get("llm", {}).get("default_model", "deepseek")
        plat_cfg = settings.get("llm", {}).get("platforms", {}).get(default_platform, {})
        key_info = api_keys.get("platforms", {}).get(default_platform, {})

        api_key = key_info.get("api_key", "")
        if api_key and "your-" not in api_key:
            adapter_type = AIPlatform(default_platform).adapter_type
            llm = LLMFactory.create(
                platform=adapter_type,
                api_key=api_key,
                model_name=plat_cfg.get("model_name", ""),
                base_url=plat_cfg.get("base_url"),
            )
            if adapter_type == "wenxin":
                llm.secret_key = key_info.get("secret_key", "")

    return ContentDiagnoser(llm)


@router.post("/quick")
async def quick_diagnosis(req: QuickDiagnosisRequest):
    """快速诊断 — 纯规则引擎（无需LLM），秒级返回"""
    text = req.text
    sandtable_type = req.sandtable_type

    if not text or len(text.strip()) < 50:
        return {
            "overall_score": 0,
            "dimensions": {},
            "top_issues": ["文本过短（<50字），无法进行有效诊断"],
            "text_stats": {"length": len(text)},
            "diagnosis_mode": "rule",
        }

    diagnoser = ContentDiagnoser()
    return diagnoser.diagnose_sync(text, sandtable_type)


@router.post("/deep")
async def deep_diagnosis(req: DeepDiagnosisRequest):
    """深度诊断 — LLM辅助，返回详细分析和改进建议"""
    text = req.text
    sandtable_type = req.sandtable_type

    if not text or len(text.strip()) < 50:
        raise HTTPException(status_code=400, detail="文本过短（<50字），无法诊断")

    try:
        diagnoser = _get_diagnoser(with_llm=True)
        result = await diagnoser.diagnose(text, sandtable_type)
        return result
    except Exception as e:
        logger.exception("深度诊断失败")
        raise HTTPException(status_code=500, detail=f"诊断服务暂时不可用: {e}")


@router.post("/batch")
async def batch_diagnosis(req: BatchDiagnosisRequest):
    """批量诊断 — 多段文本逐一评分"""
    texts = req.texts
    sandtable_type = req.sandtable_type

    if not texts:
        raise HTTPException(status_code=400, detail="请提供待诊断文本列表")

    diagnoser = ContentDiagnoser()
    results = []
    for i, text in enumerate(texts):
        if text and len(text.strip()) >= 50:
            result = diagnoser.diagnose_sync(text, sandtable_type)
            result["index"] = i
            results.append(result)
        else:
            results.append({
                "index": i,
                "overall_score": 0,
                "top_issues": ["文本过短，跳过诊断"],
            })

    avg = round(sum(r.get("overall_score", 0) for r in results) / max(len(results), 1), 1)
    return {
        "total": len(texts),
        "diagnosed": len(results),
        "average_score": avg,
        "results": results,
    }


@router.post("/to-hints")
async def diagnosis_to_hints(req: QuickDiagnosisRequest):
    """诊断结果转优化提示 — 一键反馈至GEO工坊改写"""
    text = req.text
    sandtable_type = req.sandtable_type

    if not text or len(text.strip()) < 50:
        return {
            "hints": ["文本过短（少于50字），请提供更完整的企业/产品文案以便诊断"],
            "ready_for_rewrite": True,
        }

    diagnoser = ContentDiagnoser()
    result = diagnoser.diagnose_sync(text, sandtable_type)

    hints = _map_diagnosis_to_hints(result)

    return {
        "hints": hints,
        "ready_for_rewrite": True,
    }


def _map_diagnosis_to_hints(diagnosis: dict) -> list[str]:
    """将诊断结果中的弱项映射为可操作的优化提示"""
    hints = []
    dimensions = diagnosis.get("dimensions", {})

    hint_map = {
        "entity_completeness": {
            "low": "在文案首段和标题中突出企业全称、地域标识、产品/服务关键词，确保AI实体识别系统可准确提取",
            "medium": "补充企业名称完整表述和地域标识，增强AI实体识别信号",
        },
        "structure_quality": {
            "low": "增加H2/H3层级标题和要点列表（•或-），控制段落长度在200-500字，降低AI解析成本",
            "medium": "适当增加标题层级和列表结构，提升结构化程度以便AI提取关键信息",
        },
        "quantified_data": {
            "low": "增加量化数据（项目数量、技术参数、服务年限等），AI对数字信号的敏感度是纯文本的3倍以上",
            "medium": "补充具体量化的技术参数或项目数据，增强AI引用信号的数字密度",
        },
        "faq_friendliness": {
            "low": "在文中嵌入FAQ问答对（如'XX沙盘能做什么？''如何选择沙盘厂家？'），适配对话式AI检索场景",
            "medium": "增加自然问答结构，提升AI在对话式检索场景中的匹配概率",
        },
        "source_credibility": {
            "low": "删除未经证实的绝对化表述，用具体案例、数据、认证替代形容词堆砌，提升信源可信度",
            "medium": "审视文中的对比/排名声明，用可验证的具体数据替代模糊表述",
        },
    }

    for dim_key, dim_data in dimensions.items():
        score = dim_data.get("score", 100)
        if score < 40:
            level = "low"
        elif score < 60:
            level = "medium"
        else:
            continue
        if dim_key in hint_map:
            hints.append(hint_map[dim_key][level])

    # 附加 top_issues 中的具体问题
    top_issues = diagnosis.get("top_issues", [])
    for issue in top_issues[:2]:
        hints.append(f"具体问题修复: {issue}")

    if not hints:
        hints.append("各项指标表现良好，可进行常规GEO优化")

    return hints
