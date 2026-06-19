"""
懂球帝高级数据引擎 v1.0
从真实世界杯数据提取: 射门效率、创造力、防守脆弱度、门将质量
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def load_dq():
    with open(DATA_DIR / "dongqiudi_stats.json") as f:
        return json.load(f)


def team_shots_per_match(team_id: str) -> float:
    """场均射门数"""
    dq = load_dq()
    t = dq["teams"].get(team_id, {})
    shots = t.get("shots", 0)
    # 估算已赛场次: 从groups.json获取
    groups = json.load(open(DATA_DIR / "groups.json"))
    played = 1
    for gid, gdata in groups.items():
        if team_id in gdata["teams"]:
            played = gdata["standings"][team_id]["p"]
            break
    return round(shots / max(1, played), 1)


def shot_accuracy(team_id: str) -> float:
    """射正率 0-100"""
    dq = load_dq()
    t = dq["teams"].get(team_id, {})
    shots = t.get("shots", 1)
    on_target = t.get("shots_on_target", 0)
    return round(on_target / max(1, shots) * 100, 1)


def creativity_per_match(team_id: str) -> float:
    """场均关键传球 (创造力指标)"""
    dq = load_dq()
    t = dq["teams"].get(team_id, {})
    kp = t.get("key_passes", 0)
    groups = json.load(open(DATA_DIR / "groups.json"))
    played = 1
    for gid, gdata in groups.items():
        if team_id in gdata["teams"]:
            played = gdata["standings"][team_id]["p"]
            break
    return round(kp / max(1, played), 1)


def defensive_fragility(team_id: str) -> float:
    """防守脆弱度 0-100 (越高越差) — 基于失误导致丢球"""
    dq = load_dq()
    t = dq["teams"].get(team_id, {})
    errors = t.get("errors_lead_goal", 0)
    groups = json.load(open(DATA_DIR / "groups.json"))
    played = 1
    for gid, gdata in groups.items():
        if team_id in gdata["teams"]:
            played = gdata["standings"][team_id]["p"]
            break
    return round(min(100, errors / max(1, played) * 40), 1)


def goalkeeper_quality(team_id: str) -> float:
    """门将质量 0-100 — 基于禁区射门扑救"""
    dq = load_dq()
    t = dq["teams"].get(team_id, {})
    saves = t.get("box_saves", 0)
    groups = json.load(open(DATA_DIR / "groups.json"))
    played = 1
    for gid, gdata in groups.items():
        if team_id in gdata["teams"]:
            played = gdata["standings"][team_id]["p"]
            break
    # 4次扑救/场 ≈ 满分
    return round(min(100, saves / max(1, played) / 4 * 100), 1)


def offensive_pressure(team_id: str) -> float:
    """进攻压迫 0-100 — 基于场均射门+射正率"""
    spm = team_shots_per_match(team_id)
    acc = shot_accuracy(team_id)
    return round(min(100, spm / 15 * 50 + acc * 0.5), 1)


def fouls_per_match(team_id: str) -> float:
    """场均犯规 — 侵略性/身体对抗强度"""
    dq = load_dq()
    t = dq["teams"].get(team_id, {})
    fouls = t.get("fouls", 0)
    groups = json.load(open(DATA_DIR / "groups.json"))
    played = 1
    for gid, gdata in groups.items():
        if team_id in gdata["teams"]:
            played = gdata["standings"][team_id]["p"]
            break
    return round(fouls / max(1, played), 1)


def team_pass_accuracy(team_id: str) -> float:
    """团队传球成功率"""
    dq = load_dq()
    t = dq["teams"].get(team_id, {})
    return t.get("pass_accuracy", 75)


def saves_per_match(team_id: str) -> float:
    """场均扑救 — 高值=防线压力大"""
    dq = load_dq()
    t = dq["teams"].get(team_id, {})
    saves = t.get("saves", 0)
    groups = json.load(open(DATA_DIR / "groups.json"))
    played = 1
    for gid, gdata in groups.items():
        if team_id in gdata["teams"]:
            played = gdata["standings"][team_id]["p"]
            break
    return round(saves / max(1, played), 1)


def offsides_per_match(team_id: str) -> float:
    """场均越位 — 高值=激进进攻线"""
    dq = load_dq()
    t = dq["teams"].get(team_id, {})
    offsides = t.get("offsides", 0)
    groups = json.load(open(DATA_DIR / "groups.json"))
    played = 1
    for gid, gdata in groups.items():
        if team_id in gdata["teams"]:
            played = gdata["standings"][team_id]["p"]
            break
    return round(offsides / max(1, played), 1)


def dongqiudi_bonus(home_id: str, away_id: str) -> dict:
    """
    懂球帝数据综合加成 → 正数利主队
    返回: {bonus, details, reasons}
    """
    home_sa = shot_accuracy(home_id)
    away_sa = shot_accuracy(away_id)
    home_cr = creativity_per_match(home_id)
    away_cr = creativity_per_match(away_id)
    home_df = defensive_fragility(home_id)
    away_df = defensive_fragility(away_id)
    home_gk = goalkeeper_quality(home_id)
    away_gk = goalkeeper_quality(away_id)
    home_pass = team_pass_accuracy(home_id)
    away_pass = team_pass_accuracy(away_id)
    home_fouls = fouls_per_match(home_id)
    away_fouls = fouls_per_match(away_id)

    reasons = []
    bonus = 0.0

    # 射正率 (权重1)
    sa_diff = home_sa - away_sa
    if abs(sa_diff) > 12:
        b = 2.0 if sa_diff > 0 else -2.0
        bonus += b
        reasons.append(f"射正差{sa_diff:+.0f}%")

    # 创造力 (权重1)
    cr_diff = home_cr - away_cr
    if abs(cr_diff) > 3:
        b = 1.5 if cr_diff > 0 else -1.5
        bonus += b
        reasons.append(f"创造力差{cr_diff:+.1f}次")

    # 防守脆弱度 (权重1)
    df_diff = away_df - home_df
    if abs(df_diff) > 15:
        b = 1.5 if df_diff > 0 else -1.5
        bonus += b
        reasons.append(f"防守差{df_diff:+.0f}分")

    # 门将 (权重1)
    gk_diff = home_gk - away_gk
    if abs(gk_diff) > 25:
        b = 1.5 if gk_diff > 0 else -1.5
        bonus += b
        reasons.append(f"门将差{gk_diff:+.0f}分")

    # 传球成功率 (权重0.5)
    pass_diff = home_pass - away_pass
    if abs(pass_diff) > 8:
        b = 1.0 if pass_diff > 0 else -1.0
        bonus += b
        reasons.append(f"传球差{pass_diff:+.0f}%")

    # 犯规/侵略性 (负相关: 太多犯规不利控球)
    fouls_diff = away_fouls - home_fouls
    if abs(fouls_diff) > 8:
        b = 0.8 if fouls_diff > 0 else -0.8
        bonus += b
        reasons.append(f"犯规差{fouls_diff:+.0f}次")

    return {
        "bonus": round(min(5.0, max(-5.0, bonus)), 1),
        "home_sa": home_sa, "away_sa": away_sa,
        "home_cr": home_cr, "away_cr": away_cr,
        "home_gk": home_gk, "away_gk": away_gk,
        "home_pass": home_pass, "away_pass": away_pass,
        "reasons": reasons
    }
