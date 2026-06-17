#!/usr/bin/env python3
"""
审计#1 —— 系统自身完整性审计
检查：数据层 → 引擎层 → 输出层 全链路一致性
"""
import sys, json, math
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent))

PASS, FAIL, WARN = "✅", "❌", "⚠️"
issues = []

def check(cond, msg, severity=FAIL):
    tag = PASS if cond else severity
    if not cond:
        issues.append(f"  {tag} {msg}")
    return cond

# ============================================================
print("=" * 70)
print("  审计#1: 预测系统自身完整性")
print(f"  审计时间: {date.today()}")
print("=" * 70)

# ---- 1. 数据层完整性 ----
print("\n📦 1. 数据层完整性")

teams = json.load(open("data/teams.json"))
groups = json.load(open("data/groups.json"))
injuries = json.load(open("data/injuries.json"))
gossip = json.load(open("data/gossip.json"))

ALL_48 = set()
for gid, g in groups.items():
    for t in g["teams"]:
        ALL_48.add(t)

# 1.1 球队覆盖
missing_teams = ALL_48 - set(teams.keys())
check(len(missing_teams) == 0, f"teams.json缺{len(missing_teams)}队: {missing_teams}" if missing_teams else "48队数据完整")
extra_teams = set(teams.keys()) - ALL_48
if extra_teams:
    print(f"  {WARN} teams.json多余队伍(不在任何小组): {extra_teams}")

# 1.2 必要字段
required_fields = ["fifa_rank", "elo_rating", "market_value_eur", "recent_10", "recent_5", "odds", "group"]
for tid in ALL_48:
    t = teams.get(tid, {})
    for f in required_fields:
        check(f in t, f"{tid}缺少字段 {f}")

    # 子字段检查
    for sub in ["recent_10", "recent_5"]:
        if sub in t:
            for k in ["w", "d", "l", "gf", "ga"]:
                check(k in t[sub], f"{tid}.{sub}缺少{k}")

# 1.3 小组-球队一致性
for gid, g in groups.items():
    for tid in g["teams"]:
        check(tid in teams, f"Group {gid}: {tid}不在teams.json")
        if tid in teams:
            check(teams[tid].get("group") == gid, f"{tid} group字段={teams[tid].get('group')}, 应在{gid}")
    for tid in g["standings"]:
        check(tid in g["teams"], f"Group {gid}: standings中{tid}不在teams列表")

# 1.4 数值合理性
for tid in ALL_48:
    t = teams.get(tid, {})
    if "fifa_rank" in t:
        check(1 <= t["fifa_rank"] <= 210, f"{tid} FIFA排名{t['fifa_rank']}异常")
    if "elo_rating" in t:
        check(1300 <= t["elo_rating"] <= 2100, f"{tid} Elo={t['elo_rating']}异常")
    if "market_value_eur" in t:
        check(t["market_value_eur"] > 0, f"{tid} 身价={t['market_value_eur']}异常")
    r10 = t.get("recent_10", {})
    if r10:
        check(r10["w"] + r10["d"] + r10["l"] == 10, f"{tid} 近10场战绩和不等于10 (={r10['w']+r10['d']+r10['l']})")
    r5 = t.get("recent_5", {})
    if r5:
        check(r5["w"] + r5["d"] + r5["l"] == 5, f"{tid} 近5场战绩和不等于5 (={r5['w']+r5['d']+r5['l']})")

# 1.5 伤病数据合理性
for tid, inj_list in injuries.items():
    check(tid in ALL_48, f"injuries.json: {tid}不在48队中")
    for inj in inj_list:
        check(inj["status"] in ("out", "out_retired", "doubtful"), f"{tid}.{inj['player']} 状态异常:{inj['status']}")
        check(inj["irreplaceability"] in (0.5, 1.0, 1.5, 2.0), f"{tid}.{inj['player']} 替代系数异常")

# 1.6 八卦数据合理性
for tid, gdata in gossip.items():
    check(tid in ALL_48, f"gossip.json: {tid}不在48队中")
    for section in ["locker_room", "political", "player_off_field"]:
        if section in gdata:
            s = gdata[section]
            check(isinstance(s.get("score", 0), (int, float)), f"{tid}.{section}.score异常")

# ---- 2. 引擎层计算一致性 ----
print("\n⚙️ 2. 引擎层计算一致性")

from engine.hard_data import hard_data_score, base_strength, recent_form, injury_penalty
from engine.betting import betting_score
from engine.gossip import gossip_score
from engine.predictor import final_score

for tid in sorted(ALL_48)[:48]:
    # 硬数据层
    hd = hard_data_score(tid)
    check(0 <= hd["score"] <= 100, f"{tid} 硬数据={hd['score']} 越界")
    check(abs(hd["score"] - (hd["detail"]["base_strength"]*0.4 + hd["detail"]["recent_form"]*0.4 + hd["detail"]["injury_score"]*0.2)) < 0.5,
          f"{tid} 硬数据加权不一致: {hd['score']} vs 计算值", WARN)

    # 外盘层
    bt = betting_score(tid)
    check(0 <= bt["score"] <= 100, f"{tid} 外盘={bt['score']} 越界")

    # 八卦层
    gs = gossip_score(tid)
    check(0 <= gs["score"] <= 100, f"{tid} 八卦={gs['score']} 越界")
    # 八卦层满分100, 扣分制
    if gs["score"] == 100:
        pass  # 干净球队
    elif gs["score"] < 100:
        check(gs["detail"]["locker_room_score"] < 40 or gs["detail"]["political_score"] < 35 or gs["detail"]["player_off_field_score"] < 25,
              f"{tid} 八卦扣分({gs['score']})但三个子项都满分", WARN)

    # 最终总分
    fs = final_score(tid)
    expected = round(hd["score"]*0.50 + bt["score"]*0.30 + gs["score"]*0.20, 1)
    check(abs(fs["total"] - expected) < 0.2, f"{tid} 总分不一致: {fs['total']} vs {expected}")

# ---- 3. 输出层合理性 ----
print("\n📊 3. 输出层合理性")

from engine import predict

# 3.1 概率归一化
test_matches = ["FRA-SEN", "IRQ-NOR", "ARG-ALG", "ENG-CRO", "GER-CUW", "ESP-CPV"]
for m in test_matches:
    p = predict(m)
    if "error" in p: continue
    r = p["prediction"]
    total_pct = r["win_pct"] + r["draw_pct"] + r["lose_pct"]
    check(abs(total_pct - 100) < 0.5, f"{m} 胜平负和={total_pct:.1f}≠100%")

    # 比分概率合理性
    for s in r["top_scores"]:
        check(0 < s["probability"] <= 0.99, f"{m} 比分{s['score']}概率{s['probability']}异常")

    # xG合理性
    check(0.2 <= r["xg_home"] <= 6.0, f"{m} xG_home={r['xg_home']}异常")
    check(0.2 <= r["xg_away"] <= 6.0, f"{m} xG_away={r['xg_away']}异常")

# 3.2 总分与胜负一致性
for m in test_matches:
    p = predict(m)
    if "error" in p: continue
    r = p["prediction"]
    delta = p["delta"]
    w, d, l = r["win_pct"], r["draw_pct"], r["lose_pct"]

    # delta > 15: 胜方应该有最高概率
    if delta > 15:
        check(w > l, f"{m} Δ={delta:.1f}>15但w({w}%)≤l({l}%)", WARN)
    elif delta < -15:
        check(l > w, f"{m} Δ={delta:.1f}<-15但l({l}%)≤w({w}%)", WARN)

# 3.3 冷门预警一致性
cold_matches = [m for m in test_matches]
for m in cold_matches:
    p = predict(m)
    if "error" in p: continue
    r = p["prediction"]
    alert = r["cold_alert"]
    w, d, l = r["win_pct"], r["draw_pct"], r["lose_pct"]

    # "高"冷门预警应该对应lose%>30%或优势方概率不高
    if "高" in alert:
        home_adv = p["delta"] > 0
        underdog_pct = l if home_adv else w
        check(underdog_pct > 25, f"{m} 冷门预警={alert}但冷门方仅{underdog_pct}%", WARN)

# ---- 4. 无幻觉检查 ----
print("\n🔍 4. 无幻觉检查")

# 4.1 所有引用的球队ID必须真实存在
from engine.predictor import team_name
for tid in ALL_48:
    name = team_name(tid)
    check(name != tid, f"{tid} 无法解析球队名(返回代码本身)")

# 4.2 比分预测不超出合理范围
for m in test_matches:
    p = predict(m)
    if "error" in p: continue
    for s in p["prediction"]["top_scores"]:
        parts = s["score"].split("-")
        check(0 <= int(parts[0]) <= 8 and 0 <= int(parts[1]) <= 8,
              f"{m} 比分{s['score']}超出0-8范围")

# 4.3 八卦时间衰减不产生负数
for tid, gdata in gossip.items():
    gs = gossip_score(tid)
    for k in ["locker_room_score", "political_score", "player_off_field_score"]:
        check(gs["detail"][k] >= 0, f"{tid} {k}={gs['detail'][k]}为负数")

# ---- 5. 实时数据检查 ----
print("\n🕐 5. 实时数据时效性")

# 检查小组积分是否已更新（首轮已完成的比赛）
from engine.gossip import time_decay

# 八卦事件时间衰减
decay_checks = {
    "POR": ("2026-05-24", "Braga主席攻击Martinez"),
    "KSA": ("2026-04-16", "解雇Renard"),
    "TUN": ("2026-06-14", "Lamouchi将被解雇"),
}
for tid, (event_date, desc) in decay_checks.items():
    if tid in gossip:
        d = gossip[tid].get("locker_room", {}).get("date", "")
        if d:
            decay = time_decay(d)
            check(0 < decay <= 1.0, f"{tid} {desc}: 时间衰减={decay:.2f}异常")
            if decay < 0.1:
                print(f"  {WARN} {tid} {desc}: 衰减至{decay:.2f}, 事件已过期, 建议从gossip.json移除")

# ---- 汇总 ----
print(f"\n{'═' * 70}")
total_issues = len(issues)
print(f"审计完成: {total_issues}个问题")
if total_issues == 0:
    print("🏆 系统完整性: 全部通过")
else:
    fails = sum(1 for i in issues if FAIL in i)
    warns = sum(1 for i in issues if WARN in i)
    print(f"❌={fails} ⚠️={warns}")
    for i in issues:
        print(i)
print(f"{'═' * 70}")
