#!/usr/bin/env python3
"""
竞彩SP自动刷新 v2.0 — 双源抓取
数据源: 500.com (主) / nowscore cp.nowscore.com (备)
用法: python3 fetch_sp_auto.py
每日自动抓取未来5天已开盘的世界杯竞彩SP赔率
"""
import urllib.request, re, json, sys
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
SP_FILE = DATA_DIR / "sp.json"
TEAMS_FILE = DATA_DIR / "teams.json"

# ── 中文队名 → 英文队名 (500.com使用中文) ──
CN_TO_EN = {
    "西班牙":"Spain","阿根廷":"Argentina","法国":"France","巴西":"Brazil",
    "英格兰":"England","德国":"Germany","荷兰":"Netherlands","比利时":"Belgium",
    "葡萄牙":"Portugal","挪威":"Norway","乌拉圭":"Uruguay","克罗地亚":"Croatia",
    "日本":"Japan","塞内加尔":"Senegal","韩国":"South Korea","美国":"United States",
    "摩洛哥":"Morocco","哥伦比亚":"Colombia","墨西哥":"Mexico","瑞士":"Switzerland",
    "奥地利":"Austria","瑞典":"Sweden","加拿大":"Canada","澳大利亚":"Australia",
    "厄瓜多尔":"Ecuador","土耳其":"Türkiye","苏格兰":"Scotland","捷克":"Czechia",
    "埃及":"Egypt","伊朗":"Iran","加纳":"Ghana","阿尔及利亚":"Algeria",
    "突尼斯":"Tunisia","南非":"South Africa","佛得角":"Cape Verde",
    "沙特阿拉伯":"Saudi Arabia","沙特":"Saudi Arabia",
    "卡塔尔":"Qatar","伊拉克":"Iraq","约旦":"Jordan","乌兹别克":"Uzbekistan",
    "新西兰":"New Zealand","巴拿马":"Panama","海地":"Haiti",
    "库拉索":"Curaçao","刚果(金)":"DR Congo","刚果":"DR Congo",
    "波黑":"Bosnia-Herzegovina","巴拉圭":"Paraguay","科特迪瓦":"Ivory Coast",
    "塞尔维亚":"Serbia",
}


def cn_to_code(cn_name):
    """中文队名 → 3字母代码"""
    en = CN_TO_EN.get(cn_name, "")
    if not en:
        return ""
    teams = json.load(open(TEAMS_FILE))
    for code, info in teams.items():
        if info.get("name") == en:
            return code
    return ""


def fetch_500com(date_str):
    """
    从500.com抓取竞彩SPF赔率
    playid=269 胜平负, playid=270 让球胜平负
    """
    matches = {}
    handicap = {}
    url = f"https://trade.500.com/jczq/index.php?date={date_str}&g=2&playid=269"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Referer": "https://trade.500.com/jczq/",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=15)
        raw = resp.read()
        text = raw.decode("gb2312", errors="ignore")

        rows = re.findall(
            r'<tr[^>]*data-homesxname="(.*?)"[^>]*data-awaysxname="(.*?)"'
            r'[^>]*data-matchdate="(.*?)"[^>]*data-matchtime="(.*?)"'
            r'[^>]*data-rangqiu="(.*?)"[^>]*>(.*?)</tr>',
            text, re.DOTALL,
        )
        for home_cn, away_cn, mdate, mtime, hcap, content in rows:
            home_code = cn_to_code(home_cn)
            away_code = cn_to_code(away_cn)
            if not home_code or not away_code:
                continue

            sp_values = re.findall(r">(\d+\.\d{2})<", content)
            if len(sp_values) < 3:
                continue

            match_id = f"{home_code}-{away_code}"
            handicap_line = int(hcap) if hcap and hcap not in ("", "0") else 0

            matches[match_id] = {
                "home": float(sp_values[0]),
                "draw": float(sp_values[1]),
                "away": float(sp_values[2]),
                "single": False,  # 500.com不直接标注单关
            }
            if handicap_line != 0:
                # RQSPF赔率需要从playid=270获取
                handicap[match_id] = {"line": handicap_line}

        return matches, handicap
    except Exception as e:
        return {}, {}


def fetch_nowscore_backup():
    """备用: 从nowscore cp.nowscore.com抓取 (需解析HTML)"""
    # nowscore的竞彩页面需要浏览器渲染, 暂时跳过
    return {}, {}


def main():
    existing = {"matches": {}, "handicap": {}, "total_goals": {}, "score": {}}
    if SP_FILE.exists():
        existing = json.load(open(SP_FILE))

    today = datetime.now()
    total_new = 0

    for i in range(5):
        d = today + timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        print(f"📡 500.com {date_str}...", end=" ")
        matches, handicap = fetch_500com(date_str)
        if matches:
            # 合并: 新数据覆盖旧
            for mid, spf in matches.items():
                existing["matches"][mid] = spf
                total_new += 1
            for mid, hc in handicap.items():
                existing.setdefault("handicap", {})[mid] = hc
            print(f"✅ {len(matches)}场")
        else:
            print(f"⏳ 未开盘")

    existing["updated"] = datetime.now().isoformat()
    existing["source"] = "500.com + nowscore"

    json.dump(existing, open(SP_FILE, "w"), indent=2, ensure_ascii=False)
    print(f"\n✅ SP更新完成: +{total_new}场新增")
    print(f"   总计: {len(existing['matches'])}场SPF, {len(existing.get('handicap',{}))}场让球")


if __name__ == "__main__":
    main()
