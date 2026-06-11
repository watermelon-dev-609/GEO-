"""审计日志查询API"""

from pathlib import Path
from fastapi import APIRouter, Query, HTTPException
from app.utils.config import load_settings

router = APIRouter()


@router.get("/logs")
async def query_audit_logs(
    date: str | None = Query(default=None, description="日期 YYYY-MM-DD"),
    action: str | None = Query(default=None, description="路径过滤"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    """分页查询审计日志"""
    import json
    import time

    if date is None:
        date = time.strftime("%Y-%m-%d")

    settings = load_settings()
    data_dir = settings.get("system", {}).get("data_dir", "./data")
    base = Path(data_dir)
    if not base.is_absolute():
        base = Path(__file__).resolve().parent.parent.parent / data_dir

    filepath = base / "audit" / f"{date}.jsonl"
    if not filepath.exists():
        return {"entries": [], "total": 0, "page": page, "page_size": page_size, "message": "该日无审计日志"}

    entries = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if action and action not in entry.get("path", ""):
                    continue
                entries.append(entry)
            except json.JSONDecodeError:
                continue

    entries.reverse()
    total = len(entries)
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "entries": entries[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/export")
async def export_audit_logs(date: str | None = Query(default=None)):
    """导出审计日志为CSV"""
    import csv
    import io
    import json
    import time
    from fastapi.responses import Response

    if date is None:
        date = time.strftime("%Y-%m-%d")

    settings = load_settings()
    data_dir = settings.get("system", {}).get("data_dir", "./data")
    base = Path(data_dir)
    if not base.is_absolute():
        base = Path(__file__).resolve().parent.parent.parent / data_dir

    filepath = base / "audit" / f"{date}.jsonl"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="该日无审计日志")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["时间", "方法", "路径", "客户端IP", "状态码", "耗时(ms)"])

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                writer.writerow([
                    entry.get("timestamp", ""),
                    entry.get("method", ""),
                    entry.get("path", ""),
                    entry.get("client_ip", ""),
                    entry.get("status", ""),
                    entry.get("duration_ms", ""),
                ])
            except json.JSONDecodeError:
                continue

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=audit-log-{date}.csv"},
    )
