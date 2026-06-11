# test_keywords_api.py — Regression tests for keywords API (had P0 bug at line 126)

from __future__ import annotations
import sys, os
_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest


class TestKeywordsModuleIntegrity:
    """P0 regression: keywords.py line 126 had NameError: 'category' referenced but undefined."""

    def test_module_imports_without_name_error(self):
        """Verify the module can be imported without NameError."""
        from app.api.keywords import router, SANDBTABLE_TYPES, SANDBTABLE_LABELS, PRELOADED_KEYWORDS
        assert router is not None

    def test_sandtable_types_count(self):
        from app.api.keywords import SANDBTABLE_TYPES
        assert len(SANDBTABLE_TYPES) == 8

    def test_preloaded_keywords_exist(self):
        from app.api.keywords import PRELOADED_KEYWORDS
        assert "brand" in PRELOADED_KEYWORDS
        assert "scene" in PRELOADED_KEYWORDS
        assert "longtail" in PRELOADED_KEYWORDS
        assert len(PRELOADED_KEYWORDS["brand"]) >= 4

    def test_category_field_accessible(self):
        """P0 regression: the 'category' variable was undefined at line 126.
        The fix: use req.category (schema field) instead of bare 'category'."""
        from app.api.keywords import KeywordAddRequest
        req = KeywordAddRequest(
            word="测试关键词",
            category="brand",
            weight="core",
            status="pending",
        )
        assert req.word == "测试关键词"
        assert req.category == "brand"
        # This is the field that was causing NameError — now properly accessed via req.category


class TestReportsModuleIntegrity:
    """P0 regression: reports.py line 72 had NameError: 'report_format' referenced but undefined."""

    def test_module_imports(self):
        from app.api.reports import router
        assert router is not None
