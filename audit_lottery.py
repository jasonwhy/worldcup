#!/usr/bin/env python3
"""
审计#2 —— 竞彩投注方案完整审计
检查：竞彩规则合规 + 方案一致性 + 风险分散 + 无幻觉
"""
import sys, json, math
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent))

from engine.lottery import (
    generate_plan, classify_match, RULE, THRESHOLD,
    cold_rank, est_odds, format_lottery
)
from engine import predict
from engine.gossip import gossip_score

PASS, FAIL, WARN = "✅", "❌", "⚠️"
issues = []

def check(cond, msg, severity=FAIL):
    tag = PASS if cond else severity
    if not cond:
        issues.append(f"  {tag} {msg}")
    return cond

# ============================================================
print("=" * 70)
print("  审计#2: 竞彩投注方案完整性")
print(f"  审计时间: {date.today()}  |  总预算: {RULE['budget']}元")
print("=" * 70)

TODAY = ["FRA-SEN","IRQ-NOR","ARG-ALG","AUT-JOR","ENG-CRO","GHA-PAN","POR-COD","COL-UZB"]

# ---- 1. 竞彩规则合规 ----
print("\n📋 1. 竞彩规则合规")

# 1.1 胜平负串关不超过8场
plan = generate_plan(TODAY)
cons = plan.get("conservative", {})
bal = plan.get("balanced", {})
agg = plan.get("aggressive", {})

if "error" not in cons:
    check(len(cons["bets"]) <= RULE["WDL_max_parlay"],
          f"稳健仓串关{len(cons['bets'])}场 > 胜平负上限{RULE['WDL_max_parlay']}")

# 1.2 比分串关不超过3场
if "error" not in agg:
    check(len(agg["bets"]) <= RULE["score_max_parlay"],
          f"进取仓比分串关{len(agg['bets'])}场 > 上限{RULE['score_max_parlay']}")

# 1.3 混合过关：同场不同玩法不能混串
if "error" not in bal:
    for b in bal["bets"]:
        # 确保均衡仓两注来自不同比赛
        pass
    match_ids = [b.get("match", "") for b in bal["bets"]]
    if len(match_ids) == 2:
        check(match_ids[0] != match_ids[1], f"均衡仓同一场比赛混串: {match_ids}")

# 1.4 预算分配
total_budget = plan["total_budget"]
allocated = 0
for tier in [cons, bal, agg]:
    if "error" not in tier:
        allocated += tier["amount"]
check(allocated == total_budget, f"预算分配={allocated} ≠ 总额{total_budget}")

# 1.5 中奖金额不超限
for tier_name, tier in [("稳健仓", cons), ("均衡仓", bal), ("进取仓", agg)]:
    if "error" in tier: continue
    ret = tier.get("est_return", 0)
    if len(tier["bets"]) <= 3:
        check(ret <= 200000, f"{tier_name}预估回报{ret}元 > 20万限额(2-3关)")
    elif len(tier["bets"]) <= 5:
        check(ret <= 500000, f"{tier_name} 预估回报{ret}元 > 50万限额(4-5关)")

# ---- 2. 方案与模型输出一致性 ----
print("\n🔗 2. 方案与模型输出一致性")

# 2.1 每个投注选项必须在模型输出中找到对应
for tier_name, tier in [("稳健仓", cons), ("均衡仓", bal), ("进取仓", agg)]:
    if "error" in tier: continue
    for b in tier["bets"]:
        match_name = b["match"]
        pick = b["pick"]

        # 找对应的match_id
        found = False
        for mid in TODAY:
            p = predict(mid)
            if "error" in p: continue
            if p["match"] == match_name:
                c = classify_match(mid, p)
                r = p["prediction"]

                # 验证选择在模型输出中存在
                if "总进球" in pick:
                    tg_val = int(pick.replace("总进球", "").replace("球", ""))
                    check(c["total_goals_signal"] == tg_val,
                          f"{tier_name}: 选{pick}但模型tg_signal={c['total_goals_signal']}")
                elif "胜" in pick:
                    team = pick.replace("胜", "")
                    check(team in match_name,
                          f"{tier_name}: 选{pick}但不在{match_name}中")
                    # 验证方向
                    if team in p["home"]["name"]:
                        check(r["win_pct"] >= 30, f"{tier_name}: {match_name}选{team}胜但模型仅{r['win_pct']}%", WARN)
                    else:
                        check(r["lose_pct"] >= 30, f"{tier_name}: {match_name}选{team}胜但模型仅{r['lose_pct']}%", WARN)
                elif "比分" in str(b.get("type", "")) or "-" in pick:
                    # 比分: 检查是否在Top3
                    top3 = [s["score"] for s in r["top_scores"][:3]]
                    check(pick in top3,
                          f"{tier_name}: 比分{pick}不在{match_name}Top3{top3}")
                found = True
                break

        check(found, f"{tier_name}: 找不到{match_name}的比赛数据")

# 2.2 排除场次合理性
excluded = plan["classified"]["excluded_pool"]
for match_name in excluded:
    for mid in TODAY:
        p = predict(mid)
        if "error" in p: continue
        if p["match"] == match_name:
            r = p["prediction"]
            c = classify_match(mid, p)
            # 验证排除原因
            has_reason = (
                "低" in r["confidence"]
                or c["cold_rank"] >= 3
                or c["dir_prob"] < 30
            )
            check(has_reason, f"排除{match_name}但无明确原因: conf={r['confidence']} cold={c['cold_rank']} prob={c['dir_prob']}", WARN)
            break

# 2.3 模型概率与预估赔率一致性
for tier_name, tier in [("稳健仓", cons), ("均衡仓", bal)]:
    if "error" in tier: continue
    for b in tier["bets"]:
        if "model_prob" in b:
            est = b["est_odds"]
            prob = b["model_prob"]
            fair = 100 / prob if prob > 0 else 99
            implied = fair * 0.71  # 竞彩返奖率
            check(est <= implied * 1.2, f"{tier_name}: {b['match']} 估赔{est}远超隐含赔率{implied:.2f} (prob={prob}%)", WARN)

# ---- 3. 风险分散审计 ----
print("\n🎲 3. 风险分散审计")

# 3.1 同场次跨仓检测
all_picks = {}
for tier_name, tier in [("稳健仓", cons), ("均衡仓", bal), ("进取仓", agg)]:
    if "error" in tier: continue
    for b in tier["bets"]:
        match = b["match"]
        if match not in all_picks:
            all_picks[match] = []
        all_picks[match].append({"tier": tier_name, "pick": b["pick"]})

# 同场比赛出现在多个仓位 = 集中风险
for match, picks in all_picks.items():
    if len(picks) >= 2:
        tiers = [p["tier"] for p in picks]
        # 进取仓与其它仓重叠可接受（比分独立）
        has_non_agg = [t for t in tiers if "进取" not in t]
        if len(has_non_agg) >= 2:
            print(f"  {WARN} {match}: 在{has_non_agg}中重复使用 → 集中风险")
            check(False, f"{match}: 稳健+均衡仓重叠")

# 3.2 冷门场景压力测试
print("\n  压力测试:")
stress_scenarios = [
    ("Norway不胜(平/负)", "IRQ-NOR", ["Norway胜"]),
    ("Austria不胜", "AUT-JOR", ["Austria胜"]),
    ("Portugal不胜", "POR-COD", ["Portugal胜"]),
]
for scenario, mid, affected_picks in stress_scenarios:
    dead_tiers = []
    for tier_name, tier in [("稳健仓", cons), ("均衡仓", bal), ("进取仓", agg)]:
        if "error" in tier: continue
        for b in tier["bets"]:
            if b["match"] == (predict(mid).get("match", "")) and any(ap in b["pick"] for ap in affected_picks):
                dead_tiers.append(tier_name)
                break
    if dead_tiers:
        print(f"  {scenario}: {dead_tiers}失效, 损失{sum(t['amount'] for n,t in [('稳健仓',cons),('均衡仓',bal),('进取仓',agg)] if 'error' not in t and n in dead_tiers)}元")

# ---- 4. 实时数据审计 ----
print("\n🕐 4. 投注相关实时数据")

# 4.1 八卦层影响投注的球队
for mid in TODAY:
    parts = mid.split("-")
    for tid in parts:
        gs = gossip_score(tid)
        if gs["score"] < 90:
            p = predict(mid)
            if "error" in p: continue
            h = p["home"]
            a = p["away"]
            affected_side = h["name"] if h.get("gossip_detail", {}).get("locker_room_score", 40) < 40 else a["name"]
            print(f"  {WARN} {mid}: {tid}八卦{gs['score']}分 → 影响{affected_side}方向判定")

# 4.2 伤病实时状态
from engine.hard_data import injury_penalty
for mid in TODAY:
    parts = mid.split("-")
    for tid in parts:
        ip = injury_penalty(tid)
        if ip > 1:
            print(f"  {WARN} {mid}: {tid}伤病扣分{ip:.1f} → 显著影响硬数据")

# ---- 5. 方案与模型结论自洽性 ----
print("\n🔬 5. 方案-模型自洽性")

# 5.1 稳健仓每注必须有明确模型支撑
if "error" not in cons:
    for b in cons["bets"]:
        # 查找原始预测
        for mid in TODAY:
            p = predict(mid)
            if "error" in p: continue
            if p["match"] == b["match"]:
                r = p["prediction"]
                delta = abs(p["delta"])
                # 必须满足稳健仓标准
                check(delta >= THRESHOLD["conservative_min_delta"],
                      f"稳健仓 {b['match']}: Δ={delta:.1f}<阈值{THRESHOLD['conservative_min_delta']}", WARN)
                c = classify_match(mid, p)
                check(c["cold_rank"] <= THRESHOLD["conservative_max_cold_rank"],
                      f"稳健仓 {b['match']}: 冷门{c['cold_rank']}>阈值{THRESHOLD['conservative_max_cold_rank']}")
                break

# 5.2 进取仓比分必须是模型Top1或Top2
if "error" not in agg:
    for b in agg["bets"]:
        for mid in TODAY:
            p = predict(mid)
            if "error" in p: continue
            if p["match"] == b["match"]:
                r = p["prediction"]
                top2 = [s["score"] for s in r["top_scores"][:2]]
                check(b["pick"] in top2,
                      f"进取仓 {b['match']}: 选{b['pick']}但模型Top2={top2}")
                break

# 5.3 全链路可追溯
print("\n  全链路追溯:")
for tier_name, tier in [("稳健仓", cons), ("均衡仓", bal), ("进取仓", agg)]:
    if "error" in tier:
        print(f"  {WARN} {tier_name}: 跳过({tier['error']})")
        continue
    for b in tier["bets"]:
        for mid in TODAY:
            p = predict(mid)
            if "error" in p: continue
            if p["match"] == b["match"]:
                r = p["prediction"]
                print(f"  {PASS} {tier_name} {b['match'][:30]} → {b['pick']}")
                print(f"      模型: {r['win_pct']:.0f}/{r['draw_pct']:.0f}/{r['lose_pct']:.0f} "
                      f"xG={r['xg_home']:.2f}/{r['xg_away']:.2f} 冷门={r['cold_alert'][:6]} "
                      f"Δ={p['delta']:+.1f}")
                break

# ---- 汇总 ----
print(f"\n{'═' * 70}")
total_issues = len(issues)
print(f"审计完成: {total_issues}个问题")
if total_issues == 0:
    print("🏆 投注方案完整性: 全部通过")
else:
    fails = sum(1 for i in issues if FAIL in i)
    warns = sum(1 for i in issues if WARN in i)
    print(f"❌={fails} ⚠️={warns}")
    for i in issues:
        print(i)
print(f"{'═' * 70}")
