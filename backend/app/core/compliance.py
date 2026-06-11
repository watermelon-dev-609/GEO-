"""合规检测引擎 — 广告法禁词检测 + 行业敏感词过滤"""

from __future__ import annotations
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 广告法禁词库
AD_LAW_FORBIDDEN = {
    "绝对化用语": [
        "最", "第一", "唯一", "独家", "首个", "首创", "首选", "顶级", "极品",
        "最佳", "最好", "最大", "最高", "最低", "最强", "最优", "领先",
        "冠军", "王牌", "王者", "第一品牌", "第一选择", "独一无二",
        "全网第一", "全国第一", "行业第一", "销量第一",
    ],
    "虚假承诺": [
        "100%", "百分百", "绝对", "肯定", "保证", "确保", "必定", "一定",
        "永不", "永久", "终身", "彻底", "完全", "根治",
    ],
    "国家级表述": [
        "国家级", "世界级", "全球级", "国际级", "全国级", "中国级",
        "国家重点", "国家免检", "国家认证", "国家专利",
    ],
    "权威背书": [
        "政府推荐", "机关指定", "政府采购", "军队特供",
        "央视推荐", "人民大会堂", "中南海",
    ],
    "金融诱导": [
        "零风险", "稳赚", "保本", "无风险", "高回报",
        "收益翻倍", "只赚不赔",
    ],
    "时间限定": [
        "最后一天", "仅此一次", "绝版", "限量", "限时",
    ],
}


@dataclass
class Violation:
    word: str
    category: str
    position: int  # 字符位置
    context: str   # 上下文片段


@dataclass
class ComplianceReport:
    passed: bool
    violation_count: int
    violations: list[dict] = field(default_factory=list)
    risk_level: str = "none"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "violation_count": self.violation_count,
            "violations": self.violations,
            "risk_level": self.risk_level,
        }


class ComplianceChecker:
    """内容合规检测器"""

    def __init__(self, custom_blacklist: list[str] | None = None):
        self.forbidden_words = dict(AD_LAW_FORBIDDEN)
        if custom_blacklist:
            self.forbidden_words["自定义"] = custom_blacklist

    def check(self, text: str) -> ComplianceReport:
        violations = []
        covered_positions: set[tuple[int, int]] = set()

        for category, words in self.forbidden_words.items():
            # Sort longest first to avoid substring double-counting
            # e.g., "最好" (2-char) matched before "最" (1-char) at same position
            for word in sorted(words, key=len, reverse=True):
                for match in re.finditer(re.escape(word), text):
                    span = (match.start(), match.end())
                    # Skip if this position is already covered by a longer match
                    if any(
                        covered_start <= span[0] and span[1] <= covered_end
                        for covered_start, covered_end in covered_positions
                    ):
                        continue
                    covered_positions.add(span)

                    start_ctx = max(0, match.start() - 10)
                    end_ctx = min(len(text), match.end() + 10)
                    context = text[start_ctx:end_ctx]
                    violations.append({
                        "word": word,
                        "category": category,
                        "position": match.start(),
                        "context": f"...{context}...",
                        "suggestion": self._get_suggestion(category, word),
                    })

        count = len(violations)
        risk = "none"
        if count > 0:
            risk = "low"
        if count >= 3:
            risk = "medium"
        if count >= 8:
            risk = "high"

        return ComplianceReport(
            passed=count == 0,
            violation_count=count,
            violations=violations,
            risk_level=risk,
        )

    def check_quick(self, text: str) -> bool:
        """快速检测是否通过（不返回详情）"""
        for category, words in self.forbidden_words.items():
            for word in words:
                if word in text:
                    return False
        return True

    @staticmethod
    def _get_suggestion(category: str, word: str) -> str:
        suggestions = {
            "绝对化用语": f'建议将"{word}"替换为客观描述，如"具有竞争力""市场认可"',
            "虚假承诺": f'建议删除"{word}"或改为"力争""致力于"等表述',
            "国家级表述": f'建议删除"{word}"，除非持有对应官方认证文件',
            "权威背书": f'建议删除"{word}"，避免使用政府/官方名义背书',
            "金融诱导": f'建议删除"{word}"，投资类表述需符合金融广告法规',
            "时间限定": f'建议删除"{word}"或注明具体活动周期',
        }
        return suggestions.get(category, f'建议替换或删除"{word}"')

    @classmethod
    def from_config(cls) -> "ComplianceChecker":
        """从配置文件加载禁词列表"""
        custom_words = []
        try:
            config_path = Path(__file__).resolve().parent.parent.parent / "config" / "compliance_words.yaml"
            if config_path.exists():
                import yaml
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                for cat in cfg.get("categories", []):
                    custom_words.extend(cat.get("words", []))
        except Exception as e:
            logger.warning(f"加载自定义合规词库失败: {e}")
        return cls(custom_blacklist=custom_words if custom_words else None)
