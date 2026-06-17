#!/usr/bin/env python3
"""
数据抓取更新任务调度器
用法:
  python update_data.py --check       # 检查所有数据文件完整性
  python update_data.py --postmatch   # 赛后更新：积分+伤病+八卦
  python update_data.py --prematch    # 赛前更新：赔率+预测+审计
  python update_data.py --full        # 完整每日循环
"""
import sys, json, os
from pathlib import Path
from datetime import date, datetime

DATA = Path(__file__).parent / "data"
AUDIT_SYSTEM = Path(__file__).parent / "audit_system.py"
AUDIT_LOTTERY = Path(__file__).parent / "audit_lottery.py"


def load(name):
    with open(DATA / name) as f:
        return json.load(f)


def save(name, data):
    with open(DATA / name, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# 任务1：数据完整性检查
# ============================================================
def task_check():
    header(f"数据完整性检查 — {date.today()}")

    teams = load("teams.json")
    groups = load("groups.json")
    injuries = load("injuries.json")
    gossip = load("gossip.json")

    ALL_48 = set()
    for g in groups.values():
        for t in g["teams"]:
            ALL_48.add(t)

    results = []

    # 1.1 球队覆盖
    missing = ALL_48 - set(teams.keys())
    results.append(("teams.json覆盖", len(missing) == 0, f"缺{len(missing)}队" if missing else "48队完整"))

    # 1.2 积分一致性
    standings_ok = True
    for gid, g in groups.items():
        for tid in g["teams"]:
            s = g["standings"].get(tid, {})
            calc_pts = s.get("w", 0) * 3 + s.get("d", 0) * 1
            if calc_pts != s.get("p", 0):
                standings_ok = False
                break
    results.append(("小组积分计算", standings_ok, "所有组积分=3W+1D" if standings_ok else "积分计算错误"))

    # 1.3 伤病合理性
    inj_count = sum(len(v) for v in injuries.values())
    results.append(("伤病记录", True, f"{inj_count}条记录, {len(injuries)}队受影响"))

    # 1.4 八卦时效
    stale = []
    for tid, gdata in gossip.items():
        for section in ["locker_room", "political", "player_off_field"]:
            if section in gdata and gdata[section].get("date"):
                event_date = datetime.strptime(gdata[section]["date"], "%Y-%m-%d").date()
                days = (date.today() - event_date).days
                if days > 30:
                    import math
                    decay = math.exp(-0.05 * days)
                    if decay < 0.1:
                        stale.append(f"{tid}.{section} ({days}d, decay={decay:.2f})")
    results.append(("八卦时效", len(stale) == 0, f"{len(stale)}条过期" if stale else "全部有效"))

    # 输出
    for name, ok, detail in results:
        tag = "✅" if ok else "⚠️"
        print(f"  {tag} {name}: {detail}")

    if stale:
        print(f"\n  ⚠️ 建议清理以下过期八卦事件:")
        for s in stale:
            print(f"    - {s}")

    return all(r[1] for r in results)


# ============================================================
# 任务2：赛后数据更新
# ============================================================
def task_postmatch():
    header(f"赛后数据更新 — {date.today()}")

    print("""
  赛后更新清单:
  □ 从 FIFA.com Standings 抓取最新积分 → 更新 groups.json
  □ 从 ESPN伤病追踪器 抓取伤病 → 更新 injuries.json
  □ 从 ESPN/Fox/Yahoo新闻线 抓取场外 → 更新 gossip.json
  □ 从 FotMob/WhoScored 抓取比赛统计 → 更新 teams.json recent_5/10
  □ 抓取赛后赔率变化 → 更新 teams.json odds_history

  操作方式:
  1. 使用 web_search_exa 搜索 "FIFA World Cup 2026 standings [date]"
  2. 提取积分数据 → 手动更新 groups.json
  3. 搜索 "[team] injury World Cup 2026" → 更新 injuries.json
  4. 搜索 "World Cup 2026 controversy drama news" → 更新 gossip.json
  5. 运行 python audit_system.py 验证
    """)

    # 自动运行审计
    os.system(f"python3 {AUDIT_SYSTEM}")


# ============================================================
# 任务3：赛前数据更新
# ============================================================
def task_prematch():
    header(f"赛前数据更新 — {date.today()}")

    print("""
  赛前更新清单:
  □ 从 Fox Sports Odds 抓取最新赔率 → 更新 teams.json odds
  □ 从 bet365/DraftKings 抓取单场盘口 → 更新 teams.json
  □ 更新 betting.py 中赔率漂移阈值(如有重大变化)
  □ 运行 python main.py --today 生成当日预测+投注方案
  □ 运行 python audit_lottery.py 验证投注合规

  操作方式:
  1. web_search "2026 World Cup odds [today's date] bet365 FanDuel"
  2. 提取赔率数据 → 手动更新 teams.json odds 字段
  3. web_search "2026 World Cup match odds [match1] [match2]"
  4. 运行完整预测流程
    """)

    # 自动运行今日预测
    os.system(f"python3 -m main --today")


# ============================================================
# 任务4：完整每日循环
# ============================================================
def task_full():
    print(f"{'='*60}")
    print(f"  2026世界杯数据维护 — 完整每日循环")
    print(f"  日期: {date.today()}")
    print(f"{'='*60}")

    # Phase 1: 赛后更新
    task_postmatch()

    # Phase 2: 数据检查
    ok = task_check()

    # Phase 3: 赛前预测
    if ok:
        task_prematch()
    else:
        print("\n⚠️ 数据检查未通过, 跳过赛前预测。请先修复上述问题。")

    print(f"\n{'='*60}")
    print(f"  每日循环完成")
    print(f"{'='*60}")


# ============================================================
def main():
    if len(sys.argv) < 2:
        print("数据抓取更新任务调度器")
        print("用法: python update_data.py --check | --postmatch | --prematch | --full")
        return

    cmd = sys.argv[1]
    if cmd == "--check":
        task_check()
    elif cmd == "--postmatch":
        task_postmatch()
    elif cmd == "--prematch":
        task_prematch()
    elif cmd == "--full":
        task_full()
    else:
        print(f"未知命令: {cmd}")


if __name__ == "__main__":
    main()
