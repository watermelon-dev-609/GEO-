"""竞品调研 API"""

import json
import logging
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    CompetitorCreateRequest, CompetitorUpdateRequest, SnapshotAddRequest,
    CompetitorCompareRequest, CompetitorReportRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "competitors"


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_file(comp_id: str) -> Path:
    return DATA_DIR / f"{comp_id}.json"


def _list_all() -> list[dict]:
    _ensure_dir()
    files = sorted(DATA_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    result = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                result.append(json.load(fh))
        except Exception:
            pass
    return result


@router.get("")
async def list_competitors():
    """列出所有竞品"""
    return {"competitors": _list_all()}


@router.get("/{comp_id}")
async def get_competitor(comp_id: str):
    """获取竞品详情"""
    f = _get_file(comp_id)
    if not f.exists():
        raise HTTPException(status_code=404, detail="竞品不存在")
    with open(f, "r", encoding="utf-8") as fh:
        return json.load(fh)


@router.post("")
async def create_competitor(req: CompetitorCreateRequest):
    """添加竞品"""
    comp_id = "comp_" + datetime.now().strftime("%Y%m%d%H%M%S")
    data = {
        "id": comp_id,
        "name": req.name,
        "website": req.website,
        "industry": req.industry,
        "notes": req.notes,
        "platform_exposure": req.platform_exposure,
        "content_features": req.content_features,
        "snapshots": [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    _ensure_dir()
    with open(_get_file(comp_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


@router.put("/{comp_id}")
async def update_competitor(comp_id: str, req: CompetitorUpdateRequest):
    """更新竞品"""
    f = _get_file(comp_id)
    if not f.exists():
        raise HTTPException(status_code=404, detail="竞品不存在")
    with open(f, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    updates = req.model_dump(exclude_none=True)
    for key in ("name", "website", "industry", "notes", "platform_exposure", "content_features"):
        if key in updates:
            data[key] = updates[key]
    data["updated_at"] = datetime.now().isoformat()

    with open(f, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return data


@router.delete("/{comp_id}")
async def delete_competitor(comp_id: str):
    """删除竞品"""
    f = _get_file(comp_id)
    if not f.exists():
        raise HTTPException(status_code=404, detail="竞品不存在")
    f.unlink()
    return {"status": "deleted"}


@router.post("/{comp_id}/snapshot")
async def add_snapshot(comp_id: str, req: SnapshotAddRequest):
    """添加竞品快照 — 记录某时间点在AI平台上的引用情况"""
    if not req.platform or not req.platform.strip():
        raise HTTPException(status_code=422, detail="平台名称不能为空")
    f = _get_file(comp_id)
    if not f.exists():
        raise HTTPException(status_code=404, detail="竞品不存在")
    with open(f, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    data.setdefault("snapshots", []).insert(0, {
        "date": req.date or datetime.now().strftime("%Y-%m-%d"),
        "platform": req.platform,
        "query": req.query,
        "citation_found": req.citation_found,
        "citation_snippet": req.citation_snippet,
        "notes": req.notes,
    })
    data["updated_at"] = datetime.now().isoformat()

    with open(f, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return data


@router.post("/compare")
async def compare_competitors(req: CompetitorCompareRequest):
    """竞品对比分析 — 支持 LLM 生成对比报告"""
    ids = req.competitor_ids

    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="请至少选择 2 个竞品进行对比")

    competitors = []
    for cid in ids:
        f = _get_file(cid)
        if f.exists():
            with open(f, "r", encoding="utf-8") as fh:
                competitors.append(json.load(fh))

    if len(competitors) < 2:
        raise HTTPException(status_code=400, detail="有效竞品数量不足")

    # 构建对比矩阵
    comparison = {
        "competitors": [{"id": c["id"], "name": c["name"], "website": c["website"]} for c in competitors],
        "platform_coverage": {},
        "content_features": {},
    }
    for c in competitors:
        comparison["platform_coverage"][c["name"]] = c.get("platform_exposure", {})
        comparison["content_features"][c["name"]] = c.get("content_features", {})

    # LLM 分析
    llm_analysis = None
    if req.include_llm:
        llm_analysis = await _generate_llm_comparison(competitors, req.sandtable_type)

    return {
        "comparison": comparison,
        "llm_analysis": llm_analysis,
    }


async def _generate_llm_comparison(competitors: list[dict], sandtable_type: str) -> dict | None:
    """LLM 生成竞品对比分析"""
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

    try:
        adapter_type = AIPlatform(default_platform).adapter_type
        llm = LLMFactory.create(
            platform=adapter_type,
            api_key=api_key,
            model_name=plat_cfg.get("model_name", ""),
            base_url=plat_cfg.get("base_url"),
        )

        comp_list = "\n".join([
            f"- {c['name']}: {c.get('website', '')}, {c.get('industry', '')}, "
            f"AI平台曝光: {json.dumps(c.get('platform_exposure', {}), ensure_ascii=False)}, "
            f"内容特征: {json.dumps(c.get('content_features', {}), ensure_ascii=False)}"
            for c in competitors
        ])

        prompt = f"""你是竞品分析专家。请对以下同行业竞品进行对比分析：

行业：{sandtable_type or '沙盘模型定制'}

竞品列表：
{comp_list}

请从以下维度进行分析，给出JSON格式：
1. 各竞品在AI搜索场景的内容优势与劣势
2. 我方可借鉴的策略方向
3. 竞品未覆盖的内容空白机会点

返回JSON：
{{"analysis": "综合分析...", "strengths": {{"竞品名": "优势描述"}}, "weaknesses": {{"竞品名": "劣势描述"}}, "opportunities": ["机会点1", "机会点2"], "recommendations": ["策略建议1", "策略建议2"]}}"""

        messages = [
            LLMMessage(role="system", content="你是竞品分析专家。基于给定数据客观分析，不编造信息。"),
            LLMMessage(role="user", content=prompt),
        ]
        resp = await llm.chat(messages, temperature=0.5, max_tokens=2048)

        import re
        json_match = re.search(r'\{[\s\S]*\}', resp.content)
        if json_match:
            return json.loads(json_match.group(0))
        return {"analysis": resp.content}
    except Exception as e:
        logger.warning(f"LLM comparison failed: {e}")
        return None


@router.post("/report")
async def generate_report(req: CompetitorReportRequest):
    """生成竞品调研报告（Markdown格式）"""
    ids = req.competitor_ids
    if len(ids) < 1:
        raise HTTPException(status_code=400, detail="请选择至少 1 个竞品")

    competitors = []
    for cid in ids:
        f = _get_file(cid)
        if f.exists():
            with open(f, "r", encoding="utf-8") as fh:
                competitors.append(json.load(fh))

    lines = ["# 竞品调研报告", f"\n生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]

    for i, c in enumerate(competitors, 1):
        lines.append(f"## {i}. {c['name']}")
        lines.append(f"- 官网：{c.get('website', '未填写')}")
        lines.append(f"- 行业：{c.get('industry', '未填写')}")
        lines.append(f"- 备注：{c.get('notes', '无')}")
        lines.append("")
        if c.get("platform_exposure"):
            lines.append("### AI平台曝光情况")
            for plat, level in c["platform_exposure"].items():
                lines.append(f"- **{plat}**: {level}")
            lines.append("")
        if c.get("content_features"):
            lines.append("### 内容特征")
            for feat, val in c["content_features"].items():
                lines.append(f"- **{feat}**: {val}")
            lines.append("")
        if c.get("snapshots"):
            lines.append("### 历史快照")
            for snap in c["snapshots"][:5]:
                lines.append(f"- {snap['date']} | {snap['platform']} | 查询「{snap['query']}」→ {'✓ 有引用' if snap.get('citation_found') else '✗ 无引用'}")
            lines.append("")

    report = "\n".join(lines)
    return {"report": report, "format": "markdown"}
