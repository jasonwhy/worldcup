"""
泊松比分预测引擎 —— 系统最终输出 v3.0
- 总分 → xG预期进球
- 泊松概率矩阵 (0-8球)
- 八卦冷门修正
- 盘口约束校正
- 平局加成 + 温差修正 [P0]
- 屠杀因子 + 大比分过滤优化 [P1]
- 胜平负% + 最可能比分Top3
- [v3.0] 校准文件隔离, 全局变量不再被直接修改
"""
import math
import json
from pathlib import Path
from typing import Tuple, List, Dict

DATA_DIR = Path(__file__).parent.parent / "data"

# 世界杯历史场均进球中位数
BASELINE_XG = 1.35

# P0: 平局加成系数 (v3.0: 审计校准, 对标实际平局率30%)
DRAW_BONUS = {
    "group_1": 1.6,   # 首轮 (降0.4: 模型平局率33%→对标实际30%)
    "group_2": 1.3,   # 次轮 (降0.3)
    "group_3": 1.0,   # 末轮：恢复正常
    "ko": 2.5,        # 淘汰赛90min平局率更高(4场50%): 保守+加时安全网
}

# [v3.0] 加载校准文件 (calibrator写入, 引擎读取, 不直接改全局变量)
_calib_file = DATA_DIR / "calibration.json"
if _calib_file.exists():
    try:
        _calib = json.load(open(_calib_file))
        if "draw_bonus" in _calib:
            DRAW_BONUS.update(_calib["draw_bonus"])
        if "baseline_xg" in _calib:
            BASELINE_XG = _calib["baseline_xg"]
    except:
        pass


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

    # P3: 屠杀因子 (大差距时放大)
    if slaughter_factor >= 1.4:
        xg = xg * slaughter_factor * 1.2  # 屠杀加成额外20%
    else:
        xg = xg * slaughter_factor

    return max(0.2, xg)


def poisson_prob(lmbda: float, k: int) -> float:
    """泊松概率 P(X=k)"""
    if lmbda <= 0:
        return 1.0 if k == 0 else 0.0
    return (lmbda ** k * math.exp(-lmbda)) / math.factorial(k)


def neg_binom_prob(lmbda: float, k: int, dispersion: float = 0.3) -> float:
    """
    负二项分布(泊松-伽马混合): 比泊松更分散, 更好拟合足球比分的超额方差
    dispersion: 0=泊松, 越大越分散 (推荐0.2-0.4)
    """
    if lmbda <= 0:
        return 1.0 if k == 0 else 0.0
    if dispersion <= 0.01:
        return poisson_prob(lmbda, k)
    # Gamma-Poisson (Negative Binomial)
    r = 1.0 / dispersion  # 形状参数
    p = r / (r + lmbda)
    # NB(k; r, p) = C(k+r-1, k) * p^r * (1-p)^k
    from math import lgamma
    log_prob = lgamma(k + r) - lgamma(r) - lgamma(k + 1) + r * math.log(p) + k * math.log(1 - p)
    return math.exp(log_prob)


def dixon_coles_adjust(prob_matrix: dict, xg_home: float, xg_away: float,
                       rho: float = -0.08) -> dict:
    """
    Dixon-Coles低比分修正: 调整0-0/1-0/0-1/1-1的实际概率

    标准泊松高估低比分平局概率, Dixon-Coles用ρ参数修正
    ρ < 0: 降低0-0/1-1概率 (足球实际比泊松独立假设更少低分平局)

    论文: Dixon & Coles (1997) "Modelling Association Football Scores"
    """
    adjusted = dict(prob_matrix)
    total_adjustment = 0.0

    # 只修正低比分 (0-0, 0-1, 1-0, 1-1)
    for (i, j) in [(0, 0), (0, 1), (1, 0), (1, 1)]:
        if (i, j) not in prob_matrix:
            continue
        orig = prob_matrix[(i, j)]
        # Dixon-Coles: λ_ij = 1 + ρ * (指标)
        if i == j:
            # 平局修正: 通常降低
            factor = 1.0 + rho * 0.5
        else:
            # 1球差分修正: 通常微升
            factor = 1.0 + rho * 0.3
        adjusted[(i, j)] = orig * factor
        total_adjustment += orig * factor - orig

    # 将修正量均匀分布到其他比分
    if abs(total_adjustment) > 0.0001:
        other_count = len(adjusted) - 4
        if other_count > 0:
            per_other = -total_adjustment / other_count
            for key in adjusted:
                if key not in [(0, 0), (0, 1), (1, 0), (1, 1)]:
                    adjusted[key] = max(0.0, adjusted[key] + per_other)

    # 重归一化
    total = sum(adjusted.values())
    if total > 0:
        for key in adjusted:
            adjusted[key] /= total

    return adjusted


def build_prob_matrix(xg_a: float, xg_b: float, max_goals: int = 8,
                     match_round: str = "group_1", temperature: float = 25.0,
                     score_gap: float = 0.0, team_draw_factor: float = 1.0) -> Dict:
    """
    构建完整概率矩阵
    team_draw_factor: [v3.0 P2] 两队历史平局倾向因子 (1.0=平均, >1=偏好平局)
    match_round: group_1/group_2/group_3/ko [P0]
    temperature: 比赛温度(°C) [P0]
    score_gap: 两队总分差 [P1] 用于判断是否放宽大比分过滤
    返回: {probs, win%, draw%, lose%, top_scores}
    """
    # [P3屠杀模式] 大差距时扩展比分范围, 不压缩强队进球
    slaughter_mode = score_gap > 25  # 屠杀阈值
    if score_gap > 30:
        actual_max = 10
    elif score_gap > 25:
        actual_max = 9
    else:
        actual_max = max_goals

    # [v3.5] 负二项分布: 比泊松更分散, 更好拟合足球超额方差
    # dispersion: 基于score_gap调节 (接近比赛用低分散, 碾压局用高分散)
    use_dispersion = 0.25 if score_gap > 20 else (0.18 if score_gap > 10 else 0.12)
    prob_a = {k: neg_binom_prob(xg_a, k, use_dispersion) for k in range(actual_max + 1)}
    prob_b = {k: neg_binom_prob(xg_b, k, use_dispersion) for k in range(actual_max + 1)}

    # 基础概率矩阵
    raw_probs = {}
    for a in range(actual_max + 1):
        for b in range(actual_max + 1):
            p = prob_a[a] * prob_b[b]
            raw_probs[(a, b)] = p

    # Dixon-Coles 低比分修正 (降低泊松对0-0/1-1的高估)
    # ρ参数: 差距越大ρ越负 (接近比赛用更轻的修正)
    dc_rho = -0.10 if score_gap > 15 else (-0.06 if score_gap > 8 else -0.03)
    adjusted_probs = dixon_coles_adjust(raw_probs, xg_a, xg_b, rho=dc_rho)

    all_probs = []
    win_prob = 0
    draw_prob = 0
    lose_prob = 0

    for (a, b), p in adjusted_probs.items():
        # 屠杀/大比分过滤
        if slaughter_mode:
            pass
        elif score_gap > 30:
            pass
        elif (a >= 4 and b >= 4) or (a == 0 and b >= 6) or (b == 0 and a >= 6):
            p *= 0.85

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
    # [v3.0 P2] 比赛级平局因子: 按两队历史平局倾向调节
    draw_bonus *= team_draw_factor
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
            if match_round == "group_1" and 12 <= score_gap <= 22:
                strength = 0.65
            elif match_round == "ko":
                strength = 0.8   # 淘汰赛就算强队也保守(1-0足矣)
        elif max_original > 0.40:
            strength = 0.85 if match_round == "ko" else 0.75
        else:
            strength = 1.2 if match_round == "ko" else 1.0  # 淘汰赛势均力敌平局更高

        # [v3.6] 实力差感知 + 近战保护
        # 若原始平局率已达30-45%, 说明是真实接近比赛 → 不降权
        close_match_protection = (0.30 <= draw_prob <= 0.45)
        if close_match_protection and score_gap < 20:
            strength *= 1.0  # 保留完整加成
        elif score_gap > 25:
            strength *= 0.5
        elif score_gap > 18:
            strength *= 0.7
        elif score_gap > 12:
            strength *= 0.85
        elif score_gap > 8:
            # [v3.0] Δ5-10区间错误率62%, 平局加成额外降30%
            strength *= 0.70

        effective_draw_bonus = 1.0 + (effective_draw_bonus - 1.0) * strength
    if effective_draw_bonus != 1.0:
        draw_prob *= effective_draw_bonus
        total2 = win_prob + draw_prob + lose_prob
        if total2 > 0:
            win_prob /= total2
            draw_prob /= total2
            lose_prob /= total2

    # P0: 实力悬殊-平局悖论 (强队围攻无果模式)
    # 在调用层处理, 此处根据score_gap做微调
    if score_gap > 25:
        # 大差距下平局微调 (v2.2: 降至1pp, 不与屠杀模式矛盾)
        draw_paradox_shift = min(0.01, draw_prob * 0.05)
        win_prob -= draw_paradox_shift * 0.7
        draw_prob += draw_paradox_shift
        lose_prob -= draw_paradox_shift * 0.3

    # 最可能比分 Top-5
    all_probs.sort(key=lambda x: x["probability"], reverse=True)

    # [v2.3] 确保Top比分与预测方向一致 (避免"主胜但比分1-1"的悖论)
    pred_direction = "home" if win_prob > draw_prob and win_prob > lose_prob else \
                     ("draw" if draw_prob >= win_prob and draw_prob >= lose_prob else "away")
    dir_scores = {"home": [], "draw": [], "away": []}
    for s in all_probs:
        h, a = map(int, s["score"].split("-"))
        if h > a: dir_scores["home"].append(s)
        elif h == a: dir_scores["draw"].append(s)
        else: dir_scores["away"].append(s)
    # Top3: 优先预测方向, 其余按概率补充(共5个)
    top_matching = dir_scores[pred_direction][:3]
    other_scores = [s for s in all_probs if s not in top_matching]
    top_scores_out = (top_matching + other_scores)[:5]

    return {
        "xg_home": round(xg_a, 2),
        "xg_away": round(xg_b, 2),
        "total_xg": round(xg_a + xg_b, 2),
        "win_pct": round(win_prob * 100, 1),
        "draw_pct": round(draw_prob * 100, 1),
        "lose_pct": round(lose_prob * 100, 1),
        "top_scores": top_scores_out
    }


def apply_gossip_shift(result: Dict, home_gossip_deduction: float, away_gossip_deduction: float) -> Dict:
    """
    八卦冷门修正
    热门方八卦扣分远大于冷门方 → 冷门概率上升
    """
    gap = abs(home_gossip_deduction - away_gossip_deduction)

    if gap >= 10:
        upset_shift = 4
        draw_shift = 1
    elif gap >= 5:
        upset_shift = 2
        draw_shift = 0
    elif gap >= 2:
        upset_shift = 1
        draw_shift = 0
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
                  home_conceded: float = 1.5, away_conceded: float = 1.5,
                  home_def_resilience: float = 50, away_def_resilience: float = 50,
                  home_att_conversion: float = 50, away_att_conversion: float = 50,
                  home_xg_off: float = 1.5, away_xg_off: float = 1.5,
                  home_xg_def: float = 1.5, away_xg_def: float = 1.5,
                  style_bonus: float = 0.0,
                  home_player_penalty: float = 0.0, away_player_penalty: float = 0.0,
                  home_fatigue: float = 0.0, away_fatigue: float = 0.0,
                  dq_bonus: float = 0.0, team_draw_factor: float = 1.0) -> Dict:
    """
    完整比赛预测 [v2.3]
    *_xg_off/def: xG代理值 [P1]
    style_bonus: 风格相克加成(±2) [P1]
    *_player_penalty: 关键球员缺阵惩罚(0-10) [P2]
    *_fatigue: 体能耗损(0-5) [P2]
    dq_bonus: 懂球帝高级数据综合加成(±5) [懂球帝]
    返回: {xg, win/draw/lose%, top_scores, cold_alert}
    """
    score_gap = abs(home_score - away_score)

    # P3: 屠杀因子 2.0 — 大差距+弱防守时大幅放大xG
    home_slaughter = 1.0
    away_slaughter = 1.0
    if home_score > away_score:
        gap = home_score - away_score
        if home_goals_per_game > 2.5 and away_conceded > 2.0:
            home_slaughter = 1.6 if gap > 30 else 1.4
        elif home_goals_per_game > 2.0 and away_conceded > 1.5:
            home_slaughter = 1.4 if gap > 25 else 1.2
        elif gap > 30:
            home_slaughter = 1.3  # 纯实力碾压
    else:
        gap = away_score - home_score
        if away_goals_per_game > 2.5 and home_conceded > 2.0:
            away_slaughter = 1.6 if gap > 30 else 1.4
        elif away_goals_per_game > 2.0 and home_conceded > 1.5:
            away_slaughter = 1.4 if gap > 25 else 1.2
        elif gap > 30:
            away_slaughter = 1.3

    # [v2.3] 防守韧性: 弱队摆大巴 → 降低强队xG
    home_def_factor = 1.0
    away_def_factor = 1.0
    if home_score < away_score and home_def_resilience > 60:
        # 主队是弱队但防守好 → 压制客队进攻
        home_def_factor = 1.0 - (home_def_resilience - 60) / 200  # max -20%
    if away_score < home_score and away_def_resilience > 60:
        away_def_factor = 1.0 - (away_def_resilience - 60) / 200

    # [v2.3] 进攻转化率: 把握机会能力强 → xG加成
    home_att_factor = 1.0 + max(0, (home_att_conversion - 55)) / 200  # max +22%
    away_att_factor = 1.0 + max(0, (away_att_conversion - 55)) / 200

    xg_home = score_to_xg(home_score, away_defense, home_slaughter)
    xg_away = score_to_xg(away_score, home_defense, away_slaughter)

    # Apply factor modifiers
    xg_home = xg_home * home_def_factor * home_att_factor
    xg_away = xg_away * away_def_factor * away_att_factor

    # [v2.3 P1] xG代理: 用近5场实际进球/失球微调(30%权重)
    xg_home = xg_home * 0.70 + home_xg_off * 0.30
    xg_away = xg_away * 0.70 + away_xg_off * 0.30

    # [v2.3 P1] 风格相克: 正数利好主队
    if style_bonus > 0:
        xg_home *= 1.0 + style_bonus / 50  # +2 → +4%
        xg_away *= 1.0 - style_bonus / 100
    elif style_bonus < 0:
        xg_away *= 1.0 - style_bonus / 50
        xg_home *= 1.0 + style_bonus / 100

    # [v2.3 P2] 关键球员缺阵: 直接降低xG
    xg_home *= max(0.7, 1.0 - home_player_penalty / 30)  # 10分→-33%
    xg_away *= max(0.7, 1.0 - away_player_penalty / 30)

    # [v2.3 P2] 体能惩罚: 疲劳→降低xG
    xg_home *= max(0.8, 1.0 - home_fatigue / 25)  # 5分→-20%
    xg_away *= max(0.8, 1.0 - away_fatigue / 25)

    # [v2.3] 懂球帝高级数据: 射正率+创造力+门将+防守综合 (±5分)
    if dq_bonus > 0:
        xg_home *= 1.0 + dq_bonus / 80
        xg_away *= 1.0 - dq_bonus / 160
    elif dq_bonus < 0:
        xg_away *= 1.0 - dq_bonus / 80
        xg_home *= 1.0 + dq_bonus / 160

    xg_home = max(0.2, xg_home)
    xg_away = max(0.2, xg_away)

    result = build_prob_matrix(xg_home, xg_away,
                               match_round=match_round,
                               temperature=temperature,
                               score_gap=score_gap,
                               team_draw_factor=team_draw_factor)

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

    # [v2.3] 最终对齐: 确保Top比分与最终方向一致 (覆盖gossip_shift等后处理)
    result = align_scores_to_direction(result)
    return result


def align_scores_to_direction(result: Dict) -> Dict:
    """确保TopN比分与最终W/D/L方向一致"""
    wp, dp, lp = result["win_pct"], result["draw_pct"], result["lose_pct"]
    if wp > dp and wp > lp:
        pred_dir = "home"
    elif dp >= wp and dp >= lp:
        pred_dir = "draw"
    else:
        pred_dir = "away"

    dir_scores = {"home": [], "draw": [], "away": []}
    for s in result["top_scores"]:
        h, a = map(int, s["score"].split("-"))
        if h > a: dir_scores["home"].append(s)
        elif h == a: dir_scores["draw"].append(s)
        else: dir_scores["away"].append(s)

    top_matching = dir_scores[pred_dir][:3]
    others = [s for s in result["top_scores"] if s not in top_matching]
    result["top_scores"] = (top_matching + others)[:5]
    return result
