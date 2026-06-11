# -*- coding: utf-8 -*-
"""GEO System Performance & Boundary Tests"""
import requests
import json
import time
import sys
import concurrent.futures

BASE = "http://localhost:8000"

with open("test_text_zh.txt", "r", encoding="utf-8") as f:
    TEXT = f.read().strip()

LONG_TEXT = TEXT * 20  # ~3000+ chars
TINY_TEXT = "武汉微艺达"  # <50 chars

def test(name, method, path, data=None, expected=200, timeout=60):
    url = BASE + path
    t0 = time.time()
    try:
        if method == "GET":
            resp = requests.get(url, timeout=timeout)
        else:
            resp = requests.post(url, json=data, timeout=timeout)
        elapsed = time.time() - t0
        ok = resp.status_code == expected
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name} -> {resp.status_code} ({elapsed:.1f}s)")
        return ok, elapsed, resp
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [ERR] {name} -> {e} ({elapsed:.1f}s)")
        return False, elapsed, None

print("="*60)
print("GEO System Performance & Boundary Tests")
print("="*60)

# ============================================================
# Test 1: Long Text (>3000 chars)
# ============================================================
print("\n--- Test 1: Long Text (>3000 chars) ---")
print(f"  Input length: {len(LONG_TEXT)} chars")
ok, t, resp = test("Clean long text", "POST", "/api/cleaning/clean",
                    {"content": LONG_TEXT, "sandtable_type": "smart_traffic"}, timeout=120)
if resp:
    d = resp.json()
    print(f"  Output length: {len(d.get('cleaned_text', ''))}")

# ============================================================
# Test 2: Concurrent API Calls (5 concurrent reads)
# ============================================================
print("\n--- Test 2: Concurrency (5 parallel health checks) ---")
def health_check(i):
    t0 = time.time()
    try:
        resp = requests.get(f"{BASE}/api/health", timeout=30)
        return time.time() - t0, resp.status_code
    except Exception as e:
        return time.time() - t0, str(e)

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
    futures = [ex.submit(health_check, i) for i in range(5)]
    results = [f.result() for f in futures]

times = []
for i, (t, code) in enumerate(results):
    times.append(t)
    print(f"  Request {i+1}: {code} ({t:.2f}s)")
print(f"  Avg: {sum(times)/len(times):.2f}s, Max: {max(times):.2f}s, Min: {min(times):.2f}s")

# ============================================================
# Test 3: Multi-platform Concurrent Rewrite
# ============================================================
print("\n--- Test 3: Multi-platform Rewrite (DeepSeek + Kimi) ---")
ok, t, resp = test("Rewrite[deepseek+kimi]", "POST", "/api/geo/rewrite",
                    {"cleaned_text": TEXT, "sandtable_type": "smart_traffic",
                     "platforms": ["deepseek", "kimi"]}, timeout=300)
if resp:
    for r in resp.json().get("results", []):
        print(f"  [{r.get('platform')}] words={r.get('word_count')}")

# ============================================================
# Test 4: Data Pressure - Read with large history
# ============================================================
print("\n--- Test 4: Data Pressure (eval history + keywords + audit) ---")
endpoints = [
    ("Eval History", "/api/evaluate/history"),
    ("Keywords(smart_traffic)", "/api/keywords/smart_traffic"),
    ("Competitors", "/api/competitors"),
    ("Audit Logs(50)", "/api/audit/logs?limit=50"),
    ("Platform Rules", "/api/platform-monitor/platforms"),
]
for name, path in endpoints:
    test(f"Load:{name}", "GET", path, timeout=30)

# ============================================================
# Test 5: Edge Input Types
# ============================================================
print("\n--- Test 5: Edge Input Types ---")

# Numbers only
test("Numbers only", "POST", "/api/cleaning/clean",
     {"content": "123456789012345678901234567890123456789012345678901234567890", "sandtable_type": "smart_traffic"}, timeout=30)

# English only
test("English only", "POST", "/api/cleaning/clean",
     {"content": "This is a test content for smart traffic sandbox design and manufacturing. " * 5, "sandtable_type": "smart_traffic"}, timeout=30)

# Emoji in text
test("With emoji", "POST", "/api/cleaning/clean",
     {"content": TEXT + " 😊🎉✨", "sandtable_type": "smart_traffic"}, timeout=30)

# Special chars
test("Special chars", "POST", "/api/cleaning/clean",
     {"content": TEXT + " <>&\"'", "sandtable_type": "smart_traffic"}, timeout=30)

# ============================================================
# Test 6: Batch Processing
# ============================================================
print("\n--- Test 6: Batch Processing ---")
test("BatchClean(3 items)", "POST", "/api/batch/clean",
     {"texts": [{"content": TEXT} for _ in range(3)], "sandtable_type": "smart_traffic"}, timeout=120)

# ============================================================
# Test 7: Compliance Edge Cases
# ============================================================
print("\n--- Test 7: Compliance Edge Cases ---")
# Contains superlatives
test("Compliance:superlative", "POST", "/api/compliance/check",
     {"text": "我们是行业第一、国内最好的沙盘公司，100%满意保证"}, timeout=30)

# Contains competitor attack
test("Compliance:competitor", "POST", "/api/compliance/check",
     {"text": "竞品公司技术落后，质量差，不如我们"}, timeout=30)

# Clean text
test("Compliance:clean", "POST", "/api/compliance/check",
     {"text": TEXT}, timeout=30)

# ============================================================
# Test 8: P0 Bug Verification
# ============================================================
print("\n--- Test 8: P0 Bug Regression ---")
# P0-1: Keywords add (was NameError: category)
resp = test("P0-1:AddKeyword", "POST", "/api/keywords/smart_traffic",
            {"word": "P0_REGRESSION_TEST", "category": "brand", "weight": "8", "status": "approved"}, timeout=30)

# P0-2: Report generate (was NameError: report_format)
resp = test("P0-2:ReportGen", "POST", "/api/reports/generate-from-data",
            {"data": {"overall_score": 80, "dimensions": {"test": 80}}, "format": "html", "enterprise_name": "P0_Test"}, timeout=30)

# P0-3: Extract (was AttributeError: SandtableType.smart_traffic)
resp = test("P0-3:Extract", "POST", "/api/cleaning/extract",
            {"content": TEXT, "sandtable_type": "smart_traffic"}, timeout=30)

# ============================================================
# Test 9: P1 Issues Check
# ============================================================
print("\n--- Test 9: P1 Issues Check ---")

# P1-1: Source consistency check
print("  [INFO] Checking source_consistency scores in recent evals...")
resp = requests.get(f"{BASE}/api/evaluate/history", timeout=30)
if resp.status_code == 200:
    history = resp.json()
    # history could be a list directly or wrapped
    if isinstance(history, list):
        sessions = history
    elif isinstance(history, dict):
        sessions = history.get("sessions", history.get("history", []))
    else:
        sessions = []
    if sessions:
        recent = sessions[:5]  # last 5
        for s in recent:
            dims = s.get("dimensions", s.get("scores", {}))
            sc = dims.get("source_consistency", "N/A")
            if isinstance(sc, dict):
                sc = sc.get("score", sc)
            overall = s.get("overall_score", "N/A")
            print(f"  session={s.get('session_id','?')[:12]}... overall={overall} source_consistency={sc}")

# P1-3: Stream rewrite validation check
print("\n  [INFO] P1-3: Stream rewrite validation...")
resp = requests.post(f"{BASE}/api/geo/rewrite",
                     json={"cleaned_text": TEXT, "sandtable_type": "smart_traffic",
                           "platforms": ["deepseek"]}, timeout=300)
if resp.status_code == 200:
    results = resp.json().get("results", [])
    if results:
        txt = results[0].get("optimized_text", "")
        # Check for enterprise name presence
        has_company = "微艺达" in txt or "武汉微艺达" in txt
        print(f"  Company name present: {has_company}")
        print(f"  Word count: {len(txt)}")

# P1-5: Empty text for unconfigured platforms
print("\n  [INFO] P1-5: Unconfigured platform response...")
resp = requests.post(f"{BASE}/api/geo/rewrite",
                     json={"cleaned_text": TEXT, "sandtable_type": "smart_traffic",
                           "platforms": ["doubao"]}, timeout=120)
if resp.status_code == 200:
    results = resp.json().get("results", [])
    for r in results:
        wc = r.get("word_count", r.get("error", "N/A"))
        print(f"  [{r.get('platform')}] result: {wc}")

print("\n" + "="*60)
print("Performance & Boundary Tests Complete")
print("="*60)
