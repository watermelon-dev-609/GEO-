"""品牌收录监测 API — 追踪品牌在AI平台中的被引用情况"""

from __future__ import annotations
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.schemas import (
    BrandMonitorCheckRequest, BrandMonitorCheckAllRequest,
    BrandMentionCheckResult, BrandMonitorSession, MonitorOverviewResponse,
    MonitorTrendDataPoint, BrandMonitorQueryRequest,
)
from app.core.brand_checker import BrandMentionChecker

logger = logging.getLogger(__name__)

router = APIRouter()
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "brand_mentions"
SESSIONS_DIR = DATA_DIR / "sessions"
CUSTOM_QUERIES_FILE = DATA_DIR / "custom_queries.json"


def _ensure_dir():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_sessions(limit: int = 50) -> list[dict]:
    _ensure_dir()
    sessions = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            sessions.append(json.load(open(f, "r", encoding="utf-8")))
        except Exception:
            continue
        if len(sessions) >= limit:
            break
    return sessions


def _load_custom_queries() -> dict:
    _ensure_dir()
    if CUSTOM_QUERIES_FILE.exists():
        try:
            return json.load(open(CUSTOM_QUERIES_FILE, "r", encoding="utf-8"))
        except Exception:
            pass
    return {"queries": []}


def _save_custom_queries(data: dict):
    _ensure_dir()
    with open(CUSTOM_QUERIES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _build_overview() -> dict:
    sessions = _load_sessions(limit=100)
    if not sessions:
        return {
            "last_check_at": None, "total_sessions": 0, "total_checks": 0,
            "total_mentioned": 0, "overall_mention_rate": 0.0,
            "by_platform": {}, "recent_results": [],
        }

    last_check = sessions[0]["created_at"]
    total_sessions = len(sessions)
    total_checks = sum(s.get("total_queries", 0) for s in sessions)
    total_mentioned = sum(s.get("mentioned_count", 0) for s in sessions)
    overall_rate = round(total_mentioned / total_checks * 100, 1) if total_checks > 0 else 0.0

    by_platform = {}
    for s in sessions:
        for r in s.get("results", []):
            plat = r["platform"]
            if plat not in by_platform:
                by_platform[plat] = {"checked": 0, "mentioned": 0}
            by_platform[plat]["checked"] += 1
            if r.get("brand_mentioned"):
                by_platform[plat]["mentioned"] += 1

    for p in by_platform:
        c = by_platform[p]["checked"]
        by_platform[p]["rate"] = round(by_platform[p]["mentioned"] / c * 100, 1) if c > 0 else 0.0

    recent_results = sessions[0].get("results", [])[:10] if sessions else []

    # ── 情感汇总 ──
    sentiment_summary = {"positive": 0, "neutral": 0, "negative": 0, "total": 0}
    for s in sessions:
        for r in s.get("results", []):
            sent = r.get("sentiment", {})
            if sent:
                sentiment_summary["total"] += 1
                pol = sent.get("polarity", "neutral")
                if pol in sentiment_summary:
                    sentiment_summary[pol] += 1

    return {
        "last_check_at": last_check, "total_sessions": total_sessions,
        "total_checks": total_checks, "total_mentioned": total_mentioned,
        "overall_mention_rate": overall_rate, "by_platform": by_platform,
        "recent_results": recent_results,
        "sentiment_summary": sentiment_summary,
    }


# ── API Endpoints ──

@router.get("/overview", response_model=MonitorOverviewResponse)
async def get_overview():
    return _build_overview()


@router.get("/history")
async def get_history(page: int = 1, page_size: int = 20):
    _ensure_dir()
    all_sessions = _load_sessions(limit=500)
    total = len(all_sessions)
    start = (page - 1) * page_size
    items = all_sessions[start:start + page_size]
    for s in items:
        s.pop("results", None)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/history/{session_id}")
async def get_session_detail(session_id: str):
    _ensure_dir()
    session_path = SESSIONS_DIR / f"{session_id}.json"
    if not session_path.exists():
        raise HTTPException(status_code=404, detail="会话不存在")
    return json.load(open(session_path, "r", encoding="utf-8"))


@router.post("/check")
async def run_check(req: BrandMonitorCheckRequest):
    checker = BrandMentionChecker()
    queries = [{"text": q, "category": "custom"} for q in req.queries] if req.queries else None
    if not queries:
        queries = checker._select_queries(
            req.sandtable_type, req.query_categories, req.max_queries_per_category
        )
    platform = req.platform or "deepseek"
    results = await checker.check_single_platform(platform, queries, req.sandtable_type)
    return {"results": results, "platform": platform}


@router.post("/check-all")
async def run_check_all(req: BrandMonitorCheckAllRequest):
    checker = BrandMentionChecker()
    session = await checker.check_all_platforms(
        platforms=req.platforms,
        query_categories=req.query_categories,
        max_per_category=req.max_queries_per_category,
        sandtable_type=req.sandtable_type,
    )

    # ── 附加情感标签（轻量规则模式，不阻塞检测主流程） ──
    try:
        from app.core.sentiment_classifier import SentimentClassifier
        classifier = SentimentClassifier()
        for r in session.get("results", []):
            response_text = r.get("full_response") or r.get("mention_context", "")
            if response_text and r.get("brand_mentioned"):
                r["sentiment"] = classifier.classify_sync(response_text, r.get("query", ""))
            else:
                r["sentiment"] = {
                    "polarity": "neutral", "confidence": 0,
                    "factual_accuracy": "unverifiable", "factual_issues": [],
                    "summary": "品牌未被提及", "method": "skip",
                }
    except Exception as e:
        logger.warning(f"情感标签附加失败: {e}")

    return session


@router.get("/trend")
async def get_trend(days: int = 30):
    sessions = _load_sessions(limit=500)
    from datetime import datetime as dt
    cutoff = dt.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_ts = cutoff.timestamp() - days * 86400

    by_date = {}
    for s in sessions:
        try:
            date_str = s["created_at"][:10]
        except Exception:
            continue
        try:
            d = dt.fromisoformat(s["created_at"])
            if d.timestamp() < cutoff_ts:
                continue
        except Exception:
            pass
        if date_str not in by_date:
            by_date[date_str] = {"checked": 0, "mentioned": 0, "by_platform": {}}
        by_date[date_str]["checked"] += s.get("total_queries", 0)
        by_date[date_str]["mentioned"] += s.get("mentioned_count", 0)
        for r in s.get("results", []):
            p = r["platform"]
            if p not in by_date[date_str]["by_platform"]:
                by_date[date_str]["by_platform"][p] = {"checked": 0, "mentioned": 0}
            by_date[date_str]["by_platform"][p]["checked"] += 1
            if r.get("brand_mentioned"):
                by_date[date_str]["by_platform"][p]["mentioned"] += 1

    trend = []
    for date_str in sorted(by_date):
        d = by_date[date_str]
        rate = round(d["mentioned"] / d["checked"] * 100, 1) if d["checked"] > 0 else 0.0
        for p in d["by_platform"]:
            pc = d["by_platform"][p]["checked"]
            d["by_platform"][p]["rate"] = round(d["by_platform"][p]["mentioned"] / pc * 100, 1) if pc > 0 else 0.0
        trend.append({
            "date": date_str, "mention_rate": rate,
            "total_checked": d["checked"], "total_mentioned": d["mentioned"],
            "by_platform": d["by_platform"],
        })

    return {"days": days, "data_points": trend}


@router.get("/queries")
async def get_queries():
    """获取预设查询 + 自定义查询"""
    custom = _load_custom_queries()
    return {
        "preset_categories": [
            {"key": "brand_direct", "label": "品牌直问", "desc": "直接询问品牌/厂家"},
            {"key": "scenario", "label": "场景问询", "desc": "特定场景下的供应商选择"},
            {"key": "product", "label": "产品问询", "desc": "产品技术参数和方案"},
        ],
        "custom_queries": custom.get("queries", []),
    }


@router.post("/queries")
async def add_custom_query(req: BrandMonitorQueryRequest):
    custom = _load_custom_queries()
    qid = f"q_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    entry = {"id": qid, "text": req.text, "category": req.category, "created_at": datetime.now(timezone.utc).isoformat()}
    custom["queries"].append(entry)
    _save_custom_queries(custom)
    return {"status": "ok", "query": entry}


@router.delete("/queries/{query_id}")
async def delete_custom_query(query_id: str):
    custom = _load_custom_queries()
    before = len(custom["queries"])
    custom["queries"] = [q for q in custom["queries"] if q.get("id") != query_id]
    if len(custom["queries"]) == before:
        raise HTTPException(status_code=404, detail="查询不存在")
    _save_custom_queries(custom)
    return {"status": "ok"}


# ── 真实AI收录搜索（通过AI平台API实际检索品牌）──

class RealSearchRequest(BaseModel):
    sandtable_type: str = "general"
    platforms: list[str] = ["deepseek"]
    custom_queries: list[str] = []
    brand_name: str = ""

@router.post("/real-search")
async def real_search(req: RealSearchRequest):
    """在真实AI平台上搜索品牌收录状态

    与普通品牌监测不同：此接口实际调用各AI平台API发起搜索查询，
    解析返回结果中是否包含目标品牌，而非LLM模拟评估。
    """
    from app.core.real_search import RealSearchEngine

    sandtable_type = req.sandtable_type
    platforms = req.platforms
    custom_queries = req.custom_queries
    brand_name = req.brand_name

    if not platforms:
        raise HTTPException(status_code=400, detail="至少选择一个AI平台")

    queries = RealSearchEngine.get_preset_queries(sandtable_type, custom_queries)
    if not queries:
        raise HTTPException(status_code=400, detail=f"没有找到沙盘类型 {sandtable_type} 的搜索查询")

    try:
        engine = RealSearchEngine()
        result = await engine.search(
            queries=queries,
            platforms=platforms,
            brand_name=brand_name,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"真实搜索失败: {str(e)}")


@router.get("/real-search/history")
async def real_search_history(days: int = 30):
    """获取真实搜索历史记录"""
    history_dir = DATA_DIR / "real_search"
    if not history_dir.exists():
        return {"searches": [], "total": 0}

    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    searches = []
    for f in sorted(history_dir.glob("rs_*.json"), reverse=True):
        try:
            stat = f.stat()
            if stat.st_mtime < cutoff:
                continue
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            searches.append({
                "search_id": data.get("search_id"),
                "timestamp": data.get("timestamp"),
                "mention_rate": data.get("mention_rate"),
                "citation_rate": data.get("citation_rate"),
                "total_platforms": data.get("total_platforms"),
                "total_queries": data.get("total_queries"),
            })
        except Exception:
            continue
        if len(searches) >= 50:
            break

    return {"searches": searches, "total": len(searches)}