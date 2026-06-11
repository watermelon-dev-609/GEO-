# -*- coding: utf-8 -*-
"""GEO System Full API Test - using requests with correct routes"""
import requests
import json
import time
import sys
import os

os.environ["PYTHONIOENCODING"] = "utf-8"

BASE = "http://localhost:8000"
PASS = 0
FAIL = 0
ERRORS = []

TEXT = ("武汉微艺达智能科技有限公司是一家专注于智慧交通沙盘设计与制作的专业公司，"
        "总部位于武汉。公司拥有10年行业经验，服务过50+政企客户，项目覆盖智慧城市、"
        "智慧交通、智慧工业等领域。我们的核心技术团队来自国内顶尖高校，采用数字化"
        "仿真技术打造高精度沙盘模型。")

LONG_TEXT = TEXT * 15

def test(name, method, path, data=None, expected_status=200, timeout=60):
    global PASS, FAIL
    url = BASE + path
    start = time.time()
    try:
        if method == "GET":
            resp = requests.get(url, timeout=timeout)
        elif method == "POST":
            resp = requests.post(url, json=data, timeout=timeout)
        else:
            resp = requests.request(method, url, json=data, timeout=timeout)

        elapsed = time.time() - start
        status_ok = resp.status_code == expected_status

        if status_ok:
            PASS += 1
            print(f"  [PASS] {name} ({resp.status_code}, {elapsed:.1f}s)")
        else:
            FAIL += 1
            err = f"{name}: expected {expected_status}, got {resp.status_code}"
            ERRORS.append(err)
            detail = resp.text[:150]
            print(f"  [FAIL] {name} ({resp.status_code}, {elapsed:.1f}s)")
            print(f"         {detail}")

        return resp
    except Exception as e:
        FAIL += 1
        err = f"{name}: {type(e).__name__}: {e}"
        ERRORS.append(err)
        print(f"  [ERR] {name} - {err[:120]}")
        return None

print("="*60)
print("GEO System Landing Verification Test")
print("Started:", time.strftime("%Y-%m-%d %H:%M:%S"))
print("="*60)

# ============================================================
# Phase 1: System Health & Config
# ============================================================
print("\n--- Phase 1: System Health & Config ---")

resp = test("Health Check", "GET", "/api/health")
if resp:
    d = resp.json()
    print(f"     version={d.get('version')}, embedding={d.get('embedding_model_loaded')}")

resp = test("LLM Config", "GET", "/api/config/llm")
if resp:
    d = resp.json()
    configured = [p["platform"] for p in d["llm_platforms"] if p["configured"]]
    print(f"     configured: {configured}")

# ============================================================
# Phase 2: Core Pipeline
# ============================================================
print("\n--- Phase 2: Core Pipeline ---")

# 2.1 Text Cleaning
resp = test("Clean Text", "POST", "/api/cleaning/clean",
            {"content": TEXT, "sandtable_type": "smart_traffic"}, timeout=120)
cleaned = ""
if resp:
    d = resp.json()
    cleaned = d.get("cleaned_text", d.get("cleaned_content", ""))
    print(f"     cleaned_len={len(cleaned)}, reduction={d.get('reduction_rate', 'N/A')}")
    dims = d.get("dimensions", {})
    if dims:
        print(f"     five_dims={list(dims.keys())}")

# 2.2 Extract (P0-3 was fixed)
resp = test("Extract Info", "POST", "/api/cleaning/extract",
            {"content": TEXT, "sandtable_type": "smart_traffic"}, timeout=120)

# 2.3 Content Diagnosis (use correct path)
resp = test("Quick Diagnosis", "POST", "/api/diagnosis/quick",
            {"content": TEXT, "sandtable_type": "smart_traffic"}, timeout=120)
if resp:
    d = resp.json()
    print(f"     overall={d.get('overall_score', 'N/A')}")

# 2.4 GEO Rewrite
resp = test("GEO Rewrite", "POST", "/api/geo/rewrite",
            {"content": TEXT, "platforms": ["deepseek"], "sandtable_type": "smart_traffic"}, timeout=300)
optimized = ""
if resp:
    d = resp.json()
    results = d.get("results", {})
    if "deepseek" in results:
        optimized = results["deepseek"].get("optimized_text", "")
        print(f"     words={results['deepseek'].get('word_count','N/A')}")

# 2.5 JSON-LD
resp = test("JSON-LD", "POST", "/api/jsonld/generate",
            {"content": TEXT, "sandtable_type": "smart_traffic",
             "enterprise_name": "武汉微艺达智能科技有限公司",
             "enterprise_url": "https://www.weiyida.com"}, timeout=120)
if resp:
    d = resp.json()
    print(f"     validation={d.get('validation_passed')}, schemas={d.get('schema_types')}")

# 2.6 AI Evaluation (correct path: /api/evaluate/start)
eval_content = optimized if optimized else TEXT
resp = test("AI Evaluation", "POST", "/api/evaluate/start",
            {"content": eval_content, "sandtable_type": "smart_traffic",
             "platforms": ["deepseek"], "user_role": "b_enterprise"}, timeout=300)
if resp:
    d = resp.json()
    score = d.get("overall_score", "N/A")
    sc = d.get("dimensions", {}).get("source_consistency", "N/A")
    print(f"     overall={score}, source_consistency={sc}")
    dims = d.get("dimensions", {})
    for k, v in dims.items():
        flag = "WARN" if v < 60 else "OK"
        print(f"       {flag} {k}={v}")

# 2.7 Report
resp = test("Report Gen", "POST", "/api/reports/generate-from-data",
            {"data": {"overall_score": 75, "dimensions": {"brand_recall": 70, "solution_match": 80}},
             "format": "html", "enterprise_name": "Test"}, timeout=120)
if resp:
    d = resp.json()
    print(f"     report_id={d.get('report_id', 'N/A')}")

# ============================================================
# Phase 3: Strategy Center
# ============================================================
print("\n--- Phase 3: Strategy Center ---")

resp = test("Platform Rules", "GET", "/api/platform-monitor/platforms")
if resp:
    d = resp.json()
    print(f"     platforms={len(d.get('platforms', []))}")

for st in ["smart_traffic", "smart_city", "smart_industry", "military_terrain",
           "smart_agriculture", "smart_logistics", "digital_multimedia", "real_estate"]:
    resp = test(f"Keywords[{st}]", "GET", f"/api/keywords/{st}")
    if resp:
        d = resp.json()
        kw = d.get("keywords", {})
        total = sum(len(v) for v in kw.values())
        print(f"     {st}: {total} keywords")

resp = test("Add Keyword", "POST", "/api/keywords/smart_traffic",
            {"word": "GEO测试关键词_" + str(int(time.time())), "category": "brand",
             "weight": "8", "status": "approved"}, timeout=30)

resp = test("Competitors", "GET", "/api/competitors")

resp = test("Templates", "GET", "/api/templates/list")

# ============================================================
# Phase 4: Edge Cases & Errors
# ============================================================
print("\n--- Phase 4: Edge Cases ---")

test("Empty Input -> 422", "POST", "/api/cleaning/clean",
     {"content": "", "sandtable_type": "smart_traffic"}, expected_status=422)

test("XSS Input (clean)", "POST", "/api/cleaning/clean",
     {"content": "<script>alert(1)</script>", "sandtable_type": "smart_traffic"})

test("Invalid Platform -> 422", "POST", "/api/cleaning/clean",
     {"content": TEXT, "sandtable_type": "nonexistent"}, expected_status=422)

test("Nonexistent Platform (P2-2)", "GET", "/api/platform-monitor/platforms/nonexistent")

test("SEO Check", "GET", "/api/seo/analysis")

# ============================================================
# Phase 5: v2.0 Features
# ============================================================
print("\n--- Phase 5: v2.0 New Features ---")

test("Batch Clean", "POST", "/api/batch/clean",
     {"items": [{"content": TEXT, "sandtable_type": "smart_traffic"}]}, timeout=120)

resp = test("Compliance Check", "POST", "/api/compliance/check",
            {"content": TEXT}, timeout=60)
if resp and resp.status_code == 200:
    d = resp.json()
    risks = d.get("risks", []) if isinstance(d, dict) else []
    print(f"     risks={len(risks)}")

resp = test("Usage Summary", "GET", "/api/usage/summary")

resp = test("Audit Logs", "GET", "/api/audit/logs")

# Test with real text to get versions
resp = test("Scheduler Jobs", "GET", "/api/scheduler/jobs")

resp = test("Scheduler Status", "GET", "/api/scheduler/status")

respx = test("Brand History", "GET", "/api/brand-monitor/history")

# ============================================================
# Phase 6: 8 Sandtable Types - JSON-LD Generation
# ============================================================
print("\n--- Phase 6: All 8 Sandtable Types (JSON-LD) ---")
TYPES = {
    "smart_traffic": "智慧交通沙盘",
    "smart_city": "智慧城市沙盘",
    "smart_industry": "智慧工业沙盘",
    "smart_agriculture": "智慧农业沙盘",
    "smart_logistics": "智慧物流沙盘",
    "military_terrain": "军事地形沙盘",
    "digital_multimedia": "数字多媒体展厅",
    "real_estate": "地产规划设计沙盘",
}
for st, label in TYPES.items():
    resp = test(f"JSON-LD [{label}]", "POST", "/api/jsonld/generate",
                {"content": TEXT, "sandtable_type": st,
                 "enterprise_name": "武汉微艺达智能科技有限公司",
                 "enterprise_url": "https://www.weiyida.com"}, timeout=120)
    if resp and resp.status_code == 200:
        d = resp.json()
        print(f"     [{label}] ok schemas={d.get('schema_types')}")

# ============================================================
# Summary
# ============================================================
print("\n" + "="*60)
print("TEST SUMMARY")
print("="*60)
total = PASS + FAIL
print(f"  PASS: {PASS}/{total}")
print(f"  FAIL: {FAIL}/{total}")
if ERRORS:
    print(f"\nFAILURES ({len(ERRORS)}):")
    for e in ERRORS:
        print(f"  - {e}")
else:
    print("\nALL TESTS PASSED!")
print(f"\nCompleted: {time.strftime('%Y-%m-%d %H:%M:%S')}")
