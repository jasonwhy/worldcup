"""
轮次态势感知 v1.0
=================
读取 groups.json 积分榜, 为每场比赛的双发计算"心理动力修正"
- 出线需求: 必须赢=+2, 可接受平=-1, 无关=0
- 净胜球需求: 同分争净胜=+1
- 输出: (home_bonus, away_bonus) → 动量修正 -3~+3
"""
import json
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"

def load_json(n):
    with open(DATA / n) as f:
        return json.load(f)

MAX_POINTS = 6  # 48队赛制下, 6分稳出线

def motivation_score(team_id: str) -> float:
    """计算球队的出线动力分 (-3 ~ +3)"""
    groups = load_json("groups.json")

    # Find this team's group
    gid = None
    for g, info in groups.items():
        if team_id in info.get("teams", []):
            gid = g
            break
    if not gid:
        return 0.0

    g = groups[gid]
    st = sorted(g["standings"].items(), key=lambda x: (-x[1]["p"], -x[1]["gd"], -x[1]["gf"]))
    team_rank = next(i for i, (t, _) in enumerate(st) if t == team_id)
    team_pts = g["standings"][team_id]["p"]
    team_gd = g["standings"][team_id]["gd"]
    games_played = g["standings"][team_id]["w"] + g["standings"][team_id]["d"] + g["standings"][team_id]["l"]

    bonus = 0.0

    # 48队赛制: 前2直通 + 8个最佳第3
    # Round 2 (1 game played): 3分→形势好, 0-1分→必须赢
    if games_played == 1:
        if team_pts == 3:
            bonus = 0.5   # 形势良好, 可稳可攻
        elif team_pts == 1:
            bonus = 1.0   # 平局不够, 需要赢
        elif team_pts == 0:
            bonus = 1.5   # 背水一战

    # Round 3 (2 games played): 更明确的出线形势
    elif games_played == 2:
        if team_pts >= 4:
            bonus = -0.5  # 基本出线, 可接受平
        elif team_pts == 3:
            # 3分 → 需要根据其他人的情况判断
            others = [(t, s["p"]) for t, s in st if t != team_id]
            if any(p >= 4 for _, p in others):
                bonus = 1.5  # 有人4分, 必须赢
            else:
                bonus = 0.5  # 其他人也乱, 平局可能够
        elif team_pts <= 2:
            bonus = 2.0   # 必须赢才有一线生机

    # 排名因素: 排在前面→动力降低, 排在后面→动力增加
    if team_rank == 0:
        bonus -= 0.5
    elif team_rank >= 2:
        bonus += 0.5

    # 净胜球需求: 同分时看净胜球
    for other_t, other_s in st:
        if other_t == team_id: continue
        if other_s["p"] == team_pts and abs(team_gd - other_s["gd"]) <= 1:
            bonus += 0.5  # 同分+净胜球接近→需要刷净胜球
            break

    return round(min(3, max(-3, bonus)), 1)


def round_momentum_adjust(home_id: str, away_id: str) -> float:
    """
    返回主队动量调整值 (正=主队有利, 负=客队有利)
    注入到 hard_data_score 的最终分数中
    """
    hm = motivation_score(home_id)
    am = motivation_score(away_id)
    return round((hm - am) * 1.5, 1)  # 放大系数1.5
