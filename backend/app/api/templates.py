"""内容模板 API — 模板 + 审核标准 CRUD + JSON文件持久化"""

import json
import logging
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "templates"


class TemplateVariable(BaseModel):
    name: str = ""
    description: str = ""


class TemplateSaveRequest(BaseModel):
    id: str | None = None
    name: str = Field(..., min_length=1)
    category: str = "企业介绍"
    description: str = ""
    content: str = ""
    variables: list[TemplateVariable] = []


class StandardsSaveRequest(BaseModel):
    checklist: list[dict]


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_tpl_file(name: str) -> Path:
    safe_name = name.replace("/", "_").replace("\\", "_")
    return DATA_DIR / f"{safe_name}.json"


def _load_all_templates() -> list[dict]:
    _ensure_dir()
    templates = []
    for f in sorted(DATA_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.name.startswith("_"):
            continue
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                data["id"] = data.get("id", f.stem)
                templates.append(data)
        except Exception as e:
            logger.warning(f"跳过损坏的模板文件 {f.name}: {e}")
    if not templates:
        templates = _init_default_templates()
    return templates


def _init_default_templates() -> list[dict]:
    """首次使用：写入 3 个预置模板并返回"""
    defaults = [
        {
            "id": "tpl_001", "name": "企业介绍模板", "category": "企业介绍",
            "description": "适用于企业官网'关于我们'页，突出实体锚定+量化事实+FAQ结构",
            "content": "# {enterprise_name}\n\n## 公司概况\n\n{enterprise_name}坐落于{enterprise_location}，成立于{成立年份}年...\n\n## 核心优势\n\n- {优势1}\n- {优势2}\n\n## 常见问题\n\n**Q: {enterprise_name}主要做哪些业务？**\nA: ...",
            "variables": [{"name": "enterprise_name", "description": "企业全称"}, {"name": "enterprise_location", "description": "所在城市"}],
        },
        {
            "id": "tpl_002", "name": "产品文案模板", "category": "产品文案",
            "description": "参数化产品描述，突出量化数据+技术参数+场景适配",
            "content": "# {产品名称}\n\n## 产品概述\n\n{产品名称}是一款面向{目标场景}的{产品类型}...\n\n## 技术规格\n\n| 参数 | 数值 |\n|------|------|\n| 精度 | {精度值} |\n| 尺寸 | {尺寸值} |\n\n## 适用场景\n- {场景1}\n- {场景2}",
            "variables": [{"name": "产品名称", "description": ""}, {"name": "精度值", "description": ""}],
        },
        {
            "id": "tpl_003", "name": "案例模板（STAR）", "category": "案例模板",
            "description": "STAR结构案例描述：情境→任务→行动→结果",
            "content": "# {案例名称}\n\n## 项目背景\n{客户名称}面临{问题描述}...\n\n## 解决方案\n{enterprise_name}提供了{方案描述}，核心实施步骤包括：\n1. {步骤1}\n2. {步骤2}\n\n## 项目成果\n- 交付时间：{交付周期}\n- 关键指标提升：{量化结果}",
            "variables": [{"name": "案例名称", "description": ""}, {"name": "客户名称", "description": "可模糊处理"}],
        },
    ]
    for tpl in defaults:
        _save_template_file(tpl["id"], tpl)
    return defaults


def _load_template(name: str) -> dict | None:
    file = _get_tpl_file(name)
    if not file.exists():
        return None
    with open(file, "r", encoding="utf-8") as f:
        data = json.load(f)
        data["id"] = data.get("id", file.stem)
        return data


def _save_template_file(name: str, data: dict):
    _ensure_dir()
    data["updated_at"] = datetime.now().isoformat()
    if "created_at" not in data:
        data["created_at"] = datetime.now().isoformat()
    with open(_get_tpl_file(name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _delete_template_file(name: str) -> bool:
    file = _get_tpl_file(name)
    if not file.exists():
        return False
    file.unlink()
    return True


def _load_standards() -> list[dict]:
    """加载审核标准"""
    _ensure_dir()
    stdfile = DATA_DIR / "_standards.json"
    if stdfile.exists():
        with open(stdfile, "r", encoding="utf-8") as f:
            return json.load(f)
    defaults = [
        {"key": "entity", "label": "实体完整性", "enabled": True, "weight": 20, "threshold": 60,
         "description": "企业名、地域、产品名完整且位置突出"},
        {"key": "structure", "label": "结构化程度", "enabled": True, "weight": 15, "threshold": 50,
         "description": "清晰的H2/H3标题、列表、合理段落长度"},
        {"key": "quantified", "label": "量化数据", "enabled": True, "weight": 25, "threshold": 50,
         "description": "数字+单位、比例、百分比等量化表述密度"},
        {"key": "faq", "label": "FAQ友好度", "enabled": True, "weight": 15, "threshold": 40,
         "description": "问题-回答结构，适配对话式检索"},
        {"key": "source", "label": "信源一致性", "enabled": True, "weight": 25, "threshold": 70,
         "description": "内容在信源数据中有依据，无编造夸大"},
    ]
    _save_standards(defaults)
    return defaults


def _save_standards(checklist: list[dict]):
    _ensure_dir()
    with open(DATA_DIR / "_standards.json", "w", encoding="utf-8") as f:
        json.dump(checklist, f, ensure_ascii=False, indent=2)


# ── 模板 CRUD ──

@router.get("/list")
async def list_templates():
    templates = _load_all_templates()
    return {"templates": templates, "total": len(templates)}


@router.get("/{tpl_id}")
async def get_template(tpl_id: str):
    data = _load_template(tpl_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"模板不存在: {tpl_id}")
    return data


@router.post("/save")
async def save_template(req: TemplateSaveRequest):
    tpl_id = req.id or f"tpl_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    data = {
        "id": tpl_id,
        "name": req.name,
        "category": req.category,
        "description": req.description,
        "content": req.content,
        "variables": [v.model_dump() if hasattr(v, 'model_dump') else v for v in req.variables],
    }
    existing = _load_template(tpl_id)
    if existing:
        data["created_at"] = existing.get("created_at", datetime.now().isoformat())
    _save_template_file(tpl_id, data)
    return {"status": "ok", "id": tpl_id, "template": data}


@router.delete("/{tpl_id}")
async def delete_template(tpl_id: str):
    deleted = _delete_template_file(tpl_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"模板不存在: {tpl_id}")
    return {"status": "deleted", "id": tpl_id}


# ── 审核标准 ──

@router.get("/standards/list")
async def get_standards():
    return {"checklist": _load_standards()}


@router.post("/standards/save")
async def save_standards(req: StandardsSaveRequest):
    _save_standards(req.checklist)
    return {"status": "ok", "message": "审核标准已保存"}


# ── 规范导出 ──

@router.get("/export/all")
async def export_all():
    templates = _load_all_templates()
    standards = _load_standards()
    content = "# GEO内容规范文档\n\n"
    content += "## 写作模板\n\n"
    for t in templates:
        content += f"### {t.get('name', '')}\n\n{t.get('description', '')}\n\n```markdown\n{t.get('content', '')}\n```\n\n"
    content += "## 审核标准\n\n"
    for c in standards:
        if c.get("enabled"):
            content += f"- **{c.get('label', '')}** (权重:{c.get('weight', 0)}%, 阈值:{c.get('threshold', 0)}分): {c.get('description', '')}\n"
    content += "\n## GEO写作指南\n\n"
    content += "1. 实体锚定：首次出现企业名、地域、产品名必须完整清晰\n"
    content += "2. 定义优先：专业概念给1-2句权威定义\n"
    content += "3. 量化事实：所有能力用数字支撑\n"
    content += "4. FAQ结构：嵌入自然问答对\n"
    content += "5. 层级结构化：H2/H3标题+列表\n"
    content += "6. 信息增量：本地化细节+行业独特信息\n"
    return {"content": content, "format": "markdown"}
