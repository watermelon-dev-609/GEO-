"""JSON-LD生成API路由"""

from fastapi import APIRouter, HTTPException
from app.models.schemas import JSONLDRequest, JSONLDResponse
from app.models.enums import SandtableType
from app.core.jsonld_gen import JSONLDGenerator, SCHEMA_MAPPING

router = APIRouter()


@router.post("/generate", response_model=JSONLDResponse)
async def generate_jsonld(req: JSONLDRequest):
    """生成JSON-LD结构化代码"""
    try:
        gen = JSONLDGenerator()
        result = gen.generate(
            sandtable_type=req.sandtable_type,
            enterprise_info=req.enterprise_info,
            product_info=req.product_info,
            include_faq=req.include_faq,
            include_breadcrumb=req.include_breadcrumb,
        )
        return JSONLDResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"JSON-LD生成失败: {str(e)}")


@router.get("/templates")
async def get_templates():
    """获取所有沙盘类型的Schema映射"""
    return {
        "schema_mapping": SCHEMA_MAPPING,
        "sandtable_types": {t.value: t.label for t in SandtableType},
    }


@router.get("/templates/{sandtable_type}")
async def get_template_by_type(sandtable_type: SandtableType):
    """获取指定沙盘类型的Schema模板"""
    schemas = SCHEMA_MAPPING.get(sandtable_type.value, [])
    return {
        "sandtable_type": sandtable_type.value,
        "sandtable_label": sandtable_type.label,
        "schemas": schemas,
    }


@router.post("/validate")
async def validate_jsonld(req: dict):
    """校验JSON-LD代码合法性"""
    import json
    gen = JSONLDGenerator()
    try:
        if isinstance(req.get("json_ld"), str):
            data = json.loads(req["json_ld"])
        else:
            data = req.get("json_ld", req)
        valid = gen._validate(data)
        return {"valid": valid}
    except Exception as e:
        return {"valid": False, "error": str(e)}
