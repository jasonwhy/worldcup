"""
外盘信号层引擎 —— 钱是最诚实的预言
- 赔率结构与漂移
- 资金流向分析
- 亚洲盘口语言
- 归一化输出0-100分
"""
import json
import math
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def load_json(name):
    with open(DATA_DIR / name, "r") as f:
        return json.load(f)


def odds_structure(team: dict) -> float:
    """3.1 赔率结构分析 (0-100)"""
    odds = team.get("odds", {})
    outright = odds.get("outright", 10000)

    # 赔率排名分: 直接用赔率反推概率, +450≈18.2% → 高分
    implied_prob_pct = 100 / (outright / 100 + 1) if outright > 0 else 0
    rank_score = min(50, implied_prob_pct * 2.5)  # 20%概率→50分, 10%→25分

    # 赔率漂移分析
    history = team.get("odds_history", {})
    drift_score = 25  # 基准
    if history:
        week_ago = history.get("7d_ago", outright)
        month_ago = history.get("30d_ago", outright)
        week_change = (week_ago - outright) / week_ago if week_ago > 0 else 0

        if week_change > 0.15:
            drift_score = 40  # 急剧收缩→内部利好
        elif week_change > 0.05:
            drift_score = 32  # 温和收缩
        elif week_change > -0.05:
            drift_score = 25  # 稳定
        elif week_change > -0.15:
            drift_score = 18  # 温和外扩
        else:
            drift_score = 10  # 急剧外扩→利空

    # 庄家共识: 方向性判断——收缩=市场信心增强, 外扩=信心减弱
    if history:
        if week_change > 0.10:
            consensus = 28  # 大幅收缩: 市场高度一致看强
        elif week_change > 0.05:
            consensus = 25  # 温和收缩: 共识增强
        elif week_change > -0.05:
            consensus = 22  # 稳定: 共识不变
        elif week_change > -0.10:
            consensus = 18  # 温和外扩: 共识减弱
        else:
            consensus = 12  # 大幅外扩: 信心崩溃
    else:
        consensus = 20

    return rank_score + drift_score + consensus


def sharp_money_signal(team_id: str, team: dict) -> dict:
    """3.2 资金流向分析"""
    odds = team.get("odds", {})
    history = team.get("odds_history", {})

    signals = {
        "sharp_inflow": False,
        "public_overheat": False,
        "value_flag": False,
        "score": 50
    }

    if history:
        week_ago = history.get("7d_ago", odds.get("outright", 5000))
        current = odds.get("outright", 5000)
        change_pct = (week_ago - current) / week_ago if week_ago > 0 else 0

        # Sharp Money: 赔率收缩 + 低交易量 (我们通过幅度推断)
        if change_pct > 0.15:
            signals["sharp_inflow"] = True
            signals["score"] += 20
        elif change_pct > 0.05:
            signals["score"] += 10

        # 公众过热: USA爱国注等 (通过特定标记)
        if team_id in ["USA"]:
            signals["public_overheat"] = True
            signals["score"] -= 10

    # 低赔率+低热度 = 价值洼地
    if odds.get("outright", 5000) > 4000 and not signals.get("public_overheat"):
        signals["value_flag"] = True

    signals["score"] = min(100, max(0, signals["score"]))
    return signals


def asian_handicap_signal(team_id: str, opponent_id: str = None) -> float:
    """3.3 亚洲盘口信号 (简化版)"""
    # 基于球队实力差距推断隐含盘口
    teams = load_json("teams.json")
    team = teams.get(team_id, {})
    if not opponent_id or not team:
        return 50

    opponent = teams.get(opponent_id, {})
    if not opponent:
        return 50

    # 用FIFA排名差推断隐含让球
    rank_diff = opponent.get("fifa_rank", 25) - team.get("fifa_rank", 25)

    if rank_diff > 20:
        handicap_signal = 80  # 深度让球
    elif rank_diff > 10:
        handicap_signal = 65
    elif rank_diff > 5:
        handicap_signal = 55
    elif abs(rank_diff) <= 5:
        handicap_signal = 45  # 势均力敌
    elif rank_diff > -10:
        handicap_signal = 35
    else:
        handicap_signal = 20  # 被深度让球

    return handicap_signal


def betting_score(team_id: str, opponent_id: str = None) -> dict:
    """外盘信号层总分 (0-100)"""
    teams = load_json("teams.json")
    team = teams.get(team_id)
    if not team:
        return {"score": 50, "detail": {"odds_struct": 50, "money_flow": 50, "handicap": 50}}

    odds_s = odds_structure(team)
    money = sharp_money_signal(team_id, team)
    handicap = asian_handicap_signal(team_id, opponent_id)

    final = odds_s * 0.40 + money["score"] * 0.33 + handicap * 0.27
    return {
        "score": round(final, 1),
        "detail": {
            "odds_structure": round(odds_s, 1),
            "money_flow": round(money["score"], 1),
            "handicap_signal": round(handicap, 1),
            "sharp_money": money["sharp_inflow"],
            "public_overheat": money["public_overheat"]
        }
    }
