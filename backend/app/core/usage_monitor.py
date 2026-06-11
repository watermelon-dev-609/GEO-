"""API用量监控 — 调用次数/token估算/费用估算 + 配额告警"""

from __future__ import annotations
import json
import logging
import time
import threading
from pathlib import Path
from dataclasses import dataclass, field

from app.utils.config import load_settings

logger = logging.getLogger(__name__)

# 各平台 token 费用估算（每 1K tokens，人民币）
PLATFORM_COST_PER_1K = {
    "deepseek": {"input": 0.001, "output": 0.002},
    "tongyi": {"input": 0.02, "output": 0.06},
    "wenxin": {"input": 0.008, "output": 0.008},
    "doubao": {"input": 0.003, "output": 0.006},
    "kimi": {"input": 0.012, "output": 0.012},
    "yuanbao": {"input": 0.01, "output": 0.01},
    "xinghuo": {"input": 0.0015, "output": 0.0015},
}


@dataclass
class UsageRecord:
    timestamp: str
    platform: str
    action: str        # clean / rewrite / evaluate / check
    estimated_tokens: int
    estimated_cost: float


class UsageMonitor:
    """API用量监控器（单例）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._records: list[UsageRecord] = []
        self._write_lock = threading.Lock()
        self._data_dir = self._get_data_dir()

    @staticmethod
    def _get_data_dir() -> Path:
        settings = load_settings()
        data_dir = settings.get("system", {}).get("data_dir", "./data")
        path = Path(data_dir)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent.parent / data_dir
        usage_dir = path / "usage"
        usage_dir.mkdir(parents=True, exist_ok=True)
        return usage_dir

    def _today_file(self) -> Path:
        today = time.strftime("%Y-%m-%d")
        return self._data_dir / f"{today}.json"

    def record(self, platform: str, action: str, estimated_tokens: int = 500):
        """记录一次API调用"""
        cost_rate = PLATFORM_COST_PER_1K.get(platform, {"input": 0.001, "output": 0.002})
        avg_cost = (cost_rate["input"] + cost_rate["output"]) / 2
        estimated_cost = (estimated_tokens / 1000) * avg_cost

        record = UsageRecord(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            platform=platform,
            action=action,
            estimated_tokens=estimated_tokens,
            estimated_cost=round(estimated_cost, 6),
        )
        self._records.append(record)
        self._persist()

    def _persist(self):
        """持久化到当日文件"""
        try:
            filepath = self._today_file()
            existing = []
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            existing.append({
                "timestamp": self._records[-1].timestamp,
                "platform": self._records[-1].platform,
                "action": self._records[-1].action,
                "estimated_tokens": self._records[-1].estimated_tokens,
                "estimated_cost": self._records[-1].estimated_cost,
            })
            import tempfile
            import os
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json",
                                              delete=False, dir=self._data_dir) as tmp:
                json.dump(existing, tmp, ensure_ascii=False, indent=2)
                tmp_path = tmp.name
            os.replace(tmp_path, str(filepath))
        except Exception as e:
            logger.warning(f"用量记录持久化失败: {e}")

    def get_summary(self, date: str | None = None) -> dict:
        """获取用量摘要"""
        if date is None:
            date = time.strftime("%Y-%m-%d")
        filepath = self._data_dir / f"{date}.json"
        if not filepath.exists():
            return {"date": date, "total_calls": 0, "estimated_tokens": 0, "estimated_cost": 0, "by_platform": {}}

        with open(filepath, "r", encoding="utf-8") as f:
            records = json.load(f)

        by_platform = {}
        total_tokens = 0
        total_cost = 0
        for r in records:
            plat = r["platform"]
            if plat not in by_platform:
                by_platform[plat] = {"calls": 0, "tokens": 0, "cost": 0}
            by_platform[plat]["calls"] += 1
            by_platform[plat]["tokens"] += r["estimated_tokens"]
            by_platform[plat]["cost"] += r["estimated_cost"]
            total_tokens += r["estimated_tokens"]
            total_cost += r["estimated_cost"]

        return {
            "date": date,
            "total_calls": len(records),
            "estimated_tokens": total_tokens,
            "estimated_cost": round(total_cost, 4),
            "by_platform": by_platform,
        }

    def get_history(self, days: int = 7) -> list[dict]:
        """获取历史用量趋势"""
        results = []
        for i in range(days - 1, -1, -1):
            date = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400))
            results.append(self.get_summary(date))
        return results

    def check_quota(self) -> dict:
        """检查配额状态"""
        settings = load_settings()
        limits = settings.get("usage_limits", {})
        if not limits:
            return {"status": "ok", "alerts": []}

        summary = self.get_summary()
        daily_limit = limits.get("daily_calls", 1000)
        monthly_limit = limits.get("monthly_cost", 100.0)
        warn_pct = limits.get("warn_threshold", 80) / 100
        crit_pct = limits.get("critical_threshold", 95) / 100

        alerts = []
        if summary["total_calls"] >= daily_limit * crit_pct:
            alerts.append({"level": "critical", "message": f"今日API调用已达上限的{int(crit_pct * 100)}%", "triggered_at": time.strftime("%Y-%m-%d %H:%M:%S"), "threshold_pct": crit_pct})
        elif summary["total_calls"] >= daily_limit * warn_pct:
            alerts.append({"level": "warning", "message": f"今日API调用已达上限的{int(warn_pct * 100)}%", "triggered_at": time.strftime("%Y-%m-%d %H:%M:%S"), "threshold_pct": warn_pct})

        # 月度费用检查
        month_cost = 0
        for i in range(30):
            date = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400))
            s = self.get_summary(date)
            month_cost += s["estimated_cost"]
        if month_cost >= monthly_limit * crit_pct:
            alerts.append({"level": "critical", "message": f"月度费用已达预算的{int(crit_pct * 100)}%", "triggered_at": time.strftime("%Y-%m-%d %H:%M:%S"), "threshold_pct": crit_pct})

        return {
            "status": "critical" if any(a["level"] == "critical" for a in alerts) else ("warning" if alerts else "ok"),
            "alerts": alerts,
            "quota_remaining": {
                "daily_calls": max(0, daily_limit - summary["total_calls"]),
                "monthly_cost": round(max(0, monthly_limit - month_cost), 2),
            },
        }
