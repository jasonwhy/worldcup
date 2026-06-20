#!/usr/bin/env python3
"""
竞彩官方SP值抓取工具 v2.0 — Playwright浏览器方案
用法: pip install playwright && playwright install chromium
      python fetch_sp.py              # 今天
      python fetch_sp.py 2026-06-17   # 指定日期
输出: 可直接替换 lottery.py 中 REAL_SP 字典的代码
"""
import sys, json, re
from datetime import date

MATCH_DATE = sys.argv[1] if len(sys.argv) > 1 else str(date.today())

print(f"🏧 竞彩SP抓取 v2.1 — {MATCH_DATE}")
print(f"{'='*50}")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ 需要安装: pip install playwright && playwright install chromium")
    print("💡 备用: 浏览器打开 https://m.sporttery.cn/mjc/jsq/zqhhgg/ 手动复制赔率")
    sys.exit(1)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    # 直接用Playwright发API请求, 绕过页面的CORS限制
    api_url = f"https://webapi.sporttery.cn/gateway/jc/football/getMatchListV1.qry?matchPage=1&pcOrWap=1&matchBeginDate={MATCH_DATE}&matchEndDate={MATCH_DATE}"
    response = page.request.get(api_url, headers={"Accept": "application/json"})
    result = response.json()
    browser.close()

if isinstance(result, dict) and "value" in result:
    matches = result["value"].get("matchList", [])
elif isinstance(result, dict) and "data" in result:
    matches = result["data"].get("list", [])
else:
    print(f"⚠️ API返回格式异常: {str(result)[:300]}")
    print("💡 浏览器手动: https://m.sporttery.cn/mjc/jsq/zqhhgg/")
    sys.exit(1)

print(f"📋 找到 {len(matches)} 场比赛\n")

sp_dict = {}
tg_dict = {}
score_dict = {}

for m in matches:
    home = m.get("homeTeam", "?").split(",")[0]
    away = m.get("awayTeam", "?").split(",")[0]
    mid = m.get("matchId", "")
    num = m.get("matchNumStr", "")

    # 解析 matchResultList: [0]=SPF, [1]=RQ, [2]=BF, [3]=JQ, [4]=BQC
    mrl = m.get("matchResultList", [])
    if not mrl:
        print(f"  ⚠️ {num} {home}vs{away}: 无SP数据")
        continue

    # SPF (胜平负)
    if len(mrl) > 0 and mrl[0].get("odds"):
        spf = mrl[0]["odds"].split(",")
        if len(spf) >= 3:
            sp_dict[f"{home}-{away}"] = {"home": float(spf[0]), "draw": float(spf[1]), "away": float(spf[2])}
            print(f"  ✅ {num} {home}vs{away}: 胜={spf[0]} 平={spf[1]} 负={spf[2]}")

    # JQ (总进球)
    if len(mrl) > 3 and mrl[3].get("odds"):
        jq = mrl[3]["odds"].split(",")
        tg_dict[f"{home}-{away}"] = {}
        for i, g in enumerate([0, 1, 2, 3, 4, 5, 6, 7]):
            if i < len(jq): tg_dict[f"{home}-{away}"][g] = float(jq[i])

    # BF (比分) - 31项，分胜/平/负三段
    if len(mrl) > 2 and mrl[2].get("odds"):
        bf_all = mrl[2]["odds"].split(",")
        score_dict[f"{home}-{away}"] = {}
        score_labels = ["1:0","2:0","2:1","3:0","3:1","3:2","4:0","4:1","4:2","5:0","5:1","5:2","胜其他",
                        "0:0","1:1","2:2","3:3","平其他",
                        "0:1","0:2","1:2","0:3","1:3","2:3","0:4","1:4","2:4","0:5","1:5","2:5","负其他"]
        for i, label in enumerate(score_labels):
            if i < len(bf_all): score_dict[f"{home}-{away}"][label] = float(bf_all[i])

# 生成Python代码
print(f"\n{'='*50}")
print("📋 复制以下代码替换 lottery.py 中的 REAL_SP / REAL_TOTAL_GOALS_SP / REAL_SCORE_SP:")
print(f"{'='*50}\n")

print("# 竞彩官方SP值（来源: webapi.sporttery.cn 实时抓取）")
print(f"# 抓取时间: {date.today()} 比赛日期: {MATCH_DATE}")
print("REAL_SP = {")
for k, v in sp_dict.items():
    print(f'    "{k}": {{"home": {v["home"]}, "draw": {v["draw"]}, "away": {v["away"]}}},')
print("}")

if tg_dict:
    print("\nREAL_TOTAL_GOALS_SP = {")
    for k, v in tg_dict.items():
        inner = ", ".join(f"{g}: {sp}" for g, sp in sorted(v.items()))
        print(f'    "{k}": {{{inner}}},')
    print("}")

if score_dict:
    print("\nREAL_SCORE_SP = {")
    for k, v in score_dict.items():
        top = {lab: sp for lab, sp in v.items() if sp < 15.0}  # 只保留<15倍的高概率比分
        inner = ", ".join(f'"{lab}": {sp}' for lab, sp in sorted(top.items(), key=lambda x: x[1])[:12])
        print(f'    "{k}": {{{inner}}},')
    print("}")

print(f"\n✅ 完成: {len(sp_dict)}场SPF + {len(tg_dict)}场JQ + {len(score_dict)}场BF")
