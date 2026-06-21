#!/usr/bin/env python3
"""
竞彩SP自动刷新 v1.0
赛前1-2天竞彩才开盘 → 每日运行此脚本自动抓取最新SP赔率
数据源: 中国竞彩官网 sporttery.cn (主) / nowscore (备)
用法: python3 fetch_sp_auto.py
"""
import json, urllib.request, sys
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
SP_FILE = DATA_DIR / "sp.json"

def fetch_sporttery(date_str):
    """从竞彩官网API获取SP数据"""
    url = f"https://webapi.sporttery.cn/gateway/jc/football/getMatchListV1.qry?matchPage=1&pcOrWap=1&matchBeginDate={date_str}&matchEndDate={date_str}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://m.sporttery.cn/",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        if data.get("success") and data.get("value"):
            return data["value"].get("matchList", [])
    except Exception as e:
        print(f"  ⚠️ sporttery API失败({date_str}): {e}")
    return []

def parse_sporttery_matches(match_list):
    """解析竞彩API返回的比赛数据 → sp.json格式"""
    updates = {}
    handicap = {}
    for m in match_list:
        match_id = f"{m.get('homeTeam','')}-{m.get('awayTeam','')}"
        updates[match_id] = {
            "home": float(m.get("spfHome", 0)),
            "draw": float(m.get("spfDraw", 0)),
            "away": float(m.get("spfAway", 0)),
            "single": m.get("single", 0) == 1,
        }
        # RQSPF
        if m.get("rqspfHome"):
            line = m.get("handicap", 0)
            handicap[match_id] = {
                "line": line,
                "home": float(m.get("rqspfHome", 0)),
                "draw": float(m.get("rqspfDraw", 0)),
                "away": float(m.get("rqspfAway", 0)),
            }
    return updates, handicap

def main():
    existing = json.load(open(SP_FILE)) if SP_FILE.exists() else {"matches": {}, "handicap": {}, "total_goals": {}}

    # 检查未来3天
    today = datetime.now()
    new_matches = {}
    new_handicap = {}

    for i in range(5):
        d = today + timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        print(f"📡 抓取 {date_str}...")
        matches = fetch_sporttery(date_str)
        if matches:
            ug, hg = parse_sporttery_matches(matches)
            new_matches.update(ug)
            new_handicap.update(hg)
            print(f"  ✅ {len(matches)}场")
        else:
            print(f"  ⏳ 未开盘")

    if not new_matches:
        print("\n⚠️ 无新SP数据")
        return

    # 合并: 新数据覆盖旧
    existing["matches"].update(new_matches)
    existing["handicap"].update(new_handicap)
    existing["updated"] = datetime.now().isoformat()
    existing["source"] = "竞彩官网 sporttery.cn (自动刷新)"

    json.dump(existing, open(SP_FILE, "w"), indent=2, ensure_ascii=False)
    print(f"\n✅ 更新完成: +{len(new_matches)}场SPF, +{len(new_handicap)}场RQSPF")
    print(f"   总计: {len(existing['matches'])}场SPF, {len(existing['handicap'])}场RQSPF")

if __name__ == "__main__":
    main()
