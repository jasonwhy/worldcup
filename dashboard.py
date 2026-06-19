#!/usr/bin/env python3
"""世界杯预测系统 Dashboard v5.0 — FIFA/Fox风格 + 赛程总览 + 实时"""
import json, sys, os, time
from pathlib import Path
from datetime import date, datetime
from math import exp

DATA = Path(__file__).parent / "data"

def auto_refresh():
    today = date.today()
    changed = False
    if (DATA / "gossip.json").exists():
        gossip = json.load(open(DATA / "gossip.json"))
        for tid, g in gossip.items():
            for cat in ["locker_room","political","player_off_field"]:
                if cat not in g: continue
                e = g[cat]; score = e.get("score",0); original = e.get("original_score",score)
                if "original_score" not in e: e["original_score"] = score
                ds = e.get("date","")
                if not ds or original == 0: continue
                try:
                    days = (today - datetime.strptime(ds,"%Y-%m-%d").date()).days
                    if days > 0:
                        ns = round(original * exp(-0.05*days), 1)
                        if ns != score: e["score"] = ns; changed = True
                except: pass
        if changed: json.dump(gossip, open(DATA/"gossip.json","w"), indent=2, ensure_ascii=False)
    if (DATA / "injuries.json").exists():
        injuries = json.load(open(DATA/"injuries.json"))
        for tid in injuries:
            for inj in injuries[tid]:
                rd = inj.get("return_date","")
                if rd and inj["status"] == "doubtful":
                    try:
                        if datetime.strptime(rd,"%Y-%m-%d").date() <= today:
                            inj["status"] = "active"; changed = True
                    except: pass
        if changed: json.dump(injuries, open(DATA/"injuries.json","w"), indent=2, ensure_ascii=False)

auto_refresh()
# 后验校准 (自动调整模型参数)
try:
    from engine.calibrator import calibrate
    calibrate(verbose=True)
except Exception as e:
    pass

def load(n): return json.load(open(DATA/n))

teams = load("teams.json")
groups = load("groups.json")
injuries = load("injuries.json")
gossip = load("gossip.json")
results = load("results.json")
news = load("news.json")
live_scores = load("live_scores.json") if (DATA / "live_scores.json").exists() else {"matches_in_progress": []}

sys.path.insert(0, str(Path(__file__).parent))
from engine.predictor import final_score, predict
from engine.lottery import generate_plan, format_lottery, MATCH_SCHEDULE

F = {"France":"🇫🇷","Spain":"🇪🇸","Argentina":"🇦🇷","England":"🏴󠁧󠁢󠁥󠁮󠁧󠁿","Brazil":"🇧🇷","Portugal":"🇵🇹","Germany":"🇩🇪","Netherlands":"🇳🇱","Belgium":"🇧🇪","Norway":"🇳🇴","Morocco":"🇲🇦","Colombia":"🇨🇴","Mexico":"🇲🇽","South Korea":"🇰🇷","United States":"🇺🇸","Uruguay":"🇺🇾","Croatia":"🇭🇷","Japan":"🇯🇵","Senegal":"🇸🇳","Switzerland":"🇨🇭","Austria":"🇦🇹","Sweden":"🇸🇪","Canada":"🇨🇦","Australia":"🇦🇺","Ecuador":"🇪🇨","Türkiye":"🇹🇷","Scotland":"🏴","Czechia":"🇨🇿","Egypt":"🇪🇬","Iran":"🇮🇷","Ghana":"🇬🇭","Algeria":"🇩🇿","Tunisia":"🇹🇳","South Africa":"🇿🇦","Cape Verde":"🇨🇻","Saudi Arabia":"🇸🇦","Qatar":"🇶🇦","Iraq":"🇮🇶","Jordan":"🇯🇴","Uzbekistan":"🇺🇿","New Zealand":"🇳🇿","Panama":"🇵🇦","Haiti":"🇭🇹","Curaçao":"🇨🇼","DR Congo":"🇨🇩","Congo DR":"🇨🇩","Bosnia-Herzegovina":"🇧🇦","Bosnia":"🇧🇦","Paraguay":"🇵🇾","Cote dIvoire":"🇨🇮","Ivory Coast":"🇨🇮"}
def flag(name): return f"{F.get(name,'🏳️')} {name}"

# Rankings
ESPN = {"ESP":1,"FRA":2,"ARG":3,"ENG":4,"BRA":5,"POR":6,"GER":7,"NED":8,"MAR":9,"NOR":10,"BEL":11,"COL":12,"SEN":13,"CRO":14,"JPN":15}
FOX  = {"FRA":1,"ESP":2,"ENG":3,"COL":4,"ARG":5,"POR":6,"BRA":7,"NED":8,"GER":9,"CRO":10,"BEL":11,"USA":12,"MAR":13,"MEX":14,"URU":15,"NOR":16}
YHOO = {"FRA":1,"ESP":2,"ARG":3,"ENG":4,"POR":5,"BRA":6,"GER":7,"NED":8,"BEL":9,"COL":10,"MAR":11,"SEN":12,"ECU":13,"URU":14,"CRO":15}
consensus = {}
for tid in set(list(ESPN)+list(FOX)+list(YHOO)):
    r = [v for d in [ESPN,FOX,YHOO] if tid in d for v in [d[tid]]]
    consensus[tid] = round(sum(r)/len(r),1) if r else 0

rankings = []
for tid in teams:
    fs = final_score(tid)
    rankings.append((tid, fs["name"], fs["total"], fs["hard_data"]["score"], fs["betting"]["score"], fs["gossip"]["score"]))
rankings.sort(key=lambda x: x[2], reverse=True)

# ============================================================
# PANEL 1: 赛程总览 (Schedule)
# ============================================================
# Build live score map
live_map = {}
for lm in live_scores.get("matches_in_progress", []):
    live_map[lm["match_id"]] = lm

played_map = {}
for m in results["matches"]:
    played_map[f"{m['home']}-{m['away']}"] = m

# Group all scheduled matches by date
venue_tz = {
    # Match: (UTC_offset_in_June, venue_city)
    "MEX-RSA": (-6, "Mexico City"), "KOR-CZE": (-6, "Mexico City"),
    "CAN-BIH": (-4, "Toronto"), "USA-PAR": (-7, "Los Angeles"),
    "HAI-SCO": (-7, "San Francisco"), "AUS-TUR": (-7, "Seattle"),
    "BRA-MAR": (-4, "Atlanta"), "QAT-SUI": (-7, "Vancouver"),
    "GER-CUW": (-5, "Houston"), "NED-JPN": (-5, "Dallas"),
    "CIV-ECU": (-5, "Kansas City"), "SWE-TUN": (-6, "Monterrey"),
    "ESP-CPV": (-4, "Atlanta"), "BEL-EGY": (-7, "Seattle"),
    "KSA-URU": (-4, "Miami"), "IRN-NZL": (-7, "Los Angeles"),
    "FRA-SEN": (-4, "New Jersey"), "IRQ-NOR": (-4, "Boston"),
    "ARG-ALG": (-5, "Kansas City"), "AUT-JOR": (-7, "San Francisco"),
    "POR-COD": (-5, "Houston"), "ENG-CRO": (-5, "Dallas"),
    "GHA-PAN": (-4, "Toronto"), "COL-UZB": (-6, "Mexico City"),
    "CZE-RSA": (-7, "Los Angeles"), "SUI-BIH": (-7, "San Francisco"),
    "CAN-QAT": (-7, "Vancouver"), "MEX-KOR": (-4, "Philadelphia"),
    # 6/20
    "USA-AUS": (-7, "Seattle"), "SCO-MAR": (-4, "Boston"),
    "BRA-HAI": (-4, "Philadelphia"), "TUR-PAR": (-7, "Santa Clara"),
    # 6/21
    "GER-CIV": (-5, "Houston"), "ECU-CUW": (-5, "Kansas City"),
    "NED-SWE": (-5, "Dallas"), "JPN-TUN": (-6, "Monterrey"),
    # 6/22
    "BEL-IRN": (-7, "Seattle"), "EGY-NZL": (-4, "Miami"),
    "ESP-KSA": (-4, "Atlanta"), "CPV-URU": (-4, "Miami"),
}

def format_match_time(beijing_time, utc_offset):
    """将北京时间(UTC+8)转为当地时间和东8区时间显示"""
    bj_parts = beijing_time.split()
    bj_date = bj_parts[0]  # "6/18"
    bj_hh, bj_mm = bj_parts[1].split(":") if len(bj_parts)>1 else ("00","00")
    # 当地时间 = 北京时间 + (local_utc - 8)
    local_hour = int(bj_hh) + (utc_offset - 8)
    local_day_offset = 0
    if local_hour < 0:
        local_hour += 24; local_day_offset = -1
    elif local_hour >= 24:
        local_hour -= 24; local_day_offset = 1
    # Format local date
    month, day = bj_date.split("/")
    local_month, local_day = int(month), int(day) + local_day_offset
    return f"{local_month}/{local_day} {local_hour:02d}:{bj_mm}", f"{month}/{day} {bj_hh}:{bj_mm}"

schedule_by_date = {}
for match_id, time_str in sorted(MATCH_SCHEDULE.items()):
    parts = time_str.split()
    d = parts[0]
    t = parts[1] if len(parts)>1 else ""
    if d not in schedule_by_date:
        schedule_by_date[d] = []
    schedule_by_date[d].append((match_id, t))

schedule_rows = ""
for sdate in sorted(schedule_by_date.keys(), key=lambda x: (int(x.split('/')[0]), int(x.split('/')[1]))):
    matches = schedule_by_date[sdate]
    played_count = sum(1 for m,t in matches if m in played_map)
    total_count = len(matches)
    label = "✅ 已完赛" if played_count == total_count else ("🔄 进行中" if played_count > 0 else "📅 待赛")

    schedule_rows += f"""<div class="matchday-group">
    <div class="matchday-header"><span class="matchday-date">{sdate}</span><span class="matchday-badge">{label}</span><span class="matchday-count">{played_count}/{total_count}</span></div>"""

    for match_id, kickoff in matches:
        home, away = match_id.split("-")
        hn = teams.get(home,{}).get("name",home)
        an = teams.get(away,{}).get("name",away)

        vinfo = venue_tz.get(match_id, (-5, ""))
        local_utc, venue = vinfo[0], vinfo[1]
        local_time, bj_time = format_match_time(f"{sdate} {kickoff}", local_utc)

        if match_id in played_map:
            m = played_map[match_id]
            ok = m["prediction_correct"]
            score = m["score"]
            cls = "result-win" if ok=="✅" else "result-loss"
            schedule_rows += f"""<div class="match-card played {cls}">
            <div class="match-time">🏟 {venue} 当地 {local_time} | 🇨🇳 北京 {bj_time}</div>
            <div class="match-teams">{flag(hn)} <span class="match-score">{score}</span> {flag(an)}</div>
            <div class="match-note">{m['note'][:30]}</div></div>"""
        elif match_id in live_map:
            lm = live_map[match_id]
            hg = lm.get("home_goals", 0)
            ag = lm.get("away_goals", 0)
            minute = lm.get("minute", "LIVE")
            source = lm.get("source", "")
            schedule_rows += f"""<div class="match-card live-now">
            <div class="match-time"><span class="live-dot"></span> {minute}' · 🏟 {venue} · 🇨🇳 北京 {bj_time}</div>
            <div class="match-teams">{flag(hn)} <span class="match-score live-score">{hg}-{ag}</span> {flag(an)}</div>
            <div class="match-note" style="color:var(--red);font-weight:600">🔴 比赛进行中</div></div>"""
        else:
            try:
                p = predict(match_id)
                if "error" not in p:
                    r = p["prediction"]
                    sw,sd,sl = r['win_pct'], r['draw_pct'], r['lose_pct']
                    top = r['top_scores'][0]['score']
                    schedule_rows += f"""<div class="match-card upcoming">
                    <div class="match-time">🏟 {venue} · 🇨🇳 北京 {bj_time}</div>
                    <div class="match-teams">{flag(hn)} <span class="match-vs">vs</span> {flag(an)}</div>
                    <div class="match-prediction">
                      <span class="pred-item win">W {sw:.0f}%</span>
                      <span class="pred-item draw">D {sd:.0f}%</span>
                      <span class="pred-item lose">L {sl:.0f}%</span>
                      <span class="pred-score">🏆 {top}</span>
                    </div></div>"""
                else:
                    schedule_rows += f"""<div class="match-card upcoming"><div class="match-teams">{flag(hn)} vs {flag(an)}</div></div>"""
            except:
                schedule_rows += f"""<div class="match-card upcoming"><div class="match-teams">{flag(hn)} vs {flag(an)}</div></div>"""

    schedule_rows += "</div>"

# ============================================================
# PANEL 2: 赛果回测 (Results)
# ============================================================
# Group by date
from collections import defaultdict
results_by_date = defaultdict(list)
for m in results["matches"]:
    results_by_date[m["date"]].append(m)

result_rows = ""
for rdate in sorted(results_by_date.keys(), key=lambda x: (int(x.split('/')[0]), int(x.split('/')[1])), reverse=True):
    day_matches = results_by_date[rdate]
    result_rows += f"""<div class="matchday-group"><div class="matchday-header"><span class="matchday-date">{rdate}</span></div><table class="data-table"><thead><tr><th>比赛</th><th>比分</th><th>判</th><th>备注</th></tr></thead><tbody>"""
    for m in day_matches:
        hn = teams.get(m["home"],{}).get("name",m["home"])
        an = teams.get(m["away"],{}).get("name",m["away"])
        ok = m["prediction_correct"]
        cls = "text-green" if ok=="✅" else "text-red"
        result_rows += f"<tr><td>{flag(hn)} vs {flag(an)}</td><td><b>{m['score']}</b></td><td class='{cls}'>{ok}</td><td class='note-cell'>{m['note'][:40]}</td></tr>"
    result_rows += "</tbody></table></div>"

# == 比分回测 (Score Prediction Backtest) ==
score_backtest_rows = ""
score_top1_hits = 0
score_top3_hits = 0
goal_error_total = 0
backtest_n = 0

for m in results["matches"]:
    mid = f"{m['home']}-{m['away']}"
    try:
        p = predict(mid)
        if "error" in p: continue
        r = p["prediction"]
        backtest_n += 1
        actual = m["score"]
        pred_top = r["top_scores"][0]["score"]
        if actual == pred_top:
            score_top1_hits += 1
        hit_top3 = actual in [s["score"] for s in r["top_scores"][:3]]
        if hit_top3:
            score_top3_hits += 1
        ah, aa = map(int, actual.split("-"))
        ph, pa = map(int, pred_top.split("-"))
        goal_error_total += abs((ah+aa) - (ph+pa))
        hn = teams.get(m["home"],{}).get("name",m["home"])
        an = teams.get(m["away"],{}).get("name",m["away"])
        hit1_mark = "✅" if actual == pred_top else ""
        hit3_mark = "✅" if hit_top3 else "❌"
        score_backtest_rows += f"<tr><td>{flag(hn)} vs {flag(an)}</td><td><b>{actual}</b></td><td>{pred_top}</td><td class='text-green'>{hit1_mark}</td><td class='{'text-green' if hit_top3 else 'text-red'}'>{hit3_mark}</td></tr>"
    except:
        pass

avg_goal_error = round(goal_error_total / max(1, backtest_n), 1)
top1_rate_str = f"{score_top1_hits/backtest_n*100:.0f}%" if backtest_n else "-"
top3_rate_str = f"{score_top3_hits/backtest_n*100:.0f}%" if backtest_n else "-"

# ============================================================
# PANEL 3: 积分排名 (Standings + Rankings)
# ============================================================
s_rows = ""
for gid in sorted(groups.keys()):
    g = groups[gid]
    st = sorted(g["standings"].items(), key=lambda x: (-x[1]["p"], -x[1]["gd"], -x[1]["gf"]))
    s_rows += f"""<div class="group-table"><div class="group-title">Group {gid}</div><table class="data-table"><thead><tr><th></th><th>球队</th><th>分</th><th>场</th><th>战绩</th><th>GF:GA</th><th>GD</th></tr></thead><tbody>"""
    for i, (tid, s) in enumerate(st):
        name = teams.get(tid,{}).get("name",tid)
        pos = "🥇" if i==0 else ("🥈" if i==1 else ("📌" if i==2 else "  "))
        s_rows += f"<tr><td>{pos}</td><td>{flag(name)}</td><td><b>{s['p']}</b></td><td>{s['w']+s['d']+s['l']}</td><td>{s['w']}-{s['d']}-{s['l']}</td><td>{s['gf']}:{s['ga']}</td><td class='{'text-green' if s['gd']>0 else ('text-red' if s['gd']<0 else '')}'>{s['gd']:+d}</td></tr>"
    s_rows += "</tbody></table></div>"

r_rows = ""
for i, (tid, name, total, hard, bet, goss) in enumerate(rankings, 1):
    es, fx, yh, cn = ESPN.get(tid,"-"), FOX.get(tid,"-"), YHOO.get(tid,"-"), consensus.get(tid,"-")
    warn = "🔴" if goss<85 else ("🟡" if goss<95 else "")
    dev = ""
    if isinstance(cn,(int,float)) and abs(i-cn)>8: dev = f" ⚠️{abs(i-cn):.0f}"
    elif isinstance(cn,(int,float)) and abs(i-cn)>4: dev = f" △{abs(i-cn):.0f}"
    r_rows += f"<tr><td>{i}</td><td><b>{name}</b>{warn}{dev}</td><td class='num-cell'>{total:.1f}</td><td class='num-cell'>{hard:.1f}</td><td class='num-cell'>{bet:.1f}</td><td class='num-cell'>{goss:.1f}</td><td class='num-cell'>{es}</td><td class='num-cell'>{fx}</td><td class='num-cell'>{yh}</td><td class='num-cell'>{cn}</td></tr>"

# ============================================================
# PANEL 4: 情报中心 (Intel: News + Injuries + Gossip)
# ============================================================
# News
news_rows = ""
for item in news.get("items",[])[:30]:
    badge = item.get("badge","")
    d = item.get("date","")
    dt = f"{int(d[5:7])}/{int(d[8:10])}" if len(d)>=10 else d
    title = item.get("title","")
    detail = f"{item.get('detail','')} ({item.get('source','')})"
    news_rows += f"<tr><td>{badge}</td><td class='date-cell'>{dt}</td><td><b>{title}</b></td><td class='note-cell'>{detail[:55]}</td></tr>"

# Injuries
i_rows = ""
for tid, inj_list in sorted(injuries.items()):
    name = teams.get(tid,{}).get("name",tid)
    for inj in inj_list:
        badge = "🔴" if inj["status"] in ("out","out_retired") else ("🟡" if inj["status"]=="doubtful" else "🟢")
        dt = inj.get('date','')[:10] if inj.get('date') else ''
        i_rows += f"<tr><td>{badge}</td><td class='date-cell'>{dt}</td><td>{flag(name)}</td><td>{inj['player']}</td><td class='note-cell'>{inj.get('role','')}</td><td>{inj['status']}</td><td class='note-cell'>{inj.get('reason','')[:40]}</td></tr>"

# Gossip
g_rows = ""
for tid, g in sorted(gossip.items()):
    name = teams.get(tid,{}).get("name",tid)
    lr = g.get("locker_room",{})
    pol = g.get("political",{})
    off = g.get("player_off_field",{})
    total = abs(lr.get("score",0)) + abs(pol.get("score",0)) + abs(off.get("score",0))
    if total > 0:
        badge = "🔴" if total>=7 else ("🟡" if total>=3 else "🟢")
        dt = lr.get('date','') or pol.get('date','') or off.get('date','') or ''
        g_rows += f"<tr><td>{badge}</td><td class='date-cell'>{dt[:10]}</td><td>{flag(name)}</td><td class='num-cell'>{total}</td><td class='note-cell'>{lr.get('reason','')[:45]}</td><td>{'★'*pol.get('level',0)}</td></tr>"

# ============================================================
# PANEL 5: 购彩方案 (Betting) — 按日期分Tab, 卡片式布局
# ============================================================
# Collect all upcoming matchdays from schedule
from collections import OrderedDict
upcoming_dates = OrderedDict()
for match_id, time_str in sorted(MATCH_SCHEDULE.items()):
    parts = time_str.split()
    d = parts[0]  # "6/18"
    t = parts[1] if len(parts)>1 else ""
    if match_id in played_map: continue  # Skip played
    if d not in upcoming_dates: upcoming_dates[d] = []
    upcoming_dates[d].append((match_id, t))

# Generate per-date betting content
bet_date_tabs = ""
bet_date_panels = ""
first_date = True

for bdate, bmatches in upcoming_dates.items():
    match_ids = [m[0] for m in bmatches]
    date_label = f"{bdate} ({len(bmatches)}场)"
    bdate_safe = bdate.replace("/","-")
    active_cls = "active" if first_date else ""
    bet_date_tabs += f'<button class="bet-date-tab {active_cls}" onclick="showBetDate(\'bet-{bdate_safe}\',this)">{date_label}</button>'
    first_date = False

    try:
        plan = generate_plan(match_ids)
        plan_text = format_lottery(plan).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    except:
        plan_text = "方案生成中..."

    match_cards = ""
    for bmid, bkickoff in bmatches:
        home, away = bmid.split("-")
        hn = teams.get(home,{}).get("name",home)
        an = teams.get(away,{}).get("name",away)
        try:
            p = predict(bmid)
            if "error" not in p:
                r = p["prediction"]
                wpct, dpct, lpct = r['win_pct'], r['draw_pct'], r['lose_pct']
                top = r['top_scores'][0]['score']

                best = max(("主胜",wpct),("平局",dpct),("客胜",lpct), key=lambda x: x[1])
                pick_cls = "pick-win" if best[0]=="主胜" else ("pick-draw" if best[0]=="平局" else "pick-lose")
                cold = r.get('cold_alert','')
                conf = r.get('confidence','中')
                cold_icon = "🔥" if "高" in cold else ("⚠️" if "中" in cold else "✅")

                match_cards += f"""<div class="bet-card">
                <div class="bet-card-header">
                  <span class="bet-time">{bdate} {bkickoff}</span>
                  <span class="bet-confidence {'conf-high' if conf=='高' else ('conf-mid' if conf=='中' else 'conf-low')}">{conf}置信</span>
                </div>
                <div class="bet-teams">{flag(hn)} <span class="bet-vs">VS</span> {flag(an)}</div>
                <div class="bet-probs">
                  <div class="prob-bar win" style="flex:{wpct}"><span>主 {wpct:.0f}%</span></div>
                  <div class="prob-bar draw" style="flex:{dpct}"><span>平 {dpct:.0f}%</span></div>
                  <div class="prob-bar lose" style="flex:{lpct}"><span>客 {lpct:.0f}%</span></div>
                </div>
                <div class="bet-pick-row">
                  <span class="bet-pick-label {pick_cls}">推荐: {best[0]} ({best[1]:.0f}%)</span>
                  <span class="bet-score">预测: {top}</span>
                  <span class="bet-cold">{cold_icon} {cold[:6]}</span>
                </div></div>"""
        except:
            match_cards += f"""<div class="bet-card"><div class="bet-teams">{flag(hn)} vs {flag(an)}</div></div>"""

    active_panel = 'style="display:block"' if bdate == list(upcoming_dates.keys())[0] else 'style="display:none"'
    bet_date_panels += f"""<div id="bet-{bdate_safe}" class="bet-date-panel" {active_panel}>
    <div class="bet-matches-grid">{match_cards}</div>
    <div class="bet-plan-section">
      <div class="bet-plan-header">📋 {bdate} 购彩方案 · 200元预算</div>
      <div class="betting-plan">{plan_text}</div>
    </div></div>"""


# ============================================================
# PANEL 0: 亮点 (Golden Boot + Upsets + Bracket + Form)
# ============================================================

# --- Golden Boot ---
scorer_notes = {
    "L. Messi": (3, "ARG"), "J. David": (3, "CAN"),
    "E. Haaland": (2, "NOR"), "Y. Ayari": (2, "SWE"),
    "K. Havertz": (2, "GER"), "F. Balogun": (2, "USA"),
    "H. Kane": (2, "ENG"), "J. Quinones": (2, "MEX"),
    "B. Just": (2, "NZL"), "Mbappe": (2, "FRA"),
    "Irankunda": (1, "AUS"), "Schmid": (1, "AUT"),
    "Arnautovic": (1, "AUT"), "F. Nmecha": (1, "GER"),
    "Musiala": (1, "GER"), "Schlotterbeck": (1, "GER"),
    "Undav": (1, "GER"), "Brown": (1, "GER"),
    "Summerville": (1, "NED"), "Van Dijk": (1, "NED"),
    "Nakamura": (1, "JPN"), "Kamada": (1, "JPN"),
    "Amad": (1, "CIV"), "Isak": (1, "SWE"), "Gyokeres": (1, "SWE"),
    "Hussein": (1, "IRQ"), "Olwan": (1, "JOR"),
    "Ashour": (1, "EGY"), "Araujo": (1, "URU"),
    "Al-Amri": (1, "KSA"), "Rashford": (1, "ENG"),
    "Bellingham": (1, "ENG"), "L. Diaz": (1, "COL"),
    "Hwang": (1, "KOR"),
}
boot_sorted = sorted(scorer_notes.items(), key=lambda x: -x[1][0])
boot_rows = ""
for i, (name, (goals, tid)) in enumerate(boot_sorted[:15], 1):
    tn = teams.get(tid,{}).get("name", tid)
    medal = "🥇" if i==1 else ("🥈" if i==2 else ("🥉" if i==3 else f"{i}."))
    cls = "gold" if i<=3 else ""
    boot_rows += f"<tr><td class='num-cell'>{medal}</td><td>{F.get(tn,'🏳️')} {name}</td><td class='num-cell'><b>{goals}</b></td><td class='note-cell'>{tn}</td></tr>"

# --- Assist Leaders ---
assist_notes = {
    "C. Wood": (2, "NZL"), "A. Isak": (2, "SWE"),
    "R. Gravenberch": (2, "NED"), "J. Kimmich": (2, "GER"),
    "D. Undav": (2, "GER"), "C. Roldan": (1, "USA"),
    "G. Reyna": (1, "USA"), "W. McKennie": (1, "USA"),
}
assist_sorted = sorted(assist_notes.items(), key=lambda x: -x[1][0])
assist_rows = ""
for i, (name, (ast, tid)) in enumerate(assist_sorted[:8], 1):
    tn = teams.get(tid,{}).get("name", tid)
    assist_rows += f"<tr><td class='num-cell'>{i}.</td><td>{F.get(tn,'🏳️')} {name}</td><td class='num-cell'><b>{ast}</b></td><td class='note-cell'>{tn}</td></tr>"

# --- Upset Wall ---
upsets = [
    ("🇨🇻 Cape Verde 0-0 🇪🇸 Spain", "人口<50万岛国首秀逼平欧洲冠军, 27射0球, 40岁Vozinha封神", "⭐⭐⭐"),
    ("🇨🇩 DR Congo 1-1 🇵🇹 Portugal", "52年后回归首秀逼平葡萄牙, Wissa打入历史首球", "⭐⭐⭐"),
    ("🇸🇦 Saudi Arabia 1-1 🇺🇾 Uruguay", "换帅后首战逼平南美劲旅, Araujo 80分救主", "⭐⭐"),
    ("🇨🇮 Ivory Coast 1-0 🇪🇨 Ecuador", "Amad替补绝杀, 非洲黑马搅局", "⭐⭐"),
    ("🇦🇺 Australia 2-0 🇹🇷 Turkiye", "低位防守+快速反击完封土耳其, 身体碾压", "⭐⭐"),
    ("🇶🇦 Qatar 1-1 🇨🇭 Switzerland", "东道主VAR争议下逼平欧洲二档", "⭐"),
]
upset_rows = ""
for match, detail, level in upsets:
    upset_rows += f"""<div class="upset-card">
    <div class="upset-level">{level}</div>
    <div class="upset-match">{match}</div>
    <div class="upset-detail">{detail}</div>
</div>"""

# --- Bracket Projection ---
# Get current group leaders + runners-up
group_order = []
for gid in sorted(groups.keys()):
    g = groups[gid]
    st = sorted(g["standings"].items(), key=lambda x: (-x[1]["p"], -x[1]["gd"], -x[1]["gf"]))
    group_order.append((gid, st))

# Simple knockout bracket visualization (top 2 from each group)
bracket_rows = ""
for i in range(0, 12, 2):
    g1, st1 = group_order[i]
    g2, st2 = group_order[i+1]
    a_tid = st1[0][0]; a_name = teams.get(a_tid,{}).get("name", a_tid)
    b_tid = st2[1][0]; b_name = teams.get(b_tid,{}).get("name", b_tid)
    c_tid = st2[0][0]; c_name = teams.get(c_tid,{}).get("name", c_tid)
    d_tid = st1[1][0]; d_name = teams.get(d_tid,{}).get("name", d_tid)
    bracket_rows += f"""<div class="bracket-pair">
    <div class="bracket-label">{g1}1 vs {g2}2</div>
    <div class="bracket-teams">{flag(a_name)} vs {flag(b_name)}</div>
</div>
<div class="bracket-pair">
    <div class="bracket-label">{g2}1 vs {g1}2</div>
    <div class="bracket-teams">{flag(c_name)} vs {flag(d_name)}</div>
</div>"""

# --- Form Trends ---
hot_teams = []
cold_teams = []
for tid in teams:
    # Find this team's result
    for m in results["matches"]:
        if m["home"] == tid or m["away"] == tid:
            name = teams.get(tid,{}).get("name", tid)
            hg, ag = map(int, m["score"].split("-"))
            if m["home"] == tid:
                gd = hg - ag
            else:
                gd = ag - hg
            if gd >= 3:
                hot_teams.append((tid, name, gd, m["score"]))
            elif gd <= -3:
                cold_teams.append((tid, name, gd, m["score"]))
            break

hot_teams.sort(key=lambda x: -x[2])
cold_teams.sort(key=lambda x: x[2])
hot_rows = "".join(f'<span class="trend-badge hot">{F.get(n,"🏳️")} {n} +{gd}</span>' for tid,n,gd,sc in hot_teams[:6])
cold_rows = "".join(f'<span class="trend-badge cold">{F.get(n,"🏳️")} {n} {gd}</span>' for tid,n,gd,sc in cold_teams[:4])

# --- Live Now / Upcoming (for Highlights panel) ---
live_now_html = ""
if live_scores.get("matches_in_progress"):
    live_now_html = '<div class="hl-card live-hl-card"><div class="hl-card-title">🔴 正在直播</div>'
    for lm in live_scores["matches_in_progress"]:
        mid = lm["match_id"]
        home, away = mid.split("-")
        hn = teams.get(home,{}).get("name",home)
        an = teams.get(away,{}).get("name",away)
        hg = lm.get("home_goals",0)
        ag = lm.get("away_goals",0)
        minute = lm.get("minute","LIVE")
        note = lm.get("note","")
        vinfo = venue_tz.get(mid, (-5, ""))
        _, bj_time = format_match_time(MATCH_SCHEDULE.get(mid, "? ?:?"), vinfo[0])
        live_now_html += f"""<div class="live-hl-match">
        <div class="live-hl-header"><span class="live-dot"></span> {minute}' · 🇨🇳 北京 {bj_time}</div>
        <div class="live-hl-teams">{flag(hn)} <span class="live-score">{hg}-{ag}</span> {flag(an)}</div>
        <div class="live-hl-note">{note[:45]}</div></div>"""
    live_now_html += '</div>'
else:
    # 无直播时显示即将进行的4场比赛
    upcoming = []
    for match_id, time_str in sorted(MATCH_SCHEDULE.items(), key=lambda x: (x[1].split()[0].split("/")[0], x[1].split()[0].split("/")[1], x[1].split()[1] if len(x[1].split())>1 else "00:00")):
        if match_id not in played_map and match_id not in live_map:
            d = time_str.split()[0]
            t = time_str.split()[1] if len(time_str.split())>1 else ""
            upcoming.append((match_id, d, t))
        if len(upcoming) >= 4:
            break
    if upcoming:
        live_now_html = '<div class="hl-card upcoming-hl-card"><div class="hl-card-title">⏰ 即将开赛</div>'
        for mid, d, t in upcoming:
            home, away = mid.split("-")
            hn = teams.get(home,{}).get("name",home)
            an = teams.get(away,{}).get("name",away)
            vinfo = venue_tz.get(mid, (-5, ""))
            local_t, bj_t = format_match_time(f"{d} {t}", vinfo[0])
            try:
                p = predict(mid)
                if "error" not in p:
                    wpct = p["prediction"]["win_pct"]
                    dpct = p["prediction"]["draw_pct"]
                    lpct = p["prediction"]["lose_pct"]
                    top_score = p["prediction"]["top_scores"][0]["score"]
                else:
                    wpct = dpct = lpct = 33
                    top_score = "?-?"
            except:
                wpct = dpct = lpct = 33
                top_score = "?-?"
            live_now_html += f"""<div class="live-hl-match">
            <div class="live-hl-header">📅 {d} {t} · 🇨🇳 {bj_t}</div>
            <div class="live-hl-teams">{flag(hn)} <span style="color:var(--text-secondary);font-size:12px">vs</span> {flag(an)}</div>
            <div style="display:flex;gap:3px;margin-top:2px">
              <span style="flex:{wpct};background:var(--bar-win);height:3px;border-radius:2px" title="主{wpct:.0f}%"></span>
              <span style="flex:{dpct};background:var(--bar-draw);height:3px;border-radius:2px" title="平{dpct:.0f}%"></span>
              <span style="flex:{lpct};background:var(--bar-lose);height:3px;border-radius:2px" title="客{lpct:.0f}%"></span>
            </div>
            <div class="live-hl-note">AI预测: {top_score} (主{wpct:.0f}% 平{dpct:.0f}% 客{lpct:.0f}%)</div></div>"""
        live_now_html += '</div>'

# ============================================================
# CSS (FIFA/Fox-inspired dark theme)
# ============================================================
CSS = """<style>
:root {
  --bg-primary: #0a0e14;
  --bg-secondary: #131820;
  --bg-card: #181f2a;
  --bg-card-hover: #1e2735;
  --border: #222b38;
  --text-primary: #e8ecf1;
  --text-secondary: #8899b4;
  --text-muted: #5a6a80;
  --accent: #ffd700;
  --accent-dim: #b8940f;
  --green: #00c853;
  --green-bg: #0a2818;
  --red: #ff1744;
  --red-bg: #280a10;
  --amber: #ff9100;
  --blue: #2196f3;
  --blue-bg: #0a1830;
  --radius: 8px;
  --radius-sm: 4px;
  --shadow: 0 2px 8px rgba(0,0,0,.3);
  --font-mono: 'SF Mono', 'Fira Code', 'Consolas', monospace;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Helvetica Neue",sans-serif;background:var(--bg-primary);color:var(--text-primary);min-height:100vh;line-height:1.5}
a{color:var(--blue);text-decoration:none}

/* Header */
.header{background:linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);border-bottom:3px solid var(--accent);padding:16px 20px;text-align:center;position:sticky;top:0;z-index:100}
.header h1{font-size:20px;font-weight:800;color:var(--accent);letter-spacing:1px;text-transform:uppercase;margin:0}
.header h1 .icon{font-size:24px}
.header .subtitle{font-size:11px;color:var(--text-secondary);margin-top:2px}
.header .live-dot{display:inline-block;width:8px;height:8px;background:var(--green);border-radius:50%;margin-right:4px;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

/* Stats Bar */
.stats-bar{display:grid;grid-template-columns:repeat(auto-fit,minmax(90px,1fr));gap:8px;padding:12px 16px;background:var(--bg-secondary);border-bottom:1px solid var(--border)}
.stat-card{background:linear-gradient(135deg,var(--bg-card),var(--bg-card-hover));border-radius:var(--radius);padding:10px 8px;text-align:center;border:1px solid var(--border);transition:transform .2s}
.stat-card:hover{transform:translateY(-2px)}
.stat-card .num{font-size:22px;font-weight:800;color:var(--accent);font-family:var(--font-mono)}
.stat-card .num.green{color:var(--green)}
.stat-card .num.red{color:var(--red)}
.stat-card .num.amber{color:var(--amber)}
.stat-card .label{font-size:10px;color:var(--text-secondary);margin-top:2px;text-transform:uppercase;letter-spacing:.5px}

/* Tab Navigation */
.tab-nav{display:flex;gap:0;padding:0 16px;background:var(--bg-secondary);border-bottom:1px solid var(--border);overflow-x:auto;position:sticky;top:92px;z-index:99}
.tab-btn{flex:1;min-width:70px;padding:10px 12px;background:none;border:none;color:var(--text-secondary);cursor:pointer;font-size:12px;font-weight:600;border-bottom:3px solid transparent;transition:all .2s;white-space:nowrap;text-align:center}
.tab-btn:hover{color:var(--text-primary);background:var(--bg-card)}
.tab-btn.active{color:var(--accent);border-bottom-color:var(--accent)}
.tab-btn .icon{font-size:14px;display:block;margin-bottom:2px}

/* Panels */
.panel{display:none;padding:12px 16px;max-width:1200px;margin:0 auto}
.panel.active{display:block}

/* Match Cards (Schedule) */
.matchday-group{margin-bottom:16px}
.matchday-header{display:flex;align-items:center;gap:8px;padding:8px 0;margin-bottom:8px;border-bottom:1px solid var(--border)}
.matchday-date{font-size:18px;font-weight:800;color:var(--accent)}
.matchday-badge{font-size:10px;padding:2px 8px;border-radius:12px;background:var(--bg-card);color:var(--text-secondary)}
.matchday-count{font-size:11px;color:var(--text-muted);margin-left:auto}
.match-card{background:var(--bg-card);border-radius:var(--radius);padding:10px 14px;margin-bottom:6px;border-left:3px solid var(--border);transition:all .2s}
.match-card:hover{background:var(--bg-card-hover);transform:translateX(2px)}
.match-card.played{border-left-color:var(--text-muted)}
.match-card.played.result-win{border-left-color:var(--green)}
.match-card.played.result-loss{border-left-color:var(--red)}
.match-card.upcoming{border-left-color:var(--blue)}
.match-card.live-now{border-left-color:var(--red);background:linear-gradient(135deg,#1a0a0f,#1a1015);animation:live-glow 2s infinite}
@keyframes live-glow{0%,100%{box-shadow:0 0 8px rgba(255,23,68,.2)}50%{box-shadow:0 0 20px rgba(255,23,68,.5)}}
.live-score{color:var(--red);font-size:20px;animation:pulse 1s infinite}
.match-time{font-size:11px;color:var(--text-muted);margin-bottom:2px}
.match-teams{font-size:14px;font-weight:600;display:flex;align-items:center;gap:8px}
.match-score{font-size:18px;font-weight:800;color:var(--accent);padding:0 6px;font-family:var(--font-mono)}
.match-vs{font-size:11px;color:var(--text-muted)}
.match-note{font-size:10px;color:var(--text-secondary);margin-top:2px}
.match-prediction{display:flex;gap:10px;align-items:center;margin-top:4px}
.pred-item{font-size:11px;padding:2px 6px;border-radius:var(--radius-sm);font-weight:600}
.pred-item.win{background:var(--green-bg);color:var(--green)}
.pred-item.draw{background:var(--bg-card-hover);color:var(--amber)}
.pred-item.lose{background:var(--red-bg);color:var(--red)}
.pred-score{font-size:12px;font-weight:700;color:var(--accent);margin-left:auto}

/* Tables */
.data-table{width:100%;border-collapse:collapse;font-size:11px;margin:6px 0}
.data-table th{background:var(--bg-secondary);padding:8px 6px;text-align:left;color:var(--text-secondary);font-weight:600;border-bottom:2px solid var(--border);white-space:nowrap;font-size:10px;text-transform:uppercase;letter-spacing:.5px}
.data-table td{padding:6px;border-bottom:1px solid var(--border);white-space:nowrap}
.data-table tr:hover td{background:var(--bg-card-hover)}
.data-table .num-cell{font-family:var(--font-mono);text-align:center}
.data-table .date-cell{color:var(--text-muted);font-size:10px}
.data-table .note-cell{font-size:10px;color:var(--text-secondary);max-width:200px;overflow:hidden;text-overflow:ellipsis}

/* Group Tables Grid */
.group-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}
.group-table{background:var(--bg-card);border-radius:var(--radius);overflow:hidden;border:1px solid var(--border)}
.group-title{font-size:13px;font-weight:700;padding:8px 12px;background:var(--bg-secondary);color:var(--accent);border-bottom:1px solid var(--border)}
.group-table table{font-size:10px}
.group-table th{font-size:9px}

/* Intel Sub-tabs */
.sub-tabs{display:flex;gap:4px;margin-bottom:12px}
.sub-tab{padding:6px 14px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);color:var(--text-secondary);cursor:pointer;font-size:11px;transition:all .2s}
.sub-tab:hover{color:var(--text-primary)}
.sub-tab.active{background:var(--blue-bg);border-color:var(--blue);color:var(--blue)}

/* Betting Panel */
.betting-plan{background:var(--bg-card);border-radius:var(--radius);padding:16px;border:1px solid var(--border);font-family:var(--font-mono);font-size:11px;line-height:1.6;white-space:pre-wrap;color:var(--text-primary);overflow-x:auto}

/* Utility */
.text-green{color:var(--green)}
.text-red{color:var(--red)}
.text-amber{color:var(--amber)}
.card{border-radius:var(--radius);border:1px solid var(--border);overflow:hidden;margin-bottom:12px}
.card-header{padding:10px 14px;background:var(--bg-secondary);border-bottom:1px solid var(--border);font-size:13px;font-weight:700}
.card-header h3{font-size:13px;color:var(--accent)}
.card-body{padding:10px 14px;background:var(--bg-card)}

/* Scrollbar */
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:var(--bg-primary)}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}

/* Footer */
.footer{text-align:center;padding:20px;color:var(--text-muted);font-size:10px}
.footer button{padding:8px 20px;background:linear-gradient(135deg,var(--accent-dim),var(--accent));border:none;color:#000;border-radius:var(--radius);cursor:pointer;font-size:12px;font-weight:700;transition:all .2s}
.footer button:hover{transform:scale(1.05);box-shadow:0 4px 16px rgba(255,215,0,.3)}

/* Highlights Panel */
.highlights-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.hl-card{background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);padding:14px;transition:all .2s}
.hl-card:hover{border-color:var(--accent-dim)}
.hl-card.full-width{grid-column:1/-1}
.hl-card-title{font-size:13px;font-weight:700;color:var(--accent);margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid var(--border)}
/* Upset cards */
.upset-card{background:linear-gradient(135deg,#1a1015,#1a1510);border-radius:var(--radius-sm);padding:8px 10px;margin-bottom:6px;border-left:3px solid var(--red)}
.upset-level{font-size:14px;margin-bottom:2px}
.upset-match{font-size:12px;font-weight:600;color:var(--text-primary)}
.upset-detail{font-size:10px;color:var(--text-secondary);margin-top:2px}
/* Bracket */
.bracket-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:8px}
.bracket-pair{background:var(--bg-secondary);border-radius:var(--radius-sm);padding:8px 12px;border:1px solid var(--border)}
.bracket-label{font-size:10px;color:var(--text-muted);margin-bottom:3px}
.bracket-teams{font-size:12px;font-weight:600}
/* Live highlight card */
.live-hl-card{border-color:var(--red);background:linear-gradient(135deg,#1a060a,#1a0a10);animation:live-glow 2s infinite}
.live-hl-match{background:rgba(255,23,68,.08);border-radius:var(--radius-sm);padding:10px 12px;margin-bottom:6px;border-left:3px solid var(--red)}
.live-hl-header{font-size:10px;color:var(--text-muted);margin-bottom:4px}
.live-hl-teams{font-size:14px;font-weight:700;margin:4px 0}
.live-hl-note{font-size:10px;color:var(--text-secondary)}
/* Trend badges */
.trend-badge{display:inline-block;padding:3px 8px;border-radius:12px;font-size:10px;font-weight:600}
.trend-badge.hot{background:var(--green-bg);color:var(--green);border:1px solid rgba(0,200,83,.3)}
.trend-badge.cold{background:var(--red-bg);color:var(--red);border:1px solid rgba(255,23,68,.3)}
/* Gold in boot table */
.gold{color:var(--accent);font-weight:700}

/* === Betting Panel Redesign === */
.bet-date-tabs{display:flex;gap:4px;margin-bottom:16px;flex-wrap:wrap}
.bet-date-tab{padding:8px 16px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);color:var(--text-secondary);cursor:pointer;font-size:12px;font-weight:600;transition:all .2s}
.bet-date-tab:hover{color:var(--text-primary);border-color:var(--accent-dim)}
.bet-date-tab.active{background:var(--accent);color:#000;border-color:var(--accent);font-weight:700}
.bet-date-panel{display:none}
.bet-matches-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px;margin-bottom:16px}
/* Bet Card */
.bet-card{background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);padding:12px;transition:all .2s}
.bet-card:hover{border-color:var(--accent-dim);transform:translateY(-1px)}
.bet-card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.bet-time{font-size:10px;color:var(--text-muted)}
.bet-confidence{font-size:9px;padding:2px 8px;border-radius:10px;font-weight:600}
.conf-high{background:var(--green-bg);color:var(--green)}
.conf-mid{background:var(--bg-card-hover);color:var(--amber)}
.conf-low{background:var(--red-bg);color:var(--red)}
.bet-teams{font-size:14px;font-weight:700;text-align:center;margin:8px 0;display:flex;align-items:center;justify-content:center;gap:8px}
.bet-vs{font-size:10px;color:var(--text-muted);font-weight:400}
/* Probability Bars */
.bet-probs{display:flex;gap:3px;height:24px;margin:8px 0;border-radius:4px;overflow:hidden}
.prob-bar{display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;color:#fff;min-width:40px;transition:flex .3s}
.prob-bar.win{background:linear-gradient(135deg,#1b5e20,#2e7d32)}
.prob-bar.draw{background:linear-gradient(135deg,#4a3800,#6d5200)}
.prob-bar.lose{background:linear-gradient(135deg,#4a1428,#6d1a35)}
/* Pick Row */
.bet-pick-row{display:flex;align-items:center;gap:8px;margin-top:8px;flex-wrap:wrap}
.bet-pick-label{padding:4px 10px;border-radius:12px;font-size:10px;font-weight:700}
.pick-win{background:var(--green-bg);color:var(--green);border:1px solid rgba(0,200,83,.3)}
.pick-draw{background:var(--bg-card-hover);color:var(--amber);border:1px solid rgba(255,145,0,.3)}
.pick-lose{background:var(--red-bg);color:var(--red);border:1px solid rgba(255,23,68,.3)}
.bet-score{font-size:10px;color:var(--text-secondary);margin-left:auto}
.bet-cold{font-size:9px;color:var(--text-muted)}
.bet-plan-section{background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);overflow:hidden;margin-top:8px}
.bet-plan-header{padding:10px 14px;background:var(--bg-secondary);font-size:13px;font-weight:700;color:var(--accent);border-bottom:1px solid var(--border)}

@media(max-width:768px){
  .group-grid{grid-template-columns:1fr}
  .stats-bar{grid-template-columns:repeat(3,1fr)}
  .tab-btn{font-size:10px;padding:8px 6px}
  .header h1{font-size:16px}
}
</style>"""

# ============================================================
# HTML Assembly
# ============================================================
injury_count = sum(len(v) for v in injuries.values())
gossip_warn_count = sum(1 for _,_,_,_,_,g in rankings if g<90)
today_str = str(date.today())

html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>2026世界杯 Dashboard v5.1</title>{CSS}</head><body>

<div class="header">
  <h1><span class="icon">🏆</span> 2026 World Cup</h1>
  <div class="subtitle"><span class="live-dot"></span> v5.1 实时 · {today_str} · {results['total_played']}场已赛 · 方向正确率{results['direction_rate']}%</div>
</div>

<div class="stats-bar">
  <div class="stat-card"><div class="num">48</div><div class="label">参赛球队</div></div>
  <div class="stat-card"><div class="num green">{results['total_played']}/48</div><div class="label">已完赛</div></div>
  <div class="stat-card"><div class="num green">{results['direction_rate']}%</div><div class="label">方向正确率</div></div>
  <div class="stat-card"><div class="num amber">{gossip_warn_count}</div><div class="label">八卦预警</div></div>
  <div class="stat-card"><div class="num red">{injury_count}</div><div class="label">伤病追踪</div></div>
  <div class="stat-card"><div class="num">{len(news.get('items',[]))}</div><div class="label">新闻条目</div></div>
</div>

<div class="tab-nav">
  <button class="tab-btn active" onclick="showPanel('highlights')"><span class="icon">🔥</span> 亮点</button>
  <button class="tab-btn" onclick="showPanel('schedule')"><span class="icon">🏟️</span> 赛程</button>
  <button class="tab-btn" onclick="showPanel('results')"><span class="icon">📊</span> 赛果</button>
  <button class="tab-btn" onclick="showPanel('standings')"><span class="icon">📋</span> 积分</button>
  <button class="tab-btn" onclick="showPanel('intel')"><span class="icon">📰</span> 情报</button>
  <button class="tab-btn" onclick="showPanel('betting')"><span class="icon">💰</span> 方案</button>
</div>

<!-- PANEL 0: 亮点 -->
<div id="highlights" class="panel active">
  <h2 style="font-size:16px;color:var(--accent);margin-bottom:12px">🔥 赛事亮点</h2>
  <div class="highlights-grid">
    <!-- Live Now -->
    {live_now_html}
    <!-- Golden Boot -->
    <div class="hl-card">
      <div class="hl-card-title">👟 金靴争夺</div>
      <table class="data-table"><thead><tr><th></th><th>球员</th><th>进球</th><th>球队</th></tr></thead><tbody>{boot_rows}</tbody></table>
    </div>
    <!-- Assist Leaders -->
    <div class="hl-card">
      <div class="hl-card-title">🅰️ 助攻王</div>
      <table class="data-table"><thead><tr><th></th><th>球员</th><th>助攻</th><th>球队</th></tr></thead><tbody>{assist_rows}</tbody></table>
    </div>
    <!-- Upset Wall -->
    <div class="hl-card">
      <div class="hl-card-title">💥 冷门墙</div>
      {upset_rows}
    </div>
    <!-- Form Trends -->
    <div class="hl-card">
      <div class="hl-card-title">📈 状态趋势</div>
      <div style="margin:4px 0"><span style="color:var(--green);font-size:10px">🔥 火爆</span></div>
      <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px">{hot_rows}</div>
      <div style="margin:4px 0"><span style="color:var(--red);font-size:10px">❄️ 低迷</span></div>
      <div style="display:flex;flex-wrap:wrap;gap:4px">{cold_rows}</div>
    </div>
    <!-- Bracket Preview -->
    <div class="hl-card full-width">
      <div class="hl-card-title">🏆 即时淘汰赛对阵（如果现在结束）</div>
      <div class="bracket-grid">{bracket_rows}</div>
      <p style="font-size:9px;color:var(--text-muted);margin-top:6px">每组前2名晋级 · 实时随积分变化</p>
    </div>
    <!-- Model Accuracy Card -->
    <div class="hl-card">
      <div class="hl-card-title">🎯 模型表现</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;text-align:center">
        <div><div class="num" style="font-size:28px;color:var(--green)">{results['direction_rate']}%</div><div class="label">方向正确率</div></div>
        <div><div class="num" style="font-size:28px;color:var(--amber)">{sum(1 for m in results['matches'] if m['score'].split('-')[0]==m['score'].split('-')[1] and m['prediction_correct']=='✅')}/{sum(1 for m in results['matches'] if m['score'].split('-')[0]==m['score'].split('-')[1])}</div><div class="label">平局侦测</div></div>
        <div><div class="num" style="font-size:20px;color:var(--blue)">{results['total_played']}</div><div class="label">已赛</div></div>
        <div><div class="num" style="font-size:20px;color:var(--text-secondary)">{results['direction_correct']}/{results['direction_total']}</div><div class="label">正确/总</div></div>
      </div>
    </div>
  </div>
</div>

<!-- PANEL 1: 赛程总览 -->
<div id="schedule" class="panel">
  <div style="margin-bottom:12px">
    <h2 style="font-size:16px;color:var(--accent);margin-bottom:4px">🏟️ 赛程总览</h2>
    <p style="font-size:10px;color:var(--text-secondary)">已完赛显示比分+预测对错 · 待赛显示AI预测 · 实时更新</p>
  </div>
  {schedule_rows}
</div>

<!-- PANEL 2: 赛果回测 -->
<div id="results" class="panel">
  <div style="margin-bottom:12px">
    <h2 style="font-size:16px;color:var(--accent);margin-bottom:4px">📊 赛果回测</h2>
    <p style="font-size:10px;color:var(--text-secondary)">{results['total_played']}场已赛 · {results['direction_correct']}场判对 · {results['direction_rate']}%正确率</p>
  </div>
  <!-- 比分预测回测 -->
  <div class="hl-card" style="margin-bottom:16px">
    <div class="hl-card-title">🎯 比分预测回测 ({backtest_n}场)</div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;text-align:center;margin-bottom:12px">
      <div><div class="num" style="font-size:24px;color:var(--green)">{top1_rate_str}</div><div class="label">比分Top1命中</div></div>
      <div><div class="num" style="font-size:24px;color:var(--amber)">{top3_rate_str}</div><div class="label">比分Top3命中</div></div>
      <div><div class="num" style="font-size:20px;color:var(--blue)">{avg_goal_error}</div><div class="label">场均进球误差</div></div>
      <div><div class="num" style="font-size:20px;color:var(--text-secondary)">{score_top1_hits}/{backtest_n}</div><div class="label">精确命中/总</div></div>
    </div>
    <table class="data-table"><thead><tr><th>比赛</th><th>实际</th><th>预测Top1</th><th>命中</th><th>Top3</th></tr></thead><tbody>{score_backtest_rows}</tbody></table>
  </div>
  {result_rows}
</div>

<!-- PANEL 3: 积分排名 -->
<div id="standings" class="panel">
  <div style="margin-bottom:12px">
    <h2 style="font-size:16px;color:var(--accent);margin-bottom:4px">📋 积分榜 & 实力排名</h2>
    <p style="font-size:10px;color:var(--text-secondary)">12组小组赛 · 每组前2+8个最佳第3晋级32强</p>
  </div>
  <h3 style="font-size:14px;color:var(--accent);margin:8px 0">小组积分榜</h3>
  <div class="group-grid">{s_rows}</div>
  <h3 style="font-size:14px;color:var(--accent);margin:16px 0 8px">48队实力排名 · 模型 vs ESPN vs Fox vs Yahoo</h3>
  <p style="font-size:10px;color:var(--text-secondary);margin-bottom:8px">⚠️=偏差>8位 △=偏差>4位 🔴🟡=八卦预警</p>
  <div style="overflow-x:auto"><table class="data-table"><thead><tr><th>#</th><th>球队</th><th>总分</th><th>硬</th><th>外</th><th>八</th><th>ESPN</th><th>Fox</th><th>Yh</th><th>共识</th></tr></thead><tbody>{r_rows}</tbody></table></div>
</div>

<!-- PANEL 4: 情报中心 -->
<div id="intel" class="panel">
  <div style="margin-bottom:12px">
    <h2 style="font-size:16px;color:var(--accent);margin-bottom:4px">📰 情报中心</h2>
    <p style="font-size:10px;color:var(--text-secondary)">多源聚合 · 实时更新 · 53条新闻 · 28条伤病 · 18队八卦</p>
  </div>
  <div class="sub-tabs">
    <button class="sub-tab active" onclick="showSub('news-pane',this)">📰 新闻 ({len(news.get('items',[]))})</button>
    <button class="sub-tab" onclick="showSub('injuries-pane',this)">🏥 伤病 ({injury_count})</button>
    <button class="sub-tab" onclick="showSub('gossip-pane',this)">🚨 八卦 ({len(gossip)})</button>
  </div>
  <div id="news-pane" class="sub-panel"><div class="card"><div class="card-body" style="max-height:70vh;overflow-y:auto"><table class="data-table"><thead><tr><th></th><th>时间</th><th>标题</th><th>详情</th></tr></thead><tbody>{news_rows}</tbody></table></div></div></div>
  <div id="injuries-pane" class="sub-panel" style="display:none"><div class="card"><div class="card-body" style="max-height:70vh;overflow-y:auto"><table class="data-table"><thead><tr><th></th><th>时间</th><th>球队</th><th>球员</th><th>角色</th><th>状态</th><th>原因</th></tr></thead><tbody>{i_rows}</tbody></table></div></div></div>
  <div id="gossip-pane" class="sub-panel" style="display:none"><div class="card"><div class="card-body" style="max-height:70vh;overflow-y:auto"><table class="data-table"><thead><tr><th></th><th>时间</th><th>球队</th><th>扣分</th><th>事件</th><th>政治</th></tr></thead><tbody>{g_rows}</tbody></table></div></div></div>
</div>

<!-- PANEL 5: 购彩方案 按日期Tab -->
<div id="betting" class="panel">
  <div style="margin-bottom:12px">
    <h2 style="font-size:16px;color:var(--accent);margin-bottom:4px">💰 竞彩购彩方案</h2>
    <p style="font-size:10px;color:var(--text-secondary)">按比赛日分Tab · 200元预算 · 概率条可视化 · 方向推荐 · 仅供参考</p>
  </div>
  <div class="bet-date-tabs">{bet_date_tabs}</div>
  {bet_date_panels}
</div>

<div class="footer">
  <button onclick="location.reload()">🔄 刷新数据</button>
  <p style="margin-top:8px">Dashboard v5.0 · 数据源: 17个媒体 · 自动衰减+监听 · 60秒刷新</p>
</div>

<script>
function showPanel(id){{
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  event.target.classList.add('active');
  localStorage.setItem('activeTab', id);
  localStorage.setItem('activeSubTab', '');
}}
function showSub(id,btn){{
  document.querySelectorAll('.sub-panel').forEach(p=>p.style.display='none');
  document.querySelectorAll('.sub-tab').forEach(b=>b.classList.remove('active'));
  document.getElementById(id).style.display='block';
  btn.classList.add('active');
  localStorage.setItem('activeSubTab', id);
}}
function showBetDate(id,btn){{
  document.querySelectorAll('.bet-date-panel').forEach(p=>p.style.display='none');
  document.querySelectorAll('.bet-date-tab').forEach(b=>b.classList.remove('active'));
  document.getElementById(id).style.display='block';
  btn.classList.add('active');
  localStorage.setItem('activeBetDate', id);
}}
// 恢复上次Tab
(function(){{
  var savedTab = localStorage.getItem('activeTab');
  if (savedTab && document.getElementById(savedTab)) {{
    document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
    document.getElementById(savedTab).classList.add('active');
    var btns = document.querySelectorAll('.tab-btn');
    for (var i=0; i<btns.length; i++) {{
      if (btns[i].getAttribute('onclick') && btns[i].getAttribute('onclick').indexOf(savedTab)>=0) {{
        btns[i].classList.add('active');
      }}
    }}
  }}
  var savedSub = localStorage.getItem('activeSubTab');
  if (savedSub && document.getElementById(savedSub)) {{
    document.querySelectorAll('.sub-panel').forEach(p=>p.style.display='none');
    document.querySelectorAll('.sub-tab').forEach(b=>b.classList.remove('active'));
    document.getElementById(savedSub).style.display='block';
  }}
  // 恢复方案分日Tab
  var savedBetDate = localStorage.getItem('activeBetDate');
  if (savedBetDate && document.getElementById(savedBetDate)) {{
    document.querySelectorAll('.bet-date-panel').forEach(p=>p.style.display='none');
    document.querySelectorAll('.bet-date-tab').forEach(b=>b.classList.remove('active'));
    document.getElementById(savedBetDate).style.display='block';
  }}
}})();
// 智能刷新
var hasLive = document.querySelectorAll('.live-now').length > 0;
var interval = hasLive ? 30000 : 60000;
setTimeout(function(){{location.reload()}}, interval);
</script></body></html>"""

out = Path(__file__).parent / "dashboard.html"
out.write_text(html)
print(f"Dashboard v5.1: {out}")

WATCH_MODE = "--watch" in sys.argv
SERVE_MODE = "--serve" in sys.argv

if WATCH_MODE:
    data_dir = DATA
    mtimes = {f.name: f.stat().st_mtime for f in data_dir.glob("*.json")}
    last_live_check = 0
    print(f"👀 文件监听 + 实时比分: {data_dir}/")

    def auto_check_live():
        """自动检测进行中比赛 + 更新分钟数 + 自动推送GitHub"""
        now = datetime.now()
        results_data = json.load(open(DATA/"results.json"))
        played = {f"{m['home']}-{m['away']}" for m in results_data["matches"]}
        live_data = json.load(open(DATA/"live_scores.json")) if (DATA/"live_scores.json").exists() else {"matches_in_progress":[]}

        changed = False
        # 1. 检测新开球的比赛
        for match_id, time_str in MATCH_SCHEDULE.items():
            if match_id in played: continue
            parts = time_str.split()
            try:
                m, d = parts[0].split("/")
                h, mi = parts[1].split(":")
                kickoff = datetime(2026, int(m), int(d), int(h), int(mi))
                if kickoff <= now <= kickoff.replace(hour=kickoff.hour+3, minute=kickoff.minute+30):
                    if any(lm["match_id"] == match_id for lm in live_data["matches_in_progress"]):
                        continue
                    # Try public API
                    try:
                        import urllib.request
                        url = f"https://www.fotmob.com/api/matchDetails?matchId={match_id}"
                        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            data = json.loads(resp.read())
                            status = data.get("header",{}).get("status",{})
                            if status.get("live") or status.get("started"):
                                score = {"hg": status.get("homeScore",0), "ag": status.get("awayScore",0), "min": status.get("minutes","?")}
                                live_data["matches_in_progress"].append({
                                    "match_id": match_id, "home_goals": score["hg"], "away_goals": score["ag"],
                                    "minute": str(score["min"]), "source": "fotmob", "updated": now.strftime("%H:%M")
                                })
                                changed = True
                                print(f"  ⚽ LIVE {match_id} {score['hg']}-{score['ag']} ({score['min']}')")
                    except: pass

                    if not any(lm["match_id"] == match_id for lm in live_data["matches_in_progress"]):
                        minutes = int((now - kickoff).total_seconds() / 60)
                        live_data["matches_in_progress"].append({
                            "match_id": match_id, "home_goals": 0, "away_goals": 0,
                            "minute": str(minutes), "source": "auto", "updated": now.strftime("%H:%M")
                        })
                        changed = True
                        print(f"  🔴 {match_id} 0-0 ({minutes}') — 等待数据")
            except: pass

        # 2. 更新现有条目的分钟数
        for lm in live_data.get("matches_in_progress", []):
            ts = MATCH_SCHEDULE.get(lm["match_id"], "")
            if not ts: continue
            try:
                parts = ts.split(); m,d = parts[0].split("/"); h,mi = parts[1].split(":")
                kickoff = datetime(2026,int(m),int(d),int(h),int(mi))
                minutes = int((now - kickoff).total_seconds() / 60)
                if 0 <= minutes <= 120 and str(minutes) != str(lm.get("minute","")):
                    lm["minute"] = str(minutes); lm["updated"] = now.strftime("%H:%M")
                    changed = True
            except: pass

        # 3. 清理已超时的条目
        live_data["matches_in_progress"] = [lm for lm in live_data.get("matches_in_progress", [])
            if not _is_match_expired(lm["match_id"])]

        if changed:
            live_data["updated"] = now.strftime("%Y-%m-%dT%H:%M:%S")
            json.dump(live_data, open(DATA/"live_scores.json","w"), indent=2, ensure_ascii=False)
            # 自动推送到 GitHub
            import subprocess
            try:
                subprocess.run(["git","add","data/live_scores.json"], cwd=str(Path(__file__).parent),
                              capture_output=True, timeout=10)
                r = subprocess.run(["git","commit","-m",f"Live: auto-refresh ({now.strftime('%H:%M')})"],
                                  cwd=str(Path(__file__).parent), capture_output=True, timeout=10)
                if b"nothing to commit" not in r.stdout:
                    subprocess.run(["git","push"], cwd=str(Path(__file__).parent),
                                  capture_output=True, timeout=30)
                    print(f"  📤 已推送 GitHub")
            except: pass

    def _is_match_expired(match_id):
        """比赛结束超过30分钟 → 清理live条目(但不自动写results.json)"""
        ts = MATCH_SCHEDULE.get(match_id, "")
        try:
            parts = ts.split(); m,d = parts[0].split("/"); h,mi = parts[1].split(":")
            kickoff = datetime(2026,int(m),int(d),int(h),int(mi))
            # 开球后4.5小时(270分钟) → 肯定结束了, 从live中清除
            return datetime.now() > kickoff.replace(hour=kickoff.hour+4, minute=kickoff.minute+30)
        except: return True

    if SERVE_MODE:
        import threading, http.server, socketserver, webbrowser
        os.chdir(Path(__file__).parent)
        socketserver.TCPServer.allow_reuse_address = True
        server = socketserver.TCPServer(("", 8900), http.server.SimpleHTTPRequestHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True); t.start()
        print(f"\n📍 本地: http://localhost:8900/dashboard.html")
        webbrowser.open(f"http://localhost:8900/dashboard.html")
    if "--public" in sys.argv:
        import subprocess
        print("🌐 启动公网隧道 (ngrok)...")
        env = {**os.environ, "http_proxy":"", "https_proxy":"", "HTTP_PROXY":"", "HTTPS_PROXY":""}
        subprocess.Popen(["/tmp/ngrok","http","8900","--log=stdout"], env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(4)
        try:
            import urllib.request
            resp = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=3)
            data = json.loads(resp.read())
            for t in data.get("tunnels",[]):
                print(f"🌐 公网: {t['public_url']}/dashboard.html")
        except:
            print("   公网地址: 查看 http://127.0.0.1:4040 或运行 /tmp/ngrok http 8900")
    try:
        while True:
            time.sleep(2)
            # 文件变更检测
            for f in data_dir.glob("*.json"):
                prev = mtimes.get(f.name,0); cur = f.stat().st_mtime
                if cur > prev:
                    mtimes[f.name] = cur
                    print(f"  🔄 {f.name} 已修改 → 重新生成...")
                    os.system(f"python3 {__file__}")
                    for f2 in data_dir.glob("*.json"): mtimes[f2.name] = f2.stat().st_mtime
                    break
            # 每60秒检查一次实时比分
            if time.time() - last_live_check > 60:
                last_live_check = time.time()
                auto_check_live()
    except KeyboardInterrupt:
        print("\n👋 监听已停止")
elif SERVE_MODE:
    import http.server, socketserver, webbrowser
    os.chdir(Path(__file__).parent)
    socketserver.TCPServer.allow_reuse_address = True
    if "--public" in sys.argv:
        import subprocess
        print("🌐 启动公网隧道 (ngrok)...")
        env = {**os.environ, "http_proxy":"", "https_proxy":"", "HTTP_PROXY":"", "HTTPS_PROXY":""}
        subprocess.Popen(["/tmp/ngrok","http","8900","--log=stdout"], env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(4)
        try:
            import urllib.request
            resp = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=3)
            data = json.loads(resp.read())
            for t in data.get("tunnels",[]):
                print(f"🌐 公网: {t['public_url']}/dashboard.html")
        except:
            print("   查看 http://127.0.0.1:4040 获取公网地址")
    with socketserver.TCPServer(("", 8900), http.server.SimpleHTTPRequestHandler) as httpd:
        print(f"\n📍 本地: http://localhost:8900/dashboard.html")
        if "--public" in sys.argv:
            print(f"🌐 公网: 见上方 ngrok 输出地址")
        webbrowser.open(f"http://localhost:8900/dashboard.html")
        httpd.serve_forever()
