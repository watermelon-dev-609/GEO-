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


async def _llm_check_platform(platform_name: str, platform_category: str) -> str | None:
    """使用 LLM 获取平台最新规则摘要"""
    from app.prompts.diagnosis import PLATFORM_RULES_SUMMARY_SYSTEM
    from app.services.llm.base import LLMFactory, LLMMessage
    from app.utils.config import load_settings, load_api_keys
    from app.models.enums import AIPlatform

    settings = load_settings()
    api_keys = load_api_keys()
    default_platform = settings.get("llm", {}).get("default_model", "deepseek")
    plat_cfg = settings.get("llm", {}).get("platforms", {}).get(default_platform, {})
    key_info = api_keys.get("platforms", {}).get(default_platform, {})

    api_key = key_info.get("api_key", "")
    if not api_key or "your-" in api_key:
        return None

    adapter_type = AIPlatform(default_platform).adapter_type
    llm = LLMFactory.create(
        platform=adapter_type, api_key=api_key,
        model_name=plat_cfg.get("model_name", ""),
        base_url=plat_cfg.get("base_url"),
    )

    prompt = (
        f"请基于你对 {platform_name}（{platform_category}）的了解，按以下格式输出：\n\n"
        f"【摘要】\n用1-2句话概括该平台当前最核心的内容收录策略。\n\n"
        f"【规则要点】\n"
        f"- 列出该平台的具体内容收录规则（每条一行，以 - 开头）\n"
        f"- 列出该平台的内容推荐偏好（格式/长度/风格）\n"
        f"- 列出近期已知的规则变化或算法更新\n"
        f"- 列出在该平台获得高引用的内容特征\n\n"
        f"请严格按此格式输出，用中文。"
    )
    messages = [
        LLMMessage(role="system", content=PLATFORM_RULES_SUMMARY_SYSTEM),
        LLMMessage(role="user", content=prompt),
    ]
    try:
        resp = await llm.chat(messages, temperature=0.3, max_tokens=1024)
        return resp.content.strip()
    except Exception as e:
        logger.warning(f"LLM检查 {platform_name} 失败: {e}")
        return None


def _parse_llm_response(raw: str) -> tuple[str, list[str]]:
    """解析 LLM 结构化返回，提取摘要和要点列表"""
    import re
    summary = ""
    details = []
    summary_match = re.search(r'【摘要】\s*\n?(.+?)(?=【规则要点】|$)', raw, re.DOTALL)
    if summary_match:
        summary = summary_match.group(1).strip()
    details_match = re.search(r'【规则要点】\s*\n?(.+)', raw, re.DOTALL)
    if details_match:
        details_text = details_match.group(1).strip()
        details = [re.sub(r'^[-*•]\s*', '', line).strip() for line in details_text.split('\n') if line.strip()]
        details = [d for d in details if d]
    if not summary:
        summary = raw.strip()
    if not details:
        details = [line.strip() for line in raw.split('\n') if line.strip() and not line.startswith('【')]
    return summary, details


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
        result.append({
            "id": rules["platform_id"],
            "name": rules["platform_name"],
            "category": rules["category"],
            "status": rules.get("status", "normal"),
            "last_updated": rules.get("last_updated", ""),
            "last_checked": rules.get("last_checked", ""),
            "summary": rules.get("current_rules", {}).get("summary", ""),
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
    """使用LLM生成平台规则摘要并自动保存"""
    rules = _load_rules(platform_id)
    summary = await _llm_check_platform(rules["platform_name"], rules["category"])
    if summary is None:
        raise HTTPException(status_code=503, detail="LLM不可用，请先配置API Key")

    old_summary = rules.get("current_rules", {}).get("summary", "")
    has_changes, similarity = _detect_changes(old_summary, summary)
    if has_changes and old_summary:
        rules.setdefault("change_log", []).insert(0, {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "previous": old_summary[:120],
            "new": summary[:120],
            "impact": "",
            "response": "",
        })
        rules["status"] = "changed"
    else:
        rules["status"] = "normal"
    parsed_summary, parsed_details = _parse_llm_response(summary)
    rules["current_rules"] = {"summary": parsed_summary, "details": parsed_details}
    rules["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_rules(platform_id, rules)

    return {
        "platform_id": platform_id,
        "platform_name": rules["platform_name"],
        "generated_summary": summary,
        "has_changes": has_changes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/check-all")
async def check_all_platforms(background_tasks: BackgroundTasks):
    """触发全量平台规则检查（异步后台执行）"""
    background_tasks.add_task(_run_full_check)
    return {"status": "started", "message": f"正在对 {len(PRESET_PLATFORMS)} 个平台进行规则检查，请稍后查看结果"}


@router.post("/check/{platform_id}")
async def check_single_platform(platform_id: str):
    """对单个平台执行规则检查"""
    rules = _load_rules(platform_id)
    summary = await _llm_check_platform(rules["platform_name"], rules["category"])
    if summary is None:
        raise HTTPException(status_code=503, detail="LLM不可用，请先配置API Key")

    old_summary = rules.get("current_rules", {}).get("summary", "")
    has_changes, similarity = _detect_changes(old_summary, summary)
    if has_changes and old_summary:
        rules.setdefault("change_log", []).insert(0, {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "previous": old_summary[:120],
            "new": summary[:120],
            "impact": "",
            "response": "",
        })
        rules["status"] = "changed"
    else:
        rules["status"] = "normal"
    parsed_summary, parsed_details = _parse_llm_response(summary)
    rules["current_rules"] = {"summary": parsed_summary, "details": parsed_details}
    rules["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_rules(platform_id, rules)
    return {
        "platform_id": platform_id,
        "has_changes": has_changes,
        "similarity": round(similarity * 100, 1),
        "new_summary": summary,
        "checked_at": rules["last_checked"],
    }


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
            summary = await _llm_check_platform(rules["platform_name"], rules["category"])
            if summary is None:
                continue
            old_summary = rules.get("current_rules", {}).get("summary", "")
            has_changes, _ = _detect_changes(old_summary, summary)
            if has_changes and old_summary:
                rules.setdefault("change_log", []).insert(0, {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "previous": old_summary[:120],
                    "new": summary[:120],
                    "impact": "",
                    "response": "",
                })
                rules["status"] = "changed"
                changed_count += 1
            else:
                rules["status"] = "normal"
            parsed_summary, parsed_details = _parse_llm_response(summary)
            rules["current_rules"] = {"summary": parsed_summary, "details": parsed_details}
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
