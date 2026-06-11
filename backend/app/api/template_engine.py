"""模板引擎 API — 平台模板CRUD、版本管理、Diff、预览、回滚

提供对 data/platform_templates/*.yaml 的完整管理接口。
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 请求/响应模型 ──

class TemplateUpdateRequest(BaseModel):
    config: dict  # 完整 YAML 模板内容


class TemplatePreviewRequest(BaseModel):
    platform_id: str
    sandtable_type: str = "smart_city"
    enterprise_name: str = ""
    enterprise_location: str = ""


class TemplateRollbackRequest(BaseModel):
    version_id: str


# ── 端点 ──

@router.get("/platforms")
async def list_platforms():
    """列出所有平台模板及其状态"""
    try:
        from app.core.template_engine import load_all_templates, validate_platform

        templates = load_all_templates()
        result = []
        for pid, tmpl in sorted(templates.items()):
            if pid == "base":
                continue
            validation = validate_platform(pid)
            result.append({
                "platform_id": pid,
                "platform_name": tmpl.get("platform_name", pid),
                "version": tmpl.get("version", 1),
                "updated_at": tmpl.get("updated_at", ""),
                "strategy": (tmpl.get("strategy", "") or "")[:60],
                "valid": validation["valid"],
                "issues": validation["issues"],
                "template_exists": validation["template_exists"],
            })
        return {"status": "ok", "total": len(result), "platforms": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取平台列表失败: {e}")


@router.get("/watchdog-status")
async def watchdog_status():
    """获取文件监控状态与缓存信息"""
    try:
        from app.core.template_watcher import get_watcher_status
        from app.core.template_engine import get_cache_info

        watcher = get_watcher_status()
        cache = get_cache_info()

        mode = "watchdog" if watcher.get("watching") else "polling"

        return {
            "status": "ok",
            "mode": mode,
            "watchdog": watcher,
            "cache": cache,
        }
    except ImportError:
        return {
            "status": "ok",
            "mode": "polling",
            "watchdog": {"watching": False, "watched_dir": "", "last_event": {}, "debounce_pending": 0},
            "cache": {"entries": 0, "age_seconds": -1, "ttl": 60, "cached_platforms": []},
        }


@router.get("/{platform_id}")
async def get_platform_template(platform_id: str):
    """获取指定平台的完整模板配置"""
    try:
        from app.core.template_engine import load_platform_template

        template = load_platform_template(platform_id)
        if template.get("_source") == "empty_fallback":
            raise HTTPException(status_code=404, detail=f"平台模板不存在: {platform_id}")

        return {"status": "ok", "platform_id": platform_id, "template": template}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模板失败: {e}")


@router.put("/{platform_id}")
async def update_platform_template(platform_id: str, req: TemplateUpdateRequest):
    """更新平台模板配置（自动创建历史版本）"""
    try:
        import yaml
        import tempfile
        import os
        from pathlib import Path
        from app.core.template_engine import (
            load_platform_template, save_template_version,
            validate_template, invalidate_cache, _get_templates_dir,
        )

        new_config = req.config

        # 校验
        issues = validate_template(new_config)
        if issues:
            raise HTTPException(
                status_code=400,
                detail=f"模板校验失败: {'; '.join(issues[:5])}"
            )

        # 确保 platform_id 一致
        new_config["platform_id"] = platform_id

        # 保存当前版本
        current = load_platform_template(platform_id)
        if current.get("_source") != "empty_fallback":
            save_template_version(platform_id, current)

        # 更新版本号和时间
        new_config["version"] = current.get("version", 0) + 1
        new_config["updated_at"] = datetime.now().strftime("%Y-%m-%d")

        # 原子写入
        templates_dir = _get_templates_dir()
        target_file = templates_dir / f"{platform_id}.yaml"

        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".yaml",
            delete=False, dir=templates_dir
        ) as tmp:
            yaml.dump(new_config, tmp, allow_unicode=True, default_flow_style=False)
            tmp_path = tmp.name
        os.replace(tmp_path, str(target_file))

        # 刷新缓存
        invalidate_cache()

        logger.info(f"模板已更新: {platform_id} -> v{new_config['version']}")
        return {
            "status": "ok",
            "platform_id": platform_id,
            "version": new_config["version"],
            "message": f"模板已更新至 v{new_config['version']}，缓存已刷新",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新模板失败: {e}")


@router.post("/{platform_id}/validate")
async def validate_platform_template(platform_id: str):
    """校验指定平台的模板配置"""
    try:
        from app.core.template_engine import validate_platform

        result = validate_platform(platform_id)
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"校验失败: {e}")


@router.get("/{platform_id}/history")
async def get_template_history(platform_id: str):
    """获取模板版本历史"""
    try:
        from app.core.template_engine import get_template_history

        history = get_template_history(platform_id)
        return {"status": "ok", "platform_id": platform_id, "total": len(history), "history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取版本历史失败: {e}")


@router.get("/{platform_id}/diff/{v1}/{v2}")
async def diff_template_versions(platform_id: str, v1: str, v2: str):
    """对比两个模板版本的差异"""
    try:
        from app.core.template_engine import get_template_version, diff_templates

        old = get_template_version(platform_id, v1)
        new = get_template_version(platform_id, v2)

        if old is None:
            raise HTTPException(status_code=404, detail=f"版本不存在: {v1}")
        if new is None:
            raise HTTPException(status_code=404, detail=f"版本不存在: {v2}")

        diff = diff_templates(old, new)
        return {"status": "ok", "platform_id": platform_id, "v1": v1, "v2": v2, "diff": diff}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对比失败: {e}")


@router.post("/{platform_id}/rollback/{version_id}")
async def rollback_template(platform_id: str, version_id: str):
    """回滚到指定历史版本"""
    try:
        from app.core.template_engine import rollback_template

        success = rollback_template(platform_id, version_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"回滚失败: 版本 {version_id} 不存在")

        return {
            "status": "ok",
            "platform_id": platform_id,
            "rolled_back_to": version_id,
            "message": f"已回滚到版本 {version_id}",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回滚失败: {e}")


@router.post("/{platform_id}/preview")
async def preview_template_structure(platform_id: str, req: TemplatePreviewRequest):
    """预览基于模板的内容结构"""
    try:
        from app.core.template_engine import load_platform_template
        from app.prompts.rewrite import get_sandtable_profile

        template = load_platform_template(platform_id)
        if template.get("_source") == "empty_fallback":
            raise HTTPException(status_code=404, detail=f"平台模板不存在: {platform_id}")

        profile = get_sandtable_profile(req.sandtable_type)

        # 构建结构预览
        header = template.get("header", {})
        body = template.get("body", {})
        schema_cfg = template.get("schema", {})
        footer = template.get("footer", {})
        verification = template.get("verification", {})

        preview = {
            "title_format": header.get("title_format", "").format(
                business=profile.get("industry", ""),
                location=req.enterprise_location or "{location}",
                company=req.enterprise_name or "{company}",
                region=req.enterprise_location or "{region}",
            ),
            "first_paragraph_template": header.get("first_paragraph_rules", [])[:3],
            "word_limits": header.get("word_limits", {}),
            "section_structure": {
                "h2_density": body.get("h2_density", ""),
                "paragraph_length": body.get("paragraph_length", {}),
                "faq_count": body.get("faq_count", {}),
                "list_ratio": f"{body.get('list_ratio', 0) * 100:.0f}%",
            },
            "schema_config": {
                "preferred_types": schema_cfg.get("preferred_types", []),
                "official_site_extra": schema_cfg.get("official_site_extra", ""),
            },
            "footer_template": {
                "tags": footer.get("tags_template", []),
                "cta": footer.get("cta_limits", {}),
            },
            "verification_checks": [c.get("description", "") for c in verification.get("checks", [])],
            "content_source_weights": template.get("weights", {}).get("content_sources", {}),
            "forbidden_words": verification.get("forbidden_words", []),
            "taboo_patterns": verification.get("taboo_patterns", []),
        }

        return {"status": "ok", "platform_id": platform_id, "preview": preview}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预览失败: {e}")


@router.post("/reload")
async def reload_templates():
    """强制刷新所有模板缓存"""
    try:
        from app.core.template_engine import invalidate_cache
        invalidate_cache()
        return {"status": "ok", "message": "模板缓存已刷新，下次请求将重新加载YAML文件"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"刷新缓存失败: {e}")
