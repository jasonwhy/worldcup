"""
硬数据层引擎 —— 球队真实实力画像
- 基础实力分 (FIFA排名+Elo+身价+大赛经验)
- 近10场状态评估 (战绩面板+WARO对手质量+攻防效率+关键球员)
- 伤病折损
- 归一化输出0-100分
"""
import json
import math
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def load_json(name):
    with open(DATA_DIR / name, "r") as f:
        return json.load(f)


def base_strength(team: dict) -> float:
    """2.1 球队基础实力 (0-100)"""
    # FIFA排名分 (0-8 → 0-100)
    fifa = max(0, (49 - team["fifa_rank"]) / 48) * 100 * 0.40

    # Elo评分 (0-100)
    elo_min, elo_max = 1400, 2000
    elo = max(0, min(100, (team["elo_rating"] - elo_min) / (elo_max - elo_min) * 100)) * 0.20

    # 身价分 (0-100)
    mv = min(100, team["market_value_eur"] / 1_200_000_000 * 100) * 0.25

    # 大赛经验分 (0-100)
    exp = min(100, team["tournament_exp"] / 18 * 100) * 0.10

    # 五大联赛主力 (0-100)
    t5 = team["top5_league_starters"] / 11 * 100 * 0.05

    return fifa + elo + mv + exp + t5


def recent_form(team: dict) -> float:
    """2.2 近10场状态评估 (0-100)"""
    r10 = team["recent_10"]
    r5 = team["recent_5"]

    # 战绩面板
    win_rate_10 = r10["w"] / 10
    win_rate_5 = r5["w"] / 5

    # P1: 爆发性状态检测 —— 近5场显著优于近10场时加大近5场权重
    if win_rate_5 > win_rate_10 + 0.2:
        weight_5 = 0.75   # 爆发状态
        weight_10 = 0.25
    elif win_rate_5 < win_rate_10 - 0.2:
        weight_5 = 0.50   # 下滑状态(仍保持一定权重)
        weight_10 = 0.50
    else:
        weight_5 = 0.60   # 正常
        weight_10 = 0.40

    record_score = (win_rate_10 * weight_10 + win_rate_5 * weight_5) * 100

    # WARO 对手质量修正 (修正后的公式)
    opp_rank_10 = r10.get("opponent_avg_rank", 25)
    opp_rank_5 = r5.get("opponent_avg_rank", 25)
    difficulty_10 = 1 + (48 - opp_rank_10) / 48
    difficulty_5 = 1 + (48 - opp_rank_5) / 48
    avg_difficulty = (difficulty_10 + difficulty_5) / 2

    # 趋势修正 + 交叉验证
    if abs(opp_rank_5 - opp_rank_10) <= opp_rank_10 * 0.3:
        if win_rate_5 > win_rate_10:
            trend = 1.15
        elif win_rate_5 < win_rate_10:
            trend = 0.85
        else:
            trend = 1.0
    else:
        trend = 1.0

    waro_score = record_score * avg_difficulty * trend

    # 攻防效率
    goals_10_per_game = r10["gf"] / 10
    goals_5_per_game = r5["gf"] / 5
    conceded_5_per_game = r5["ga"] / 5
    clean_sheet_rate_10 = max(0, (10 - r10["ga"]) / 10) if r10["ga"] < 10 else 0.1
    clean_sheet_rate_5 = max(0, (5 - r5["ga"]) / 5) if r5["ga"] < 5 else 0.1

    attack_ratio = goals_5_per_game / max(0.1, goals_10_per_game)
    defense_ratio = clean_sheet_rate_5 / max(0.1, clean_sheet_rate_10)
    net_goal_per_game = goals_5_per_game - conceded_5_per_game

    attack_score = 2 if attack_ratio > 1.2 else (1 if attack_ratio >= 0.8 else 0)
    defense_score = 2 if defense_ratio > 1.2 else (1 if defense_ratio >= 0.8 else 0)
    net_score = 2 if net_goal_per_game > 1.5 else (1 if net_goal_per_game >= 0.5 else 0)

    eff_score = (attack_score + defense_score + net_score) / 6 * 100

    # 关键球员追踪
    kp = team.get("key_players", {})
    kp_bonus = 0
    for role_key in ["striker", "midfielder", "goalkeeper"]:
        if role_key in kp:
            player = kp[role_key]
            recent_k = player.get("recent_goal_rate") or player.get("recent_key_pass") or player.get("recent_save_pct")
            season_k = player.get("season_avg") or 0.5
            if recent_k and season_k and season_k > 0:
                ratio = recent_k / season_k
                if ratio > 1.2:
                    kp_bonus += 1
                elif ratio < 0.8:
                    kp_bonus -= 1
    kp_bonus = max(-2, min(2, kp_bonus))

    # 综合: 战绩40% + WARO 30% + 效率20% + 球员10%
    form_final = waro_score * 0.40 + record_score * avg_difficulty * 0.30 + eff_score * 0.20 + (50 + kp_bonus * 10) * 0.10
    return min(100, max(0, form_final))


def injury_penalty(team_id: str) -> float:
    """2.3 伤病折损 (返回扣分值, 0=无伤病)"""
    injuries = load_json("injuries.json")
    if team_id not in injuries:
        return 0.0

    penalty = 0.0
    for inj in injuries[team_id]:
        if inj["status"] in ("out", "out_retired"):
            penalty += 1.0 * inj["irreplaceability"]
        elif inj["status"] == "doubtful":
            penalty += 0.5 * inj["irreplaceability"]

    return min(10, penalty)


def hard_data_score(team_id: str, opponent_id: str = None) -> dict:
    """硬数据层总分 (0-100), opponent_id传入时计算对位加成"""
    teams = load_json("teams.json")
    team = teams.get(team_id)
    if not team:
        return {"score": 50, "detail": {"base": 50, "form": 50, "injury_penalty": 0}}

    base = base_strength(team)
    form = recent_form(team)
    injury = injury_penalty(team_id)

    # 球员+战术对位修正
    matchup_bonus = 0
    if opponent_id:
        try:
            from .matchup import full_matchup_score
            mu = full_matchup_score(team_id, opponent_id)
            matchup_bonus = mu["combined"]  # 可正可负
        except Exception:
            pass

    # 归一化每项到0-100, 加权: 基础40% + 状态40% + 伤病20%
    # 伤病转化为扣分后的分数: 满分100 - injury*10
    injury_score = max(0, 100 - injury * 10)

    # 基础:40% 状态:35% 伤病:15% 对位:10%
    final = base * 0.40 + form * 0.35 + injury_score * 0.15 + (50 + matchup_bonus * 5) * 0.10
    return {
        "score": round(final, 1),
        "detail": {
            "base_strength": round(base, 1),
            "recent_form": round(form, 1),
            "injury_penalty": round(injury, 1),
            "injury_score": round(injury_score, 1),
            "matchup_bonus": round(matchup_bonus, 1)
        }
    }


def team_defense_score(team_id: str) -> float:
    """提取球队防守分 (用于对手压制修正)"""
    teams = load_json("teams.json")
    team = teams.get(team_id)
    if not team:
        return 50

    r5 = team["recent_5"]
    conceded_rate = 1 - min(1, r5["ga"] / 10)  # 失球越少分越高

    # 伤病影响防线
    injuries = load_json("injuries.json")
    defense_injury_penalty = 0
    if team_id in injuries:
        for inj in injuries[team_id]:
            if inj.get("role") == "defense_leader" and inj["status"] in ("out", "out_retired"):
                defense_injury_penalty += 1.5
            elif inj.get("role") == "defense_leader" and inj["status"] == "doubtful":
                defense_injury_penalty += 0.75

    return min(100, max(10, conceded_rate * 100 - defense_injury_penalty * 10))
