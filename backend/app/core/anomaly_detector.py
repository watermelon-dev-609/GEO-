"""异常检测器 — 收录率突变/评测分数波动/API异常检测"""

from __future__ import annotations
import json
import logging
import time
from pathlib import Path

from app.utils.config import load_settings

logger = logging.getLogger(__name__)


def _get_data_dirs() -> tuple[Path, Path]:
    settings = load_settings()
    data_dir = settings.get("system", {}).get("data_dir", "./data")
    base = Path(data_dir)
    if not base.is_absolute():
        base = Path(__file__).resolve().parent.parent.parent / data_dir
    return base / "brand_mentions" / "sessions", base / "usage"


def detect_anomalies() -> list[dict]:
    """检测所有异常并返回告警列表"""
    alerts = []
    alerts.extend(_detect_mention_rate_drop())
    alerts.extend(_detect_api_spike())
    return alerts


def _detect_mention_rate_drop(threshold_pct: float = 30) -> list[dict]:
    """检测收录率突变（下降超过阈值）"""
    alerts = []
    sessions_dir, _ = _get_data_dirs()
    if not sessions_dir.exists():
        return alerts

    session_files = sorted(sessions_dir.glob("*.json"))
    if len(session_files) < 2:
        return alerts

    try:
        current = _load_session(session_files[-1])
        previous = _load_session(session_files[-2])
        if current["rate"] is None or previous["rate"] is None:
            return alerts
        drop = previous["rate"] - current["rate"]
        if drop > threshold_pct:
            alerts.append({
                "type": "mention_rate_drop",
                "level": "warning",
                "message": f"品牌收录率下降 {drop:.1f}%（{previous['rate']:.1f}% → {current['rate']:.1f}%）",
                "detected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "detail": {"previous_rate": previous["rate"], "current_rate": current["rate"], "drop": drop},
            })
    except Exception as e:
        logger.warning(f"收录率异常检测失败: {e}")
    return alerts


def _detect_api_spike(threshold_multiplier: float = 5) -> list[dict]:
    """检测API调用异常增长（比前日均值高5倍）"""
    alerts = []
    _, usage_dir = _get_data_dirs()
    if not usage_dir.exists():
        return alerts

    usage_files = sorted(usage_dir.glob("*.json"))
    if len(usage_files) < 3:
        return alerts

    try:
        today_calls = _count_calls(usage_files[-1])
        historical = [_count_calls(uf) for uf in usage_files[-7:-1]]
        avg = sum(historical) / max(1, len(historical))
        if avg > 0 and today_calls > avg * threshold_multiplier:
            alerts.append({
                "type": "api_usage_spike",
                "level": "warning",
                "message": f"API调用量异常增长: 今日 {today_calls} 次（近7日均值 {avg:.0f} 次）",
                "detected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "detail": {"today_calls": today_calls, "avg_7d": round(avg, 1)},
            })
    except Exception as e:
        logger.warning(f"API异常检测失败: {e}")
    return alerts


def _load_session(filepath: Path) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        rate = data.get("mention_rate")
        if rate is not None:
            rate = float(rate)
        return {"rate": rate}
    return {"rate": None}


def _count_calls(filepath: Path) -> int:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return len(data) if isinstance(data, list) else 0
