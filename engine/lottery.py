"""
竞彩投注方案自动生成引擎 v3.1
新增: SP动态读取 + 截止时间检查 + 今日不推荐机制
"""
import json, math
from pathlib import Path
from datetime import datetime
from .predictor import predict

# 国旗映射
FLAG = {
    "France": "🇫🇷", "Spain": "🇪🇸", "Argentina": "🇦🇷", "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Brazil": "🇧🇷", "Portugal": "🇵🇹", "Germany": "🇩🇪", "Netherlands": "🇳🇱",
    "Belgium": "🇧🇪", "Norway": "🇳🇴", "Morocco": "🇲🇦", "Colombia": "🇨🇴",
    "Mexico": "🇲🇽", "South Korea": "🇰🇷", "United States": "🇺🇸", "Uruguay": "🇺🇾",
    "Croatia": "🇭🇷", "Japan": "🇯🇵", "Senegal": "🇸🇳", "Switzerland": "🇨🇭",
    "Austria": "🇦🇹", "Sweden": "🇸🇪", "Canada": "🇨🇦", "Australia": "🇦🇺",
    "Ecuador": "🇪🇨", "Türkiye": "🇹🇷", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Czechia": "🇨🇿",
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
    "deadline": "开球前15分钟",  # 2025从30分钟缩到15分钟
    # 预算分配
    "budget": 200,
    "banker_pct": 0.20, "parlay_pct": 0.35,
    "balanced_pct": 0.15, "flexi_pct": 0.20, "aggressive_pct": 0.10,
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
}

THRESHOLD = {
    "conservative_min_delta": 10,
    "conservative_max_cold_rank": 2,
    "conservative_min_prob": 42,     # 从45降到42，避免仅差1%被排除
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
    return _sp_data().get("matches", {}).get(match_id, {})

def _match_handicap_sp(match_id: str) -> dict:
    return _sp_data().get("handicap", {}).get(match_id, {})

def _match_tg_sp(match_id: str) -> dict:
    return _sp_data().get("total_goals", {}).get(match_id, {})

def _match_score_sp(match_id: str) -> dict:
    return _sp_data().get("score", {}).get(match_id, {})

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
    tg_sp = _match_tg_sp(match_id) if match_id else {}
    if tg_sp and bet_type == "total_goals":
        tg = str(int(str(pick).replace("总进球","").replace("球",""))) if pick else "2"
        return tg_sp.get(tg, 3.20)
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
        direction, dir_prob, dir_name = "home", w, fn(h["name"] + "胜")
        handicap_pick = f"{flag(h['name'])} {h['name']}{est_handicap(p['delta'])}胜"
    elif l > w and l > d:
        direction, dir_prob, dir_name = "away", l, fn(a["name"] + "胜")
        handicap_pick = f"{flag(a['name'])} {a['name']}{est_handicap(-p['delta'])}胜"
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

    # 构建带国旗的比赛名称 + 开赛时间
    parts = p["match"].split(" vs ")
    flagged_match = f"{fn(parts[0])} vs {fn(parts[1])}" if len(parts) == 2 else p["match"]
    kickoff = MATCH_SCHEDULE.get(match_id, "")

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
    }


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
    conservative_pool = [c for c in classified if c["is_conservative"]]
    banker_pool = [c for c in classified if c["is_banker"]]
    usable_pool = [c for c in classified if c["is_usable"] and not c["is_excluded"]]
    excluded_pool = [c for c in classified if c["is_excluded"]]
    draw_pool = [c for c in classified if c["direction"] == "draw" and c["dir_prob"] >= 40]

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

    # 资金分配
    b_banker = int(RULE["budget"] * RULE["banker_pct"])
    b_conservative = int(RULE["budget"] * RULE["parlay_pct"])
    b_balanced = int(RULE["budget"] * RULE["balanced_pct"])
    b_flexi = int(RULE["budget"] * RULE["flexi_pct"])
    b_aggressive = int(RULE["budget"] * RULE["aggressive_pct"])
    b_reserve = RULE["budget"] - b_banker - b_conservative - b_balanced - b_flexi - b_aggressive

    # 回收跳过层级预算
    if not banker: b_reserve += b_banker; b_banker = 0
    if len(conservative_bet) < 2: b_reserve += b_conservative; b_conservative = 0
    if not (balanced_wdl and balanced_tg): b_reserve += b_balanced; b_balanced = 0
    if len(aggressive_bet) < 3: b_reserve += b_aggressive; b_aggressive = 0

    # 单关推荐: 从动态单关列表中选方向明确的场次
    single_bets = []
    for c in classified:
        if (c["match_id"] in dyn_singles
                and not c["is_excluded"]
                and c["direction"] != "draw"
                and c["dir_prob"] >= 40):
            single_bets.append(c)

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

    plan = {
        "generated_by": "模型自动输出 v3.1 (截止检查+动态SP+不推荐机制)",
        "total_budget": RULE["budget"],
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
                "handicap_tip": b.get("handicap_advice"),
            } for b in conservative_bet],
            "est_odds": cons_combined, "est_return": round(b_conservative * cons_combined if cons_combined else 0),
            "golden_check": check_golden_range(cons_combined, "2串1") if cons_combined else None,
            "condition": " AND ".join([b["dir_name"] for b in conservative_bet]),
        } if len(conservative_bet) >= 2 else {"error": "无可投场次"},
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
    L.append("=" * 70)
    L.append("  竞彩足球 2026世界杯 自动投注方案 v3.1")
    L.append(f"  引擎: {plan['generated_by']}  |  预算: {plan['total_budget']}元")
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
            if "model_signal" in b: extra = f" ({b['model_signal']})"
            elif "model_prob" in b: extra = f" 概率{b['model_prob']}%"
            ht = b.get("handicap_tip", "")
            ht_str = f"  💡让球:{ht['line']}{ht['pick']}" if ht else ""
            time = MATCH_SCHEDULE.get(b.get("match_id",""), "")
            L.append(f"  {time:<10} {b['match']:<36} → {b['pick']:<14}{extra} 估赔{b['est_odds']}{ht_str}")
        if detail:
            L.append(f"  结构: {detail['structure']} | 每单位{detail.get('per_unit_cost','')} × {detail.get('units','')}倍 = {detail.get('actual_bet','')}元")
            L.append(f"  2串1赔率: {detail.get('pair_odds','')}")
            L.append(f"  3串1赔率: {detail.get('triple_odds','')}")
            if plan_dict.get("one_miss_return"):
                L.append(f"  🛡️ 容错: 错1场仍中1注2串1 ≈{plan_dict['one_miss_return']}元")
        L.append(f"  预估回报: ≈{plan_dict.get('est_return', 0)}元")
        if plan_dict.get("all_hit_return"):
            L.append(f"  全中回报: ≈{plan_dict['all_hit_return']}元")
        L.append(f"  命中条件: {plan_dict.get('condition', '')[:80]}")
        gc = plan_dict.get("golden_check", "")
        if gc: L.append(f"  {gc}")
        ret = plan_dict.get("est_return", 0)
        all_ret = plan_dict.get("all_hit_return", ret)
        total_return += all_ret if isinstance(all_ret, (int, float)) else ret

    render_tier("conservative", "🛡️")
    render_tier("balanced", "📊")
    render_tier("flexi", "🔀")
    render_tier("aggressive", "🎯")

    # 保留金
    reserve = plan.get("reserve", {})
    L.append(f"\n💰 保留金: {reserve.get('amount', 0)}元 ({reserve.get('reason', '')})")

    L.append(f"\n{'═'*70}")
    L.append(f"💵 全中总回报: ≈{total_return}元")
    L.append(f"{'═'*70}")

    if plan["risk_notes"]:
        L.append(f"\n⚠️ 风险提示:")
        for n in plan["risk_notes"]: L.append(f"  • {n}")

    L.append(f"\n📐 模型自动输出 v3.1 | 截止检查+动态SP+不推荐 | 竞彩90分钟赛果为准")
    return "\n".join(L)
