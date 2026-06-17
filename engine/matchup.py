"""
球员对位 + 战术风格匹配引擎
输出 ± 修正分，注入 hard_data 层
"""
import json
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"


def load(n):
    with open(DATA / n) as f:
        return json.load(f)


# 风格克制矩阵: [攻击风格][对手弱点] → 加成值
STYLE_MATCHUP = {
    ("high_press","aging_defense"): +3,
    ("direct_attack","aging_defense"): +2,
    ("counter_attack","high_press"): +3,
    ("possession","defensive_block"): -2,
    ("wing_play","narrow_defense"): +2,
    ("target_man","aerial_weakness"): +3,
    ("technical_press","physical_duels"): -2,
    ("physical_direct","technical_quality"): +2,
    ("set_pieces","defensive_organization"): +1,
    ("pace","aging_core"): +3,
    ("dribbling","tackling_weakness"): +2,
    ("playmaking","midfield_press_resistance"): +2,
    ("tournament_experience","inexperience"): +2,
    ("home_advantage","inexperience"): +2,
}

GK_RATING_IMPACT = {85: +1, 88: +2, 90: +3}  # 顶级门将额外加成


def player_matchup_score(team_a: str, team_b: str) -> dict:
    """计算两队球员对位优势"""
    players = load("players.json")
    a_p = players.get(team_a, {}).get("top_players", [])
    b_p = players.get(team_b, {}).get("top_players", [])

    if not a_p or not b_p:
        return {"total": 0, "detail": "无球员数据"}
    if len(a_p) < 2 or len(b_p) < 2:
        return {"total": 0, "detail": "球员数据不足(需≥2)"}

    score = 0
    details = []

    # 1. 锋线 vs 防线 (只计算双方都有对应位置球员时)
    a_attackers = [p for p in a_p if p["pos"] in ("FW","MF")]
    b_defenders = [p for p in b_p if p["pos"] in ("DF","GK")]
    if a_attackers and b_defenders:
        a_avg_rating = sum(p["rating"] for p in a_attackers) / len(a_attackers)
        b_avg_rating = sum(p["rating"] for p in b_defenders) / len(b_defenders)
        forward_advantage_a = round((a_avg_rating - b_avg_rating) / 5, 1)
        score += forward_advantage_a
        if abs(forward_advantage_a) > 1:
            details.append(f"锋线vs防线: {'+' if forward_advantage_a>0 else ''}{forward_advantage_a}")

    # 2. 锋线 vs 防线 (反方向, 同样需双方都有数据)
    b_attackers = [p for p in b_p if p["pos"] in ("FW","MF")]
    a_defenders = [p for p in a_p if p["pos"] in ("DF","GK")]
    if b_attackers and a_defenders:
        b_avg = sum(p["rating"] for p in b_attackers) / len(b_attackers)
        a_avg = sum(p["rating"] for p in a_defenders) / len(a_defenders)
        forward_advantage_b = round((b_avg - a_avg) / 5, 1)
        score -= forward_advantage_b
        if abs(forward_advantage_b) > 1:
            details.append(f"对手锋线vs我方防线: {'+' if -forward_advantage_b>0 else ''}{-forward_advantage_b}")

    # 3. 超级球星效应 (rating >= 90)
    superstars_a = [p for p in a_p if p["rating"] >= 90]
    superstars_b = [p for p in b_p if p["rating"] >= 90]
    star_diff = len(superstars_a) - len(superstars_b)
    if star_diff > 0:
        score += star_diff * 2
        details.append(f"超级球星效应: +{star_diff*2} ({', '.join(p['name'] for p in superstars_a)})")
    elif star_diff < 0:
        score += star_diff * 2
        details.append(f"对手超级球星效应: {star_diff*2} ({', '.join(p['name'] for p in superstars_b)})")

    # 4. 门将差距
    gk_a = next((p for p in a_p if p["pos"] == "GK"), None)
    gk_b = next((p for p in b_p if p["pos"] == "GK"), None)
    if gk_a and gk_b:
        gk_gap = gk_a["rating"] - gk_b["rating"]
        if gk_gap >= 5:
            score += 2
            details.append(f"门将优势: {gk_a['name']} vs {gk_b['name']} (+2)")
        elif gk_gap <= -5:
            score -= 2
            details.append(f"门将劣势: {gk_a['name']} vs {gk_b['name']} (-2)")

    # 5. xG总和差异
    xg_a = sum(p.get("xg90", 0) for p in a_p)
    xg_b = sum(p.get("xg90", 0) for p in b_p)
    xg_diff = round((xg_a - xg_b) * 2, 1)
    if abs(xg_diff) > 0.5:
        score += xg_diff
        details.append(f"xG优势: {'+' if xg_diff>0 else ''}{xg_diff:.1f}")

    final = round(max(-5, min(5, score)), 1)  # 收紧clamp
    return {"total": final, "detail": "; ".join(details) if details else "实力均衡"}


def tactical_matchup_score(team_a: str, team_b: str) -> dict:
    """计算战术风格匹配优势"""
    tactics = load("tactics.json")
    t_a = tactics.get(team_a, {})
    t_b = tactics.get(team_b, {})

    if not t_a or not t_b:
        return {"total": 0, "detail": "无战术数据"}

    score = 0
    details = []

    # 风格克制
    for (atk_style, def_weak), bonus in STYLE_MATCHUP.items():
        if atk_style in t_a.get("strength", []) and def_weak in t_b.get("weakness", []):
            score += bonus
            details.append(f"{atk_style}克制对手{def_weak}: +{bonus}")
        if atk_style in t_b.get("strength", []) and def_weak in t_a.get("weakness", []):
            score -= bonus
            details.append(f"对手{atk_style}克制我方{def_weak}: -{bonus}")

    final = round(max(-6, min(6, score)), 1)
    return {"total": final, "detail": "; ".join(details) if details else "战术无明显克制"}


def full_matchup_score(team_a: str, team_b: str) -> dict:
    """综合球员+战术的对位评分 (± 可注入硬数据或作为独立修正)"""
    player = player_matchup_score(team_a, team_b)
    tactic = tactical_matchup_score(team_a, team_b)
    combined = round(player["total"] * 0.55 + tactic["total"] * 0.45, 1)

    return {
        "team_a": team_a, "team_b": team_b,
        "player_score": player["total"],
        "player_detail": player["detail"],
        "tactical_score": tactic["total"],
        "tactical_detail": tactic["detail"],
        "combined": combined,
        "direction": "A有利" if combined > 0 else ("B有利" if combined < 0 else "均衡"),
    }
