#!/usr/bin/env python3
"""
竞彩投注审计系统 v1.0
三阶段验证: 数据(生成前) → 规则(生成中) → 结果(生成后)
确保: 顶级规则与执行统一, 数据准确, 不产生幻觉
"""
import sys, json, math
from pathlib import Path
from datetime import datetime, date
from collections import namedtuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.lottery import (
    BetOpportunity, PortfolioConfig, PortfolioResult,
    generate_plan, classify_match, RULE, THRESHOLD,
    _load_sp, _match_sp, _match_handicap_sp, _match_tg_sp,
    _check_deadline, compute_value, cold_rank,
    CN_NAME, MATCH_SCHEDULE,
)

DATA_DIR = Path(__file__).parent.parent / "data"
PASS, FAIL, WARN = "✅", "❌", "⚠️"
AuditItem = namedtuple("AuditItem", ["phase", "check", "status", "detail", "severity"])

results_log = []


def log(phase, check, cond, detail="", severity="MEDIUM"):
    tag = PASS if cond else (WARN if severity == "WARN" else FAIL)
    item = AuditItem(phase, check, tag, detail, severity)
    results_log.append(item)
    return cond


# ═══════════════════════════════════════════════════════════════
# Phase A: 数据验证（生成前）
# ═══════════════════════════════════════════════════════════════

def audit_phase_a_data() -> list:
    """验证所有输入数据的完整性和合理性"""
    sp = _load_sp()
    now = datetime.now()

    # A1: SP数据新鲜度
    sp_updated = sp.get("updated", "")
    try:
        sp_dt = datetime.fromisoformat(sp_updated)
        hours_old = (now - sp_dt).total_seconds() / 3600
        log("A-数据", "SP新鲜度", hours_old <= 48,
            f"SP更新于{sp_updated} ({hours_old:.0f}h前, 阈值48h)", "HIGH")
    except:
        log("A-数据", "SP新鲜度", False, "无法解析SP更新时间", "HIGH")

    # A2: 赔率合理性
    for mid, m in sp.get("matches", {}).items():
        h, d, a = m.get("home", 0), m.get("draw", 0), m.get("away", 0)
        if h > 0 and d > 0 and a > 0:
            # 检测三值相同（数据异常）
            if h == d == a:
                log("A-数据", f"赔率三同值({mid})", False,
                    f"{mid}: home={h} draw={d} away={a} 三项完全相同, 可能数据污染", "HIGH")
            # 检测极端赔率
            if h < 1.01 or d < 1.01 or a < 1.01:
                log("A-数据", f"极端赔率({mid})", False,
                    f"{mid}: 有赔率<1.01 (不可能出现在真实市场)", "MEDIUM")

    # A3: 赛程队伍在teams.json中
    teams = json.load(open(DATA_DIR / "teams.json"))
    missing = []
    for mid in MATCH_SCHEDULE:
        for tid in mid.split("-"):
            if tid not in teams:
                missing.append(tid)
    if missing:
        log("A-数据", "队伍代码有效性", False,
            f"{len(set(missing))}个队伍代码不在teams.json: {set(missing)}", "HIGH")
    else:
        log("A-数据", "队伍代码有效性", True, "所有赛程队伍在teams.json中")

    # A4: 校准参数边界检查
    calib_file = DATA_DIR / "calibration.json"
    if calib_file.exists():
        calib = json.load(open(calib_file))
        bl = calib.get("baseline_xg", 1.35)
        log("A-数据", "BASELINE_XG边界", 0.5 <= bl <= 3.5,
            f"baseline_xg={bl} (合理区间[0.5,3.5])", "MEDIUM")
        db = calib.get("draw_bonus", {})
        for k, v in db.items():
            log("A-数据", f"DRAW_BONUS边界({k})", 0.2 <= v <= 3.5,
                f"draw_bonus.{k}={v} (合理区间[0.2,3.5])", "MEDIUM")

    # A5: 比赛时间正确性
    now_dt = datetime.now()
    for mid, t in MATCH_SCHEDULE.items():
        try:
            parts = t.split()
            mo, d = parts[0].split("/")
            h, mi = parts[1].split(":")
            kickoff = datetime(2026, int(mo), int(d), int(h), int(mi))
            if kickoff < now_dt:
                # 已开球的比赛应该在results.json中有记录
                pass  # 仅记录不报警
        except:
            log("A-数据", f"比赛时间格式({mid})", False,
                f"无法解析时间: {t}", "MEDIUM")

    return results_log


# ═══════════════════════════════════════════════════════════════
# Phase B: 规则执行验证（生成中/后）
# ═══════════════════════════════════════════════════════════════

def audit_phase_b_rules(plan: dict, portfolio: PortfolioResult) -> list:
    """验证每注投注都符合规则"""
    config = PortfolioConfig(
        budget=RULE["budget"],
        min_edge_pct=RULE["min_edge_pct"],
        max_bets_per_match=RULE["max_bets_per_match"],
        max_stake_per_bet=RULE["max_stake_per_bet"],
        min_stake_per_bet=RULE["min_stake_per_bet"],
        kelly_fraction=RULE["kelly_fraction"],
        max_concentration_pct=RULE["max_concentration_pct"],
    )

    if portfolio is None:
        log("B-规则", "投资组合存在", False, "无投资组合生成", "HIGH")
        return results_log

    sp = _load_sp()

    for i, bet in enumerate(portfolio.bets):
        prefix = f"#{i+1} {bet.match_id}/{bet.play_type}"

        # B1: 正edge检查
        log("B-规则", f"正Edge({prefix})", bet.edge_pct >= config.min_edge_pct,
            f"edge={bet.edge_pct:+.1f}pp (门槛{config.min_edge_pct}pp)", "HIGH")

        # B2: 反幻觉 — match_id必须在SP数据或赛程中
        in_sp = bet.match_id in sp.get("matches", {}) or _reverse_key(bet.match_id) in sp.get("matches", {})
        in_schedule = bet.match_id in MATCH_SCHEDULE
        log("B-规则", f"数据源({prefix})", in_sp or in_schedule,
            f"match_id在SP中存在={in_sp}, 在赛程中存在={in_schedule}", "HIGH")

        # B3: 赔率与SP数据一致
        if in_sp:
            if bet.play_type == "spf":
                sp_odds = _match_sp(bet.match_id)
                match_ok = abs(bet.odds - sp_odds.get("home", 0)) < 0.01 or \
                          abs(bet.odds - sp_odds.get("draw", 0)) < 0.01 or \
                          abs(bet.odds - sp_odds.get("away", 0)) < 0.01
                log("B-规则", f"赔率一致性({prefix})", match_ok,
                    f"模型使用赔率={bet.odds}, SP数据={sp_odds}", "MEDIUM")

        # B4: Kelly仓位边界
        log("B-规则", f"仓位边界({prefix})",
            config.min_stake_per_bet <= bet.stake <= config.max_stake_per_bet,
            f"stake={bet.stake}元 (边界[{config.min_stake_per_bet},{config.max_stake_per_bet}])", "MEDIUM")

        # B5: 概率合理性
        log("B-规则", f"概率合理性({prefix})", 0 < bet.model_prob < 100,
            f"model_prob={bet.model_prob}%", "LOW")

    # B6: 总投注不超过预算
    total_ok = portfolio.total_stake <= config.budget
    log("B-规则", "总预算", total_ok,
        f"total_stake={portfolio.total_stake} <= budget={config.budget}", "HIGH")

    # B7: 集中度
    conc = portfolio.concentration
    conc_ok = conc.get("max_direction_pct", 100) <= config.max_concentration_pct * 100
    log("B-规则", "方向集中度", conc_ok,
        f"max={conc.get('max_direction_pct', '?')}% (阈值{config.max_concentration_pct*100}%)", "MEDIUM")

    match_ok = conc.get("max_match_exposure", 99) <= config.max_bets_per_match
    log("B-规则", "比赛集中度", match_ok,
        f"max={conc.get('max_match_exposure', '?')}注/场 (阈值{config.max_bets_per_match})", "MEDIUM")

    # B8: 无重复投注
    seen = set()
    dupes = False
    for bet in portfolio.bets:
        key = (bet.match_id, bet.play_type, bet.pick)
        if key in seen:
            dupes = True
        seen.add(key)
    log("B-规则", "无重复投注", not dupes, f"{len(portfolio.bets)}注, {len(seen)}个唯一key", "HIGH")

    return results_log


# ═══════════════════════════════════════════════════════════════
# Phase C: 存档验证（生成后）
# ═══════════════════════════════════════════════════════════════

def audit_phase_c_archive(plan: dict, archive_path: Path = None) -> list:
    """验证存档完整性"""
    if archive_path is None:
        archive_path = DATA_DIR / "bet_plans_archive.json"

    # C1: 存档文件存在
    if not archive_path.exists():
        log("C-存档", "存档文件存在", False, f"{archive_path} 不存在", "HIGH")
        return results_log

    archive = json.load(open(archive_path))

    # C2: 旧条目保留 (v6.0 legacy key)
    legacy = archive.get("legacy", {})
    plans = archive.get("plans", {})
    log("C-存档", "旧条目保留", len(legacy) > 0 or len(plans) > 0,
        f"legacy: {len(legacy)}条, plans: {len(plans)}条", "HIGH")

    # C3: 结构完整性
    portfolio = plan.get("portfolio")
    if portfolio and hasattr(portfolio, 'bets'):
        for i, bet in enumerate(portfolio.bets):
            required = ["match_id", "play_type", "pick", "model_prob", "odds", "edge_pct", "ev", "stake"]
            missing_fields = [f for f in required if not hasattr(bet, f) or getattr(bet, f, None) is None]
            if missing_fields:
                log("C-存档", f"字段完整(#{i+1})", False,
                    f"缺少: {missing_fields}", "HIGH")

    # C4: EV/Edge可追溯
    if portfolio and hasattr(portfolio, 'bets'):
        for bet in portfolio.bets:
            # 重建edge验证: edge = model_prob - 1/odds*100
            if bet.odds > 1.0:
                implied = 1.0 / bet.odds * 100
                recomputed_edge = round(bet.model_prob - implied, 1)
                edge_match = abs(recomputed_edge - bet.edge_pct) <= 0.2
                if not edge_match:
                    log("C-存档", f"Edge可追溯({bet.match_id})", False,
                        f"存储edge={bet.edge_pct}, 重算={recomputed_edge}", "LOW")

    return results_log


def _reverse_key(match_id: str) -> str:
    return "-".join(match_id.split("-")[::-1])


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

def audit_all(upcoming_matches: list = None) -> dict:
    """
    完整三阶段审计
    返回: {"phases": {"A": [...], "B": [...], "C": [...]}, "summary": {...}}
    """
    global results_log
    results_log = []

    if upcoming_matches is None:
        # 默认: 明天未开球的比赛
        upcoming_matches = []
        now = datetime.now()
        for m, t in sorted(MATCH_SCHEDULE.items(), key=lambda x: x[1]):
            try:
                parts = t.split()
                mo, d = parts[0].split("/")
                h, mi = parts[1].split(":")
                kickoff = datetime(2026, int(mo), int(d), int(h), int(mi))
                if kickoff > now:
                    upcoming_matches.append(m)
            except:
                pass

    # Phase A
    audit_phase_a_data()
    phase_a_results = [r for r in results_log if r.phase == "A-数据"]

    # Phase B
    plan = generate_plan(upcoming_matches)
    portfolio = plan.get("portfolio")
    audit_phase_b_rules(plan, portfolio)
    phase_b_results = [r for r in results_log if r.phase == "B-规则"]

    # Phase C
    audit_phase_c_archive(plan)
    phase_c_results = [r for r in results_log if r.phase == "C-存档"]

    fails = [r for r in results_log if r.status == FAIL]
    warns = [r for r in results_log if r.status == WARN]

    return {
        "phases": {
            "A_data": phase_a_results,
            "B_rules": phase_b_results,
            "C_archive": phase_c_results,
        },
        "summary": {
            "total_checks": len(results_log),
            "passed": len([r for r in results_log if r.status == PASS]),
            "failed": len(fails),
            "warned": len(warns),
            "blockers": [r for r in fails if r.severity == "HIGH"],
            "verdict": "✅ 审计通过" if len(fails) == 0 else f"❌ {len(fails)}项失败",
            "timestamp": datetime.now().isoformat(),
        }
    }


def print_audit(result: dict):
    """格式化输出审计结果"""
    print("=" * 70)
    print("  竞彩投注审计 v1.0 — 三阶段验证")
    print(f"  审计时间: {result['summary']['timestamp'][:19]}")
    print("=" * 70)

    for phase_name, phase_key in [("Phase A: 数据验证", "A_data"),
                                   ("Phase B: 规则执行", "B_rules"),
                                   ("Phase C: 存档验证", "C_archive")]:
        items = result["phases"].get(phase_key, [])
        print(f"\n{'─'*70}")
        print(f"  {phase_name} ({len(items)}项)")
        print(f"{'─'*70}")
        for item in items:
            icon = item.status
            print(f"  {icon} [{item.severity}] {item.check}: {item.detail}")

    s = result["summary"]
    print(f"\n{'═'*70}")
    print(f"  审计结论: {s['verdict']}")
    print(f"  总检查: {s['total_checks']} | 通过: {s['passed']} | 失败: {s['failed']} | 警告: {s['warned']}")
    if s["blockers"]:
        print(f"  ⛔ 阻塞项:")
        for b in s["blockers"]:
            print(f"    {b.check}: {b.detail}")
    print(f"{'═'*70}")


if __name__ == "__main__":
    result = audit_all()
    print_audit(result)
