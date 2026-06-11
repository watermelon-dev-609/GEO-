# -*- coding: utf-8 -*-
"""P1-1 Fix Verification - Compare evaluation scores before/after fix"""
import requests
import json
import time

BASE = "http://localhost:8000"

with open("test_text_zh.txt", "r", encoding="utf-8") as f:
    TEXT = f.read().strip()

print("="*60)
print("P1-1 Fix Verification Test")
print("="*60)

# Step 1: Clean + Rewrite (reuse if cached, otherwise regenerate)
print("\n[1] Clean + Rewrite...")
resp = requests.post(BASE + "/api/cleaning/clean",
                     json={"content": TEXT, "sandtable_type": "smart_traffic"}, timeout=120)
cleaned = resp.json().get("cleaned_text", TEXT)
print(f"    cleaned={len(cleaned)} chars")

resp = requests.post(BASE + "/api/geo/rewrite",
                     json={"cleaned_text": cleaned, "sandtable_type": "smart_traffic",
                           "platforms": ["deepseek"]}, timeout=300)
optimized = ""
if resp.status_code == 200:
    results = resp.json().get("results", [])
    if results:
        optimized = results[0].get("optimized_text", "")
        print(f"    optimized={results[0].get('word_count')} words")

# Step 2: Run evaluation (SSE stream)
print("\n[2] Running evaluation (SSE)...")
eval_text = optimized if optimized else TEXT
t0 = time.time()

resp = requests.post(BASE + "/api/evaluate/start",
                     json={"optimized_text": eval_text, "original_text": TEXT,
                           "sandtable_type": "smart_traffic",
                           "platforms": ["deepseek"],
                           "user_roles": ["b_end_procurement"]},
                     timeout=300, stream=True)

session_id = None
phases_data = {}
for line in resp.iter_lines(decode_unicode=True):
    if line and line.startswith("data:"):
        try:
            data_str = line[5:].strip()
            if data_str:
                event_data = json.loads(data_str)
                phase = event_data.get("phase", "")
                data = event_data.get("data", {})
                if "session_id" in event_data:
                    session_id = event_data["session_id"]
                if phase and phase != "progress":
                    # Print dimension results
                    if isinstance(data, dict) and "average" in data:
                        phases_data[phase] = data["average"]
                        print(f"    {phase}: {data['average']}")
                    elif isinstance(data, dict) and "overall_score" in data:
                        phases_data["overall"] = data["overall_score"]
                        print(f"    overall: {data['overall_score']}")
        except:
            pass

elapsed = time.time() - t0
print(f"\n[3] Evaluation completed in {elapsed:.0f}s")

# Step 3: Get session details
if session_id:
    print(f"\n[4] Session detail: {session_id}")
    sresp = requests.get(BASE + f"/api/evaluate/session/{session_id}", timeout=30)
    if sresp.status_code == 200:
        sd = sresp.json()
        phases = sd.get("phases", {})
        print("\n--- Dimension Scores ---")
        for phase_name, phase_data in phases.items():
            if phase_name in ("generating_questions",):
                continue
            result = phase_data.get("result", {})
            avg = result.get("average", "N/A")
            if avg != "N/A":
                print(f"  {phase_name}: {avg}")

# Step 4: Compare with historical
print("\n[5] Historical comparison...")
hresp = requests.get(BASE + "/api/evaluate/history", timeout=30)
if hresp.status_code == 200:
    items = hresp.json().get("items", [])
    recent = items[:5]
    scores = [s.get("overall_score", 0) for s in recent]
    if scores:
        print(f"  Recent 5 scores: {scores}")
        print(f"  Average: {sum(scores)/len(scores):.1f}")
        above_50 = sum(1 for s in scores if s > 50)
        print(f"  Scores above 50: {above_50}/{len(scores)}")

print("\nDone!")
