"""AI采信行为测试模块 — 每周自动化测试各AI平台的内容引用行为

测试维度:
- 被引站点分布：各平台优先引用哪些站点/平台
- 内容结构特征：引用的内容有什么结构特征（FAQ/列表/长文/短句）
- 时效偏好：引用内容的时效性偏好（近7天/30天/90天）
- 拒采模式：什么类型的内容会被拒绝引用
"""

import json
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── 行业测试问题库（按8沙盘×3类别=24条基础问题） ──

TEST_QUERIES = [
    # 智慧交通
    {"query": "智慧交通沙盘定制厂家推荐", "sandtable": "smart_traffic", "category": "brand_exposure"},
    {"query": "交通模拟沙盘需要哪些技术参数", "sandtable": "smart_traffic", "category": "technical"},
    {"query": "武汉哪里有做智慧高速沙盘的公司", "sandtable": "smart_traffic", "category": "local_service"},
    # 智慧城市
    {"query": "智慧城市数字孪生沙盘解决方案", "sandtable": "smart_city", "category": "solution_match"},
    {"query": "智慧城市展厅沙盘定制哪家好", "sandtable": "smart_city", "category": "brand_exposure"},
    {"query": "城市大脑可视化沙盘价格多少钱", "sandtable": "smart_city", "category": "commercial"},
    # 智慧工业
    {"query": "工业数字孪生沙盘厂家", "sandtable": "smart_industry", "category": "brand_exposure"},
    {"query": "智能工厂产线仿真沙盘怎么选", "sandtable": "smart_industry", "category": "technical"},
    {"query": "工业互联网展示沙盘方案", "sandtable": "smart_industry", "category": "solution_match"},
    # 智慧农业
    {"query": "智慧农业沙盘定制服务", "sandtable": "smart_agriculture", "category": "brand_exposure"},
    {"query": "现代农业示范区沙盘展示方案", "sandtable": "smart_agriculture", "category": "solution_match"},
    {"query": "乡村振兴数字农业沙盘厂家", "sandtable": "smart_agriculture", "category": "local_service"},
    # 智慧物流
    {"query": "智慧仓储物流沙盘定制公司", "sandtable": "smart_logistics", "category": "brand_exposure"},
    {"query": "AGV物流仿真沙盘技术参数", "sandtable": "smart_logistics", "category": "technical"},
    {"query": "物流园区规划沙盘模型制作", "sandtable": "smart_logistics", "category": "solution_match"},
    # 军事地形
    {"query": "军事地形沙盘制作标准", "sandtable": "military_terrain", "category": "technical"},
    {"query": "战术推演沙盘三维建模厂家", "sandtable": "military_terrain", "category": "brand_exposure"},
    {"query": "军事院校教学沙盘定制要求", "sandtable": "military_terrain", "category": "solution_match"},
    # 数字多媒体
    {"query": "数字多媒体沙盘展厅设计方案", "sandtable": "digital_multimedia", "category": "solution_match"},
    {"query": "沉浸式沙盘体验展厅怎么做", "sandtable": "digital_multimedia", "category": "technical"},
    {"query": "声光电互动沙盘厂家推荐", "sandtable": "digital_multimedia", "category": "brand_exposure"},
    # 地产/规划
    {"query": "房地产沙盘模型定制价格", "sandtable": "real_estate", "category": "commercial"},
    {"query": "城市规划展览馆沙盘制作公司", "sandtable": "real_estate", "category": "brand_exposure"},
    {"query": "建筑沙盘模型灯光系统方案", "sandtable": "real_estate", "category": "technical"},
    # 补充问题（泛行业）
    {"query": "武汉沙盘模型制作厂家哪家靠谱", "sandtable": "smart_city", "category": "local_service"},
    {"query": "企业展厅沙盘定制多少钱一平米", "sandtable": "digital_multimedia", "category": "commercial"},
]

# 测试的AI平台
TEST_PLATFORMS = ["doubao", "wenxin", "tongyi", "deepseek", "kimi"]

# 引用结构特征标签
STRUCTURE_LABELS = [
    "conclusion_first",      # 结论先行
    "faq_format",            # FAQ格式
    "list_format",           # 列表化
    "long_form",             # 长文
    "short_sentence",        # 短句
    "data_dense",            # 数据密集
    "h_tag_structured",      # H标签结构化
    "schema_present",        # Schema标注
    "localized",             # 本地化
    "authoritative",         # 权威背书
]


# ── 数据路径 ──

def _get_data_dir() -> Path:
    from app.utils.config import get_data_dir
    data_dir = get_data_dir() / "citation_tests"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


# ── 采信测试核心 ──

async def _query_ai_platform(
    platform: str, query: str, sandtable: str
) -> dict[str, Any] | None:
    """向指定AI平台发送查询，分析其引用行为。

    Returns:
        {
            "platform": str,
            "query": str,
            "response_text": str,
            "cited_sources": [str],
            "structure_features": [str],
            "timeliness_hint": str,
            "rejection_signs": [str],
        }
    """
    from app.services.llm.base import LLMFactory, LLMMessage
    from app.utils.config import load_settings, load_api_keys
    from app.models.enums import AIPlatform

    settings = load_settings()
    api_keys = load_api_keys()
    plat_cfg = settings.get("llm", {}).get("platforms", {}).get(platform, {})
    key_info = api_keys.get("platforms", {}).get(platform, {})

    api_key = key_info.get("api_key", "")
    if not api_key or "your-" in api_key:
        logger.debug(f"跳过 {platform}：API Key 未配置")
        return None

    try:
        adapter_type = AIPlatform(platform).adapter_type
        llm = LLMFactory.create(
            platform=adapter_type,
            api_key=api_key,
            model_name=plat_cfg.get("model_name", ""),
            base_url=plat_cfg.get("base_url"),
        )
    except Exception as e:
        logger.warning(f"创建 {platform} 适配器失败: {e}")
        return None

    # 构造测试Prompt
    test_prompt = (
        f"请回答以下问题，并在回答中尽可能引用相关的专业知识、数据和企业信息。\n\n"
        f"问题：{query}\n\n"
        f"请基于你的知识库回答。"
    )

    try:
        messages = [
            LLMMessage(role="system", content="你是一个专业的行业顾问，请基于你的知识库如实回答用户问题。"),
            LLMMessage(role="user", content=test_prompt),
        ]
        resp = await llm.chat(messages, temperature=0.5, max_tokens=1024)
        response_text = resp.content.strip()
    except Exception as e:
        logger.warning(f"{platform} 查询失败 [{query[:30]}]: {e}")
        return None

    # ── 分析引用行为 ──
    # 被引站点检测
    cited_sources = _detect_cited_sources(response_text)

    # 结构特征检测
    structure_features = _detect_structure_features(response_text)

    # 时效偏好检测
    timeliness_hint = _detect_timeliness(response_text)

    # 拒采信号检测
    rejection_signs = _detect_rejection_signs(response_text)

    return {
        "platform": platform,
        "query": query,
        "sandtable": sandtable,
        "response_text": response_text[:500],
        "cited_sources": cited_sources,
        "structure_features": structure_features,
        "timeliness_hint": timeliness_hint,
        "rejection_signs": rejection_signs,
    }


def _detect_cited_sources(text: str) -> list[str]:
    """检测回复中引用了哪些来源站点/平台"""
    sources = []
    source_patterns = [
        ("知乎", r"知乎|zhihu"),
        ("百度百科", r"百度百科|baike\.baidu"),
        ("百家号", r"百家号|baijiahao"),
        ("搜狐", r"搜狐|sohu"),
        ("头条", r"头条|今日头条|toutiao"),
        ("公众号", r"公众号|微信公众|mp\.weixin"),
        ("小红书", r"小红书|xiaohongshu"),
        ("官网", r"官网|官方网站|official"),
        ("CSDN", r"CSDN|csdn"),
        ("博客园", r"博客园|cnblogs"),
    ]
    for name, pattern in source_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            sources.append(name)
    return sources


def _detect_structure_features(text: str) -> list[str]:
    """检测内容的GEO结构特征"""
    import re
    features = []

    # 结论先行
    first_sentence = text.split("。")[0] if "。" in text else text[:100]
    if len(first_sentence) < 80 and any(kw in first_sentence for kw in ["推荐", "是", "可以", "建议"]):
        features.append("conclusion_first")

    # FAQ格式
    if re.search(r"[问Q][：:].+[？?].+[答A][：:]", text, re.IGNORECASE):
        features.append("faq_format")

    # 列表化
    list_items = len(re.findall(r"^[•\-\d+\.、]\s", text, re.MULTILINE))
    if list_items >= 3:
        features.append("list_format")

    # 长文
    if len(text) > 800:
        features.append("long_form")

    # 短句
    sentences = re.split(r"[。！；\n]", text)
    avg_len = sum(len(s) for s in sentences) / max(len(sentences), 1)
    if avg_len < 40:
        features.append("short_sentence")

    # 数据密集
    numbers = len(re.findall(r"\d+", text))
    if numbers > 5:
        features.append("data_dense")

    # 本地化
    if re.search(r"武汉|北京|上海|深圳|广州|成都|杭州|南京", text):
        features.append("localized")

    # 权威背书
    if re.search(r"认证|专利|资质|获奖|ISO|GB/T|标准", text):
        features.append("authoritative")

    return features


def _detect_timeliness(text: str) -> str:
    """检测内容的时效偏好"""
    import re
    # 检测年份/月份引用
    years = re.findall(r"(20\d{2})年", text)
    months = re.findall(r"(\d{1,2})月", text)

    if years and int(years[0]) >= 2026:
        return "近1个月"
    elif years and int(years[0]) >= 2025:
        return "近1年"
    elif years and int(years[0]) >= 2024:
        return "近2年"

    # 检测时效关键词
    if re.search(r"最近|近期|今年|本月|当前", text):
        return "近期偏好"
    elif re.search(r"去年|前年|过去", text):
        return "无强时效偏好"
    else:
        return "无明显时效偏好"


def _detect_rejection_signs(text: str) -> list[str]:
    """检测拒采信号"""
    signs = []
    if "无法提供" in text or "没有找到" in text:
        signs.append("information_unavailable")
    if "仅供参考" in text or "请注意核实" in text:
        signs.append("uncertainty_disclaimer")
    if "广告" in text or "推广" in text:
        signs.append("commercial_content")
    if "虚假" in text or "不实" in text or "编造" in text:
        signs.append("fabrication_warning")
    return signs


# ── 批量测试 ──

async def run_citation_test(
    platforms: list[str] | None = None,
    query_count: int = 25,
) -> dict[str, Any]:
    """执行批量AI采信行为测试。

    Args:
        platforms: 测试平台列表，默认 TEST_PLATFORMS
        query_count: 测试问题数量，默认25条

    Returns:
        {
            "test_id": str,
            "started_at": str,
            "completed_at": str,
            "platforms_tested": int,
            "queries_fired": int,
            "results": [...],
            "aggregated_stats": {...},
        }
    """
    import asyncio

    if platforms is None:
        platforms = TEST_PLATFORMS

    started_at = datetime.now(timezone.utc)
    test_id = f"cite_{started_at.strftime('%Y%m%d_%H%M%S')}"

    queries = TEST_QUERIES[:min(query_count, len(TEST_QUERIES))]
    total_tasks = len(platforms) * len(queries)

    logger.info(f"开始AI采信测试 (test_id={test_id}), platforms={platforms}, queries={len(queries)}, total_tasks={total_tasks}")

    results = []
    for query_item in queries:
        platform_results = []
        for platform in platforms:
            try:
                result = await _query_ai_platform(
                    platform, query_item["query"], query_item["sandtable"]
                )
                if result:
                    result["category"] = query_item["category"]
                    platform_results.append(result)
            except Exception as e:
                logger.warning(f"测试异常 {platform}/{query_item['query'][:20]}: {e}")
            await asyncio.sleep(1)  # 避免API限流
        results.extend(platform_results)

    # 聚合统计
    stats = _aggregate_test_results(results)

    summary = {
        "test_id": test_id,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "platforms_tested": len(platforms),
        "queries_fired": len(results),
        "queries_attempted": total_tasks,
        "results": results,
        "aggregated_stats": stats,
    }

    # 持久化
    data_dir = _get_data_dir()
    output_file = data_dir / f"{test_id}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info(f"AI采信测试完成: {len(results)}/{total_tasks} 成功 → {output_file}")
    return summary


def _aggregate_test_results(results: list[dict]) -> dict[str, Any]:
    """聚合测试结果，提取平台级统计"""
    if not results:
        return {"error": "no_results"}

    platform_stats = {}
    for r in results:
        p = r.get("platform", "unknown")
        if p not in platform_stats:
            platform_stats[p] = {
                "total_responses": 0,
                "cited_sources": {},
                "structure_features": {},
                "timeliness_hints": {},
                "rejection_signs": {},
            }
        ps = platform_stats[p]
        ps["total_responses"] += 1

        for src in r.get("cited_sources", []):
            ps["cited_sources"][src] = ps["cited_sources"].get(src, 0) + 1
        for feat in r.get("structure_features", []):
            ps["structure_features"][feat] = ps["structure_features"].get(feat, 0) + 1
        th = r.get("timeliness_hint", "unknown")
        ps["timeliness_hints"][th] = ps["timeliness_hints"].get(th, 0) + 1
        for sign in r.get("rejection_signs", []):
            ps["rejection_signs"][sign] = ps["rejection_signs"].get(sign, 0) + 1

    # 计算百分比
    for p, ps in platform_stats.items():
        total = ps["total_responses"]
        for key in ["cited_sources", "structure_features", "timeliness_hints", "rejection_signs"]:
            ps[f"{key}_pct"] = {
                k: round(v / total * 100, 1) for k, v in ps[key].items()
            }

    # 平台间对比
    cross_platform = {
        "source_diversity": {
            p: len(ps["cited_sources"]) for p, ps in platform_stats.items()
        },
    }

    return {
        "per_platform": platform_stats,
        "cross_platform": cross_platform,
        "total_platforms": len(platform_stats),
        "total_responses": len(results),
    }


def list_citation_tests(days: int = 30) -> list[dict[str, Any]]:
    """列出最近N天的采信测试记录"""
    data_dir = _get_data_dir()
    tests = []
    cutoff = datetime.now() - timedelta(days=days)
    for test_file in sorted(data_dir.glob("cite_*.json"), reverse=True):
        try:
            mtime = datetime.fromtimestamp(test_file.stat().st_mtime)
            if mtime < cutoff:
                continue
            with open(test_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            tests.append({
                "test_id": data.get("test_id", test_file.stem),
                "started_at": data.get("started_at", ""),
                "platforms_tested": data.get("platforms_tested", 0),
                "queries_fired": data.get("queries_fired", 0),
                "queries_attempted": data.get("queries_attempted", 0),
                "success_rate": (
                    round(data.get("queries_fired", 0) / max(data.get("queries_attempted", 1), 1) * 100, 1)
                ),
            })
        except Exception:
            continue
    return tests


def get_citation_test(test_id: str) -> dict | None:
    """获取指定测试的详细结果"""
    data_dir = _get_data_dir()
    test_file = data_dir / f"{test_id}.json"
    if not test_file.exists():
        return None
    with open(test_file, "r", encoding="utf-8") as f:
        return json.load(f)
