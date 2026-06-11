# -*- coding: utf-8 -*-
"""Phase 2 Pilot Simulation - 3 team members x 2 clients multi-platform delivery"""
import requests
import json
import time
import os

BASE = "http://localhost:8000"

# ============================================================
# Client A: XX市交通规划设计院 (smart_traffic, B端政企)
# Platforms: DeepSeek + Kimi (available) + 文心一言(unavailable->skip)
# ============================================================
CLIENT_A = {
    "name": "XX市交通规划设计院",
    "sandtable": "smart_traffic",
    "platforms": ["deepseek", "kimi"],
    "copies": [
        {
            "id": "A01",
            "title": "企业简介",
            "text": (
                "XX市交通规划设计院成立于1998年，是经住建部批准的甲级交通规划设计单位。"
                "业务涵盖城市交通规划、智慧交通系统设计、交通仿真模型制作等领域。"
                "院方为多个城市的交通指挥中心提供过沙盘模型设计与制作服务，"
                "积累了丰富的政企项目经验。我们拥有专业设计团队50余人，"
                "其中高级工程师12人，注册规划师8人。"
                "与武汉微艺达智能科技有限公司在智慧交通沙盘领域有深度合作，"
                "共同交付过多个省级重点项目。"
            ),
        },
        {
            "id": "A02",
            "title": "技术方案",
            "text": (
                "智慧交通数字沙盘技术方案：采用BIM+GIS双引擎架构，"
                "实现城市级交通路网的三维可视化呈现。核心技术指标——"
                "地图比例1:500至1:2000可调，地形精度误差≤0.5mm，"
                "支持实时交通流量数据接入和信号灯动态联动仿真。"
                "系统兼容MySQL/PostgreSQL数据库，支持RESTful API数据对接。"
                "灯光系统采用DMX512协议控制，支持16万色动态渲染。"
                "武汉微艺达智能科技有限公司为本项目提供沙盘定制与系统集成服务。"
            ),
        },
        {
            "id": "A03",
            "title": "项目案例",
            "text": (
                "典型案例——某省会城市综合交通指挥中心沙盘项目："
                "沙盘面积120平方米，覆盖主城区300平方公里路网，"
                "集成500+路视频监控点位、200+组信号灯数据、"
                "50条公交线路实时轨迹。项目历时8个月交付，"
                "通过省级专家组验收，被评为智慧交通示范项目。"
                "武汉微艺达智能科技有限公司作为沙盘承建方，"
                "提供了从方案设计到现场施工的全流程服务。"
            ),
        },
    ],
}

# ============================================================
# Client B: XX企业展厅运营公司 (digital_multimedia, 大众+技术)
# Platforms: Kimi + DeepSeek
# ============================================================
CLIENT_B = {
    "name": "XX企业展厅运营公司",
    "sandtable": "digital_multimedia",
    "platforms": ["deepseek", "kimi"],
    "copies": [
        {
            "id": "B01",
            "title": "展厅方案",
            "text": (
                "沉浸式企业展厅解决方案：集成触控交互大屏、全息投影、"
                "声光电联动控制系统，为企业打造科技感十足的品牌展示空间。"
                "展厅面积200-1000平方米灵活适配，支持多媒体内容云端更新。"
                "武汉微艺达智能科技有限公司拥有8年数字展厅项目经验，"
                "已为制造业、科技企业、政府单位交付50+数字展厅项目。"
                "采用模块化设计，施工周期较传统展厅缩短40%。"
            ),
        },
        {
            "id": "B02",
            "title": "服务介绍",
            "text": (
                "武汉微艺达智能科技有限公司提供数字多媒体展厅一站式服务——"
                "从创意策划、空间设计、数字内容制作到施工交付全程负责。"
                "核心技术包括：投影融合（支持4K/8K分辨率）、雷达触控、"
                "体感交互、AR增强现实、中控系统集成。"
                "服务流程：需求沟通→方案设计→内容制作→现场施工→验收培训。"
                "提供3年免费质保，终身技术支持。"
            ),
        },
    ],
}

def test(name, method, path, data=None, timeout=60, stream=False):
    url = BASE + path
    try:
        if method == "GET":
            return requests.get(url, timeout=timeout)
        return requests.post(url, json=data, timeout=timeout, stream=stream)
    except Exception as e:
        print(f"  [ERR] {name}: {e}")
        return None

def run_client_delivery(client, operator_name):
    """Simulate one operator delivering one client's full order"""
    results = []
    print(f"\n{'='*60}")
    print(f"Operator: {operator_name} | Client: {client['name']}")
    print(f"Sandtable: {client['sandtable']} | Platforms: {client['platforms']}")
    print(f"{'='*60}")

    for copy_item in client["copies"]:
        copy_id = copy_item["id"]
        title = copy_item["title"]
        text = copy_item["text"]

        print(f"\n  [{copy_id}] {title} ({len(text)} chars)")

        # 1. Clean
        resp = test(f"Clean:{copy_id}", "POST", "/api/cleaning/clean",
                    {"content": text, "sandtable_type": client["sandtable"]}, timeout=120)
        if not resp or resp.status_code != 200:
            results.append({"id": copy_id, "title": title, "status": "FAIL:clean"})
            continue
        cleaned = resp.json().get("cleaned_text", text)

        for platform in client["platforms"]:
            pid = f"{copy_id}_{platform}"
            print(f"    [{platform}] ", end="", flush=True)

            # 2. Rewrite
            resp = test(f"Rewrite:{pid}", "POST", "/api/geo/rewrite",
                        {"cleaned_text": cleaned, "sandtable_type": client["sandtable"],
                         "platforms": [platform]}, timeout=300)
            if not resp or resp.status_code != 200:
                print(f"Rewrite FAIL")
                results.append({"id": pid, "title": f"{title}({platform})", "status": "FAIL:rewrite"})
                continue
            rlist = resp.json().get("results", [])
            if not rlist:
                print(f"Empty")
                results.append({"id": pid, "title": f"{title}({platform})", "status": "EMPTY"})
                continue
            optimized = rlist[0].get("optimized_text", "")
            wc = rlist[0].get("word_count", "?")

            # 3. Evaluate
            eval_score = None
            sc_score = None
            br_score = None
            resp = test(f"Eval:{pid}", "POST", "/api/evaluate/start",
                        {"optimized_text": optimized, "original_text": text,
                         "sandtable_type": client["sandtable"],
                         "platforms": [platform],
                         "user_roles": ["b_end_procurement"]},
                        timeout=300, stream=True)
            if resp and resp.status_code == 200:
                for line in resp.iter_lines(decode_unicode=True):
                    if line and line.startswith("data:"):
                        try:
                            ds = line[5:].strip()
                            if ds:
                                ed = json.loads(ds)
                                data = ed.get("data", {})
                                if isinstance(data, dict):
                                    if "overall_score" in data:
                                        eval_score = data["overall_score"]
                                    dims = data.get("dimensions", data.get("scores", {}))
                                    if "source_consistency" in dims:
                                        sc = dims["source_consistency"]
                                        sc_score = sc.get("score", sc) if isinstance(sc, dict) else sc
                                    if "brand_recall" in dims:
                                        br = dims["brand_recall"]
                                        br_score = br.get("score", br) if isinstance(br, dict) else br
                                if "overall_score" in ed:
                                    eval_score = ed["overall_score"]
                        except:
                            pass

            # Determine pass/fail
            passed = eval_score and eval_score >= 65 and (sc_score is None or sc_score > 30)
            status = f"PASS({eval_score})" if passed else f"FAIL(score={eval_score},sc={sc_score})"
            print(f"words={wc} score={eval_score} sc={sc_score} br={br_score} -> {status}")

            results.append({
                "id": pid, "title": f"{title}({platform})",
                "platform": platform, "words": wc,
                "score": eval_score, "source_consistency": sc_score,
                "brand_recall": br_score, "status": status,
            })

    return results

# ============================================================
# Run Simulation
# ============================================================
print("="*70)
print("PHASE 2 PILOT SIMULATION")
print("3 Operators x 2 Clients x Multi-Platform Delivery")
print("="*70)

all_results = []

# Operator 1 (Senior Engineer): Client A copies A01, A02
all_results.extend(run_client_delivery({
    "name": CLIENT_A["name"],
    "sandtable": CLIENT_A["sandtable"],
    "platforms": CLIENT_A["platforms"],
    "copies": CLIENT_A["copies"][:2],  # A01, A02
}, "Engineer_Zhang(Senior)"))

# Operator 2 (Copywriter): Client A copy A03
all_results.extend(run_client_delivery({
    "name": CLIENT_A["name"],
    "sandtable": CLIENT_A["sandtable"],
    "platforms": CLIENT_A["platforms"],
    "copies": CLIENT_A["copies"][2:],  # A03
}, "Copywriter_Wang"))

# Operator 3 (Junior/New): Client B - all copies
all_results.extend(run_client_delivery({
    "name": CLIENT_B["name"],
    "sandtable": CLIENT_B["sandtable"],
    "platforms": CLIENT_B["platforms"],
    "copies": CLIENT_B["copies"],
}, "Junior_Li(New)"))

# ============================================================
# Summary
# ============================================================
print("\n" + "="*70)
print("PILOT DELIVERY SUMMARY")
print("="*70)

total = len(all_results)
passed = sum(1 for r in all_results if "PASS" in str(r.get("status", "")))
failed = sum(1 for r in all_results if "FAIL" in str(r.get("status", "")))
scores_list = [r.get("score") for r in all_results if isinstance(r.get("score"), (int, float))]

print(f"\n{'ID':<15} {'Title':<25} {'Score':>6} {'SC':>6} {'BR':>6} {'Status'}")
print("-"*75)
for r in all_results:
    sc = r.get("source_consistency", "?")
    br = r.get("brand_recall", "?")
    print(f"{r['id']:<15} {r['title']:<25} {str(r.get('score','?')):>6} {str(sc):>6} {str(br):>6} {r['status']}")

print(f"\n  Total items: {total}")
print(f"  Passed (>=65, SC>30): {passed}/{total}")
print(f"  Failed: {failed}/{total}")
if scores_list:
    print(f"  Score avg: {sum(scores_list)/len(scores_list):.1f}")
    print(f"  Score min: {min(scores_list):.1f}")
    print(f"  Score max: {max(scores_list):.1f}")

# Iteration check
need_retry = [r for r in all_results if isinstance(r.get("score"), (int, float)) and r["score"] < 65]
if need_retry:
    print(f"\n  Items needing Round 2: {len(need_retry)}")
    for r in need_retry:
        print(f"    - {r['id']}: {r['title']} (score={r['score']})")

print(f"\n  Completed: {time.strftime('%Y-%m-%d %H:%M:%S')}")
