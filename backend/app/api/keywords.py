"""关键词体系 API — 行业关键词库 CRUD + LLM扩展"""

import json
import logging
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from app.models.schemas import KeywordAddRequest, KeywordUpdateRequest, KeywordExpandRequest

logger = logging.getLogger(__name__)
router = APIRouter()

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "keywords"
SANDBTABLE_TYPES = [
    "smart_traffic", "smart_city", "smart_industry", "smart_agriculture",
    "smart_logistics", "military_terrain", "digital_multimedia", "real_estate",
]

SANDBTABLE_LABELS = {
    "smart_traffic": "智慧交通沙盘",
    "smart_city": "智慧城市沙盘",
    "smart_industry": "智慧工业沙盘",
    "smart_agriculture": "智慧农业沙盘",
    "smart_logistics": "智慧物流沙盘",
    "military_terrain": "军事地形沙盘",
    "digital_multimedia": "数字多媒体沙盘",
    "real_estate": "地产规划展厅沙盘",
}

PRELOADED_KEYWORDS = {
    "brand": [
        {"word": "武汉微艺达", "weight": "core", "status": "optimized"},
        {"word": "微艺达智能科技", "weight": "core", "status": "optimized"},
        {"word": "武汉沙盘定制", "weight": "core", "status": "optimized"},
        {"word": "沙盘模型厂家", "weight": "core", "status": "optimized"},
        {"word": "武汉沙盘模型", "weight": "core", "status": "optimized"},
    ],
    "scene": [
        {"word": "智慧交通沙盘定制", "weight": "core", "status": "pending"},
        {"word": "智慧城市数字沙盘", "weight": "core", "status": "pending"},
        {"word": "工业仿真沙盘", "weight": "core", "status": "pending"},
        {"word": "智慧农业物联网沙盘", "weight": "core", "status": "pending"},
        {"word": "军事地形沙盘模型", "weight": "core", "status": "pending"},
        {"word": "数字多媒体展厅", "weight": "core", "status": "pending"},
    ],
    "longtail": [
        {"word": "沙盘模型定制多少钱", "weight": "longtail", "status": "pending"},
        {"word": "武汉沙盘厂家哪家好", "weight": "longtail", "status": "pending"},
        {"word": "数字沙盘制作流程", "weight": "longtail", "status": "pending"},
        {"word": "智慧交通沙盘方案", "weight": "longtail", "status": "pending"},
    ],
}


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_kw_file(sandtable_type: str) -> Path:
    return DATA_DIR / f"{sandtable_type}.json"


def _load_keywords(sandtable_type: str) -> dict:
    file = _get_kw_file(sandtable_type)
    if file.exists():
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    label = SANDBTABLE_LABELS.get(sandtable_type, sandtable_type)
    return {
        "sandtable_type": sandtable_type,
        "label": label,
        "keywords": {
            "brand": [],
            "scene": [],
            "longtail": [],
        },
        "updated_at": "",
    }


def _save_keywords(data: dict):
    _ensure_dir()
    data["updated_at"] = datetime.now().isoformat()
    sandtable_type = data["sandtable_type"]
    with open(_get_kw_file(sandtable_type), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@router.get("/types")
async def list_sandtable_types():
    """获取所有沙盘类型"""
    return {
        "types": [{"key": k, "label": v} for k, v in SANDBTABLE_LABELS.items()]
    }


@router.get("/{sandtable_type}")
async def get_keywords(sandtable_type: str):
    """获取指定沙盘类型的关键词库"""
    if sandtable_type not in SANDBTABLE_TYPES:
        raise HTTPException(status_code=400, detail=f"无效的沙盘类型: {sandtable_type}")

    data = _load_keywords(sandtable_type)

    # 如果是空库，填充预置关键词
    total_keywords = sum(len(v) for v in data["keywords"].values())
    if total_keywords == 0:
        data["keywords"] = json.loads(json.dumps(PRELOADED_KEYWORDS))
        _save_keywords(data)

    return data


@router.post("/{sandtable_type}")
async def add_keyword(sandtable_type: str, req: KeywordAddRequest):
    """添加关键词"""
    if sandtable_type not in SANDBTABLE_TYPES:
        raise HTTPException(status_code=400, detail=f"无效的沙盘类型: {sandtable_type}")

    word = req.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="关键词不能为空")

    data = _load_keywords(sandtable_type)
    if req.category not in data["keywords"]:
        data["keywords"][req.category] = []

    # 去重
    existing = [k for k in data["keywords"][req.category] if k["word"] == word]
    if existing:
        raise HTTPException(status_code=409, detail=f"关键词已存在: {word}")

    data["keywords"][req.category].append({
        "word": word, "weight": req.weight, "status": req.status,
    })
    _save_keywords(data)
    return {"status": "ok", "word": word}


@router.delete("/{sandtable_type}/{category}/{word:path}")
async def delete_keyword(sandtable_type: str, category: str, word: str):
    """删除关键词"""
    if sandtable_type not in SANDBTABLE_TYPES:
        raise HTTPException(status_code=400, detail=f"无效的沙盘类型: {sandtable_type}")

    data = _load_keywords(sandtable_type)
    if category not in data["keywords"]:
        raise HTTPException(status_code=404, detail=f"分类不存在: {category}")

    data["keywords"][category] = [
        k for k in data["keywords"][category] if k["word"] != word
    ]
    _save_keywords(data)
    return {"status": "deleted", "word": word}


@router.put("/{sandtable_type}/{category}/{word:path}")
async def update_keyword(sandtable_type: str, category: str, word: str, req: KeywordUpdateRequest):
    """更新关键词状态/权重"""
    if sandtable_type not in SANDBTABLE_TYPES:
        raise HTTPException(status_code=400, detail=f"无效的沙盘类型: {sandtable_type}")

    data = _load_keywords(sandtable_type)
    if category not in data["keywords"]:
        raise HTTPException(status_code=404, detail=f"分类不存在: {category}")

    for kw in data["keywords"][category]:
        if kw["word"] == word:
            if req.weight is not None:
                kw["weight"] = req.weight
            if req.status is not None:
                kw["status"] = req.status
            if req.word_new:
                kw["word"] = req.word_new
            _save_keywords(data)
            return {"status": "ok", "keyword": kw}

    raise HTTPException(status_code=404, detail=f"关键词不存在: {word}")


@router.post("/{sandtable_type}/expand")
async def expand_keywords(sandtable_type: str, req: KeywordExpandRequest):
    """LLM扩展关键词 — 输入种子词生成关联关键词矩阵"""
    from app.services.llm.base import LLMFactory, LLMMessage
    from app.utils.config import load_settings, load_api_keys
    from app.models.enums import AIPlatform

    if sandtable_type not in SANDBTABLE_TYPES:
        raise HTTPException(status_code=400, detail=f"无效的沙盘类型: {sandtable_type}")

    seed = req.seed
    label = SANDBTABLE_LABELS.get(sandtable_type, sandtable_type)

    settings = load_settings()
    api_keys = load_api_keys()

    default_platform = settings.get("llm", {}).get("default_model", "deepseek")
    plat_cfg = settings.get("llm", {}).get("platforms", {}).get(default_platform, {})
    key_info = api_keys.get("platforms", {}).get(default_platform, {})

    api_key = key_info.get("api_key", "")
    if not api_key or "your-" in api_key:
        raise HTTPException(status_code=400, detail="未配置LLM API Key")

    adapter_type = AIPlatform(default_platform).adapter_type
    llm = LLMFactory.create(
        platform=adapter_type,
        api_key=api_key,
        model_name=plat_cfg.get("model_name", ""),
        base_url=plat_cfg.get("base_url"),
    )

    expand_prompt = f"""你是一个GEO关键词研究专家。请为「{label}」行业扩展关键词矩阵。

种子词: {seed if seed else '无，请自行生成'}

请按以下三类输出30个关键词（JSON格式）：

1. brand（品牌词）：企业名、品牌名、地域+业务变体（5-8个）
2. scene（场景词）：行业场景+产品/服务组合（10-12个）
3. longtail（长尾词）：用户实际会搜索的自然问句、长尾查询（10-12个）

直接返回JSON数组，每个词包含 word, weight(core/secondary/longtail), search_intent 字段。"""

    messages = [
        LLMMessage(role="system", content="你是一个专业的SEO/GEO关键词研究专家，擅长行业词汇扩展。"),
        LLMMessage(role="user", content=expand_prompt),
    ]
    resp = await llm.chat(messages, temperature=0.7, max_tokens=2048)

    # 尝试解析JSON
    import re
    json_match = re.search(r'\[[\s\S]*\]', resp.content)
    generated = []
    if json_match:
        try:
            generated = json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    return {
        "sandtable_type": sandtable_type,
        "label": label,
        "seed": seed,
        "generated_keywords": generated,
        "total": len(generated),
    }


@router.get("/{sandtable_type}/export")
async def export_keywords(sandtable_type: str):
    """导出关键词为CSV格式"""
    import csv
    import io

    if sandtable_type not in SANDBTABLE_TYPES:
        raise HTTPException(status_code=400, detail=f"无效的沙盘类型: {sandtable_type}")

    data = _load_keywords(sandtable_type)
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)
    writer.writerow(["分类", "关键词", "权重", "状态"])
    for cat, kws in data["keywords"].items():
        for kw in kws:
            writer.writerow([cat, kw["word"], kw["weight"], kw["status"]])

    return {"csv": output.getvalue(), "filename": f"keywords_{sandtable_type}.csv"}
