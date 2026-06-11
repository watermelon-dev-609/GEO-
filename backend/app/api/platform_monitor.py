"""平台规则监测 API — CRUD + LLM规则抓取 + 变更检测 + 后台调度"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.models.schemas import PlatformRulesUpdateRequest

logger = logging.getLogger(__name__)
router = APIRouter()

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "platform_rules"

PRESET_PLATFORMS = [
    {"id": "doubao", "name": "豆包", "category": "AI大模型", "status": "normal"},
    {"id": "deepseek", "name": "DeepSeek", "category": "AI大模型", "status": "normal"},
    {"id": "tongyi", "name": "通义千问", "category": "AI大模型", "status": "normal"},
    {"id": "wenxin", "name": "文心一言", "category": "AI大模型", "status": "normal"},
    {"id": "kimi", "name": "Kimi", "category": "AI大模型", "status": "normal"},
    {"id": "yuanbao", "name": "腾讯元宝", "category": "AI大模型", "status": "normal"},
    {"id": "xinghuo", "name": "讯飞星火", "category": "AI大模型", "status": "normal"},
    {"id": "xiaohongshu", "name": "小红书", "category": "社媒平台", "status": "normal"},
    {"id": "douyin", "name": "抖音", "category": "短视频", "status": "normal"},
    {"id": "weixin", "name": "微信公众号", "category": "社媒平台", "status": "normal"},
    {"id": "sogou_ai", "name": "搜狗AI", "category": "AI搜索", "status": "normal"},
    {"id": "baidu_ai", "name": "百度AI", "category": "AI搜索", "status": "normal"},
]

CHECK_INTERVAL_MINUTES = 30  # 默认检测间隔
_scheduler_task: asyncio.Task | None = None
_scheduler_running = False


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_rule_file(platform_id: str) -> Path:
    return DATA_DIR / f"{platform_id}.json"


def _load_rules(platform_id: str) -> dict:
    file = _get_rule_file(platform_id)
    if file.exists():
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    preset = next((p for p in PRESET_PLATFORMS if p["id"] == platform_id), None)
    return {
        "platform_id": platform_id,
        "platform_name": preset["name"] if preset else platform_id,
        "category": preset["category"] if preset else "其他",
        "status": "normal",
        "current_rules": {"summary": "", "details": []},
        "change_log": [],
        "last_updated": "",
        "last_checked": "",
        "check_interval_minutes": CHECK_INTERVAL_MINUTES,
    }


def _save_rules(platform_id: str, data: dict):
    _ensure_dir()
    data["last_checked"] = datetime.now(timezone.utc).isoformat()
    with open(_get_rule_file(platform_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def _bing_search(platform_name: str, platform_category: str) -> str | None:
    """策略1：Bing直接搜索（免费、无需API Key、最稳定）"""
    try:
        import httpx
        from bs4 import BeautifulSoup

        from urllib.parse import quote
        query = f"{platform_name} 内容收录规则 算法 2025 2026"
        # Bing时间过滤: ex1:'ez3' = 过去1个月, 确保拿到最新数据
        url = f"https://www.bing.com/search?q={quote(query)}&setlang=zh-cn&filters=ex1:%22ez3%22"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            resp = await client.get(url, headers=headers)

        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        for item in soup.select("li.b_algo")[:8]:
            title_el = item.select_one("h2 a")
            snippet_el = item.select_one(".b_caption p")
            if title_el:
                results.append(
                    f"标题：{title_el.get_text(strip=True)}\n"
                    f"摘要：{snippet_el.get_text(strip=True) if snippet_el else ''}\n"
                    f"链接：{title_el.get('href', '')}"
                )
        if results:
            return "\n\n---\n".join(results)
        return None
    except Exception as e:
        logger.warning(f"Bing搜索 {platform_name} 失败: {e}")
        return None


async def _ddgs_search(platform_name: str, platform_category: str) -> str | None:
    """策略2：DuckDuckGo搜索（备选）"""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return None
    try:
        query = f"{platform_name} 内容收录规则 算法 {platform_category} 2025 2026"
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=8):
                results.append(f"标题：{r.get('title','')}\n摘要：{r.get('body','')}\n链接：{r.get('href','')}")
        return "\n\n---\n".join(results) if results else None
    except Exception as e:
        logger.warning(f"DDGS搜索 {platform_name} 失败: {e}")
        return None


async def _get_kimi_llm():
    """获取Kimi LLM实例（支持原生Web搜索），不可用时返回None"""
    from app.services.llm.base import LLMFactory
    from app.utils.config import load_settings, load_api_keys
    from app.models.enums import AIPlatform

    settings = load_settings()
    api_keys = load_api_keys()
    plat_cfg = settings.get("llm", {}).get("platforms", {}).get("kimi", {})
    key_info = api_keys.get("platforms", {}).get("kimi", {})

    api_key = key_info.get("api_key", "")
    if not api_key or "your-" in api_key:
        return None

    try:
        return LLMFactory.create(
            platform=AIPlatform("kimi").adapter_type,
            api_key=api_key,
            model_name=plat_cfg.get("model_name", "moonshot-v1-128k"),
            base_url=plat_cfg.get("base_url"),
        )
    except Exception:
        return None


async def _kimi_web_search(platform_name: str, platform_category: str) -> dict | None:
    """策略1：使用Kimi原生Web搜索获取平台规则"""
    from app.prompts.diagnosis import PLATFORM_RULES_SUMMARY_SYSTEM
    from app.services.llm.base import LLMMessage

    llm = await _get_kimi_llm()
    if llm is None:
        return None

    output_format = (
        f"按以下格式输出：\n"
        f"【数据时效】YYYY年MM月\n"
        f"【数据来源】web_search\n"
        f"【摘要】1-2句话概括该平台对企业内容最核心的收录策略\n\n"
        f"【规则要点】\n"
        f"- 内容格式偏好：（FAQ/结构化段落/深度长文/短句列表？）\n"
        f"- 字数敏感度：（偏好多少字？过长过短影响？）\n"
        f"- 关键引用信号：（品牌名/量化数据/权威背书/本地化信息？）\n"
        f"- 引用机制：（RAG检索/训练语料/搜索引擎索引/实时搜索？）\n"
        f"- 避坑指南：（关键词堆砌/虚假数据/AI感/过度营销？）\n"
        f"- 近期算法变化：（最近1年内的规则调整）\n"
        f"- 企业内容建议：（3条最具体的获得高引用的建议）\n\n"
        f"用中文输出。"
    )

    try:
        search_prompt = (
            f"请联网搜索 {platform_name}（{platform_category}）最新的内容收录规则、算法特点和引用机制。"
            f"聚焦GEO优化核心问题：什么样的企业内容会被该平台优先引用？"
            f"请基于搜索结果回答，不要凭记忆编造。\n\n{output_format}"
        )
        messages = [
            LLMMessage(role="system", content=PLATFORM_RULES_SUMMARY_SYSTEM),
            LLMMessage(role="user", content=search_prompt),
        ]
        # Kimi原生Web搜索：通过tools参数启用
        resp = await llm.chat(
            messages, temperature=0.3, max_tokens=1024,
            tools=[{"type": "web_search"}],
        )
        # Kimi搜索结果可能包含在content中，也可能在tool_calls中
        content = resp.content.strip()
        if content:
            return {
                "raw": content,
                "data_source": "kimi_web_search",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        logger.warning(f"Kimi Web搜索 {platform_name} 失败 ({e})，回退到DuckDuckGo")

    return None


async def _llm_check_platform(platform_name: str, platform_category: str) -> dict | None:
    """获取平台最新规则 — Bing搜索 → DDGS搜索 → LLM知识兜底"""
    from app.prompts.diagnosis import PLATFORM_RULES_SUMMARY_SYSTEM
    from app.services.llm.base import LLMFactory, LLMMessage
    from app.utils.config import load_settings, load_api_keys
    from app.models.enums import AIPlatform

    settings = load_settings()
    api_keys = load_api_keys()
    default_platform = settings.get("llm", {}).get("default_model", "deepseek")

    # 结构化输出格式
    output_format = (
        f"按以下格式输出：\n"
        f"【数据时效】YYYY年MM月\n"
        f"【数据来源】web_search 或 llm_knowledge\n"
        f"【摘要】1-2句话概括该平台对企业内容最核心的收录策略\n\n"
        f"【规则要点】\n"
        f"- 内容格式偏好：（FAQ/结构化段落/深度长文/短句列表？）\n"
        f"- 字数敏感度：（偏好多少字？过长过短影响？）\n"
        f"- 关键引用信号：（品牌名/量化数据/权威背书/本地化信息？）\n"
        f"- 引用机制：（RAG检索/训练语料/搜索引擎索引/实时搜索？）\n"
        f"- 避坑指南：（关键词堆砌/虚假数据/AI感/过度营销？）\n"
        f"- 近期算法变化：（最近1年内的规则调整）\n"
        f"- 企业内容建议：（3条最具体的获得高引用的建议）\n\n"
        f"用中文输出。"
    )

    # 获取LLM实例（DeepSeek兜底）
    plat_cfg = settings.get("llm", {}).get("platforms", {}).get(default_platform, {})
    key_info = api_keys.get("platforms", {}).get(default_platform, {})
    api_key = key_info.get("api_key", "")
    llm = None
    if api_key and "your-" not in api_key:
        adapter_type = AIPlatform(default_platform).adapter_type
        llm = LLMFactory.create(
            platform=adapter_type, api_key=api_key,
            model_name=plat_cfg.get("model_name", ""),
            base_url=plat_cfg.get("base_url"),
        )

    # ── 策略1：Bing直接搜索 + LLM总结 ──
    search_results = await _bing_search(platform_name, platform_category)
    if not search_results:
        # ── 策略2：DDGS搜索 ──
        search_results = await _ddgs_search(platform_name, platform_category)
        data_source_note = "ddgs_search"
    else:
        data_source_note = "web_search"

    if search_results and llm:
        try:
            web_prompt = (
                f"以下是关于 {platform_name}（{platform_category}）的最新网络搜索结果。"
                f"请基于这些搜索结果，总结该平台的内容收录规则和算法特点。"
                f"只基于以下搜索结果回答，不要添加搜索结果中没有的信息。"
                f"如果搜索结果信息不足，诚实说明。\n\n"
                f"=== 网络搜索结果 ===\n{search_results}\n\n"
                f"=== 请按要求输出 ===\n{output_format}"
            )
            messages = [
                LLMMessage(role="system", content=PLATFORM_RULES_SUMMARY_SYSTEM),
                LLMMessage(role="user", content=web_prompt),
            ]
            resp = await llm.chat(messages, temperature=0.3, max_tokens=1024)
            return {
                "raw": resp.content.strip(),
                "data_source": data_source_note,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.warning(f"LLM总结搜索结果失败 ({e})，回退到LLM知识")

    # ── 策略3：回退到LLM训练数据（明确标注）──
    if llm is not None:
        try:
            fallback_prompt = (
                f"请基于你对 {platform_name}（{platform_category}）的了解，按以下格式输出。"
                f"诚实标注知识截止日期，不得编造。\n\n"
                f"【数据时效】YYYY年MM月（你训练数据的截止时间）\n"
                f"【数据来源】llm_knowledge\n"
                f"{output_format}"
            )
            messages = [
                LLMMessage(role="system", content=PLATFORM_RULES_SUMMARY_SYSTEM),
                LLMMessage(role="user", content=fallback_prompt),
            ]
            resp = await llm.chat(messages, temperature=0.3, max_tokens=1024)
            return {
                "raw": resp.content.strip(),
                "data_source": "llm_knowledge",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.warning(f"LLM检查 {platform_name} 失败: {e}")
    return None


def _parse_llm_response(raw: str) -> dict:
    """解析 LLM 结构化返回，提取摘要、要点、时效和来源"""
    import re
    result = {"summary": "", "details": [], "knowledge_cutoff": "", "data_source": "unknown"}

    # 提取数据时效
    cutoff_match = re.search(r'【数据时效】\s*(.+?)(?=\n【|$)', raw, re.DOTALL)
    if cutoff_match:
        result["knowledge_cutoff"] = cutoff_match.group(1).strip()

    # 提取数据来源
    source_match = re.search(r'【数据来源】\s*(.+?)(?=\n【|$)', raw, re.DOTALL)
    if source_match:
        result["data_source"] = source_match.group(1).strip()

    # 提取摘要
    summary_match = re.search(r'【摘要】\s*\n?(.+?)(?=【规则要点】|$)', raw, re.DOTALL)
    if summary_match:
        result["summary"] = summary_match.group(1).strip()

    # 提取规则要点
    details_match = re.search(r'【规则要点】\s*\n?(.+)', raw, re.DOTALL)
    if details_match:
        details_text = details_match.group(1).strip()
        details = [re.sub(r'^[-*•]\s*', '', line).strip() for line in details_text.split('\n') if line.strip()]
        result["details"] = [d for d in details if d]

    if not result["summary"]:
        result["summary"] = raw.strip()
    if not result["details"]:
        result["details"] = [line.strip() for line in raw.split('\n') if line.strip() and not line.startswith('【')]

    return result


def _detect_changes(old_summary: str, new_summary: str) -> tuple[bool, float]:
    """检测新旧规则摘要的差异程度。返回 (has_changes, similarity_ratio)"""
    if not old_summary or not new_summary:
        return True, 0.0
    old_clean = old_summary.strip().lower()
    new_clean = new_summary.strip().lower()
    if old_clean == new_clean:
        return False, 1.0
    old_hash = hashlib.md5(old_clean.encode()).hexdigest()
    new_hash = hashlib.md5(new_clean.encode()).hexdigest()
    if old_hash == new_hash:
        return False, 1.0
    old_lines = set(line.strip() for line in old_clean.split('\n') if line.strip())
    new_lines = set(line.strip() for line in new_clean.split('\n') if line.strip())
    if not old_lines or not new_lines:
        return True, 0.0
    common = old_lines & new_lines
    ratio = len(common) / max(len(old_lines), len(new_lines))
    return ratio < 0.6, ratio


# ── API 端点 ──

@router.get("/platforms")
async def list_platforms():
    """获取所有监测平台列表"""
    _ensure_dir()
    result = []
    for preset in PRESET_PLATFORMS:
        rules = _load_rules(preset["id"])
        current = rules.get("current_rules", {})
        result.append({
            "id": rules["platform_id"],
            "name": rules["platform_name"],
            "category": rules["category"],
            "status": rules.get("status", "normal"),
            "last_updated": rules.get("last_updated", ""),
            "last_checked": rules.get("last_checked", ""),
            "summary": current.get("summary", ""),
            "knowledge_cutoff": current.get("knowledge_cutoff", ""),
            "data_source": current.get("data_source", ""),
            "alert": rules.get("status") == "changed",
            "change_count": len(rules.get("change_log", [])),
        })
    return {"platforms": result}


@router.get("/platforms/{platform_id}")
async def get_platform_detail(platform_id: str):
    """获取单个平台的详细规则"""
    valid_ids = {p["id"] for p in PRESET_PLATFORMS}
    if platform_id not in valid_ids:
        raise HTTPException(status_code=404, detail=f"平台不存在: {platform_id}")
    rules = _load_rules(platform_id)
    return rules


@router.post("/platforms/{platform_id}")
async def update_platform_rules(platform_id: str, req: PlatformRulesUpdateRequest):
    """手动更新平台规则"""
    valid_ids = {p["id"] for p in PRESET_PLATFORMS}
    if platform_id not in valid_ids:
        raise HTTPException(status_code=404, detail=f"平台不存在: {platform_id}")
    rules = _load_rules(platform_id)
    status = req.status or rules.get("status", "normal")
    old_summary = rules.get("current_rules", {}).get("summary", "")
    if req.summary and req.summary != old_summary:
        rules.setdefault("change_log", []).insert(0, {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "previous": old_summary[:100],
            "new": req.summary[:100],
            "impact": req.impact,
            "response": req.response,
        })
    rules["current_rules"] = {"summary": req.summary, "details": req.details}
    rules["status"] = status
    rules["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_rules(platform_id, rules)
    return {"status": "ok", "platform_id": platform_id}


@router.post("/platforms/{platform_id}/llm-summary")
async def generate_llm_summary(platform_id: str):
    """使用LLM搜索+知识生成平台规则摘要并自动保存"""
    rules = _load_rules(platform_id)
    check_result = await _llm_check_platform(rules["platform_name"], rules["category"])
    if check_result is None:
        raise HTTPException(status_code=503, detail="LLM不可用，请先配置API Key")

    raw = check_result["raw"]
    data_source = check_result["data_source"]
    old_summary = rules.get("current_rules", {}).get("summary", "")
    has_changes, similarity = _detect_changes(old_summary, raw)
    if has_changes and old_summary:
        rules.setdefault("change_log", []).insert(0, {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "previous": old_summary[:120],
            "new": raw[:120],
            "impact": "",
            "response": "",
        })
        rules["status"] = "changed"
    else:
        rules["status"] = "normal"
    parsed = _parse_llm_response(raw)
    rules["current_rules"] = {
        "summary": parsed["summary"],
        "details": parsed["details"],
        "knowledge_cutoff": parsed["knowledge_cutoff"],
        "data_source": parsed["data_source"] or data_source,
    }
    rules["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_rules(platform_id, rules)

    return {
        "platform_id": platform_id,
        "platform_name": rules["platform_name"],
        "generated_summary": raw,
        "has_changes": has_changes,
        "data_source": data_source,
        "knowledge_cutoff": parsed["knowledge_cutoff"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/check-all")
async def check_all_platforms(background_tasks: BackgroundTasks):
    """触发全量平台规则检查（异步后台执行）"""
    background_tasks.add_task(_run_full_check)
    return {"status": "started", "message": f"正在对 {len(PRESET_PLATFORMS)} 个平台进行规则检查，请稍后查看结果"}


@router.post("/check/{platform_id}")
async def check_single_platform(platform_id: str):
    """对单个平台执行规则检查（Web搜索优先）"""
    rules = _load_rules(platform_id)
    check_result = await _llm_check_platform(rules["platform_name"], rules["category"])
    if check_result is None:
        raise HTTPException(status_code=503, detail="LLM不可用，请先配置API Key")

    raw = check_result["raw"]
    data_source = check_result["data_source"]
    old_summary = rules.get("current_rules", {}).get("summary", "")
    has_changes, similarity = _detect_changes(old_summary, raw)
    if has_changes and old_summary:
        rules.setdefault("change_log", []).insert(0, {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "previous": old_summary[:120],
            "new": raw[:120],
            "impact": "",
            "response": "",
        })
        rules["status"] = "changed"
    else:
        rules["status"] = "normal"
    parsed = _parse_llm_response(raw)
    rules["current_rules"] = {
        "summary": parsed["summary"],
        "details": parsed["details"],
        "knowledge_cutoff": parsed["knowledge_cutoff"],
        "data_source": parsed["data_source"] or data_source,
    }
    rules["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_rules(platform_id, rules)
    return {
        "platform_id": platform_id,
        "has_changes": has_changes,
        "similarity": round(similarity * 100, 1),
        "new_summary": raw,
        "data_source": data_source,
        "knowledge_cutoff": parsed["knowledge_cutoff"],
        "checked_at": rules["last_checked"],
    }


@router.get("/pending-updates")
async def list_pending_updates():
    """列出所有检测到规则变更、待管理员审核的平台"""
    _ensure_dir()
    pending = []
    for preset in PRESET_PLATFORMS:
        rules = _load_rules(preset["id"])
        if rules.get("status") == "changed":
            current = rules.get("current_rules", {})
            change_log = rules.get("change_log", [])
            pending.append({
                "platform_id": rules["platform_id"],
                "platform_name": rules["platform_name"],
                "category": rules["category"],
                "last_checked": rules.get("last_checked", ""),
                "data_source": current.get("data_source", ""),
                "knowledge_cutoff": current.get("knowledge_cutoff", ""),
                "current_summary": current.get("summary", ""),
                "current_details": current.get("details", []),
                "change_count": len(change_log),
                "latest_change": change_log[0] if change_log else None,
            })
    return {"total": len(pending), "platforms": pending}


@router.post("/sync-to-rules/{platform_id}")
async def sync_to_rewrite_rules(platform_id: str):
    """将平台监测数据转换为PLATFORM_RULES建议格式（供管理员审核后更新rewrite.py）"""
    rules = _load_rules(platform_id)
    current = rules.get("current_rules", {})
    details = current.get("details", [])
    # 提取策略关键词
    fmt = next((d for d in details if any(k in d for k in ["格式","FAQ","结构"])), "")
    sig = next((d for d in details if any(k in d for k in ["信号","品牌","引用"])), "")
    strategy = " + ".join(filter(None, [
        fmt.split("：")[-1].strip()[:40] if fmt else "",
        sig.split("：")[-1].strip()[:40] if sig else "",
    ])) or "待人工总结"
    return {
        "platform_id": platform_id,
        "platform_name": rules["platform_name"],
        "source": current.get("data_source", "unknown"),
        "knowledge_cutoff": current.get("knowledge_cutoff", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suggested_rules_entry": {
            "name": rules["platform_name"],
            "strategy": strategy,
            "citation_mechanism": current.get("summary", ""),
            "rules": details,
            "updated_at": datetime.now().strftime("%Y-%m-%d"),
        },
        "warning": "请人工审核后再替换 rewrite.py 中对应的 PLATFORM_RULES 条目。"
                   "建议对照《GEO使用手册》平台采信偏好表确认。",
    }


# ── RSS监控端点 ──

@router.post("/rss/check-all")
async def run_rss_check_all():
    """手动触发全量RSS信源检查"""
    try:
        from app.core.rss_monitor import run_daily_crawl
        result = await run_daily_crawl()
        return {
            "status": "ok",
            "run_id": result.get("run_id", ""),
            "total_sources": result.get("total_sources", 0),
            "total_alerts": result.get("total_alerts", 0),
            "sources_checked": result.get("sources_checked", 0),
            "message": f"已完成 {result.get('sources_checked', 0)}/{result.get('total_sources', 0)} 个信源检查，发现 {result.get('total_alerts', 0)} 条告警",
        }
    except Exception as e:
        logger.error(f"RSS全量检查失败: {e}")
        raise HTTPException(status_code=500, detail=f"RSS检查失败: {e}")


@router.get("/rss/results/{date}")
async def get_rss_results(date: str):
    """获取指定日期的RSS检查结果（YYYY-MM-DD）"""
    try:
        from app.core.rss_monitor import get_rss_results as _get_rss
        result = _get_rss(date)
        if result is None:
            return {"status": "not_found", "date": date, "message": f"日期 {date} 无RSS数据"}
        return {"status": "ok", "date": date, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取RSS结果失败: {e}")


@router.get("/rss/recent")
async def get_recent_rss(days: int = 7):
    """获取最近N天的RSS监控摘要"""
    try:
        from app.core.rss_monitor import list_rss_results
        results = list_rss_results(days)
        return {"status": "ok", "days": days, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取RSS摘要失败: {e}")


@router.get("/rss/alerts")
async def get_keyword_alerts(hours: int = 24):
    """获取最近N小时的关键词告警"""
    try:
        from app.core.rss_monitor import get_keyword_alerts
        alerts = get_keyword_alerts(hours)
        return {"status": "ok", "hours": hours, "total": len(alerts), "alerts": alerts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取告警失败: {e}")


# ── AI采信测试端点 ──

@router.post("/citation-test")
async def run_citation_test(platforms: str = "", query_count: int = 25):
    """手动触发AI采信行为测试

    Args:
        platforms: 逗号分隔的平台列表，默认全部 (doubao,wenxin,tongyi,deepseek,kimi)
        query_count: 测试问题数量（最大50）
    """
    try:
        from app.core.citation_tester import run_citation_test as _run_test
        plat_list = [p.strip() for p in platforms.split(",") if p.strip()] if platforms else None
        query_count = min(query_count, 50)
        result = await _run_test(platforms=plat_list, query_count=query_count)
        return {
            "status": "ok",
            "test_id": result.get("test_id", ""),
            "platforms_tested": result.get("platforms_tested", 0),
            "queries_fired": result.get("queries_fired", 0),
            "queries_attempted": result.get("queries_attempted", 0),
        }
    except Exception as e:
        logger.error(f"AI采信测试失败: {e}")
        raise HTTPException(status_code=500, detail=f"采信测试失败: {e}")


@router.get("/citation-tests")
async def list_citation_tests(days: int = 30):
    """列出历史采信测试记录"""
    try:
        from app.core.citation_tester import list_citation_tests as _list
        tests = _list(days)
        return {"status": "ok", "days": days, "total": len(tests), "tests": tests}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取测试列表失败: {e}")


@router.get("/citation-tests/{test_id}")
async def get_citation_test(test_id: str):
    """获取指定采信测试的详细结果"""
    try:
        from app.core.citation_tester import get_citation_test as _get
        result = _get(test_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"测试不存在: {test_id}")
        return {"status": "ok", "test_id": test_id, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取测试详情失败: {e}")


# ── AI结构变化报告端点 ──

@router.post("/structure-report")
async def generate_structure_report(week_start: str = ""):
    """生成《AI抓取结构变化周报》

    Args:
        week_start: 报告起始日期 YYYY-MM-DD，默认本周一
    """
    try:
        from app.core.ai_structure_reporter import generate_weekly_structure_report
        ws = week_start if week_start else None
        report = generate_weekly_structure_report(week_start=ws)
        return {
            "status": "ok",
            "week_start": ws or "auto",
            "report_length": len(report),
            "report_preview": report[:500] + "..." if len(report) > 500 else report,
        }
    except Exception as e:
        logger.error(f"生成结构报告失败: {e}")
        raise HTTPException(status_code=500, detail=f"报告生成失败: {e}")


@router.get("/structure-reports")
async def list_structure_reports(days: int = 90):
    """列出历史结构报告"""
    try:
        from app.core.ai_structure_reporter import list_structure_reports as _list
        reports = _list(days)
        return {"status": "ok", "days": days, "total": len(reports), "reports": reports}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取报告列表失败: {e}")


@router.get("/structure-reports/{report_id}")
async def get_structure_report(report_id: str):
    """获取指定结构报告的完整内容"""
    try:
        from app.core.ai_structure_reporter import get_structure_report as _get
        report = _get(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail=f"报告不存在: {report_id}")
        return {"status": "ok", "report_id": report_id, "content": report}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取报告详情失败: {e}")


@router.get("/scheduler/status")
async def scheduler_status():
    """查看后台调度器状态"""
    return {
        "running": _scheduler_running,
        "interval_minutes": CHECK_INTERVAL_MINUTES,
        "platforms_count": len(PRESET_PLATFORMS),
    }


@router.post("/scheduler/start")
async def start_scheduler(interval_minutes: int = 30):
    """启动后台规则监测调度器"""
    global _scheduler_running, _scheduler_task
    if _scheduler_running:
        return {"status": "already_running", "interval_minutes": CHECK_INTERVAL_MINUTES}
    _scheduler_running = True
    _scheduler_task = asyncio.create_task(_scheduler_loop(interval_minutes))
    logger.info(f"平台监测调度器已启动，间隔 {interval_minutes} 分钟")
    return {"status": "started", "interval_minutes": interval_minutes}


@router.post("/scheduler/stop")
async def stop_scheduler():
    """停止后台调度器"""
    global _scheduler_running, _scheduler_task
    _scheduler_running = False
    if _scheduler_task:
        _scheduler_task.cancel()
        _scheduler_task = None
    logger.info("平台监测调度器已停止")
    return {"status": "stopped"}


# ── 内部逻辑 ──

async def _run_full_check():
    """全量平台规则检查"""
    logger.info(f"开始全量平台规则检查 ({len(PRESET_PLATFORMS)} 个平台)...")
    changed_count = 0
    for preset in PRESET_PLATFORMS:
        try:
            rules = _load_rules(preset["id"])
            await asyncio.sleep(2)  # 平台间间隔，避免 LLM 限流
            check_result = await _llm_check_platform(rules["platform_name"], rules["category"])
            if check_result is None:
                continue
            raw = check_result["raw"]
            data_source = check_result["data_source"]
            old_summary = rules.get("current_rules", {}).get("summary", "")
            has_changes, _ = _detect_changes(old_summary, raw)
            if has_changes and old_summary:
                rules.setdefault("change_log", []).insert(0, {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "previous": old_summary[:120],
                    "new": raw[:120],
                    "impact": "",
                    "response": "",
                })
                rules["status"] = "changed"
                changed_count += 1
            else:
                rules["status"] = "normal"
            parsed = _parse_llm_response(raw)
            rules["current_rules"] = {
                "summary": parsed["summary"],
                "details": parsed["details"],
                "knowledge_cutoff": parsed["knowledge_cutoff"],
                "data_source": parsed["data_source"] or data_source,
            }
            rules["last_updated"] = datetime.now(timezone.utc).isoformat()
            _save_rules(preset["id"], rules)
        except Exception as e:
            logger.error(f"检查 {preset['name']} 规则失败: {e}")
    logger.info(f"全量检查完成: {changed_count}/{len(PRESET_PLATFORMS)} 个平台有变化")


async def _scheduler_loop(interval_minutes: int = 30):
    """后台调度循环"""
    seconds = max(interval_minutes * 60, 300)  # 最低 5 分钟
    while _scheduler_running:
        try:
            await asyncio.sleep(seconds)
            if _scheduler_running:
                await _run_full_check()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"调度器异常: {e}")


# ── 应用启动时自动初始化 ──

async def init_platform_rules():
    """首次启动时：为所有平台初始化默认规则数据"""
    _ensure_dir()
    initialized = 0
    for preset in PRESET_PLATFORMS:
        file = _get_rule_file(preset["id"])
        if not file.exists():
            rules = {
                "platform_id": preset["id"],
                "platform_name": preset["name"],
                "category": preset["category"],
                "status": "normal",
                "current_rules": {"summary": "", "details": []},
                "change_log": [],
                "last_updated": "",
                "last_checked": datetime.now(timezone.utc).isoformat(),
                "check_interval_minutes": CHECK_INTERVAL_MINUTES,
            }
            _save_rules(preset["id"], rules)
            initialized += 1
    if initialized > 0:
        logger.info(f"已初始化 {initialized} 个平台的规则数据文件")
    return initialized
