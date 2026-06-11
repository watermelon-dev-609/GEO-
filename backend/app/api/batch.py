"""批量处理API路由 — 批量清洗/优化/评测/导出/诊断 + SSE进度推送"""

from __future__ import annotations
import asyncio
import json
import time
import uuid
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.schemas import (
    BatchCleanRequest, BatchCleanResult, BatchOptimizeRequest,
    BatchEvalRequest, BatchExportRequest, BatchProgressResponse,
    BatchDiagnoseRequest, BatchDiagnoseResult, BatchTaskStatus,
    TaskCancelRequest,
)
from app.models.enums import SandtableType, AIPlatform, UserRole

router = APIRouter()
logger = logging.getLogger(__name__)

_tasks: dict[str, dict] = {}
_task_lock = asyncio.Lock()


def _make_task_id() -> str:
    return uuid.uuid4().hex[:12]


async def _update_task(task_id: str, **kwargs):
    async with _task_lock:
        if task_id in _tasks:
            _tasks[task_id].update(kwargs)


@router.get("/progress/{task_id}", response_model=BatchProgressResponse)
async def get_batch_progress(task_id: str):
    async with _task_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    items = [it.copy() for it in task.get("items", [])]
    return BatchProgressResponse(
        task_id=task_id,
        task_type=task["task_type"],
        total=task["total"],
        completed=task["completed"],
        failed=task["failed"],
        items=items,
        overall_status=task["overall_status"],
    )


@router.post("/cancel", response_model=dict)
async def cancel_batch_task(req: TaskCancelRequest):
    async with _task_lock:
        task = _tasks.get(req.task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {req.task_id}")
    task["cancelled"] = True
    task["overall_status"] = "cancelled"
    return {"status": "ok", "task_id": req.task_id, "message": "任务已取消"}


# ── 批量清洗 ──

@router.post("/clean", response_model=list[BatchCleanResult])
async def batch_clean(req: BatchCleanRequest):
    """批量文本清洗（同步，最多50篇）"""
    from app.api.cleaning import _get_cleaner
    try:
        cleaner = _get_cleaner()
    except HTTPException:
        raise
    results = []
    for item in req.texts:
        try:
            result = await cleaner.clean(content=item.content, sandtable_type=None)
            dims = None
            detected = result.get("detected_type")
            if req.sandtable_type:
                try:
                    detected = SandtableType(req.sandtable_type)
                except ValueError:
                    pass
            if req.extract_dimensions:
                try:
                    dims = await cleaner.extract_dimensions(result["cleaned_text"])
                except Exception:
                    pass
            if not detected:
                try:
                    detected = await cleaner.detect_type(item.content)
                except Exception:
                    detected = SandtableType.SMART_TRAFFIC
            results.append(BatchCleanResult(
                id=item.id or _make_task_id(),
                title=item.title or f"文本{len(results) + 1}",
                original_word_count=result["word_count_before"],
                cleaned_word_count=result["word_count_after"],
                detected_type=detected.value if isinstance(detected, SandtableType) else str(detected),
                dimensions=dims,
                status="completed",
            ))
        except Exception as e:
            logger.error(f"批量清洗失败 [{item.title}]: {e}")
            results.append(BatchCleanResult(
                id=item.id or _make_task_id(),
                title=item.title or f"文本{len(results) + 1}",
                original_word_count=len(item.content),
                cleaned_word_count=0,
                status="failed",
                error=str(e),
            ))
    return results


# ── 批量优化（SSE流式进度）─

@router.post("/optimize/stream")
async def batch_optimize_stream(req: BatchOptimizeRequest):
    """批量GEO优化 — SSE流式推送每篇完成进度"""
    task_id = _make_task_id()
    platforms = [AIPlatform(p) for p in req.platforms]
    items_init = [
        {"id": t.id or uuid.uuid4().hex[:12], "title": t.title or f"文案{i + 1}", "status": "pending", "progress": 0}
        for i, t in enumerate(req.texts)
    ]
    async with _task_lock:
        _tasks[task_id] = {
            "task_type": "optimize",
            "total": len(req.texts),
            "completed": 0,
            "failed": 0,
            "items": items_init,
            "overall_status": "running",
            "cancelled": False,
        }

    sandtable_type = SandtableType(req.sandtable_type)
    from app.core.rewriter import GEORewriter
    rewriter = GEORewriter()

    async def event_stream():
        completed = 0
        failed = 0
        all_results = []
        for i, item in enumerate(req.texts):
            task = _tasks.get(task_id, {})
            if task.get("cancelled"):
                yield f"data: {json.dumps({'type': 'cancelled', 'task_id': task_id}, ensure_ascii=False)}\n\n"
                return

            item_id = items_init[i]["id"]
            items_init[i]["status"] = "running"
            await _update_task(task_id, items=items_init)

            yield f"data: {json.dumps({'type': 'item_start', 'item_id': item_id, 'title': items_init[i]['title'], 'index': i, 'total': len(req.texts)}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.01)

            try:
                if not req.texts[i].content or len(req.texts[i].content.strip()) < 10:
                    raise ValueError("文本内容过短（<10字符）")

                # 先清洗
                from app.api.cleaning import _get_cleaner
                cleaner = _get_cleaner()
                clean_result = await cleaner.clean(content=item.content, sandtable_type=sandtable_type)
                cleaned = clean_result["cleaned_text"]
                dims = None
                try:
                    dims = await cleaner.extract_dimensions(cleaned)
                except Exception:
                    pass

                # 批量改写
                rewrite_results = await rewriter.rewrite(
                    cleaned_text=cleaned,
                    sandtable_type=sandtable_type,
                    platforms=platforms,
                    dimensions=dims,
                    optimization_hints=req.optimization_hints or None,
                    enterprise_name=req.enterprise_name or None,
                    enterprise_location=req.enterprise_location or None,
                )

                platform_results = {
                    r.platform.value: {
                        "optimized_text": r.optimized_text,
                        "strategy_notes": r.strategy_notes,
                        "word_count": r.word_count,
                    }
                    for r in rewrite_results
                }
                items_init[i]["status"] = "completed"
                items_init[i]["progress"] = 100
                items_init[i]["result"] = platform_results
                completed += 1

                yield f"data: {json.dumps({'type': 'item_done', 'item_id': item_id, 'title': items_init[i]['title'], 'index': i, 'total': len(req.texts), 'platform_results': platform_results, 'completed': completed, 'failed': failed}, ensure_ascii=False)}\n\n"
                all_results.append({"id": item_id, "title": items_init[i]["title"], "status": "completed", "platform_results": platform_results})

            except Exception as e:
                logger.error(f"批量优化失败 [{item.title}]: {e}")
                items_init[i]["status"] = "failed"
                items_init[i]["progress"] = 0
                items_init[i]["error"] = str(e)
                failed += 1
                yield f"data: {json.dumps({'type': 'item_error', 'item_id': item_id, 'title': items_init[i]['title'], 'index': i, 'error': str(e), 'completed': completed, 'failed': failed}, ensure_ascii=False)}\n\n"
                all_results.append({"id": item_id, "title": items_init[i]["title"], "status": "failed", "error": str(e)})

            await _update_task(task_id, completed=completed, failed=failed, items=items_init)
            await asyncio.sleep(0.5)

        await _update_task(task_id, overall_status="completed", completed=completed, failed=failed, items=items_init)
        yield f"data: {json.dumps({'type': 'batch_done', 'task_id': task_id, 'total': len(req.texts), 'completed': completed, 'failed': failed, 'results': all_results}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ── 批量评测（SSE流式进度）─

@router.post("/evaluate/stream")
async def batch_evaluate_stream(req: BatchEvalRequest):
    """批量AI评测 — SSE流式推送每篇评测进度"""
    task_id = _make_task_id()
    items_init = [
        {"id": t.id or uuid.uuid4().hex[:12], "title": t.title or f"文案{i + 1}", "status": "pending", "progress": 0}
        for i, t in enumerate(req.texts)
    ]
    async with _task_lock:
        _tasks[task_id] = {
            "task_type": "evaluate",
            "total": len(req.texts),
            "completed": 0,
            "failed": 0,
            "items": items_init,
            "overall_status": "running",
            "cancelled": False,
        }

    sandtable_type = SandtableType(req.sandtable_type) if req.sandtable_type else SandtableType.SMART_TRAFFIC
    platforms = [AIPlatform(p) for p in req.platforms] if req.platforms else [AIPlatform.DEEPSEEK]
    from app.core.evaluator import AIEvaluator

    async def event_stream():
        completed = 0
        failed = 0
        all_results = []
        evaluator = AIEvaluator()
        for i, item in enumerate(req.texts):
            task = _tasks.get(task_id, {})
            if task.get("cancelled"):
                yield f"data: {json.dumps({'type': 'cancelled', 'task_id': task_id}, ensure_ascii=False)}\n\n"
                return

            item_id = items_init[i]["id"]
            items_init[i]["status"] = "running"
            await _update_task(task_id, items=items_init)
            yield f"data: {json.dumps({'type': 'item_start', 'item_id': item_id, 'title': items_init[i]['title'], 'index': i, 'total': len(req.texts)}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.01)

            try:
                if not item.content or len(item.content.strip()) < 50:
                    raise ValueError("评测文本过短（<50字符）")

                result = await evaluator.evaluate(
                    optimized_text=item.content,
                    original_text=None,
                    sandtable_type=sandtable_type,
                    platforms=platforms,
                    user_roles=[UserRole(r) for r in req.user_roles] if req.user_roles else [UserRole.B_END_PROCUREMENT],
                    custom_questions=[],
                )

                # result 是 dict，非 Pydantic 对象，需用 dict 访问
                platform_results = result.get("platform_results", [])
                scores_dict = {
                    pr.get("platform", "unknown"): {
                        "overall_score": pr.get("overall_score", 0),
                        "scores": [
                            {"dimension": s.get("dimension", ""), "score": s.get("score", 0), "detail": s.get("detail", "")}
                            for s in pr.get("scores", [])
                        ],
                    }
                    for pr in platform_results
                }

                overall = result.get("overall_score", 0)
                items_init[i]["status"] = "completed"
                items_init[i]["progress"] = 100
                items_init[i]["result"] = {"overall_score": overall, "platform_scores": scores_dict}
                completed += 1

                yield f"data: {json.dumps({'type': 'item_done', 'item_id': item_id, 'title': items_init[i]['title'], 'index': i, 'total': len(req.texts), 'overall_score': overall, 'completed': completed, 'failed': failed}, ensure_ascii=False)}\n\n"
                all_results.append({"id": item_id, "title": items_init[i]["title"], "status": "completed", "overall_score": overall})

            except Exception as e:
                logger.error(f"批量评测失败 [{item.title}]: {e}")
                items_init[i]["status"] = "failed"
                items_init[i]["progress"] = 0
                items_init[i]["error"] = str(e)
                failed += 1
                yield f"data: {json.dumps({'type': 'item_error', 'item_id': item_id, 'title': items_init[i]['title'], 'index': i, 'error': str(e), 'completed': completed, 'failed': failed}, ensure_ascii=False)}\n\n"
                all_results.append({"id": item_id, "title": items_init[i]["title"], "status": "failed", "error": str(e)})

            await _update_task(task_id, completed=completed, failed=failed, items=items_init)
            await asyncio.sleep(0.5)

        await _update_task(task_id, overall_status="completed", completed=completed, failed=failed, items=items_init)
        yield f"data: {json.dumps({'type': 'batch_done', 'task_id': task_id, 'total': len(req.texts), 'completed': completed, 'failed': failed, 'results': all_results}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ── 批量导出 ──

@router.post("/export")
async def batch_export(req: BatchExportRequest):
    """批量导出 — 打包为 ZIP 下载"""
    import tempfile
    import zipfile
    import io
    from fastapi.responses import Response

    if not req.text_ids:
        raise HTTPException(status_code=400, detail="text_ids 不能为空")

    from app.utils.config import get_data_dir
    data_dir = get_data_dir()
    buf = io.BytesIO()
    file_count = 0

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if "optimized_text" in req.export_items:
            out_dir = data_dir / "output"
            if out_dir.exists():
                for f in sorted(out_dir.glob("*.md")):
                    zf.write(f, f"optimized/{f.name}")
                    file_count += 1
                for f in sorted(out_dir.glob("*.json")):
                    zf.write(f, f"optimized/{f.name}")
                    file_count += 1

        if "evaluation_report" in req.export_items:
            eval_dir = data_dir / "evaluations"
            if eval_dir.exists():
                for f in sorted(eval_dir.glob("*.json")):
                    zf.write(f, f"evaluations/{f.name}")
                    file_count += 1

        if "keywords" in req.export_items:
            kw_dir = data_dir / "keywords"
            if kw_dir.exists():
                for f in sorted(kw_dir.glob("*.json")):
                    zf.write(f, f"keywords/{f.name}")
                    file_count += 1

        if file_count == 0:
            zf.writestr("README.txt", "暂无可导出的内容。请先执行优化和评测。")

    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=geo-batch-export-{time.strftime('%Y%m%d-%H%M%S')}.zip"},
    )


# ── 批量诊断 ──

@router.post("/diagnose", response_model=list[BatchDiagnoseResult])
async def batch_diagnose(req: BatchDiagnoseRequest):
    """批量快速诊断"""
    from app.core.diagnoser import ContentDiagnoser
    diagnoser = ContentDiagnoser()
    results = []
    for item in req.texts:
        try:
            diag = await diagnoser.quick_diagnose(text=item.content, sandtable_type=req.sandtable_type)
            results.append(BatchDiagnoseResult(
                id=item.id or _make_task_id(),
                title=item.title or f"文本{len(results) + 1}",
                scores=diag.get("scores", {}),
                overall_score=diag.get("overall_score", 0),
                weak_points=diag.get("weak_points", []),
            ))
        except Exception as e:
            logger.error(f"批量诊断失败 [{item.title}]: {e}")
            results.append(BatchDiagnoseResult(
                id=item.id or _make_task_id(),
                title=item.title or f"文本{len(results) + 1}",
                overall_score=0,
                weak_points=[f"诊断失败: {str(e)}"],
            ))
    return results


# ── 任务状态查询 ──

@router.get("/tasks", response_model=list[BatchProgressResponse])
async def list_batch_tasks():
    """列出所有活跃的批量任务"""
    async with _task_lock:
        tasks = []
        for tid, t in _tasks.items():
            items = [it.copy() for it in t.get("items", [])]
            tasks.append(BatchProgressResponse(
                task_id=tid,
                task_type=t["task_type"],
                total=t["total"],
                completed=t["completed"],
                failed=t["failed"],
                items=items,
                overall_status=t["overall_status"],
            ))
    return tasks
