#!/usr/bin/env python3
"""世界杯预测系统 Dashboard v4.0 — 赛果+预测+新闻"""
import json, sys, os
from pathlib import Path
from datetime import date, datetime

DATA = Path(__file__).parent / "data"

def load(n): return json.load(open(DATA / n))
teams = load("teams.json")
groups = load("groups.json")
injuries = load("injuries.json")
gossip = load("gossip.json")

sys.path.insert(0, str(Path(__file__).parent))
from engine.predictor import final_score, predict
from engine.lottery import generate_plan, format_lottery, MATCH_SCHEDULE

# 国旗
FLAG_DB = {"France":"🇫🇷","Spain":"🇪🇸","Argentina":"🇦🇷","England":"🏴󠁧󠁢󠁥󠁮󠁧󠁿","Brazil":"🇧🇷","Portugal":"🇵🇹","Germany":"🇩🇪","Netherlands":"🇳🇱","Belgium":"🇧🇪","Norway":"🇳🇴","Morocco":"🇲🇦","Colombia":"🇨🇴","Mexico":"🇲🇽","South Korea":"🇰🇷","United States":"🇺🇸","Uruguay":"🇺🇾","Croatia":"🇭🇷","Japan":"🇯🇵","Senegal":"🇸🇳","Switzerland":"🇨🇭","Austria":"🇦🇹","Sweden":"🇸🇪","Canada":"🇨🇦","Australia":"🇦🇺","Ecuador":"🇪🇨","Türkiye":"🇹🇷","Scotland":"🏴󠁧󠁢󠁳󠁣󠁴󠁿","Czechia":"🇨🇿","Egypt":"🇪🇬","Iran":"🇮🇷","Ghana":"🇬🇭","Algeria":"🇩🇿","Tunisia":"🇹🇳","South Africa":"🇿🇦","Cape Verde":"🇨🇻","Saudi Arabia":"🇸🇦","Qatar":"🇶🇦","Iraq":"🇮🇶","Jordan":"🇯🇴","Uzbekistan":"🇺🇿","New Zealand":"🇳🇿","Panama":"🇵🇦","Haiti":"🇭🇹","Curaçao":"🇨🇼","DR Congo":"🇨🇩","Congo DR":"🇨🇩","Bosnia-Herzegovina":"🇧🇦","Bosnia":"🇧🇦","Paraguay":"🇵🇾","Côte d'Ivoire":"🇨🇮","Ivory Coast":"🇨🇮"}
def f(name): return f"{FLAG_DB.get(name,'🏳️')} {name}"

# === 模型排名 ===
rankings = []
for tid in teams:
    fs = final_score(tid)
    rankings.append((tid, fs["name"], fs["total"], fs["hard_data"]["score"], fs["betting"]["score"], fs["gossip"]["score"]))
rankings.sort(key=lambda x: x[2], reverse=True)

# === 外部排名 ===
ESPN = {"ESP":1,"FRA":2,"ARG":3,"ENG":4,"BRA":5,"POR":6,"GER":7,"NED":8,"MAR":9,"NOR":10,"BEL":11,"COL":12,"SEN":13,"CRO":14,"JPN":15}
FOX  = {"FRA":1,"ESP":2,"ENG":3,"COL":4,"ARG":5,"POR":6,"BRA":7,"NED":8,"GER":9,"CRO":10,"BEL":11,"USA":12,"MAR":13,"MEX":14,"URU":15,"NOR":16}
YHOO = {"FRA":1,"ESP":2,"ARG":3,"ENG":4,"POR":5,"BRA":6,"GER":7,"NED":8,"BEL":9,"COL":10,"MAR":11,"SEN":12,"ECU":13,"URU":14,"CRO":15}
consensus = {}
for tid in set(list(ESPN)+list(FOX)+list(YHOO)):
    r = []
    if tid in ESPN: r.append(ESPN[tid])
    if tid in FOX: r.append(FOX[tid])
    if tid in YHOO: r.append(YHOO[tid])
    consensus[tid] = round(sum(r)/len(r),1) if r else 0

# === 已完成比赛结果 ===
MATCH_RESULTS = [
    ("6/11","MEX","RSA","2-0","✅","Mexico 2-0, Quinones+Jimenez, 3红牌创纪录"),
    ("6/11","KOR","CZE","2-1","✅","Korea 2-1逆转, Hwang 1球1助"),
    ("6/12","CAN","BIH","1-1","✅","Davies伤缺, 1-1平"),
    ("6/12","USA","PAR","4-1","✅","Balogun双响, USA碾压"),
    ("6/13","HAI","SCO","0-1","✅","McGinn制胜, Scotland 1998年后首胜"),
    ("6/13","AUS","TUR","2-0","✅","Irankunda致敬Cahill, Beach 8扑救"),
    ("6/13","BRA","MAR","1-1","✅","Neymar缺阵, 巴西不胜"),
    ("6/13","QAT","SUI","1-1","❌","QAT 94分钟绝平, VAR争议"),
    ("6/14","GER","CUW","7-1","✅","德国屠杀, Curaçao先拔头筹后崩溃"),
    ("6/14","NED","JPN","2-2","✅","Japan 88分钟绝平"),
    ("6/14","CIV","ECU","1-0","❌","Amad绝杀, 模型判Ecuador胜"),
    ("6/14","SWE","TUN","5-1","✅","Ayari双响, Tunisia主帅将被解雇"),
    ("6/15","ESP","CPV","0-0","❌","40岁Vozinha神扑, 本届最大冷门"),
    ("6/15","BEL","EGY","1-1","✅","埃及逼平比利时"),
    ("6/15","KSA","URU","1-1","❌","Araujo 80分钟救主"),
    ("6/15","IRN","NZL","2-2","✅","Just双响, Iran两度扳平, 政治干扰"),
    ("6/16","FRA","SEN","3-1","❌","Mbappe双响+世界波, 模型判DRAW"),
    ("6/16","IRQ","NOR","4-1","✅","Haaland首轮双响, Norway榜首"),
    ("6/16","ARG","ALG","2-0","✅","Messi第5届世界杯进球, 200场里程碑"),
]

# === 今日比赛预测 ===
TODAY_MATCHES = ["POR-COD","ENG-CRO","GHA-PAN","COL-UZB"]  # 6/17
TOMORROW = ["CZE-RSA","SUI-BIH","CAN-QAT","MEX-KOR"]  # 6/18
today_preds = []
for m in TODAY_MATCHES:
    p = predict(m)
    if "error" not in p:
        r = p["prediction"]
        today_preds.append({
            "match": p["match"], "w": r["win_pct"], "d": r["draw_pct"], "l": r["lose_pct"],
            "top_score": r["top_scores"][0]["score"], "xg": f"{r['xg_home']}-{r['xg_away']}",
            "delta": f"{p['delta']:+.1f}", "cold": r["cold_alert"][:6],
            "conf": r["confidence"]
        })

# === 重要新闻 ===
NEWS = [
    ("🔴","Ruben Dias缺阵","葡萄牙防线核心热身赛被撞击, Martinez确认缺战首轮(Ge.Globo 6/16)"),
    ("🔴","Thomas Partey被拒入加拿大","Ghana中场核心被加拿大拒绝入境, 缺席首战vs Panama(Yahoo独家)"),
    ("🟡","France 3-1 Senegal","Mbappe双响+20米世界波, 法国开局慢热但下半场爆发(BBC)"),
    ("🟡","Norway 4-1 Iraq","Haaland首轮双响, Norway净胜球压法国排I组榜首(ABC)"),
    ("🟡","Messi 200场里程碑","第5届世界杯进球, Argentina 2-0 Algeria(ESPN)"),
    ("🟡","VAR争议持续","Gary Neville称FIFA'独裁', SAOT动画故障未播出(Metro)"),
    ("🟢","USA 4-1 Paraguay","场倾斜率80.5%为1998年以来第4高, Balogun金靴领跑(ESPN)"),
    ("🟢","网易彩票=SP来源","sports.163.com/caipiao确认为竞彩SP稳定源, 含让球盘+多日预告"),
]

# === 排名表 ===
def rankings_html():
    rows = ""
    for i, (tid, name, total, hard, bet, goss) in enumerate(rankings, 1):
        es = ESPN.get(tid, "-"); fx = FOX.get(tid, "-"); yh = YHOO.get(tid, "-"); cn = consensus.get(tid, "-")
        warn = "🔴" if goss<85 else ("🟡" if goss<95 else "")
        dev = ""
        if isinstance(cn,(int,float)) and isinstance(i,int) and abs(i-cn)>8: dev=f" ⚠️差{abs(i-cn):.0f}"
        elif isinstance(cn,(int,float)) and abs(i-cn)>4: dev=f" △{abs(i-cn):.0f}"
        rows += f"<tr><td>{i}</td><td><b>{name}</b>{warn}{dev}</td><td>{total:.1f}</td><td>{hard:.1f}</td><td>{bet:.1f}</td><td>{goss:.1f}</td><td>{es}</td><td>{fx}</td><td>{yh}</td><td>{cn}</td></tr>"
    return rows

def standings_html():
    rows = ""
    for gid in sorted(groups.keys()):
        g = groups[gid]
        st = sorted(g["standings"].items(), key=lambda x: (-x[1]["p"], -x[1]["gd"], -x[1]["gf"]))
        for i, (tid, s) in enumerate(st):
            name = teams.get(tid,{}).get("name",tid)
            pos = "🥇" if i==0 else ("🥈" if i==1 else ("📌" if i==2 else "  "))
            p = s['p']; played = s['w']+s['d']+s['l']
            rows += f"<tr><td>{pos}</td><td>{gid}</td><td>{f(name)}</td><td>{p}</td><td>{played}场</td><td>{s['w']}-{s['d']}-{s['l']}</td><td>{s['gf']}:{s['ga']}</td><td>{s['gd']:+d}</td></tr>"
    return rows

def results_html():
    rows = ""
    for d, h, a, sc, ok, note in reversed(MATCH_RESULTS):
        hn = teams.get(h,{}).get("name",h)
        an = teams.get(a,{}).get("name",a)
        cls = "color:#4f4" if ok=="✅" else "color:#f44"
        rows += f"<tr><td>{d}</td><td>{f(hn)} vs {f(an)}</td><td><b>{sc}</b></td><td style='{cls}'>{ok}</td><td style='font-size:10px'>{note[:60]}</td></tr>"
    return rows

def today_html():
    rows = ""
    for t in today_preds:
        cold_cls = "color:#f44" if "高" in t["cold"] else ("color:#fa0" if "中" in t["cold"] else "")
        conf_cls = "color:#f44" if "低" in t["conf"] else ("color:#fa0" if "中" in t["conf"] else "color:#4f4")
        rows += f"<tr><td>{t['match'][:30]}</td><td>{t['w']:.0f}/{t['d']:.0f}/{t['l']:.0f}</td><td>{t['top_score']}</td><td>{t['xg']}</td><td>{t['delta']}</td><td style='{cold_cls}'>{t['cold']}</td><td style='{conf_cls}'>{t['conf']}</td></tr>"
    return rows

def injuries_html():
    rows = ""
    for tid, inj_list in sorted(injuries.items()):
        name = teams.get(tid,{}).get("name",tid)
        for inj in inj_list:
            badge = "🔴" if inj["status"] in ("out","out_retired") else "🟡"
            rows += f"<tr><td>{badge}</td><td>{name}</td><td>{inj['player']}</td><td>{inj.get('role','')}</td><td>{inj['status']}</td><td style='font-size:10px'>{inj.get('reason','')[:50]}</td></tr>"
    return rows

def gossip_html():
    rows = ""
    for tid, g in sorted(gossip.items()):
        name = teams.get(tid,{}).get("name",tid)
        lr = g.get("locker_room",{}); pol = g.get("political",{}); off = g.get("player_off_field",{})
        total = abs(lr.get("score",0)) + abs(pol.get("score",0)) + abs(off.get("score",0))
        if total > 0:
            badge = "🔴" if total>=7 else ("🟡" if total>=3 else "🟢")
            rows += f"<tr><td>{badge}</td><td>{name}</td><td>{total}</td><td style='font-size:10px'>{lr.get('reason','')[:55]}</td><td>{'★'*pol.get('level',0)}</td></tr>"
    return rows

def news_html():
    rows = ""
    for badge, title, detail in NEWS:
        rows += f"<tr><td>{badge}</td><td><b>{title}</b></td><td style='font-size:10px'>{detail[:80]}</td></tr>"
    return rows

# 预计算所有HTML片段
RANK_HTML = rankings_html()
STAN_HTML = standings_html()
RES_HTML = results_html()
INJ_HTML = injuries_html()
GOS_HTML = gossip_html()
NEWS_HTML = news_html()
TODAY_HTML = today_html()
TODAY_LOTTERY = format_lottery(generate_plan(TODAY_MATCHES)).replace("<","&lt;")

HTML = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>2026世界杯 Dashboard v4.0</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0f1923;color:#e0e6ed;padding:8px}}
h1{{text-align:center;color:#ffd700;margin:4px 0;font-size:18px}}
.sub{{text-align:center;color:#8899aa;margin-bottom:8px;font-size:10px}}
.tabs{{display:flex;gap:2px;margin-bottom:8px;flex-wrap:wrap}}
.tab{{padding:5px 10px;background:#1a2a3a;border:none;color:#8899aa;cursor:pointer;border-radius:6px 6px 0 0;font-size:11px}}
.tab.active{{background:#2a4a6a;color:#ffd700}}
.panel{{display:none}}
.panel.active{{display:block}}
table{{width:100%;border-collapse:collapse;font-size:10px}}
th{{background:#1a2a3a;padding:5px 3px;text-align:left;color:#aabbcc;position:sticky;top:0;white-space:nowrap}}
td{{padding:3px;border-bottom:1px solid #1a2a3a;white-space:nowrap}}
tr:hover{{background:#1a2a3a}}
.card{{background:#1a2a3a;border-radius:6px;padding:8px;margin-bottom:8px}}
.card h3{{color:#ffd700;margin-bottom:4px;font-size:12px}}
.stats{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}}
.stat{{background:#1a2a3a;border-radius:6px;padding:8px 10px;text-align:center;flex:1;min-width:55px}}
.stat .num{{font-size:18px;font-weight:bold;color:#ffd700}}
.stat .label{{font-size:9px;color:#8899aa}}
.legend{{font-size:9px;color:#8899aa;margin-top:4px}}
@media(max-width:768px){{table{{font-size:9px}}}}
</style></head>
<body>
<h1>🏆 2026世界杯预测系统</h1>
<p class="sub">v4.0 · {date.today()} · 赛果+预测+新闻+排名 · 5分钟自动刷新</p>
<div class="stats">
  <div class="stat"><div class="num">48</div><div class="label">球队</div></div>
  <div class="stat"><div class="num">20/48</div><div class="label">首轮已赛</div></div>
  <div class="stat"><div class="num">73.7%</div><div class="label">方向正确</div></div>
  <div class="stat"><div class="num">{sum(1 for _,_,_,_,_,g in rankings if g<90)}</div><div class="label">八卦预警</div></div>
  <div class="stat"><div class="num">{sum(len(v) for v in injuries.values())}</div><div class="label">伤病</div></div>
  <div class="stat"><div class="num">21</div><div class="label">信息源</div></div>
</div>
<div class="tabs">
  <button class="tab active" onclick="show('results')">📊 赛果</button>
  <button class="tab" onclick="show('today')">🎯 今日预测</button>
  <button class="tab" onclick="show('rankings')">🏅 排名</button>
  <button class="tab" onclick="show('standings')">📋 积分</button>
  <button class="tab" onclick="show('news')">📰 新闻</button>
  <button class="tab" onclick="show('injuries')">🏥 伤病</button>
  <button class="tab" onclick="show('gossip')">🚨 八卦</button>
</div>

<div id="results" class="panel active">
  <div class="card"><h3>已赛结果 & 模型预测对照 (19场)</h3>
  <p class="legend">✅=方向正确 ❌=方向错误 | 75%方向正确率</p>
  <div style="overflow-x:auto"><table><thead><tr><th>日期</th><th>比赛</th><th>比分</th><th>判向</th><th>备注</th></tr></thead>
  <tbody><tr><td>6/16</td><td>🇦🇷 Argentina vs 🇩🇿 Algeria</td><td><b>2-0</b></td><td style='color:#4f4'>✅</td><td style='font-size:10px'>Messi第5届世界杯进球, 200场里程碑</td></tr><tr><td>6/16</td><td>🇮🇶 Iraq vs 🇳🇴 Norway</td><td><b>4-1</b></td><td style='color:#4f4'>✅</td><td style='font-size:10px'>Haaland首轮双响, Norway榜首</td></tr><tr><td>6/16</td><td>🇫🇷 France vs 🇸🇳 Senegal</td><td><b>3-1</b></td><td style='color:#f44'>❌</td><td style='font-size:10px'>Mbappe双响+世界波, 模型判DRAW</td></tr><tr><td>6/15</td><td>🇮🇷 Iran vs 🇳🇿 New Zealand</td><td><b>2-2</b></td><td style='color:#4f4'>✅</td><td style='font-size:10px'>Just双响, Iran两度扳平, 政治干扰</td></tr><tr><td>6/15</td><td>🇸🇦 Saudi Arabia vs 🇺🇾 Uruguay</td><td><b>1-1</b></td><td style='color:#f44'>❌</td><td style='font-size:10px'>Araujo 80分钟救主</td></tr><tr><td>6/15</td><td>🇧🇪 Belgium vs 🇪🇬 Egypt</td><td><b>1-1</b></td><td style='color:#4f4'>✅</td><td style='font-size:10px'>埃及逼平比利时</td></tr><tr><td>6/15</td><td>🇪🇸 Spain vs 🇨🇻 Cape Verde</td><td><b>0-0</b></td><td style='color:#f44'>❌</td><td style='font-size:10px'>40岁Vozinha神扑, 本届最大冷门</td></tr><tr><td>6/14</td><td>🇸🇪 Sweden vs 🇹🇳 Tunisia</td><td><b>5-1</b></td><td style='color:#4f4'>✅</td><td style='font-size:10px'>Ayari双响, Tunisia主帅将被解雇</td></tr><tr><td>6/14</td><td>🇨🇮 Ivory Coast vs 🇪🇨 Ecuador</td><td><b>1-0</b></td><td style='color:#f44'>❌</td><td style='font-size:10px'>Amad绝杀, 模型判Ecuador胜</td></tr><tr><td>6/14</td><td>🇳🇱 Netherlands vs 🇯🇵 Japan</td><td><b>2-2</b></td><td style='color:#4f4'>✅</td><td style='font-size:10px'>Japan 88分钟绝平</td></tr><tr><td>6/14</td><td>🇩🇪 Germany vs 🇨🇼 Curaçao</td><td><b>7-1</b></td><td style='color:#4f4'>✅</td><td style='font-size:10px'>德国屠杀, Curaçao先拔头筹后崩溃</td></tr><tr><td>6/13</td><td>🇶🇦 Qatar vs 🇨🇭 Switzerland</td><td><b>1-1</b></td><td style='color:#f44'>❌</td><td style='font-size:10px'>QAT 94分钟绝平, VAR争议</td></tr><tr><td>6/13</td><td>🇧🇷 Brazil vs 🇲🇦 Morocco</td><td><b>1-1</b></td><td style='color:#4f4'>✅</td><td style='font-size:10px'>Neymar缺阵, 巴西不胜</td></tr><tr><td>6/13</td><td>🇦🇺 Australia vs 🇹🇷 Türkiye</td><td><b>2-0</b></td><td style='color:#4f4'>✅</td><td style='font-size:10px'>Irankunda致敬Cahill, Beach 8扑救</td></tr><tr><td>6/13</td><td>🇭🇹 Haiti vs 🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scotland</td><td><b>0-1</b></td><td style='color:#4f4'>✅</td><td style='font-size:10px'>McGinn制胜, Scotland 1998年后首胜</td></tr><tr><td>6/12</td><td>🇺🇸 United States vs 🇵🇾 Paraguay</td><td><b>4-1</b></td><td style='color:#4f4'>✅</td><td style='font-size:10px'>Balogun双响, USA碾压</td></tr><tr><td>6/12</td><td>🇨🇦 Canada vs 🇧🇦 Bosnia-Herzegovina</td><td><b>1-1</b></td><td style='color:#4f4'>✅</td><td style='font-size:10px'>Davies伤缺, 1-1平</td></tr><tr><td>6/11</td><td>🇰🇷 South Korea vs 🇨🇿 Czechia</td><td><b>2-1</b></td><td style='color:#4f4'>✅</td><td style='font-size:10px'>Korea 2-1逆转, Hwang 1球1助</td></tr><tr><td>6/11</td><td>🇲🇽 Mexico vs 🇿🇦 South Africa</td><td><b>2-0</b></td><td style='color:#4f4'>✅</td><td style='font-size:10px'>Mexico 2-0, Quinones+Jimenez, 3红牌创纪录</td></tr></tbody></table></div></div>
</div>

<div id="today" class="panel">
  <div class="card"><h3>6/17-18 今日预测 + 200元购彩方案</h3>
  <table><thead><tr><th>比赛</th><th>胜/平/负%</th><th>Top比分</th><th>xG</th><th>Δ</th><th>冷门</th><th>置信</th></tr></thead>
  <tbody><tr><td>Portugal vs DR Congo</td><td>34/41/25</td><td>2-1</td><td>2.23-1.45</td><td>+30.0</td><td style='color:#fa0'>★★☆ 中</td><td style='color:#4f4'>高</td></tr><tr><td>England vs Croatia</td><td>36/40/24</td><td>1-1</td><td>1.63-1.27</td><td>+18.9</td><td style='color:#fa0'>★★☆ 中</td><td style='color:#4f4'>高</td></tr><tr><td>Ghana vs Panama</td><td>25/49/26</td><td>1-1</td><td>1.5-1.53</td><td>-5.0</td><td style=''>★☆☆ 低</td><td style='color:#f44'>低——建议观望</td></tr><tr><td>Colombia vs Uzbekistan</td><td>43/38/19</td><td>1-0</td><td>1.44-0.85</td><td>+27.0</td><td style=''>★☆☆ 低</td><td style='color:#4f4'>高</td></tr></tbody></table></div>
  <div class="card"><h3>📋 200元自动投注方案</h3><pre style="font-size:10px;color:#aaccdd;line-height:1.4;white-space:pre-wrap">""" + "======================================================================
  竞彩足球 2026世界杯 自动投注方案 v3.0
  引擎: 模型自动输出 v3.0 (让球+自由过关+稳胆)  |  预算: 200元
======================================================================

📋 场次: 稳胆[] | 稳健[] | 排除['🇬🇭 Ghana vs 🇵🇦 Panama']

⭐ 稳胆 — 跳过: 今日无稳胆场次(Δ≥25+概率≥50%)

──────────────────────────────────────────────────────────────────────
🛡️ conservative — 跳过: 无可投场次

──────────────────────────────────────────────────────────────────────
📊 均衡混合 — 30元 | 2串1 混合过关(胜平负+总进球)
──────────────────────────────────────────────────────────────────────
  6/18 10:00 🇨🇴 Colombia vs 🇺🇿 Uzbekistan         → 🇨🇴 Colombia胜   概率43.0% 估赔1.24
  6/18 01:00 🇵🇹 Portugal vs 🇨🇩 DR Congo           → 总进球3球          (xG=3.7) 估赔3.2
  预估回报: ≈119元
  命中条件: 

──────────────────────────────────────────────────────────────────────
🔀 自由过关3串4 — 40元 | 3注2串1 + 1注3串1 = 4注 | M串N 容错 (错1场仍中2串1)
──────────────────────────────────────────────────────────────────────
  6/18 10:00 🇨🇴 Colombia vs 🇺🇿 Uzbekistan         → 🇨🇴 Colombia胜   概率43.0% 估赔1.24
  6/18 01:00 🇵🇹 Portugal vs 🇨🇩 DR Congo           → 平局             概率41.0% 估赔5.86
  6/18 04:00 🏴󠁧󠁢󠁥󠁮󠁧󠁿 England vs 🇭🇷 Croatia        → 平局             概率40.3% 估赔3.5
  结构: 3注2串1 + 1注3串1 = 4注 | 每单位8元/倍 × 5倍 = 40元
  2串1赔率: 7.27× / 4.34× / 20.51×
  3串1赔率: 25.43×
  🛡️ 容错: 错1场仍中1注2串1 ≈43元
  预估回报: ≈0元
  全中回报: ≈575元
  命中条件: 3场中至少2场 = 中1注2串1; 3场全中 = 3注2串1+1注3串1

──────────────────────────────────────────────────────────────────────
🎯 进取比分 — 20元 | 3串1 比分
──────────────────────────────────────────────────────────────────────
             🏳️ 🇨🇴 Colombia vs 🇺🇿 Uzbekistan      → 1-0            估赔7.1
             🏳️ 🇵🇹 Portugal vs 🇨🇩 DR Congo        → 2-1            估赔7.1
             🏳️ 🏴󠁧󠁢󠁥󠁮󠁧󠁿 England vs 🇭🇷 Croatia     → 1-1            估赔7.1
  预估回报: ≈7158元
  命中条件: 🇨🇴 Colombia vs 🇺🇿 Uzbekistan 1-0 AND 🇵🇹 Portugal vs 🇨🇩 DR Congo 2-1 AND 🏴󠁧󠁢󠁥󠁮󠁧󠁿 

💰 保留金: 110元 (保留金：按实战铁律每日保留5%)

══════════════════════════════════════════════════════════════════════
💵 全中总回报: ≈7852元
══════════════════════════════════════════════════════════════════════

⚠️ 风险提示:
  • 排除 🇬🇭 Ghana vs 🇵🇦 Panama: 低——建议观望

📐 模型自动输出 v3.0 | 让球+自由过关容错+稳胆 | 竞彩90分钟赛果为准"</pre></div>
</div>

<div id="rankings" class="panel">
  <div class="card"><h3>48队多源排名 — 模型 vs ESPN vs Fox vs Yahoo</h3>
  <p class="legend">⚠️=偏差>8位 △=偏差>4位 🔴🟡=八卦预警</p>
  <div style="overflow-x:auto"><table><thead><tr><th>#</th><th>球队</th><th>总分</th><th>硬</th><th>外</th><th>八</th><th>ESPN</th><th>Fox</th><th>Yh</th><th>共识</th></tr></thead>
  <tbody><tr><td>1</td><td><b>France</b></td><td>87.6</td><td>90.6</td><td>74.3</td><td>100.0</td><td>2</td><td>1</td><td>1</td><td>1.3</td></tr><tr><td>2</td><td><b>England</b></td><td>86.1</td><td>91.1</td><td>68.6</td><td>100.0</td><td>4</td><td>3</td><td>4</td><td>3.7</td></tr><tr><td>3</td><td><b>Spain</b></td><td>82.2</td><td>89.1</td><td>58.7</td><td>100.0</td><td>1</td><td>2</td><td>2</td><td>1.7</td></tr><tr><td>4</td><td><b>Portugal</b>🟡</td><td>80.1</td><td>84.5</td><td>67.9</td><td>87.5</td><td>6</td><td>6</td><td>5</td><td>5.7</td></tr><tr><td>5</td><td><b>Argentina</b></td><td>79.5</td><td>88.3</td><td>51.1</td><td>100.0</td><td>3</td><td>5</td><td>3</td><td>3.7</td></tr><tr><td>6</td><td><b>Germany</b></td><td>76.4</td><td>79.6</td><td>55.5</td><td>100.0</td><td>7</td><td>9</td><td>7</td><td>7.7</td></tr><tr><td>7</td><td><b>Colombia</b></td><td>76.2</td><td>76.5</td><td>59.7</td><td>100.0</td><td>12</td><td>4</td><td>10</td><td>8.7</td></tr><tr><td>8</td><td><b>Sweden</b></td><td>75.2</td><td>71.6</td><td>64.6</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>9</td><td><b>Morocco</b></td><td>74.1</td><td>77.7</td><td>50.8</td><td>100.0</td><td>9</td><td>13</td><td>11</td><td>11.0</td></tr><tr><td>10</td><td><b>Norway</b></td><td>73.5</td><td>71.4</td><td>59.3</td><td>100.0</td><td>10</td><td>16</td><td>-</td><td>13.0</td></tr><tr><td>11</td><td><b>Mexico</b></td><td>73.4</td><td>76.4</td><td>50.8</td><td>100.0</td><td>-</td><td>14</td><td>-</td><td>14.0</td></tr><tr><td>12</td><td><b>Australia</b></td><td>73.0</td><td>68.9</td><td>65.0</td><td>95.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>13</td><td><b>Switzerland</b></td><td>71.3</td><td>72.6</td><td>50.0</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>14</td><td><b>Uruguay</b></td><td>71.1</td><td>72.1</td><td>50.3</td><td>100.0</td><td>-</td><td>15</td><td>14</td><td>14.5</td></tr><tr><td>15</td><td><b>Croatia</b></td><td>70.2</td><td>73.0</td><td>45.6</td><td>100.0</td><td>14</td><td>10</td><td>15</td><td>13.0</td></tr><tr><td>16</td><td><b>Brazil</b>🟡 ⚠️差10</td><td>69.2</td><td>71.7</td><td>51.1</td><td>90.0</td><td>5</td><td>7</td><td>6</td><td>6.0</td></tr><tr><td>17</td><td><b>Belgium</b> △7</td><td>69.2</td><td>71.7</td><td>44.4</td><td>100.0</td><td>11</td><td>11</td><td>9</td><td>10.3</td></tr><tr><td>18</td><td><b>Japan</b></td><td>68.4</td><td>57.4</td><td>65.8</td><td>100.0</td><td>15</td><td>-</td><td>-</td><td>15.0</td></tr><tr><td>19</td><td><b>South Korea</b></td><td>68.4</td><td>67.4</td><td>49.0</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>20</td><td><b>Netherlands</b> ⚠️差12</td><td>67.8</td><td>67.8</td><td>49.7</td><td>95.0</td><td>8</td><td>8</td><td>8</td><td>8.0</td></tr><tr><td>21</td><td><b>Austria</b></td><td>67.5</td><td>65.2</td><td>49.5</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>22</td><td><b>Egypt</b></td><td>66.9</td><td>59.3</td><td>57.6</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>23</td><td><b>Algeria</b></td><td>66.6</td><td>58.7</td><td>57.6</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>24</td><td><b>United States</b>🟡 ⚠️差12</td><td>64.7</td><td>71.2</td><td>37.1</td><td>90.0</td><td>-</td><td>12</td><td>-</td><td>12.0</td></tr><tr><td>25</td><td><b>Scotland</b></td><td>64.0</td><td>58.4</td><td>49.3</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>26</td><td><b>Senegal</b>🟡 ⚠️差14</td><td>62.7</td><td>61.7</td><td>49.6</td><td>85.0</td><td>13</td><td>-</td><td>12</td><td>12.5</td></tr><tr><td>27</td><td><b>Ivory Coast</b>🟡</td><td>60.5</td><td>57.6</td><td>49.1</td><td>85.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>28</td><td><b>Canada</b></td><td>59.7</td><td>49.8</td><td>49.2</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>29</td><td><b>Ecuador</b> ⚠️差16</td><td>59.6</td><td>55.3</td><td>39.8</td><td>100.0</td><td>-</td><td>-</td><td>13</td><td>13.0</td></tr><tr><td>30</td><td><b>Czechia</b></td><td>59.3</td><td>49.2</td><td>49.0</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>31</td><td><b>Türkiye</b></td><td>58.5</td><td>53.4</td><td>39.5</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>32</td><td><b>Bosnia-Herzegovina</b></td><td>57.5</td><td>45.5</td><td>49.1</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>33</td><td><b>Iran</b>🔴</td><td>55.3</td><td>58.3</td><td>64.0</td><td>35.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>34</td><td><b>DR Congo</b></td><td>55.0</td><td>40.6</td><td>48.9</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>35</td><td><b>South Africa</b></td><td>54.9</td><td>40.6</td><td>48.8</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>36</td><td><b>Qatar</b></td><td>54.8</td><td>40.3</td><td>48.8</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>37</td><td><b>Paraguay</b></td><td>54.1</td><td>38.8</td><td>49.0</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>38</td><td><b>Cape Verde</b></td><td>54.0</td><td>38.8</td><td>48.8</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>39</td><td><b>Uzbekistan</b></td><td>54.0</td><td>38.7</td><td>48.9</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>40</td><td><b>Panama</b></td><td>52.7</td><td>36.0</td><td>48.9</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>41</td><td><b>Tunisia</b>🟡</td><td>52.6</td><td>41.3</td><td>49.0</td><td>86.4</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>42</td><td><b>New Zealand</b></td><td>52.5</td><td>35.7</td><td>48.8</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>43</td><td><b>Saudi Arabia</b></td><td>52.4</td><td>35.5</td><td>48.9</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>44</td><td><b>Curaçao</b></td><td>50.8</td><td>32.4</td><td>48.8</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>45</td><td><b>Jordan</b></td><td>50.7</td><td>32.2</td><td>48.8</td><td>100.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>46</td><td><b>Iraq</b>🔴</td><td>48.2</td><td>39.1</td><td>48.9</td><td>70.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>47</td><td><b>Haiti</b>🟡</td><td>47.6</td><td>31.9</td><td>48.8</td><td>85.0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr><tr><td>48</td><td><b>Ghana</b>🔴</td><td>46.0</td><td>30.3</td><td>49.0</td><td>80.5</td><td>-</td><td>-</td><td>-</td><td>-</td></tr></tbody></table></div></div>
</div>

<div id="standings" class="panel">
  <div class="card"><h3>小组积分榜</h3>
  <table><thead><tr><th></th><th>组</th><th>球队</th><th>分</th><th>场</th><th>战绩</th><th>进球</th><th>净胜</th></tr></thead>
  <tbody><tr><td>🥇</td><td>A</td><td>🇲🇽 Mexico</td><td>3</td><td>1场</td><td>1-0-0</td><td>2:0</td><td>+2</td></tr><tr><td>🥈</td><td>A</td><td>🇰🇷 South Korea</td><td>3</td><td>1场</td><td>1-0-0</td><td>2:1</td><td>+1</td></tr><tr><td>📌</td><td>A</td><td>🇨🇿 Czechia</td><td>0</td><td>1场</td><td>0-0-1</td><td>1:2</td><td>-1</td></tr><tr><td>  </td><td>A</td><td>🇿🇦 South Africa</td><td>0</td><td>1场</td><td>0-0-1</td><td>0:2</td><td>-2</td></tr><tr><td>🥇</td><td>B</td><td>🇨🇦 Canada</td><td>1</td><td>1场</td><td>0-1-0</td><td>1:1</td><td>+0</td></tr><tr><td>🥈</td><td>B</td><td>🇧🇦 Bosnia-Herzegovina</td><td>1</td><td>1场</td><td>0-1-0</td><td>1:1</td><td>+0</td></tr><tr><td>📌</td><td>B</td><td>🇶🇦 Qatar</td><td>1</td><td>1场</td><td>0-1-0</td><td>1:1</td><td>+0</td></tr><tr><td>  </td><td>B</td><td>🇨🇭 Switzerland</td><td>1</td><td>1场</td><td>0-1-0</td><td>1:1</td><td>+0</td></tr><tr><td>🥇</td><td>C</td><td>🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scotland</td><td>3</td><td>1场</td><td>1-0-0</td><td>1:0</td><td>+1</td></tr><tr><td>🥈</td><td>C</td><td>🇧🇷 Brazil</td><td>1</td><td>1场</td><td>0-1-0</td><td>1:1</td><td>+0</td></tr><tr><td>📌</td><td>C</td><td>🇲🇦 Morocco</td><td>1</td><td>1场</td><td>0-1-0</td><td>1:1</td><td>+0</td></tr><tr><td>  </td><td>C</td><td>🇭🇹 Haiti</td><td>0</td><td>1场</td><td>0-0-1</td><td>0:1</td><td>-1</td></tr><tr><td>🥇</td><td>D</td><td>🇺🇸 United States</td><td>3</td><td>1场</td><td>1-0-0</td><td>4:1</td><td>+3</td></tr><tr><td>🥈</td><td>D</td><td>🇦🇺 Australia</td><td>3</td><td>1场</td><td>1-0-0</td><td>2:0</td><td>+2</td></tr><tr><td>📌</td><td>D</td><td>🇹🇷 Türkiye</td><td>0</td><td>1场</td><td>0-0-1</td><td>0:2</td><td>-2</td></tr><tr><td>  </td><td>D</td><td>🇵🇾 Paraguay</td><td>0</td><td>1场</td><td>0-0-1</td><td>1:4</td><td>-3</td></tr><tr><td>🥇</td><td>E</td><td>🇩🇪 Germany</td><td>3</td><td>1场</td><td>1-0-0</td><td>7:1</td><td>+6</td></tr><tr><td>🥈</td><td>E</td><td>🇨🇮 Ivory Coast</td><td>3</td><td>1场</td><td>1-0-0</td><td>1:0</td><td>+1</td></tr><tr><td>📌</td><td>E</td><td>🇪🇨 Ecuador</td><td>0</td><td>1场</td><td>0-0-1</td><td>0:1</td><td>-1</td></tr><tr><td>  </td><td>E</td><td>🇨🇼 Curaçao</td><td>0</td><td>1场</td><td>0-0-1</td><td>1:7</td><td>-6</td></tr><tr><td>🥇</td><td>F</td><td>🇸🇪 Sweden</td><td>3</td><td>1场</td><td>1-0-0</td><td>5:1</td><td>+4</td></tr><tr><td>🥈</td><td>F</td><td>🇳🇱 Netherlands</td><td>1</td><td>1场</td><td>0-1-0</td><td>2:2</td><td>+0</td></tr><tr><td>📌</td><td>F</td><td>🇯🇵 Japan</td><td>1</td><td>1场</td><td>0-1-0</td><td>2:2</td><td>+0</td></tr><tr><td>  </td><td>F</td><td>🇹🇳 Tunisia</td><td>0</td><td>1场</td><td>0-0-1</td><td>1:5</td><td>-4</td></tr><tr><td>🥇</td><td>G</td><td>🇮🇷 Iran</td><td>1</td><td>1场</td><td>0-1-0</td><td>2:2</td><td>+0</td></tr><tr><td>🥈</td><td>G</td><td>🇳🇿 New Zealand</td><td>1</td><td>1场</td><td>0-1-0</td><td>2:2</td><td>+0</td></tr><tr><td>📌</td><td>G</td><td>🇧🇪 Belgium</td><td>1</td><td>1场</td><td>0-1-0</td><td>1:1</td><td>+0</td></tr><tr><td>  </td><td>G</td><td>🇪🇬 Egypt</td><td>1</td><td>1场</td><td>0-1-0</td><td>1:1</td><td>+0</td></tr><tr><td>🥇</td><td>H</td><td>🇸🇦 Saudi Arabia</td><td>1</td><td>1场</td><td>0-1-0</td><td>1:1</td><td>+0</td></tr><tr><td>🥈</td><td>H</td><td>🇺🇾 Uruguay</td><td>1</td><td>1场</td><td>0-1-0</td><td>1:1</td><td>+0</td></tr><tr><td>📌</td><td>H</td><td>🇪🇸 Spain</td><td>1</td><td>1场</td><td>0-1-0</td><td>0:0</td><td>+0</td></tr><tr><td>  </td><td>H</td><td>🇨🇻 Cape Verde</td><td>1</td><td>1场</td><td>0-1-0</td><td>0:0</td><td>+0</td></tr><tr><td>🥇</td><td>I</td><td>🇳🇴 Norway</td><td>3</td><td>1场</td><td>1-0-0</td><td>4:1</td><td>+3</td></tr><tr><td>🥈</td><td>I</td><td>🇫🇷 France</td><td>3</td><td>1场</td><td>1-0-0</td><td>3:1</td><td>+2</td></tr><tr><td>📌</td><td>I</td><td>🇸🇳 Senegal</td><td>0</td><td>1场</td><td>0-0-1</td><td>1:3</td><td>-2</td></tr><tr><td>  </td><td>I</td><td>🇮🇶 Iraq</td><td>0</td><td>1场</td><td>0-0-1</td><td>1:4</td><td>-3</td></tr><tr><td>🥇</td><td>J</td><td>🇦🇹 Austria</td><td>3</td><td>1场</td><td>1-0-0</td><td>3:1</td><td>+2</td></tr><tr><td>🥈</td><td>J</td><td>🇦🇷 Argentina</td><td>3</td><td>1场</td><td>1-0-0</td><td>2:0</td><td>+2</td></tr><tr><td>📌</td><td>J</td><td>🇯🇴 Jordan</td><td>0</td><td>1场</td><td>0-0-1</td><td>1:3</td><td>-2</td></tr><tr><td>  </td><td>J</td><td>🇩🇿 Algeria</td><td>0</td><td>1场</td><td>0-0-1</td><td>0:2</td><td>-2</td></tr><tr><td>🥇</td><td>K</td><td>🇵🇹 Portugal</td><td>0</td><td>0场</td><td>0-0-0</td><td>0:0</td><td>+0</td></tr><tr><td>🥈</td><td>K</td><td>🇨🇴 Colombia</td><td>0</td><td>0场</td><td>0-0-0</td><td>0:0</td><td>+0</td></tr><tr><td>📌</td><td>K</td><td>🇺🇿 Uzbekistan</td><td>0</td><td>0场</td><td>0-0-0</td><td>0:0</td><td>+0</td></tr><tr><td>  </td><td>K</td><td>🇨🇩 DR Congo</td><td>0</td><td>0场</td><td>0-0-0</td><td>0:0</td><td>+0</td></tr><tr><td>🥇</td><td>L</td><td>🏴󠁧󠁢󠁥󠁮󠁧󠁿 England</td><td>0</td><td>0场</td><td>0-0-0</td><td>0:0</td><td>+0</td></tr><tr><td>🥈</td><td>L</td><td>🇭🇷 Croatia</td><td>0</td><td>0场</td><td>0-0-0</td><td>0:0</td><td>+0</td></tr><tr><td>📌</td><td>L</td><td>🇬🇭 Ghana</td><td>0</td><td>0场</td><td>0-0-0</td><td>0:0</td><td>+0</td></tr><tr><td>  </td><td>L</td><td>🇵🇦 Panama</td><td>0</td><td>0场</td><td>0-0-0</td><td>0:0</td><td>+0</td></tr></tbody></table></div>
</div>

<div id="news" class="panel">
  <div class="card"><h3>重要新闻 (实时更新)</h3>
  <table><thead><tr><th></th><th>标题</th><th>详情</th></tr></thead>
  <tbody><tr><td>🔴</td><td><b>Ruben Dias缺阵</b></td><td style='font-size:10px'>葡萄牙防线核心热身赛被撞击, Martinez确认缺战首轮(Ge.Globo 6/16)</td></tr><tr><td>🔴</td><td><b>Thomas Partey被拒入加拿大</b></td><td style='font-size:10px'>Ghana中场核心被加拿大拒绝入境, 缺席首战vs Panama(Yahoo独家)</td></tr><tr><td>🟡</td><td><b>France 3-1 Senegal</b></td><td style='font-size:10px'>Mbappe双响+20米世界波, 法国开局慢热但下半场爆发(BBC)</td></tr><tr><td>🟡</td><td><b>Norway 4-1 Iraq</b></td><td style='font-size:10px'>Haaland首轮双响, Norway净胜球压法国排I组榜首(ABC)</td></tr><tr><td>🟡</td><td><b>Messi 200场里程碑</b></td><td style='font-size:10px'>第5届世界杯进球, Argentina 2-0 Algeria(ESPN)</td></tr><tr><td>🟡</td><td><b>VAR争议持续</b></td><td style='font-size:10px'>Gary Neville称FIFA'独裁', SAOT动画故障未播出(Metro)</td></tr><tr><td>🟢</td><td><b>USA 4-1 Paraguay</b></td><td style='font-size:10px'>场倾斜率80.5%为1998年以来第4高, Balogun金靴领跑(ESPN)</td></tr><tr><td>🟢</td><td><b>网易彩票=SP来源</b></td><td style='font-size:10px'>sports.163.com/caipiao确认为竞彩SP稳定源, 含让球盘+多日预告</td></tr></tbody></table></div>
</div>

<div id="injuries" class="panel">
  <div class="card"><h3>伤病追踪 ({sum(len(v) for v in injuries.values())}条)</h3>
  <table><thead><tr><th></th><th>球队</th><th>球员</th><th>角色</th><th>状态</th><th>原因</th></tr></thead>
  <tbody><tr><td>🔴</td><td>Brazil</td><td>Rodrygo</td><td>core_scorer</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Brazil</td><td>Estevao</td><td>core_creator</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Brazil</td><td>Eder Militao</td><td>defense_leader</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Brazil</td><td>Vanderson</td><td>regular_starter</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🟡</td><td>Brazil</td><td>Neymar</td><td>regular_starter</td><td>doubtful</td><td style='font-size:10px'></td></tr><tr><td>🟡</td><td>Canada</td><td>Alphonso Davies</td><td>core_creator</td><td>doubtful</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Canada</td><td>Marcelo Flores</td><td>rotation</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Spain</td><td>Fermin Lopez</td><td>rotation</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🟡</td><td>Spain</td><td>Lamine Yamal</td><td>core_scorer</td><td>doubtful</td><td style='font-size:10px'></td></tr><tr><td>🟡</td><td>France</td><td>William Saliba</td><td>defense_leader</td><td>doubtful</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>France</td><td>Hugo Ekitike</td><td>rotation</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Germany</td><td>Serge Gnabry</td><td>regular_starter</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Germany</td><td>Marc-Andre ter Stegen</td><td>regular_starter</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Germany</td><td>Lennart Karl</td><td>rotation</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Ghana</td><td>Thomas Partey</td><td>core_creator</td><td>out</td><td style='font-size:10px'>被拒绝进入加拿大(Yahoo Sports独家), 缺席首战vs Panama</td></tr><tr><td>🔴</td><td>Ghana</td><td>Mohammed Kudus</td><td>core_creator</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Japan</td><td>Kaoru Mitoma</td><td>core_scorer</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Japan</td><td>Takumi Minamino</td><td>regular_starter</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Japan</td><td>Wataru Endo</td><td>regular_starter</td><td>out_retired</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Netherlands</td><td>Xavi Simons</td><td>core_creator</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Netherlands</td><td>Jurrien Timber</td><td>defense_leader</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Netherlands</td><td>Matthijs de Ligt</td><td>defense_leader</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Netherlands</td><td>Jerdy Schouten</td><td>regular_starter</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>Portugal</td><td>Ruben Dias</td><td>defense_leader</td><td>out</td><td style='font-size:10px'>热身赛对尼日利亚被撞击, Martinez确认缺战首轮(Ge.Globo 6/16)</td></tr><tr><td>🔴</td><td>Scotland</td><td>Billy Gilmour</td><td>regular_starter</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🟡</td><td>United States</td><td>Christian Pulisic</td><td>core_scorer</td><td>doubtful</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>United States</td><td>Patrick Agyemang</td><td>rotation</td><td>out</td><td style='font-size:10px'></td></tr><tr><td>🔴</td><td>United States</td><td>Johnny Cardoso</td><td>regular_starter</td><td>out</td><td style='font-size:10px'></td></tr></tbody></table></div>
</div>

<div id="gossip" class="panel">
  <div class="card"><h3>八卦风控（仅扣分球队）</h3>
  <table><thead><tr><th></th><th>球队</th><th>扣分</th><th>事件</th><th>政治</th></tr></thead>
  <tbody><tr><td>🟢</td><td>Australia</td><td>1</td><td style='font-size:10px'>2-0土耳其爆冷, Irankunda世界杯处子球致敬Cahill, Beach 8次扑救</td><td></td></tr><tr><td>🟢</td><td>Brazil</td><td>2</td><td style='font-size:10px'>Neymar名望入选vs状态(2023年后未代表巴西出场)→国内争议+Ancelotti选人分歧</td><td></td></tr><tr><td>🟡</td><td>Ivory Coast</td><td>3</td><td style='font-size:10px'></td><td>★★★</td></tr><tr><td>🟡</td><td>Ghana</td><td>4</td><td style='font-size:10px'>Thomas Partey被拒绝进入加拿大→缺席首战vs Panama(Yahoo Sports独家)</td><td>★★★</td></tr><tr><td>🟡</td><td>Haiti</td><td>3</td><td style='font-size:10px'></td><td>★★★</td></tr><tr><td>🔴</td><td>Iran</td><td>13</td><td style='font-size:10px'>政治压力+基地被迫搬迁+签证被拒→球员心理压力极限</td><td>★★★★★</td></tr><tr><td>🟡</td><td>Iraq</td><td>6</td><td style='font-size:10px'>部分球员在美国机场被扣留问话→心理影响</td><td>★★★★</td></tr><tr><td>🟢</td><td>Netherlands</td><td>1</td><td style='font-size:10px'>Van Dijk公开批评世界杯补水暂停制度→潜在不满情绪</td><td></td></tr><tr><td>🟡</td><td>Portugal</td><td>5</td><td style='font-size:10px'>Braga主席公开攻击Martinez(5/24)+Ronaldo首发争议持续发酵+足协与CR7公司商业合作嫌</td><td></td></tr><tr><td>🟡</td><td>Senegal</td><td>3</td><td style='font-size:10px'></td><td>★★★</td></tr><tr><td>🟡</td><td>Tunisia</td><td>3</td><td style='font-size:10px'>主帅Lamouchi预计被解雇→赛前内乱(ESPN消息源)</td><td></td></tr><tr><td>🟢</td><td>United States</td><td>2</td><td style='font-size:10px'>4-1巴拉圭士气爆棚, 场倾斜率80.5%为1998年以来第4高, Pulisic小腿轻伤但无大碍</td><td></td></tr></tbody></table></div>
</div>

<div style="text-align:center;margin-top:8px">
  <button onclick="location.reload()" style="padding:5px 14px;background:#2a4a6a;border:none;color:#ffd700;border-radius:4px;cursor:pointer;font-size:11px">🔄 刷新</button>
</div>
<script>
function show(id){{
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  event.target.classList.add('active');
}}
setTimeout(function(){{ location.reload(); }}, 300000);
</script>
</body></html>"""

out = Path(__file__).parent / "dashboard.html"
out.write_text(HTML)
print(f"Dashboard v4.0 generated: {out}")

if "--serve" in sys.argv:
    import http.server, socketserver, webbrowser
    os.chdir(Path(__file__).parent)
    with socketserver.TCPServer(("", 8899), http.server.SimpleHTTPRequestHandler) as httpd:
        print(f"http://localhost:8899/dashboard.html")
        webbrowser.open(f"http://localhost:8899/dashboard.html")
        httpd.serve_forever()
