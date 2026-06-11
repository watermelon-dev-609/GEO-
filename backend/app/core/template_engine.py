"""平台模板引擎 — 从YAML配置文件动态加载平台规则，替代硬编码PLATFORM_RULES

设计原则：
- 每个AI平台对应一个 YAML 配置文件（data/platform_templates/{platform_id}.yaml）
- 支持热加载（60s TTL缓存），改YAML后无需重启
- 结构化组件分解（header/body/data/schema/footer/verification/weights）
- 向后兼容：YAML不存在时回退到legacy硬编码规则
- 规则变化时只需修改YAML，不需要改代码

使用方式：
    from app.core.template_engine import load_platform_rules
    rules = load_platform_rules("wenxin")  # 返回与legacy PLATFORM_RULES兼容的dict
"""

import logging
import time
import threading
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ── 全局缓存 ──

_TEMPLATES_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TS: float = 0
_CACHE_LOCK = threading.Lock()
_CACHE_TTL: float = 60.0  # 60秒TTL，支持热加载

# ── 路径解析 ──

_TEMPLATES_DIR: Path | None = None


def _get_templates_dir() -> Path:
    """获取平台模板目录的绝对路径"""
    global _TEMPLATES_DIR
    if _TEMPLATES_DIR is None:
        from app.utils.config import ROOT_DIR
        _TEMPLATES_DIR = ROOT_DIR / "data" / "platform_templates"
        _TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    return _TEMPLATES_DIR


def invalidate_cache():
    """强制刷新模板缓存"""
    global _TEMPLATES_CACHE, _CACHE_TS
    with _CACHE_LOCK:
        _TEMPLATES_CACHE = {}
        _CACHE_TS = 0
    logger.info("模板缓存已手动刷新")


def get_cache_info() -> dict[str, Any]:
    """获取模板缓存状态信息（供 watchdog 状态 API 使用）。

    Returns:
        {
            "entries": int,          # 缓存条目数
            "age_seconds": float,    # 缓存年龄（秒），-1 表示无缓存
            "ttl": float,            # 当前 TTL 设置
            "cached_platforms": [str],  # 已缓存的平台列表
        }
    """
    with _CACHE_LOCK:
        age = (time.time() - _CACHE_TS) if _CACHE_TS > 0 and _TEMPLATES_CACHE else -1
        return {
            "entries": len(_TEMPLATES_CACHE),
            "age_seconds": round(age, 1) if age >= 0 else -1,
            "ttl": _CACHE_TTL,
            "cached_platforms": sorted(_TEMPLATES_CACHE.keys()),
        }


def set_cache_ttl(ttl: float):
    """设置缓存TTL（秒），0表示禁用缓存"""
    global _CACHE_TTL
    _CACHE_TTL = max(0, ttl)


# ── 原始YAML加载 ──

def load_platform_template(platform: str) -> dict[str, Any]:
    """加载单个平台的完整YAML模板配置。

    优先加载 {platform}.yaml，不存在时回退到 base.yaml。

    Args:
        platform: 平台ID（如 "wenxin", "doubao"）

    Returns:
        模板配置字典，包含所有结构化组件字段
    """
    templates_dir = _get_templates_dir()

    # 尝试平台专属文件
    plat_file = templates_dir / f"{platform}.yaml"
    if plat_file.exists():
        try:
            with open(plat_file, "r", encoding="utf-8") as f:
                template = yaml.safe_load(f)
            if template and template.get("platform_id"):
                logger.debug(f"加载平台模板: {platform} ← {plat_file.name}")
                return template
        except (yaml.YAMLError, OSError) as e:
            logger.warning(f"平台模板文件损坏，尝试回退: {platform} — {e}")

    # 回退到 base.yaml
    base_file = templates_dir / "base.yaml"
    if base_file.exists():
        try:
            with open(base_file, "r", encoding="utf-8") as f:
                template = yaml.safe_load(f)
            if template:
                logger.debug(f"平台模板 {platform} 回退到 base.yaml")
                # 注入平台ID
                template["platform_id"] = platform
                template["platform_name"] = platform
                return template
        except (yaml.YAMLError, OSError) as e:
            logger.warning(f"base.yaml 也加载失败: {e}")

    # 终极回退：返回空模板
    logger.warning(f"无可用模板配置: {platform}")
    return {"platform_id": platform, "platform_name": platform, "_source": "empty_fallback"}


def load_all_templates() -> dict[str, dict[str, Any]]:
    """加载所有平台的模板配置。

    Returns:
        {platform_id: template_dict} 字典
    """
    templates = {}
    templates_dir = _get_templates_dir()
    for yaml_file in sorted(templates_dir.glob("*.yaml")):
        platform_id = yaml_file.stem
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                template = yaml.safe_load(f)
            if template and template.get("platform_id"):
                templates[platform_id] = template
        except (yaml.YAMLError, OSError) as e:
            logger.warning(f"跳过损坏的模板文件: {yaml_file.name} — {e}")
    return templates


# ── 兼容层：YAML → legacy PLATFORM_RULES dict ──

def _yaml_to_legacy_rules(template: dict[str, Any]) -> dict[str, Any]:
    """将结构化YAML模板转换为与legacy PLATFORM_RULES兼容的dict格式。

    这使得现有代码（build_geo_prompt等）无需修改即可使用YAML模板。

    Args:
        template: YAML加载的完整模板字典

    Returns:
        兼容legacy PLATFORM_RULES格式的dict:
        {name, strategy, citation_mechanism, rules, style, updated_at, _source, ...}
    """
    rules_list: list[str] = []

    # 优先使用显式声明的 rules 列表（完全兼容旧格式）
    if template.get("rules"):
        rules_list = list(template["rules"])
    else:
        # 从结构化组件生成规则列表
        header = template.get("header", {})
        body = template.get("body", {})
        data = template.get("data", {})
        schema = template.get("schema", {})
        footer = template.get("footer", {})

        # Header rules
        title_fmt = header.get("title_format", "")
        if title_fmt:
            rules_list.append(f"★ 标题格式：'{title_fmt}'")
        title_example = header.get("title_example", "")
        if title_example:
            rules_list.append(f"  示例：{title_example}")
        for rule in header.get("first_paragraph_rules", []):
            rules_list.append(rule)
        wl = header.get("word_limits", {})
        if wl:
            rules_list.append(f"字数范围：{wl.get('target', 1200)}字（{wl.get('min', 800)}-{wl.get('max', 1500)}）")

        # Body rules
        special = body.get("special_rule", "")
        if special:
            rules_list.append(special)
        h2d = body.get("h2_density", "")
        if h2d:
            rules_list.append(f"H2标题密度：{h2d}")
        para_len = body.get("paragraph_length", {})
        if para_len:
            rules_list.append(f"段落长度：每段{para_len.get('min', 150)}-{para_len.get('max', 350)}{para_len.get('unit', '字')}")
        faq = body.get("faq_count", {})
        if faq:
            rules_list.append(f"FAQ数量：{faq.get('min', 2)}-{faq.get('max', 4)}组问答")

        # Data rules
        for req in data.get("quantified_requirements", []):
            rules_list.append(req)

        # Schema rules
        schema_types = schema.get("preferred_types", [])
        if schema_types:
            rules_list.append(f"Schema类型：{', '.join(schema_types)}")

        # Footer rules
        cta = footer.get("cta_limits", {})
        if cta:
            rules_list.append(f"CTA限制：最多{cta.get('max_cta_count', 1)}处，风格-{cta.get('cta_style', '自然引导')}")

    # 构建兼容dict
    result = {
        "name": template.get("platform_name", template.get("platform_id", "")),
        "strategy": template.get("strategy", ""),
        "citation_mechanism": template.get("citation_mechanism",
            "该平台通过搜索引擎索引和训练语料获取外部内容"),
        "rules": rules_list,
        "style": template.get("style", ""),
        "updated_at": template.get("updated_at", ""),
        "_source": "yaml_template",
        # 附加结构化信息（新增功能可用）
        "_template": template,
    }
    return result


# ── 核心API：带缓存的规则加载 ──

def load_platform_rules(platform: str) -> dict[str, Any]:
    """加载平台优化规则（主要接口）。

    优先从YAML模板加载，失败时返回None让调用方回退到legacy规则。

    Args:
        platform: 平台ID（如 "wenxin", "doubao", "deepseek"）

    Returns:
        兼容legacy PLATFORM_RULES格式的dict，包含 name/strategy/citation_mechanism/rules/style/updated_at/_source
        如果YAML模板不存在且无法加载，返回空dict（调用方应回退到legacy规则）
    """
    global _TEMPLATES_CACHE, _CACHE_TS

    now = time.time()

    # 检查缓存
    with _CACHE_LOCK:
        if _CACHE_TTL > 0 and _TEMPLATES_CACHE and (now - _CACHE_TS) < _CACHE_TTL:
            cached = _TEMPLATES_CACHE.get(platform)
            if cached is not None:
                return cached

    # 加载YAML模板
    template = load_platform_template(platform)

    # 检查是否成功加载
    if template.get("_source") == "empty_fallback":
        # YAML不存在，返回空dict让调用方回退到legacy
        result = {}
    else:
        result = _yaml_to_legacy_rules(template)

    # 更新缓存
    with _CACHE_LOCK:
        _TEMPLATES_CACHE[platform] = result
        _CACHE_TS = now

    return result


def get_platform_structured_config(platform: str) -> dict[str, Any]:
    """获取平台的结构化配置（header/body/data/schema/footer等）。

    这个方法返回原始的YAML结构化数据，供需要结构化组件的新功能使用。

    Args:
        platform: 平台ID

    Returns:
        完整的YAML模板字典（结构化格式）
    """
    template = load_platform_template(platform)
    if template.get("_source") == "empty_fallback":
        return {}
    return template


# ── 模板校验 ──

REQUIRED_SECTIONS = ["header", "body", "data", "schema", "footer", "verification", "weights"]


def validate_template(template: dict[str, Any]) -> list[str]:
    """校验模板配置是否包含所有必需字段。

    Returns:
        问题列表，空列表表示通过校验
    """
    issues = []
    for section in REQUIRED_SECTIONS:
        if section not in template:
            issues.append(f"缺少必需字段: {section}")

    # 校验子字段
    header = template.get("header", {})
    if header:
        if not header.get("title_format"):
            issues.append("header.title_format 不能为空")
        if not header.get("first_paragraph_rules"):
            issues.append("header.first_paragraph_rules 不能为空")

    body = template.get("body", {})
    if body:
        if not body.get("faq_count"):
            issues.append("body.faq_count 不能为空")
        if not body.get("paragraph_length"):
            issues.append("body.paragraph_length 不能为空")

    verification = template.get("verification", {})
    if verification:
        if not verification.get("checks"):
            issues.append("verification.checks 不能为空（至少1条校验规则）")

    return issues


def validate_platform(platform: str) -> dict[str, Any]:
    """校验指定平台的模板配置。

    Returns:
        {
            "platform_id": str,
            "valid": bool,
            "issues": list[str],
            "template_exists": bool,
            "source": str  # yaml_template / base_fallback / empty_fallback
        }
    """
    template = load_platform_template(platform)
    source = template.get("_source", "yaml_template")
    template_exists = source != "empty_fallback"

    issues = validate_template(template) if template_exists else ["模板文件不存在"]

    return {
        "platform_id": platform,
        "valid": len(issues) == 0,
        "issues": issues,
        "template_exists": template_exists,
        "source": source,
    }


# ── 模板版本管理 ──

def save_template_version(platform: str, template: dict[str, Any]) -> str:
    """保存模板的历史版本（在更新模板时调用）。

    Returns:
        版本文件名
    """
    from datetime import datetime
    versions_dir = _get_templates_dir().parent / "template_versions" / platform
    versions_dir.mkdir(parents=True, exist_ok=True)

    version_num = len(list(versions_dir.glob("v*.yaml"))) + 1
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"v{version_num}_{timestamp}.yaml"

    with open(versions_dir / filename, "w", encoding="utf-8") as f:
        yaml.dump(template, f, allow_unicode=True, default_flow_style=False)

    logger.info(f"模板版本已保存: {platform}/{filename}")
    return filename


def get_template_history(platform: str) -> list[dict[str, Any]]:
    """获取指定平台的模板版本历史。

    Returns:
        [{version_id, version_num, saved_at, filename}, ...]
    """
    versions_dir = _get_templates_dir().parent / "template_versions" / platform
    if not versions_dir.exists():
        return []

    history = []
    for version_file in sorted(versions_dir.glob("v*.yaml"), reverse=True):
        # 解析文件名: v{n}_{timestamp}.yaml
        stem = version_file.stem
        parts = stem.split("_", 1)
        version_id = stem
        version_num = int(parts[0][1:]) if parts[0].startswith("v") else 0
        timestamp = parts[1] if len(parts) > 1 else ""

        saved_at = ""
        try:
            saved_at = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]} {timestamp[9:11]}:{timestamp[11:13]}:{timestamp[13:15]}"
        except (IndexError, ValueError):
            saved_at = timestamp

        history.append({
            "version_id": version_id,
            "version_num": version_num,
            "saved_at": saved_at,
            "filename": version_file.name,
        })

    return history


def get_template_version(platform: str, version_id: str) -> dict[str, Any] | None:
    """获取指定版本的模板内容。"""
    versions_dir = _get_templates_dir().parent / "template_versions" / platform
    version_file = versions_dir / f"{version_id}.yaml"
    if not version_file.exists():
        return None
    with open(version_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def rollback_template(platform: str, version_id: str) -> bool:
    """将指定平台回滚到历史版本。

    Args:
        platform: 平台ID
        version_id: 历史版本ID

    Returns:
        是否成功
    """
    old_template = get_template_version(platform, version_id)
    if old_template is None:
        logger.error(f"回滚失败：版本不存在 {platform}/{version_id}")
        return False

    # 保存当前版本
    current = load_platform_template(platform)
    if current.get("_source") != "empty_fallback":
        save_template_version(platform, current)

    # 写入回滚版本
    templates_dir = _get_templates_dir()
    target_file = templates_dir / f"{platform}.yaml"

    # 更新版本号和更新时间
    from datetime import datetime
    old_template["version"] = old_template.get("version", 1) + 1
    old_template["updated_at"] = datetime.now().strftime("%Y-%m-%d")

    with open(target_file, "w", encoding="utf-8") as f:
        yaml.dump(old_template, f, allow_unicode=True, default_flow_style=False)

    # 刷新缓存
    invalidate_cache()

    logger.info(f"模板回滚成功: {platform} → {version_id}")
    return True


def diff_templates(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """对比两个模板版本的差异。

    Returns:
        {
            "changed_sections": ["header", "weights"],
            "details": {
                "header": {"field": "title_format", "old": "...", "new": "..."},
                ...
            },
            "summary": "修改了2个字段"
        }
    """
    import difflib

    changed_sections = []
    details = {}

    # 对比顶级字段
    all_keys = set(old.keys()) | set(new.keys())
    for key in sorted(all_keys):
        if key in ("_source", "version", "updated_at"):
            continue
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val:
            changed_sections.append(key)
            if isinstance(old_val, dict) and isinstance(new_val, dict):
                # 嵌套dict对比
                sub_details = {}
                sub_keys = set(old_val.keys()) | set(new_val.keys())
                for sk in sorted(sub_keys):
                    ov = old_val.get(sk)
                    nv = new_val.get(sk)
                    if ov != nv:
                        sub_details[sk] = {"old": str(ov)[:200], "new": str(nv)[:200]}
                details[key] = sub_details
            elif isinstance(old_val, list) and isinstance(new_val, list):
                # 列表对比
                old_text = "\n".join(str(x) for x in old_val)
                new_text = "\n".join(str(x) for x in new_val)
                diff_lines = list(difflib.unified_diff(
                    old_text.splitlines(), new_text.splitlines(),
                    lineterm="",
                ))
                details[key] = {"diff_lines": diff_lines[:50]}  # 限制50行
            else:
                details[key] = {"old": str(old_val)[:200], "new": str(new_val)[:200]}

    summary = f"修改了 {len(changed_sections)} 个配置段"
    return {
        "changed_sections": changed_sections,
        "details": details,
        "summary": summary,
    }
