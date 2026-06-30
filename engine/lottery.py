"""
竞彩投注方案自动生成引擎 v6.0
体彩竞彩彩票投注系统 — 收益最大化投资组合优化
核心理念: 机会驱动 · Kelly仓位 · 正EV精选 · 非均衡分配
"""
import json, math
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
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
    # 奖金规则
    "base_bet": 2, "return_rate": 0.71, "max_multiplier": 99,
    "max_ticket": 20000, "max_single_bet": 2000, "max_daily": 10000,
    "tax_threshold": 10000,
    "prize_2_3": 200000, "prize_4_5": 500000,
    "prize_6_8": 5000000, "prize_9_plus": 2000000,
    # 投注规则
    "match_duration": "90分钟+伤停补时",
    "deadline": "开球前1分钟",
    # ★ v6.0 投资组合优化参数
    "budget": 200,                     # 预算上限(非强制分配)
    "min_edge_pct": 0.5,               # 最低edge门槛(%)
    "max_bets_per_match": 2,           # 每场最多投注数
    "max_stake_per_bet": 50,           # 单注最大金额(元)
    "min_stake_per_bet": 10,           # 单注最小金额(元)
    "kelly_fraction": 0.25,            # 1/4 Kelly (保守)
    "min_odds": 1.08,                  # 最低赔率
    "max_odds": 50.0,                  # 最高赔率(排除彩票级)
    "max_portfolio_bets": 8,           # 最大总注数
    "rqspf_preference": True,          # RQSPF优先于SPF
    "golden_odds_min": 1.8,            # 黄金赔率区间下限
    "golden_odds_max": 2.5,            # 黄金赔率区间上限
    "max_concentration_pct": 0.30,     # 单一方向最大集中度
    "reserve_min_pct": 0.05,           # 最低保留比例
    # 单关场次: 动态从SP数据读取
    "single_matches": [],
}

# ★ v6.0 数据结构
@dataclass
class BetOpportunity:
    """投注机会 — 投资组合的基本单位"""
    match_id: str
    match_name: str
    kickoff: str
    play_type: str          # "spf"|"rqspf"|"total_goals"|"correct_score"|"half_full"
    pick: str               # 完整投注项名称
    pick_short: str
    model_prob: float       # 模型概率 0-100
    odds: float             # 实际SP赔率
    edge_pct: float         # model_prob - market_implied (百分点)
    ev: float               # (prob/100)*odds - 1
    kelly_full_pct: float   # 全凯利比例
    stake: float            # 1/4凯利仓位(元)
    confidence: str = ""    # "高"|"中"|"低"
    delta: float = 0.0
    market_implied: float = 0.0
    handicap_line: int = 0  # only RQSPF
    note: str = ""

@dataclass
class PortfolioConfig:
    """投资组合配置"""
    budget: int = 200
    min_edge_pct: float = 0.5
    max_bets_per_match: int = 2
    max_stake_per_bet: int = 50
    min_stake_per_bet: int = 10
    kelly_fraction: float = 0.25
    min_odds: float = 1.08
    max_odds: float = 50.0
    max_portfolio_bets: int = 8
    rqspf_preference: bool = True
    golden_odds_min: float = 1.8
    golden_odds_max: float = 2.5
    max_concentration_pct: float = 0.30
    reserve_min_pct: float = 0.05

@dataclass
class PortfolioResult:
    """投资组合结果"""
    bets: list = field(default_factory=list)
    total_stake: int = 0
    reserve: int = 0
    total_ev_pct: float = 0.0
    expected_return: float = 0.0
    opportunities_scanned: int = 0
    opportunities_selected: int = 0
    concentration: dict = field(default_factory=dict)
    skipped: list = field(default_factory=list)
    excluded_count: int = 0
    risk_notes: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

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
    # 6/23 I+J组第二轮
    "ARG-AUT": "6/23 01:00", "FRA-IRQ": "6/23 05:00",
    "NOR-SEN": "6/23 08:00", "JOR-ALG": "6/23 11:00",
    # 6/24 K+L组第二轮
    "POR-UZB": "6/24 01:00", "ENG-GHA": "6/24 04:00",
    "PAN-CRO": "6/24 07:00", "COL-COD": "6/24 10:00",
    # 6/25 A+B+C组第三轮(末轮)
    "SUI-CAN": "6/25 03:00", "BIH-QAT": "6/25 03:00",
    "SCO-BRA": "6/25 06:00", "MAR-HAI": "6/25 06:00",
    "CZE-MEX": "6/25 09:00", "RSA-KOR": "6/25 09:00",
    # 6/26 D+E+F组第三轮(末轮)
    "ECU-GER": "6/26 04:00", "CUW-CIV": "6/26 04:00",
    "JPN-SWE": "6/26 07:00", "TUN-NED": "6/26 07:00",
    "TUR-USA": "6/26 10:00", "PAR-AUS": "6/26 10:00",
    # 6/27 G+H+I组第三轮(末轮)
    "NOR-FRA": "6/27 03:00", "SEN-IRQ": "6/27 03:00",
    "CPV-KSA": "6/27 08:00", "URU-ESP": "6/27 08:00",
    "EGY-IRN": "6/27 11:00", "NZL-BEL": "6/27 11:00",
    # 6/28 J+K+L组第三轮(末轮)
    "PAN-ENG": "6/28 05:00", "CRO-GHA": "6/28 05:00",
    "COL-POR": "6/28 07:30", "COD-UZB": "6/28 07:30",
    "ALG-AUT": "6/28 10:00", "JOR-ARG": "6/28 10:00",
    # ── 淘汰赛 ──
    # 1/16决赛 (Round of 32): 6/28-7/3
    "RSA-CAN": "6/29 03:00",   # M73 南非 0-1 加拿大 ✅
    "BRA-JPN": "6/30 01:00",   # M76 巴西 vs 日本
    "GER-PAR": "6/30 04:30",   # M74 德国 vs 巴拉圭
    "NED-MAR": "6/30 09:00",   # M75 荷兰 vs 摩洛哥
    # 7/1
    "CIV-NOR": "7/01 01:00",   # M78 科特迪瓦 vs 挪威
    "FRA-SWE": "7/01 05:00",   # M77 法国 vs 瑞典
    "MEX-ECU": "7/01 09:00",   # M79 墨西哥 vs 厄瓜多尔
    # 7/2
    "ENG-COD": "7/02 00:00",   # M80 英格兰 vs 刚果(金)
    "BEL-SEN": "7/02 04:00",   # M82 比利时 vs 塞内加尔
    "USA-BIH": "7/02 08:00",   # M81 美国 vs 波黑
    # 7/3
    "ESP-AUT": "7/03 03:00",   # M84 西班牙 vs 奥地利
    "POR-CRO": "7/03 07:00",   # M83 葡萄牙 vs 克罗地亚
    "SUI-ALG": "7/03 11:00",   # M85 瑞士 vs 阿尔及利亚
    # 7/4
    "AUS-EGY": "7/04 02:00",   # M88 澳大利亚 vs 埃及
    "ARG-CPV": "7/04 06:00",   # M86 阿根廷 vs 佛得角
    "COL-GHA": "7/04 09:30",   # M87 哥伦比亚 vs 加纳
    # 1/8决赛 (Round of 16): 7/4-7/7
    "R16-1": "7/05 01:00", "R16-2": "7/05 05:00",
    "R16-3": "7/06 04:00", "R16-4": "7/06 08:00",
    "R16-5": "7/07 03:00", "R16-6": "7/07 08:00",
    "R16-7": "7/08 00:00", "R16-8": "7/08 04:00",
    # 1/4决赛 (Quarter-finals): 7/9-7/11
    "QF-1": "7/10 04:00", "QF-2": "7/11 03:00",
    "QF-3": "7/12 05:00", "QF-4": "7/12 09:00",
    # 半决赛 (Semi-finals): 7/14-7/15
    "SF-1": "7/15 03:00", "SF-2": "7/16 03:00",
    # 季军赛 + 决赛
    "BRONZE": "7/19 05:00",
    "FINAL": "7/20 03:00",
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
        # RQSPF概率计算用
        "score_probs": r["top_scores"],
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



def _rqspf_raw_poisson_prob(xg_home: float, xg_away: float, handicap_line: int, direction: str) -> float:
    """
    用原始Poisson(未经Dixon-Coles/平局加成等调整)计算RQSPF概率
    返回: 0-100的概率值
    """
    import math as _m
    def _pois(l, k):
        if l <= 0: return 1.0 if k == 0 else 0.0
        return (l**k * _m.exp(-l)) / _m.factorial(k)

    prob_h = prob_push = prob_a = 0.0
    for hg in range(9):
        for ag in range(9):
            p = _pois(xg_home, hg) * _pois(xg_away, ag)
            adj = hg - ag + handicap_line
            if adj > 0.5: prob_h += p
            elif adj < -0.5: prob_a += p
            else: prob_push += p

    total = prob_h + prob_push + prob_a
    if total <= 0: return 30.0

    if direction == "home":
        return max(5.0, min(90.0, prob_h / total * 100))
    elif direction == "away":
        return max(5.0, min(90.0, prob_a / total * 100))
    else:
        return max(5.0, min(60.0, prob_push / total * 100))


def _rqspf_real_prob(score_probs: list, handicap_line: int, direction: str) -> float:
    """
    用模型预测的比分分布(top_scores)计算真实RQSPF概率 (保留给向后兼容)
    """
    prob_cover_home = 0.0
    prob_push = 0.0
    prob_cover_away = 0.0
    for s in score_probs:
        hg, ag = map(int, s['score'].split('-'))
        adj = hg - ag + handicap_line
        p = s['probability']
        if adj > 0.5: prob_cover_home += p
        elif adj < -0.5: prob_cover_away += p
        else: prob_push += p
    total = prob_cover_home + prob_push + prob_cover_away
    if total <= 0: return 30.0
    if direction == "home": return max(5.0, min(90.0, prob_cover_home / total * 100))
    elif direction == "away": return max(5.0, min(90.0, prob_cover_away / total * 100))
    else: return max(5.0, min(60.0, prob_push / total * 100))


def _htft_poisson_prob(xg_home: float, xg_away: float, htft_pick: str) -> float:
    """
    半全场Poisson精确概率 (替代旧公式 dir_prob*0.45)
    半场xG = 全场xG × 0.45, 下半场xG = 全场xG × 0.55
    htft_pick: '胜胜','胜平','胜负','平胜','平平','平负','负胜','负平','负负'
    """
    import math as _m
    def _pois(l, k):
        if l <= 0: return 1.0 if k == 0 else 0.0
        return (l**k * _m.exp(-l)) / _m.factorial(k)

    h1_home_xg = xg_home * 0.45
    h1_away_xg = xg_away * 0.45
    h2_home_xg = xg_home * 0.55
    h2_away_xg = xg_away * 0.55

    ht_map = {'胜': 0, '平': 1, '负': 2}
    ft_map = ht_map
    ht = htft_pick[0]  # 半场
    ft = htft_pick[1]  # 全场

    prob = 0.0
    for h1_hg in range(6):
        for h1_ag in range(6):
            p_ht = _pois(h1_home_xg, h1_hg) * _pois(h1_away_xg, h1_ag)
            if p_ht < 0.0002: continue
            if h1_hg > h1_ag: h1_res = '胜'
            elif h1_hg == h1_ag: h1_res = '平'
            else: h1_res = '负'
            if h1_res != ht: continue

            for h2_hg in range(6):
                for h2_ag in range(6):
                    p_2h = _pois(h2_home_xg, h2_hg) * _pois(h2_away_xg, h2_ag)
                    ft_hg, ft_ag = h1_hg + h2_hg, h1_ag + h2_ag
                    if ft_hg > ft_ag: ft_res = '胜'
                    elif ft_hg == ft_ag: ft_res = '平'
                    else: ft_res = '负'
                    if ft_res == ft:
                        prob += p_ht * p_2h
    return max(1.0, min(90.0, prob * 100))


def _handicap_note(match_id: str) -> tuple:
    """让球盘信息: (line, rqspf_pick, rqspf_odds)"""
    hsp = _match_handicap_sp(match_id)
    if not hsp or hsp.get("line") is None:
        sp = _match_sp(match_id)
        if sp and sp.get("handicap") is not None:
            hsp = {"line": sp["handicap"]}
        else:
            return (0, "", 0)
    line = hsp["line"]
    pick = "让球主胜" if line < 0 else ("让球客胜" if line > 0 else "平手")
    odds = hsp.get("home", 0) or hsp.get("away", 0) or 0
    return (line, pick, odds)


# ═══════════════════════════════════════════════════════════════
# 竞彩方案 v6.0 — 收益最大化投资组合引擎
# ═══════════════════════════════════════════════════════════════

def compute_tg_edge(goals_key: str, tg_sp: dict, model_xg: float) -> dict:
    """
    总进球数 edge 计算: 模型Poisson隐含概率 vs 市场赔率
    """
    odds = tg_sp.get(goals_key, 0)
    if odds <= 1.0:
        return {"edge": 0, "ev": 0, "is_value": False, "odds": odds, "model_implied": 0}
    market_implied = 1.0 / odds * 100
    # 本地Poisson PMF: P(X=k) = lambda^k * e^(-lambda) / k!
    try:
        k = int(goals_key.replace("7+", "7"))
        if goals_key == "7+":
            # P(X >= 7) = 1 - sum_{i=0}^{6} P(X=i)
            cdf = 0.0
            for i in range(7):
                cdf += (model_xg ** i) * math.exp(-model_xg) / math.factorial(i)
            model_implied_pct = (1 - cdf) * 100
        else:
            pmf = (model_xg ** k) * math.exp(-model_xg) / math.factorial(k)
            model_implied_pct = pmf * 100
    except (ValueError, OverflowError):
        model_implied_pct = 10.0  # fallback
    edge = model_implied_pct - market_implied
    ev = (model_implied_pct / 100) * odds - 1.0
    return {
        "edge": round(edge, 1), "ev": round(ev, 3),
        "is_value": ev > 0.005, "odds": odds,
        "model_implied": round(model_implied_pct, 1),
        "market_implied": round(market_implied, 1),
    }


def generate_all_opportunities(classified: list, config: PortfolioConfig = None) -> list:
    """
    对所有已分类比赛, 生成全部可用玩法的 BetOpportunity
    返回: 候选机会列表
    """
    if config is None:
        config = PortfolioConfig()
    opportunities = []
    parlay_only_ops = []  # 非单关SPF供串关专用池

    for c in classified:
        if c.get("is_excluded"):
            continue
        mid = c["match_id"]
        mn = c["match_name"]
        ko = c["kickoff"]
        delta = abs(c["delta"])
        conf = c["confidence"]
        xg_total = c["total_xg"]

        # ── SPF (胜平负) — 仅单关场次可单投, 非单关只用于串关 ──
        is_single = _is_single_match(mid)
        wdl = c.get("wdl", "0/0/0")
        parts_wdl = [float(x) for x in wdl.split("/")]
        probs = {
            "home": (parts_wdl[0] if len(parts_wdl) > 0 else 0, c.get("dir_name", "主胜")),
            "draw": (parts_wdl[1] if len(parts_wdl) > 1 else 0, "平局"),
            "away": (parts_wdl[2] if len(parts_wdl) > 2 else 0, c.get("dir_name", "客胜")),
        }
        if "away" in probs:
            away_name = c["match_name"].split(" vs ")
            away_team = away_name[1] if len(away_name) > 1 else ""
            probs["away"] = (probs["away"][0], f"{away_team}胜" if away_team else "客胜")

        # ⚠️ 核心规则: 非单关场次SPF不生成单注, 但仍然生成供串关使用
        if not is_single:
            for direction, (prob, pick_name) in probs.items():
                if prob <= 0: continue
                spf_val = compute_value(mid, direction, prob)
                if spf_val["is_value"] and spf_val["ev"] > 0:
                    flag_name = "平局" if direction == "draw" else pick_name
                    hcap_note = _handicap_note(mid)
                    parlay_only_ops.append(BetOpportunity(
                        match_id=mid, match_name=mn, kickoff=ko,
                        play_type="spf", pick=flag_name, pick_short=f"SPF-{direction}",
                        model_prob=prob, odds=spf_val["odds"],
                        edge_pct=spf_val["edge"], ev=spf_val["ev"],
                        kelly_full_pct=0, stake=0,
                        confidence=conf, delta=delta,
                        market_implied=spf_val.get("market_prob", 0),
                        handicap_line=hcap_note[0] if hcap_note else 0,
                        note=f"WDL={wdl}",
                    ))
            # 继续处理其他玩法, 然后返回
            # (TP/TG/RQSPF/HTFT below)
        else:
            # 单关场次: 正常生成SPF单注
            for direction, (prob, pick_name) in probs.items():
                if prob <= 0: continue
                spf_val = compute_value(mid, direction, prob)
                if spf_val["is_value"] and spf_val["ev"] > 0:
                    flag_name = "平局" if direction == "draw" else pick_name
                    hcap_note = _handicap_note(mid)
                    opportunities.append(BetOpportunity(
                        match_id=mid, match_name=mn, kickoff=ko,
                        play_type="spf", pick=flag_name, pick_short=f"SPF-{direction}",
                        model_prob=prob, odds=spf_val["odds"],
                        edge_pct=spf_val["edge"], ev=spf_val["ev"],
                        kelly_full_pct=0, stake=0,
                        confidence=conf, delta=delta,
                        market_implied=spf_val.get("market_prob", 0),
                        handicap_line=hcap_note[0] if hcap_note else 0,
                        note=f"WDL={wdl}",
                    ))

        # ── RQSPF (让球胜平负) ──
        rq = c.get("rqspf")
        if rq and rq.get("odds", 0) > 1.0:
            rq_odds = rq["odds"]
            market_imp = 1.0 / rq_odds * 100 if rq_odds > 1.0 else 0
            # RQSPF概率: 基于调整后xG差 + 方向
            rq_dir = rq.get("direction", "")
            # ★ 原始Poisson计算RQSPF概率 (不经Dixon-Coles等调整)
            rq_prob = _rqspf_raw_poisson_prob(c["xg_home"], c["xg_away"],
                                              rq.get("handicap_line", 0), rq_dir)
            rq_edge = rq_prob - market_imp
            rq_ev = (rq_prob / 100) * rq_odds - 1.0
            # RQSPF安全边际: edge门槛5pp (让球盘概率估算误差大)
            rq_min_edge = 5.0
            if rq_ev > 0 and rq_edge >= rq_min_edge:
                opportunities.append(BetOpportunity(
                    match_id=mid, match_name=mn, kickoff=ko,
                    play_type="rqspf", pick=rq.get("pick_short", rq.get("pick", "")),
                    pick_short=rq.get("pick_short", "让球"),
                    model_prob=round(rq_prob, 1), odds=rq_odds,
                    edge_pct=round(rq_edge, 1), ev=round(rq_ev, 3),
                    kelly_full_pct=0, stake=0,
                    confidence=conf, delta=delta,
                    market_implied=round(market_imp, 1),
                    handicap_line=rq.get("handicap_line", 0),
                    note=f"让{rq.get('handicap_line',0)}球 xG差={rq.get('adjusted_diff',0):+.1f}",
                ))

        # ── 总进球数 ──
        tg = c.get("tg_pred")
        tg_sp = _match_tg_sp(mid)
        if tg and tg_sp:
            for goals_key in [tg["primary"], tg.get("secondary", "")]:
                if not goals_key:
                    continue
                tg_edge = compute_tg_edge(goals_key, tg_sp, xg_total)
                if tg_edge["is_value"] and tg_edge["ev"] > 0:
                    opportunities.append(BetOpportunity(
                        match_id=mid, match_name=mn, kickoff=ko,
                        play_type="total_goals",
                        pick=f"总进球{goals_key}球",
                        pick_short=f"总进球{goals_key}球",
                        model_prob=tg_edge["model_implied"],
                        odds=tg_edge["odds"],
                        edge_pct=tg_edge["edge"], ev=tg_edge["ev"],
                        kelly_full_pct=0, stake=0,
                        confidence=conf, delta=delta,
                        market_implied=tg_edge.get("market_implied", 0),
                        note=f"xG={xg_total:.1f}",
                    ))

        # ── 半全场 ──
        ht = c.get("htft")
        if ht and ht.get("odds", 0) > 1.0:
            ht_odds = ht["odds"]
            market_imp = 1.0 / ht_odds * 100
            # 半全场概率: 基于胜平负概率打折
            # 半全场Poisson精确概率 (半场xG=全场×0.45)
            ht_prob = _htft_poisson_prob(c["xg_home"], c["xg_away"], ht['pick'])
            ht_edge = ht_prob - market_imp
            ht_ev = (ht_prob / 100) * ht_odds - 1.0
            if ht_ev > 0 and ht_odds <= config.max_odds:
                opportunities.append(BetOpportunity(
                    match_id=mid, match_name=mn, kickoff=ko,
                    play_type="half_full",
                    pick=f"半全场-{ht['pick']}",
                    pick_short=f"半全{ht['pick']}",
                    model_prob=round(ht_prob, 1), odds=ht_odds,
                    edge_pct=round(ht_edge, 1), ev=round(ht_ev, 3),
                    kelly_full_pct=0, stake=0,
                    confidence=conf, delta=delta,
                    market_implied=round(market_imp, 1),
                ))

        # ── 比分 (仅高置信+SP数据) ──
        if conf == "高" and c.get("top_score"):
            score_sp = _match_score_sp(mid)
            top = c["top_score"]
            if score_sp and top in score_sp:
                s_odds = score_sp[top]
                if s_odds > 1.0:
                    s_prob = c["top3_scores"][0] if c.get("top3_scores") else 8.0
                    if isinstance(s_prob, str):
                        s_prob = 8.0
                    s_market_imp = 1.0 / s_odds * 100
                    s_edge = s_prob - s_market_imp
                    s_ev = (s_prob / 100) * s_odds - 1.0
                    if s_ev > 0 and s_odds <= config.max_odds:
                        opportunities.append(BetOpportunity(
                            match_id=mid, match_name=mn, kickoff=ko,
                            play_type="correct_score",
                            pick=f"比分{top}",
                            pick_short=f"比分{top}",
                            model_prob=float(s_prob), odds=s_odds,
                            edge_pct=round(s_edge, 1), ev=round(s_ev, 3),
                            kelly_full_pct=0, stake=0,
                            confidence=conf, delta=delta,
                            market_implied=round(s_market_imp, 1),
                        ))

    # 返回: (单注机会, 串关专用池)
    return opportunities, parlay_only_ops


def generate_parlay_opportunities(single_ops: list, config: PortfolioConfig) -> list:
    """
    从单注候选中生成串关: 2串1→3串1→4串1 + M串N容错(3串4)
    竞彩规则: SPF最多8串, RQSPF最多8串, 总进球最多6串, 混合以最低上限为准
    """
    parlays = []
    if len(single_ops) < 2:
        return parlays

    # 按风险调整EV排序选top
    ranked = sorted(single_ops, key=lambda o: o.ev / math.sqrt(max(0.1, o.odds - 1)), reverse=True)
    top15 = ranked[:15]
    top10 = ranked[:10]
    top8 = ranked[:8]

    def _make_multi_leg(ops_list, parlay_name, max_legs_per_match=1):
        """通用多串生成: n个单注组合"""
        n = len(ops_list)
        results = []
        indices = list(range(n))

        def _recurse(start, selected):
            if len(selected) >= 2:
                # 生成这个组合
                odds = 1.0
                prob = 1.0
                mkt_imp = 1.0
                match_ids_set = set()
                for op in selected:
                    odds *= op.odds
                    prob *= op.model_prob / 100.0
                    mkt_imp *= (op.market_implied / 100.0 if op.market_implied > 0 else 1.0 / op.odds)
                    match_ids_set.add(op.match_id)

                k = len(selected)
                combined_odds = round(odds, 2)
                if combined_odds < config.min_odds or combined_odds > 200.0:
                    return  # 不再继续(赔率已超界,更深串关更超)

                combined_prob_pct = prob * 100
                combined_ev = prob * combined_odds - 1.0
                if combined_ev <= 0:
                    return

                combined_edge = combined_prob_pct - mkt_imp * 100
                types = list(set(op.play_type for op in selected))
                type_label = "×".join(_play_type_name(t) for t in types) if len(types) > 1 else _play_type_name(types[0])

                if len(set(types)) == 1:
                    parlay_type = f"{k}串1-{types[0]}"
                else:
                    parlay_type = f"{k}串1-混合过关"

                match_name = " × ".join(f"[{op.pick_short}]{op.match_name}" for op in selected)
                pick = " + ".join(op.pick for op in selected)
                pick_short_list = ",".join(op.pick_short for op in selected)
                kickoff = max(op.kickoff for op in selected)
                conf = "高" if all(op.confidence == "高" for op in selected) else "中"

                # 串关让球信息汇总
                hcap_parts = []
                for op in selected:
                    h, _, _ = _handicap_note(op.match_id)
                    if h and h != 0:
                        label = f"让{abs(h)}球" if h < 0 else f"受{h}球"
                        hcap_parts.append(f"{op.match_id}({label})")
                hcap_note_str = " | ".join(hcap_parts) if hcap_parts else ""
                odds_str = "×".join(str(op.odds) for op in selected)
                note_str = f"{type_label} {odds_str}={combined_odds}"
                if hcap_note_str:
                    note_str += f" [{hcap_note_str}]"

                results.append(BetOpportunity(
                    match_id="+".join(op.match_id for op in selected),
                    match_name=match_name, kickoff=kickoff,
                    play_type=parlay_type,
                    pick=pick,
                    pick_short=f"{k}串1({pick_short_list})",
                    model_prob=round(combined_prob_pct, 1),
                    odds=combined_odds,
                    edge_pct=round(combined_edge, 1),
                    ev=round(combined_ev, 3),
                    kelly_full_pct=0, stake=0,
                    confidence=conf, delta=0,
                    market_implied=round(mkt_imp * 100, 1),
                    note=note_str,
                ))

            if len(selected) >= parlay_name:  # 达到目标串数
                return

            for i in range(start, n):
                op = ops_list[i]
                # 跳过同场比赛
                if any(op.match_id == s.match_id for s in selected):
                    continue
                # 跳过已超界的组合
                if selected:
                    test_odds = math.prod(s.odds for s in selected) * op.odds
                    if test_odds > 200.0:
                        continue
                _recurse(i + 1, selected + [op])

        _recurse(0, [])
        return results

    # ── 2串1 (from top15, 已有但用递归统一生成) ──
    parlays.extend(_make_multi_leg(top15, 2))

    # ── 3串1 (from top10, C(10,3)=120) ──
    parlays.extend(_make_multi_leg(top10, 3))

    # ── 4串1 (from top8, C(8,4)=70) ──
    parlays.extend(_make_multi_leg(top8, 4))

    # ── 3串4 (M串N容错) ──
    # 对top 3串1候选, 生成3串4结构: 3注2串1 + 1注3串1 = 4注/倍 = 8元/倍
    top3s = [p for p in parlays if p.play_type.startswith("3串1")]
    top3s.sort(key=lambda o: o.ev / math.sqrt(max(0.1, o.odds - 1)), reverse=True)
    for t3 in top3s[:8]:  # top8个3串1
        legs = t3.match_id.split("+")
        if len(legs) != 3:
            continue
        # 找对应的单注
        leg_ops = []
        for lid in legs:
            found = next((o for o in top15 if o.match_id == lid), None)
            if found:
                leg_ops.append(found)
        if len(leg_ops) != 3:
            continue

        # 3注2串1赔率
        pairs = [(0,1),(0,2),(1,2)]
        pair_odds = [round(leg_ops[i].odds * leg_ops[j].odds, 2) for i,j in pairs]
        # 1注3串1赔率
        triple_odds = t3.odds
        # 总投入: 4注×2元=8元/倍
        cost_per_unit = 8

        # 最大回报(全中): sum(3注2串1) + 1注3串1
        # 最小回报(错1场): min(2串1) — 还有1注2串1命中
        min_pair = min(pair_odds)
        max_return = round(sum(pair_odds) * 2 + triple_odds * 2, 0)

        # 3串4的等效EV: 考虑容错
        # 全中概率 = 三场都中
        full_prob = math.prod(o.model_prob / 100.0 for o in leg_ops)
        # 错1场概率 = 任意2场中+1场错
        miss1_prob = 0.0
        for miss_idx in range(3):
            p_miss = 1.0
            for j in range(3):
                if j == miss_idx:
                    p_miss *= (1.0 - leg_ops[j].model_prob / 100.0)
                else:
                    p_miss *= leg_ops[j].model_prob / 100.0
            miss1_prob += p_miss

        expected_return_34 = full_prob * max_return + miss1_prob * min_pair * 2
        combined_ev = expected_return_34 / cost_per_unit - 1.0 if cost_per_unit > 0 else 0
        if combined_ev <= 0:
            continue

        # 等效赔率: 最大回报/投入
        equiv_odds = round(max_return / cost_per_unit, 1)

        parlays.append(BetOpportunity(
            match_id=t3.match_id,
            match_name=t3.match_name,
            kickoff=t3.kickoff,
            play_type="3串4-M串N",
            pick=f"3串4: {t3.pick}",
            pick_short=f"3串4({t3.pick_short})",
            model_prob=round(full_prob * 100, 1),
            odds=equiv_odds,
            edge_pct=round(t3.model_prob - (1.0 / equiv_odds * 100), 1),
            ev=round(combined_ev, 3),
            kelly_full_pct=0, stake=0,
            confidence=t3.confidence, delta=0,
            market_implied=round(1.0 / equiv_odds * 100, 1),
            note=f"M串N容错 3×2串1+1×3串1={4}注/倍 全中≈{max_return}元 错1场保{pair_odds.index(min_pair)+1}注",
        ))

    # 去重: match_id + play_type 作为key (3串1和3串4同腿不冲突)
    seen = set()
    deduped = []
    for p in parlays:
        key = p.play_type + "|" + "+".join(sorted(p.match_id.split("+")))
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    # 按风险调整EV排序
    deduped.sort(key=lambda o: o.ev / math.sqrt(max(0.1, o.odds - 1)), reverse=True)
    return deduped[:80]  # 最多80个串关候选


def kelly_stake(edge_pct: float, odds: float, bankroll: float, fraction: float = 0.25) -> float:
    """
    凯利准则仓位计算
    f* = (p*b - q) / b  其中 b = odds-1, p = model_prob, q = 1-p
    返回: 建议投注金额(元)
    """
    if odds <= 1.0 or edge_pct <= 0:
        return 0.0
    model_prob = edge_pct / 100.0 + 1.0 / odds
    # 概率合理性校验
    if model_prob <= 0 or model_prob >= 1:
        return 0.0
    b = odds - 1.0
    q = 1.0 - model_prob
    full_kelly = max(0.0, (model_prob * b - q) / b)
    stake = bankroll * full_kelly * fraction
    return round(stake, 1)


def select_portfolio(opportunities: list, config: PortfolioConfig = None) -> PortfolioResult:
    """
    投资组合选择器: 贪婪算法, 风险调整EV排序
    """
    if config is None:
        config = PortfolioConfig()

    # 1. 过滤
    filtered = []
    for op in opportunities:
        if op.edge_pct < config.min_edge_pct:
            continue
        if op.odds < config.min_odds or op.odds > config.max_odds:
            continue
        if op.confidence == "低":
            continue
        if op.ev <= 0:
            continue
        filtered.append(op)

    # 2. RQSPF优先: 同一比赛有SPF和RQSPF时, 若RQSPF在黄金区间而SPF不在, 仅保留RQSPF
    if config.rqspf_preference:
        match_ops = {}
        for op in filtered:
            match_ops.setdefault(op.match_id, []).append(op)
        suppressed = []
        for mid, ops in match_ops.items():
            has_rqspf = any(o.play_type == "rqspf" for o in ops)
            has_spf = any(o.play_type == "spf" for o in ops)
            if has_rqspf and has_spf:
                rq_odds = next((o.odds for o in ops if o.play_type == "rqspf"), 0)
                sp_odds = next((o.odds for o in ops if o.play_type == "spf"), 0)
                rq_golden = config.golden_odds_min <= rq_odds <= config.golden_odds_max
                sp_golden = config.golden_odds_min <= sp_odds <= config.golden_odds_max
                if rq_golden and not sp_golden:
                    suppressed.extend([o for o in ops if o.play_type == "spf"])
        filtered = [o for o in filtered if o not in suppressed]

    # 3. 排序: 风险调整EV × Edge可靠性系数
    # Edge可靠性: SPF单注(1.0) > RQSPF/TG(0.8) > 串关(0.6)
    edge_reliability = {"spf": 1.0, "rqspf": 0.8, "total_goals": 0.8, "half_full": 0.7, "correct_score": 0.6}
    def sharpe_ev(op):
        variance_penalty = math.sqrt(max(0.1, op.odds - 1.0))
        base_type = op.play_type.split("-")[0].split("串")[0]
        reliability = 0.6  # default: parlay
        for key, r in edge_reliability.items():
            if key in op.play_type: reliability = r; break
        return op.ev / variance_penalty * reliability
    filtered.sort(key=sharpe_ev, reverse=True)

    # 3.5 同场对立方向检测: 禁止同一比赛同时押主胜+客胜/让球主胜+让球客胜
    match_directions = {}
    clean_filtered = []
    for op in filtered:
        dir_key = _direction_key(op)
        prev_dir = match_directions.get(op.match_id, "")
        # 检测对立: 主胜 vs 客胜, 主胜方向 vs 客胜方向
        opposing = (("主胜" in dir_key and "客胜" in prev_dir) or
                    ("客胜" in dir_key and "主胜" in prev_dir))
        if opposing:
            continue  # 跳过对立方向的第二注
        match_directions[op.match_id] = dir_key
        clean_filtered.append(op)
    filtered = clean_filtered

    # 3.6 强制锚定: 确保至少2注含强队胜方向
    # 锚定可以是: SPF单注(赔率1.5-3.0) 或 2串1中含强队胜的串关
    anchors = []
    for o in filtered:
        is_win_dir = ("主胜" in _direction_key(o) or "SPF-home" in o.pick_short or "SPF-away" in o.pick_short)
        # SPF单注锚定: 赔率1.5-3.0, prob>45%
        if is_win_dir and o.play_type == "spf" and 1.5 <= o.odds <= 3.0 and o.model_prob > 45:
            anchors.append(o)
        # 串关中含强队胜: 赔率3-15, prob>15%
        elif "串1" in o.play_type and is_win_dir and 3.0 <= o.odds <= 15.0 and o.model_prob > 15:
            anchors.append(o)
    # 按edge排序取top2
    anchors.sort(key=lambda o: o.edge_pct, reverse=True)
    anchors = anchors[:3]

    # 4. 计算Kelly仓位
    for op in filtered:
        stake = kelly_stake(op.edge_pct, op.odds, config.budget, config.kelly_fraction)
        stake = max(config.min_stake_per_bet, min(config.max_stake_per_bet, stake))
        # M串N: 3串4 = 8元/倍, 取整倍数
        if op.play_type == "3串4-M串N":
            unit = 8  # 4注×2元
            if stake >= unit:
                stake = int(stake / unit) * unit
            else:
                stake = unit  # 至少1倍
        op.stake = round(stake, 1)
        op.kelly_full_pct = round((op.edge_pct / (op.odds - 1.0)) * 100, 1) if op.odds > 1.0 else 0

    # 5. 贪婪填充 (锚定优先 + 平局上限)
    selected = []
    match_bet_count = {}
    direction_count = {"主胜": 0, "客胜": 0, "平局": 0, "其他": 0}
    draw_count = 0
    total_spent = 0

    # 5a. 先选锚定 (强队胜方向, 赔率1.5-2.8)
    anchor_filled = 0
    for op in anchors:
        if anchor_filled >= 2: break
        if match_bet_count.get(op.match_id, 0) >= config.max_bets_per_match: continue
        if total_spent + op.stake > config.budget: continue
        selected.append(op)
        match_bet_count[op.match_id] = match_bet_count.get(op.match_id, 0) + 1
        direction_count[_direction_key(op)] = direction_count.get(_direction_key(op), 0) + op.stake
        total_spent += op.stake
        anchor_filled += 1

    # 5b. 填充剩余 (平局/冷门不超过40%)
    max_draws = max(2, int(config.max_portfolio_bets * 0.4))
    for op in filtered:
        if op in selected: continue
        if len(selected) >= config.max_portfolio_bets: break
        if match_bet_count.get(op.match_id, 0) >= config.max_bets_per_match: continue

        dir_key = _direction_key(op)
        is_draw = ("平局" in dir_key or "draw" in op.pick_short.lower() or "让球平" in op.pick_short)
        if is_draw and draw_count >= max_draws: continue

        dir_current = direction_count.get(dir_key, 0) + op.stake
        if dir_current / config.budget > config.max_concentration_pct: continue

        if total_spent + op.stake > config.budget:
            remaining = config.budget - total_spent
            if remaining >= config.min_stake_per_bet:
                op.stake = remaining
            else: continue

        selected.append(op)
        match_bet_count[op.match_id] = match_bet_count.get(op.match_id, 0) + 1
        direction_count[dir_key] = direction_count.get(dir_key, 0) + op.stake
        if is_draw: draw_count += 1
        total_spent += op.stake

    # 6. 保留金
    reserve = config.budget - total_spent
    min_reserve = int(config.budget * config.reserve_min_pct)
    if reserve < min_reserve and selected:
        # 从最小仓位削减
        selected.sort(key=lambda o: o.stake)
        for op in selected:
            reduction = min(op.stake - config.min_stake_per_bet, min_reserve - reserve)
            if reduction > 0:
                op.stake -= reduction
                total_spent -= reduction
                reserve += reduction
            if reserve >= min_reserve:
                break

    total_spent = int(sum(o.stake for o in selected))
    reserve = config.budget - total_spent

    # 7. 构建结果
    total_ev = sum(o.ev * o.stake for o in selected) / max(1, total_spent) * 100
    expected_ret = sum(o.stake * o.odds * o.model_prob / 100 for o in selected)

    # 最大方向暴露
    max_dir = max(direction_count.items(), key=lambda x: x[1]) if direction_count else ("none", 0)

    result = PortfolioResult(
        bets=selected,
        total_stake=total_spent,
        reserve=reserve,
        total_ev_pct=round(total_ev, 1),
        expected_return=round(expected_ret, 0),
        opportunities_scanned=len(opportunities),
        opportunities_selected=len(selected),
        concentration={
            "max_direction": max_dir[0],
            "max_direction_pct": round(max_dir[1] / max(1, config.budget) * 100, 1),
            "max_match_exposure": max(match_bet_count.values()) if match_bet_count else 0,
        },
    )
    return result


def _direction_key(op: BetOpportunity) -> str:
    """提取投注方向关键字（用于集中度计算）"""
    pick = op.pick_short + op.pick + op.play_type
    if "主胜" in pick or "胜胜" in pick or ("half_full" in op.play_type and op.pick.endswith("胜")):
        return "主胜方向"
    elif "客胜" in pick or "负负" in pick or ("half_full" in op.play_type and op.pick.endswith("负")):
        return "客胜方向"
    elif ("平" in op.pick_short and "平局" in pick) or "平平" in pick or "让球平" in pick:
        return "平局方向"
    elif op.play_type == "total_goals":
        return "总进球数"
    else:
        return op.play_type


# ═══════════════════════════════════════════════════════════════
# 主入口: generate_plan (签名保持兼容)
# ═══════════════════════════════════════════════════════════════

def generate_plan(matches: list) -> dict:
    """
    竞彩方案 v6.0: 生成收益最大化投资组合 (替代均匀仓位分配)
    参数 matches: 比赛ID列表, 如 ["BEL-IRN","ESP-KSA",...]
    返回: dict (兼容旧格式 + 新结构化字段)
    """
    config = PortfolioConfig(
        budget=RULE["budget"],
        min_edge_pct=RULE["min_edge_pct"],
        max_bets_per_match=RULE["max_bets_per_match"],
        max_stake_per_bet=RULE["max_stake_per_bet"],
        min_stake_per_bet=RULE["min_stake_per_bet"],
        kelly_fraction=RULE["kelly_fraction"],
        min_odds=RULE["min_odds"],
        max_odds=RULE["max_odds"],
        max_portfolio_bets=RULE["max_portfolio_bets"],
        rqspf_preference=RULE["rqspf_preference"],
        golden_odds_min=RULE["golden_odds_min"],
        golden_odds_max=RULE["golden_odds_max"],
        max_concentration_pct=RULE["max_concentration_pct"],
        reserve_min_pct=RULE["reserve_min_pct"],
    )

    # P0: 截止时间检查
    skipped_deadline = []
    valid_matches = []
    for m in matches:
        can_bet, reason = _check_deadline(m)
        if can_bet:
            valid_matches.append(m)
        else:
            skipped_deadline.append((m, reason))

    # 预测 + 分类
    results = {}
    classified = []
    for m in valid_matches:
        p = predict(m)
        if "error" not in p:
            c = classify_match(m, p)
            classified.append(c)
            results[m] = c

    if not classified:
        return {
            "error": "无有效比赛" if not skipped_deadline else f"所有比赛已跳过({len(skipped_deadline)}场)",
            "skipped": skipped_deadline,
            "portfolio": None,
        }

    # EV标注
    ev_enabled = False
    real_sp_count = sum(1 for c in classified if _match_sp(c["match_id"]))
    if real_sp_count >= len(classified) * 0.5:
        ev_enabled = True
        for c in classified:
            val = compute_value(c["match_id"], c["direction"], c["dir_prob"])
            c["value"] = val
            c["is_value"] = val["is_value"]
            c["ev_score"] = val["ev"]

    # ★ 生成所有单注投注机会 (单关SPF + RQSPF + 总进球 + 半全场)
    single_opportunities, parlay_only_ops = generate_all_opportunities(classified, config)

    # ★ 生成串关机会: 合并单关SPF + 非单关SPF → 串关池
    all_for_parlay = single_opportunities + parlay_only_ops
    parlay_opportunities = generate_parlay_opportunities(all_for_parlay, config)

    # ★ 合并: 单注 + 串关 → 统一池
    all_opportunities = single_opportunities + parlay_opportunities

    # ★ 投资组合选择
    portfolio = select_portfolio(all_opportunities, config)

    # 排除场次信息
    excluded_pool = [c for c in classified if c.get("is_excluded")]
    risk_notes = []
    for c in excluded_pool:
        reason = c["confidence"] if "低" in c.get("confidence", "") else c.get("cold_alert", "")
        risk_notes.append(f"排除 {c['match_name']}: {reason}")

    # SPF池信息（向后兼容）
    cons_pool = sorted(
        [c for c in classified if c.get("is_conservative")],
        key=lambda x: (x.get("dir_prob", 0), abs(x.get("delta", 0))), reverse=True
    )
    banker_pool = sorted(
        [c for c in classified if c.get("is_banker")],
        key=lambda x: (x.get("dir_prob", 0), abs(x.get("delta", 0))), reverse=True
    )

    # 单关推荐
    dyn_singles = {m for m in results if _is_single_match(m)}
    dyn_singles.update(RULE.get("single_matches", []))
    single_bets = []
    for c in classified:
        if c["match_id"] in dyn_singles and not c.get("is_excluded") and c["direction"] != "draw" and c.get("dir_prob", 0) >= 40:
            bet_info = {
                "match": c["match_name"], "match_id": c["match_id"],
                "spf_pick": c["dir_name"], "spf_prob": c["dir_prob"],
                "spf_odds": est_odds(c["dir_prob"], match_id=c["match_id"], direction=c["direction"]),
                "kickoff": c["kickoff"],
            }
            if c.get("rqspf"):
                bet_info["rqspf_pick"] = c["rqspf"]["pick"]
                bet_info["rqspf_odds"] = c["rqspf"].get("odds", 0)
            if c.get("tg_pred"):
                bet_info["tg_pick"] = f"总进球{c['tg_pred']['primary']}球"
                bet_info["tg_odds"] = c["tg_pred"].get("odds", 0)
            single_bets.append(bet_info)

    # 构建返回 (兼容旧dashboard.py)
    plan = {
        "generated_by": "竞彩方案 v6.0 (收益最大化·Kelly仓位·正EV精选)",
        "total_budget": config.budget,
        "skipped": skipped_deadline,
        # ★ v6.0 核心: 投资组合
        "portfolio": portfolio,
        "opportunities_total": len(all_opportunities),
        # 向后兼容字段
        "classified": {
            "banker_pool": [c["match_name"] for c in banker_pool],
            "conservative_pool": [c["match_name"] for c in cons_pool],
            "excluded_pool": [c["match_name"] for c in excluded_pool],
        },
        "single_bets": single_bets,
        "single_bet_note": "单关场次建议单独投注; RQSPF赔率更优时可替代SPF" if single_bets else "",
        "risk_notes": risk_notes,
        "ev_enabled": ev_enabled,
    }
    return plan


# ═══════════════════════════════════════════════════════════════
# 格式化输出: format_lottery
# ═══════════════════════════════════════════════════════════════

def format_lottery(plan: dict) -> str:
    """竞彩方案 v6.0 格式化输出"""
    if "error" in plan:
        msg = f"❌ {plan['error']}"
        skipped = plan.get("skipped", [])
        if skipped:
            msg += f"\n   跳过场次: {', '.join(m+'('+r+')' for m,r in skipped[:5])}"
            msg += "\n💡 建议: 今日无可投场次, 保留资金等待明日"
        return msg

    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = []
    L.append("═" * 68)
    L.append("  竞彩方案 v6.0 · 2026世界杯 · 最优投资组合")
    L.append(f"  生成时间: {now_ts}  |  预算上限: {plan['total_budget']}元")
    L.append(f"  策略: 正EV精选 + 1/4 Kelly仓位 | 机会驱动·非均衡分配")
    L.append("═" * 68)

    # 跳过信息
    skipped = plan.get("skipped", [])
    if skipped:
        L.append(f"\n⚠️ 已跳过 {len(skipped)} 场 (开球/不足15分钟):")
        for m, reason in skipped[:4]:
            L.append(f"  • {m}: {reason}")

    # ★ 投资组合核心
    portfolio = plan.get("portfolio")
    if portfolio is None:
        L.append("\n❌ 未生成投资组合")
        return "\n".join(L)

    ops_total = plan.get("opportunities_total", 0)
    ops_sel = portfolio.opportunities_selected
    L.append(f"\n📊 市场扫描: {len(plan.get('classified',{}).get('conservative_pool',[]))}场可投 → {ops_total}个投注机会 → {ops_sel}个入选")
    L.append(f"💰 已部署: {portfolio.total_stake}元  |  保留: {portfolio.reserve}元")
    L.append(f"📈 组合期望: EV+{portfolio.total_ev_pct}%  |  预期回报: ≈{portfolio.expected_return:.0f}元")

    # 集中度
    conc = portfolio.concentration
    if conc:
        L.append(f"🎯 集中度: 最大方向{conc.get('max_direction','?')} {conc.get('max_direction_pct',0)}%  |  最多{conc.get('max_match_exposure',0)}注/场")

    L.append("─" * 68)

    # 排名列表
    if not portfolio.bets:
        L.append("\n⚠️ 今日无符合条件的正EV投注机会")
        L.append(f"   保留{plan['total_budget']}元等待明日更好机会")
        reserve_reason = "无正EV机会"
    else:
        medals = ["🥇", "🥈", "🥉"] + [f"  {i+1}." for i in range(3, len(portfolio.bets))]
        for i, bet in enumerate(portfolio.bets):
            medal = medals[i] if i < len(medals) else f"  {i+1}."
            L.append("")
            L.append(f"{medal} #{i+1} {_play_type_name(bet.play_type)} · {bet.match_name}")
            # 让球盘信息
            hcap_str = ""
            if bet.handicap_line and bet.handicap_line != 0:
                hcap_label = f"让{abs(bet.handicap_line)}球" if bet.handicap_line < 0 else f"受{bet.handicap_line}球"
                hcap_str = f"  |  让球盘: {hcap_label}"
            L.append(f"   方向: {bet.pick:<24} 赔率: {bet.odds:.2f}{hcap_str}")
            L.append(f"   模型概率: {bet.model_prob}%  |  市场隐含: {bet.market_implied}%  |  Edge: {bet.edge_pct:+.1f}pp")
            L.append(f"   EV: {bet.ev:+.1%}  |  凯利仓位: {bet.stake:.0f}元 (1/{1/RULE['kelly_fraction']:.0f}凯利)")
            if bet.note:
                L.append(f"   依据: {bet.note}")

        reserve_reason = "按投资组合纪律保留"

    L.append("")
    L.append("─" * 68)

    # 风险提示
    L.append(f"\n🛡️ 风险管理:")
    L.append(f"  · 最大单注暴露: {max((b.stake for b in portfolio.bets), default=0):.0f}元 "
             f"({max((b.stake for b in portfolio.bets), default=0)/plan['total_budget']*100:.0f}% of budget)")
    if conc:
        L.append(f"  · 方向集中度: {conc.get('max_direction','?')}方向{conc.get('max_direction_pct',0)}% "
                 f"(阈值{RULE['max_concentration_pct']*100:.0f}%)")
        match_status = "✅安全" if conc.get('max_match_exposure', 0) <= RULE['max_bets_per_match'] else "⚠️超标"
        L.append(f"  · 比赛集中度: 最多{conc.get('max_match_exposure',0)}注/场 ({match_status})")
    L.append(f"  · 保留金: {portfolio.reserve}元 — {reserve_reason}")

    # 排除场次
    if plan.get("risk_notes"):
        L.append(f"\n⚠️ 排除场次:")
        for n in plan["risk_notes"][:5]:
            L.append(f"  • {n}")

    # 单关推荐
    single_bets = plan.get("single_bets", [])
    if single_bets:
        L.append(f"\n{'─'*68}")
        L.append(f"🎯 单关推荐 (可单独投注)")
        L.append(f"{'─'*68}")
        for sb in single_bets[:5]:
            L.append(f"  {sb['match']}")
            L.append(f"    SPF: {sb['spf_pick']:<16} 概率{sb['spf_prob']}%  赔率{sb.get('spf_odds','?')}")
            if sb.get("rqspf_pick"):
                L.append(f"    RQSPF: {sb['rqspf_pick']:<20} 赔率{sb.get('rqspf_odds','?')}")
            if sb.get("tg_pick"):
                L.append(f"    总进球: {sb['tg_pick']:<16} 赔率{sb.get('tg_odds','?')}")

    L.append("")
    L.append("═" * 68)
    L.append(f"📐 竞彩方案 v6.0 ({now_ts}) | 正EV+Kelly+组合优化 | 竞彩90分钟赛果为准 | 仅作参考")
    return "\n".join(L)


def _play_type_name(pt: str) -> str:
    """玩法中文名"""
    return {
        "spf": "胜平负",
        "rqspf": "让球胜平负",
        "total_goals": "总进球数",
        "correct_score": "比分",
        "half_full": "半全场",
    }.get(pt, pt)


# ═══════════════════════════════════════════════════════════════
# 兼容性别名 (dashboard.py / audit 引用)
# ═══════════════════════════════════════════════════════════════

# filter_value_bets 保留名义供 audit 引用, 内部不再使用
def filter_value_bets(classified: list) -> list:
    """正EV筛选 (v5.0兼容, v6.0已内置在generate_all_opportunities)"""
    for c in classified:
        val = compute_value(c["match_id"], c["direction"], c["dir_prob"])
        c["value"] = val
        c["is_value"] = val["is_value"]
        c["ev_score"] = val["ev"]
    value_bets = [c for c in classified if c.get("is_value")]
    value_bets.sort(key=lambda x: x.get("ev_score", 0), reverse=True)
    return value_bets
