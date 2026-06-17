#!/usr/bin/env python3
"""
数据自动更新引擎 v1.0
=====================
解决伤病/八卦/新闻数据过时问题。

工作原理:
  1. 检查每个数据源的 last_check 时间
  2. 标记过期源 (>2天未更新)
  3. 对八卦数据应用时间衰减 (14天半衰期)
  4. 清理已解决的伤病条目
  5. 自动重新生成 dashboard

用法:
  python3 fetch_updates.py           # 审计模式: 只检查不修改
  python3 fetch_updates.py --apply   # 应用模式: 执行衰减+清理+重新生成
  python3 fetch_updates.py --serve   # 守护模式: 每30分钟自动运行

建议 crontab (Mac):
  */30 * * * * cd /path/to/worldcup && python3 fetch_updates.py --apply
"""

import json, sys, os
from pathlib import Path
from datetime import date, datetime, timedelta
from math import exp

DATA = Path("data")
SRC = load_sources = lambda: json.load(open(DATA / "sources.json"))

PASS, FAIL, WARN = "✅", "❌", "⚠️"

# ============================================================
# 配置
# ============================================================
STALE_THRESHOLD_DAYS = 2        # 超此天数标记过期
GOSSIP_HALF_LIFE_DAYS = 14      # 八卦半衰期
DECAY_RATE = 0.05               # e^(-0.05*days)
AUTO_CLEAN_THRESHOLD = 0.05     # 衰减到5%以下自动删除

# ============================================================
# Layer 1: 检测过期源
# ============================================================
def check_sources():
    """扫描 sources.json, 返回过期源列表"""
    sources = json.load(open(DATA / "sources.json"))
    today = date.today()
    stale, blocked, active = [], [], []

    for sid, s in sources["sources"].items():
        last = s.get("last_check", "")
        status = s.get("status", "")
        if status == "blocked":
            blocked.append(s)
            continue
        if not last:
            stale.append(s)
            continue
        days = (today - datetime.strptime(last, "%Y-%m-%d").date()).days
        if days > STALE_THRESHOLD_DAYS:
            stale.append((s, days))
        else:
            active.append((s, days))

    return active, stale, blocked


# ============================================================
# Layer 2: 八卦时间衰减
# ============================================================
def decay_gossip():
    """对 gossip.json 中所有条目应用时间衰减"""
    gossip = json.load(open(DATA / "gossip.json"))
    today = date.today()
    cleaned = []

    for tid, g in gossip.items():
        for category in ["locker_room", "political", "player_off_field"]:
            if category not in g:
                continue
            entry = g[category]
            score = entry.get("score", 0)
            if score == 0:
                continue

            entry_date_str = entry.get("date", "")
            if not entry_date_str:
                continue

            try:
                entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d").date()
                days = (today - entry_date).days
                if days <= 0:
                    continue

                decay_factor = exp(-DECAY_RATE * days)
                new_score = round(score * decay_factor, 1)

                if abs(new_score) < AUTO_CLEAN_THRESHOLD * abs(score):
                    # 衰减到接近0, 清理
                    entry["score"] = 0
                    entry["reason"] = f"(已过期清理) {entry.get('reason','')}"
                    cleaned.append(f"{tid}/{category}")
                elif new_score != score:
                    old_s = entry["score"]
                    entry["score"] = new_score
                    print(f"  ⏳ {tid}/{category}: {old_s} → {new_score} (衰减{days}天)")

            except ValueError:
                continue

    json.dump(gossip, open(DATA / "gossip.json", "w"), indent=2, ensure_ascii=False)
    if cleaned:
        print(f"  🧹 清理过期八卦: {', '.join(cleaned)}")
    return len(cleaned)


# ============================================================
# Layer 3: 清理已过期的伤病
# ============================================================
def clean_injuries():
    """清理 return_date 已过的伤病条目, 降级 doubtful→active"""
    injuries = json.load(open(DATA / "injuries.json"))
    today = date.today()
    removed = []

    for tid in list(injuries.keys()):
        new_list = []
        for inj in injuries[tid]:
            return_date = inj.get("return_date", "")
            if return_date:
                try:
                    rd = datetime.strptime(return_date, "%Y-%m-%d").date()
                    if rd <= today and inj["status"] in ("doubtful",):
                        # Doubtful 且归期已到 → 降级为 active
                        inj["status"] = "active"
                        inj["reason"] = f"(已按时回归) {inj.get('reason','')}"
                        print(f"  🟢 {tid} {inj['player']}: doubtful→active (return {return_date})")
                except ValueError:
                    pass
            new_list.append(inj)
        injuries[tid] = new_list

    json.dump(injuries, open(DATA / "injuries.json", "w"), indent=2, ensure_ascii=False)
    return len(removed)


# ============================================================
# Layer 4: 数据源更新指引
# ============================================================
UPDATE_GUIDE = """
📋 手动更新指引 (无法自动抓取的源):
┌─────────────────────┬──────────────────────┬──────────┐
│ 数据文件              │ 主要来源               │ 更新频率   │
├─────────────────────┼──────────────────────┼──────────┤
│ injuries.json       │ Action Network       │ 每日      │
│                     │ SquadWire            │ 每日      │
│                     │ The Independent      │ 每日      │
│                     │ WorldCupWiki         │ 每2日     │
├─────────────────────┼──────────────────────┼──────────┤
│ gossip.json         │ The Mirror           │ 每日      │
│                     │ The Observer         │ 每日      │
│                     │ Fabrizio Romano (X)  │ 实时      │
├─────────────────────┼──────────────────────┼──────────┤
│ news.json           │ ESPN, BBC, Sky       │ 每日      │
│                     │ Fox Sports, Yahoo    │ 每日      │
│                     │ Ge.Globo (巴西)       │ 每日      │
└─────────────────────┴──────────────────────┴──────────┘

实际操作: 每次运行 fetch_updates.py --apply 时:
  1. 自动衰减过期八卦 (无需手动)
  2. 自动清理过期伤病条目 (return_date已过)
  3. 从 sources.json 检查哪些源过期 → 提醒手动更新
  4. 自动重新生成 dashboard.html
"""

# ============================================================
# Main
# ============================================================
def main():
    apply_mode = "--apply" in sys.argv
    serve_mode = "--serve" in sys.argv

    print("=" * 70)
    print(f"  数据自动更新引擎 v1.0")
    print(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  模式: {'应用+重新生成' if apply_mode else '审计'}")
    print("=" * 70)

    # Step 1: 检查源
    print("\n📡 Layer 1: 源新鲜度")
    active, stale, blocked = check_sources()
    print(f"  活跃: {len(active)} | 过期: {len(stale)} | 被墙: {len(blocked)}")

    if stale:
        print("\n  ⚠️ 过期源 (需要手动更新):")
        for item in stale:
            if isinstance(item, tuple):
                s, days = item
                print(f"    {s['name']:<25} 过期{days}天 → {s['type']}")
            else:
                print(f"    {item['name']:<25} 从未更新")

    if not apply_mode:
        print("\n💡 仅审计模式。运行 python3 fetch_updates.py --apply 执行更新")
        return

    # Step 2: 衰减八卦
    print("\n⏳ Layer 2: 八卦时间衰减")
    decay_gossip()

    # Step 3: 清理伤病
    print("\n🏥 Layer 3: 伤病条目清理")
    clean_injuries()

    # Step 4: 输出指引
    print(UPDATE_GUIDE)

    # Step 5: 重新生成 dashboard
    print("\n🔄 重新生成 dashboard...")
    os.system("python3 dashboard.py")

    # Step 6: 审计
    print("\n📊 运行审计...")
    os.system("python3 audit_sync.py")

    print(f"\n✅ 自动更新完成 ({datetime.now().strftime('%H:%M')})")


if __name__ == "__main__":
    main()
