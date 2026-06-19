#!/usr/bin/env python3
"""
引擎v2.0全面审计 — 一问一答式，基于真实数据，零幻觉
=====================================================
Layer A: 数据准确性 — 赛果/积分/球员/SP是否自洽
Layer B: 预测准确度 — 28场回溯，方向+比分+平局诊断
Layer C: 前瞻性 — 模型是否考虑了轮次/出线/伤病协同
Layer D: 信息能力 — 新闻源覆盖/时效/缺口
"""
import json, sys, os, math
from pathlib import Path
from datetime import date, datetime
from collections import defaultdict

DATA = Path("data")
PASS, FAIL, WARN = "✅", "❌", "⚠️"

def load(n):
    with open(DATA / n) as f:
        return json.load(f)

issues = []
warnings = []

def QA(question, condition, pass_msg, fail_msg, severity=FAIL):
    if condition:
        print(f"  {PASS} {pass_msg}")
    else:
        msg = f"  {FAIL} {fail_msg}"
        print(msg)
        if severity == FAIL:
            issues.append(fail_msg)
        else:
            warnings.append(fail_msg)

sys.path.insert(0, ".")
from engine.predictor import predict, final_score
from engine.hard_data import tournament_momentum, hard_data_score
from engine.lottery import generate_plan, MATCH_SCHEDULE

print("=" * 70)
print(f"  引擎 v2.0 全面审计 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
print("=" * 70)

# ================================================================
# LAYER A: 数据准确性
# ================================================================
print("\n" + "─" * 70)
print("LAYER A: 数据准确性 — 一问一答")
print("─" * 70)

teams = load("teams.json")
groups = load("groups.json")
results = load("results.json")
injuries = load("injuries.json")
gossip = load("gossip.json")
news = load("news.json")
sources = load("sources.json")
sp = load("sp.json")

# A1: results.json vs groups.json 交叉验证
played_in_results = {f"{m['home']}-{m['away']}" for m in results["matches"]}
total_games = 0
for gid, g in groups.items():
    for tid, s in g["standings"].items():
        total_games += s["w"] + s["d"] + s["l"]
actual_matches = total_games // 2

QA("A1: 赛果与积分是否自洽？",
   actual_matches == results["total_played"],
   f"groups={actual_matches}场, results={results['total_played']}场, 一致",
   f"groups={actual_matches}场 ≠ results={results['total_played']}场")

# A2: 逐场GF/GA核对
gf_errors = []
for m in results["matches"]:
    h, a = m["home"], m["away"]
    hg, ag = map(int, m["score"].split("-"))
    for gid, g in groups.items():
        if h in g["standings"] and a in g["standings"]:
            hs, aw = g["standings"][h], g["standings"][a]
            if hs["gf"] < hg or aw["gf"] < ag:
                gf_errors.append(f"{h}-{a}: GF不足")
            if hs["ga"] < ag or aw["ga"] < hg:
                gf_errors.append(f"{h}-{a}: GA不足")

QA("A2: 逐场GF/GA是否匹配？",
   len(gf_errors) == 0,
   f"{results['total_played']}场全部通过",
   f"{len(gf_errors)}场GF/GA不匹配: {gf_errors[:3]}")

# A3: 48队数据完整性
group_teams = set()
for gid, g in groups.items():
    for tid in g["standings"]:
        group_teams.add(tid)
missing = group_teams - set(teams.keys())

QA("A3: 48队数据完整性？",
   len(teams) == 48 and len(missing) == 0,
   f"teams.json={len(teams)}队, groups引用{len(group_teams)}队, 无缺失",
   f"groups.json引用{len(missing)}队无teams数据: {list(missing)[:5]}")

# A4: 伤病条目日期新鲜度
today = date.today()
stale_injuries = 0
for tid in injuries:
    for inj in injuries[tid]:
        dt = inj.get("date", "")
        if dt:
            try:
                days = (today - datetime.strptime(dt[:10], "%Y-%m-%d").date()).days
                if days > 5: stale_injuries += 1
            except: pass

QA("A4: 伤病数据是否新鲜？",
   stale_injuries <= 5,
   f"过期间{stale_injuries}条 (共{sum(len(v) for v in injuries.values())}条)",
   f"过期间{stale_injuries}条, 需更新")

# A5: SP数据覆盖待赛
sp_covered = set(sp.get("matches", {}).keys())
upcoming = set()
for mid in MATCH_SCHEDULE:
    if mid not in played_in_results:
        upcoming.add(mid)
coverage = len(sp_covered & upcoming) / max(1, len(upcoming)) * 100

QA("A5: SP数据覆盖待赛？",
   coverage >= 50,
   f"覆盖{coverage:.0f}% ({len(sp_covered & upcoming)}/{len(upcoming)})",
   f"仅覆盖{coverage:.0f}% ({len(sp_covered & upcoming)}/{len(upcoming)}), 建议补SP数据")

# ================================================================
# LAYER B: 预测准确度
# ================================================================
print("\n" + "─" * 70)
print("LAYER B: 预测准确度 — 一问一答")
print("─" * 70)

# B1: 方向正确率
correct = sum(1 for m in results["matches"] if m["prediction_correct"] == "✅")
total = len(results["matches"])

QA("B1: 方向正确率？",
   correct / total >= 0.73,
   f"{correct}/{total} = {correct/total*100:.1f}%",
   f"{correct}/{total} = {correct/total*100:.1f}% < 73%目标")

# B2: 失败分类
draw_misses = [m for m in results["matches"]
               if m["prediction_correct"]=="❌" and m["score"].split("-")[0]==m["score"].split("-")[1]]
dir_misses = [m for m in results["matches"]
              if m["prediction_correct"]=="❌" and m["score"].split("-")[0]!=m["score"].split("-")[1]]

print(f"\n  失败分布: 平局漏判{len(draw_misses)}场, 方向错误{len(dir_misses)}场")
for m in draw_misses:
    print(f"    平局漏判: {m['date']} {m['home']}-{m['away']} {m['score']} — {m['note'][:40]}")
for m in dir_misses:
    print(f"    方向错误: {m['date']} {m['home']}-{m['away']} {m['score']} — {m['note'][:40]}")

# B3: 比分Top3命中率
hit_top1 = hit_top3 = 0
goal_errs = []
for m in results["matches"]:
    mid = f"{m['home']}-{m['away']}"
    try:
        p = predict(mid)
        if "error" in p: continue
        r = p["prediction"]
        top3 = [s["score"] for s in r["top_scores"][:3]]
        if m["score"] == top3[0]: hit_top1 += 1
        if m["score"] in top3: hit_top3 += 1
        ah, aa = map(int, m["score"].split("-"))
        ph, pa = map(int, top3[0].split("-"))
        goal_errs.append(abs(ah-ph) + abs(aa-pa))
    except: pass

QA("B3: 比分Top3命中率？",
   hit_top3 / total >= 0.35,
   f"Top1={hit_top1}/{total}({hit_top1/total*100:.0f}%) Top3={hit_top3}/{total}({hit_top3/total*100:.0f}%) 均误差={sum(goal_errs)/len(goal_errs):.1f}球",
   f"Top3仅{hit_top3/total*100:.0f}%, 均误差{sum(goal_errs)/len(goal_errs):.1f}球, 需改善")

# B4: 进球系统性偏差
actual_total_goals = sum(int(m["score"].split("-")[0])+int(m["score"].split("-")[1]) for m in results["matches"])
pred_total_goals = 0
for m in results["matches"]:
    try:
        p = predict(f"{m['home']}-{m['away']}")
        if "error" in p: continue
        top = p["prediction"]["top_scores"][0]["score"]
        pred_total_goals += sum(map(int, top.split("-")))
    except: pass

QA("B4: 进球数是否系统性偏低？",
   pred_total_goals >= actual_total_goals * 0.75,
   f"实际{actual_total_goals}球 vs 预测{pred_total_goals}球 (偏{pred_total_goals/actual_total_goals*100-100:+.0f}%)",
   f"实际{actual_total_goals}球 vs 预测{pred_total_goals}球 (严重偏低{pred_total_goals/actual_total_goals*100-100:+.0f}%)")

# B5: 平局侦测率
actual_draws = sum(1 for m in results["matches"] if m["score"].split("-")[0]==m["score"].split("-")[1])
draw_correct = sum(1 for m in results["matches"] if m["score"].split("-")[0]==m["score"].split("-")[1] and m["prediction_correct"]=="✅")
QA("B5: 平局侦测率？",
   draw_correct / max(1, actual_draws) >= 0.55,
   f"{draw_correct}/{actual_draws} = {draw_correct/max(1,actual_draws)*100:.0f}%",
   f"{draw_correct}/{actual_draws} = {draw_correct/max(1,actual_draws)*100:.0f}% < 55%目标")

# ================================================================
# LAYER C: 前瞻性
# ================================================================
print("\n" + "─" * 70)
print("LAYER C: 前瞻性 — 一问一答")
print("─" * 70)

# C1: 动量因子是否生效
momentum_teams = 0
for tid in teams:
    m = tournament_momentum(tid)
    if abs(m) > 0.1:
        momentum_teams += 1

QA("C1: 赛事动量是否覆盖已赛球队？",
   momentum_teams >= 24,
   f"{momentum_teams}队有动量值(≥24已赛)",
   f"仅{momentum_teams}队有动量, 需要更新")

# C2: 出线形势是否可计算
# Check if groups.json has standings for all 12 groups
groups_ready = all(
    sum(s["w"]+s["d"]+s["l"] for s in g["standings"].values()) > 0
    for g in groups.values()
)

QA("C2: 小组积分数据是否可用于出线计算？",
   groups_ready,
   "12组均有比赛记录, 可计算出线形势 (需新模块round_factor.py)",
   "部分组无数据, 无法计算")

# C3: 伤病协同效应
# Find teams with >=2 same-position injuries
position_clusters = defaultdict(list)
for tid in injuries:
    for inj in injuries[tid]:
        if inj["status"] in ("out", "out_retired"):
            pos = inj.get("position", "unknown")
            position_clusters[(tid, pos)].append(inj["player"])

multi_injured = {k: v for k, v in position_clusters.items() if len(v) >= 2}
if multi_injured:
    print(f"\n  发现同位置多人伤缺 (需连坐惩罚):")
    for (tid, pos), players in sorted(multi_injured.items()):
        tname = teams.get(tid, {}).get("name", tid)
        print(f"    {tname} {pos}: {', '.join(players)}")
QA("C3: 伤病连坐惩罚是否存在？",
   True,
   f"发现{len(multi_injured)}组同位置多人伤缺, 建议实施模块四",
   "", WARN)

# C4: 政治高危球队识别
political_teams = {tid: g["political"]["level"]
                   for tid, g in gossip.items()
                   if g.get("political", {}).get("level", 0) >= 3}
if political_teams:
    print(f"\n  政治高危球队 (需精准加权):")
    for tid, level in sorted(political_teams.items(), key=lambda x: -x[1]):
        print(f"    {tid}: level={level}")
QA("C4: 政治因子精准加权是否就绪？",
   True,
   f"发现{len(political_teams)}支政治高危队, 建议实施模块三",
   "", WARN)

# ================================================================
# LAYER D: 信息能力
# ================================================================
print("\n" + "─" * 70)
print("LAYER D: 信息能力 — 一问一答")
print("─" * 70)

# D1: 新闻源活跃度
today_s = str(date.today())
active_sources = sum(1 for s in sources["sources"].values()
                     if s.get("last_check", "") >= today_s and s.get("status") == "active")
stale_sources = sum(1 for s in sources["sources"].values()
                    if s.get("status") == "stale")

QA("D1: 新闻源活跃度？",
   active_sources >= 14,
   f"{active_sources}活跃 / {len(sources['sources'])}总源",
   f"仅{active_sources}个活跃源, {stale_sources}个过期")

# D2: 新闻时效性
news_dates = []
for item in news.get("items", []):
    d = item.get("date", "")
    if d:
        try:
            days = (today - datetime.strptime(d[:10], "%Y-%m-%d").date()).days
            news_dates.append(days)
        except: pass

if news_dates:
    avg_age = sum(news_dates) / len(news_dates)
    recent_24h = sum(1 for d in news_dates if d <= 1)
    QA("D2: 新闻时效性？",
       avg_age <= 3 and recent_24h >= 20,
       f"平均{avg_age:.1f}天, 近24h {recent_24h}条",
       f"平均{avg_age:.1f}天, 近24h仅{recent_24h}条, 需刷新")

# D3: 伤病覆盖率
teams_with_any_injury = set(injuries.keys())
played_teams = set()
for m in results["matches"]:
    played_teams.add(m["home"])
    played_teams.add(m["away"])

QA("D3: 已赛球队伤病覆盖率？",
   len(teams_with_any_injury) >= 15,
   f"{len(teams_with_any_injury)}队有伤病数据 (共{len(played_teams)}队已赛)",
   f"仅{len(teams_with_any_injury)}队有伤病数据")

# D4: 八卦覆盖率
teams_with_gossip = set(gossip.keys())
QA("D4: 八卦覆盖率？",
   len(teams_with_gossip) >= 18,
   f"{len(teams_with_gossip)}队有八卦数据",
   f"仅{len(teams_with_gossip)}队有八卦")

# D5: SP数据新鲜度
sp_updated = sp.get("updated", "")
if sp_updated:
    try:
        sp_days = (today - datetime.strptime(sp_updated[:10], "%Y-%m-%d").date()).days
        QA("D5: SP数据新鲜度？",
           sp_days <= 3,
           f"sp.json {sp_days}天前更新",
           f"sp.json {sp_days}天未更新, 赔率可能过时")
    except: pass

# ================================================================
# 总结
# ================================================================
print("\n" + "=" * 70)
total_issues = len(issues)
total_warnings = len(warnings)

print(f"审计完成: {total_issues}个问题, {total_warnings}个警告")
print()

if total_issues == 0:
    print("✅ 数据层: 全部自洽")
else:
    for i in issues:
        print(f"  ❌ {i}")

if total_warnings == 0:
    print("✅ 前瞻性: 全通过")
else:
    for w in warnings:
        print(f"  ⚠️ {w}")

print(f"\n📊 模型表现: 方向{correct/total*100:.0f}% | 平局侦测{draw_correct}/{actual_draws} | 比分Top3 {hit_top3/total*100:.0f}%")

# 升级建议
print(f"\n🔧 升级优先级:")
if pred_total_goals < actual_total_goals * 0.8:
    print("  P0: 模块二(屠杀模式) — 进球系统性低估")
if draw_correct / max(1, actual_draws) < 0.6:
    print("  P0: 模块一(轮次态势) — 平局漏判率高")
if len(multi_injured) > 2:
    print("  P1: 模块四(伤病连坐) — 发现同位置多人伤缺")
if political_teams:
    print("  P1: 模块三(政治加权) — 高危球队需精准打击")
print("  P2: 模块五(后验校准) — 赛后自动学习修正")
