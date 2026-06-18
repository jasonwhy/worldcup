#!/usr/bin/env python3
"""
实时比分自动监控 v1.0
=====================
持续监控进行中比赛, 自动抓取比分变化, 更新 live_scores.json
并在比分变化时自动 git commit + push 到 GitHub

用法:
  python3 live_watcher.py          # 前台运行, 每60秒检测
  python3 live_watcher.py --daemon # 后台守护模式
  python3 live_watcher.py --once   # 仅检测一次, 适合 cron
"""

import json, sys, os, time
from pathlib import Path
from datetime import datetime
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

# FotMob match ID mapping for teams we can query
FOTMOB_MAP = {
    "COL-UZB": "colombia-uzbekistan",
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

def find_in_progress():
    """找出所有已开球但未在 results.json 中的比赛"""
    results = get_results()
    played = {f"{m['home']}-{m['away']}" for m in results["matches"]}
    now = datetime.now()
    in_progress = []
    for mid, ts in MATCH_SCHEDULE.items():
        if mid in played: continue
        try:
            parts = ts.split()
            m, d = parts[0].split("/")
            h, mi = parts[1].split(":")
            kickoff = datetime(2026, int(m), int(d), int(h), int(mi))
            # 开赛后3.5小时内
            end_time = kickoff.replace(hour=kickoff.hour+3, minute=kickoff.minute+30)
            if kickoff <= now <= end_time:
                minutes = int((now - kickoff).total_seconds() / 60)
                in_progress.append((mid, minutes, ts))
        except: pass
    return in_progress

def try_fetch_score(match_id):
    """尝试从公开API获取实时比分"""
    # FotMob API
    try:
        url = f"https://www.fotmob.com/api/matchDetails?matchId={match_id}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            header = data.get("header", {})
            status = header.get("status", {})
            if status.get("started") or status.get("live"):
                return {
                    "home_goals": status.get("homeScore", 0),
                    "away_goals": status.get("awayScore", 0),
                    "minute": status.get("minutes", "?"),
                    "finished": status.get("finished", False),
                    "source": "fotmob"
                }
    except: pass

    # Fallback: Sofascore
    try:
        url = f"https://api.sofascore.com/api/v1/event/{match_id}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            event = data.get("event", {})
            if event.get("status", {}).get("type") in ("inprogress", "live"):
                hs = event.get("homeScore", {})
                aw = event.get("awayScore", {})
                return {
                    "home_goals": hs.get("current", 0),
                    "away_goals": aw.get("current", 0),
                    "minute": event.get("status", {}).get("description", "?"),
                    "finished": False,
                    "source": "sofascore"
                }
    except: pass

    return None

def update_minute_only(live):
    """仅更新已记录比分的时间（无实数据时的保底方案）"""
    now = datetime.now()
    changed = False
    for lm in live.get("matches_in_progress", []):
        mid = lm["match_id"]
        ts = MATCH_SCHEDULE.get(mid, "")
        if not ts: continue
        try:
            parts = ts.split()
            m, d = parts[0].split("/")
            h, mi = parts[1].split(":")
            kickoff = datetime(2026, int(m), int(d), int(h), int(mi))
            minutes = int((now - kickoff).total_seconds() / 60)
            if 0 <= minutes <= 120 and str(minutes) != str(lm.get("minute", "")):
                lm["minute"] = str(minutes)
                lm["updated"] = now.strftime("%H:%M")
                changed = True
        except: pass
    return changed

def auto_commit_push():
    """自动提交并推送到 GitHub"""
    import subprocess
    try:
        subprocess.run(["git", "add", "data/live_scores.json"],
                      cwd=Path(__file__).parent, capture_output=True, timeout=10)
        result = subprocess.run(
            ["git", "commit", "-m", f"Live: auto-refresh scores ({datetime.now().strftime('%H:%M')})"],
            cwd=Path(__file__).parent, capture_output=True, timeout=10)
        if "nothing to commit" not in result.stdout.decode():
            subprocess.run(["git", "push"], cwd=Path(__file__).parent,
                          capture_output=True, timeout=30)
            return True
    except: pass
    return False

def run_once():
    """单次检测循环"""
    in_progress = find_in_progress()
    if not in_progress:
        # Check if live_scores has stale entries (matches that should be over)
        live = get_live()
        if live.get("matches_in_progress"):
            now = datetime.now()
            active = []
            for lm in live["matches_in_progress"]:
                ts = MATCH_SCHEDULE.get(lm["match_id"], "")
                try:
                    parts = ts.split(); m,d = parts[0].split("/"); h,mi = parts[1].split(":")
                    kickoff = datetime(2026,int(m),int(d),int(h),int(mi))
                    if kickoff.replace(hour=kickoff.hour+3) > now:
                        active.append(lm)
                except:
                    active.append(lm)
            if len(active) < len(live["matches_in_progress"]):
                live["matches_in_progress"] = active
                save_live(live)
        return False

    live = get_live()
    changed = False

    for mid, minutes, ts in in_progress:
        # Try real API first
        score = try_fetch_score(mid)
        if score:
            existing = next((lm for lm in live["matches_in_progress"] if lm["match_id"] == mid), None)
            if not existing or existing.get("home_goals") != score["home_goals"] or existing.get("away_goals") != score["away_goals"]:
                # Remove old entry
                live["matches_in_progress"] = [lm for lm in live["matches_in_progress"] if lm["match_id"] != mid]
                live["matches_in_progress"].append({
                    "match_id": mid, "home_goals": score["home_goals"], "away_goals": score["away_goals"],
                    "minute": str(score["minute"]), "source": score["source"],
                    "updated": datetime.now().strftime("%H:%M"),
                    "finished": score.get("finished", False)
                })
                changed = True
                emoji = "🏁" if score.get("finished") else "⚽"
                print(f"{emoji} {mid} {score['home_goals']}-{score['away_goals']} ({score['minute']}') via {score['source']}")
        else:
            # No real data: ensure at least minute tracking
            existing = next((lm for lm in live["matches_in_progress"] if lm["match_id"] == mid), None)
            if not existing:
                live["matches_in_progress"].append({
                    "match_id": mid, "home_goals": 0, "away_goals": 0,
                    "minute": str(minutes), "source": "auto",
                    "updated": datetime.now().strftime("%H:%M"),
                    "note": "等待实时数据..."
                })
                changed = True
                print(f"🔴 {mid} 0-0 ({minutes}') — 等待数据源")

    if changed:
        save_live(live)
        # Trigger dashboard regen via file watcher (if running)
        auto_commit_push()

    # Update minute tracking for existing entries
    if update_minute_only(live):
        save_live(live)

    return changed

def main():
    if "--once" in sys.argv:
        run_once()
        return

    print("=" * 60)
    print("  实时比分自动监控 v1.0")
    print(f"  启动: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("  每60秒检测 | 比分变化自动推送GitHub")
    print("=" * 60)

    while True:
        try:
            changed = run_once()
            if changed:
                print(f"  ✅ {datetime.now().strftime('%H:%M:%S')} 已更新")
        except Exception as e:
            print(f"  ⚠️ 检测异常: {e}")
        time.sleep(60)


if __name__ == "__main__":
    main()
