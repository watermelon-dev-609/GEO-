"""GEO生成式搜索优化系统 - FastAPI入口"""

import os
import logging
import tempfile
import threading
from pathlib import Path

# 修复 PyTorch scikit-learn OpenMP DLL 冲突导致 segfault 的问题
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# ⚠️ 必须在任何 huggingface/sentence-transformers 导入之前设置镜像
# 否则模型下载会直连 huggingface.co（国内可能被阻断）
_HF_MIRROR = os.environ.get("HF_MIRROR", "https://hf-mirror.com")
os.environ.setdefault("HF_ENDPOINT", _HF_MIRROR)
os.environ.setdefault("HF_HUB_ENDPOINT", _HF_MIRROR)

# backend根目录
APP_DIR = Path(__file__).resolve().parent  # backend/app
BACKEND_DIR = APP_DIR.parent  # backend

_config_lock = threading.Lock()


def _setup_logging():
    """初始化日志配置"""
    from app.utils.config import load_settings
    settings = load_settings()
    log_cfg = settings.get("logging", {})
    level_name = log_cfg.get("level", "INFO").upper()
    fmt = log_cfg.get("format",
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s")
    datefmt = log_cfg.get("datefmt", "%Y-%m-%d %H:%M:%S")

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level_name, logging.INFO))

    # 避免重复 handler
    if root_logger.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root_logger.addHandler(handler)

    # 文件日志（可选）
    log_file = log_cfg.get("file", "")
    if log_file:
        log_path = Path(log_file)
        if not log_path.is_absolute():
            log_path = BACKEND_DIR / log_file
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(log_path), encoding="utf-8")
        fh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        root_logger.addHandler(fh)

    # 抑制第三方库的 DEBUG 日志噪音
    for noisy in ("httpx", "httpcore", "urllib3", "matplotlib", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_setup_logging()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.api import cleaning, geo_rewrite, jsonld, evaluation, reports
from app.api import analytics, diagnosis, platform_monitor, keywords, competitors, templates, brand_monitor
from app.api import batch, auth, usage, logs, audit, compliance_api, scheduler_api, versions, seo
from app.models.schemas import SystemConfigResponse, LLMConfigStatus, LLMConfigUpdateRequest
from app.models.enums import AIPlatform
from app.utils.config import load_settings, load_api_keys, get_data_dir

# ── 应用初始化 ──

from app.utils.config import get_enterprise_name as _ent_name
app = FastAPI(
    title="GEO生成式搜索优化系统",
    description=f"{_ent_name()} - 轻量化GEO优化平台",
    version="2.0.0-personal",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 审计日志中间件（纯ASGI，不影响SSE流式响应）
from app.core.audit_logger import AuditLogMiddleware
app.add_middleware(AuditLogMiddleware)

# ── 注册路由 ──

app.include_router(cleaning.router, prefix="/api/cleaning", tags=["文本清洗"])
app.include_router(geo_rewrite.router, prefix="/api/geo", tags=["GEO文案重构"])
app.include_router(jsonld.router, prefix="/api/jsonld", tags=["JSON-LD生成"])
app.include_router(evaluation.router, prefix="/api/evaluate", tags=["AI评测"])
app.include_router(reports.router, prefix="/api/reports", tags=["数据报表"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["数据看板"])
app.include_router(diagnosis.router, prefix="/api/diagnosis", tags=["内容诊断"])
app.include_router(platform_monitor.router, prefix="/api/platform-monitor", tags=["平台监测"])
app.include_router(keywords.router, prefix="/api/keywords", tags=["关键词库"])
app.include_router(competitors.router, prefix="/api/competitors", tags=["竞品调研"])
app.include_router(templates.router, prefix="/api/templates", tags=["内容模板"])
app.include_router(brand_monitor.router, prefix="/api/brand-monitor", tags=["品牌收录监测"])
app.include_router(analytics.router, prefix="/api/samples", tags=["示例数据"])

# ── Phase 1 新增路由 ──
app.include_router(batch.router, prefix="/api/batch", tags=["批量处理"])
app.include_router(auth.router, prefix="/api/auth", tags=["鉴权"])
app.include_router(usage.router, prefix="/api/usage", tags=["用量监控"])
app.include_router(logs.router, prefix="/api/logs", tags=["系统日志"])
app.include_router(audit.router, prefix="/api/audit", tags=["审计日志"])
app.include_router(compliance_api.router, prefix="/api/compliance", tags=["合规检测"])
app.include_router(scheduler_api.router, prefix="/api/scheduler", tags=["定时任务"])
app.include_router(versions.router, prefix="/api/versions", tags=["版本管理"])
app.include_router(seo.router, prefix="/api/seo", tags=["SEO集成"])

# ── Phase 2: 模板引擎 ──
from app.api import template_engine
app.include_router(template_engine.router, prefix="/api/templates/engine", tags=["模板引擎"])

# ── Phase 3+4: 适配流水线 + 数据闭环 ──
from app.api import adaptation, feedback
app.include_router(adaptation.router, prefix="/api/adaptation", tags=["适配流水线"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["数据闭环"])

# ── Phase 5: 流量与转化追踪 ──
from app.api import traffic, utm, conversions as conv_api
app.include_router(traffic.router, prefix="/api/traffic", tags=["流量分析"])
app.include_router(utm.router, prefix="/api/utm", tags=["UTM追踪"])
app.include_router(conv_api.router, prefix="/api/conversions", tags=["转化归因"])

# ── Phase 6: 品牌舆情管理 ──
from app.api import reputation
app.include_router(reputation.router, prefix="/api/reputation", tags=["品牌舆情管理"])

# 确保数据目录存在
get_data_dir()
(BACKEND_DIR / "data" / "output").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "evaluations").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "platform_rules").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "competitors").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "keywords").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "templates").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "brand_mentions" / "sessions").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "usage").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "audit").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "versions").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "rss_monitor").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "citation_tests").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "structure_reports").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "platform_templates").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "template_versions").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "adaptation_runs").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "feedback_metrics").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "traffic").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "conversions").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "utm_campaigns").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "reputation" / "incidents").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "reputation" / "corrections").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "reputation" / "scans").mkdir(parents=True, exist_ok=True)


# ── 启动事件 ──

@app.on_event("startup")
async def startup_embedding_check():
    """预加载Embedding模型，提前发现网络/下载问题"""
    import logging
    startup_logger = logging.getLogger(__name__)
    try:
        startup_logger.info("正在预加载向量模型（首次运行可能需下载约1.3GB模型文件）...")
        from app.services.embedding_svc import EmbeddingService
        EmbeddingService()
        startup_logger.info("向量模型就绪，AI评测功能可用")
    except Exception as e:
        startup_logger.warning(
            "向量模型不可用，AI评测功能将无法使用。"
            f"错误: {e}。"
            "其他功能（文本清洗、GEO重构、JSON-LD）不受影响。"
        )


@app.on_event("startup")
async def startup_load_history():
    """启动时加载评测历史"""
    import logging
    hist_logger = logging.getLogger(__name__)
    try:
        from app.core.eval_history_store import load_all_sessions
        sessions = load_all_sessions()
        hist_logger.info(f"已加载 {len(sessions)} 条评测历史记录")
    except Exception as e:
        hist_logger.warning(f"评测历史加载失败: {e}")


@app.on_event("startup")
async def startup_init_scheduler():
    """启动定时任务调度器"""
    import logging
    sched_logger = logging.getLogger(__name__)
    try:
        from app.core.scheduler import _ensure_running
        _ensure_running()
        sched_logger.info("定时任务调度器已启动")
    except Exception as e:
        sched_logger.warning(f"定时任务调度器启动失败: {e}")


@app.on_event("startup")
async def startup_init_platform_rules():
    """启动时初始化平台规则数据"""
    import logging
    plat_logger = logging.getLogger(__name__)
    try:
        from app.api.platform_monitor import init_platform_rules
        count = await init_platform_rules()
        if count > 0:
            plat_logger.info(f"已初始化 {count} 个平台的规则数据文件")
        else:
            plat_logger.info("平台规则数据文件已就绪")
    except Exception as e:
        plat_logger.warning(f"平台规则初始化失败: {e}")


@app.on_event("startup")
async def startup_watchdog():
    """启动文件系统监控（watchdog），实时监听YAML模板变更"""
    import logging
    wd_logger = logging.getLogger(__name__)
    try:
        from app.core.template_watcher import start_watcher
        ok = start_watcher()
        if ok:
            wd_logger.info("Watchdog 文件监控已启动")
        else:
            wd_logger.info("Watchdog 未启动（可能被禁用或库未安装），使用 TTL 轮询模式")
    except Exception as e:
        wd_logger.warning(f"Watchdog 启动失败: {e}，回退到 TTL 轮询模式")


@app.on_event("startup")
async def startup_backup():
    """启动时注册每日数据自动备份"""
    import logging
    bk_logger = logging.getLogger(__name__)
    try:
        from app.core.data_backup import register_backup_job
        register_backup_job()
        bk_logger.info("每日数据备份任务已注册（凌晨2:00自动执行，保留最近7天）")
    except Exception as e:
        bk_logger.warning(f"数据备份任务注册失败: {e}")


@app.on_event("shutdown")
async def shutdown_watchdog():
    """停止文件系统监控"""
    try:
        from app.core.template_watcher import stop_watcher
        stop_watcher()
    except Exception:
        pass


# ── 数据备份管理API ──

@app.get("/api/backup/list")
async def list_backups():
    """列出所有数据备份"""
    from app.core.data_backup import list_backups
    return list_backups()


@app.post("/api/backup/create")
async def manual_backup():
    """手动触发一次数据备份"""
    from app.core.data_backup import create_backup
    try:
        result = create_backup()
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"备份失败: {str(e)}")


@app.post("/api/backup/restore")
async def restore_backup(backup_name: str):
    """从指定备份恢复数据（会覆盖当前数据！）"""
    from app.core.data_backup import restore_backup
    try:
        result = restore_backup(backup_name)
        return {"success": True, **result}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"备份文件不存在: {backup_name}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"恢复失败: {str(e)}")


# ── 系统接口 ──

@app.get("/api/health")
async def health_check():
    from app.services.embedding_svc import _embedding_model
    from app.services.llm.base import LLMFactory

    # 检查 LLM 平台可用性
    settings = load_settings()
    api_keys = load_api_keys()
    available_llm = []
    for pk, cfg in settings.get("llm", {}).get("platforms", {}).items():
        ki = api_keys.get("platforms", {}).get(pk, {})
        if ki.get("api_key", "") and "your-" not in ki.get("api_key", ""):
            available_llm.append(pk)

    return {
        "status": "ok",
        "version": "2.0.0-personal",
        "embedding_model_loaded": _embedding_model is not None,
        "model_status": "ready" if _embedding_model is not None else "loading/下载中",
        "llm_platforms_available": available_llm,
        "llm_count": len(available_llm),
        "features": {
            "cleaning": True,
            "geo_rewrite": len(available_llm) > 0,
            "evaluation": _embedding_model is not None and len(available_llm) > 0,
            "brand_monitor": len(available_llm) > 0,
            "publish_adapt": len(available_llm) > 0,
        },
    }


@app.get("/api/config/llm", response_model=SystemConfigResponse)
async def get_llm_config():
    """获取LLM平台配置状态"""
    settings = load_settings()
    api_keys = load_api_keys()
    platforms_status = []

    for plat_key, plat_cfg in settings.get("llm", {}).get("platforms", {}).items():
        key_info = api_keys.get("platforms", {}).get(plat_key, {})
        has_key = bool(key_info.get("api_key") and "your-" not in str(key_info.get("api_key", "")))
        platforms_status.append(LLMConfigStatus(
            platform=AIPlatform(plat_key),
            configured=has_key,
            api_key_masked=f"{key_info.get('api_key', '')[:8]}****" if has_key else "未配置",
            model_name=plat_cfg.get("model_name", ""),
            base_url=plat_cfg.get("base_url"),
        ).model_dump())

    return SystemConfigResponse(
        llm_platforms=platforms_status,
        embedding_model=settings.get("embedding", {}).get("model_name", ""),
        data_dir=str(settings.get("system", {}).get("data_dir", "./data")),
        version="2.0.0-personal",
        enterprise_name=settings.get("system", {}).get("enterprise_name", ""),
        enterprise_location=settings.get("system", {}).get("enterprise_location", ""),
        enterprise_website=settings.get("system", {}).get("enterprise_website", ""),
    ).model_dump()


# ── API Key 格式校验规则 ──
KEY_PATTERNS = {
    "deepseek": {"api_key": r"^sk-[a-zA-Z0-9]{28,}$"},
    "tongyi": {"api_key": r"^sk-[a-zA-Z0-9]{18,}$"},
    "doubao": {"api_key": r"^[a-zA-Z0-9_-]{20,}$"},
    "yuanbao": {"api_key": r"^[a-zA-Z0-9_-]{20,}$"},
    "wenxin": {"api_key": r"^[a-zA-Z0-9]{16,}$", "secret_key": r"^[a-zA-Z0-9]{16,}$"},
    "kimi": {"api_key": r"^sk-[a-zA-Z0-9]{28,}$"},
    "xinghuo": {"api_key": r"^[a-zA-Z0-9_-]{20,}$"},
    "claude": {"api_key": r"^sk-ant-[a-zA-Z0-9_-]{20,}$"},
    "openai": {"api_key": r"^sk-[a-zA-Z0-9]{28,}$"},
}

@app.post("/api/config/llm/update")
async def update_llm_config(req: LLMConfigUpdateRequest):
    """更新LLM平台的API Key（格式校验 + 立即生效）"""
    import re
    import yaml
    from pathlib import Path

    platform = req.platform
    api_key = req.api_key.strip()
    secret_key = req.secret_key.strip()

    if not platform:
        raise HTTPException(status_code=400, detail="请指定平台")
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空")

    # 格式校验
    patterns = KEY_PATTERNS.get(platform, {"api_key": r"^[a-zA-Z0-9_-]{16,}$"})
    if not re.match(patterns["api_key"], api_key):
        hint = ""
        if platform in ("deepseek", "tongyi", "kimi"):
            hint = "，应以 sk- 开头"
        raise HTTPException(status_code=400, detail=f"API Key 格式不正确{hint}")
    if "secret_key" in patterns and secret_key and not re.match(patterns["secret_key"], secret_key):
        raise HTTPException(status_code=400, detail="Secret Key 格式不正确")

    # 检查是否是占位符
    if "your-" in api_key.lower():
        raise HTTPException(status_code=400, detail="请替换为真实的 API Key，而非示例占位符")

    config_path = BACKEND_DIR / "config" / "api_keys.yaml"
    if not config_path.exists():
        raise HTTPException(status_code=500, detail="配置文件 api_keys.yaml 不存在")

    with _config_lock:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        if "platforms" not in config:
            config["platforms"] = {}
        if platform not in config["platforms"]:
            config["platforms"][platform] = {}
        config["platforms"][platform]["api_key"] = api_key
        if secret_key:
            config["platforms"][platform]["secret_key"] = secret_key

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".yaml",
                                          delete=False, dir=config_path.parent) as tmp:
            yaml.dump(config, tmp, allow_unicode=True, default_flow_style=False)
            tmp_path = tmp.name
        os.replace(tmp_path, str(config_path))

    from app.utils.config import invalidate_config_cache
    invalidate_config_cache()

    return {"status": "ok", "platform": platform, "configured": True, "message": f"{platform} 配置已保存并立即生效"}


# ── 启动入口 ──

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )
