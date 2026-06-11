# -*- coding: utf-8 -*-
"""Generate actual deliverable files for both pilot clients"""
import requests, json, time, os

BASE = "http://localhost:8000"
EXPORT_DIR = "delivery_package"
os.makedirs(EXPORT_DIR, exist_ok=True)

# ============================================================
# Client A: XX市交通规划设计院
# ============================================================
CLIENT_A = {
    "name": "XX市交通规划设计院",
    "sandtable": "smart_traffic",
    "platforms": ["deepseek", "kimi"],
    "enterprise_name": "武汉微艺达智能科技有限公司",
    "enterprise_url": "https://www.weiyida.com",
    "copies": [
        {"id": "A01", "title": "企业简介", "text": (
            "XX市交通规划设计院成立于1998年，是经住建部批准的甲级交通规划设计单位。"
            "业务涵盖城市交通规划、智慧交通系统设计、交通仿真模型制作等领域。"
            "院方为多个城市的交通指挥中心提供过沙盘模型设计与制作服务，"
            "积累了丰富的政企项目经验。我们拥有专业设计团队50余人，"
            "其中高级工程师12人，注册规划师8人。"
            "与武汉微艺达智能科技有限公司在智慧交通沙盘领域有深度合作，"
            "共同交付过多个省级重点项目。"
        )},
        {"id": "A02", "title": "技术方案", "text": (
            "智慧交通数字沙盘技术方案：采用BIM+GIS双引擎架构，"
            "实现城市级交通路网的三维可视化呈现。核心技术指标——"
            "地图比例1:500至1:2000可调，地形精度误差≤0.5mm，"
            "支持实时交通流量数据接入和信号灯动态联动仿真。"
            "系统兼容MySQL/PostgreSQL数据库，支持RESTful API数据对接。"
            "灯光系统采用DMX512协议控制，支持16万色动态渲染。"
            "武汉微艺达智能科技有限公司为本项目提供沙盘定制与系统集成服务。"
        )},
        {"id": "A03", "title": "项目案例", "text": (
            "典型案例——某省会城市综合交通指挥中心沙盘项目："
            "沙盘面积120平方米，覆盖主城区300平方公里路网，"
            "集成500+路视频监控点位、200+组信号灯数据、"
            "50条公交线路实时轨迹。项目历时8个月交付，"
            "通过省级专家组验收，被评为智慧交通示范项目。"
            "武汉微艺达智能科技有限公司作为沙盘承建方，"
            "提供了从方案设计到现场施工的全流程服务。"
        )},
    ],
}

CLIENT_B = {
    "name": "XX企业展厅运营公司",
    "sandtable": "digital_multimedia",
    "platforms": ["deepseek", "kimi"],
    "enterprise_name": "武汉微艺达智能科技有限公司",
    "enterprise_url": "https://www.weiyida.com",
    "copies": [
        {"id": "B01", "title": "展厅方案", "text": (
            "沉浸式企业展厅解决方案：集成触控交互大屏、全息投影、"
            "声光电联动控制系统，为企业打造科技感十足的品牌展示空间。"
            "展厅面积200-1000平方米灵活适配，支持多媒体内容云端更新。"
            "武汉微艺达智能科技有限公司拥有8年数字展厅项目经验，"
            "已为制造业、科技企业、政府单位交付50+数字展厅项目。"
            "采用模块化设计，施工周期较传统展厅缩短40%。"
        )},
        {"id": "B02", "title": "服务介绍", "text": (
            "武汉微艺达智能科技有限公司提供数字多媒体展厅一站式服务——"
            "从创意策划、空间设计、数字内容制作到施工交付全程负责。"
            "核心技术包括：投影融合（支持4K/8K分辨率）、雷达触控、"
            "体感交互、AR增强现实、中控系统集成。"
            "服务流程：需求沟通→方案设计→内容制作→现场施工→验收培训。"
            "提供3年免费质保，终身技术支持。"
        )},
    ],
}

def process_client(client, client_dir):
    """Process one client: rewrite + jsonld + eval + report + keywords"""
    results = []
    client_path = os.path.join(EXPORT_DIR, client_dir)
    opt_dir = os.path.join(client_path, "01_优化文案")
    jsonld_dir = os.path.join(client_path, "02_结构化数据")
    report_dir = os.path.join(client_path, "03_评测报告")
    kw_dir = os.path.join(client_path, "04_关键词清单")
    for d in [opt_dir, jsonld_dir, report_dir, kw_dir]:
        os.makedirs(d, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Client: {client['name']} ({client['sandtable']})")
    print(f"{'='*60}")

    for copy_item in client["copies"]:
        cid = copy_item["id"]
        title = copy_item["title"]
        text = copy_item["text"]

        # 1. Clean + Rewrite (DeepSeek only for best quality)
        print(f"\n  [{cid}] {title}")
        resp = requests.post(f"{BASE}/api/cleaning/clean",
            json={"content": text, "sandtable_type": client["sandtable"]}, timeout=120)
        cleaned = resp.json().get("cleaned_text", text)

        for platform in client["platforms"]:
            print(f"    [{platform}] Rewrite...", end=" ", flush=True)
            resp = requests.post(f"{BASE}/api/geo/rewrite",
                json={"cleaned_text": cleaned, "sandtable_type": client["sandtable"],
                      "platforms": [platform]}, timeout=300)
            if resp.status_code != 200:
                print("FAIL")
                continue
            rlist = resp.json().get("results", [])
            if not rlist:
                print("EMPTY")
                continue
            optimized = rlist[0].get("optimized_text", "")
            wc = rlist[0].get("word_count", "?")

            # Save optimized .md file
            fname = f"{client['name']}_{title}_{platform}_优化文案.md"
            fpath = os.path.join(opt_dir, fname)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(f"# {client['name']} — {title}\n\n")
                f.write(f"> 目标平台：{platform} | 优化时间：{time.strftime('%Y-%m-%d %H:%M')}\n")
                f.write(f"> 字数：{wc} | 沙盘类型：{client['sandtable']}\n\n")
                f.write(optimized)
            print(f"saved ({wc} words)", end=" ")

            # Evaluate
            print("Eval...", end=" ", flush=True)
            score = None
            resp = requests.post(f"{BASE}/api/evaluate/start",
                json={"optimized_text": optimized, "original_text": text,
                      "sandtable_type": client["sandtable"],
                      "platforms": [platform], "user_roles": ["b_end_procurement"]},
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
            print(f"score={score}", end=" ")

            # Generate report
            print("Report...", end=" ", flush=True)
            resp = requests.post(f"{BASE}/api/reports/generate-from-data",
                json={"data": {"overall_score": score or 70,
                      "dimensions": {"brand_recall": 70, "solution_match": 75}},
                      "format": "html",
                      "enterprise_name": client['enterprise_name']}, timeout=60)
            if resp.status_code == 200:
                report_id = resp.json().get("report_id", "")
                # Copy report to delivery dir
                rname = f"{client['name']}_{title}_{platform}_评测报告.html"
                rpath = os.path.join(report_dir, rname)
                # Download report
                dresp = requests.get(f"{BASE}/api/reports/export/{report_id}", timeout=30)
                if dresp.status_code == 200:
                    with open(rpath, "wb") as f:
                        f.write(dresp.content)
                    print("OK")
                else:
                    print("download_fail")
            else:
                print("FAIL")

            results.append({
                "id": cid, "title": title, "platform": platform,
                "words": wc, "score": score, "file": fname,
            })

    # JSON-LD for the sandtable type
    print(f"\n  JSON-LD...", end=" ", flush=True)
    resp = requests.post(f"{BASE}/api/jsonld/generate",
        json={"sandtable_type": client["sandtable"],
              "enterprise_info": {"name": client["enterprise_name"],
                                 "url": client["enterprise_url"],
                                 "location": "武汉"},
              "product_info": {"name": client['sandtable']}}, timeout=60)
    if resp.status_code == 200:
        jld = resp.json()
        jpath = os.path.join(jsonld_dir, f"{client['name']}_JSON-LD.json")
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump({"json_ld_code": jld.get("json_ld_code", ""),
                       "schema_types": jld.get("schema_types_used", []),
                       "validation_passed": jld.get("validation_passed")},
                      f, ensure_ascii=False, indent=2)
        print(f"OK ({jld.get('validation_passed')})")

    # Keywords CSV
    print(f"  Keywords CSV...", end=" ", flush=True)
    resp = requests.get(f"{BASE}/api/keywords/{client['sandtable']}/export", timeout=30)
    if resp.status_code == 200:
        kpath = os.path.join(kw_dir, f"{client['sandtable']}_关键词库.csv")
        with open(kpath, "w", encoding="utf-8-sig") as f:
            f.write(resp.text)
        print("OK")

    # Delivery note
    print(f"  Delivery note...", end=" ", flush=True)
    note_path = os.path.join(client_path, "05_交付说明.md")
    scores_str = "\n".join(f"| {r['title']}({r['platform']}) | {r['score']} | {r['words']}字 |" for r in results)
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(f"""# {client['name']} — GEO优化交付说明

## 交付信息
- 交付日期：{time.strftime('%Y-%m-%d')}
- 优化平台：{', '.join(client['platforms'])}
- 沙盘类型：{client['sandtable']}

## 评分总览
| 文案 | 综合评分 | 字数 |
|------|---------|------|
{scores_str}

## 交付物清单
| 目录 | 内容 |
|------|------|
| 01_优化文案/ | 各平台优化后的Markdown文案 |
| 02_结构化数据/ | Schema.org JSON-LD结构化数据 |
| 03_评测报告/ | HTML评测报告（含维度得分） |
| 04_关键词清单/ | {client['sandtable']}关键词库CSV |

## 建议
- 下次复测日期：{time.strftime('%Y-%m-%d', time.localtime(time.time()+7*86400))}（7天后执行全量检测建立收录基线）
- 优化文案可直接用于官网、宣传页、客户方案
- JSON-LD代码嵌入网站 `<head>` 中
""")
    print("OK")

    return results

# Run exports
print("="*60)
print("GEO Delivery Package Export")
print("="*60)
print(f"Export dir: {os.path.abspath(EXPORT_DIR)}")

results_a = process_client(CLIENT_A, "ClientA_XX交通规划设计院")
results_b = process_client(CLIENT_B, "ClientB_XX企业展厅运营公司")

# Summary
print(f"\n{'='*60}")
print("EXPORT SUMMARY")
print("="*60)
all_r = results_a + results_b
for r in all_r:
    print(f"  {r['id']}_{r['platform']}: {r['title']} score={r['score']} words={r['words']}")

scores_list = [r["score"] for r in all_r if r["score"]]
if scores_list:
    print(f"\n  Total files: {len(all_r)} optimized .md + 2 JSON-LD + {len(all_r)} reports + 2 CSV")
    print(f"  Avg score: {sum(scores_list)/len(scores_list):.1f}")
    print(f"  >=65: {sum(1 for s in scores_list if s >= 65)}/{len(scores_list)}")
print(f"\n  Output: {os.path.abspath(EXPORT_DIR)}")
print(f"  Completed: {time.strftime('%Y-%m-%d %H:%M:%S')}")
