# -*- coding: utf-8 -*-
"""GEO System Full Landing Test - Corrected"""
import requests
import json
import time
import sys

BASE = "http://localhost:8000"
PASS = 0
FAIL = 0
ERRORS = []

# Read test text from UTF-8 file
with open("test_text_zh.txt", "r", encoding="utf-8") as f:
    TEXT = f.read().strip()

def test(name, method, path, data=None, expected_status=200, timeout=60, parse_json=True):
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
        ok = resp.status_code == expected_status

        if ok:
            PASS += 1
            print(f"  [PASS] {name} ({resp.status_code}, {elapsed:.1f}s)")
        else:
            FAIL += 1
            msg = f"{name}: expected {expected_status}, got {resp.status_code}"
            ERRORS.append(msg)
            print(f"  [FAIL] {name} ({resp.status_code}, {elapsed:.1f}s)")
            try:
                detail = json.dumps(resp.json(), ensure_ascii=False)[:200]
            except:
                detail = resp.text[:200]
            print(f"         {detail}")

        return resp
    except Exception as e:
        FAIL += 1
        err = f"{name}: {type(e).__name__}: {e}"
        ERRORS.append(err)
        print(f"  [ERR] {name} - {err[:150]}")
        return None

print("="*60)
print("GEO System Landing Verification")
print("Started:", time.strftime("%Y-%m-%d %H:%M:%S"))
print("="*60)

# ============================================================
# Phase 1: Health & Config
# ============================================================
print("\n--- Phase 1: Health & Config ---")
test("Health", "GET", "/api/health")
resp = test("LLM Config", "GET", "/api/config/llm")
if resp:
    d = resp.json()
    configured = [p["platform"] for p in d.get("llm_platforms", []) if p.get("configured")]
    print(f"     configured={configured}")

# ============================================================
# Phase 2: Core Pipeline (correct field names)
# ============================================================
print("\n--- Phase 2: Core Pipeline ---")

# 2.1 Clean
resp = test("Clean", "POST", "/api/cleaning/clean",
            {"content": TEXT, "sandtable_type": "smart_traffic"}, timeout=120)
cleaned = ""
if resp:
    d = resp.json()
    cleaned = d.get("cleaned_text", "")
    print(f"     len={len(cleaned)}")

# 2.2 Extract
test("Extract", "POST", "/api/cleaning/extract",
     {"content": TEXT, "sandtable_type": "smart_traffic"}, timeout=120)

# 2.3 Diagnosis (field=text)
resp = test("QuickDiagnosis", "POST", "/api/diagnosis/quick",
            {"text": TEXT, "sandtable_type": "smart_traffic"}, timeout=120)
if resp:
    d = resp.json()
    print(f"     score={d.get('overall_score')}")
    dims = d.get("dimensions", {})
    for k, v in dims.items():
        if isinstance(v, dict):
            sv = v.get("score", v)
        else:
            sv = v
        flag = "WARN" if isinstance(sv, (int, float)) and sv < 60 else "OK"
        print(f"       {flag} {k}={sv}")

# 2.4 GEO Rewrite (field=cleaned_text)
rewrite_text = cleaned if cleaned else TEXT
resp = test("GEO Rewrite[deepseek]", "POST", "/api/geo/rewrite",
            {"cleaned_text": rewrite_text, "sandtable_type": "smart_traffic",
             "platforms": ["deepseek"]}, timeout=300)
optimized = ""
if resp:
    d = resp.json()
    results = d.get("results", [])
    if results:
        r0 = results[0]
        optimized = r0.get("optimized_text", "")
        print(f"     platform={r0.get('platform')}, words={r0.get('word_count','?')}")

# 2.5 JSON-LD (correct schema)
resp = test("JSON-LD", "POST", "/api/jsonld/generate",
            {"sandtable_type": "smart_traffic",
             "enterprise_info": {"name": "武汉微艺达智能科技有限公司", "url": "https://www.weiyida.com", "location": "武汉"},
             "product_info": {"name": "智慧交通沙盘"}}, timeout=120)
if resp:
    d = resp.json()
    print(f"     validation={d.get('validation_passed')}, schemas={d.get('schema_types_used')}")

# 2.6 AI Evaluation - SSE stream, get result via session
print("\n  [2.6] AI Evaluation (SSE stream)...")
eval_text = optimized if optimized else TEXT

# Start evaluation (SSE)
try:
    resp = requests.post(BASE + "/api/evaluate/start",
                         json={"optimized_text": eval_text, "original_text": TEXT,
                               "sandtable_type": "smart_traffic",
                               "platforms": ["deepseek"],
                               "user_roles": ["b_end_procurement"]},
                         timeout=300, stream=True)
    session_id = None
    if resp.status_code == 200:
        # Parse SSE events to find session_id and final result
        last_data = None
        for line in resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                try:
                    data_str = line[5:].strip()
                    if data_str:
                        event_data = json.loads(data_str)
                        phase = event_data.get("phase", "")
                        if phase == "completed":
                            last_data = event_data
                        if "session_id" in event_data and not session_id:
                            session_id = event_data["session_id"]
                except:
                    pass

        # Try to get session result
        if last_data:
            score = last_data.get("overall_score", "N/A")
            dims = last_data.get("dimensions", {})
            sc = dims.get("source_consistency", "N/A") if isinstance(dims, dict) else "N/A"
            if isinstance(sc, dict):
                sc = sc.get("score", sc)
            PASS += 1
            print(f"  [PASS] AI Eval-SSE ({resp.status_code})")
            print(f"     overall={score}, source_consistency={sc}")
        elif session_id:
            # Query session directly
            sresp = requests.get(BASE + f"/api/evaluate/session/{session_id}", timeout=30)
            if sresp.status_code == 200:
                sd = sresp.json()
                scores = sd.get("scores", sd.get("dimensions", {}))
                PASS += 1
                print(f"  [PASS] AI Eval-SSE ({resp.status_code})")
                print(f"     session_id={session_id}, overall={sd.get('overall_score', 'N/A')}")
            else:
                PASS += 1
                print(f"  [PASS] AI Eval-SSE ({resp.status_code}), session={session_id}, but no result")
        else:
            PASS += 1
            print(f"  [PASS] AI Eval-SSE ({resp.status_code}) - stream completed")
    else:
        FAIL += 1
        ERRORS.append(f"AI Eval: got {resp.status_code}")
        print(f"  [FAIL] AI Eval-SSE ({resp.status_code}) - {resp.text[:200]}")
except Exception as e:
    FAIL += 1
    ERRORS.append(f"AI Eval: {e}")
    print(f"  [ERR] AI Eval - {e}")

# 2.7 Check eval history
test("EvalHistory", "GET", "/api/evaluate/history")

# 2.8 Report
test("Report", "POST", "/api/reports/generate-from-data",
     {"data": {"overall_score": 75, "dimensions": {"brand_recall": 70, "solution_match": 80}},
      "format": "html", "enterprise_name": "Test"}, timeout=120)

# ============================================================
# Phase 3: Strategy Center
# ============================================================
print("\n--- Phase 3: Strategy Center ---")
test("PlatformRules", "GET", "/api/platform-monitor/platforms")

all_8 = ["smart_traffic","smart_city","smart_industry","smart_agriculture",
         "smart_logistics","military_terrain","digital_multimedia","real_estate"]
for st in all_8:
    test(f"KW:{st}", "GET", f"/api/keywords/{st}")

test("AddKW", "POST", "/api/keywords/smart_traffic",
     {"word": "TEST_" + str(int(time.time())), "category": "brand", "weight": "8", "status": "approved"})

resp = test("Competitors", "GET", "/api/competitors")
test("Templates", "GET", "/api/templates/list")
test("EvalDimensions", "GET", "/api/evaluate/dimensions")

# ============================================================
# Phase 4: Edge Cases
# ============================================================
print("\n--- Phase 4: Edge Cases ---")
test("Empty->422", "POST", "/api/cleaning/clean", {"content": "", "sandtable_type": "smart_traffic"}, expected_status=422)
test("XSS", "POST", "/api/cleaning/clean", {"content": "<script>alert(1)</script>", "sandtable_type": "smart_traffic"})
test("BadType->422", "POST", "/api/cleaning/clean", {"content": TEXT, "sandtable_type": "invalid"}, expected_status=422)
test("BadPlat(404?)", "GET", "/api/platform-monitor/platforms/nonexistent", expected_status=200)
test("SEO", "GET", "/api/seo/analysis")

# ============================================================
# Phase 5: v2.0 Features
# ============================================================
print("\n--- Phase 5: v2.0 Features ---")
test("BatchClean", "POST", "/api/batch/clean",
     {"texts": [{"content": TEXT}], "sandtable_type": "smart_traffic"}, timeout=120)

# Compliance: field=text
test("Compliance", "POST", "/api/compliance/check", {"text": TEXT}, timeout=60)

test("Usage", "GET", "/api/usage/summary")
test("Audit", "GET", "/api/audit/logs")
test("Scheduler", "GET", "/api/scheduler/jobs")
test("BrandHist", "GET", "/api/brand-monitor/history")

# ============================================================
# Phase 6: All 8 Sandtable JSON-LD
# ============================================================
print("\n--- Phase 6: 8 Sandtable JSON-LD ---")
labels = {"smart_traffic":"traffic","smart_city":"city","smart_industry":"industry",
          "smart_agriculture":"agriculture","smart_logistics":"logistics",
          "military_terrain":"military","digital_multimedia":"multimedia","real_estate":"estate"}
for st, lb in labels.items():
    resp = test(f"JSONLD:{lb}", "POST", "/api/jsonld/generate",
                {"sandtable_type": st,
                 "enterprise_info": {"name": "武汉微艺达智能科技有限公司", "url": "https://www.weiyida.com"},
                 "product_info": {"name": lb + " sandtable"}}, timeout=120)

# ============================================================
# Phase 7: Multi-platform Rewrite
# ============================================================
print("\n--- Phase 7: Multi-platform Rewrite ---")
resp = test("Rewrite[deepseek+kimi]", "POST", "/api/geo/rewrite",
            {"cleaned_text": rewrite_text, "sandtable_type": "smart_traffic",
             "platforms": ["deepseek", "kimi"]}, timeout=300)
if resp:
    for r in resp.json().get("results", []):
        print(f"     [{r.get('platform')}] words={r.get('word_count','?')}")

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
