"""48队小组第三出线路径建模"""
import json, itertools
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"


def get_third_place_ranking() -> list:
    """获取当前12个小组第三名的排名（最佳8队出线）"""
    groups = json.load(open(DATA / "groups.json"))
    teams = json.load(open(DATA / "teams.json"))

    thirds = []
    for gid, g in groups.items():
        sorted_teams = sorted(g["standings"].items(), key=lambda x: (-x[1]["p"], -x[1]["gd"], -x[1]["gf"]))
        if len(sorted_teams) >= 3:
            tid, stats = sorted_teams[2]
            thirds.append({
                "team_id": tid,
                "team_name": teams.get(tid, {}).get("name", tid),
                "group": gid,
                "pts": stats["p"],
                "gd": stats["gd"],
                "gf": stats["gf"],
                "ga": stats["ga"],
                "fair_play": 0,  # 黄牌-1/红牌-3
            })

    # 按FIFA官方规则排序: 积分>净胜球>进球>公平竞赛>抽签
    thirds.sort(key=lambda x: (-x["pts"], -x["gd"], -x["gf"], x["fair_play"]))

    for i, t in enumerate(thirds):
        t["rank"] = i + 1
        t["qualifies"] = i < 8  # 前8出线

    return thirds


def third_place_matchups(third_qualifiers: list) -> dict:
    """
    根据FIFA官方淘汰赛对阵表，确定小组第三出线后32强的对阵
    参考: PREDICTION_SYSTEM.md §6.4 淘汰赛对阵路径
    """
    # 小组第一 vs 小组第三 的对阵映射
    group_winner_waiting = {
        "E": "M74: 1E vs 3A/B/C/D/F",
        "I": "M77: 1I vs 3C/D/F/G/H",
        "A": "M79: 1A vs 3C/E/F/H/I",
        "L": "M80: 1L vs 3E/H/I/J/K",
        "D": "M81: 1D vs 3B/E/F/I/J",
        "G": "M82: 1G vs 3A/E/H/I/J",
        "B": "M85: 1B vs 3E/F/G/I/J",
        "K": "M87: 1K vs 3D/E/I/J/L",
    }

    qualifier_groups = {t["group"] for t in third_qualifiers if t["qualifies"]}

    # 根据出线的8个第三名分组，确定具体对阵
    # 规则: 四个第三名来自不同组别时，有一个确定的映射表
    matchups = {}
    for gw, match_desc in group_winner_waiting.items():
        possible_thirds = match_desc.split("3")[1].split(" ")[0].split("/")[1:]
        for pg in possible_thirds:
            if pg in qualifier_groups:
                matchups[gw] = {"match": match_desc[:4], "third_group": pg}
                break

    return matchups


def simulate_third_place() -> str:
    """输出小组第三出线形势报告"""
    thirds = get_third_place_ranking()

    lines = ["=" * 60, "  48队小组第三出线形势", "=" * 60, ""]
    lines.append(f"{'排名':<4} {'球队':<16} {'组':<3} {'分':>3} {'GD':>4} {'GF':>3} {'出线':<6}")
    lines.append("-" * 50)

    for t in thirds:
        status = "✅ 晋级" if t["qualifies"] else "❌ 淘汰"
        mark = ""
        if t["pts"] == 0: mark = " (未赛)"
        lines.append(f"{t['rank']:<4} {t['team_name']:<16} {t['group']:<3} {t['pts']:>3} {t['gd']:>+4} {t['gf']:>3} {status}{mark}")

    lines.append("")
    lines.append("出线规则: 积分>净胜球>进球>公平竞赛>抽签")
    lines.append("前8名小组第三晋级32强, 对阵FIFA官方指定小组第一")
    return "\n".join(lines)
