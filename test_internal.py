# -*- coding: utf-8 -*-
"""Engineer Internal Test - 8 sandtable types x full pipeline"""
import requests
import json
import time
import os

BASE = "http://localhost:8000"
RESULTS = []

# 8 sandtable types with realistic business copy
TEST_CASES = {
    "smart_traffic": {
        "label": "智慧交通沙盘",
        "text": (
            "武汉微艺达智能科技有限公司专注于智慧交通沙盘设计与制作，"
            "总部位于武汉。公司拥有10年行业经验，服务过50+政企客户，"
            "项目覆盖城市交通指挥中心、智慧高速、车路协同等领域。"
            "核心技术团队来自国内顶尖高校，采用数字化仿真技术，"
            "支持交通流量模拟、信号灯动态联动、物联网数据对接。"
            "典型项目包括某省会城市交通指挥中心沙盘、"
            "某智慧高速全息感知沙盘系统。"
        ),
    },
    "smart_city": {
        "label": "智慧城市沙盘",
        "text": (
            "武汉微艺达智能科技有限公司是专业的智慧城市数字沙盘定制厂家。"
            "公司深耕城市大脑、数字政府、一网统管类项目的可视化呈现，"
            "具备从城市总体规划到片区详规的多尺度展现能力。"
            "采用大数据可视化、数字孪生、应急指挥调度等技术，"
            "已完成多个市级城市运营管理中心沙盘项目。"
        ),
    },
    "smart_industry": {
        "label": "智慧工业沙盘",
        "text": (
            "武汉微艺达智能科技有限公司提供智慧工厂数字孪生沙盘定制服务。"
            "面向智能工厂、产线仿真、工业互联网等领域，"
            "实现设备互联可视化、产线仿真模拟、MES系统数据对接。"
            "公司拥有工业数字孪生核心技术，支持从产线级到园区级的多尺度呈现，"
            "已为多家制造企业交付智能工厂仿真沙盘。"
        ),
    },
    "smart_agriculture": {
        "label": "智慧农业沙盘",
        "text": (
            "武汉微艺达智能科技有限公司承接数字农业与智慧农业沙盘项目。"
            "服务范围覆盖智能灌溉、精准种植、农产品溯源、乡村振兴示范等场景。"
            "以科技兴农为理念，将物联网传感数据、遥感影像与实物沙盘融合，"
            "打造可交互的现代农业科技示范区展示模型。"
        ),
    },
    "smart_logistics": {
        "label": "智慧物流沙盘",
        "text": (
            "武汉微艺达智能科技有限公司专注智慧仓储与物流自动化沙盘定制。"
            "面向AGV调度、供应链可视化、数字孪生仓等应用场景，"
            "实现仓储布局模拟、物流路径优化、设备运行状态实时映射。"
            "为物流园区和电商仓储企业提供从方案设计到沙盘交付的全流程服务。"
        ),
    },
    "military_terrain": {
        "label": "军事地形沙盘",
        "text": (
            "武汉微艺达智能科技有限公司具备军事地形沙盘模型的精密制作能力。"
            "面向军事院校教学、作战推演、国防教育等专业场景，"
            "严格执行比例标准化、地形精准还原、战术仿真等工艺标准。"
            "以严谨的工艺流程和保密合规为原则，为军方院校提供高精度地形模型。"
        ),
    },
    "digital_multimedia": {
        "label": "数字多媒体展厅",
        "text": (
            "武汉微艺达智能科技有限公司打造沉浸式数字多媒体展厅解决方案。"
            "面向企业展厅、科技馆、文旅体验、新品发布等场景，"
            "集成触控交互、声光电特效、投影融合、全息成像等数字技术。"
            "提供从创意策划到展厅施工的一站式数字化升级服务。"
        ),
    },
    "real_estate": {
        "label": "地产规划展厅",
        "text": (
            "武汉微艺达智能科技有限公司承接地产营销展厅与城市规划展览沙盘项目。"
            "服务范围包括地产沙盘、政府规划展示、品牌展厅等，"
            "在城市空间还原、建筑模型精细度、灯光系统设计方面具备成熟工艺。"
            "为多家地产开发商和城市规划馆提供专业沙盘模型定制服务。"
        ),
    },
}

def run_full_pipeline(case_id, label, text):
    """Run full pipeline: clean -> diagnose -> rewrite -> jsonld -> evaluate -> report"""
    result = {"case": label, "steps": {}}
    t0 = time.time()

    # 1. Clean
    try:
        resp = requests.post(f"{BASE}/api/cleaning/clean",
                            json={"content": text, "sandtable_type": case_id}, timeout=120)
        if resp.status_code == 200:
            d = resp.json()
            cleaned = d.get("cleaned_text", text)
            result["steps"]["clean"] = f"OK ({len(cleaned)} chars)"
        else:
            result["steps"]["clean"] = f"FAIL {resp.status_code}"
            return result
    except Exception as e:
        result["steps"]["clean"] = f"ERR: {e}"
        return result

    # 2. Diagnose
    try:
        resp = requests.post(f"{BASE}/api/diagnosis/quick",
                            json={"text": cleaned, "sandtable_type": case_id}, timeout=60)
        if resp.status_code == 200:
            d = resp.json()
            result["steps"]["diagnose"] = d.get("overall_score", "?")
    except:
        result["steps"]["diagnose"] = "ERR"

    # 3. GEO Rewrite (DeepSeek)
    try:
        resp = requests.post(f"{BASE}/api/geo/rewrite",
                            json={"cleaned_text": cleaned, "sandtable_type": case_id,
                                  "platforms": ["deepseek"]}, timeout=300)
        if resp.status_code == 200:
            d = resp.json()
            results_list = d.get("results", [])
            if results_list:
                r0 = results_list[0]
                optimized = r0.get("optimized_text", "")
                result["steps"]["rewrite"] = f"OK ({r0.get('word_count', '?')} words)"
            else:
                result["steps"]["rewrite"] = "EMPTY"
        else:
            result["steps"]["rewrite"] = f"FAIL {resp.status_code}"
            return result
    except Exception as e:
        result["steps"]["rewrite"] = f"ERR: {e}"
        return result

    # 4. JSON-LD
    try:
        resp = requests.post(f"{BASE}/api/jsonld/generate",
                            json={"sandtable_type": case_id,
                                  "enterprise_info": {"name": "武汉微艺达智能科技有限公司",
                                                     "url": "https://www.weiyida.com",
                                                     "location": "武汉"},
                                  "product_info": {"name": label}}, timeout=60)
        if resp.status_code == 200:
            d = resp.json()
            result["steps"]["jsonld"] = f"OK (valid={d.get('validation_passed')})"
    except:
        result["steps"]["jsonld"] = "ERR"

    # 5. AI Evaluation (SSE)
    try:
        resp = requests.post(f"{BASE}/api/evaluate/start",
                            json={"optimized_text": optimized if optimized else cleaned,
                                  "sandtable_type": case_id,
                                  "platforms": ["deepseek"],
                                  "user_roles": ["b_end_procurement"]},
                            timeout=300, stream=True)
        for line in resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                try:
                    ds = line[5:].strip()
                    if ds:
                        ed = json.loads(ds)
                        if ed.get("phase") == "completed" and "overall_score" in ed.get("data", {}):
                            result["steps"]["eval"] = ed["data"]["overall_score"]
                        if "overall_score" in ed:
                            result["steps"]["eval"] = ed["overall_score"]
                except:
                    pass
        if "eval" not in result["steps"]:
            result["steps"]["eval"] = "stream_done"
    except Exception as e:
        result["steps"]["eval"] = f"ERR: {e}"

    # 6. Report
    try:
        resp = requests.post(f"{BASE}/api/reports/generate-from-data",
                            json={"data": {"overall_score": result["steps"].get("eval", 70),
                                          "dimensions": {"brand_recall": 70}},
                                  "format": "html", "enterprise_name": "武汉微艺达智能科技有限公司"},
                            timeout=60)
        if resp.status_code == 200:
            d = resp.json()
            result["steps"]["report"] = d.get("report_id", "OK")[:12]
    except:
        result["steps"]["report"] = "ERR"

    result["elapsed"] = f"{time.time()-t0:.0f}s"
    return result

print("="*70)
print("GEO System - Engineer Internal Test (8 Sandtable Types Full Pipeline)")
print("="*70)

for case_id, case_data in TEST_CASES.items():
    label = case_data["label"]
    text = case_data["text"]
    print(f"\n[{label}] Running...")
    result = run_full_pipeline(case_id, label, text)
    RESULTS.append(result)

    # Print step summary
    steps_str = " | ".join(f"{k}:{v}" for k, v in result["steps"].items())
    print(f"  {steps_str}")
    print(f"  Total: {result['elapsed']}")

# Summary
print("\n" + "="*70)
print("INTERNAL TEST SUMMARY")
print("="*70)

pass_count = 0
fail_count = 0
eval_scores = []
for r in RESULTS:
    label = r["case"]
    clean_ok = r["steps"].get("clean", "").startswith("OK")
    rewrite_ok = r["steps"].get("rewrite", "").startswith("OK")
    jsonld_ok = "OK" in str(r["steps"].get("jsonld", ""))
    eval_score = r["steps"].get("eval", 0)
    if isinstance(eval_score, (int, float)):
        eval_scores.append(eval_score)

    status = "PASS" if (clean_ok and rewrite_ok and jsonld_ok) else "FAIL"
    if status == "PASS":
        pass_count += 1
    else:
        fail_count += 1

    eval_display = f"eval={eval_score}" if isinstance(eval_score, (int, float)) else f"eval={eval_score}"
    print(f"  [{status}] {label}: clean={'OK' if clean_ok else 'FAIL'} rewrite={'OK' if rewrite_ok else 'FAIL'} jsonld={'OK' if jsonld_ok else 'FAIL'} {eval_display}")

if eval_scores:
    avg_score = sum(eval_scores) / len(eval_scores)
    above_65 = sum(1 for s in eval_scores if s >= 65)
    print(f"\n  Eval avg: {avg_score:.1f} | >=65: {above_65}/{len(eval_scores)} | <50: {sum(1 for s in eval_scores if s < 50)}")

print(f"\n  TOTAL: {pass_count} PASS / {fail_count} FAIL / {len(RESULTS)} cases")
print(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
