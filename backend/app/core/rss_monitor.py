"""RSS信源监控模块 — 自动抓取平台公告，关键词告警

监控范围:
- 百度搜索资源平台、百家号公告、文心一言官方博客
- 头条号/知乎创作者后台、豆包开放平台更新日志
- 微信公众号平台公告、搜一搜爬虫说明
- 知乎/小红书官方爬虫/索引规则公告

监控方式: HTTP抓取 + 关键词匹配（抓取、索引、收录、权重、算法更新）
"""

import json
import logging
import re
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── RSS信源配置 ──

RSS_SOURCES = [
    {
        "id": "baidu_search",
        "name": "百度搜索资源平台",
        "urls": [
            "https://ziyuan.baidu.com/college/courselist",
            "https://ziyuan.baidu.com/blog/articlelist",
        ],
        "keywords": ["抓取", "索引", "收录", "算法更新", "排名", "权重", "蜘蛛", "爬虫"],
        "category": "搜索引擎",
        "check_interval_hours": 24,
    },
    {
        "id": "baijiahao",
        "name": "百家号公告",
        "urls": [
            "https://baijiahao.baidu.com/builder/rc/notice",
            "https://baijiahao.baidu.com/s?id=1770000000000000000",
        ],
        "keywords": ["收录", "权重", "推荐", "审核", "规则", "算法", "内容质量"],
        "category": "内容平台",
        "check_interval_hours": 24,
    },
    {
        "id": "wenxin_blog",
        "name": "文心一言官方博客",
        "urls": [
            "https://yiyan.baidu.com/blog",
            "https://yiyan.baidu.com/news",
        ],
        "keywords": ["更新", "算法", "能力", "模型", "索引", "搜索", "内容"],
        "category": "AI大模型",
        "check_interval_hours": 48,
    },
    {
        "id": "toutiao_creator",
        "name": "头条号创作者平台",
        "urls": [
            "https://mp.toutiao.com/profile_v4/",
            "https://www.toutiao.com/",
        ],
        "keywords": ["推荐", "流量", "收录", "权重", "算法", "规则变更"],
        "category": "内容平台",
        "check_interval_hours": 24,
    },
    {
        "id": "doubao_changelog",
        "name": "豆包开放平台更新日志",
        "urls": [
            "https://www.volcengine.com/docs/82379",
            "https://www.volcengine.com/docs/82379/release-notes",
        ],
        "keywords": ["更新", "接口", "模型", "能力", "版本", "变更"],
        "category": "AI大模型",
        "check_interval_hours": 48,
    },
    {
        "id": "wechat_platform",
        "name": "微信公众号平台公告",
        "urls": [
            "https://mp.weixin.qq.com/",
            "https://developers.weixin.qq.com/community/promote",
        ],
        "keywords": ["搜一搜", "爬虫", "收录", "规则", "搜索", "索引", "内容生态"],
        "category": "社媒平台",
        "check_interval_hours": 24,
    },
    {
        "id": "zhihu_xiaohongshu",
        "name": "知乎/小红书爬虫规则",
        "urls": [
            "https://www.zhihu.com/robots.txt",
            "https://www.xiaohongshu.com/robots.txt",
        ],
        "keywords": ["爬虫", "索引", "收录", "规则", "Allow", "Disallow"],
        "category": "社媒平台",
        "check_interval_hours": 72,
    },
]

# 关键词告警匹配模式
ALERT_KEYWORD_PATTERN = re.compile(
    r"(抓取|索引|收录|权重|算法更新|排名|蜘蛛|爬虫|规则变更|内容生态|搜索规则|引用机制)",
    re.IGNORECASE
)


# ── 数据路径 ──

def _get_data_dir() -> Path:
    """获取RSS监控数据目录"""
    from app.utils.config import get_data_dir
    data_dir = get_data_dir() / "rss_monitor"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


# ── 内容哈希工具 ──

def _compute_content_hash(text: str) -> str:
    """计算内容的MD5哈希，用于变更检测"""
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()


def _compute_article_hash(article: dict) -> str:
    """计算单篇文章的联合标题+摘要哈希"""
    combined = f"{article.get('title', '')}|{article.get('snippet', '')}"
    return hashlib.md5(combined.encode("utf-8", errors="replace")).hexdigest()


# ── 信源检查间隔追踪 ──

def _get_source_tracker_path() -> Path:
    """获取信源检查追踪文件路径"""
    return _get_data_dir() / "_source_check_tracker.json"


def _get_last_check(source_id: str) -> str | None:
    """获取指定信源的上次检查时间戳"""
    tracker_file = _get_source_tracker_path()
    if not tracker_file.exists():
        return None
    try:
        with open(tracker_file, "r", encoding="utf-8") as f:
            tracker = json.load(f)
        return tracker.get(source_id)
    except Exception:
        return None


def _set_last_check(source_id: str, timestamp: str):
    """记录指定信源的检查时间戳"""
    tracker_file = _get_source_tracker_path()
    tracker = {}
    if tracker_file.exists():
        try:
            with open(tracker_file, "r", encoding="utf-8") as f:
                tracker = json.load(f)
        except Exception:
            pass
    tracker[source_id] = timestamp
    with open(tracker_file, "w", encoding="utf-8") as f:
        json.dump(tracker, f, ensure_ascii=False, indent=2)


def _should_check_source(source: dict) -> bool:
    """检查信源是否到了检查间隔"""
    interval_hours = source.get("check_interval_hours", 24)
    last_check = _get_last_check(source["id"])
    if last_check is None:
        return True
    try:
        last_dt = datetime.fromisoformat(last_check)
        elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
        return elapsed >= interval_hours
    except Exception:
        return True


def _load_previous_crawl_result(source_id: str) -> dict | None:
    """加载指定信源最近一次抓取结果（用于哈希对比）。

    回溯最近30天的抓取记录，找到包含该信源的最新结果。
    """
    data_dir = _get_data_dir()
    for i in range(1, 30):
        date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        result_file = data_dir / f"{date_str}.json"
        if result_file.exists():
            try:
                with open(result_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for r in data.get("results", []):
                    if r.get("source_id") == source_id:
                        return r
            except Exception:
                continue
    return None


# ── 抓取核心 ──

async def _fetch_url(url: str, timeout: int = 15) -> str | None:
    """抓取单个URL的文本内容"""
    try:
        import httpx
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text[:50000]  # 限制50KB
    except Exception as e:
        logger.debug(f"抓取失败 {url}: {e}")
        return None


def _extract_text_from_html(html: str) -> str:
    """从HTML提取纯文本"""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        # 移除script和style
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # 合并空白行
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)
    except Exception:
        # 简单正则清除HTML标签
        clean = re.sub(r"<[^>]+>", " ", html)
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()


def _extract_articles(text: str, source_keywords: list[str]) -> list[dict[str, Any]]:
    """从页面文本中提取与关键词相关的文章片段。

    Returns:
        [{title, snippet, matched_keywords, relevance_score}, ...]
    """
    articles = []
    # 按段落分割
    paragraphs = text.split("\n")
    for i, para in enumerate(paragraphs):
        if len(para) < 30:  # 跳过过短的段落
            continue
        matched = [kw for kw in source_keywords if kw in para]
        if not matched:
            # 检查告警关键词
            alert_matches = ALERT_KEYWORD_PATTERN.findall(para)
            if not alert_matches:
                continue
            matched = alert_matches

        # 使用前一行作为可能的标题
        title = paragraphs[i - 1] if i > 0 and len(paragraphs[i - 1]) < 100 else para[:80]
        articles.append({
            "title": title.strip()[:100],
            "snippet": para.strip()[:300],
            "matched_keywords": list(set(matched)),
            "relevance_score": len(matched) * 10,
            "position": i,
        })

    # 按相关性排序，取前20条
    articles.sort(key=lambda x: x["relevance_score"], reverse=True)
    return articles[:20]


async def check_source(source: dict) -> dict[str, Any]:
    """检查单个RSS信源。

    Returns:
        {
            "source_id": str,
            "source_name": str,
            "checked_at": str,
            "status": "ok" | "error" | "no_data",
            "articles_found": int,
            "alerts": [{title, snippet, matched_keywords, url}, ...],
            "error": str | None,
        }
    """
    logger.info(f"检查信源: {source['name']} ({source['id']})")
    result = {
        "source_id": source["id"],
        "source_name": source["name"],
        "category": source.get("category", ""),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "no_data",
        "articles_found": 0,
        "alerts": [],
        "error": None,
    }

    all_articles = []
    for url in source["urls"]:
        html = await _fetch_url(url)
        if html is None:
            continue
        text = _extract_text_from_html(html)
        if not text:
            continue
        articles = _extract_articles(text, source["keywords"])
        # 注入来源URL
        for a in articles:
            a["source_url"] = url
        all_articles.extend(articles)

    if all_articles:
        # 去重（按snippet相似度）
        seen = set()
        unique = []
        for a in all_articles:
            key = a["snippet"][:50]
            if key not in seen:
                seen.add(key)
                unique.append(a)
        result["articles_found"] = len(unique)
        result["alerts"] = unique[:15]  # 最多15条告警
        result["status"] = "ok"

        # ── 内容哈希对比（变更检测）──
        full_text = "\n".join(a["snippet"] for a in unique)
        result["content_hash"] = _compute_content_hash(full_text)
        result["hash_changed"] = False
        result["previous_hash"] = ""

        prev_result = _load_previous_crawl_result(source["id"])
        if prev_result:
            result["previous_hash"] = prev_result.get("content_hash", "")
            result["hash_changed"] = (result["content_hash"] != result["previous_hash"])
            if result["hash_changed"]:
                logger.info(
                    f"信源内容哈希变更: {source['id']} "
                    f"{result['previous_hash'][:8]} -> {result['content_hash'][:8]}"
                )
    elif html is None:
        result["status"] = "error"
        result["error"] = "所有URL抓取失败"
    else:
        result["status"] = "no_data"

    return result


async def run_daily_crawl(force: bool = False) -> dict[str, Any]:
    """执行每日全量RSS抓取（支持按信源间隔跳过）。

    Args:
        force: 如果为 True，强制检查所有信源（忽略间隔限制）

    Returns:
        {
            "run_id": str,
            "started_at": str,
            "completed_at": str,
            "total_sources": int,
            "sources_checked": int,
            "sources_skipped": int,
            "total_alerts": int,
            "results": [...],
        }
    """
    started_at = datetime.now(timezone.utc)
    run_id = f"rss_{started_at.strftime('%Y%m%d_%H%M%S')}"

    logger.info(f"开始RSS抓取 (run_id={run_id}, 信源数={len(RSS_SOURCES)}, force={force})")

    results = []
    skipped = 0
    for source in RSS_SOURCES:
        # 检查间隔（force 模式跳过）
        if not force and not _should_check_source(source):
            logger.debug(f"跳过信源 {source['id']}: 未到检查间隔")
            skipped += 1
            continue

        try:
            result = await check_source(source)
            _set_last_check(source["id"], datetime.now(timezone.utc).isoformat())
            results.append(result)
        except Exception as e:
            logger.error(f"信源检查异常 {source['id']}: {e}")
            results.append({
                "source_id": source["id"],
                "source_name": source["name"],
                "status": "error",
                "error": str(e),
                "articles_found": 0,
                "alerts": [],
            })

    total_alerts = sum(r.get("articles_found", 0) for r in results)

    summary = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "total_sources": len(RSS_SOURCES),
        "sources_checked": sum(1 for r in results if r.get("status") != "error"),
        "sources_skipped": skipped,
        "total_alerts": total_alerts,
        "results": results,
    }

    # 持久化
    data_dir = _get_data_dir()
    date_str = started_at.strftime("%Y-%m-%d")
    output_file = data_dir / f"{date_str}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info(f"每日RSS抓取完成: {total_alerts} 条告警 → {output_file}")
    return summary


def get_rss_results(date_str: str | None = None) -> dict | None:
    """获取指定日期的RSS抓取结果。

    Args:
        date_str: 日期字符串 YYYY-MM-DD，默认今天
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    data_dir = _get_data_dir()
    result_file = data_dir / f"{date_str}.json"
    if not result_file.exists():
        return None
    with open(result_file, "r", encoding="utf-8") as f:
        return json.load(f)


def list_rss_results(days: int = 7) -> list[dict[str, Any]]:
    """列出最近N天的RSS抓取摘要。

    Returns:
        [{date, file_exists, total_alerts, sources_checked}, ...]
    """
    data_dir = _get_data_dir()
    results = []
    for i in range(days):
        date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        result_file = data_dir / f"{date_str}.json"
        if result_file.exists():
            try:
                with open(result_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results.append({
                    "date": date_str,
                    "file_exists": True,
                    "total_alerts": data.get("total_alerts", 0),
                    "sources_checked": data.get("sources_checked", 0),
                })
            except Exception:
                results.append({"date": date_str, "file_exists": False, "total_alerts": 0, "sources_checked": 0})
        else:
            results.append({"date": date_str, "file_exists": False, "total_alerts": 0, "sources_checked": 0})
    return results


def get_keyword_alerts(hours: int = 24) -> list[dict[str, Any]]:
    """获取最近N小时内的关键词告警（3级分类）。

    告警等级：
    - major (重大): 算法更新、规则变更 → 触发适配流水线审核
    - moderate (中等): 索引、收录、权重变化 → 提醒运营人工确认
    - micro (微观): 抓取、爬虫、推荐、审核调整 → 自动更新YAML草稿

    hash_changed 为 True 时自动升级一级。
    """
    today_results = get_rss_results()
    if not today_results:
        return []

    # 关键词分级
    MAJOR_KW = {"算法更新", "规则变更"}
    MODERATE_KW = {"索引", "收录", "权重", "排名"}
    MICRO_KW = {"抓取", "蜘蛛", "爬虫", "推荐", "审核", "内容质量", "内容生态", "搜索规则", "引用机制"}

    alerts = []
    for source_result in today_results.get("results", []):
        hash_changed = source_result.get("hash_changed", False)
        for article in source_result.get("alerts", []):
            matched = set(article.get("matched_keywords", []))

            # 三级分类
            if matched & MAJOR_KW:
                tier = "major"
            elif matched & MODERATE_KW:
                tier = "moderate"
            else:
                tier = "micro"

            # 内容实际变化时升级一级
            if hash_changed and tier != "major":
                tier = "moderate" if tier == "micro" else "major"

            alerts.append({
                "source_name": source_result.get("source_name", ""),
                "source_id": source_result.get("source_id", ""),
                "title": article.get("title", ""),
                "snippet": article.get("snippet", ""),
                "matched_keywords": sorted(matched),
                "tier": tier,
                "tier_label": {"major": "重大", "moderate": "中等", "micro": "微观"}[tier],
                "hash_changed": hash_changed,
                "source_url": article.get("source_url", ""),
            })

    # 排序：重大 → 中等 → 微观
    tier_order = {"major": 0, "moderate": 1, "micro": 2}
    alerts.sort(key=lambda x: tier_order.get(x["tier"], 99))
    return alerts[:50]  # 最多50条


def get_hash_changes_since(days: int = 7) -> list[dict[str, Any]]:
    """获取最近N天内内容哈希发生变化的信源列表。

    供适配流水线使用：检测到哈希变化 → 可能意味着平台规则变动。

    Returns:
        [{source_id, source_name, date, content_hash, previous_hash, alerts_count}, ...]
    """
    data_dir = _get_data_dir()
    changes = []
    seen_sources = set()

    for i in range(days):
        date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        result_file = data_dir / f"{date_str}.json"
        if not result_file.exists():
            continue
        try:
            with open(result_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for r in data.get("results", []):
                sid = r.get("source_id", "")
                if sid in seen_sources:
                    continue
                if r.get("hash_changed"):
                    seen_sources.add(sid)
                    changes.append({
                        "source_id": sid,
                        "source_name": r.get("source_name", ""),
                        "date": date_str,
                        "content_hash": r.get("content_hash", ""),
                        "previous_hash": r.get("previous_hash", ""),
                        "alerts_count": r.get("articles_found", 0),
                    })
        except Exception:
            continue

    return changes
