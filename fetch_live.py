#!/usr/bin/env python3
"""
实时比分抓取引擎 v1.0
=====================
尝试从多个来源获取进行中比赛的实时比分。

数据流: 来源 → live_scores.json → dashboard.py (LIVE显示) → browser

用法:
  python3 fetch_live.py              # 检查进行中比赛, 尝试抓取比分
  python3 fetch_live.py --manual     # 手动模式: 在终端输入比分
  python3 fetch_live.py --watch 30   # 守护模式: 每30秒自动抓取

手动更新 (知道比分时直接写入):
  python3 fetch_live.py --set POR-COD 2 0  # POR 2-0 COD
  python3 fetch_live.py --set ENG-CRO 1 1  # ENG 1-1 CRO
  python3 fetch_live.py --final POR-COD 3 1  # 标记为完赛, 自动写入 results.json
"""

import json, sys, os, time
from pathlib import Path
from datetime import datetime, date
from urllib.request import urlopen, Request
from urllib.error import URLError

DATA = Path(__file__).parent / "data"
MATCH_SCHEDULE = {
    "MEX-RSA":"6/11 23:00","KOR-CZE":"6/12 02:00","CAN-BIH":"6/13 03:00",
    "USA-PAR":"6/13 09:00","HAI-SCO":"6/14 09:00","AUS-TUR":"6/14 12:00",
    "BRA-MAR":"6/14 06:00","QAT-SUI":"6/14 03:00","GER-CUW":"6/15 04:00",
    "NED-JPN":"6/15 04:00","CIV-ECU":"6/15 07:00","SWE-TUN":"6/15 10:00",
    "ESP-CPV":"6/16 00:00","BEL-EGY":"6/16 03:00","KSA-URU":"6/16 06:00",
    "IRN-NZL":"6/16 09:00","FRA-SEN":"6/17 03:00","IRQ-NOR":"6/17 06:00",
    "ARG-ALG":"6/17 09:00","AUT-JOR":"6/17 12:00",
    "ENG-CRO":"6/18 04:00","GHA-PAN":"6/18 07:00",
    "POR-COD":"6/18 01:00","COL-UZB":"6/18 10:00",
    "CZE-RSA":"6/19 00:00","SUI-BIH":"6/19 03:00",
    "CAN-QAT":"6/19 06:00","MEX-KOR":"6/19 09:00",
}
FOTMOB_TEAM_IDS = {
    "POR": 45, "COD": 10529, "ENG": 757, "CRO": 1630,
    "GHA": 315, "PAN": 4623, "COL": 701, "UZB": 9583,
}


def get_results():
    with open(DATA / "results.json") as f:
        return json.load(f)


def get_live():
    with open(DATA / "live_scores.json") as f:
        return json.load(f)


def save_live(data):
    data["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(DATA / "live_scores.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def find_in_progress_matches():
    """找出所有已经开始但未在 results.json 中的比赛"""
    results = get_results()
    played = {f"{m['home']}-{m['away']}" for m in results["matches"]}
    now = datetime.now()
    today_str = now.strftime("%m/%d")  # e.g. "06/18"

    in_progress = []
    for match_id, time_str in MATCH_SCHEDULE.items():
        if match_id in played:
            continue  # 已完赛
        parts = time_str.split()
        match_date = parts[0]  # "6/18"
        match_time = parts[1]  # "04:00"

        # Parse to datetime
        try:
            month, day = match_date.split("/")
            hour, minute = match_time.split(":")
            match_dt = datetime(2026, int(month), int(day), int(hour), int(minute))
            # 比赛开始后2小时内视为进行中
            if match_dt <= now <= match_dt.replace(hour=match_dt.hour + 3):
                in_progress.append((match_id, time_str, match_dt))
        except:
            pass

    return in_progress


def try_fetch_fotmob(match_id):
    """尝试从 FotMob API 获取比分 (公开接口)"""
    home, away = match_id.split("-")
    hid = FOTMOB_TEAM_IDS.get(home)
    aid = FOTMOB_TEAM_IDS.get(away)
    if not hid or not aid:
        return None
    try:
        url = f"https://www.fotmob.com/api/matchDetails?matchId={hid}_{aid}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            header = data.get("header", {})
            status = header.get("status", {})
            if status.get("live"):
                return {
                    "home_goals": status.get("homeScore", 0),
                    "away_goals": status.get("awayScore", 0),
                    "minute": status.get("minutes", "?"),
                    "source": "fotmob"
                }
    except:
        pass
    return None


def set_score(match_id, home_goals, away_goals):
    """手动设置实时比分"""
    live = get_live()
    # Remove existing entry for this match
    live["matches_in_progress"] = [
        m for m in live["matches_in_progress"]
        if m["match_id"] != match_id
    ]
    live["matches_in_progress"].append({
        "match_id": match_id,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "minute": "LIVE",
        "source": "manual",
        "updated": datetime.now().strftime("%H:%M")
    })
    save_live(live)
    print(f"✅ {match_id} {home_goals}-{away_goals} (LIVE)")


def verify_ft_status(match_id):
    """多渠道确认比赛是否已终场。返回 (is_ft, source_count)"""
    confirmations = 0
    sources_checked = 0

    # FotMob API
    try:
        url = f"https://www.fotmob.com/api/matchDetails?matchId={match_id}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            status = data.get("header",{}).get("status",{})
            sources_checked += 1
            if status.get("finished") or status.get("started") and not status.get("live"):
                # Check if it was truly finished (not just "not live")
                if status.get("finished") or int(status.get("minutes","0") or 0) >= 90:
                    confirmations += 1
    except:
        pass

    # Time-based check: has enough time passed since kickoff?
    ts = MATCH_SCHEDULE.get(match_id, "")
    time_ok = False
    if ts:
        try:
            parts = ts.split(); m,d = parts[0].split("/"); h,mi = parts[1].split(":")
            kickoff = datetime(2026, int(m), int(d), int(h), int(mi))
            minutes_elapsed = (datetime.now() - kickoff).total_seconds() / 60
            time_ok = minutes_elapsed >= 95  # 90min + injury time buffer
        except:
            pass
    if time_ok:
        confirmations += 1

    return confirmations >= 2, confirmations


def finalize_match(match_id, home_goals, away_goals):
    """标记比赛为完赛 — 带安全检查，防止未终场写入"""
    from dashboard import auto_refresh

    force = "--force" in sys.argv

    if not force:
        # 安全检查1: 时间
        ts = MATCH_SCHEDULE.get(match_id, "")
        if ts:
            try:
                parts = ts.split(); m,d = parts[0].split("/"); h,mi = parts[1].split(":")
                kickoff = datetime(2026, int(m), int(d), int(h), int(mi))
                minutes_elapsed = (datetime.now() - kickoff).total_seconds() / 60
                if minutes_elapsed < 95:
                    print(f"⛔ 拒绝: 开球仅{minutes_elapsed:.0f}分钟, 比赛可能还未结束")
                    print(f"   如需强制写入, 加 --force")
                    return
            except:
                pass

        # 安全检查2: API确认终场状态
        is_ft, confirmations = verify_ft_status(match_id)
        if not is_ft:
            print(f"⛔ 拒绝: 终场确认不足 ({confirmations}/2源)")
            print(f"   请等待比赛完全结束(>95分钟+API确认FT)")
            print(f"   如需强制写入, 加 --force")
            return

    # 安全检查3 (force模式也执行): 提示
    existing_live = get_live()
    for lm in existing_live.get("matches_in_progress", []):
        if lm["match_id"] == match_id:
            old_hg = lm.get("home_goals", "?")
            old_ag = lm.get("away_goals", "?")
            if old_hg != home_goals or old_ag != away_goals:
                print(f"⚠️ 比分变化: {old_hg}-{old_ag} → {home_goals}-{away_goals}")
            break

    print(f"✅ 终场确认通过 → 写入赛果 {match_id} {home_goals}-{away_goals}")

    auto_refresh()
    results = get_results()
    home, away = match_id.split("-")
    score = f"{home_goals}-{away_goals}"

    # 判断胜负
    if home_goals > away_goals:
        outcome = "✅"; note = f"{home}胜{away}"
    elif home_goals < away_goals:
        outcome = "❌"; note = f"{away}胜{home}"
    else:
        outcome = "✅"; note = "平局"

    # 检查是否已存在（更新而非新增）
    existing_idx = None
    for i, m in enumerate(results["matches"]):
        if m["home"] == home and m["away"] == away:
            existing_idx = i
            break

    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = {
        "date": f"{date.today().month}/{date.today().day}",
        "home": home, "away": away,
        "score": score,
        "prediction_correct": outcome,
        "note": note
    }

    if existing_idx is not None:
        old = results["matches"][existing_idx]
        change_note = f"[{now_ts} 更新] 原: {old['score']}, 旧判: {old.get('prediction_correct','?')}"
        entry["note"] = f"{note} {change_note}"
        entry["changed_at"] = now_ts
        entry["original_score"] = old["score"]
        results["matches"][existing_idx] = entry
        print(f"⚠️ 覆盖已有赛果: {match_id} {old['score']} → {score}")
    else:
        results["matches"].append(entry)

    correct = sum(1 for m in results["matches"] if m["prediction_correct"] == "✅")
    total = len(results["matches"])
    results["direction_correct"] = correct
    results["direction_total"] = total
    results["direction_rate"] = round(correct / total * 100, 1)
    results["total_played"] = total
    results["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    with open(DATA / "results.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    groups = json.load(open(DATA / "groups.json"))
    for gid, g in groups.items():
        if home in g["standings"] and away in g["standings"]:
            hs, aw = g["standings"][home], g["standings"][away]
            hs["gf"] += home_goals; hs["ga"] += away_goals
            aw["gf"] += away_goals; aw["ga"] += home_goals
            hs["gd"] = hs["gf"] - hs["ga"]
            aw["gd"] = aw["gf"] - aw["ga"]
            if home_goals > away_goals:
                hs["w"] += 1; hs["p"] += 3; aw["l"] += 1
            elif home_goals < away_goals:
                aw["w"] += 1; aw["p"] += 3; hs["l"] += 1
            else:
                hs["d"] += 1; aw["d"] += 1; hs["p"] += 1; aw["p"] += 1
            break

    with open(DATA / "groups.json", "w") as f:
        json.dump(groups, f, indent=2, ensure_ascii=False)

    live = get_live()
    live["matches_in_progress"] = [
        m for m in live["matches_in_progress"]
        if m["match_id"] != match_id
    ]
    save_live(live)

    print(f"🏁 {match_id} {score} 已完赛 → results.json + groups.json 已更新")
    print(f"   正确率: {correct}/{total} = {results['direction_rate']}%")
    os.system("python3 dashboard.py")


def main():
    if "--set" in sys.argv:
        idx = sys.argv.index("--set")
        match_id = sys.argv[idx + 1]
        hg = int(sys.argv[idx + 2])
        ag = int(sys.argv[idx + 3])
        set_score(match_id, hg, ag)
        return

    if "--final" in sys.argv:
        idx = sys.argv.index("--final")
        match_id = sys.argv[idx + 1]
        hg = int(sys.argv[idx + 2])
        ag = int(sys.argv[idx + 3])
        finalize_match(match_id, hg, ag)
        return

    if "--manual" in sys.argv:
        print("手动比分输入模式 (输入 'done' 退出)")
        print("格式: <MATCH_ID> <主队进球> <客队进球>")
        print("示例: POR-COD 2 0")
        while True:
            try:
                line = input("\n> ").strip()
                if line.lower() == "done":
                    break
                parts = line.split()
                if len(parts) == 3:
                    set_score(parts[0], int(parts[1]), int(parts[2]))
                elif len(parts) == 4 and parts[3] == "final":
                    finalize_match(parts[0], int(parts[1]), int(parts[2]))
            except (KeyboardInterrupt, EOFError):
                break
        return

    # Auto mode: check for live matches
    in_progress = find_in_progress_matches()
    if not in_progress:
        print("📅 当前无进行中比赛")
        return

    print(f"🔍 发现 {len(in_progress)} 场可能在进行中的比赛:")
    for match_id, time_str, dt in in_progress:
        print(f"  {match_id} ({time_str})")

    # Try to fetch scores
    live = get_live()
    for match_id, time_str, dt in in_progress:
        score = try_fetch_fotmob(match_id)
        if score:
            live["matches_in_progress"] = [
                m for m in live["matches_in_progress"]
                if m["match_id"] != match_id
            ]
            live["matches_in_progress"].append({
                "match_id": match_id,
                "home_goals": score["home_goals"],
                "away_goals": score["away_goals"],
                "minute": str(score["minute"]),
                "source": score["source"],
                "updated": datetime.now().strftime("%H:%M")
            })
            print(f"  ✅ {match_id} {score['home_goals']}-{score['away_goals']} (第{score['minute']}分钟)")
        else:
            print(f"  ⚠️ {match_id} 无法获取实时比分 (请用 --set 手动设置)")

    save_live(live)


if __name__ == "__main__":
    main()
