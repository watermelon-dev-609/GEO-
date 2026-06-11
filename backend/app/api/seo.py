"""SEO数据集成API"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from app.core.seo_connector import SEODataImporter

router = APIRouter()


@router.post("/import")
async def import_seo_data(
    file: UploadFile = File(...),
    source: str = Form(default="baidu"),
):
    """导入SEO关键词数据（CSV）"""
    if not file.filename or not file.filename.endswith(('.csv', '.txt')):
        raise HTTPException(status_code=400, detail="请上传CSV格式文件")
    try:
        content = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            content = (await file.read()).decode("gbk")
        except Exception:
            raise HTTPException(status_code=400, detail="无法解析文件编码，请使用UTF-8或GBK编码")

    try:
        result = SEODataImporter.import_csv(content, source)
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV解析失败: {e}")


@router.get("/analysis")
async def seo_analysis():
    """GEO+SEO联合分析"""
    result = SEODataImporter.get_analysis()
    return result
