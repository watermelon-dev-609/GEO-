"""自动报表生成 — 周报/月报"""

from __future__ import annotations
import json
import time
from pathlib import Path
from app.utils.config import load_settings, get_enterprise_name


def _get_output_dir() -> Path:
    settings = load_settings()
    data_dir = settings.get("system", {}).get("data_dir", "./data")
    base = Path(data_dir)
    if not base.is_absolute():
        base = Path(__file__).resolve().parent.parent.parent / data_dir
    out = base / "reports"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _collect_stats(days: int) -> dict:
    """收集指定天数内的统计数据"""
    settings = load_settings()
    data_dir = settings.get("system", {}).get("data_dir", "./data")
    base = Path(data_dir)
    if not base.is_absolute():
        base = Path(__file__).resolve().parent.parent.parent / data_dir

    evals = base / "evaluations"
    usage = base / "usage"
    monitor = base / "brand_mentions" / "sessions"

    eval_count = len(list(evals.glob("*.json"))) if evals.exists() else 0
    usage_files = sorted(usage.glob("*.json")) if usage.exists() else []
    recent_usage = []
    cutoff = time.time() - days * 86400
    for uf in usage_files:
        try:
            ft = uf.stat().st_mtime
            if ft < cutoff:
                continue
            with open(uf, "r", encoding="utf-8") as f:
                data = json.load(f)
                recent_usage.append({
                    "date": uf.stem,
                    "calls": len(data) if isinstance(data, list) else 0,
                })
        except Exception:
            pass

    session_files = sorted(monitor.glob("*.json")) if monitor.exists() else []
    monitor_sessions = []
    for sf in session_files[-10:]:
        try:
            with open(sf, "r", encoding="utf-8") as f:
                data = json.load(f)
                monitor_sessions.append({
                    "date": sf.stem[:10],
                    "mention_rate": data.get("mention_rate", 0) if isinstance(data, dict) else 0,
                })
        except Exception:
            pass

    return {
        "eval_count": eval_count,
        "usage_recent": recent_usage,
        "monitor_sessions": monitor_sessions,
        "total_api_calls": sum(u["calls"] for u in recent_usage),
        "traffic_summary": _collect_traffic_stats(days),
        "conversion_summary": _collect_conversion_stats(days),
    }


def _collect_traffic_stats(days: int) -> dict:
    """收集流量统计数据"""
    try:
        from app.core.traffic_connector import get_traffic_summary
        return get_traffic_summary(days=days)
    except Exception:
        return {"total_page_views": 0, "total_visitors": 0, "ai_referral_visits": 0}


def _collect_conversion_stats(days: int) -> dict:
    """收集转化统计数据"""
    try:
        from app.core.conversion_attribution import get_attribution
        return get_attribution(days=days)
    except Exception:
        return {"total_conversions": 0, "ai_attributed_count": 0, "total_value": 0.0}


async def generate_weekly_report() -> str:
    """生成周报"""
    stats = _collect_stats(7)
    enterprise = get_enterprise_name()
    now = time.strftime("%Y-%m-%d %H:%M")
    week_ago = time.strftime("%Y-%m-%d", time.localtime(time.time() - 7 * 86400))

    traffic = stats.get("traffic_summary", {})
    conv = stats.get("conversion_summary", {})

    md = f"""# {enterprise} GEO运营周报

> 报告周期: {week_ago} ~ {now.split()[0]}
> 生成时间: {now}

## 一、AI收录监测

| 指标 | 数值 |
|------|------|
| 监测会话数 | {len(stats['monitor_sessions'])} |
| API总调用次数 | {stats['total_api_calls']} |

## 二、网站流量

| 指标 | 数值 |
|------|------|
| 页面浏览量(PV) | {traffic.get('total_page_views', 0)} |
| 独立访客(UV) | {traffic.get('total_visitors', 0)} |
| AI来源访问 | {traffic.get('ai_referral_visits', 0)} |

## 三、转化追踪

| 指标 | 数值 |
|------|------|
| 总转化数 | {conv.get('total_conversions', 0)} |
| AI归因转化 | {conv.get('ai_attributed_count', 0)} |
| AI转化占比 | {conv.get('ai_citation_rate_pct', 0)}% |
| 转化总价值 | ¥{conv.get('total_value', 0):,.0f} |

## 四、本周总结

- 累计评测次数: {stats['eval_count']}
- API调用: {stats['total_api_calls']} 次
- AI引荐流量: {traffic.get('ai_referral_visits', 0)} 次访问
- AI归因转化: {conv.get('ai_attributed_count', 0)} 次

## 五、下周建议

1. 针对收录率较低的平台进行针对性优化
2. 更新关键词库，补充近期热门行业词
3. 检查平台规则变化，及时调整优化策略
4. 对比流量与转化趋势，优先优化高曝光低转化平台
"""
    filepath = _get_output_dir() / f"weekly_report_{time.strftime('%Y%m%d')}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)
    return str(filepath)


async def generate_monthly_report() -> str:
    """生成月报"""
    stats = _collect_stats(30)
    enterprise = get_enterprise_name()
    now = time.strftime("%Y-%m-%d %H:%M")
    month_ago = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))

    traffic = stats.get("traffic_summary", {})
    conv = stats.get("conversion_summary", {})

    md = f"""# {enterprise} GEO运营月报

> 报告周期: {month_ago} ~ {now.split()[0]}
> 生成时间: {now}

## 一、月度AI收录概览

| 指标 | 数值 |
|------|------|
| 累计评测次数 | {stats['eval_count']} |
| API总调用 | {stats['total_api_calls']} 次 |

## 二、月度网站流量

| 指标 | 数值 |
|------|------|
| 页面浏览量(PV) | {traffic.get('total_page_views', 0)} |
| 独立访客(UV) | {traffic.get('total_visitors', 0)} |
| 会话数 | {traffic.get('total_sessions', 0)} |
| AI来源访问 | {traffic.get('ai_referral_visits', 0)} |
| 跳出率 | {traffic.get('avg_bounce_rate_pct', 0)}% |

## 三、月度转化归因

| 指标 | 数值 |
|------|------|
| 总转化数 | {conv.get('total_conversions', 0)} |
| AI归因转化 | {conv.get('ai_attributed_count', 0)} |
| AI转化占比 | {conv.get('ai_citation_rate_pct', 0)}% |
| 转化总价值 | ¥{conv.get('total_value', 0):,.0f} |

### 按AI平台转化分布
{_render_platform_conv_table(conv)}

### 按来源转化分布
{_render_source_conv_table(conv)}

## 四、月度趋势分析

本月API调用量: {stats['total_api_calls']} 次
AI引荐流量: {traffic.get('ai_referral_visits', 0)} 次访问
AI归因转化: {conv.get('ai_attributed_count', 0)} 次

## 五、下月优化建议

1. 持续监测重点平台的收录率变化
2. 扩展竞品分析范围，更新差异化策略
3. 根据月度数据调整关键词权重
4. 分析AI转化漏斗，定位流失环节并优化
"""
    filepath = _get_output_dir() / f"monthly_report_{time.strftime('%Y%m')}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)
    return str(filepath)


def _render_platform_conv_table(conv: dict) -> str:
    """渲染按AI平台转化分布表格"""
    by_platform = conv.get("by_ai_platform", {})
    if not by_platform:
        return "暂无数据"
    rows = []
    for plat, count in sorted(by_platform.items(), key=lambda x: x[1], reverse=True):
        rows.append(f"| {plat} | {count} |")
    return "| 平台 | 转化数 |\n|------|--------|\n" + "\n".join(rows)


def _render_source_conv_table(conv: dict) -> str:
    """渲染按来源转化分布表格"""
    by_source = conv.get("by_source", {})
    if not by_source:
        return "暂无数据"
    rows = []
    for src, count in sorted(by_source.items(), key=lambda x: x[1], reverse=True):
        rows.append(f"| {src} | {count} |")
    return "| 来源 | 转化数 |\n|------|--------|\n" + "\n".join(rows)
