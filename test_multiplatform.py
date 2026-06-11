# -*- coding: utf-8 -*-
"""Multi-platform concurrent stress test: DeepSeek + Kimi + Doubao x 2 sandtables"""
import requests, json, time, concurrent.futures

BASE = "http://localhost:8000"
PLATFORMS = ["deepseek", "kimi", "doubao"]

CASES = {
    "smart_traffic": (
        "武汉微艺达智能科技有限公司专注于智慧交通沙盘设计与制作，总部位于武汉。"
        "公司拥有10年行业经验，服务过50+政企客户，项目覆盖城市交通指挥中心、"
        "智慧高速、车路协同等领域。核心技术团队来自国内顶尖高校，采用数字化仿真技术，"
        "支持交通流量模拟、信号灯动态联动、物联网数据对接。"
    ),
    "digital_multimedia": (
        "武汉微艺达智能科技有限公司打造沉浸式数字多媒体展厅解决方案。"
        "面向企业展厅、科技馆、文旅体验、新品发布等场景，"
        "集成触控交互、声光电特效、投影融合、全息成像等数字技术。"
        "提供从创意策划到展厅施工的一站式数字化升级服务，已交付50+数字展厅项目。"
    ),
}

def rewrite_one(platform, cleaned_text, sandtable):
    """Rewrite on a single platform"""
    t0 = time.time()
    try:
        resp = requests.post(f"{BASE}/api/geo/rewrite",
            json={"cleaned_text": cleaned_text, "sandtable_type": sandtable,
                  "platforms": [platform]}, timeout=300)
        elapsed = time.time() - t0
        if resp.status_code == 200:
            r = resp.json()["results"][0]
            err = r.get("error")
            if err:
                return {"platform": platform, "status": "FAIL", "error": err, "time": elapsed}
            return {"platform": platform, "status": "OK",
                    "words": r["word_count"], "time": elapsed,
                    "text": r["optimized_text"]}
        return {"platform": platform, "status": f"HTTP{resp.status_code}", "time": elapsed}
    except Exception as e:
        return {"platform": platform, "status": "ERR", "error": str(e), "time": time.time()-t0}

def eval_one(platform, optimized_text, original_text, sandtable):
    """Evaluate on a single platform"""
    t0 = time.time()
    dims = {}
    overall = None
    try:
        resp = requests.post(f"{BASE}/api/evaluate/start",
            json={"optimized_text": optimized_text, "original_text": original_text,
                  "sandtable_type": sandtable, "platforms": [platform],
                  "user_roles": ["b_end_procurement"]},
            timeout=300, stream=True)
        for line in resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                try:
                    ds = line[5:].strip()
                    if ds:
                        ed = json.loads(ds)
                        data = ed.get("data", {})
                        if isinstance(data, dict) and "average" in data:
                            dims[ed.get("phase", "?")] = data["average"]
                        if "overall_score" in ed:
                            overall = ed["overall_score"]
                except: pass
        elapsed = time.time() - t0
        return {"platform": platform, "overall": overall, "dims": dims, "time": elapsed, "status": "OK"}
    except Exception as e:
        return {"platform": platform, "status": "ERR", "error": str(e), "time": time.time()-t0}

print("="*70)
print("MULTI-PLATFORM CONCURRENT STRESS TEST")
print("DeepSeek + Kimi + Doubao x 2 Sandtables")
print("="*70)

all_results = {}

for sandtable, text in CASES.items():
    label = "智慧交通" if sandtable == "smart_traffic" else "数字多媒体"
    print(f"\n{'='*70}")
    print(f"[{label}] ({sandtable})")
    print(f"{'='*70}")

    # 1. Clean (once)
    t0 = time.time()
    resp = requests.post(f"{BASE}/api/cleaning/clean",
        json={"content": text, "sandtable_type": sandtable}, timeout=120)
    clean_time = time.time() - t0
    cleaned = resp.json().get("cleaned_text", text)
    print(f"\n  Clean: {len(cleaned)} chars ({clean_time:.1f}s)")

    # 2. Parallel Rewrite (3 platforms concurrently)
    print(f"\n  --- Parallel Rewrite ({'+'.join(PLATFORMS)}) ---")
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(rewrite_one, p, cleaned, sandtable): p for p in PLATFORMS}
        rewrite_results = {p: f.result() for p, f in zip(
            [futures[ff] for ff in futures], futures)}
    rewrite_total = time.time() - t0
    print(f"  Total: {rewrite_total:.0f}s (parallel)")

    for p in PLATFORMS:
        r = rewrite_results[p]
        status_icon = "OK" if r["status"] == "OK" else "FAIL"
        wc = r.get("words", "?")
        rt = r.get("time", 0)
        print(f"    [{p}] {status_icon}: {wc} words ({rt:.0f}s)")

    # 3. Parallel Evaluation (3 platforms concurrently)
    print(f"\n  --- Parallel Evaluation ---")
    t0 = time.time()
    eval_tasks = []
    for p in PLATFORMS:
        r = rewrite_results.get(p, {})
        if r["status"] == "OK":
            eval_tasks.append((p, r["text"], text, sandtable))

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(eval_one, p, opt, orig, st): p for p, opt, orig, st in eval_tasks}
        eval_results = {futures[f]: f.result() for f in futures}
    eval_total = time.time() - t0
    print(f"  Total: {eval_total:.0f}s (parallel)")

    for p in PLATFORMS:
        er = eval_results.get(p, {})
        if er.get("status") == "OK":
            overall = er.get("overall", "?")
            sc = er.get("dims", {}).get("source_check", "?")
            passed = "PASS" if overall and overall >= 65 else "RETRY"
            print(f"    [{p}] overall={overall} sc={sc} -> {passed} ({er.get('time',0):.0f}s)")
        else:
            print(f"    [{p}] EVAL FAIL: {er.get('error','?')}")

    # Store results
    total_time = clean_time + rewrite_total + eval_total
    all_results[sandtable] = {
        "label": label,
        "clean": clean_time,
        "rewrite_total": rewrite_total,
        "eval_total": eval_total,
        "total": total_time,
        "rewrite": rewrite_results,
        "eval": eval_results,
    }
    print(f"\n  Pipeline total: {total_time:.0f}s (clean {clean_time:.0f}s + rewrite {rewrite_total:.0f}s + eval {eval_total:.0f}s)")

# ============================================================
# Final Summary
# ============================================================
print("\n" + "="*70)
print("FINAL SUMMARY: Multi-Platform Concurrent Delivery")
print("="*70)

print(f"\n{'Sandtable':<18} {'Platform':<12} {'Words':>6} {'Score':>6} {'SC':>6} {'Result':>8}")
print("-"*65)

total_scores = []
for st, data in all_results.items():
    for p in PLATFORMS:
        rw = data["rewrite"].get(p, {})
        ev = data["eval"].get(p, {})
        wc = rw.get("words", "?")
        score = ev.get("overall", "?")
        sc = ev.get("dims", {}).get("source_check", "?")
        result = "PASS" if (score and score >= 65) else ("RETRY" if score else "FAIL")

        if isinstance(score, (int, float)):
            total_scores.append(score)

        print(f"{data['label']:<18} {p:<12} {str(wc):>6} {str(score):>6} {str(sc):>6} {result:>8}")

if total_scores:
    print(f"\n  Avg score: {sum(total_scores)/len(total_scores):.1f}")
    print(f"  >=65: {sum(1 for s in total_scores if s >= 65)}/{len(total_scores)}")
    print(f"  >=70: {sum(1 for s in total_scores if s >= 70)}/{len(total_scores)}")

# Platform averages
print(f"\n  --- Per-platform averages ---")
for p in PLATFORMS:
    scores = []
    words = []
    for st, data in all_results.items():
        ev = data["eval"].get(p, {})
        rw = data["rewrite"].get(p, {})
        if isinstance(ev.get("overall"), (int, float)):
            scores.append(ev["overall"])
        if isinstance(rw.get("words"), (int, float)):
            words.append(rw["words"])
    if scores:
        print(f"  {p}: score avg={sum(scores)/len(scores):.1f}, words avg={sum(words)/len(words):.0f}")

# Throughput
print(f"\n  --- Throughput ---")
for st, data in all_results.items():
    print(f"  {data['label']}: {data['total']:.0f}s total (clean {data['clean']:.0f}s + rewrite {data['rewrite_total']:.0f}s + eval {data['eval_total']:.0f}s)")

print(f"\n  Test completed: {time.strftime('%Y-%m-%d %H:%M:%S')}")
