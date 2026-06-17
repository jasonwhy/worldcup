#!/usr/bin/env python3
"""
2026世界杯预测系统 CLI v2.1
用法:
  python main.py FRA-SEN                # 单场完整预测
  python main.py France-Senegal         # 支持国家名
  python main.py --group I              # 小组分析
  python main.py --rank                 # 48队实力排名
  python main.py --gossip IRN           # 查看球队八卦风控
  python main.py --lottery FRA-SEN,IRQ-NOR,ARG-ALG,AUT-JOR,ENG-CRO,GHA-PAN,POR-COD,COL-UZB
                                        # 自动生成竞彩投注方案
  python main.py --today                # 今日8场比赛全部完整预测
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from engine import predict, final_score, format_output
from engine.gossip import gossip_score, clean_stale_gossip
from engine.hard_data import hard_data_score
from engine.lottery import generate_plan, format_lottery
from engine.penalty import penalty_shootout_prob
from engine.third_place import get_third_place_ranking, simulate_third_place


def cmd_predict(match_str: str):
    p = predict(match_str)
    print(format_output(p))


def cmd_group(group_id: str):
    """小组分析"""
    groups = json.load(open("data/groups.json"))
    if group_id.upper() not in groups:
        print(f"小组 {group_id} 不存在")
        return

    g = groups[group_id.upper()]
    print(f"\n{'='*60}")
    print(f"  Group {group_id.upper()} 分析")
    print(f"{'='*60}")

    standings = []
    for tid in g["teams"]:
        fs = final_score(tid)
        standings.append((tid, fs))

    standings.sort(key=lambda x: x[1]["total"], reverse=True)

    print(f"\n{'球队':<20} {'总分':>6} {'硬数据':>6} {'外盘':>6} {'八卦':>6}")
    print("-" * 56)
    for tid, fs in standings:
        print(f"{fs['name']:<20} {fs['total']:>6.1f} {fs['hard_data']['score']:>6.1f} "
              f"{fs['betting']['score']:>6.1f} {fs['gossip']['score']:>6.1f}")

    # 前两名vs其他
    print(f"\n📊 预测出线: 1.{standings[0][1]['name']}  2.{standings[1][1]['name']}")
    print(f"📊 第三名竞争力: {standings[2][1]['name']} ({standings[2][1]['total']:.1f}分)")


def cmd_rank():
    """48队实力排名（当前录入的球队）"""
    teams = json.load(open("data/teams.json"))
    rankings = []
    for tid in teams:
        fs = final_score(tid)
        rankings.append((tid, fs))

    rankings.sort(key=lambda x: x[1]["total"], reverse=True)

    print(f"\n{'排名':<5} {'球队':<16} {'总分':>6} {'硬数据':>6} {'外盘':>6} {'八卦':>6}")
    print("-" * 62)
    for i, (tid, fs) in enumerate(rankings, 1):
        name = fs['name']
        flag = ""
        if fs['gossip']['score'] < 85:
            flag = " ⚠️"
        print(f"{i:<5} {name:<16} {fs['total']:>6.1f} {fs['hard_data']['score']:>6.1f} "
              f"{fs['betting']['score']:>6.1f} {fs['gossip']['score']:>6.1f}{flag}")


def cmd_gossip(team_id: str):
    """查看球队八卦详情"""
    gs = gossip_score(team_id.upper())
    print(f"\n{'='*50}")
    print(f"  {team_id.upper()} 八卦风控详情")
    print(f"{'='*50}")
    print(f"总得分: {gs['score']:.1f}/100 (满分100, 扣分制)")
    d = gs["detail"]
    print(f"\n更衣室稳定性: {d['locker_room_score']:.1f}/40")
    if d.get("locker_room_decay"):
        print(f"  时间衰减: {d['locker_room_decay']:.2f}")
    print(f"政治/签证干扰: {d['political_score']:.1f}/35 (级别: {'★'*d['political_level']})")
    print(f"球星场外信号: {d['player_off_field_score']:.1f}/25")
    if d.get("positive_signal"):
        print(f"  正向信号: {d['positive_signal']}")


def cmd_lottery(matches_str: str, budget: int = 100):
    """自动生成竞彩投注方案"""
    matches = [m.strip() for m in matches_str.split(",")]
    # 动态修改预算
    import engine.lottery as lottery
    lottery.RULE["budget"] = budget
    plan = generate_plan(matches)
    print(format_lottery(plan))


def cmd_today():
    """今日全部比赛完整预测 + 自动投注方案"""
    today_matches = [
        "FRA-SEN", "IRQ-NOR", "ARG-ALG", "AUT-JOR",
        "ENG-CRO", "GHA-PAN", "POR-COD", "COL-UZB"
    ]
    for m in today_matches:
        p = predict(m)
        print(format_output(p))
        print()

    print("=" * 70)
    print("  以上8场模型输出 → 自动生成投注方案")
    print("=" * 70)
    cmd_lottery(",".join(today_matches))


def main():
    if len(sys.argv) < 2:
        print("2026世界杯预测系统 v2.0")
        print("用法: python main.py <FRA-SEN | --group I | --rank | --gossip IRN>")
        print("示例: python main.py FRA-SEN")
        print("      python main.py --group I")
        print("      python main.py --rank")
        return

    arg = sys.argv[1]

    if arg == "--rank":
        cmd_rank()
    elif arg == "--group" and len(sys.argv) > 2:
        cmd_group(sys.argv[2])
    elif arg == "--gossip" and len(sys.argv) > 2:
        cmd_gossip(sys.argv[2])
    elif arg == "--lottery" and len(sys.argv) > 2:
        budget = int(sys.argv[3]) if len(sys.argv) > 3 else 100
        cmd_lottery(sys.argv[2], budget)
    elif arg == "--today":
        cmd_today()
    elif arg == "--third":
        print(simulate_third_place())
    elif arg == "--penalty" and len(sys.argv) > 2:
        pk = penalty_shootout_prob(sys.argv[2].upper(), sys.argv[3].upper())
        for k, v in pk.items(): print(f"  {k}: {v}")
    elif arg == "--clean":
        n = clean_stale_gossip()
        print(f"🧹 清理了 {n} 条过期八卦事件")
    elif arg == "--matchup" and len(sys.argv) > 2:
        from engine.matchup import full_matchup_score
        parts = sys.argv[2].upper().split("-")
        if len(parts) == 2:
            m = full_matchup_score(parts[0], parts[1])
            print(f"{m['team_a']} vs {m['team_b']}")
            print(f"  球员对位: {m['player_score']:+}  |  战术匹配: {m['tactical_score']:+}")
            print(f"  综合: {m['combined']:+} → {m['direction']}")
            if m['player_detail']: print(f"  球员: {m['player_detail']}")
            if m['tactical_detail']: print(f"  战术: {m['tactical_detail']}")
    else:
        cmd_predict(arg)


if __name__ == "__main__":
    main()
