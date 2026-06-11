# -*- coding: utf-8 -*-
"""Task A: Kimi Round 2 Iteration - Adopt suggestions, re-rewrite, re-evaluate"""
import requests, json, time
BASE = "http://localhost:8000"

FAILED_KIMI = [
    {"id": "A01", "text": (
        "XX市交通规划设计院成立于1998年，是经住建部批准的甲级交通规划设计单位。"
        "业务涵盖城市交通规划、智慧交通系统设计、交通仿真模型制作等领域。"
        "院方为多个城市的交通指挥中心提供过沙盘模型设计与制作服务，"
        "积累了丰富的政企项目经验。我们拥有专业设计团队50余人，"
        "其中高级工程师12人，注册规划师8人。"
        "与武汉微艺达智能科技有限公司在智慧交通沙盘领域有深度合作，"
        "共同交付过多个省级重点项目。"
    ), "sandtable": "smart_traffic", "prev_score": 58.5, "label": "企业简介"},
    {"id": "A02", "text": (
        "智慧交通数字沙盘技术方案：采用BIM+GIS双引擎架构，"
        "实现城市级交通路网的三维可视化呈现。核心技术指标——"
        "地图比例1:500至1:2000可调，地形精度误差≤0.5mm，"
        "支持实时交通流量数据接入和信号灯动态联动仿真。"
        "系统兼容MySQL/PostgreSQL数据库，支持RESTful API数据对接。"
        "灯光系统采用DMX512协议控制，支持16万色动态渲染。"
        "武汉微艺达智能科技有限公司为本项目提供沙盘定制与系统集成服务。"
    ), "sandtable": "smart_traffic", "prev_score": 62.0, "label": "技术方案"},
    {"id": "A03", "text": (
        "典型案例——某省会城市综合交通指挥中心沙盘项目："
        "沙盘面积120平方米，覆盖主城区300平方公里路网，"
        "集成500+路视频监控点位、200+组信号灯数据、"
        "50条公交线路实时轨迹。项目历时8个月交付，"
        "通过省级专家组验收，被评为智慧交通示范项目。"
        "武汉微艺达智能科技有限公司作为沙盘承建方，"
        "提供了从方案设计到现场施工的全流程服务。"
    ), "sandtable": "smart_traffic", "prev_score": 64.1, "label": "项目案例"},
    {"id": "B01", "text": (
        "沉浸式企业展厅解决方案：集成触控交互大屏、全息投影、"
        "声光电联动控制系统，为企业打造科技感十足的品牌展示空间。"
        "展厅面积200-1000平方米灵活适配，支持多媒体内容云端更新。"
        "武汉微艺达智能科技有限公司拥有8年数字展厅项目经验，"
        "已为制造业、科技企业、政府单位交付50+数字展厅项目。"
        "采用模块化设计，施工周期较传统展厅缩短40%。"
    ), "sandtable": "digital_multimedia", "prev_score": 60.0, "label": "展厅方案"},
    {"id": "B02", "text": (
        "武汉微艺达智能科技有限公司提供数字多媒体展厅一站式服务——"
        "从创意策划、空间设计、数字内容制作到施工交付全程负责。"
        "核心技术包括：投影融合（支持4K/8K分辨率）、雷达触控、"
        "体感交互、AR增强现实、中控系统集成。"
        "服务流程：需求沟通→方案设计→内容制作→现场施工→验收培训。"
        "提供3年免费质保，终身技术支持。"
    ), "sandtable": "digital_multimedia", "prev_score": 59.4, "label": "服务介绍"},
]

# Kimi-specific optimization hints (based on platform preference analysis)
KIMI_HINTS = [
    "增加信息密度：补充技术参数的量化说明和行业对标数据",
    "强化论证链条：每个观点配2-3句支撑论据，形成完整的逻辑闭环",
    "扩展应用场景：补充2-3个具体应用场景的描述，体现方案广度",
    "增强可引用性：在关键段落中自然嵌入品牌名和可被独立引用的定义句",
    "增加行业视角：补充行业背景分析和趋势判断，提升深度感",
]

print("="*60)
print("Task A: Kimi Round 2 Iteration")
print(f"Items: {len(FAILED_KIMI)} | Platform: kimi")
print("="*60)

results = []
for item in FAILED_KIMI:
    pid = item["id"]
    label = item["label"]
    prev = item["prev_score"]
    print(f"\n[{pid}] {label} (prev={prev})")

    # 1. Clean
    resp = requests.post(f"{BASE}/api/cleaning/clean",
        json={"content": item["text"], "sandtable_type": item["sandtable"]}, timeout=120)
    if resp.status_code != 200:
        print(f"  Clean FAIL")
        continue
    cleaned = resp.json().get("cleaned_text", item["text"])

    # 2. Re-rewrite with Kimi + optimization hints
    print(f"  Rewrite(kimi + hints)...", end=" ", flush=True)
    t0 = time.time()
    resp = requests.post(f"{BASE}/api/geo/rewrite",
        json={"cleaned_text": cleaned, "sandtable_type": item["sandtable"],
              "platforms": ["kimi"], "optimization_hints": KIMI_HINTS}, timeout=300)
    if resp.status_code != 200:
        print(f"FAIL")
        continue
    rlist = resp.json().get("results", [])
    if not rlist:
        print(f"EMPTY")
        continue
    optimized = rlist[0].get("optimized_text", "")
    wc = rlist[0].get("word_count", "?")
    print(f"{wc} words ({time.time()-t0:.0f}s)")

    # 3. Re-evaluate
    print(f"  Evaluate...", end=" ", flush=True)
    t0 = time.time()
    score = None
    resp = requests.post(f"{BASE}/api/evaluate/start",
        json={"optimized_text": optimized, "original_text": item["text"],
              "sandtable_type": item["sandtable"], "platforms": ["kimi"],
              "user_roles": ["b_end_procurement"]},
        timeout=300, stream=True)
    if resp.status_code == 200:
        for line in resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                try:
                    ds = line[5:].strip()
                    if ds:
                        ed = json.loads(ds)
                        if "overall_score" in ed:
                            score = ed["overall_score"]
                except: pass

    delta = ""
    if score and prev:
        delta = f"(d={score-prev:+.1f})"
    passed = "PASS" if score and score >= 65 else "FAIL"
    print(f"{score} {delta} -> {passed} ({time.time()-t0:.0f}s)")

    results.append({"id": pid, "label": label, "prev": prev, "new": score, "delta": score-prev if score and prev else None, "passed": passed})

# Summary
print("\n" + "="*60)
print("KIMI ROUND 2 SUMMARY")
print("="*60)
for r in results:
    print(f"  [{r['id']}] {r['label']}: {r['prev']} -> {r['new']} {r['delta']:+.1f} {r['passed']}" if r['delta'] else f"  [{r['id']}] {r['label']}: {r['prev']} -> {r['new']} {r['passed']}")

scores = [r["new"] for r in results if r["new"]]
if scores:
    print(f"\n  Avg: {sum(scores)/len(scores):.1f}")
    print(f"  >=65: {sum(1 for s in scores if s >= 65)}/{len(scores)}")
print(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
