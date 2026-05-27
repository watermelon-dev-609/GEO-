"""数据报表生成器 — 雷达图/柱状图/诊断卡片/PDF导出"""

from __future__ import annotations
import os
import logging
import uuid
from pathlib import Path
from datetime import datetime
import json

from app.utils.config import get_data_dir

logger = logging.getLogger(__name__)

# 设置中文字体
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 尝试设置中文字体
_ZH_FONT = None
for font_name in ["SimHei", "Microsoft YaHei", "WenQuanYi Micro Hei", "Noto Sans CJK SC", "DejaVu Sans"]:
    try:
        fm.findfont(font_name, fallback_to_default=False)
        _ZH_FONT = font_name
        break
    except Exception:
        continue

if _ZH_FONT:
    plt.rcParams["font.family"] = _ZH_FONT
plt.rcParams["axes.unicode_minus"] = False

import numpy as np


RADAR_DIMENSIONS = [
    ("core_advantage", "核心优势"),
    ("scene_adaptation", "场景适配"),
    ("technical_depth", "技术深度"),
    ("service_completeness", "服务完整性"),
    ("credibility", "落地可信度"),
    ("ai_friendliness", "AI友好度"),
]


class ReportGenerator:
    """数据报表生成器"""

    def __init__(self):
        self.output_dir = get_data_dir() / "reports"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.chart_dir = self.output_dir / "charts"
        self.chart_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        evaluation_data: dict,
        output_format: str = "html",
        include_charts: bool = True,
    ) -> dict:
        """生成完整报表"""
        report_id = str(uuid.uuid4())[:8]

        chart_paths = {}
        if include_charts:
            chart_paths = self._generate_charts(evaluation_data, report_id)

        if output_format == "html":
            file_path = self._render_html(evaluation_data, chart_paths, report_id)
        elif output_format == "pdf":
            file_path = self._render_pdf(evaluation_data, chart_paths, report_id)
        else:
            file_path = self._render_json(evaluation_data, report_id)

        return {
            "report_id": report_id,
            "format": output_format,
            "file_path": str(file_path),
            "created_at": datetime.now().isoformat(),
            "chart_paths": chart_paths,
        }

    def _generate_charts(self, data: dict, report_id: str) -> dict:
        """生成图表"""
        paths = {}

        # 1. 雷达图
        radar_path = self._radar_chart(data, report_id)
        if radar_path:
            paths["radar"] = str(radar_path)

        # 2. 柱状图（平台对比）
        bar_path = self._bar_chart(data, report_id)
        if bar_path:
            paths["bar"] = str(bar_path)

        return paths

    def _radar_chart(self, data: dict, report_id: str) -> Path | None:
        """生成六维雷达图"""
        try:
            dim_labels = [d[1] for d in RADAR_DIMENSIONS]
            N = len(dim_labels)

            # 提取评测分数（从platform_results中推算六维分数）
            overall = data.get("overall_score", 0)
            comparison = data.get("before_after_comparison", {})

            # 以 overall 为基准，各维度用实际评分覆盖
            after_scores = [overall] * N
            # 确保分数合理分布
            platform_results = data.get("platform_results", [])
            if platform_results:
                for pr in platform_results:
                    for score_obj in pr.get("scores", []):
                        dim = score_obj.get("dimension", "")
                        val = score_obj.get("score", 0)
                        # 将三维评分映射到六维
                        for i, (dk, dl) in enumerate(RADAR_DIMENSIONS):
                            if dim == "brand_recall" and dk in ["core_advantage", "credibility"]:
                                after_scores[i] = max(after_scores[i], val)
                            elif dim == "solution_match" and dk in ["scene_adaptation", "ai_friendliness"]:
                                after_scores[i] = max(after_scores[i], val)
                            elif dim == "advantage_citation" and dk in ["technical_depth", "service_completeness"]:
                                after_scores[i] = max(after_scores[i], val)

            # 优化前分数（如果有对比数据）
            before_mult = comparison.get("before_score", 0) / max(comparison.get("after_score", 1), 1)
            before_scores = [s * before_mult for s in after_scores]

            angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
            after_scores += after_scores[:1]
            before_scores += before_scores[:1]
            angles += angles[:1]

            fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
            ax.fill(angles, after_scores, alpha=0.25, color="#409EFF", label="优化后")
            ax.plot(angles, after_scores, color="#409EFF", linewidth=2)
            if comparison:
                ax.fill(angles, before_scores, alpha=0.15, color="#909399", label="优化前")
                ax.plot(angles, before_scores, color="#909399", linewidth=1.5, linestyle="--")

            ax.set_xticks(angles[:-1])
            ax.set_xticklabels(dim_labels, fontsize=11)
            ax.set_ylim(0, 100)
            ax.set_yticks([20, 40, 60, 80, 100])
            ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=8)
            ax.set_title("GEO优化效果雷达图", fontsize=14, fontweight="bold", pad=20)
            ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))

            path = self.chart_dir / f"{report_id}_radar.png"
            plt.savefig(path, dpi=150, bbox_inches="tight", transparent=False)
            plt.close(fig)
            return path
        except Exception as e:
            logger.warning(f"雷达图生成失败: {e}")
            return None

    def _bar_chart(self, data: dict, report_id: str) -> Path | None:
        """生成平台对比柱状图"""
        try:
            platform_results = data.get("platform_results", [])
            if not platform_results:
                return None

            platforms = []
            scores = []
            for pr in platform_results:
                plat_name = pr.get("platform", "unknown")
                overall = pr.get("overall_score", 0)
                platforms.append(plat_name)
                scores.append(overall)

            fig, ax = plt.subplots(figsize=(10, 6))
            colors = ["#409EFF", "#67C23A", "#E6A23C", "#F56C6C", "#909399", "#B37FEB", "#36CFC9"][:len(platforms)]
            bars = ax.bar(range(len(platforms)), scores, color=colors, width=0.6, edgecolor="white")

            for bar, score in zip(bars, scores):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                        f"{score:.1f}", ha="center", va="bottom", fontsize=11, fontweight="bold")

            ax.set_xticks(range(len(platforms)))
            ax.set_xticklabels(platforms, fontsize=10)
            ax.set_ylim(0, 105)
            ax.set_ylabel("综合评分", fontsize=11)
            ax.set_title("各AI平台采信评分对比", fontsize=14, fontweight="bold")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)

            path = self.chart_dir / f"{report_id}_bar.png"
            plt.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            return path
        except Exception as e:
            logger.warning(f"柱状图生成失败: {e}")
            return None

    def _render_html(self, data: dict, chart_paths: dict, report_id: str) -> Path:
        """生成HTML报表"""
        overall = data.get("overall_score", 0)
        comparison = data.get("before_after_comparison", {})
        weak_points = data.get("weak_points", [])
        suggestions = data.get("suggestions", [])
        platform_results = data.get("platform_results", [])

        # 雷达图Base64嵌入
        radar_b64 = ""
        if "radar" in chart_paths:
            import base64
            with open(chart_paths["radar"], "rb") as f:
                radar_b64 = base64.b64encode(f.read()).decode()

        bar_b64 = ""
        if "bar" in chart_paths:
            import base64
            with open(chart_paths["bar"], "rb") as f:
                bar_b64 = base64.b64encode(f.read()).decode()

        improvement_html = ""
        if comparison:
            imp = comparison.get("improvement_percent", 0)
            color = "#67C23A" if imp > 0 else "#F56C6C"
            improvement_html = f"""
            <div class="comparison">
                <h3>优化前后对比</h3>
                <div class="score-row">
                    <span>优化前：{comparison.get('before_score', 0)}分</span>
                    <span>→</span>
                    <span>优化后：{comparison.get('after_score', 0)}分</span>
                    <span style="color:{color};font-weight:bold;">提升 {imp}%</span>
                </div>
            </div>"""

        platform_rows = ""
        for pr in platform_results:
            plat = pr.get("platform", "")
            score = pr.get("overall_score", 0)
            color = "#67C23A" if score >= 80 else ("#E6A23C" if score >= 60 else "#F56C6C")
            dim_scores = " | ".join(
                f"{s.get('dimension','')}: {s.get('score',0)}分"
                for s in pr.get("scores", [])
            )
            platform_rows += f"""
            <tr>
                <td>{plat}</td>
                <td style="color:{color};font-weight:bold;font-size:18px;">{score}</td>
                <td style="font-size:12px;">{dim_scores}</td>
            </tr>"""

        weak_items = "".join(f"<li>{w}</li>" for w in weak_points) if weak_points else "<li>暂无明显短板</li>"
        sug_items = "".join(f"<li>{s}</li>" for s in suggestions) if suggestions else ""

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GEO优化评测报告 - {report_id}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: "Microsoft YaHei", "SimHei", sans-serif; background: #f5f7fa; color: #303133; line-height: 1.6; }}
.container {{ max-width: 960px; margin: 0 auto; padding: 24px; }}
.header {{ background: linear-gradient(135deg, #409EFF, #337ECC); color: white; padding: 32px; border-radius: 12px; margin-bottom: 24px; }}
.header h1 {{ font-size: 24px; margin-bottom: 8px; }}
.header .meta {{ font-size: 14px; opacity: 0.85; }}
.card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); }}
.card h3 {{ font-size: 18px; margin-bottom: 16px; color: #303133; border-bottom: 2px solid #409EFF; padding-bottom: 8px; display: inline-block; }}
.overall-score {{ text-align: center; padding: 32px; }}
.overall-score .number {{ font-size: 64px; font-weight: bold; color: #409EFF; }}
.overall-score .label {{ font-size: 16px; color: #909399; }}
.score-row {{ display: flex; gap: 16px; align-items: center; font-size: 18px; padding: 12px 0; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid #ebeef5; }}
th {{ background: #f5f7fa; font-weight: 600; }}
.chart-container {{ text-align: center; margin: 16px 0; }}
.chart-container img {{ max-width: 100%; border-radius: 8px; }}
ul {{ padding-left: 20px; }}
li {{ margin: 8px 0; }}
.footer {{ text-align: center; color: #909399; font-size: 12px; padding: 24px; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>GEO生成式搜索优化评测报告</h1>
        <div class="meta">
            <p>服务主体：武汉微艺达智能科技有限公司</p>
            <p>报告编号：{report_id} | 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>

    <div class="card overall-score">
        <div class="number">{overall}</div>
        <div class="label">综合评分 / 100</div>
    </div>

    {improvement_html}

    <div class="card">
        <h3>六维雷达图</h3>
        <div class="chart-container">{'<img src="data:image/png;base64,' + radar_b64 + '" />' if radar_b64 else '<p>图表生成失败</p>'}</div>
    </div>

    <div class="card">
        <h3>各平台AI采信评分对比</h3>
        <table>
            <thead><tr><th>AI平台</th><th>综合评分</th><th>详细维度</th></tr></thead>
            <tbody>{platform_rows}</tbody>
        </table>
        {('<div class="chart-container"><img src="data:image/png;base64,' + bar_b64 + '" /></div>') if bar_b64 else ''}
    </div>

    <div class="card">
        <h3>内容短板诊断</h3>
        <ul>{weak_items}</ul>
    </div>

    <div class="card">
        <h3>迭代优化建议</h3>
        <ul>{sug_items}</ul>
    </div>

    <div class="footer">
        <p>本报告由GEO生成式搜索优化系统自动生成 | 武汉微艺达智能科技有限公司</p>
        <p>纯白帽合规优化 · 全平台AI采信适配</p>
    </div>
</div>
</body>
</html>"""

        path = self.output_dir / f"{report_id}.html"
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path

    def _render_pdf(self, data: dict, chart_paths: dict, report_id: str) -> Path:
        """生成PDF报表（先HTML再转PDF）"""
        html_path = self._render_html(data, chart_paths, report_id)
        pdf_path = self.output_dir / f"{report_id}.pdf"

        try:
            from weasyprint import HTML
            HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        except ImportError:
            logger.warning("weasyprint未安装，无法生成PDF，请使用HTML格式")
        except Exception as e:
            logger.warning(f"PDF生成失败: {e}")

        return pdf_path

    def _render_json(self, data: dict, report_id: str) -> Path:
        """生成JSON报表"""
        path = self.output_dir / f"{report_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
