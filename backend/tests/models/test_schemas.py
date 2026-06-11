# test_schemas.py — Pydantic schema validation tests

from __future__ import annotations
import sys, os
_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest
from pydantic import ValidationError


class TestComplianceCheckRequest:
    def test_valid_request(self):
        from app.models.schemas import ComplianceCheckRequest
        req = ComplianceCheckRequest(text="测试文本")
        assert req.text == "测试文本"

    def test_empty_text_rejected(self):
        from app.models.schemas import ComplianceCheckRequest
        with pytest.raises(ValidationError):
            ComplianceCheckRequest(text="")


class TestCleaningRequest:
    def test_valid_request(self):
        from app.models.schemas import CleaningRequest
        req = CleaningRequest(content="测试内容需要足够长才能通过校验" * 3)
        assert len(req.content) > 0

    def test_empty_content_rejected(self):
        from app.models.schemas import CleaningRequest
        with pytest.raises(ValidationError):
            CleaningRequest(content="")


class TestKeywordAddRequest:
    def test_valid_request(self):
        from app.models.schemas import KeywordAddRequest
        req = KeywordAddRequest(
            word="测试关键词",
            category="brand",
            weight="core",
            status="pending",
        )
        assert req.word == "测试关键词"
        assert req.category == "brand"

    def test_default_values(self):
        from app.models.schemas import KeywordAddRequest
        # weight and status have defaults
        req = KeywordAddRequest(word="test", category="brand")
        assert req.word == "test"
        assert req.weight is not None
        assert req.status is not None


class TestRewriteRequest:
    def test_valid_request(self):
        from app.models.schemas import RewriteRequest
        req = RewriteRequest(
            cleaned_text="测试内容足够长的企业介绍文本进行GEO优化" * 5,
            sandtable_type="smart_city",
            platforms=["deepseek", "kimi"],
        )
        assert req.platforms == ["deepseek", "kimi"]
        assert req.sandtable_type == "smart_city"

    def test_missing_required_field(self):
        from app.models.schemas import RewriteRequest
        with pytest.raises(ValidationError):
            RewriteRequest(cleaned_text="test")
