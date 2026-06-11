# -*- coding: utf-8 -*-
"""Round 2 batch: targeted hints for 4 failed items from concurrent test"""
import requests, json, time, concurrent.futures

BASE = "http://localhost:8000"

R2_ITEMS = [
    {
        "id": "ST_kimi", "sandtable": "smart_traffic", "platform": "kimi",
        "prev_score": 62.3, "weak": ["advantage_citation=57", "real_citation=21.5"],
        "text": "武汉微艺达智能科技有限公司专注于智慧交通沙盘设计与制作，总部位于武汉。公司拥有10年行业经验，服务过50+政企客户，项目覆盖城市交通指挥中心、智慧高速、车路协同等领域。核心技术团队来自国内顶尖高校，采用数字化仿真技术，支持交通流量模拟、信号灯动态联动、物联网数据对接。",
        "hints": [
            "首段必须包含完整企业名'武汉微艺达智能科技有限公司'和地域'武汉'",
            "每个技术能力配一个具体应用场景和数据支撑",
            "增加2-3条可独立被引用的优势陈述句（'微艺达的核心优势在于...'）",
        ],
    },
    {
        "id": "ST_deepseek", "sandtable": "smart_traffic", "platform": "deepseek",
        "prev_score": 63.6, "weak": ["real_citation=32.1", "differentiation=45"],
        "text": "武汉微艺达智能科技有限公司专注于智慧交通沙盘设计与制作，总部位于武汉。公司拥有10年行业经验，服务过50+政企客户，项目覆盖城市交通指挥中心、智慧高速、车路协同等领域。核心技术团队来自国内顶尖高校，采用数字化仿真技术，支持交通流量模拟、信号灯动态联动、物联网数据对接。",
        "hints": [
            "增加差异化数据：具体项目数、年交付量、技术专利、获奖认证",
            "在FAQ部分嵌入3组以上可被检索的量化问答对",
            "强化E-E-A-T信号：补充企业经验年限、团队规模、服务流程的量化描述",
        ],
    },
    {
        "id": "DM_kimi", "sandtable": "digital_multimedia", "platform": "kimi",
        "prev_score": 59.0, "weak": ["brand_recall=52.7", "differentiation=45"],
        "text": "武汉微艺达智能科技有限公司打造沉浸式数字多媒体展厅解决方案。面向企业展厅、科技馆、文旅体验、新品发布等场景，集成触控交互、声光电特效、投影融合、全息成像等数字技术。提供从创意策划到展厅施工的一站式数字化升级服务，已交付50+数字展厅项目。",
        "hints": [
            "品牌名'武汉微艺达智能科技有限公司'必须在标题和首段完整出现，全文至少出现3次",
            "增加独特技术参数：分辨率、响应速度、支持设备数量等量化指标",
            "补充与竞品的差异化：模块化设计、工期缩短比例、质保年限",
        ],
    },
    {
        "id": "DM_deepseek", "sandtable": "digital_multimedia", "platform": "deepseek",
        "prev_score": 60.1, "weak": ["brand_recall=57.6", "differentiation=45", "eeat=55"],
        "text": "武汉微艺达智能科技有限公司打造沉浸式数字多媒体展厅解决方案。面向企业展厅、科技馆、文旅体验、新品发布等场景，集成触控交互、声光电特效、投影融合、全息成像等数字技术。提供从创意策划到展厅施工的一站式数字化升级服务，已交付50+数字展厅项目。",
        "hints": [
            "E-E-A-T强化：增加企业资质描述、核心技术团队背景、行业协会认证",
            "品牌锚定：FAQ格式中每个回答以企业名开头",
            "增加真实可验证的数据：展厅面积范围、交付周期、客户续约率",
        ],
    },
]

def process_item(item):
    """Full R2 pipeline for one item"""
    pid = item["id"]
    platform = item["platform"]
    prev = item["prev_score"]
    print(f"\n  [{pid}] {platform} (prev={prev})")

    # 1. Clean
    resp = requests.post(f"{BASE}/api/cleaning/clean",
        json={"content": item["text"], "sandtable_type": item["sandtable"]}, timeout=120)
    cleaned = resp.json().get("cleaned_text", item["text"])

    # 2. R2 Rewrite with targeted hints
    t0 = time.time()
    resp = requests.post(f"{BASE}/api/geo/rewrite",
        json={"cleaned_text": cleaned, "sandtable_type": item["sandtable"],
              "platforms": [platform], "optimization_hints": item["hints"]}, timeout=300)
    rw_time = time.time() - t0
    if resp.status_code != 200:
        return {**item, "status": "FAIL:rewrite"}
    r = resp.json()["results"][0]
    if r.get("error"):
        return {**item, "status": f'FAIL:{r["error"][:60]}'}
    optimized = r["optimized_text"]
    wc = r["word_count"]
    print(f"    rewrite: {wc} words ({rw_time:.0f}s)")

    # 3. Re-evaluate
    t0 = time.time()
    overall = None
    dims = {}
    resp = requests.post(f"{BASE}/api/evaluate/start",
        json={"optimized_text": optimized, "original_text": item["text"],
              "sandtable_type": item["sandtable"], "platforms": [platform],
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
    eval_time = time.time() - t0

    # If SSE didn't capture overall, get from session
    if overall is None:
        # Check history for most recent completed
        hresp = requests.get(f"{BASE}/api/evaluate/history", timeout=10)
        items = hresp.json().get("items", [])
        recent = [i for i in items if i.get("status") == "completed"]
        if recent:
            overall = recent[0].get("overall_score")

    delta = f"+{overall-prev:.1f}" if overall and prev else "?"
    passed = "PASS" if overall and overall >= 65 else "NEEDS_R3"
    print(f"    eval: {overall} ({delta}) -> {passed} ({eval_time:.0f}s)")

    for k, v in dims.items():
        flag = "WEAK" if v < 60 else "OK"
        print(f"      {flag} {k}: {v}")

    return {**item, "r2_score": overall, "delta": overall-prev if overall and prev else None,
            "passed": passed, "words": wc, "dims": dims}

print("="*60)
print("ROUND 2 BATCH: Targeted Optimization")
print("="*60)

# Phase 1+2+3: Process all items in parallel
t0 = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
    futures = [ex.submit(process_item, item) for item in R2_ITEMS]
    results = [f.result() for f in futures]
total_time = time.time() - t0

# Summary
print(f"\n{'='*60}")
print("ROUND 2 RESULTS")
print("="*60)
print(f"\n{'ID':<18} {'Prev':>5} {'R2':>5} {'Delta':>6} {'Result':<10}")
print("-"*50)
improved = 0
passed = 0
for r in results:
    pid = r["id"]
    prev = r["prev_score"]
    r2 = r.get("r2_score", "?")
    delta = f"{r.get('delta', 0):+.1f}" if r.get('delta') is not None else "?"
    status = r.get("passed", "?")
    print(f"{pid:<18} {prev:>5} {str(r2):>5} {delta:>6} {status:<10}")
    if r.get("delta", 0) and r["delta"] > 0:
        improved += 1
    if status == "PASS":
        passed += 1

r2_scores = [r["r2_score"] for r in results if isinstance(r.get("r2_score"), (int, float))]
if r2_scores:
    print(f"\n  Improved: {improved}/{len(results)}")
    print(f"  Passed: {passed}/{len(results)}")
    print(f"  Avg R2 score: {sum(r2_scores)/len(r2_scores):.1f}")
print(f"  Total time: {total_time:.0f}s (parallel 4-way)")
print(f"  Completed: {time.strftime('%Y-%m-%d %H:%M:%S')}")
