# -*- coding: utf-8 -*-
"""GEO System Landing Verification - Full API Smoke Test"""
import httpx
import json
import time
import sys

BASE = "http://localhost:8000"
PASS = 0
FAIL = 0
ERRORS = []

TEST_TEXT = (
    "武汉微艺达智能科技有限公司"
    "是一家专注于智慧交通沙盘设计"
    "与制作的专业公司，总部位于武汉。"
    "公司拥有10年行业经验，服务过50+"
    "政企客户，项目覆盖智慧城市、"
    "智慧交通、智慧工业等领域。"
    "我们的核心技术团队来自国内顶尖"
    "高校，采用数字化仿真技术打造"
    "高精度沙盘模型。"
)

LONG_TEST = TEST_TEXT * 15

# Use a file for the raw Chinese text to avoid encoding issues
def get_test_text():
    return (
        "武汉微艺达智能科技有限公司"
        "是一家专注于智慧交通沙盘设计"
        "与制作的专业公司，总部位于武汉。"
        "公司拥有10年行业经验，服务过50+"
        "政企客户，项目覆盖智慧城市、"
        "智慧交通、智慧工业等领域。"
        "我们的核心技术团队来自国内顶尖"
        "高校，采用数字化仿真技术打造"
        "高精度沙盘模型。"
    )

def test(name, method, path, data=None, expected_status=200, timeout=60):
    global PASS, FAIL
    url = BASE + path
    start = time.time()
    try:
        if method == "GET":
            resp = httpx.get(url, timeout=timeout)
        elif method == "POST":
            resp = httpx.post(url, json=data, timeout=timeout)
        else:
            resp = httpx.request(method, url, json=data, timeout=timeout)

        elapsed = time.time() - start
        status_ok = resp.status_code == expected_status

        if status_ok:
            PASS += 1
            print(f"  [PASS] {name} ({resp.status_code}, {elapsed:.1f}s)")
        else:
            FAIL += 1
            err = f"{name}: expected {expected_status}, got {resp.status_code}"
            ERRORS.append(err)
            try:
                detail = resp.json().get("detail", resp.text[:100])
            except:
                detail = resp.text[:100]
            print(f"  [FAIL] {name} ({resp.status_code}, {elapsed:.1f}s) - {detail}")

        return resp
    except Exception as e:
        FAIL += 1
        err = f"{name}: {type(e).__name__}: {e}"
        ERRORS.append(err)
        print(f"  [ERR] {name} - {err[:120]}")
        return None

# ============================================================
# Phase 1: Basic System Checks
# ============================================================
print("\n" + "="*60)
print("Phase 1: System Health & Config")
print("="*60)

resp = test("Health Check", "GET", "/api/health")
if resp:
    data = resp.json()
    print(f"     version={data.get('version')}, embedding_loaded={data.get('embedding_model_loaded')}")

resp = test("LLM Config", "GET", "/api/config/llm")
if resp:
    data = resp.json()
    configured = [p["platform"] for p in data["llm_platforms"] if p["configured"]]
    print(f"     configured_platforms={configured}")

# ============================================================
# Phase 2: Core Pipeline (Import -> Clean -> Optimize -> Evaluate -> Export)
# ============================================================
print("\n" + "="*60)
print("Phase 2: Core Pipeline")
print("="*60)

# 2.1 Text Cleaning
print("\n  [2.1] Text Cleaning...")
resp = test("POST /api/cleaning/clean", "POST", "/api/cleaning/clean",
            {"content": get_test_text(), "sandtable_type": "smart_traffic"}, timeout=120)
cleaned_text = ""
if resp and resp.status_code == 200:
    data = resp.json()
    cleaned_text = data.get("cleaned_text", "")
    print(f"     cleaned_length={len(cleaned_text)}, reduction={data.get('reduction_rate', 0):.1%}")
    dims = data.get("dimensions", {})
    if dims:
        print(f"     five_dimensions={list(dims.keys())}")

# 2.2 Content Diagnosis
print("\n  [2.2] Content Diagnosis...")
resp = test("POST /api/diagnosis/diagnose", "POST", "/api/diagnosis/diagnose",
            {"content": get_test_text(), "sandtable_type": "smart_traffic"}, timeout=120)
if resp and resp.status_code == 200:
    data = resp.json()
    score = data.get("overall_score", "N/A")
    print(f"     overall_score={score}")
    dims = data.get("dimensions", {})
    for k, v in dims.items():
        print(f"       {k}={v}")

# 2.3 GEO Rewrite (single platform - DeepSeek)
print("\n  [2.3] GEO Rewrite (DeepSeek)...")
resp = test("POST /api/geo/rewrite", "POST", "/api/geo/rewrite",
            {"content": get_test_text(), "platforms": ["deepseek"], "sandtable_type": "smart_traffic"}, timeout=300)
optimized_text = ""
if resp and resp.status_code == 200:
    data = resp.json()
    results = data.get("results", {})
    if "deepseek" in results:
        optimized_text = results["deepseek"].get("optimized_text", "")
        wc = results["deepseek"].get("word_count", 0)
        print(f"     deepseek_word_count={wc}")
    else:
        print(f"     results_keys={list(results.keys())}")

# 2.4 JSON-LD Generation
print("\n  [2.4] JSON-LD Generation...")
resp = test("POST /api/jsonld/generate", "POST", "/api/jsonld/generate",
            {"content": get_test_text(), "sandtable_type": "smart_traffic",
             "enterprise_name": "武汉微艺达智能科技有限公司",
             "enterprise_url": "https://www.weiyida.com"}, timeout=120)
if resp and resp.status_code == 200:
    data = resp.json()
    print(f"     validation_passed={data.get('validation_passed')}, schemas={data.get('schema_types')}")

# 2.5 AI Evaluation
print("\n  [2.5] AI Evaluation...")
eval_content = optimized_text if optimized_text else get_test_text()
resp = test("POST /api/evaluate/evaluate", "POST", "/api/evaluate/evaluate",
            {"content": eval_content, "sandtable_type": "smart_traffic",
             "platforms": ["deepseek"], "user_role": "b_enterprise"}, timeout=300)
if resp and resp.status_code == 200:
    data = resp.json()
    print(f"     overall_score={data.get('overall_score')}")
    dims = data.get("dimensions", {})
    for k, v in dims.items():
        flag = "WARN" if v < 60 else "OK"
        print(f"       {flag} {k}={v}")

# 2.6 Report Generation
print("\n  [2.6] Report Generation...")
resp = test("POST /api/reports/generate-from-data", "POST", "/api/reports/generate-from-data",
            {"data": {"overall_score": 75, "dimensions": {"brand_recall": 70, "solution_match": 80}},
             "format": "html", "enterprise_name": "Test Company"}, timeout=120)
if resp and resp.status_code == 200:
    print(f"     report_bytes={len(resp.content)}")

# ============================================================
# Phase 3: Strategy Center
# ============================================================
print("\n" + "="*60)
print("Phase 3: Strategy Center Modules")
print("="*60)

resp = test("GET /api/platform-monitor/platforms", "GET", "/api/platform-monitor/platforms")
if resp and resp.status_code == 200:
    platforms = resp.json()
    print(f"  [3.1] platform_count={len(platforms) if isinstance(platforms, list) else 'N/A'}")

for st in ["smart_traffic", "smart_city"]:
    resp = test(f"GET /api/keywords/{st}", "GET", f"/api/keywords/{st}")
    if resp and resp.status_code == 200:
        data = resp.json()
        kw_count = sum(len(v) for v in data.get("keywords", {}).values())
        print(f"  [3.2] {st}_keywords={kw_count}")

resp = test("POST /api/keywords/smart_traffic", "POST", "/api/keywords/smart_traffic",
            {"word": "智能交通仿真", "category": "brand", "weight": "8", "status": "approved"}, timeout=30)
if resp and resp.status_code == 200:
    print(f"  [3.2] keyword_add=success")

resp = test("GET /api/competitors", "GET", "/api/competitors")
if resp and resp.status_code == 200:
    comps = resp.json()
    print(f"  [3.3] competitor_count={len(comps) if isinstance(comps, list) else 'N/A'}")

resp = test("GET /api/templates", "GET", "/api/templates")
if resp and resp.status_code == 200:
    temps = resp.json()
    print(f"  [3.4] template_count={len(temps) if isinstance(temps, list) else 'N/A'}")

# ============================================================
# Phase 4: Edge Cases & Error Handling
# ============================================================
print("\n" + "="*60)
print("Phase 4: Edge Cases & Error Handling")
print("="*60)

test("empty input -> 422", "POST", "/api/cleaning/clean",
     {"content": "", "sandtable_type": "smart_traffic"}, expected_status=422, timeout=30)

test("too short input", "POST", "/api/cleaning/clean",
     {"content": "武汉微艺达", "sandtable_type": "smart_traffic"}, timeout=30)

test("XSS injection", "POST", "/api/cleaning/clean",
     {"content": "<script>alert('xss')</script>", "sandtable_type": "smart_traffic"}, timeout=30)

test("very long text (>3000 chars)", "POST", "/api/cleaning/clean",
     {"content": LONG_TEST, "sandtable_type": "smart_traffic"}, timeout=120)

test("invalid sandtable type -> 422", "POST", "/api/cleaning/clean",
     {"content": get_test_text(), "sandtable_type": "invalid_type"}, expected_status=422, timeout=30)

test("invalid platform id (no 404)", "GET", "/api/platform-monitor/platforms/nonexistent", timeout=30)

# ============================================================
# Phase 5: v2.0 New Features
# ============================================================
print("\n" + "="*60)
print("Phase 5: v2.0 New Features")
print("="*60)

test("POST /api/batch/clean", "POST", "/api/batch/clean",
     {"items": [{"content": get_test_text(), "sandtable_type": "smart_traffic"}]}, timeout=120)

resp = test("POST /api/compliance/check", "POST", "/api/compliance/check",
            {"content": get_test_text()}, timeout=60)
if resp and resp.status_code == 200:
    data = resp.json()
    print(f"  [5.2] compliance_risks={len(data.get('risks', [])) if isinstance(data, dict) else 'N/A'}")

resp = test("GET /api/usage/summary", "GET", "/api/usage/summary")
if resp and resp.status_code == 200:
    data = resp.json()
    print(f"  [5.3] usage_today={data.get('today_calls', 'N/A') if isinstance(data, dict) else 'N/A'}")

resp = test("GET /api/versions", "GET", "/api/versions")
if resp and resp.status_code == 200:
    data = resp.json()
    print(f"  [5.4] version_count={len(data) if isinstance(data, list) else 'N/A'}")

resp = test("GET /api/seo/check", "GET", "/api/seo/check?url=https://www.weiyida.com", timeout=30)
print(f"  [5.5] seo_check_status={resp.status_code if resp else 'N/A'}")

resp = test("GET /api/audit/logs", "GET", "/api/audit/logs?limit=5")
if resp and resp.status_code == 200:
    data = resp.json()
    print(f"  [5.6] audit_count={len(data.get('logs', [])) if isinstance(data, dict) else 'N/A'}")

# ============================================================
# Phase 6: Brand Monitor
# ============================================================
print("\n" + "="*60)
print("Phase 6: Brand Monitor")
print("="*60)

resp = test("GET /api/brand-monitor/sessions", "GET", "/api/brand-monitor/sessions")
if resp and resp.status_code == 200:
    data = resp.json()
    print(f"  [6.1] monitor_sessions={len(data) if isinstance(data, list) else 'N/A'}")

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
    print(f"\nFAILURES:")
    for e in ERRORS:
        print(f"  - {e}")
else:
    print("\nALL TESTS PASSED!")

print(f"\nCompleted at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
sys.exit(0 if FAIL == 0 else 1)
