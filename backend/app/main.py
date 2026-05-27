"""GEO生成式搜索优化系统 - FastAPI入口"""

import os
import logging
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
from app.models.schemas import SystemConfigResponse, LLMConfigStatus
from app.models.enums import AIPlatform
from app.utils.config import load_settings, load_api_keys, get_data_dir

# ── 应用初始化 ──

app = FastAPI(
    title="GEO生成式搜索优化系统",
    description="武汉微艺达智能科技有限公司 - 轻量化GEO优化平台",
    version="1.0.0-personal",
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

# ── 注册路由 ──

app.include_router(cleaning.router, prefix="/api/cleaning", tags=["文本清洗"])
app.include_router(geo_rewrite.router, prefix="/api/geo", tags=["GEO文案重构"])
app.include_router(jsonld.router, prefix="/api/jsonld", tags=["JSON-LD生成"])
app.include_router(evaluation.router, prefix="/api/evaluate", tags=["AI评测"])
app.include_router(reports.router, prefix="/api/reports", tags=["数据报表"])

# 确保数据目录存在
get_data_dir()
(BACKEND_DIR / "data" / "output").mkdir(parents=True, exist_ok=True)
(BACKEND_DIR / "data" / "evaluations").mkdir(parents=True, exist_ok=True)


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


# ── 系统接口 ──

@app.get("/api/health")
async def health_check():
    from app.services.embedding_svc import _embedding_model
    return {
        "status": "ok",
        "version": "1.0.0-personal",
        "embedding_model_loaded": _embedding_model is not None,
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
        version="1.0.0-personal",
    ).model_dump()


# ── API Key 格式校验规则 ──
KEY_PATTERNS = {
    "deepseek": {"api_key": r"^sk-[a-zA-Z0-9]{28,}$"},
    "gpt": {"api_key": r"^sk-(proj-)?[a-zA-Z0-9_-]{28,}$"},
    "tongyi": {"api_key": r"^sk-[a-zA-Z0-9]{18,}$"},
    "doubao": {"api_key": r"^[a-zA-Z0-9_-]{20,}$"},
    "yuanbao": {"api_key": r"^[a-zA-Z0-9_-]{20,}$"},
    "claude": {"api_key": r"^sk-ant-[a-zA-Z0-9]{30,}$"},
    "wenxin": {"api_key": r"^[a-zA-Z0-9]{16,}$", "secret_key": r"^[a-zA-Z0-9]{16,}$"},
}

@app.post("/api/config/llm/update")
async def update_llm_config(req: dict):
    """更新LLM平台的API Key（格式校验 + 立即生效）"""
    import re
    import yaml
    from pathlib import Path

    platform = req.get("platform", "")
    api_key = req.get("api_key", "").strip()
    secret_key = req.get("secret_key", "").strip()

    if not platform:
        raise HTTPException(status_code=400, detail="请指定平台")
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空")

    # 格式校验
    patterns = KEY_PATTERNS.get(platform, {"api_key": r"^[a-zA-Z0-9_-]{16,}$"})
    if not re.match(patterns["api_key"], api_key):
        hint = ""
        if platform in ("deepseek", "gpt", "tongyi"):
            hint = "，应以 sk- 开头"
        elif platform == "claude":
            hint = "，应以 sk-ant- 开头"
        raise HTTPException(status_code=400, detail=f"API Key 格式不正确{hint}")
    if "secret_key" in patterns and secret_key and not re.match(patterns["secret_key"], secret_key):
        raise HTTPException(status_code=400, detail="Secret Key 格式不正确")

    # 检查是否是占位符
    if "your-" in api_key.lower():
        raise HTTPException(status_code=400, detail="请替换为真实的 API Key，而非示例占位符")

    config_path = BACKEND_DIR / "config" / "api_keys.yaml"
    if not config_path.exists():
        raise HTTPException(status_code=500, detail="配置文件 api_keys.yaml 不存在")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    if "platforms" not in config:
        config["platforms"] = {}
    if platform not in config["platforms"]:
        config["platforms"][platform] = {}
    config["platforms"][platform]["api_key"] = api_key
    if secret_key:
        config["platforms"][platform]["secret_key"] = secret_key

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

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
