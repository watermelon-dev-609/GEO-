"""内容版本管理API"""

from fastapi import APIRouter, HTTPException, Query
from app.core.version_manager import VersionManager

router = APIRouter()


@router.get("/{text_id}")
async def list_versions(text_id: str):
    """列出文本的所有版本"""
    versions = VersionManager.list_versions(text_id)
    return {
        "text_id": text_id,
        "total": len(versions),
        "versions": [
            {
                "version_id": v.version_id,
                "title": v.title,
                "platform": v.platform,
                "version_num": v.version_num,
                "created_at": v.created_at,
                "word_count": v.word_count,
                "tags": v.tags,
                "notes": v.notes,
            }
            for v in reversed(versions)
        ],
    }


@router.get("/{text_id}/{version_id}")
async def get_version(text_id: str, version_id: str):
    """获取指定版本详情"""
    v = VersionManager.get_version(text_id, version_id)
    if not v:
        raise HTTPException(status_code=404, detail="版本不存在")
    return {
        "version_id": v.version_id,
        "text_id": v.text_id,
        "title": v.title,
        "content": v.content,
        "platform": v.platform,
        "version_num": v.version_num,
        "created_at": v.created_at,
        "word_count": v.word_count,
        "tags": v.tags,
        "notes": v.notes,
    }


@router.post("/{text_id}")
async def save_version(
    text_id: str,
    content: str = Query(..., description="版本正文内容"),
    title: str = Query(default=""),
    platform: str = Query(default=""),
    notes: str = Query(default=""),
):
    """保存新版本"""
    v = VersionManager.save_version(
        text_id=text_id,
        content=content,
        title=title,
        platform=platform,
        notes=notes,
    )
    return {"status": "ok", "version": {"version_id": v.version_id, "version_num": v.version_num, "title": v.title}}


@router.post("/{text_id}/rollback/{version_id}")
async def rollback_version(text_id: str, version_id: str):
    """回滚到指定版本"""
    v = VersionManager.rollback(text_id, version_id)
    if not v:
        raise HTTPException(status_code=404, detail="版本不存在")
    return {"status": "ok", "new_version": {"version_id": v.version_id, "version_num": v.version_num, "title": v.title}}


@router.get("/{text_id}/compare")
async def compare_versions(
    text_id: str,
    v1: str = Query(..., description="版本1 ID"),
    v2: str = Query(..., description="版本2 ID"),
):
    """对比两个版本"""
    result = VersionManager.compare(text_id, v1, v2)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.delete("/{text_id}/{version_id}")
async def delete_version(text_id: str, version_id: str):
    """删除版本"""
    if VersionManager.delete_version(text_id, version_id):
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="版本不存在")
