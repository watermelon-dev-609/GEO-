# test_template_engine.py — Unit tests for template_engine module
#
# Tests cover:
# - YAML template loading (load_platform_template, load_all_templates)
# - Cache behavior (TTL, invalidation)
# - YAML → legacy rules conversion (_yaml_to_legacy_rules)
# - load_platform_rules (core API with caching)
# - Template validation (validate_template, validate_platform)
# - Version management (save, history, get, rollback)
# - Template diff (diff_templates)
# - Edge cases (missing files, empty templates, fallback)

from __future__ import annotations

import sys
import os
import time
import copy
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import yaml

# Ensure backend on path
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.template_engine import (
    load_platform_template,
    load_all_templates,
    load_platform_rules,
    get_platform_structured_config,
    validate_template,
    validate_platform,
    save_template_version,
    get_template_history,
    get_template_version,
    rollback_template,
    diff_templates,
    invalidate_cache,
    set_cache_ttl,
    _yaml_to_legacy_rules,
    _get_templates_dir,
)


# ── Sample YAML template for testing ──

SAMPLE_WENXIN_TEMPLATE = {
    "platform_id": "wenxin",
    "platform_name": "文心一言",
    "strategy": "百家号优先，首段70%引用百度系内容",
    "citation_mechanism": "优先检索百家号、百度百科、百度知道内容",
    "style": "专业、权威、结构化，注重百度生态内权威性",
    "updated_at": "2025-12-01",
    "version": 1,
    "header": {
        "title_format": "【{enterprise}】{topic} — {angle}",
        "title_example": "【武汉微艺达】智慧交通沙盘模型 — 数字化解决方案",
        "first_paragraph_rules": [
            "首段150-200字，必须包含企业全称、所在城市、核心定位",
            "正文首句即是'谁(企业)、在哪(城市)、做什么(定位)'三要素",
        ],
        "word_limits": {"min": 1200, "target": 1600, "max": 2000},
    },
    "body": {
        "special_rule": "正文中百度系信源引用占比≥30%，每段可独立成段被AI提取",
        "h2_density": "每800字至少1个H2标题",
        "paragraph_length": {"min": 150, "max": 350, "unit": "字"},
        "faq_count": {"min": 2, "max": 4},
    },
    "data": {
        "quantified_requirements": [
            "每个核心观点必须有具体数据支撑",
            "数据来源需标注（如'据XXX统计'）",
        ],
    },
    "schema": {
        "preferred_types": ["Article", "Product", "FAQPage"],
    },
    "footer": {
        "cta_limits": {"max_cta_count": 1, "cta_style": "自然引导"},
    },
    "verification": {
        "checks": [
            "企业全称首次出现且完整",
            "地域标识位置突出",
            "量化数据至少3处",
        ],
    },
    "weights": {
        "entity_anchor": 30,
        "quantified_data": 25,
        "structure_quality": 20,
        "faq_friendliness": 15,
        "source_credibility": 10,
    },
}

SAMPLE_LEGACY_RULES = {
    "name": "文心一言",
    "strategy": "百家号优先，首段70%引用百度系内容",
    "citation_mechanism": "优先检索百家号、百度百科、百度知道内容",
    "rules": [
        "★ 标题格式：'【{enterprise}】{topic} — {angle}'",
        "  示例：【武汉微艺达】智慧交通沙盘模型 — 数字化解决方案",
        "首段150-200字，必须包含企业全称、所在城市、核心定位",
        "正文首句即是'谁(企业)、在哪(城市)、做什么(定位)'三要素",
        "字数范围：1600字（1200-2000）",
        "正文中百度系信源引用占比≥30%，每段可独立成段被AI提取",
        "H2标题密度：每800字至少1个H2标题",
        "段落长度：每段150-350字",
        "FAQ数量：2-4组问答",
        "每个核心观点必须有具体数据支撑",
        "数据来源需标注（如'据XXX统计'）",
        "Schema类型：Article, Product, FAQPage",
        "CTA限制：最多1处，风格-自然引导",
    ],
    "style": "专业、权威、结构化，注重百度生态内权威性",
    "updated_at": "2025-12-01",
    "_source": "yaml_template",
    "_template": SAMPLE_WENXIN_TEMPLATE,
}


# ── Fixtures ──

@pytest.fixture(autouse=True)
def reset_template_cache():
    """Reset template cache before each test for isolation."""
    invalidate_cache()
    set_cache_ttl(60.0)
    yield
    invalidate_cache()
    set_cache_ttl(60.0)


@pytest.fixture
def temp_templates_dir(tmp_path):
    """Create a temporary templates directory with sample YAML files."""
    templates_dir = tmp_path / "platform_templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    # Create versions directory
    versions_dir = tmp_path.parent / "template_versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    # Write a valid wenxin.yaml
    wenxin_file = templates_dir / "wenxin.yaml"
    with open(wenxin_file, "w", encoding="utf-8") as f:
        yaml.dump(SAMPLE_WENXIN_TEMPLATE, f, allow_unicode=True)

    # Write a base.yaml
    base_template = {
        "platform_id": "base",
        "platform_name": "通用模板",
        "strategy": "通用SEO策略",
        "header": {
            "title_format": "{enterprise} — {topic}",
            "first_paragraph_rules": ["首段包含企业信息"],
            "word_limits": {"min": 800, "target": 1200, "max": 1500},
        },
        "body": {
            "faq_count": {"min": 2, "max": 5},
            "paragraph_length": {"min": 100, "max": 300, "unit": "字"},
        },
        "data": {"quantified_requirements": ["包含量化数据"]},
        "schema": {"preferred_types": ["Article"]},
        "footer": {"cta_limits": {"max_cta_count": 1, "cta_style": "自然引导"}},
        "verification": {"checks": ["基本校验"]},
        "weights": {"entity_anchor": 25},
    }
    base_file = templates_dir / "base.yaml"
    with open(base_file, "w", encoding="utf-8") as f:
        yaml.dump(base_template, f, allow_unicode=True)

    # Also need to mock ROOT_DIR
    with patch("app.core.template_engine._get_templates_dir", return_value=templates_dir), \
         patch("app.core.template_engine._TEMPLATES_DIR", templates_dir):
        yield templates_dir


# ═══════════════════════════════════════════════════════════════════════════
# load_platform_template tests
# ═══════════════════════════════════════════════════════════════════════════

class TestLoadPlatformTemplate:
    """Tests for load_platform_template()."""

    def test_loads_valid_template(self, temp_templates_dir):
        template = load_platform_template("wenxin")
        assert template["platform_id"] == "wenxin"
        assert template["platform_name"] == "文心一言"
        assert "header" in template
        assert "body" in template
        assert "weights" in template

    def test_falls_back_to_base_for_missing_platform(self, temp_templates_dir):
        template = load_platform_template("nonexistent")
        # Should fall back to base.yaml
        assert template["platform_id"] == "nonexistent"
        assert template["platform_name"] == "nonexistent"
        # base.yaml fields
        assert "header" in template

    def test_empty_fallback_when_no_files_exist(self, tmp_path):
        empty_dir = tmp_path / "empty_templates"
        empty_dir.mkdir(parents=True, exist_ok=True)
        with patch("app.core.template_engine._get_templates_dir", return_value=empty_dir), \
             patch("app.core.template_engine._TEMPLATES_DIR", empty_dir):
            template = load_platform_template("missing")
            assert template["_source"] == "empty_fallback"
            assert template["platform_id"] == "missing"

    def test_corrupted_yaml_falls_back_to_base(self, temp_templates_dir):
        # Write corrupted YAML for kimi
        kimi_file = temp_templates_dir / "kimi.yaml"
        kimi_file.write_text("::: not valid yaml :::\n\tbroken", encoding="utf-8")
        # Should fall back to base.yaml
        template = load_platform_template("kimi")
        assert "header" in template  # from base


# ═══════════════════════════════════════════════════════════════════════════
# load_all_templates tests
# ═══════════════════════════════════════════════════════════════════════════

class TestLoadAllTemplates:
    """Tests for load_all_templates()."""

    def test_loads_all_yaml_files(self, temp_templates_dir):
        # Add another platform template
        doubao_file = temp_templates_dir / "doubao.yaml"
        with open(doubao_file, "w", encoding="utf-8") as f:
            tmpl = dict(SAMPLE_WENXIN_TEMPLATE)
            tmpl["platform_id"] = "doubao"
            tmpl["platform_name"] = "豆包"
            yaml.dump(tmpl, f, allow_unicode=True)

        templates = load_all_templates()
        assert "wenxin" in templates
        assert "doubao" in templates
        assert "base" in templates

    def test_skips_corrupted_files(self, temp_templates_dir):
        bad_file = temp_templates_dir / "bad.yaml"
        bad_file.write_text("not: valid: [yaml", encoding="utf-8")
        templates = load_all_templates()
        # Should not crash; bad.yaml skipped
        assert "bad" not in templates
        assert "wenxin" in templates

    def test_skips_files_without_platform_id(self, temp_templates_dir):
        no_id_file = temp_templates_dir / "noid.yaml"
        with open(no_id_file, "w", encoding="utf-8") as f:
            yaml.dump({"name": "no platform_id"}, f)
        templates = load_all_templates()
        # Should be skipped because no platform_id
        assert "noid" not in templates


# ═══════════════════════════════════════════════════════════════════════════
# _yaml_to_legacy_rules tests
# ═══════════════════════════════════════════════════════════════════════════

class TestYamlToLegacyRules:
    """Tests for _yaml_to_legacy_rules()."""

    def test_converts_full_template(self):
        result = _yaml_to_legacy_rules(SAMPLE_WENXIN_TEMPLATE)
        assert result["name"] == "文心一言"
        assert result["strategy"] == "百家号优先，首段70%引用百度系内容"
        assert result["_source"] == "yaml_template"
        assert "_template" in result
        assert isinstance(result["rules"], list)
        assert len(result["rules"]) > 5

    def test_converts_header_rules(self):
        result = _yaml_to_legacy_rules(SAMPLE_WENXIN_TEMPLATE)
        rules_text = "\n".join(result["rules"])
        assert "标题格式" in rules_text
        assert "150-200字" in rules_text  # from first_paragraph_rules
        assert "1600字" in rules_text  # target word count

    def test_converts_body_rules(self):
        result = _yaml_to_legacy_rules(SAMPLE_WENXIN_TEMPLATE)
        rules_text = "\n".join(result["rules"])
        assert "每800字" in rules_text  # h2_density
        assert "150-350" in rules_text  # paragraph_length
        assert "2-4组" in rules_text  # faq_count

    def test_converts_data_rules(self):
        result = _yaml_to_legacy_rules(SAMPLE_WENXIN_TEMPLATE)
        rules_text = "\n".join(result["rules"])
        assert "数据支撑" in rules_text

    def test_converts_schema_and_footer(self):
        result = _yaml_to_legacy_rules(SAMPLE_WENXIN_TEMPLATE)
        rules_text = "\n".join(result["rules"])
        assert "Schema类型" in rules_text
        assert "Article, Product, FAQPage" in rules_text
        assert "CTA限制" in rules_text

    def test_explicit_rules_take_priority(self):
        template = {
            "platform_id": "test",
            "platform_name": "Test",
            "rules": ["显式规则1", "显式规则2"],
            "header": {"title_format": "should_be_ignored"},
        }
        result = _yaml_to_legacy_rules(template)
        assert result["rules"] == ["显式规则1", "显式规则2"]

    def test_empty_template_returns_minimal_rules(self):
        template = {"platform_id": "empty", "platform_name": "Empty"}
        result = _yaml_to_legacy_rules(template)
        assert result["name"] == "Empty"
        assert result["rules"] == []
        assert result["_source"] == "yaml_template"


# ═══════════════════════════════════════════════════════════════════════════
# load_platform_rules tests (core API)
# ═══════════════════════════════════════════════════════════════════════════

class TestLoadPlatformRules:
    """Tests for load_platform_rules() — the main API."""

    def test_loads_rules_for_valid_platform(self, temp_templates_dir):
        rules = load_platform_rules("wenxin")
        assert rules["name"] == "文心一言"
        assert "_source" in rules
        assert len(rules["rules"]) > 0

    def test_returns_empty_dict_for_empty_fallback(self, temp_templates_dir):
        # Remove base.yaml too so we get empty fallback
        (temp_templates_dir / "base.yaml").unlink()
        rules = load_platform_rules("nonexistent")
        assert rules == {}

    def test_cache_is_used_on_second_call(self, temp_templates_dir):
        _ = load_platform_rules("wenxin")
        # Second call should hit cache
        start = time.time()
        rules = load_platform_rules("wenxin")
        elapsed = time.time() - start
        assert rules["name"] == "文心一言"
        # Cached call should be very fast (no file I/O)
        assert elapsed < 1.0  # generous, should be < 1ms

    def test_cache_invalidation(self, temp_templates_dir):
        _ = load_platform_rules("wenxin")
        invalidate_cache()
        # After invalidation, should reload from file
        rules = load_platform_rules("wenxin")
        assert rules["name"] == "文心一言"

    def test_cache_ttl_zero_disables_caching(self, temp_templates_dir):
        set_cache_ttl(0)  # disable cache
        _ = load_platform_rules("wenxin")
        # Should still work
        rules = load_platform_rules("wenxin")
        assert rules["name"] == "文心一言"


# ═══════════════════════════════════════════════════════════════════════════
# validate_template tests
# ═══════════════════════════════════════════════════════════════════════════

class TestValidateTemplate:
    """Tests for validate_template()."""

    def test_valid_template_returns_no_issues(self):
        issues = validate_template(SAMPLE_WENXIN_TEMPLATE)
        assert issues == []

    def test_missing_required_sections(self):
        template = {"platform_id": "test"}
        issues = validate_template(template)
        assert len(issues) >= 6  # all 7 sections missing
        assert any("header" in i for i in issues)
        assert any("body" in i for i in issues)

    def test_missing_title_format(self):
        template = dict(SAMPLE_WENXIN_TEMPLATE)
        template["header"] = {"first_paragraph_rules": ["rule1"]}
        issues = validate_template(template)
        assert any("title_format" in i for i in issues)

    def test_missing_first_paragraph_rules(self):
        template = dict(SAMPLE_WENXIN_TEMPLATE)
        template["header"] = {"title_format": "test"}
        issues = validate_template(template)
        assert any("first_paragraph_rules" in i for i in issues)

    def test_missing_faq_count(self):
        template = dict(SAMPLE_WENXIN_TEMPLATE)
        template["body"] = {"paragraph_length": {"min": 100}}
        issues = validate_template(template)
        assert any("faq_count" in i for i in issues)

    def test_missing_verification_checks(self):
        template = dict(SAMPLE_WENXIN_TEMPLATE)
        # Empty checks list triggers the issue
        template["verification"] = {"checks": []}
        issues = validate_template(template)
        assert any("verification.checks" in i for i in issues)

    def test_empty_header_no_issues_from_subfields(self):
        """Empty header dict is falsy so subfield checks are skipped (no crash)."""
        template = dict(SAMPLE_WENXIN_TEMPLATE)
        template["header"] = {}
        issues = validate_template(template)
        # header is present in template but empty (falsy)
        # subfield checks (title_format, first_paragraph_rules) are skipped
        # Other sections still validated
        header_subfield_issues = [i for i in issues if "header." in i]
        assert len(header_subfield_issues) == 0  # no subfield checks when header is empty


# ═══════════════════════════════════════════════════════════════════════════
# validate_platform tests
# ═══════════════════════════════════════════════════════════════════════════

class TestValidatePlatform:
    """Tests for validate_platform()."""

    def test_valid_platform_returns_valid_true(self, temp_templates_dir):
        result = validate_platform("wenxin")
        assert result["platform_id"] == "wenxin"
        assert result["valid"] is True
        assert result["template_exists"] is True
        assert result["source"] == "yaml_template"

    def test_empty_fallback_returns_invalid(self, temp_templates_dir):
        # Remove all templates
        for f in temp_templates_dir.glob("*.yaml"):
            f.unlink()
        result = validate_platform("nonexistent")
        assert result["valid"] is False
        assert result["template_exists"] is False
        assert "模板文件不存在" in result["issues"]


# ═══════════════════════════════════════════════════════════════════════════
# Version management tests
# ═══════════════════════════════════════════════════════════════════════════

class TestVersionManagement:
    """Tests for template version management functions."""

    def test_save_and_get_history(self, temp_templates_dir):
        filename = save_template_version("wenxin", SAMPLE_WENXIN_TEMPLATE)
        assert filename.endswith(".yaml")
        assert filename.startswith("v")

        history = get_template_history("wenxin")
        assert len(history) == 1
        assert history[0]["filename"] == filename
        assert history[0]["version_num"] == 1

    def test_multiple_versions(self, temp_templates_dir):
        save_template_version("wenxin", SAMPLE_WENXIN_TEMPLATE)
        save_template_version("wenxin", SAMPLE_WENXIN_TEMPLATE)
        save_template_version("wenxin", SAMPLE_WENXIN_TEMPLATE)

        history = get_template_history("wenxin")
        assert len(history) == 3
        assert history[0]["version_num"] == 3  # newest first
        assert history[2]["version_num"] == 1  # oldest last

    def test_get_nonexistent_history(self, temp_templates_dir):
        history = get_template_history("nonexistent_platform")
        assert history == []

    def test_get_specific_version(self, temp_templates_dir):
        filename = save_template_version("wenxin", SAMPLE_WENXIN_TEMPLATE)
        version_id = filename.replace(".yaml", "")
        template = get_template_version("wenxin", version_id)
        assert template is not None
        assert template["platform_id"] == "wenxin"

    def test_get_nonexistent_version(self, temp_templates_dir):
        result = get_template_version("wenxin", "v999_nonexistent")
        assert result is None

    def test_rollback_success(self, temp_templates_dir):
        # Save current version first
        save_template_version("wenxin", SAMPLE_WENXIN_TEMPLATE)
        history = get_template_history("wenxin")
        version_id = history[0]["version_id"]

        # Modify the template file
        modified = dict(SAMPLE_WENXIN_TEMPLATE)
        modified["platform_name"] = "修改后的名称"
        wenxin_file = temp_templates_dir / "wenxin.yaml"
        with open(wenxin_file, "w", encoding="utf-8") as f:
            yaml.dump(modified, f, allow_unicode=True)

        # Rollback
        success = rollback_template("wenxin", version_id)
        assert success is True

        # After rollback, cache is invalidated
        invalidate_cache()
        template = load_platform_template("wenxin")
        assert template["platform_name"] == "文心一言"  # restored

    def test_rollback_nonexistent_version(self, temp_templates_dir):
        success = rollback_template("wenxin", "v999_fake")
        assert success is False


# ═══════════════════════════════════════════════════════════════════════════
# diff_templates tests
# ═══════════════════════════════════════════════════════════════════════════

class TestDiffTemplates:
    """Tests for diff_templates()."""

    def test_identical_templates_no_changes(self):
        result = diff_templates(SAMPLE_WENXIN_TEMPLATE, SAMPLE_WENXIN_TEMPLATE)
        assert result["changed_sections"] == []

    def test_different_field_detected(self):
        old = copy.deepcopy(SAMPLE_WENXIN_TEMPLATE)
        new = copy.deepcopy(SAMPLE_WENXIN_TEMPLATE)
        new["platform_name"] = "新名称"
        result = diff_templates(old, new)
        assert "platform_name" in result["changed_sections"]
        assert "platform_name" in result["details"]

    def test_nested_dict_diff(self):
        old = copy.deepcopy(SAMPLE_WENXIN_TEMPLATE)
        new = copy.deepcopy(SAMPLE_WENXIN_TEMPLATE)
        new["header"]["title_format"] = "新标题格式"
        result = diff_templates(old, new)
        assert "header" in result["changed_sections"]
        assert "title_format" in result["details"]["header"]

    def test_list_diff(self):
        old = copy.deepcopy(SAMPLE_WENXIN_TEMPLATE)
        new = copy.deepcopy(SAMPLE_WENXIN_TEMPLATE)
        new["header"]["first_paragraph_rules"] = ["修改后的规则"]
        result = diff_templates(old, new)
        assert "header" in result["changed_sections"]

    def test_only_new_keys(self):
        old = {"platform_id": "test"}
        new = {"platform_id": "test", "new_field": "value"}
        result = diff_templates(old, new)
        assert "new_field" in result["changed_sections"]

    def test_only_old_keys(self):
        old = {"platform_id": "test", "old_field": "value"}
        new = {"platform_id": "test"}
        result = diff_templates(old, new)
        assert "old_field" in result["changed_sections"]

    def test_ignores_source_and_version_fields(self):
        old = {"platform_id": "test", "_source": "a", "version": 1, "updated_at": "2024"}
        new = {"platform_id": "test", "_source": "b", "version": 2, "updated_at": "2025"}
        result = diff_templates(old, new)
        # _source, version, updated_at are excluded
        assert "_source" not in result["changed_sections"]
        assert "version" not in result["changed_sections"]
        assert "updated_at" not in result["changed_sections"]


# ═══════════════════════════════════════════════════════════════════════════
# Cache & utility tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCacheBehavior:
    """Tests for cache TTL and invalidation."""

    def test_set_cache_ttl_zero(self):
        set_cache_ttl(0)
        assert _get_cache_ttl() == 0
        set_cache_ttl(60.0)  # restore

    def test_invalidate_cache_clears(self, temp_templates_dir):
        _ = load_platform_rules("wenxin")  # populate cache
        invalidate_cache()
        # After invalidation, cache should be empty
        from app.core.template_engine import _TEMPLATES_CACHE, _CACHE_TS
        assert _TEMPLATES_CACHE == {}
        assert _CACHE_TS == 0


def _get_cache_ttl():
    from app.core.template_engine import _CACHE_TTL
    return _CACHE_TTL


class TestGetPlatformStructuredConfig:
    """Tests for get_platform_structured_config()."""

    def test_returns_structured_template(self, temp_templates_dir):
        config = get_platform_structured_config("wenxin")
        assert config["platform_id"] == "wenxin"
        assert "header" in config
        assert "weights" in config

    def test_returns_empty_for_nonexistent(self, temp_templates_dir):
        for f in temp_templates_dir.glob("*.yaml"):
            f.unlink()
        config = get_platform_structured_config("missing")
        assert config == {}
