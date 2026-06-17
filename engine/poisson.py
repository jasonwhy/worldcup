"""
泊松比分预测引擎 —— 系统最终输出 v2.1
- 总分 → xG预期进球
- 泊松概率矩阵 (0-8球)
- 八卦冷门修正
- 盘口约束校正
- 首轮平局加成 + 温差修正 [P0]
- 屠杀因子 + 大比分过滤优化 [P1]
- 胜平负% + 最可能比分Top3
"""
import math
from typing import Tuple, List, Dict


# 世界杯历史场均进球中位数
BASELINE_XG = 1.35

# P0: 平局加成系数
DRAW_BONUS = {
    "group_1": 1.6,   # 首轮：保守试探+弱队摆大巴
    "group_2": 1.3,   # 次轮：部分球队需要抢分
    "group_3": 1.0,   # 末轮：恢复正常
    "ko": 0.8,        # 淘汰赛：必须分胜负
}


def score_to_xg(total_score: float, defense_score: float = 50,
                slaughter_factor: float = 1.0) -> float:
    """
    总分 → 预期进球
    total_score: 球队在该场比赛中的综合评分(0-100)
    defense_score: 对手防守分(0-100)
    slaughter_factor: 屠杀因子 [P1] 强队攻击力远超弱队防守时>1.0
    """
    # 进攻优势系数
    attack_factor = (total_score - 50) / 50
    xg = BASELINE_XG * (1 + attack_factor)

    # 对手防守压制
    defense_factor = 1 - (defense_score - 50) / 200
    xg = xg * defense_factor

    # P1: 屠杀因子
    xg = xg * slaughter_factor

    return max(0.2, xg)


def poisson_prob(lmbda: float, k: int) -> float:
    """泊松概率 P(X=k)"""
    if lmbda <= 0:
        return 1.0 if k == 0 else 0.0
    return (lmbda ** k * math.exp(-lmbda)) / math.factorial(k)


def build_prob_matrix(xg_a: float, xg_b: float, max_goals: int = 8,
                     match_round: str = "group_1", temperature: float = 25.0,
                     score_gap: float = 0.0) -> Dict:
    """
    构建完整概率矩阵
    match_round: group_1/group_2/group_3/ko [P0]
    temperature: 比赛温度(°C) [P0]
    score_gap: 两队总分差 [P1] 用于判断是否放宽大比分过滤
    返回: {probs, win%, draw%, lose%, top_scores}
    """
    # 生成0-max_goals球的概率分布
    prob_a = {k: poisson_prob(xg_a, k) for k in range(max_goals + 1)}
    prob_b = {k: poisson_prob(xg_b, k) for k in range(max_goals + 1)}

    # 全概率矩阵
    all_probs = []
    win_prob = 0
    draw_prob = 0
    lose_prob = 0

    for a in range(max_goals + 1):
        for b in range(max_goals + 1):
            p = prob_a[a] * prob_b[b]

            # P1优化: 大比分过滤从0.5放宽到0.7, 且差距>30不应用
            if score_gap > 30:
                pass  # 屠杀可能, 不过滤
            elif (a >= 4 and b >= 4) or (a == 0 and b >= 6) or (b == 0 and a >= 6):
                p *= 0.7

            all_probs.append({
                "score": f"{a}-{b}",
                "home_goals": a,
                "away_goals": b,
                "probability": round(p, 6)
            })

            if a > b:
                win_prob += p
            elif a == b:
                draw_prob += p
            else:
                lose_prob += p

    # 归一化 (在平局加成之前)
    total = win_prob + draw_prob + lose_prob
    if total > 0:
        win_prob /= total
        draw_prob /= total
        lose_prob /= total

    # P0: 首轮平局加成 (带保护: 原胜率>50%时强度减半, 避免将明确胜负拖成平局)
    draw_bonus = DRAW_BONUS.get(match_round, 1.0)
    # P0: 温差修正 (>32°C提升平局概率)
    temp_bonus = 1.0
    if temperature > 32:
        temp_bonus = 1.3
    elif temperature > 25:
        temp_bonus = 1.1

    effective_draw_bonus = draw_bonus * temp_bonus
    if effective_draw_bonus != 1.0:
        # 保护: 原胜率越高, 平局加成越弱
        max_original = max(win_prob, draw_prob, lose_prob)
        if max_original > 0.50:
            strength = 0.5   # 一方明显占优, 平局加成减半
            # [P2] 首轮中差距例外: 48队赛制下第三名可出线, 首轮Δ12-22出平率异常高
            if match_round == "group_1" and 12 <= score_gap <= 22:
                strength = 0.65
        elif max_original > 0.40:
            strength = 0.75  # 略占优
        else:
            strength = 1.0   # 势均力敌, 完整加成

        effective_draw_bonus = 1.0 + (effective_draw_bonus - 1.0) * strength
    if effective_draw_bonus != 1.0:
        draw_prob *= effective_draw_bonus
        # 从胜/负中各扣一半
        excess = (draw_prob * effective_draw_bonus - draw_prob) / effective_draw_bonus
        # 实际上重新归一化更干净
        # 平局放大后归一化
        win_prob = win_prob
        draw_prob = draw_prob * effective_draw_bonus
        lose_prob = lose_prob
        total2 = win_prob + draw_prob + lose_prob
        if total2 > 0:
            win_prob /= total2
            draw_prob /= total2
            lose_prob /= total2

    # P0: 实力悬殊-平局悖论 (强队围攻无果模式)
    # 在调用层处理, 此处根据score_gap做微调
    if score_gap > 25:
        # 大差距下平局概率微增（强队久攻不下）
        draw_paradox_shift = min(0.03, draw_prob * 0.15)
        win_prob -= draw_paradox_shift * 0.7
        draw_prob += draw_paradox_shift
        lose_prob -= draw_paradox_shift * 0.3

    # 最可能比分 Top-5
    all_probs.sort(key=lambda x: x["probability"], reverse=True)

    return {
        "xg_home": round(xg_a, 2),
        "xg_away": round(xg_b, 2),
        "total_xg": round(xg_a + xg_b, 2),
        "win_pct": round(win_prob * 100, 1),
        "draw_pct": round(draw_prob * 100, 1),
        "lose_pct": round(lose_prob * 100, 1),
        "top_scores": all_probs[:5]
    }


def apply_gossip_shift(result: Dict, home_gossip_deduction: float, away_gossip_deduction: float) -> Dict:
    """
    八卦冷门修正
    热门方八卦扣分远大于冷门方 → 冷门概率上升
    """
    gap = abs(home_gossip_deduction - away_gossip_deduction)

    if gap >= 10:
        upset_shift = 8
        draw_shift = 2
    elif gap >= 5:
        upset_shift = 5
        draw_shift = 1
    elif gap >= 2:
        upset_shift = 2
        draw_shift = 1
    else:
        return result

    # 确定谁是热门
    if result["win_pct"] > result["lose_pct"]:
        # 主队是热门
        if home_gossip_deduction > away_gossip_deduction:
            result["win_pct"] -= upset_shift
            result["lose_pct"] += upset_shift - draw_shift
            result["draw_pct"] += draw_shift
    else:
        if away_gossip_deduction > home_gossip_deduction:
            result["lose_pct"] -= upset_shift
            result["win_pct"] += upset_shift - draw_shift
            result["draw_pct"] += draw_shift

    # 边界保护
    result["win_pct"] = max(5, min(90, result["win_pct"]))
    result["draw_pct"] = max(5, min(40, result["draw_pct"]))
    result["lose_pct"] = max(5, min(90, result["lose_pct"]))

    # 归一化
    total = result["win_pct"] + result["draw_pct"] + result["lose_pct"]
    result["win_pct"] = round(result["win_pct"] / total * 100, 1)
    result["draw_pct"] = round(result["draw_pct"] / total * 100, 1)
    result["lose_pct"] = round(result["lose_pct"] / total * 100, 1)

    return result


def apply_handicap_constraint(result: Dict, market_total_goals: float = None) -> Dict:
    """
    盘口约束校正
    如果大小球盘口与模型预测差>1球 → 以盘口为准等比例缩放
    """
    if market_total_goals is None:
        return result

    model_total = result["total_xg"]
    if abs(model_total - market_total_goals) > 1.0:
        scale = market_total_goals / max(0.5, model_total)
        new_xg_home = result["xg_home"] * scale
        new_xg_away = result["xg_away"] * scale

        # 用新xG重新计算
        new_result = build_prob_matrix(new_xg_home, new_xg_away)
        new_result["handicap_adjusted"] = True
        new_result["original_xg"] = f"{result['xg_home']}-{result['xg_away']}"
        return new_result

    return result


def predict_match(home_score: float, away_score: float,
                  home_defense: float = 50, away_defense: float = 50,
                  home_gossip_deduction: float = 0, away_gossip_deduction: float = 0,
                  market_total_goals: float = None,
                  match_round: str = "group_1", temperature: float = 25.0,
                  home_goals_per_game: float = 1.5, away_goals_per_game: float = 1.5,
                  home_conceded: float = 1.5, away_conceded: float = 1.5) -> Dict:
    """
    完整比赛预测 [v2.1]
    match_round: group_1/group_2/group_3/ko [P0]
    temperature: 比赛温度(°C) [P0]
    *_goals_per_game/conceded: 近5场攻防数据 [P1屠杀因子]
    返回: {xg, win/draw/lose%, top_scores, cold_alert}
    """
    score_gap = abs(home_score - away_score)

    # P1: 屠杀因子 —— 强队攻击力远超弱队防守时放大xG
    home_slaughter = 1.0
    away_slaughter = 1.0
    if home_score > away_score:
        if home_goals_per_game > 2.5 and away_conceded > 2.0:
            home_slaughter = 1.4
        elif home_goals_per_game > 2.0 and away_conceded > 1.5:
            home_slaughter = 1.2
    else:
        if away_goals_per_game > 2.5 and home_conceded > 2.0:
            away_slaughter = 1.4
        elif away_goals_per_game > 2.0 and home_conceded > 1.5:
            away_slaughter = 1.2

    xg_home = score_to_xg(home_score, away_defense, home_slaughter)
    xg_away = score_to_xg(away_score, home_defense, away_slaughter)

    result = build_prob_matrix(xg_home, xg_away,
                               match_round=match_round,
                               temperature=temperature,
                               score_gap=score_gap)

    # 八卦修正
    result = apply_gossip_shift(result, home_gossip_deduction, away_gossip_deduction)

    # 盘口约束
    if market_total_goals:
        result = apply_handicap_constraint(result, market_total_goals)

    # 冷门预警
    if result["lose_pct"] > 30 and home_score > away_score + 5:
        cold_alert = "★★★ 高"
    elif result["lose_pct"] > 20 and home_score > away_score:
        cold_alert = "★★☆ 中"
    elif result["lose_pct"] > 15:
        cold_alert = "★☆☆ 低"
    else:
        cold_alert = "无"

    result["cold_alert"] = cold_alert
    return result
