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
    """2.3 伤病折损 (含连坐惩罚: 同位置≥2人缺阵 → ×1.5)"""
    injuries = load_json("injuries.json")
    if team_id not in injuries:
        return 0.0

    penalty = 0.0
    pos_count = {}  # Track positions
    for inj in injuries[team_id]:
        if inj["status"] in ("out", "out_retired"):
            penalty += 1.0 * inj["irreplaceability"]
            pos = inj.get("position", "unknown")
            pos_count[pos] = pos_count.get(pos, 0) + 1
        elif inj["status"] == "doubtful":
            penalty += 0.5 * inj["irreplaceability"]

    # 连坐: 同位置≥2人缺阵 → 协同效应
    chain_penalty = 0.0
    for pos, count in pos_count.items():
        if count >= 3:
            chain_penalty += 2.0  # 整条线瘫痪 (巴西锋线)
        elif count >= 2:
            chain_penalty += 1.0  # 双核缺阵 (日本中场)

    penalty += chain_penalty
    return min(12, penalty)


def tournament_momentum(team_id: str) -> float:
    """2.4 赛事动量 — 全部已赛正赛表现(含对手强度+球员状态) (-5~+5)"""
    results = load_json("results.json")
    teams = load_json("teams.json")
    team = teams.get(team_id, {})
    fifa_rank = team.get("fifa_rank", 48)

    total_bonus = 0.0
    games_found = 0

    for m in results["matches"]:
        if m["home"] == team_id:
            gf, ga = map(int, m["score"].split("-"))
            opp_id = m["away"]
        elif m["away"] == team_id:
            ga, gf = map(int, m["score"].split("-"))
            opp_id = m["home"]
        else:
            continue

        games_found += 1
        gd = gf - ga
        opp = teams.get(opp_id, {})
        opp_rank = opp.get("fifa_rank", 48)

        # 对手强度系数 (基于Elo, 更准确反映当下实力)
        opp_elo = opp.get("elo_rating", 1500)
        if opp_elo >= 1900:
            opp_quality = 1.5   # 顶级 (Elo≥1900)
        elif opp_elo >= 1700:
            opp_quality = 1.2   # 强队 (Elo 1700-1900, 含瑞典等)
        elif opp_elo >= 1550:
            opp_quality = 1.0   # 中游
        else:
            opp_quality = 0.7   # 弱队

        # 基础动量（对手强度加权）
        if gd >= 3:
            bonus = (3 + (gd - 3) * 0.5) * opp_quality
        elif gd >= 1:
            bonus = (1 + gd * 0.5) * opp_quality
        elif gd == 0:
            if fifa_rank <= 15 and opp_rank >= 30:
                bonus = -1.5
            elif fifa_rank >= 35 and opp_rank <= 15:
                bonus = 3.0
            elif fifa_rank >= 40:
                bonus = 1.5
            elif fifa_rank <= 20:
                bonus = -1.0
            else:
                bonus = 0
        elif gd >= -1:
            bonus = -1.5 if opp_rank >= 35 else -1.0
        else:
            bonus = max(-5, (-3 + (gd + 3) * 0.5) * opp_quality)

        # 最近比赛权重更高 (exp decay: 最近×1.0, 往前×0.7)
        weight = 1.0 if games_found == 1 else 0.7
        total_bonus += bonus * weight

    if games_found == 0:
        return 0.0

    # 均值 + 边界
    return max(-5.0, min(5.0, total_bonus / max(1, games_found)))

    # 进球/零封加成
    if gf >= 3:
        bonus += 0.5
    if ga == 0:
        bonus += 0.5

    # === 关键球员状态修正 ===
    kp = team.get("key_players", {})
    player_boost = 0.0

    # 前锋状态: recent_goal_rate vs season_avg
    striker = kp.get("striker", {})
    if striker:
        recent = striker.get("recent_goal_rate", 0)
        season = striker.get("season_avg", 0.5)
        if season > 0 and recent > 0:
            ratio = recent / season
            if ratio >= 2.0:
                player_boost += 1.5  # 爆发 (Messi帽子/Mbappe双响)
            elif ratio >= 1.5:
                player_boost += 0.8  # 状态佳
            elif ratio <= 0.2:
                player_boost -= 1.0  # 低迷 (CR7 0射正)

    # 门将状态: recent vs season save rate
    gk = kp.get("goalkeeper", {})
    if gk:
        recent_sv = gk.get("recent_save_pct", 0)
        season_sv = gk.get("season_avg", 0.7)
        if season_sv > 0 and recent_sv > 0:
            if recent_sv >= 0.95:
                player_boost += 1.0  # 神扑型
            elif recent_sv <= 0.5:
                player_boost -= 0.5  # 漏勺

    bonus += player_boost

    return round(min(5, max(-5, bonus)), 1)


def hard_data_score(team_id: str, opponent_id: str = None) -> dict:
    """硬数据层总分 (0-100), opponent_id传入时计算对位加成"""
    teams = load_json("teams.json")
    team = teams.get(team_id)
    if not team:
        return {"score": 50, "detail": {"base": 50, "form": 50, "injury_penalty": 0}}

    base = base_strength(team)
    form = recent_form(team)
    injury = injury_penalty(team_id)
    momentum = tournament_momentum(team_id)  # R1正赛动量

    # 轮次态势修正 (v2.0)
    round_bonus = 0
    if opponent_id:
        try:
            from .round_factor import round_momentum_adjust
            round_bonus = round_momentum_adjust(team_id, opponent_id)
        except: pass

    # 球员+战术对位修正
    matchup_bonus = 0
    if opponent_id:
        try:
            from .matchup import full_matchup_score
            mu = full_matchup_score(team_id, opponent_id)
            matchup_bonus = mu["combined"]  # 可正可负
        except Exception:
            pass

    # 归一化: 基础+状态+伤病+赛事动量+轮次+对位
    injury_score = max(0, 100 - injury * 10)
    momentum_score = 50 + momentum * 10  # 动量-5~+5 → 0~100
    round_score = 50 + round_bonus * 3   # 轮次动力±3 → 0~100

    # [v3.0] 基础:36% 状态:31% 伤病:10% 动量:6% 轮次:8% 对位:9%
    final = (base * 0.36 + form * 0.31 + injury_score * 0.10 +
            momentum_score * 0.06 + round_score * 0.08 + (50 + matchup_bonus * 5) * 0.09)
    return {
        "score": round(final, 1),
        "detail": {
            "base_strength": round(base, 1),
            "recent_form": round(form, 1),
            "injury_penalty": round(injury, 1),
            "injury_score": round(injury_score, 1),
            "tournament_momentum": momentum,
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


def defensive_resilience(team_id: str) -> float:
    """防守韧性因子 (0-100): 弱队摆大巴能力 → 提升平局概率"""
    teams = load_json("teams.json")
    team = teams.get(team_id)
    if not team:
        return 50
    r5 = team["recent_5"]
    conceded = r5["ga"]
    # 零封率: 完全没失球的场次比例
    cs_rate = max(0, (5 - conceded) / 5) if conceded <= 5 else 0
    # 场均失球越低, 韧性越高
    conceded_per_game = conceded / 5
    # 综合: 零封率60% + 失球少40%
    score = cs_rate * 60 + max(0, (1 - conceded_per_game / 3) * 40)
    return round(min(100, max(0, score)), 1)


def attacking_conversion(team_id: str) -> float:
    """进攻转化率因子 (0-100): 把握机会能力 → 降低被误判平局"""
    teams = load_json("teams.json")
    team = teams.get(team_id)
    if not team:
        return 50
    r5 = team["recent_5"]
    gf = r5["gf"]
    ga = r5["ga"]
    gpg = gf / 5  # 场均进球
    net = (gf - ga) / 5  # 场均净胜
    # 进球能力50% + 净胜球50%
    score = min(2.0, gpg) / 2.0 * 50 + max(-1.0, min(3.0, net)) / 2.5 * 50 + 25
    return round(min(100, max(0, score)), 1)


# ============================================================
# P1: xG代理 + 比赛风格 + 球员可用性 + 体能耗损
# ============================================================

def xg_proxy(team_id: str) -> dict:
    """xG代理: 从近5场进球/失球估算进攻和防守xG (Fox xG备用: data/fox_xg.json)"""
    teams = load_json("teams.json")
    team = teams.get(team_id)
    if not team:
        return {"offensive": 1.5, "defensive": 1.5, "net": 0.0}
    r5 = team["recent_5"]
    gf, ga = r5["gf"], r5["ga"]
    off_xg = gf / 5
    def_xg = ga / 5
    net = off_xg - def_xg
    return {
        "offensive": round(off_xg, 2),
        "defensive": round(def_xg, 2),
        "net": round(net, 2)
    }


def match_style(team_id: str) -> str:
    """比赛风格分类: 基于近5场攻防数据"""
    teams = load_json("teams.json")
    team = teams.get(team_id)
    if not team:
        return "balanced"
    r5 = team["recent_5"]
    gpg = r5["gf"] / 5
    cpg = r5["ga"] / 5
    if gpg > 2.0 and cpg < 0.8:
        return "dominant"     # 攻防俱佳
    if gpg > 2.0:
        return "attacking"     # 重攻轻守
    if gpg < 1.5 and cpg < 0.8:
        return "defensive"     # 摆大巴
    if 1.0 <= gpg < 2.0 and cpg >= 0.8:
        return "counter"       # 反击型
    return "balanced"


def style_matchup_bonus(home_style: str, away_style: str) -> float:
    """风格相克加成 → 正数利好主队"""
    matrix = {
        ("counter", "dominant"): 2.0,     # 反击克控球
        ("counter", "attacking"): 1.5,
        ("defensive", "attacking"): 1.5,  # 大巴克制进攻
        ("defensive", "dominant"): 1.0,
        ("dominant", "defensive"): 1.5,   # 控球破大巴
        ("attacking", "defensive"): 1.0,
        ("attacking", "counter"): -1.0,   # 进攻被反击克制
        ("dominant", "counter"): -1.5,
    }
    return matrix.get((home_style, away_style), 0.0)


def player_availability_impact(team_id: str) -> float:
    """关键球员缺阵影响 (0-10分惩罚)"""
    injuries = load_json("injuries.json")
    teams = load_json("teams.json")
    team = teams.get(team_id)
    if not team or team_id not in injuries:
        return 0.0

    penalty = 0.0
    kp = team.get("key_players", {})
    for inj in injuries[team_id]:
        if inj["status"] not in ("out", "out_retired", "doubtful"):
            continue
        player_name = inj["player"]
        irreplaceability = inj.get("irreplaceability", 0.5)
        # 检查是否关键球员
        is_key = False
        for role, pinfo in kp.items():
            if isinstance(pinfo, dict) and pinfo.get("name", "") == player_name:
                is_key = True
                break
        weight = 2.0 if is_key else 0.5
        mult = 1.0 if inj["status"] in ("out", "out_retired") else 0.3
        penalty += irreplaceability * weight * mult
    return round(min(10, penalty), 1)


def fatigue_penalty(team_id: str, match_date: str = None) -> float:
    """体能惩罚: 基于距上一场比赛天数 (0-5分)"""
    if not match_date:
        return 0.0
    from datetime import date
    results = load_json("results.json")
    # 找到该队最近一场比赛
    last_date = None
    for m in sorted(results["matches"], key=lambda x: x["date"], reverse=True):
        if m["home"] == team_id or m["away"] == team_id:
            last_date = m["date"]
            break
    if not last_date:
        return 0.0
    try:
        md_parts = match_date.split("/")
        ld_parts = last_date.split("/")
        md = date(2026, int(md_parts[0]), int(md_parts[1]))
        ld = date(2026, int(ld_parts[0]), int(ld_parts[1]))
        days = (md - ld).days
        if days <= 2:
            return 4.0  # 严重疲劳
        elif days == 3:
            return 2.0  # 中度疲劳
        elif days == 4:
            return 1.0  # 轻微疲劳
        else:
            return 0.0
    except:
        return 0.0
