"""数据报表API路由"""

import uuid
import json
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from app.models.schemas import ReportRequest, ReportResponse
from app.core.reporter import ReportGenerator
from app.utils.config import get_data_dir

router = APIRouter()


@router.post("/preview")
async def preview_report(data: dict):
    """生成报告HTML并返回内嵌内容（非文件下载）"""
    try:
        gen = ReportGenerator()
        report_format = data.get("format", "html")
        result = gen.generate(
            evaluation_data=data,
            output_format=report_format,
            include_charts=data.get("include_charts", True),
        )
        html_path = result["file_path"]
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return {"html": html_content, "report_id": result["report_id"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"报告预览生成失败: {str(e)}")


@router.post("/generate", response_model=ReportResponse)
async def generate_report(req: ReportRequest):
    """生成评测报表"""
    try:
        gen = ReportGenerator()

        # 尝试从本地加载评测数据
        data = _load_evaluation_data(req.evaluation_id)

        result = gen.generate(
            evaluation_data=data,
            output_format=req.format.value,
            include_charts=req.include_charts,
        )

        return ReportResponse(
            report_id=result["report_id"],
            format=req.format,
            file_path=result["file_path"],
            created_at=datetime.fromisoformat(result["created_at"]) if isinstance(result["created_at"], str) else result["created_at"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"报表生成失败: {str(e)}")


@router.post("/generate-from-data", response_model=ReportResponse)
async def generate_report_from_data(data: dict):
    """直接传入评测数据生成报表"""
    try:
        gen = ReportGenerator()
        report_format = data.get("format", "html")
        result = gen.generate(
            evaluation_data=data,
            output_format=report_format,
            include_charts=data.get("include_charts", True),
        )
        return ReportResponse(
            report_id=result["report_id"],
            format=report_format,
            file_path=result["file_path"],
            created_at=datetime.fromisoformat(result["created_at"]) if isinstance(result["created_at"], str) else result["created_at"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"报表生成失败: {str(e)}")


@router.get("/export/{report_id}")
async def export_report(report_id: str, format: str = "html"):
    """下载报表文件"""
    output_dir = get_data_dir() / "reports"
    ext = "pdf" if format == "pdf" else "html"
    file_path = output_dir / f"{report_id}.{ext}"

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"报表文件不存在: {report_id}.{ext}")

    media_type = "application/pdf" if format == "pdf" else "text/html"
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=f"GEO优化报告_{report_id}.{ext}",
    )


@router.get("/history")
async def list_reports():
    """列出历史报表"""
    output_dir = get_data_dir() / "reports"
    reports = []
    for f in sorted(output_dir.glob("*.html"), key=lambda x: x.stat().st_mtime, reverse=True):
        reports.append({
            "report_id": f.stem,
            "format": "html",
            "size_kb": round(f.stat().st_size / 1024, 1),
            "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    for f in sorted(output_dir.glob("*.pdf"), key=lambda x: x.stat().st_mtime, reverse=True):
        reports.append({
            "report_id": f.stem,
            "format": "pdf",
            "size_kb": round(f.stat().st_size / 1024, 1),
            "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return {"reports": reports[:50]}  # 最多返回50条


def _load_evaluation_data(eval_id: str) -> dict:
    """加载评测数据"""
    data_dir = get_data_dir() / "reports"
    # 尝试JSON格式
    json_path = data_dir / f"{eval_id}.json"
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    # 如果没有，返回示例数据
    return {
        "evaluation_id": eval_id,
        "overall_score": 0,
        "platform_results": [],
        "weak_points": [],
        "suggestions": [],
    }
