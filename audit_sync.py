#!/usr/bin/env python3
"""
四层审计系统 v4.0
Layer 1: 数据一致性 — JSON文件交叉验证 + dashboard.py数据源检查
Layer 2: 媒体源时效 — 检查每个源的上次更新时间, 标记过期源
Layer 3: 内容新鲜度 — 检查伤病/八卦/新闻条目的实际更新时间
Layer 4: 投注合规 — 检查SP数据覆盖、截止时间、方案合理性
"""
import json, sys, os
from pathlib import Path
from datetime import date, datetime

DATA = Path("data")
PASS, FAIL, WARN = "✅", "❌", "⚠️"

def load(n):
    with open(DATA / n) as f:
        return json.load(f)

issues = []
def check(cond, msg, severity=FAIL):
    if not cond: issues.append((severity, msg))
    return cond

# ============================================================
print("=" * 70)
print("  四层审计 v4.0: 数据 + 源 + 内容 + 投注")
print(f"  审计时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 70)

# === LAYER 1: 数据一致性 ===
print("\n📊 Layer 1: 数据一致性 (JSON ↔ JSON ↔ dashboard.py)")

teams = load("teams.json")
groups = load("groups.json")
injuries = load("injuries.json")
gossip = load("gossip.json")
news = load("news.json")
sources = load("sources.json")
results = load("results.json")

# 1.1 检查 results.json 赛果数量 vs groups.json 积分
# 计算实际比赛数: 每队(w+d+l)求和 / 2
total_games_played = 0
for gid, g in groups.items():
    for tid, s in g["standings"].items():
        total_games_played += s["w"] + s["d"] + s["l"]
matches_from_standings = total_games_played // 2
results_count = len(results["matches"])
check(matches_from_standings == results_count,
      f"groups.json已赛{matches_from_standings}场 vs results.json{results_count}场")

print(f"  groups.json: {total_games_played}场次参与 → {matches_from_standings}场比赛")
print(f"  results.json: {results_count}场比赛")

# 1.2 交叉验证 results.json 比分 vs groups.json 积分
# 对于每场赛果，验证两队在该组的GF/GA是否匹配
match_errors = []
for m in results["matches"]:
    home, away = m["home"], m["away"]
    hg, ag = map(int, m["score"].split("-"))
    # 找到这两队在哪个组
    for gid, g in groups.items():
        if home in g["standings"] and away in g["standings"]:
            hs, as_ = g["standings"][home], g["standings"][away]
            # 检查：该队至少打了这场比赛（有积分）
            if hs["p"] > 0 and as_["p"] > 0:
                # GF应该 >= 本场进球（因为可能还有别的比赛）
                if hs["gf"] < hg or as_["ga"] < hg:
                    match_errors.append(f"{home}-{away}: groups GF/GA不匹配 {m['score']}")
                if as_["gf"] < ag or hs["ga"] < ag:
                    match_errors.append(f"{home}-{away}: groups GF/GA不匹配 {m['score']}")

if match_errors:
    for e in match_errors:
        check(False, e)
else:
    check(match_errors == [], f"results.json vs groups.json 比分交叉验证通过 ({results_count}场)")

# 1.3 检查 dashboard.py 是否从 JSON 读取数据（非硬编码）
dashboard_py = open("dashboard.py").read()
has_hardcoded_matches = '("6/1' in dashboard_py or '("6/11"' in dashboard_py
check(not has_hardcoded_matches, "dashboard.py 不再硬编码 MATCH_RESULTS")
check('results["matches"]' in dashboard_py, "dashboard.py 从 results.json 读取赛果")
check('news.get("items"' in dashboard_py, "dashboard.py 从 news.json 读取新闻")

# 1.4 新闻/伤病/八卦数量统计
news_count = len(news.get("items", []))
injury_count = sum(len(v) for v in injuries.values())
gossip_count = len(gossip)
print(f"  news.json: {news_count}条新闻")
print(f"  injuries.json: {injury_count}条伤病")
print(f"  gossip.json: {gossip_count}队追踪")

# 1.5 检查 sources.json 覆盖率
srcs = sources.get("sources", {})
coverage = sources.get("coverage_stats", {})
check(coverage.get("total_sources", 0) == len(srcs),
      f"coverage_stats.total_sources({coverage.get('total_sources')}) vs 实际({len(srcs)})")

# === LAYER 2: 媒体源新鲜度 ===
print("\n📡 Layer 2: 媒体源新鲜度")

today_str = str(date.today())
stale_count = 0
blocked_count = 0

for sid, s in sorted(srcs.items()):
    last = s.get("last_check", "")
    status = s.get("status", "")
    days_ago = (date.today() - datetime.strptime(last, "%Y-%m-%d").date()).days if last else 999

    if status == "blocked":
        print(f"  ❌ {s['name']:<25} 被墙 (上次:{last})")
        blocked_count += 1
    elif days_ago > 2:
        print(f"  ⚠️ {s['name']:<25} 过期{days_ago}天 (上次:{last}) — 需要更新")
        stale_count += 1
    else:
        items = s.get("items_found", 0)
        print(f"  ✅ {s['name']:<25} {days_ago}天前 | {items}条 | {s['type']}")

active_count = len(srcs) - stale_count - blocked_count
print(f"\n  活跃: {active_count} | 过期: {stale_count} | 被墙: {blocked_count} | 总计: {len(srcs)}")

# === LAYER 3: 内容新鲜度 ===
print("\n📰 Layer 3: 内容新鲜度 (数据条目本身的时效)")

today = date.today()
CONTENT_STALE_WARN = 3   # 超过3天警告
CONTENT_STALE_FAIL = 7   # 超过7天严重

# 3.1 伤病条目时效
injury_stale = []
injury_no_date = []
total_injuries = 0
for tid, inj_list in injuries.items():
    for inj in inj_list:
        total_injuries += 1
        dt = inj.get("date", "")
        if not dt:
            injury_no_date.append(f"{tid}/{inj['player']}")
            continue
        try:
            days = (today - datetime.strptime(dt[:10], "%Y-%m-%d").date()).days
            if days > CONTENT_STALE_FAIL:
                injury_stale.append((tid, inj["player"], days, FAIL))
            elif days > CONTENT_STALE_WARN:
                injury_stale.append((tid, inj["player"], days, WARN))
        except: pass

if injury_no_date:
    for item in injury_no_date:
        check(False, f"伤病缺日期: {item}")
if injury_stale:
    injury_stale.sort(key=lambda x: -x[2])
    for tid, player, days, sev in injury_stale[:8]:
        check(False, f"伤病过期{days}天: {tid}/{player}", sev)
    if len(injury_stale) > 8:
        print(f"  ... 还有{len(injury_stale)-8}条过期伤病")
else:
    check(True, f"伤病条目全部新鲜 ({total_injuries}条, 均≤{CONTENT_STALE_WARN}天)")

# 3.2 八卦条目时效
gossip_stale = []
total_gossip_entries = 0
for tid, g in gossip.items():
    for cat in ["locker_room", "political", "player_off_field"]:
        if cat in g and g[cat].get("score", 0) != 0:
            total_gossip_entries += 1
            dt = g[cat].get("date", "")
            if not dt: continue
            try:
                days = (today - datetime.strptime(dt[:10], "%Y-%m-%d").date()).days
                if days > CONTENT_STALE_WARN:
                    gossip_stale.append((tid, cat, days))
            except: pass

if gossip_stale:
    gossip_stale.sort(key=lambda x: -x[2])
    for tid, cat, days in gossip_stale[:5]:
        check(False, f"八卦过期{days}天: {tid}/{cat}", WARN)
else:
    check(True, f"八卦条目全部新鲜 ({total_gossip_entries}条)")

# 3.3 新闻条目时效
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
    newest = min(news_dates)
    oldest = max(news_dates)
    news_stale_days = 5  # 新闻允许5天（比赛报道有时效但仍有参考价值）
    check(oldest <= news_stale_days,
          f"新闻最旧{oldest}天, 平均{avg_age:.1f}天 — 需要更新",
          WARN if oldest > news_stale_days else PASS)
    # 近24小时新闻覆盖率
    recent = sum(1 for d in news_dates if d <= 1)
    check(recent >= 5, f"近24小时仅{recent}条新闻, 信息可能滞后", WARN)
    print(f"  新闻: {len(news_dates)}条, 最新{newest}天前, 最旧{oldest}天前, 平均{avg_age:.1f}天, 近24h:{recent}条")
else:
    check(False, "新闻条目无日期信息")

# 3.4 检查未覆盖的球队
teams_with_injury = set(injuries.keys())
teams_with_gossip = set(gossip.keys())
all_teams = set(teams.keys())
played_teams = set()
for gid, g in groups.items():
    for tid, s in g["standings"].items():
        if s["w"] + s["d"] + s["l"] > 0:
            played_teams.add(tid)

missing_injury = played_teams - teams_with_injury
missing_gossip = played_teams - teams_with_gossip
if missing_injury:
    print(f"  💡 已赛球队缺伤病追踪 ({len(missing_injury)}支): {', '.join(sorted(list(missing_injury))[:8])}...")
if missing_gossip:
    print(f"  💡 已赛球队缺八卦追踪 ({len(missing_gossip)}支): {', '.join(sorted(list(missing_gossip))[:8])}...")

# === LAYER 4: 投注合规 (Lottery v3.1) ===
print("\n💰 Layer 4: 投注方案合规")

# 4.1 SP数据文件检查
sp_path = DATA / "sp.json"
if sp_path.exists():
    sp_data = load("sp.json")
    sp_matches = sp_data.get("matches", {})
    handicap_sp = sp_data.get("handicap", {})
    sp_updated = sp_data.get("updated", "")
    if sp_updated:
        try:
            sp_days = (date.today() - datetime.strptime(sp_updated[:10], "%Y-%m-%d").date()).days
            check(sp_days <= 2, f"sp.json {sp_days}天未更新", WARN if sp_days > 1 else PASS)
            print(f"  sp.json: {len(sp_matches)}场SP, {len(handicap_sp)}场让球盘, 更新于{sp_updated[:10]}")
        except: pass
else:
    check(False, "sp.json 不存在! 方案将使用模型估算赔率", FAIL)

# 4.2 SP覆盖率 vs 待赛赛程
from engine.lottery import MATCH_SCHEDULE
results_data = json.load(open(DATA/"results.json"))
played = {f"{m['home']}-{m['away']}" for m in results_data["matches"]}
upcoming = {mid for mid in MATCH_SCHEDULE if mid not in played}
covered = {mid for mid in upcoming if mid in sp_matches}
missing_sp = upcoming - covered
check(len(covered) >= len(upcoming) * 0.5,
      f"SP覆盖 {len(covered)}/{len(upcoming)} 待赛 ({len(covered)/max(1,len(upcoming))*100:.0f}%)",
      WARN if len(missing_sp) > len(upcoming) // 2 else PASS)
if missing_sp:
    print(f"  ⚠️ 缺SP数据 ({len(missing_sp)}场): {', '.join(sorted(list(missing_sp))[:8])}")

# 4.3 截止时间审计: 检查待赛中有多少已过截止
from datetime import datetime as dt
deadline_skipped = 0
for mid in upcoming:
    ts = MATCH_SCHEDULE.get(mid, "")
    if not ts: continue
    try:
        parts = ts.split(); m, d = parts[0].split("/"); h, mi = parts[1].split(":")
        kickoff = dt(2026, int(m), int(d), int(h), int(mi))
        if kickoff <= dt.now():
            deadline_skipped += 1
    except: pass
check(deadline_skipped == 0,
      f"{deadline_skipped}场已过截止时间(方案v3.1会自动跳过)",
      WARN if deadline_skipped > 0 else PASS)

# 4.4 投注方案可用性测试
try:
    sys.path.insert(0, str(Path(".")))
    from engine.lottery import generate_plan
    test_matches = sorted(list(upcoming))[:8] if len(upcoming) >= 4 else sorted(list(upcoming))
    if test_matches:
        plan = generate_plan(test_matches)
        has_error = "error" in plan
        skipped_count = len(plan.get("skipped", []))
        if has_error and skipped_count < len(test_matches):
            check(False, "方案生成异常: 部分场次可用但标记error", FAIL)
        elif has_error:
            print("  ⚠️ 方案: 今日全部不可投(截止已过)")
            check(True, "", PASS)
        else:
            usable = len(plan.get("classified",{}).get("conservative_pool",[]))
            check(True, f"方案生成正常: {usable}场保守池可用", PASS)
        if skipped_count:
            print(f"  ⚠️ 截止跳过{skipped_count}场: {', '.join(m for m,_ in plan.get('skipped',[])[:4])}")
except Exception as e:
    check(False, f"方案引擎异常: {e}", FAIL)

# 4.5 SP数据合理性
if sp_matches:
    odd_sp = []
    for mid, odds in sp_matches.items():
        h, d, a = odds.get("home", 0), odds.get("draw", 0), odds.get("away", 0)
        if h == 0: continue
        implied = 1/h + 1/d + 1/a
        if implied > 1.15: odd_sp.append(f"{mid}(返还{implied:.0%})")
        if implied < 0.85: odd_sp.append(f"{mid}(返还{implied:.0%})")
    check(len(odd_sp) == 0, f"SP异常场次: {', '.join(odd_sp[:3])}" if odd_sp else "SP返还率合理",
          WARN if odd_sp else PASS)

# 汇总
total_issues = len(issues)
print(f"\n{'═' * 70}")
print(f"审计完成: {total_issues}个问题")
if total_issues == 0:
    print("🏆 数据同步: 全部通过 — JSON数据 ↔ dashboard.py 完全同步")
else:
    for sev, msg in issues:
        print(f"  {sev} {msg}")
print(f"建议: python3 dashboard.py 重新生成Dashboard")
print(f"{'═' * 70}")
