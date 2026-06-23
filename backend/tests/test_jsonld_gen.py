# test_jsonld_gen.py — Unit tests for JSONLDGenerator
#
# The generate() method returns: {json_ld_code (str), sandtable_type, schema_types_used, validation_passed}

from __future__ import annotations

import sys
import os
import json
import pytest

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.jsonld_gen import JSONLDGenerator, SCHEMA_MAPPING, SCHEMA_DESCRIPTIONS
from app.models.enums import SandtableType


@pytest.fixture
def gen():
    return JSONLDGenerator()


@pytest.fixture
def ent():
    return {
        "name": "武汉微艺达智能科技有限公司",
        "url": "https://www.weiyida.com",
        "description": "武汉定制沙盘模型专业制造商",
        "logo": "https://www.weiyida.com/logo.png",
    }


@pytest.fixture
def prod():
    return {
        "name": "智慧交通沙盘模型",
        "description": "动态仿真、物联互通的智慧交通沙盘",
        "image": "https://www.weiyida.com/products/traffic.jpg",
    }


def _parse(result):
    """Parse json_ld_code string from result dict into Python dict."""
    return json.loads(result["json_ld_code"])


class TestSchemaMapping:
    def test_all_8_types_have_mapping(self):
        for st in SandtableType:
            assert st.value in SCHEMA_MAPPING

    def test_all_8_types_have_descriptions(self):
        for st in SandtableType:
            assert st.value in SCHEMA_DESCRIPTIONS

    def test_military_has_educational(self):
        assert "EducationalProduct" in SCHEMA_MAPPING["military_terrain"]

    def test_digital_has_software_and_creative(self):
        assert "SoftwareApplication" in SCHEMA_MAPPING["digital_multimedia"]
        assert "CreativeWork" in SCHEMA_MAPPING["digital_multimedia"]

    def test_real_estate_has_unique_schemas(self):
        assert "RealEstateService" in SCHEMA_MAPPING["real_estate"]
        assert "Project" in SCHEMA_MAPPING["real_estate"]
        assert "Place" in SCHEMA_MAPPING["real_estate"]

    def test_general_has_basic_schemas(self):
        assert "general" in SCHEMA_MAPPING
        assert "Product" in SCHEMA_MAPPING["general"]
        assert "Service" in SCHEMA_MAPPING["general"]
        assert "general" in SCHEMA_DESCRIPTIONS
        assert len(SCHEMA_DESCRIPTIONS["general"]) > 0


class TestGenerateAllTypes:
    @pytest.mark.parametrize("st", list(SandtableType))
    def test_generates_valid_structure(self, gen, ent, prod, st):
        result = gen.generate(sandtable_type=st, enterprise_info=ent, product_info=prod)
        assert "json_ld_code" in result
        assert "sandtable_type" in result
        assert "schema_types_used" in result
        assert "validation_passed" in result
        assert result["validation_passed"] is True

        ld = _parse(result)
        assert "@context" in ld
        assert ld["@context"] == "https://schema.org"
        assert "@graph" in ld
        assert isinstance(ld["@graph"], list)
        assert len(ld["@graph"]) >= 2


class TestGenerateDetails:
    def test_organization_in_graph(self, gen, ent, prod):
        result = gen.generate(SandtableType.SMART_CITY, ent, prod)
        ld = _parse(result)
        types = []
        for n in ld["@graph"]:
            t = n.get("@type", "")
            types.append(t if isinstance(t, str) else str(t))
        assert any("Organization" in t for t in types)

    def test_website_in_graph(self, gen, ent, prod):
        result = gen.generate(SandtableType.SMART_CITY, ent, prod)
        ld = _parse(result)
        ws = [n for n in ld["@graph"] if n.get("@type") == "WebSite"]
        assert len(ws) >= 1

    def test_enterprise_name_embedded(self, gen, ent, prod):
        result = gen.generate(SandtableType.SMART_CITY, ent, prod)
        assert ent["name"] in result["json_ld_code"]

    def test_product_name_embedded(self, gen, ent, prod):
        result = gen.generate(SandtableType.SMART_CITY, ent, prod)
        assert prod["name"] in result["json_ld_code"]

    def test_faq_included_by_default(self, gen, ent, prod):
        result = gen.generate(SandtableType.SMART_CITY, ent, prod, include_faq=True)
        ld = _parse(result)
        faq = [n for n in ld["@graph"] if "FAQ" in str(n.get("@type", ""))]
        assert len(faq) >= 1

    def test_faq_excluded(self, gen, ent, prod):
        result = gen.generate(SandtableType.SMART_CITY, ent, prod, include_faq=False)
        ld = _parse(result)
        faq = [n for n in ld["@graph"] if "FAQ" in str(n.get("@type", ""))]
        assert len(faq) == 0

    def test_breadcrumb_included_by_default(self, gen, ent, prod):
        result = gen.generate(SandtableType.SMART_CITY, ent, prod, include_breadcrumb=True)
        ld = _parse(result)
        bc = [n for n in ld["@graph"] if "Breadcrumb" in str(n.get("@type", ""))]
        assert len(bc) >= 1

    def test_breadcrumb_excluded(self, gen, ent, prod):
        result = gen.generate(SandtableType.SMART_CITY, ent, prod, include_breadcrumb=False)
        ld = _parse(result)
        bc = [n for n in ld["@graph"] if "Breadcrumb" in str(n.get("@type", ""))]
        assert len(bc) == 0

    def test_valid_json_output(self, gen, ent, prod):
        result = gen.generate(SandtableType.SMART_CITY, ent, prod)
        ld = _parse(result)
        assert "@graph" in ld


class TestEdgeCases:
    def test_minimal_enterprise(self, gen):
        result = gen.generate(
            SandtableType.SMART_CITY,
            enterprise_info={"name": "TestCo"},
            product_info={"name": "Test"},
        )
        assert result["validation_passed"] is True
        ld = _parse(result)
        assert "@graph" in ld

    def test_empty_product(self, gen):
        result = gen.generate(
            SandtableType.SMART_CITY,
            enterprise_info={"name": "TestCo"},
            product_info={},
        )
        assert result["validation_passed"] is True
        ld = _parse(result)
        assert "@graph" in ld

    def test_no_faq_no_breadcrumb(self, gen, ent, prod):
        result = gen.generate(
            SandtableType.SMART_CITY, ent, prod,
            include_faq=False, include_breadcrumb=False,
        )
        ld = _parse(result)
        assert "@graph" in ld
        assert len(ld["@graph"]) >= 2
