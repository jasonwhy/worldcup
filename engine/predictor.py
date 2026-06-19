"""
主预测器聚合层
- 三层归一化 → 总分
- 单场比赛完整预测
- 输出格式化模板
"""
import json
from pathlib import Path
from .hard_data import (hard_data_score, team_defense_score,
                          defensive_resilience, attacking_conversion,
                          xg_proxy, match_style, style_matchup_bonus,
                          player_availability_impact, fatigue_penalty)
from .betting import betting_score
from .gossip import gossip_score
from .poisson import predict_match

DATA_DIR = Path(__file__).parent.parent / "data"


def load_json(name):
    with open(DATA_DIR / name, "r") as f:
        return json.load(f)


def team_name(team_id: str) -> str:
    teams = load_json("teams.json")
    return teams.get(team_id, {}).get("name", team_id)


def final_score(team_id: str, opponent_id: str = None) -> dict:
    """
    三层加权汇总 → 最终0-100总分
    """
    hard = hard_data_score(team_id, opponent_id)
    betting = betting_score(team_id, opponent_id)
    gossip = gossip_score(team_id)

    # 政治因子精准加权: level>=3时gossip权重从20%升至25%
    pol_level = gossip.get("detail", {}).get("political_level", 0)
    if pol_level >= 4:
        gw = 0.25; hw = 0.47; bw = 0.28
    elif pol_level >= 2:
        gw = 0.22; hw = 0.48; bw = 0.30
    else:
        gw = 0.20; hw = 0.50; bw = 0.30

    final = hard["score"] * hw + betting["score"] * bw + gossip["score"] * gw

    return {
        "team_id": team_id,
        "name": team_name(team_id),
        "total": round(final, 1),
        "hard_data": hard,
        "betting": betting,
        "gossip": gossip
    }


def predict(head_to_head: str) -> dict:
    """
    单场比赛完整预测
    head_to_head: "FRA-SEN" 或 "France-Senegal"
    """
    teams = load_json("teams.json")

    # 解析输入
    if "-" in head_to_head:
        parts = head_to_head.split("-")
    else:
        parts = head_to_head.split(" vs ")
    home_id, away_id = parts[0].strip().upper(), parts[1].strip().upper()

    # 反向查找（如果用户输入了国家名）
    id_to_code = {v["name"].upper(): k for k, v in teams.items()}
    if home_id in id_to_code:
        home_id = id_to_code[home_id]
    if away_id in id_to_code:
        away_id = id_to_code[away_id]

    if home_id not in teams or away_id not in teams:
        return {"error": f"球队代码错误: {home_id} 或 {away_id}"}

    # 三层评分
    home_final = final_score(home_id, away_id)
    away_final = final_score(away_id, home_id)

    # 防守分
    home_def = team_defense_score(home_id)
    away_def = team_defense_score(away_id)

    # 八卦扣分（用于冷门修正）
    home_gossip = gossip_score(home_id)
    away_gossip = gossip_score(away_id)
    home_gossip_deduction = 100 - home_gossip["score"]
    away_gossip_deduction = 100 - away_gossip["score"]

    # 大小球盘口（简化：基于双方攻击能力）
    r5_h = teams[home_id]["recent_5"]
    r5_a = teams[away_id]["recent_5"]
    market_goals = round((r5_h["gf"] + r5_h["ga"] + r5_a["gf"] + r5_a["ga"]) / 10, 1)

    # P0: 比赛轮次检测 (通过双方已赛场次推断)
    groups = load_json("groups.json")
    home_played = 0
    for gid, gdata in groups.items():
        if home_id in gdata["teams"]:
            home_played = gdata["standings"][home_id]["p"]
            break
    # 0场=首轮, 1场=次轮, 2场=末轮
    round_map = {0: "group_1", 1: "group_2", 2: "group_3"}
    match_round = round_map.get(home_played, "group_1")

    # P0: 温度数据 (基于场馆城市，简化映射)
    venue_temp = {
        "Dallas": 34, "Houston": 35, "Miami": 33, "Atlanta": 32,
        "Los Angeles": 28, "San Francisco": 24, "Seattle": 22, "Vancouver": 21,
        "Mexico City": 22, "Guadalajara": 26, "Monterrey": 31,
        "Toronto": 23, "Boston": 25, "Philadelphia": 27, "New York": 28, "Kansas City": 29,
    }
    temperature = venue_temp.get("Dallas", 25)  # 默认值，后续可精确到具体场馆

    # P1: 屠杀因子所需数据
    home_gpg = r5_h["gf"] / 5
    away_gpg = r5_a["gf"] / 5
    home_cpg = r5_h["ga"] / 5
    away_cpg = r5_a["ga"] / 5

    # [v2.3] 防守韧性 + 进攻转化率
    home_dr = defensive_resilience(home_id)
    away_dr = defensive_resilience(away_id)
    home_ac = attacking_conversion(home_id)
    away_ac = attacking_conversion(away_id)

    # [v2.3 P1] xG代理 + 比赛风格
    home_xg = xg_proxy(home_id)
    away_xg = xg_proxy(away_id)
    home_style = match_style(home_id)
    away_style = match_style(away_id)
    style_bonus = style_matchup_bonus(home_style, away_style)

    # [v2.3 P2] 球员可用性 + 体能
    from datetime import date
    home_pp = player_availability_impact(home_id)
    away_pp = player_availability_impact(away_id)
    today_str = date.today().strftime("%m/%d").lstrip("0")
    home_fat = fatigue_penalty(home_id, today_str)
    away_fat = fatigue_penalty(away_id, today_str)

    # 泊松预测 [v2.3]
    result = predict_match(
        home_score=home_final["total"],
        away_score=away_final["total"],
        home_defense=home_def,
        away_defense=away_def,
        home_gossip_deduction=home_gossip_deduction,
        away_gossip_deduction=away_gossip_deduction,
        market_total_goals=market_goals,
        match_round=match_round,
        temperature=temperature,
        home_goals_per_game=home_gpg,
        away_goals_per_game=away_gpg,
        home_conceded=home_cpg,
        away_conceded=away_cpg,
        home_def_resilience=home_dr,
        away_def_resilience=away_dr,
        home_att_conversion=home_ac,
        away_att_conversion=away_ac,
        home_xg_off=home_xg["offensive"],
        away_xg_off=away_xg["offensive"],
        home_xg_def=home_xg["defensive"],
        away_xg_def=away_xg["defensive"],
        style_bonus=style_bonus,
        home_player_penalty=home_pp,
        away_player_penalty=away_pp,
        home_fatigue=home_fat,
        away_fatigue=away_fat
    )

    # [v2.3] SP市场先验融合 — 贝叶斯约束模型输出
    sp = load_json("sp.json")
    match_sp = sp.get("matches", {}).get(f"{home_id}-{away_id}", {})
    if match_sp and match_sp.get("home", 0) > 0:
        # 去边际化: 归一化隐含概率
        inv_sum = 1/match_sp["home"] + 1/match_sp["draw"] + 1/match_sp["away"]
        mkt_home = (1/match_sp["home"]) / inv_sum
        mkt_draw = (1/match_sp["draw"]) / inv_sum
        mkt_away = (1/match_sp["away"]) / inv_sum
        # 贝叶斯融合: 模型85% + 市场15%
        w = 0.15
        result["win_pct"] = round(result["win_pct"] * (1-w) + mkt_home * 100 * w, 1)
        result["draw_pct"] = round(result["draw_pct"] * (1-w) + mkt_draw * 100 * w, 1)
        result["lose_pct"] = round(result["lose_pct"] * (1-w) + mkt_away * 100 * w, 1)

    delta = round(home_final["total"] - away_final["total"], 1)

    # P1: 置信度标签 (v2.2: 基于输出概率, 非Δ)
    top_pct = max(result["win_pct"], result["draw_pct"], result["lose_pct"])
    if top_pct >= 48:
        confidence = "高"
    elif top_pct >= 40:
        confidence = "中"
    else:
        confidence = "低——建议观望"

    # 比分推荐
    if abs(delta) > 25:
        recommended_bet = "亚盘: 强队方向  |  大小球: 大球"
    elif delta > 10:
        recommended_bet = "亚盘: 强队-1(谨慎)  |  大小球: 视具体盘口"
    elif delta > 5:
        recommended_bet = "亚盘: 平手/强队-0.5  |  大小球: 正常"
    else:
        recommended_bet = "亚盘: 平手盘  |  大小球: 小球/正常"

    return {
        "match": f"{home_final['name']} vs {away_final['name']}",
        "delta": delta,
        "home": {
            "name": home_final["name"],
            "total": home_final["total"],
            "hard_data": home_final["hard_data"]["score"],
            "hard_detail": home_final["hard_data"]["detail"],
            "betting": home_final["betting"]["score"],
            "betting_detail": home_final["betting"]["detail"],
            "gossip": home_final["gossip"]["score"],
            "gossip_detail": home_final["gossip"]["detail"]
        },
        "away": {
            "name": away_final["name"],
            "total": away_final["total"],
            "hard_data": away_final["hard_data"]["score"],
            "hard_detail": away_final["hard_data"]["detail"],
            "betting": away_final["betting"]["score"],
            "betting_detail": away_final["betting"]["detail"],
            "gossip": away_final["gossip"]["score"],
            "gossip_detail": away_final["gossip"]["detail"]
        },
        "prediction": {
            "win_draw_lose": f"{result['win_pct']}% / {result['draw_pct']}% / {result['lose_pct']}%",
            "win_pct": result["win_pct"],
            "draw_pct": result["draw_pct"],
            "lose_pct": result["lose_pct"],
            "xg_home": result["xg_home"],
            "xg_away": result["xg_away"],
            "total_xg": result["total_xg"],
            "top_scores": result["top_scores"][:3],
            "cold_alert": result["cold_alert"],
            "recommended_bet": recommended_bet,
            "confidence": confidence,
            "match_round": match_round
        }
    }


def format_output(p: dict) -> str:
    """格式化输出模板"""
    if "error" in p:
        return f"❌ {p['error']}"

    pred = p["prediction"]
    home = p["home"]
    away = p["away"]

    top = pred["top_scores"]
    score_lines = ""
    for i, s in enumerate(top):
        bar = "█" * max(1, int(s["probability"] * 200))
        score_lines += f"  {['①','②','③'][i]} {p['home']['name']} {s['score']} {p['away']['name']}  概率 {s['probability']*100:.1f}%  {bar}\n"

    return f"""
┌──────────────────────────────────────────────────┐
│  {p['match']}                                   │
│  总分差 Δ={p['delta']:+.1f}                                    │
├──────────────────────────────────────────────────┤
│                                                   │
│  ════════════ 模型输入 ════════════               │
│                    {home['name']:>12}    {away['name']:>12}      差值      │
│  硬数据层(50%)     {home['hard_data']:>5.1f}      {away['hard_data']:>5.1f}     {home['hard_data']-away['hard_data']:>+.1f}    │
│  外盘信号层(30%)   {home['betting']:>5.1f}      {away['betting']:>5.1f}     {home['betting']-away['betting']:>+.1f}    │
│  八卦风控层(20%)   {home['gossip']:>5.1f}      {away['gossip']:>5.1f}     {home['gossip']-away['gossip']:>+.1f}    │
│  ────────────────────────────────────────         │
│  最终总分           {home['total']:>5.1f}      {away['total']:>5.1f}     {p['delta']:>+.1f}    │
│                                                   │
│  ════════════ 核心输出 ════════════               │
│                                                   │
│  🏆 胜平负                                       │
│  {home['name']}胜  {pred['win_pct']}%    平局  {pred['draw_pct']}%    {away['name']}胜  {pred['lose_pct']}%│
│                                                   │
│  ⚽ 比分预测                                      │
{score_lines}│                                                   │
│  📊 进球预期                                      │
│  总进球期望 {pred['total_xg']:.2f}球  {home['name']} xG={pred['xg_home']:.2f}  {away['name']} xG={pred['xg_away']:.2f} │
│                                                   │
│  ⚡ 冷门预警: {pred['cold_alert']:<30} │
│  📏 置信度: {pred.get('confidence', 'N/A'):<32} │
│  🎯 推荐方向: {pred['recommended_bet'][:40]}│
│                                                   │
└──────────────────────────────────────────────────┘
"""
