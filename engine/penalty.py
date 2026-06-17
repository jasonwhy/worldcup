"""淘汰赛点球大战模块"""
import json, math
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"

# 默认点球数据（基于历史统计）
DEFAULT_PEN_SAVE_RATE = 0.18
DEFAULT_PEN_SCORE_RATE = 0.78


def penalty_shootout_prob(team_a: str, team_b: str) -> dict:
    """
    计算点球大战胜率
    基于: 门将扑点率 + 罚球手命中率 + 历史点球胜率
    """
    teams = json.load(open(DATA / "teams.json"))
    a = teams.get(team_a, {})
    b = teams.get(team_b, {})

    # 门将扑点率
    gk_a = a.get("key_players", {}).get("goalkeeper", {})
    gk_b = b.get("key_players", {}).get("goalkeeper", {})
    save_a = gk_a.get("recent_save_pct", 0) * 0.25 or DEFAULT_PEN_SAVE_RATE
    save_b = gk_b.get("recent_save_pct", 0) * 0.25 or DEFAULT_PEN_SAVE_RATE

    # 罚球手（取射手+中场近5场进球率代表点球能力）
    st_a = a.get("key_players", {}).get("striker", {})
    st_b = b.get("key_players", {}).get("striker", {})
    mid_a = a.get("key_players", {}).get("midfielder", {})
    mid_b = b.get("key_players", {}).get("midfielder", {})

    score_a = (st_a.get("recent_goal_rate", DEFAULT_PEN_SCORE_RATE) + mid_a.get("recent_key_pass", 1.5) / 4) / 2
    score_b = (st_b.get("recent_goal_rate", DEFAULT_PEN_SCORE_RATE) + mid_b.get("recent_key_pass", 1.5) / 4) / 2
    score_a = min(0.95, max(0.60, score_a))
    score_b = min(0.95, max(0.60, score_b))

    # 门将扑点 + 对手罚球 = 预期丢球率
    a_defense = save_a + (1 - score_b) * 0.3
    b_defense = save_b + (1 - score_a) * 0.3

    # 转换为胜率（门将好的球队有优势）
    a_win = 0.50 + (a_defense - b_defense) * 0.8 + (score_a - score_b) * 0.5
    a_win = min(0.75, max(0.25, a_win))
    b_win = 1.0 - a_win

    return {
        "team_a": a.get("name", team_a), "team_b": b.get("name", team_b),
        "a_win_pct": round(a_win * 100, 1), "b_win_pct": round(b_win * 100, 1),
        "a_pen_ability": round(score_a, 2), "b_pen_ability": round(score_b, 2),
        "a_gk_save_rate": round(save_a, 2), "b_gk_save_rate": round(save_b, 2),
    }


def knockout_match(home_score: float, away_score: float, home_id: str, away_id: str,
                   home_gossip: float = 100, away_gossip: float = 100) -> dict:
    """
    淘汰赛完整预测（90分钟+加时+点球）
    """
    from .poisson import predict_match

    # 90分钟常规时间预测（淘汰赛模式）
    result_90 = predict_match(home_score, away_score, match_round="ko",
                              temperature=25.0, home_gossip_deduction=100-home_gossip,
                              away_gossip_deduction=100-away_gossip)

    # 如果平局 → 加时 → 点球
    draw_pct = result_90["draw_pct"] / 100

    # 加时赛（双方xG*0.3）
    extra_xg_h = result_90["xg_home"] * 0.3
    extra_xg_a = result_90["xg_away"] * 0.3
    extra = predict_match.__wrapped__(extra_xg_h, extra_xg_a) if False else None

    # 简化: 加时赛进球概率约30%常规时间
    extra_score_prob = 0.30
    extra_draw_prob = 0.70

    # 点球大战
    pk = penalty_shootout_prob(home_id, away_id)

    # 综合胜率 = 90分钟胜 + (90分钟平 × (加时胜 + 加时平 × 点球胜))
    home_advance = result_90["win_pct"] / 100 + draw_pct * ((1 - extra_draw_prob) * 0.5 + extra_draw_prob * pk["a_win_pct"] / 100)
    away_advance = 1 - home_advance

    return {
        "90min": result_90,
        "extra_time_prob": round(draw_pct * 100, 1),
        "penalty_shootout": pk,
        "home_advance_pct": round(home_advance * 100, 1),
        "away_advance_pct": round(away_advance * 100, 1),
    }
