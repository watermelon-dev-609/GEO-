"""系统日志查询API"""

from pathlib import Path
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/recent")
async def recent_logs(
    level: str = Query(default="ERROR"),
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """查询最近日志"""
    from app.utils.config import load_settings
    settings = load_settings()
    log_file = settings.get("logging", {}).get("file", "")
    if not log_file:
        return {"entries": [], "message": "文件日志未配置，无法查询历史日志"}

    log_path = Path(log_file)
    if not log_path.is_absolute():
        log_path = Path(__file__).resolve().parent.parent.parent / log_file

    if not log_path.exists():
        return {"entries": [], "message": f"日志文件不存在: {log_path}"}

    import re
    entries = []
    level_pattern = re.compile(rf"\[({level.upper()})\]")
    time_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(hours=hours)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

        for line in reversed(lines):
            if len(entries) >= limit:
                break
            if not level_pattern.search(line):
                continue
            m = time_pattern.match(line)
            if m and m.group(1) < cutoff_str:
                continue
            entries.append({"line": line.rstrip()})

        entries.reverse()
        return {"entries": entries, "count": len(entries)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取日志失败: {e}")


@router.get("/download")
async def download_logs():
    """下载日志文件"""
    from app.utils.config import load_settings
    settings = load_settings()
    log_file = settings.get("logging", {}).get("file", "")
    if not log_file:
        raise HTTPException(status_code=400, detail="文件日志未配置")

    log_path = Path(log_file)
    if not log_path.is_absolute():
        log_path = Path(__file__).resolve().parent.parent.parent / log_file

    if not log_path.exists():
        raise HTTPException(status_code=404, detail="日志文件不存在")

    return FileResponse(
        path=str(log_path),
        filename=f"geo-system-log-{log_path.stem}.log",
        media_type="text/plain",
    )
