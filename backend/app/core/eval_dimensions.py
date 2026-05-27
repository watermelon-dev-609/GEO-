"""评测维度注册表 — 5维度定义与计算方法映射"""

from __future__ import annotations
from typing import Callable, Coroutine, Any
from app.models.enums import EvalPhase

# 维度计算函数签名
ComputeFunc = Callable[..., Coroutine[Any, Any, dict]]


class EvalDimension:
    """单个评测维度定义"""
    def __init__(
        self,
        key: str,
        label: str,
        phase: EvalPhase,
        requires_llm: bool,
        compute: ComputeFunc | None = None,
    ):
        self.key = key
        self.label = label
        self.phase = phase
        self.requires_llm = requires_llm
        self.compute = compute

    def to_config(self, weight: float = 20.0, enabled: bool = True) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "requires_llm": self.requires_llm,
            "weight": weight,
            "enabled": enabled,
        }


class DimensionRegistry:
    """5维度注册表"""

    DIMENSIONS: dict[str, EvalDimension] = {}

    @classmethod
    def register(cls, dim: EvalDimension):
        cls.DIMENSIONS[dim.key] = dim

    @classmethod
    def get(cls, key: str) -> EvalDimension | None:
        return cls.DIMENSIONS.get(key)

    @classmethod
    def list_all(cls) -> list[EvalDimension]:
        return list(cls.DIMENSIONS.values())

    @classmethod
    def list_enabled(cls, configs: list) -> list[EvalDimension]:
        """根据配置返回启用的维度列表（接受 dict 或对象）"""
        enabled_keys = {
            c["key"] if isinstance(c, dict) else c.key
            for c in configs
            if (c.get("enabled", True) if isinstance(c, dict) else c.enabled)
        }
        return [d for d in cls.list_all() if d.key in enabled_keys]

    @classmethod
    def get_phases_from_configs(cls, configs: list) -> list[EvalPhase]:
        """从维度配置推导需要执行的阶段列表（有序、去重）"""
        dims = cls.list_enabled(configs)
        phases = list(dict.fromkeys(d.phase for d in dims))
        phases.append(EvalPhase.GENERATING_QUESTIONS)
        phases.append(EvalPhase.COMPREHENSIVE)
        return sorted(set(phases), key=lambda p: p.order)


# ── 注册5个维度 ──

DimensionRegistry.register(EvalDimension(
    key="brand_recall",
    label="品牌召回率",
    phase=EvalPhase.BRAND_RECALL,
    requires_llm=False,
))

DimensionRegistry.register(EvalDimension(
    key="solution_match",
    label="方案匹配度",
    phase=EvalPhase.SOLUTION_MATCH,
    requires_llm=False,
))

DimensionRegistry.register(EvalDimension(
    key="advantage_citation",
    label="优势采信率",
    phase=EvalPhase.ADVANTAGE_CITATION,
    requires_llm=True,
))

DimensionRegistry.register(EvalDimension(
    key="structure_quality",
    label="结构化程度",
    phase=EvalPhase.STRUCTURE_QUALITY,
    requires_llm=True,
))

DimensionRegistry.register(EvalDimension(
    key="differentiation",
    label="差异化程度",
    phase=EvalPhase.DIFFERENTIATION,
    requires_llm=True,
))
