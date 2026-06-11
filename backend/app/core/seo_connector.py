"""SEO数据导入器 — 百度站长平台 / Google Search Console 数据解析与联合分析"""

from __future__ import annotations
import csv
import io
import json
import logging
import time
from pathlib import Path

from app.utils.config import load_settings

logger = logging.getLogger(__name__)


def _get_seo_dir() -> Path:
    settings = load_settings()
    data_dir = settings.get("system", {}).get("data_dir", "./data")
    base = Path(data_dir)
    if not base.is_absolute():
        base = Path(__file__).resolve().parent.parent.parent / data_dir
    sdir = base / "seo"
    sdir.mkdir(parents=True, exist_ok=True)
    return sdir


class SEODataImporter:
    """SEO数据导入与联合分析"""

    @staticmethod
    def import_csv(file_content: str, source: str = "baidu") -> dict:
        """导入CSV格式的SEO关键词数据"""
        reader = csv.DictReader(io.StringIO(file_content))
        keywords = []
        for row in reader:
            keywords.append({
                "keyword": row.get("keyword") or row.get("关键词") or row.get("query", ""),
                "clicks": int(row.get("clicks") or row.get("点击量") or row.get("点击", 0)),
                "impressions": int(row.get("impressions") or row.get("展示量") or row.get("展示", 0)),
                "ctr": float(row.get("ctr") or row.get("点击率", 0)),
                "position": float(row.get("position") or row.get("排名") or row.get("平均排名", 0)),
                "source": source,
            })

        # 保存导入数据
        filename = f"seo_import_{source}_{time.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = _get_seo_dir() / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"source": source, "imported_at": time.strftime("%Y-%m-%d %H:%M:%S"), "keywords": keywords}, f, ensure_ascii=False, indent=2)

        return {
            "file": filename,
            "source": source,
            "keyword_count": len(keywords),
            "top_keywords": sorted(keywords, key=lambda k: k["position"])[:10],
        }

    @staticmethod
    def get_analysis() -> dict:
        """GEO+SEO联合分析"""
        seo_dir = _get_seo_dir()
        imports = sorted(seo_dir.glob("seo_import_*.json"))
        if not imports:
            return {"status": "empty", "message": "暂无SEO数据，请先导入"}

        all_keywords = []
        for fp in imports:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
                all_keywords.extend(data.get("keywords", []))

        # 排名分布
        top3 = [k for k in all_keywords if k["position"] <= 3]
        top10 = [k for k in all_keywords if k["position"] <= 10]
        top30 = [k for k in all_keywords if k["position"] <= 30]

        # 高流量低排名（优化机会）
        high_opportunity = sorted(
            [k for k in all_keywords if k["position"] > 10 and k["impressions"] > 100],
            key=lambda k: k["impressions"],
            reverse=True,
        )[:20]

        return {
            "status": "ok",
            "total_keywords": len(all_keywords),
            "rank_distribution": {
                "top3_count": len(top3),
                "top10_count": len(top10),
                "top30_count": len(top30),
                "top3_pct": round(len(top3) / max(1, len(all_keywords)) * 100, 1),
                "top10_pct": round(len(top10) / max(1, len(all_keywords)) * 100, 1),
            },
            "avg_ctr": round(sum(k["ctr"] for k in all_keywords) / max(1, len(all_keywords)), 2),
            "avg_position": round(sum(k["position"] for k in all_keywords) / max(1, len(all_keywords)), 1),
            "high_opportunity": high_opportunity,
            "sources": list(set(k.get("source", "") for k in all_keywords)),
        }
