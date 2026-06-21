"""
竞彩投注方案自动生成引擎 v3.1
新增: SP动态读取 + 截止时间检查 + 今日不推荐机制
"""
import json, math
from pathlib import Path
from datetime import datetime
from .predictor import predict

# 中文名映射
CN_NAME = {
    "France":"法国","Spain":"西班牙","Argentina":"阿根廷","England":"英格兰",
    "Brazil":"巴西","Portugal":"葡萄牙","Germany":"德国","Netherlands":"荷兰",
    "Belgium":"比利时","Norway":"挪威","Morocco":"摩洛哥","Colombia":"哥伦比亚",
    "Mexico":"墨西哥","South Korea":"韩国","United States":"美国","Uruguay":"乌拉圭",
    "Croatia":"克罗地亚","Japan":"日本","Senegal":"塞内加尔","Switzerland":"瑞士",
    "Austria":"奥地利","Sweden":"瑞典","Canada":"加拿大","Australia":"澳大利亚",
    "Ecuador":"厄瓜多尔","Türkiye":"土耳其","Scotland":"苏格兰","Czechia":"捷克",
    "Egypt":"埃及","Iran":"伊朗","Ghana":"加纳","Algeria":"阿尔及利亚",
    "Tunisia":"突尼斯","South Africa":"南非","Cape Verde":"佛得角",
    "Saudi Arabia":"沙特","Qatar":"卡塔尔","Iraq":"伊拉克","Jordan":"约旦",
    "Uzbekistan":"乌兹别克","New Zealand":"新西兰","Panama":"巴拿马",
    "Haiti":"海地","Curaçao":"库拉索","DR Congo":"刚果(金)","Congo DR":"刚果(金)",
    "Bosnia-Herzegovina":"波黑","Bosnia":"波黑","Paraguay":"巴拉圭",
    "Ivory Coast":"科特迪瓦","Cote dIvoire":"科特迪瓦",
}

# 国旗映射
FLAG = {
    "France": "🇫🇷", "Spain": "🇪🇸", "Argentina": "🇦🇷", "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Brazil": "🇧🇷", "Portugal": "🇵🇹", "Germany": "🇩🇪", "Netherlands": "🇳🇱",
    "Belgium": "🇧🇪", "Norway": "🇳🇴", "Morocco": "🇲🇦", "Colombia": "🇨🇴",
    "Mexico": "🇲🇽", "South Korea": "🇰🇷", "United States": "🇺🇸", "Uruguay": "🇺🇾",
    "Croatia": "🇭🇷", "Japan": "🇯🇵", "Senegal": "🇸🇳", "Switzerland": "🇨🇭",
    "Austria": "🇦🇹", "Sweden": "🇸🇪", "Canada": "🇨🇦", "Australia": "🇦🇺",
    "Ecuador": "🇪🇨", "Türkiye": "🇹🇷", "Scotland": "🏴", "Czechia": "🇨🇿",
    "Serbia": "🇷🇸", "Egypt": "🇪🇬", "Iran": "🇮🇷", "Côte d'Ivoire": "🇨🇮",
    "Ivory Coast": "🇨🇮", "Ghana": "🇬🇭", "Algeria": "🇩🇿", "Tunisia": "🇹🇳",
    "South Africa": "🇿🇦", "Cape Verde": "🇨🇻", "Saudi Arabia": "🇸🇦",
    "Qatar": "🇶🇦", "Iraq": "🇮🇶", "Jordan": "🇯🇴", "Uzbekistan": "🇺🇿",
    "New Zealand": "🇳🇿", "Panama": "🇵🇦", "Haiti": "🇭🇹", "Curaçao": "🇨🇼",
    "DR Congo": "🇨🇩", "Bosnia-Herzegovina": "🇧🇦", "Paraguay": "🇵🇾",
    "Congo DR": "🇨🇩",
}
def flag(name): return FLAG.get(name, "🏳️")
def fn(name):
    """带国旗的名称，自动识别'队名+胜/平/负'后缀"""
    for k in FLAG:
        if name.startswith(k):
            return f"{FLAG[k]} {name}"
    return f"🏳️ {name}"

DATA_DIR = Path(__file__).parent.parent / "data"

RULE = {
    # 玩法上限 (竞彩官方规则)
    "WDL_max_parlay": 8, "handicap_max_parlay": 8,
    "total_goals_max": 6, "score_max_parlay": 4, "htft_max_parlay": 4,
    # 混合过关: 木桶原则-以关数上限最低玩法为准
    # 奖金规则
    "base_bet": 2, "return_rate": 0.71, "max_multiplier": 99,
    "max_ticket": 20000, "max_single_bet": 2000, "max_daily": 10000,  # 2025新规
    "tax_threshold": 10000,
    "prize_2_3": 200000, "prize_4_5": 500000,
    "prize_6_8": 5000000, "prize_9_plus": 2000000,  # 2025新规: 9串+上限200万
    # 投注规则 (2025新规)
    "match_duration": "90分钟+伤停补时",
    "deadline": "开球前1分钟",   # 竞彩实际: 单关截止开球前, 串关截止最早一场开球前
    # 预算分配
    "budget": 200,
    "banker_pct": 0.15, "parlay_pct": 0.25,
    "rqspf_pct": 0.15, "balanced_pct": 0.10,
    "flexi_pct": 0.15, "aggressive_pct": 0.10,
    # 单关场次: 动态从SP数据读取, 此列表为兜底
    "single_matches": [],
}

# 比赛时间表 (北京时间)
MATCH_SCHEDULE = {
    "MEX-RSA": "6/11 23:00", "KOR-CZE": "6/12 02:00",
    "CAN-BIH": "6/13 03:00", "USA-PAR": "6/13 09:00",
    "HAI-SCO": "6/14 09:00", "AUS-TUR": "6/14 12:00",
    "BRA-MAR": "6/14 06:00", "QAT-SUI": "6/14 03:00",
    "GER-CUW": "6/15 04:00", "NED-JPN": "6/15 04:00",
    "CIV-ECU": "6/15 07:00", "SWE-TUN": "6/15 10:00",
    "ESP-CPV": "6/16 00:00", "BEL-EGY": "6/16 03:00",
    "KSA-URU": "6/16 06:00", "IRN-NZL": "6/16 09:00",
    "FRA-SEN": "6/17 03:00", "IRQ-NOR": "6/17 06:00",
    "ARG-ALG": "6/17 09:00", "AUT-JOR": "6/17 12:00",
    "ENG-CRO": "6/18 04:00", "GHA-PAN": "6/18 07:00",
    "POR-COD": "6/18 01:00", "COL-UZB": "6/18 10:00",
    "CZE-RSA": "6/19 00:00", "SUI-BIH": "6/19 03:00",
    "CAN-QAT": "6/19 06:00", "MEX-KOR": "6/19 09:00",
    # 6/20 D+C组第二轮
    "USA-AUS": "6/20 03:00", "SCO-MAR": "6/20 06:00",
    "BRA-HAI": "6/20 09:00", "TUR-PAR": "6/20 10:00",
    # 6/21 E+F组第二轮
    "GER-CIV": "6/21 03:00", "ECU-CUW": "6/21 03:00",
    "NED-SWE": "6/21 06:00", "JPN-TUN": "6/21 06:00",
    # 6/22 G+H组第二轮
    "BEL-IRN": "6/22 03:00", "EGY-NZL": "6/22 03:00",
    "ESP-KSA": "6/22 06:00", "CPV-URU": "6/22 06:00",
}

THRESHOLD = {
    "conservative_min_delta": 10,
    "conservative_max_cold_rank": 2,
    "conservative_min_prob": 40,     # 精准阈值, 避免边界排除
    "conservative_min_draw_prob": 45,  # 平局方向需更高概率才纳入稳健池
    "banker_min_delta": 25,
    "banker_min_prob": 50,
    "exclude_confidence_text": "低",
    "exclude_min_cold_rank": 3,
}

# 让球盘映射
HANDICAP_MAP = {
    35: "(-2)", 25: "(-1)", 15: "(-1)",
    10: "(-0.5)", 5: "(-0.5)", 0: "(平手)",
}

# 让球胜平负(RQSPF) 方向判断
def rqspf_pick(home_xg: float, away_xg: float, handicap_line: int, cn_home: str, cn_away: str) -> dict:
    """
    根据模型xG和让球盘口判断RQSPF方向
    handicap_line: 负数=主队让球, 正数=主队受让
    返回: {direction, pick_name, odds_key, confidence}
    """
    model_diff = home_xg - away_xg
    adjusted = model_diff + handicap_line  # handicap_line为负(让球), 调整后diff变小

    hcap = handicap_line  # 负数=主让, 正数=主受
    if adjusted > 0.5:
        return {"direction": "home", "pick": f"{cn_home}({hcap})让球胜",
                "pick_short": "让球主胜", "confidence": "高" if adjusted > 1.0 else "中"}
    elif adjusted < -0.5:
        if hcap < 0:
            pick_str = f"{cn_away}(+{abs(hcap)})让球胜"
        else:
            pick_str = f"{cn_away}({hcap})让球胜"
        return {"direction": "away", "pick": pick_str,
                "pick_short": "让球客胜", "confidence": "高" if adjusted < -1.0 else "中"}
    else:
        return {"direction": "draw", "pick": f"{cn_home}({hcap})让球平",
                "pick_short": "让球平", "confidence": "中"}

# 总进球数预测
def tg_predict(total_xg: float) -> dict:
    """
    模型xG → 总进球数选项
    返回: {primary, secondary, odds_key}
    """
    tg = total_xg
    if tg < 0.8: return {"primary": "0", "secondary": "1", "odds_key": "0"}
    elif tg < 1.5: return {"primary": "1", "secondary": "2", "odds_key": "1"}
    elif tg < 2.2: return {"primary": "2", "secondary": "1", "odds_key": "2"}
    elif tg < 2.8: return {"primary": "2", "secondary": "3", "odds_key": "2"}
    elif tg < 3.3: return {"primary": "3", "secondary": "2", "odds_key": "3"}
    elif tg < 3.8: return {"primary": "3", "secondary": "4", "odds_key": "3"}
    elif tg < 4.3: return {"primary": "4", "secondary": "3", "odds_key": "4"}
    elif tg < 4.8: return {"primary": "4", "secondary": "5", "odds_key": "4"}
    elif tg < 5.5: return {"primary": "5", "secondary": "4", "odds_key": "5"}
    elif tg < 6.5: return {"primary": "6", "secondary": "5", "odds_key": "6"}
    else: return {"primary": "7+", "secondary": "6", "odds_key": "7+"}


def load_json(name):
    with open(DATA_DIR / name, "r") as f:
        return json.load(f)


def cold_rank(alert: str) -> int:
    if "高" in alert: return 3
    if "中" in alert: return 2
    if "低" in alert: return 1
    return 0


# SP数据从 sp.json 动态读取（来源：网易彩票 sports.163.com/caipiao）
def _load_sp():
    sp_path = DATA_DIR / "sp.json"
    if sp_path.exists():
        with open(sp_path) as f:
            return json.load(f)
    return {"matches": {}, "handicap": {}, "total_goals": {}, "score": {}}

def _get_sp() -> dict:
    return _load_sp()

REAL_SP = lambda: _get_sp().get("matches", {})
REAL_HANDICAP_SP = lambda: _get_sp().get("handicap", {})
REAL_TOTAL_GOALS_SP = lambda: _get_sp().get("total_goals", {})
REAL_SCORE_SP = lambda: _get_sp().get("score", {})


def _model_odds(prob: float) -> float:
    if prob <= 0: return 1.0
    return round(1.0 / (prob / 100) * 0.71, 2)


def _sp_data():
    """统一获取SP数据，自动刷新"""
    return _get_sp()

def _match_sp(match_id: str) -> dict:
    sp = _sp_data()
    m = sp.get("matches", {}).get(match_id)
    if m: return m
    # 反向查找并交换主客赔率: EGY-NZL → NZL-EGY
    rev = "-".join(match_id.split("-")[::-1])
    rev_m = sp.get("matches", {}).get(rev, {})
    if rev_m:
        swapped = dict(rev_m)
        if "home" in swapped and "away" in swapped:
            swapped["home"], swapped["away"] = swapped["away"], swapped["home"]
        return swapped
    return {}

def _match_handicap_sp(match_id: str) -> dict:
    sp = _sp_data()
    m = sp.get("handicap", {}).get(match_id)
    if m: return m
    rev = "-".join(match_id.split("-")[::-1])
    rev_m = sp.get("handicap", {}).get(rev, {})
    if rev_m:
        swapped = dict(rev_m)
        if "home" in swapped and "away" in swapped:
            swapped["home"], swapped["away"] = swapped["away"], swapped["home"]
        if "line" in swapped:
            swapped["line"] = -swapped["line"]  # 让球方向反转
        return swapped
    return {}

def _match_tg_sp(match_id: str) -> dict:
    sp = _sp_data()
    # 1) 从 total_goals 专用字典查找
    m = sp.get("total_goals", {}).get(match_id)
    if m: return m
    rev = "-".join(match_id.split("-")[::-1])
    m = sp.get("total_goals", {}).get(rev, {})
    if m: return m
    # 2) 从 match 条目内嵌的 total_goals 查找
    match_data = _match_sp(match_id)
    if match_data and match_data.get("total_goals"):
        return match_data["total_goals"]
    return {}

def _match_score_sp(match_id: str) -> dict:
    sp = _sp_data()
    m = sp.get("score", {}).get(match_id)
    if m: return m
    rev = "-".join(match_id.split("-")[::-1])
    return sp.get("score", {}).get(rev, {})

def _is_single_match(match_id: str) -> bool:
    """从SP数据动态判断是否为单关场次"""
    return _match_sp(match_id).get("single", False)

def _check_deadline(match_id: str) -> tuple:
    """检查投注截止时间。返回 (can_bet, reason)"""
    time_str = MATCH_SCHEDULE.get(match_id, "")
    if not time_str:
        return False, "无赛程"
    try:
        parts = time_str.split()
        m, d = parts[0].split("/")
        h, mi = parts[1].split(":")
        kickoff = datetime(2026, int(m), int(d), int(h), int(mi))
        now = datetime.now()
        minutes_left = (kickoff - now).total_seconds() / 60
        if minutes_left < 0:
            return False, "已开球"
        if minutes_left < 15:
            return False, f"距开球仅{minutes_left:.0f}分钟(需>15分钟)"
        return True, f"距开球{minutes_left:.0f}分钟"
    except:
        return False, "时间解析失败"

def est_odds(prob: float, bet_type: str = "wdl", match_id: str = None,
             pick: str = None, direction: str = None) -> float:
    """赔率估算：优先竞彩官方SP，无数据时模型反推"""
    sp = _match_sp(match_id) if match_id else {}
    if sp and bet_type == "wdl":
        if direction == "home": return sp.get("home", _model_odds(prob))
        if direction == "away": return sp.get("away", _model_odds(prob))
        if direction == "draw": return sp.get("draw", _model_odds(prob))
        if pick:
            if "主胜" in str(pick): return sp.get("home", _model_odds(prob))
            if "客胜" in str(pick): return sp.get("away", _model_odds(prob))
            if "平" in str(pick): return sp.get("draw", _model_odds(prob))
    tg_sp_val = _match_tg_sp(match_id) if match_id else {}
    if tg_sp_val and bet_type == "total_goals":
        tg = str(int(str(pick).replace("总进球","").replace("球",""))) if pick else "2"
        return tg_sp_val.get(tg, 3.20)
    score_sp = _match_score_sp(match_id) if match_id else {}
    if score_sp and bet_type == "score":
        return score_sp.get(str(pick), round(1.0/0.10*0.71, 1))
    return _model_odds(prob)


def est_handicap(score_gap: float) -> str:
    """根据模型分差推断合理让球盘"""
    gap = abs(score_gap)
    for threshold, handicap in sorted(HANDICAP_MAP.items(), reverse=True):
        if gap >= threshold:
            return handicap
    return "(平手)"


def classify_match(match_id: str, p: dict) -> dict:
    r = p["prediction"]
    h, a = p["home"], p["away"]
    delta = abs(p["delta"])
    w, d, l = r["win_pct"], r["draw_pct"], r["lose_pct"]

    if w > d and w > l:
        cn_name = CN_NAME.get(h["name"], h["name"])
        direction, dir_prob, dir_name = "home", w, f"{flag(h['name'])} {cn_name}胜"
        handicap_pick = f"{flag(h['name'])} {cn_name}{est_handicap(p['delta'])}胜"
    elif l > w and l > d:
        cn_name = CN_NAME.get(a["name"], a["name"])
        direction, dir_prob, dir_name = "away", l, f"{flag(a['name'])} {cn_name}胜"
        handicap_pick = f"{flag(a['name'])} {cn_name}{est_handicap(-p['delta'])}胜"
    else:
        direction, dir_prob, dir_name = "draw", d, "平局"
        handicap_pick = "平局"

    cr = cold_rank(r["cold_alert"])

    draw_prob_ok = (direction == "draw" and dir_prob >= THRESHOLD.get("conservative_min_draw_prob", 45))
    win_ok = (direction != "draw" and dir_prob >= THRESHOLD["conservative_min_prob"])
    is_conservative = (
        delta >= THRESHOLD["conservative_min_delta"]
        and cr <= THRESHOLD["conservative_max_cold_rank"]
        and THRESHOLD["exclude_confidence_text"] not in r["confidence"]
        and (win_ok or draw_prob_ok)
    )

    is_banker = (
        delta >= THRESHOLD["banker_min_delta"]
        and cr <= THRESHOLD["conservative_max_cold_rank"]
        and dir_prob >= THRESHOLD["banker_min_prob"]
        and THRESHOLD["exclude_confidence_text"] not in r["confidence"]
        and direction != "draw"
    )

    is_excluded = (
        THRESHOLD["exclude_confidence_text"] in r["confidence"]
        or cr >= THRESHOLD["exclude_min_cold_rank"]
        or (dir_prob < 30)
    )

    top_score = r["top_scores"][0]["score"]
    tg = sum(map(int, top_score.split("-")))
    total_goals_signal = tg if 1 <= tg <= 3 else None

    # 让球盘建议
    handicap_advice = None
    if direction != "draw" and delta >= 25:
        handicap_advice = {
            "line": est_handicap(p["delta"] if direction == "home" else -p["delta"]),
            "pick": handicap_pick,
            "reason": f"Δ={delta:.0f}, 让球盘可提升赔率至1.80+"
        }

    # 构建中文名 + 国旗的比赛名称 + 开赛时间
    parts = p["match"].split(" vs ")
    if len(parts) == 2:
        cn_h = CN_NAME.get(parts[0], parts[0])
        cn_a = CN_NAME.get(parts[1], parts[1])
        flagged_match = f"{flag(parts[0])} {cn_h} vs {flag(parts[1])} {cn_a}"
    else:
        flagged_match = p["match"]
        cn_h, cn_a = parts[0] if len(parts)==2 else ("","")
    kickoff = MATCH_SCHEDULE.get(match_id, "")

    # RQSPF (让球胜平负) 预测
    rqspf = None
    hsp = _match_handicap_sp(match_id)
    if not hsp or hsp.get("line") is None:
        # fallback: 检查matches中的handicap字段(只有line, 无odds)
        msp = _match_sp(match_id)
        if msp and msp.get("handicap") is not None:
            hsp = {"line": msp["handicap"], "home": 0, "draw": 0, "away": 0}
    if hsp and hsp.get("line") is not None:
        line = hsp["line"]
        rqspf = rqspf_pick(r["xg_home"], r["xg_away"], line,
                           f"{flag(parts[0])} {cn_h}" if len(parts)==2 else cn_h,
                           f"{flag(parts[1])} {cn_a}" if len(parts)==2 else cn_a)
        rqspf["handicap_line"] = line
        rqspf["adjusted_diff"] = round(r["xg_home"] - r["xg_away"] + line, 2)
        real_odds = hsp.get(rqspf["direction"], 0)
        if real_odds > 0:
            rqspf["odds"] = real_odds
        else:
            # 无真实SP时估算: 让球后概率越明确, 赔率越低
            adj_abs = abs(rqspf["adjusted_diff"])
            rqspf_prob = min(65, max(30, 30 + adj_abs * 18))
            rqspf["odds"] = round(1.0 / (rqspf_prob / 100) * 0.71, 2)
            rqspf["odds_estimated"] = True

    # 总进球数预测
    tg_pred = tg_predict(r["total_xg"])
    tg_sp = _match_tg_sp(match_id)
    tg_odds = tg_sp.get(tg_pred["odds_key"], 3.30) if tg_sp else 3.30
    tg_pred["odds"] = tg_odds

    # 半全场预测 (基于xG对比 + SP方向)
    htft = None
    match_sp_data = _match_sp(match_id)
    if match_sp_data and match_sp_data.get("half_full"):
        hf = match_sp_data["half_full"]
        if direction == "home":
            htft_pick = "胜胜" if r["xg_home"] > r["xg_away"] * 1.5 else "平胜"
        elif direction == "away":
            htft_pick = "负负" if r["xg_away"] > r["xg_home"] * 1.5 else "平负"
        else:
            htft_pick = "平平"
        htft = {"pick": htft_pick, "odds": hf.get(htft_pick, 5.0)}

    return {
        "match_id": match_id, "match_name": flagged_match, "kickoff": kickoff,
        "direction": direction, "dir_name": dir_name, "dir_prob": dir_prob,
        "wdl": f"{w:.0f}/{d:.0f}/{l:.0f}", "delta": p["delta"],
        "confidence": r["confidence"], "cold_alert": r["cold_alert"], "cold_rank": cr,
        "top_score": top_score, "top3_scores": [s["score"] for s in r["top_scores"][:3]],
        "total_xg": r["total_xg"], "total_goals_signal": total_goals_signal,
        "xg_home": r["xg_home"], "xg_away": r["xg_away"],
        "is_conservative": is_conservative, "is_banker": is_banker,
        "is_usable": not is_excluded, "is_excluded": is_excluded,
        "handicap_advice": handicap_advice,
        "home_gossip": h["gossip"], "away_gossip": a["gossip"],
        # v5.0 竞彩全玩法
        "rqspf": rqspf,
        "tg_pred": tg_pred,
        "htft": htft,
        "cn_home": cn_h, "cn_away": cn_a,
    }


def compute_value(match_id: str, direction: str, model_prob: float) -> dict:
    """正EV计算: 模型概率 vs 市场隐含概率"""
    sp = _match_sp(match_id)
    if not sp: return {"ev": 0, "edge": 0, "is_value": False}

    if direction == "home":
        odds = sp.get("home", 0)
    elif direction == "away":
        odds = sp.get("away", 0)
    else:
        odds = sp.get("draw", 0)

    if odds <= 1.0: return {"ev": 0, "edge": 0, "is_value": False}

    market_implied = 1.0 / odds * 100  # 市场隐含概率
    model_pct = model_prob / 100 if model_prob > 1 else model_prob
    edge = model_prob - market_implied  # 模型优势
    ev = (model_prob / 100) * odds - 1.0  # 期望值

    return {
        "ev": round(ev, 3),
        "edge": round(edge, 1),
        "is_value": ev > 0.005,  # 至少0.5%正期望(SP为估算值, 门槛从宽)
        "model_prob": model_prob,
        "market_prob": round(market_implied, 1),
        "odds": odds,
    }


def filter_value_bets(classified: list) -> list:
    """正EV筛选: 只保留价值投注, 按EV排序"""
    for c in classified:
        val = compute_value(c["match_id"], c["direction"], c["dir_prob"])
        c["value"] = val
        c["is_value"] = val["is_value"]
        c["ev_score"] = val["ev"]

    # 按EV排序, 高价值优先
    value_bets = [c for c in classified if c.get("is_value")]
    value_bets.sort(key=lambda x: x.get("ev_score", 0), reverse=True)
    return value_bets


def generate_plan(matches: list) -> dict:
    # P0: 截止时间检查 — 跳过已开球或不足15分钟的场次
    skipped_deadline = []
    valid_matches = []
    for m in matches:
        can_bet, reason = _check_deadline(m)
        if can_bet:
            valid_matches.append(m)
        else:
            skipped_deadline.append((m, reason))

    results = {}
    for m in valid_matches:
        p = predict(m)
        if "error" not in p:
            results[m] = classify_match(m, p)

    if not results:
        skip_msg = ""
        if skipped_deadline:
            names = ", ".join(m for m,_ in skipped_deadline[:4])
            skip_msg = f" (已跳过: {names}等{len(skipped_deadline)}场)"
        return {"error": f"无有效比赛{skip_msg}", "skipped": skipped_deadline}

    # 动态单关: 从SP数据读取 + 硬编码兜底
    dyn_singles = {m for m in results if _is_single_match(m)}
    dyn_singles.update(RULE.get("single_matches", []))

    classified = list(results.values())

    # v4.0: 正EV筛选
    # 检测SP是真实数据还是模型估算(真实SP的概率和≠估算值)
    real_sp_count = sum(1 for c in classified if _match_sp(c["match_id"]))
    using_real_sp = real_sp_count >= len(classified) * 0.5

    if using_real_sp:
        classified_ev = filter_value_bets(classified)
        # 需至少3场非排除场次才能形成有效方案
        usable_ev = [c for c in classified_ev if not c.get("is_excluded")]
        if len(usable_ev) >= 3:
            classified = classified_ev
        else:
            # EV过滤后可用场次不足, 回退全量+标注EV
            for c in classified:
                val = compute_value(c["match_id"], c["direction"], c["dir_prob"])
                c["value"] = val; c["is_value"] = val["is_value"]; c["ev_score"] = val["ev"]
    else:
        # SP为估算值, EV不可靠, 直接按分类
        for c in classified:
            c["value"] = {"ev": 0, "edge": 0, "is_value": True, "note": "SP估算"}
            c["is_value"] = True; c["ev_score"] = 0

    conservative_pool = [c for c in classified if c.get("is_conservative")]
    banker_pool = [c for c in classified if c.get("is_banker")]
    usable_pool = [c for c in classified if c.get("is_usable") and not c.get("is_excluded")]
    excluded_pool = [c for c in classified if c.get("is_excluded")]
    draw_pool = [c for c in classified if c["direction"] == "draw" and c["dir_prob"] >= 40]

    # ★ v5.0 RQSPF池: 有让球盘数据的场次, 按(赔率黄金区间 + 方向置信度)排序
    rqspf_pool = [c for c in classified if c.get("rqspf") and not c.get("is_excluded")
                  and c["rqspf"]["confidence"] in ("高", "中")]
    # RQSPF排序: 优先赔率在1.8-2.5黄金区间的
    def rqspf_score(c):
        odds = c["rqspf"].get("odds", 1.0)
        golden = 1.0 if 1.8 <= odds <= 2.5 else (0.8 if 2.5 < odds <= 3.5 else 0.5)
        return golden * 100 + min(c["dir_prob"], 99)
    rqspf_pool.sort(key=rqspf_score, reverse=True)

    # ★ v5.0 总进球池: 有总进球SP数据的场次
    tg_pool = [c for c in classified if c.get("tg_pred") and not c.get("is_excluded")]
    tg_pool.sort(key=lambda x: x["tg_pred"].get("odds", 0), reverse=True)

    # ★ v5.0 单关优化池: SP标记为单关的场次
    single_pool = [c for c in classified if c["match_id"] in dyn_singles
                   and not c.get("is_excluded")
                   and c["direction"] != "draw"
                   and c["dir_prob"] >= 40]
    single_pool.sort(key=lambda x: (x["dir_prob"], abs(x["delta"])), reverse=True)

    # 稳胆: 最优单场
    banker_pool.sort(key=lambda x: (x["dir_prob"], abs(x["delta"])), reverse=True)
    banker = banker_pool[0] if banker_pool else None

    # 稳健仓 2串1
    conservative_pool.sort(key=lambda x: (x["dir_prob"], abs(x["delta"])), reverse=True)
    conservative_bet = conservative_pool[:2]

    # 均衡仓 (与稳健仓去重)
    used_ids = {b["match_id"] for b in conservative_bet} if len(conservative_bet) >= 2 else set()
    balanced_wdl = None
    for c in classified:
        if c["is_conservative"] and c["match_id"] not in used_ids and "低" not in c["confidence"]:
            balanced_wdl = c; break
    if not balanced_wdl:
        for c in classified:
            if (c["dir_prob"] >= 42 and abs(c["delta"]) >= 12 and c["cold_rank"] < 2
                    and c["match_id"] not in used_ids and c["direction"] != "draw"
                    and "低" not in c["confidence"]):
                balanced_wdl = c; break

    balanced_tg = None
    if balanced_wdl:
        for c in classified:
            if c["total_goals_signal"] and c["match_id"] != balanced_wdl["match_id"] and not c["is_excluded"]:
                balanced_tg = c; break
    if not balanced_tg and draw_pool:
        balanced_tg = draw_pool[0]
        balanced_tg["total_goals_signal"] = 2

    # ★ 自由过关 3串4 (3注2串1 + 1注3串1，错1场仍中2串1)
    flexi_candidates = [c for c in classified if c["is_usable"] and not c["is_excluded"]]
    flexi_candidates.sort(key=lambda x: (x["dir_prob"], abs(x["delta"])), reverse=True)
    flexi_bet = flexi_candidates[:3]

    # 进取仓比分
    score_candidates = [c for c in classified if not c["is_excluded"] and c["confidence"] == "高"]
    score_candidates.sort(key=lambda x: x["dir_prob"], reverse=True)
    aggressive_bet = score_candidates[:3]

    # 资金分配 v5.0: 新增RQSPF仓位
    b_banker = int(RULE["budget"] * RULE["banker_pct"])
    b_conservative = int(RULE["budget"] * RULE["parlay_pct"])
    b_rqspf = int(RULE["budget"] * RULE["rqspf_pct"])
    b_balanced = int(RULE["budget"] * RULE["balanced_pct"])
    b_flexi = int(RULE["budget"] * RULE["flexi_pct"])
    b_aggressive = int(RULE["budget"] * RULE["aggressive_pct"])
    b_reserve = RULE["budget"] - b_banker - b_conservative - b_rqspf - b_balanced - b_flexi - b_aggressive

    # 回收跳过层级预算 → 优先补充稳健仓
    if not banker: b_reserve += b_banker; b_banker = 0
    if not (balanced_wdl and balanced_tg): b_reserve += b_balanced; b_balanced = 0
    if len(aggressive_bet) < 3: b_reserve += b_aggressive; b_aggressive = 0
    # RQSPF不可用时回收
    rqspf_bet = rqspf_pool[:2] if len(rqspf_pool) >= 2 else []
    if len(rqspf_bet) < 2: b_reserve += b_rqspf; b_rqspf = 0
    # 稳健2串1可用时 → 其他仓跳过的预算补充到稳健仓(最可靠)
    if len(conservative_bet) >= 2:
        extra = b_reserve * 0.5  # 保留金的一半给稳健仓
        b_conservative += int(extra)
        b_reserve -= int(extra)
    elif len(conservative_bet) < 2:
        b_reserve += b_conservative; b_conservative = 0

    # ★ v5.0 单关推荐: 从单关池中优选, 含RQSPF和TG建议
    single_bets = []
    for c in single_pool:
        bet_info = {
            "match": c["match_name"], "match_id": c["match_id"],
            "spf_pick": c["dir_name"], "spf_prob": c["dir_prob"],
            "spf_odds": est_odds(c["dir_prob"], match_id=c["match_id"], direction=c["direction"]),
            "kickoff": c["kickoff"],
            "ev": c.get("ev_score", 0),
        }
        # RQSPF建议
        if c.get("rqspf"):
            bet_info["rqspf_pick"] = c["rqspf"]["pick"]
            bet_info["rqspf_odds"] = c["rqspf"].get("odds", 0)
            bet_info["rqspf_confidence"] = c["rqspf"]["confidence"]
        # TG建议
        if c.get("tg_pred"):
            bet_info["tg_pick"] = f"总进球{c['tg_pred']['primary']}球"
            bet_info["tg_odds"] = c["tg_pred"].get("odds", 0)
        # 半全场建议
        if c.get("htft"):
            bet_info["htft_pick"] = f"半全场-{c['htft']['pick']}"
            bet_info["htft_odds"] = c["htft"]["odds"]
        single_bets.append(bet_info)

    # 赔率计算
    # 稳胆
    banker_odds = est_odds(banker["dir_prob"], match_id=banker["match_id"], direction=banker["direction"]) if banker else 0
    banker_return = round(b_banker * banker_odds) if banker else 0

    # 稳健仓 - 用真实SP计算串关赔率
    cons_odds_list = []
    cons_combined = 0
    if len(conservative_bet) >= 2:
        cons_odds_list = [est_odds(b["dir_prob"], match_id=b["match_id"], direction=b["direction"]) for b in conservative_bet]
        cons_combined = round(cons_odds_list[0] * cons_odds_list[1], 2)

    # 均衡仓
    bal_combined = 0
    if balanced_wdl and balanced_tg:
        wdl_sp = est_odds(balanced_wdl["dir_prob"], match_id=balanced_wdl["match_id"], direction=balanced_wdl["direction"])
        tg_sp = _match_tg_sp(balanced_tg["match_id"]).get(str(balanced_tg.get("total_goals_signal", 2)), 3.20)
        bal_combined = round(wdl_sp * tg_sp, 2)

    # 自由过关3串4
    flexi_return = 0
    flexi_detail = {}
    if len(flexi_bet) >= 3:
        f_odds = [est_odds(b["dir_prob"], match_id=b["match_id"], direction=b["direction"]) for b in flexi_bet]
        # 3注2串1赔率
        pairs = [(0,1),(0,2),(1,2)]
        pair_odds = [round(f_odds[i]*f_odds[j], 2) for i,j in pairs]
        # 1注3串1
        triple_odds = round(f_odds[0]*f_odds[1]*f_odds[2], 2)
        # 每注2元, 4注共8元/倍
        flexi_per_unit = 8
        flexi_units = b_flexi // flexi_per_unit if flexi_per_unit > 0 else 0
        flexi_actual_bet = flexi_units * flexi_per_unit if flexi_units > 0 else b_flexi
        flexi_detail = {
            "structure": "3注2串1 + 1注3串1 = 4注",
            "per_unit_cost": f"{flexi_per_unit}元/倍",
            "units": flexi_units if flexi_units > 0 else f"{(b_flexi/flexi_per_unit):.1f}(非整数)",
            "actual_bet": flexi_actual_bet,
            "pair_odds": f"{pair_odds[0]}× / {pair_odds[1]}× / {pair_odds[2]}×",
            "triple_odds": f"{triple_odds}×",
            "pairs": [f"{flexi_bet[i]['match_name']}+{flexi_bet[j]['match_name']}" for i,j in pairs],
        }
        if flexi_units > 0:
            # 错1场: 仍中1注2串1
            min_pair_return = round(min(pair_odds) * 2 * flexi_units)
            # 全中: 3注2串1 + 1注3串1
            all_pair_return = round(sum(pair_odds) * 2 * flexi_units)
            all_triple_return = round(triple_odds * 2 * flexi_units)
            flexi_return = all_pair_return + all_triple_return
            flexi_detail["min_pair_return"] = min_pair_return

    # 进取仓
    agg_combined = 0
    agg_odds_list = []
    for b in aggressive_bet[:3]:
        agg_odds_list.append(round(1.0 / 0.10 * 0.71, 1))
    if len(agg_odds_list) >= 3:
        agg_combined = round(agg_odds_list[0] * agg_odds_list[1] * agg_odds_list[2], 1)

    # 赔率黄金区间校验
    def check_golden_range(odds, label):
        if 1.8 <= odds <= 2.5:
            return f"✅ {label}赔率{odds}在黄金区间1.8-2.5"
        elif odds < 1.8:
            return f"⚠️ {label}赔率{odds}偏低(<1.8), 可考虑让球盘提升"
        else:
            return f"⚠️ {label}赔率{odds}偏高(>2.5), 准确率可能不足50%"

    # EV统计
    all_evs = [c.get("ev_score", 0) for c in classified if c.get("ev_score", 0) > 0]
    ev_stats = {
        "total": len(all_evs),
        "avg_edge": round(sum(c.get("value", {}).get("edge", 0) for c in classified if c.get("value", {}).get("is_value")) / max(1, len(all_evs)), 1) if all_evs else 0
    }

    plan = {
        "generated_by": "模型自动输出 v5.0 (全玩法: SPF+RQSPF+总进球+半全场+混合过关)",
        "total_budget": RULE["budget"],
        "value_stats": ev_stats,
        "skipped": skipped_deadline,
        "classified": {
            "banker_pool": [c["match_name"] for c in banker_pool],
            "conservative_pool": [c["match_name"] for c in conservative_pool],
            "excluded_pool": [c["match_name"] for c in excluded_pool],
        },
        # 新增：稳胆
        "banker": {
            "name": "稳胆单关",
            "amount": b_banker,
            "type": "单关胜平负" if banker and banker["dir_prob"] >= 50 else "单关(建议搭配串关使用)",
            "bet": {
                "match": banker["match_name"], "pick": banker["dir_name"], "match_id": banker["match_id"],
                "model_prob": banker["dir_prob"], "est_odds": est_odds(banker["dir_prob"], match_id=banker["match_id"], direction=banker["direction"]),
                "delta": banker["delta"], "cold": banker["cold_alert"],
                "ev": banker.get("ev_score", 0),
                "ev_str": f" EV+{banker['ev_score']:.0%}" if banker.get("ev_score", 0) > 0.01 else "",
                "banker_reason": f"Δ={banker['delta']:.0f}, 概率{banker['dir_prob']}%, 全场最强方向信号",
                "handicap_tip": banker.get("handicap_advice"),
            } if banker else None,
            "est_return": round(b_banker * banker_odds) if banker else 0,
            "golden_check": check_golden_range(banker_odds, "稳胆") if banker else None,
        } if banker else {"error": "今日无稳胆场次(Δ≥25+概率≥50%)"},
        # 稳健仓
        "conservative": {
            "name": "稳健2串1", "amount": b_conservative, "type": "2串1 胜平负",
            "bets": [{
                "match": b["match_name"], "pick": b["dir_name"], "match_id": b["match_id"],
                "model_prob": b["dir_prob"], "est_odds": est_odds(b["dir_prob"], match_id=b["match_id"], direction=b["direction"]),
                "delta": b["delta"], "cold": b["cold_alert"],
                "ev": b.get("ev_score", 0),
                "ev_str": f" EV+{b['ev_score']:.0%}" if b.get("ev_score", 0) > 0.01 else "",
                "handicap_tip": b.get("handicap_advice"),
            } for b in conservative_bet],
            "est_odds": cons_combined, "est_return": round(b_conservative * cons_combined if cons_combined else 0),
            "golden_check": check_golden_range(cons_combined, "2串1") if cons_combined else None,
            "condition": " AND ".join([b["dir_name"] for b in conservative_bet]),
        } if len(conservative_bet) >= 2 else {"error": "无可投场次"},
        # ★ v5.0 RQSPF仓 (让球胜平负 2串1)
        "rqspf": {
            "name": "让球2串1", "amount": b_rqspf, "type": "2串1 让球胜平负 (竞彩主力玩法)",
            "bets": [{
                "match": b["match_name"], "pick": b["rqspf"]["pick_short"],
                "full_pick": b["rqspf"]["pick"], "match_id": b["match_id"],
                "handicap_line": b["rqspf"]["handicap_line"],
                "model_xg_diff": round(b["xg_home"] - b["xg_away"], 2),
                "adjusted_diff": b["rqspf"]["adjusted_diff"],
                "rqspf_confidence": b["rqspf"]["confidence"],
                "est_odds": b["rqspf"].get("odds", 2.0),
                "reason": f"让{b['rqspf']['handicap_line']}球后 xG差={b['rqspf']['adjusted_diff']:+.1f}",
            } for b in rqspf_bet],
            "est_odds": round(rqspf_bet[0]["rqspf"].get("odds",2.0) * rqspf_bet[1]["rqspf"].get("odds",2.0), 2) if len(rqspf_bet) >= 2 else 0,
            "est_return": round(b_rqspf * (rqspf_bet[0]["rqspf"].get("odds",2.0) * rqspf_bet[1]["rqspf"].get("odds",2.0)), 0) if len(rqspf_bet) >= 2 else 0,
            "condition": " AND ".join([b["rqspf"]["pick"] for b in rqspf_bet]) if len(rqspf_bet) >= 2 else "",
            "note": "让球盘赔率更接近黄金区间(1.8-2.5), 是竞彩主力玩法",
        } if len(rqspf_bet) >= 2 else {"error": "无可投RQSPF场次(需2场有让球盘数据+高/中置信度)"},
        # 均衡仓
        "balanced": {
            "name": "均衡混合", "amount": b_balanced,
            "type": "2串1 混合过关(胜平负+总进球)",
            "bets": [
                {"match": balanced_wdl["match_name"], "pick": balanced_wdl["dir_name"], "match_id": balanced_wdl["match_id"],
                 "type": "胜平负", "model_prob": balanced_wdl["dir_prob"],
                 "est_odds": est_odds(balanced_wdl["dir_prob"], match_id=balanced_wdl["match_id"], direction=balanced_wdl["direction"])},
                {"match": balanced_tg["match_name"], "pick": f"总进球{balanced_tg['total_goals_signal']}球", "match_id": balanced_tg["match_id"],
                 "type": "总进球数", "model_signal": f"xG={balanced_tg['total_xg']:.1f}",
                 "est_odds": 3.20},
            ] if balanced_wdl and balanced_tg else [],
            "est_odds": bal_combined,
            "est_return": round(b_balanced * bal_combined if bal_combined else 0),
        } if balanced_wdl and balanced_tg else {"error": "条件不满足"},
        # ★ 自由过关
        "flexi": {
            "name": "自由过关3串4", "amount": b_flexi if flexi_units > 0 else b_flexi,
            "actual_bet": flexi_detail.get("actual_bet", b_flexi),
            "type": "M串N 容错 (错1场仍中2串1)",
            "bets": [{
                "match": b["match_name"], "pick": b["dir_name"], "match_id": b["match_id"],
                "model_prob": b["dir_prob"], "est_odds": est_odds(b["dir_prob"], match_id=b["match_id"], direction=b["direction"]),
                "ev": b.get("ev_score", 0),
                "ev_str": f" EV+{b['ev_score']:.0%}" if b.get("ev_score", 0) > 0.01 else "",
            } for b in flexi_bet],
            "detail": flexi_detail,
            "all_hit_return": flexi_return,
            "one_miss_return": flexi_detail.get("min_pair_return", "N/A") if isinstance(flexi_detail, dict) else "N/A",
            "condition": "3场中至少2场 = 中1注2串1; 3场全中 = 3注2串1+1注3串1",
        } if len(flexi_bet) >= 3 and flexi_units > 0 else {"error": "条件不满足"},
        # 进取仓
        "aggressive": {
            "name": "进取比分", "amount": b_aggressive, "type": "3串1 比分",
            "bets": [{
                "match": fn(b["match_name"]), "pick": b["top_score"],
                "score_prob": "~10%", "est_odds": round(1.0/0.10*0.71, 1),
            } for b in aggressive_bet[:3]],
            "est_odds": agg_combined, "est_return": round(b_aggressive * agg_combined if agg_combined else 0),
            "condition": " AND ".join([f"{b['match_name']} {b['top_score']}" for b in aggressive_bet[:3]]),
        } if len(aggressive_bet) >= 3 else {"error": "条件不满足"},
        "reserve": {"amount": b_reserve, "reason": "保留金：按实战铁律每日保留5%"},
        # ★ v5.0 单关推荐 (全玩法)
        "single_bets": single_bets,
        "single_bet_note": "单关场次可单独投注, 命中即兑; RQSPF赔率更优时可替代SPF" if single_bets else "",
        "risk_notes": [],
    }

    for c in excluded_pool:
        reason = c["confidence"] if "低" in c["confidence"] else c["cold_alert"]
        plan["risk_notes"].append(f"排除 {c['match_name']}: {reason}")

    return plan


def format_lottery(plan: dict) -> str:
    if "error" in plan:
        msg = f"❌ {plan['error']}"
        skipped = plan.get("skipped", [])
        if skipped:
            msg += f"\n   跳过场次: {', '.join(m+'('+r+')' for m,r in skipped[:5])}"
            msg += "\n💡 建议: 今日无可投场次, 保留资金等待明日"
        return msg

    L = []
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    L.append("=" * 70)
    L.append("  竞彩足球 2026世界杯 自动投注方案 v5.0 (全玩法)")
    L.append(f"  生成时间: {now_ts}  |  预算: {plan['total_budget']}元")
    L.append(f"  算法: 正EV筛选 + 高置信优先 | 引擎: {plan['generated_by']}")
    # Value stats
    val_count = plan.get("value_stats", {})
    if val_count:
        L.append(f"  📊 正EV场次: {val_count.get('total',0)}场 | 平均edge: {val_count.get('avg_edge',0):+.1f}%")
    L.append("=" * 70)

    # Deadline skipped info
    skipped = plan.get("skipped", [])
    if skipped:
        L.append(f"\n⚠️ 已跳过 {len(skipped)} 场 (开球/不足15分钟):")
        for m, reason in skipped[:4]:
            L.append(f"  • {m}: {reason}")

    c = plan["classified"]
    L.append(f"\n📋 场次: 稳胆{c['banker_pool'][:3]} | 稳健{c['conservative_pool'][:3]} | 排除{c['excluded_pool']}")

    total_return = 0

    # 稳胆
    banker = plan.get("banker", {})
    if "error" not in banker:
        b = banker["bet"]
        L.append(f"\n{'─'*70}")
        L.append(f"⭐ 稳胆单关 — {banker['amount']}元 | 单关胜平负")
        L.append(f"{'─'*70}")
        time = MATCH_SCHEDULE.get(b.get("match_id",""), "")
        L.append(f"  {time:<10} {b['match']:<36} → {b['pick']:<22} 概率{b['model_prob']}% 估赔{b['est_odds']}  Δ={b['delta']:+.0f}")
        L.append(f"  {b['banker_reason']}")
        if b.get("handicap_tip"):
            h = b["handicap_tip"]
            L.append(f"  💡 让球盘建议: {h['line']} {h['pick']} ({h['reason']})")
        L.append(f"  预估回报: ≈{banker['est_return']}元")
        L.append(f"  {banker.get('golden_check', '')}")
        total_return += banker.get("est_return", 0)
    else:
        L.append(f"\n⭐ 稳胆 — 跳过: {banker['error']}")

    # 稳健仓
    def render_tier(tier_name, emoji):
        nonlocal total_return
        plan_dict = plan.get(tier_name, {})
        L.append(f"\n{'─'*70}")
        if "error" in plan_dict:
            L.append(f"{emoji} {plan_dict.get('name', tier_name)} — 跳过: {plan_dict['error']}")
            return
        detail = plan_dict.get("detail", {})
        detail_str = f" | {detail.get('structure', '')}" if detail else ""
        L.append(f"{emoji} {plan_dict['name']} — {plan_dict['amount']}元{detail_str} | {plan_dict['type']}")
        L.append(f"{'─'*70}")
        for b in plan_dict.get("bets", []):
            extra = ""
            ev_str = ""
            if "model_signal" in b: extra = f" ({b['model_signal']})"
            elif "model_prob" in b: extra = f" 概率{b['model_prob']}%"
            elif "rqspf_confidence" in b: extra = f" [{b.get('rqspf_confidence','')}]"
            # Show EV if available
            ev_val = b.get("ev", 0)
            if ev_val > 0.01:
                ev_str = f"  EV+{ev_val:.0%}"
            elif ev_val < -0.01:
                ev_str = f"  EV{ev_val:.0%}"
            # RQSPF special: show adjusted diff and reason
            rqspf_extra = ""
            if "adjusted_diff" in b:
                rqspf_extra = f"  让球后xG差={b['adjusted_diff']:+.1f}"
                if "reason" in b:
                    rqspf_extra += f" ({b['reason']})"
            ht = b.get("handicap_tip", "")
            ht_str = ""
            if ht:
                ht_str = f"  💡让球: {ht['pick']}"
            elif "handicap_line" in b:
                line = b["handicap_line"]
                if line > 0: ht_str = f"  让{line}球"
                elif line < 0: ht_str = f"  让{abs(line)}球"
                else: ht_str = f"  平手"
            else:
                mid = b.get("match_id","")
                hsp = _match_handicap_sp(mid)
                if hsp:
                    line = hsp.get("line", 0)
                    if line > 0: ht_str = f"  💡让球: 受让{line}球"
                    elif line < 0: ht_str = f"  💡让球: 让{abs(line)}球"
                    else: ht_str = f"  💡让球: 平手"
            time = MATCH_SCHEDULE.get(b.get("match_id",""), "")
            ev_part = b.get("ev_str", "")
            L.append(f"  {time:<10} {b['match']:<36} → {b['pick']:<14}{extra} 估赔{b['est_odds']}{ht_str}{rqspf_extra}{ev_part}")
        if detail:
            L.append(f"  结构: {detail['structure']} | 每单位{detail.get('per_unit_cost','')} × {detail.get('units','')}倍 = {detail.get('actual_bet','')}元")
            pairs = detail.get("pairs", [])
            pair_odds = detail.get("pair_odds", "")
            if pairs:
                L.append(f"  📋 投注明细 (3串4):")
                L.append(f"    注① 2串1: {pairs[0] if len(pairs)>0 else '?'}")
                L.append(f"    注② 2串1: {pairs[1] if len(pairs)>1 else '?'}")
                L.append(f"    注③ 2串1: {pairs[2] if len(pairs)>2 else '?'}")
                L.append(f"    注④ 3串1: {' + '.join([b['pick'] for b in plan_dict.get('bets',[])[:3]]) if len(plan_dict.get('bets',[]))>=3 else '?'}")
            L.append(f"  2串1赔率: {pair_odds}")
            L.append(f"  3串1赔率: {detail.get('triple_odds','')}")
            if plan_dict.get("one_miss_return"):
                L.append(f"  🛡️ 容错: 错1场仍中1注2串1 ≈{plan_dict['one_miss_return']}元")
        L.append(f"  预估回报: ≈{plan_dict.get('est_return', 0)}元")
        if plan_dict.get("all_hit_return"):
            L.append(f"  全中回报: ≈{plan_dict['all_hit_return']}元")
        L.append(f"  命中条件: {plan_dict.get('condition', '')[:80]}")
        gc = plan_dict.get("golden_check", "")
        if gc: L.append(f"  {gc}")
        note = plan_dict.get("note", "")
        if note: L.append(f"  💡 {note}")
        ret = plan_dict.get("est_return", 0)
        all_ret = plan_dict.get("all_hit_return", ret)
        total_return += all_ret if isinstance(all_ret, (int, float)) else ret

    render_tier("conservative", "🛡️")
    render_tier("rqspf", "⚽")
    render_tier("balanced", "📊")
    render_tier("flexi", "🔀")
    render_tier("aggressive", "🎯")

    # ★ v5.0 单关推荐 (全玩法)
    single_bets = plan.get("single_bets", [])
    if single_bets:
        L.append(f"\n{'─'*70}")
        L.append(f"🎯 单关推荐 (可单独投注, 命中即兑)")
        L.append(f"{'─'*70}")
        for sb in single_bets[:6]:
            time = MATCH_SCHEDULE.get(sb.get("match_id",""), "")
            L.append(f"  {time:<10} {sb['match']}")
            L.append(f"    SPF: {sb['spf_pick']:<14} 概率{sb['spf_prob']}%  赔率{sb.get('spf_odds','?')}")
            if sb.get("rqspf_pick"):
                L.append(f"    RQSPF: {sb['rqspf_pick']:<20} 赔率{sb.get('rqspf_odds','?')} ({sb.get('rqspf_confidence','')})")
            if sb.get("tg_pick"):
                L.append(f"    总进球: {sb['tg_pick']:<16} 赔率{sb.get('tg_odds','?')}")
            if sb.get("htft_pick"):
                L.append(f"    半全场: {sb['htft_pick']:<16} 赔率{sb.get('htft_odds','?')}")
            L.append("")

    # 保留金
    reserve = plan.get("reserve", {})
    L.append(f"\n💰 保留金: {reserve.get('amount', 0)}元 ({reserve.get('reason', '')})")

    L.append(f"\n{'═'*70}")
    L.append(f"💵 全中总回报: ≈{total_return}元")
    L.append(f"{'═'*70}")

    if plan["risk_notes"]:
        L.append(f"\n⚠️ 风险提示:")
        for n in plan["risk_notes"]: L.append(f"  • {n}")

    L.append(f"\n📐 模型自动输出 v5.0 ({now_ts}) | 正EV+全玩法覆盖 | 竞彩90分钟赛果为准 | 仅作参考")
    return "\n".join(L)
