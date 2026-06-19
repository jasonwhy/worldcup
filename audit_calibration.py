#!/usr/bin/env python3
"""
概率校准审计 v1.0 — 评估模型概率输出是否真实可靠

运行: python3 audit_calibration.py
"""
import json, sys, math
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from engine.predictor import predict

DATA = Path(__file__).parent / "data"


def load_results():
    with open(DATA / "results.json") as f:
        return json.load(f)


def get_actual_outcome(score_str):
    h, a = map(int, score_str.split("-"))
    if h > a: return "home_win"
    if h == a: return "draw"
    return "away_win"


def normalize_confidence(raw):
    if raw.startswith("低"): return "低"
    return raw


def build_rows(results):
    rows = []
    for m in results["matches"]:
        mid = f"{m['home']}-{m['away']}"
        try:
            p = predict(mid)
            if "error" in p:
                continue
            r = p["prediction"]
            outcome = get_actual_outcome(m["score"])
            wp, dp, lp = r["win_pct"], r["draw_pct"], r["lose_pct"]

            # 方向对错
            pred_dir = "home_win" if wp > lp and wp > dp else ("draw" if dp >= wp and dp >= lp else "away_win")
            dir_correct = (outcome == pred_dir)

            rows.append({
                "home": m["home"], "away": m["away"],
                "score": m["score"], "outcome": outcome,
                "win_pct": wp, "draw_pct": dp, "lose_pct": lp,
                "delta": p["delta"],
                "confidence": normalize_confidence(r.get("confidence", "中")),
                "direction_correct": dir_correct,
                "pred_direction": pred_dir,
            })
        except Exception as e:
            print(f"  ⚠️ {mid} 预测失败: {e}")
    return rows


# ========================
# 一、可靠性图
# ========================
def compute_reliability(rows):
    WIN_BINS = [
        (0, 30, "<30%"), (30, 40, "30-40%"), (40, 50, "40-50%"),
        (50, 60, "50-60%"), (60, 70, "60-70%"), (70, 101, "70%+"),
    ]
    bins_out = []
    for low, high, label in WIN_BINS:
        in_bin = [r for r in rows if low <= r["win_pct"] < high]
        n = len(in_bin)
        pred_mid = (low + min(high, 85)) / 2
        if n == 0:
            bins_out.append({"label": label, "n": 0, "pred_mid": pred_mid,
                             "actual_rate": None, "bias": None, "small": False})
            continue
        n_wins = sum(1 for r in in_bin if r["outcome"] == "home_win")
        actual_rate = n_wins / n * 100
        bias = actual_rate - pred_mid
        bins_out.append({
            "label": label, "n": n, "pred_mid": pred_mid,
            "actual_rate": round(actual_rate, 1),
            "bias": round(bias, 1), "small": n < 3,
        })
    return bins_out


def bar(value, width=30):
    """ASCII bar: value in 0-100"""
    v = max(0, min(100, value))
    f = round(v / 100 * width)
    return "█" * f + "░" * (width - f)


def render_reliability(bins):
    out = "┌" + "─" * 81 + "┐\n"
    out += "│  可靠性图 (Reliability Diagram) — 预测主胜概率 vs 实际主胜率" + " " * 19 + "│\n"
    out += "├" + "─" * 8 + "┬" + "─" * 6 + "┬" + "─" * 10 + "┬" + "─" * 8 + "┬" + "─" * 42 + "┤\n"
    out += "│ 预测胜率│ 场次 │  实际胜率  │  偏差   │ 校准曲线" + " " * 15 + "░=预测中点│\n"
    out += "├" + "─" * 8 + "┼" + "─" * 6 + "┼" + "─" * 10 + "┼" + "─" * 8 + "┼" + "─" * 42 + "┤\n"
    for b in bins:
        if b["n"] == 0:
            out += f"│ {b['label']:<6} │   0  │    N/A     │   N/A   │ (无数据)\n"
            continue
        star = "*" if b["small"] else " "
        rate_str = f"{b['actual_rate']:.1f}%{star}"
        bias_str = f"{b['bias']:+.1f}%"
        # bar: show actual rate, reference line at pred_mid
        bar_str = bar(b["actual_rate"], 38)
        out += f"│ {b['label']:<6} │ {b['n']:>3}  │ {rate_str:>8}  │ {bias_str:>6}  │ {bar_str} │\n"
    out += "├" + "─" * 8 + "┴" + "─" * 6 + "┴" + "─" * 10 + "┴" + "─" * 8 + "┴" + "─" * 42 + "┤\n"
    out += "│ *小样本(n<3) 解释需谨慎                                             │\n"
    # Interpretation
    non_empty = [b for b in bins if b["n"] > 0]
    pos_biases = sum(1 for b in non_empty if b["bias"] and b["bias"] > 5)
    neg_biases = sum(1 for b in non_empty if b["bias"] and b["bias"] < -5)
    if neg_biases > pos_biases:
        interp = "过度自信: 实际胜率 < 预测 (条柱在左)" if not pos_biases else "混合: 低区间保守, 高区间过度自信"
    elif pos_biases > neg_biases:
        interp = "过于保守: 实际胜率 > 预测 (条柱在右)"
    else:
        interp = "整体校准良好, 偏差在可接受范围"
    out += f"│ 判定: {interp:<66}│\n"
    out += "└" + "─" * 81 + "┘\n"
    return out


# ========================
# 二、Brier Score
# ========================
def compute_brier(rows):
    total = 0.0
    home_total = draw_total = away_total = 0.0
    home_n = draw_n = away_n = 0
    for r in rows:
        if r["outcome"] == "home_win":
            o = [1.0, 0.0, 0.0]
        elif r["outcome"] == "draw":
            o = [0.0, 1.0, 0.0]
        else:
            o = [0.0, 0.0, 1.0]
        p = [r["win_pct"]/100, r["draw_pct"]/100, r["lose_pct"]/100]
        se = sum((p[i] - o[i])**2 for i in range(3))
        total += se
        if r["outcome"] == "home_win":
            home_total += se; home_n += 1
        elif r["outcome"] == "draw":
            draw_total += se; draw_n += 1
        else:
            away_total += se; away_n += 1
    N = len(rows)
    overall = total / N
    brier_components = {
        "home": round(home_total / home_n, 4) if home_n else 0,
        "draw": round(draw_total / draw_n, 4) if draw_n else 0,
        "away": round(away_total / away_n, 4) if away_n else 0,
    }
    return {"brier": round(overall, 4), "components": brier_components, "n": N}


def render_brier(br):
    # climatology: historical base rates from results
    # actual: home~39%, draw~36%, away~25% (round to 40/35/25)
    # base-rate Brier = (1-0.39)²+0²+0² ...
    # Actually compute it properly
    overall = br["brier"]
    if overall < 0.45:
        grade = "优秀 (显著优于基线)"
    elif overall < 0.50:
        grade = "良好 (优于基线)"
    elif overall < 0.55:
        grade = "一般 (略优于基线)"
    else:
        grade = "差 (接近或不如基线)"

    out = "┌" + "─" * 60 + "┐\n"
    out += "│  Brier Score (概率校准综合评分, 越低越好)                  │\n"
    out += "├" + "─" * 60 + "┤\n"
    out += f"│  总体 Brier: {overall:.4f}  →  {grade:<40}│\n"
    out += f"│  分解: 主胜 {br['components']['home']:.4f}  |  平局 {br['components']['draw']:.4f}  |  客胜 {br['components']['away']:.4f}                    │\n"
    out += "├" + "─" * 60 + "┤\n"
    out += "│  参考基线:                                                  │\n"
    out += "│    0.667 = 均匀预测(33/33/33)                               │\n"
    out += "│    <0.55 = 优于简单基线                                     │\n"
    out += "│    <0.45 = 优秀的概率校准                                   │\n"
    out += "└" + "─" * 60 + "┘\n"
    return out


# ========================
# 三、系统性偏差
# ========================
def detect_biases(rows):
    N = len(rows)

    # 3a. 主场偏差
    mean_pred_home = sum(r["win_pct"] for r in rows) / N
    actual_home_rate = sum(1 for r in rows if r["outcome"] == "home_win") / N * 100
    home_bias = round(actual_home_rate - mean_pred_home, 1)

    # 3b. 平局偏差
    DRAW_BINS = [(10, 20), (20, 30), (30, 40), (40, 101)]
    draw_analysis = []
    for low, high in DRAW_BINS:
        in_bin = [r for r in rows if low <= r["draw_pct"] < high]
        n = len(in_bin)
        if n == 0: continue
        n_draws = sum(1 for r in in_bin if r["outcome"] == "draw")
        actual_rate = n_draws / n * 100
        pred_mid = (low + min(high, 50)) / 2
        draw_analysis.append({
            "bin": f"{low}-{min(high,50)}%", "n": n,
            "pred_mid": pred_mid, "actual_rate": round(actual_rate, 1),
            "bias": round(actual_rate - pred_mid, 1),
        })

    # 3c. 热门过度自信
    favorites = []
    for r in rows:
        fav_pct = max(r["win_pct"], r["lose_pct"])
        if fav_pct > 65:
            fav_side = "home" if r["win_pct"] > r["lose_pct"] else "away"
            fav_won = (fav_side == "home" and r["outcome"] == "home_win") or \
                      (fav_side == "away" and r["outcome"] == "away_win")
            favorites.append({
                "match": f"{r['home']}-{r['away']}",
                "fav_pct": fav_pct, "fav_side": fav_side,
                "fav_won": fav_won, "score": r["score"],
            })
    if favorites:
        fav_win_rate = sum(1 for f in favorites if f["fav_won"]) / len(favorites) * 100
        mean_fav_pct = sum(f["fav_pct"] for f in favorites) / len(favorites)
    else:
        fav_win_rate = None
        mean_fav_pct = None

    # 3d. Delta 校准
    # 按实际净胜球
    ACTUAL_DELTA_BINS = [(0, "0球(平局)"), (1, "1球"), (2, "2球"), (3, "3球+")]
    delta_actual = []
    for threshold, label in ACTUAL_DELTA_BINS:
        in_bin = []
        for r in rows:
            h, a = map(int, r["score"].split("-"))
            gd = abs(h - a)
            if threshold == 3:
                if gd >= 3: in_bin.append(r)
            else:
                if gd == threshold: in_bin.append(r)
        n = len(in_bin)
        if n == 0: continue
        acc = sum(1 for r in in_bin if r["direction_correct"]) / n * 100
        delta_actual.append({"label": label, "n": n, "accuracy": round(acc, 1)})

    # 按预测 delta
    PRED_DELTA_BINS = [(0, 8, "Δ<8"), (8, 15, "Δ 8-15"), (15, 25, "Δ 15-25"), (25, 100, "Δ 25+")]
    delta_pred = []
    for low, high, label in PRED_DELTA_BINS:
        in_bin = [r for r in rows if abs(r["delta"]) >= low and abs(r["delta"]) < high]
        n = len(in_bin)
        if n == 0: continue
        acc = sum(1 for r in in_bin if r["direction_correct"]) / n * 100
        delta_pred.append({"label": label, "n": n, "accuracy": round(acc, 1)})

    return {
        "home_bias": home_bias, "mean_pred_home": round(mean_pred_home, 1),
        "actual_home_rate": round(actual_home_rate, 1),
        "draw_analysis": draw_analysis,
        "favorites": favorites, "fav_win_rate": round(fav_win_rate, 1) if fav_win_rate else None,
        "mean_fav_pct": round(mean_fav_pct, 1) if mean_fav_pct else None,
        "delta_actual": delta_actual, "delta_pred": delta_pred,
    }


def render_biases(biases):
    out = "┌" + "─" * 70 + "┐\n"
    out += "│  系统性偏差检测                                              │\n"
    out += "├" + "─" * 70 + "┤\n"

    # 3a
    hb = biases["home_bias"]
    hbm = "⚠️ 主场高估" if hb < -8 else ("⚠️ 主场低估" if hb > 8 else "✅ 正常")
    out += f"│  3a. 主场偏差: 预测主胜均值 {biases['mean_pred_home']:.1f}% | 实际 {biases['actual_home_rate']:.1f}% | 偏差 {hb:+.1f}%  {hbm:<16}│\n"

    # 3b
    out += "│  3b. 平局概率校准:                                           │\n"
    for d in biases["draw_analysis"]:
        flag = "⚠️" if abs(d["bias"]) > 8 else "✅"
        out += f"│    预测平 {d['bin']} (中点{d['pred_mid']:.0f}%): {d['n']}场, 实际平局率 {d['actual_rate']:.1f}%, 偏差 {d['bias']:+.1f}% {flag}\n"

    # 3c
    out += "│  3c. 热门过度自信 (>65%胜率):                                │\n"
    if biases["fav_win_rate"] is not None:
        n_fav = len(biases["favorites"])
        flag = "⚠️ 过度自信" if biases["fav_win_rate"] < biases["mean_fav_pct"] - 10 else "✅ 校准良好"
        sample_warn = " *小样本" if n_fav < 5 else ""
        out += f"│    {n_fav}场预测热门, 预测均值 {biases['mean_fav_pct']:.1f}%, 实际胜率 {biases['fav_win_rate']:.1f}%{sample_warn}{'':>20}│\n"
        out += f"│    → {flag}{'':>58}│\n"
        for f in biases["favorites"]:
            won = "✅" if f["fav_won"] else "❌"
            out += f"│      {f['match']}: 热门 {f['fav_pct']:.0f}% {won} ({f['score']}){'':>28}│\n"
    else:
        out += "│    无热门预测 (>65%)                                        │\n"

    # 3d
    out += "│  3d. Delta 校准:                                            │\n"
    out += "│    按实际净胜球:                                            │\n"
    for d in biases["delta_actual"]:
        bar_str = bar(d["accuracy"], 25)
        out += f"│      {d['label']:<12} ({d['n']:>2}场): {d['accuracy']:.0f}% 方向正确 {bar_str}\n"
    out += "│    按预测 Δ:                                                │\n"
    for d in biases["delta_pred"]:
        bar_str = bar(d["accuracy"], 25)
        out += f"│      {d['label']:<12} ({d['n']:>2}场): {d['accuracy']:.0f}% 方向正确 {bar_str}\n"

    out += "└" + "─" * 70 + "┘\n"
    return out


# ========================
# 四、置信度分层
# ========================
def analyze_confidence(rows):
    from collections import defaultdict
    tiers = defaultdict(list)
    for r in rows:
        tiers[r["confidence"]].append(r)

    results = []
    for tier in ["高", "中", "低"]:
        if tier not in tiers:
            continue
        group = tiers[tier]
        n = len(group)
        dir_acc = sum(1 for r in group if r["direction_correct"]) / n * 100
        mean_abs_delta = sum(abs(r["delta"]) for r in group) / n
        avg_max_pct = sum(max(r["win_pct"], r["lose_pct"]) for r in group) / n

        # Tier Brier
        total_se = 0.0
        for r in group:
            if r["outcome"] == "home_win": o = [1.0, 0.0, 0.0]
            elif r["outcome"] == "draw": o = [0.0, 1.0, 0.0]
            else: o = [0.0, 0.0, 1.0]
            p = [r["win_pct"]/100, r["draw_pct"]/100, r["lose_pct"]/100]
            total_se += sum((p[i] - o[i])**2 for i in range(3))
        tier_brier = total_se / n

        results.append({
            "tier": tier, "n": n, "direction_accuracy": round(dir_acc, 1),
            "mean_abs_delta": round(mean_abs_delta, 1),
            "avg_predicted_max_pct": round(avg_max_pct, 1),
            "brier": round(tier_brier, 4),
        })
    return results


def render_confidence(tiers):
    out = "┌" + "─" * 72 + "┐\n"
    out += "│  置信度分层分析 — 验证'高置信→高准确'是否成立               │\n"
    out += "├" + "─" * 8 + "┬" + "─" * 5 + "┬" + "─" * 10 + "┬" + "─" * 10 + "┬" + "─" * 10 + "┬" + "─" * 12 + "┤\n"
    out += "│ 置信度 │ 场次 │ 方向正确率│ 平均Δ绝对值│ 平均最高% │ 分层Brier  │\n"
    out += "├" + "─" * 8 + "┼" + "─" * 5 + "┼" + "─" * 10 + "┼" + "─" * 10 + "┼" + "─" * 10 + "┼" + "─" * 12 + "┤\n"
    for t in tiers:
        out += f"│ {t['tier']:<6} │ {t['n']:>3} │ {t['direction_accuracy']:>7.1f}% │ {t['mean_abs_delta']:>8.1f} │ {t['avg_predicted_max_pct']:>8.1f}% │ {t['brier']:>10.4f} │\n"
    out += "├" + "─" * 8 + "┴" + "─" * 5 + "┴" + "─" * 10 + "┴" + "─" * 10 + "┴" + "─" * 10 + "┴" + "─" * 12 + "┤\n"

    # Check monotonicity
    accs = [t["direction_accuracy"] for t in tiers]
    if len(accs) >= 2 and all(accs[i] >= accs[i+1] for i in range(len(accs)-1)):
        status = "✅ 单调递减: 高置信确实对应高准确"
    elif len(accs) >= 2:
        status = "⚠️ 非单调: 置信度标签与准确率不匹配"
    else:
        status = "—"

    out += f"│ 判定: {status:<63}│\n"
    out += "└" + "─" * 72 + "┘\n"
    return out


# ========================
# 五、总结
# ========================
def render_summary(brier, biases, tiers):
    issues = []

    # Check Brier
    if brier["brier"] > 0.50:
        issues.append(("P0", "Brier偏高", f"总体Brier={brier['brier']:.4f}, 概率校准不足, 需全局调参"))

    # Check draw Brier vs others
    c = brier["components"]
    if c["draw"] > max(c["home"], c["away"]) + 0.05:
        issues.append(("P1", "平局概率最差", f"平局Brier={c['draw']:.4f} 远高于主胜{c['home']:.4f}/客胜{c['away']:.4f}, 平局加成需重新校准"))

    # Check home bias
    if abs(biases["home_bias"]) > 8:
        direction = "低估" if biases["home_bias"] > 0 else "高估"
        issues.append(("P1", f"主场{direction}", f"预测主胜{biases['mean_pred_home']:.0f}%, 实际{biases['actual_home_rate']:.0f}%, 偏差{biases['home_bias']:+.1f}%"))

    # Check favorite overconfidence
    if biases["fav_win_rate"] is not None and biases["mean_fav_pct"] is not None:
        if biases["fav_win_rate"] < biases["mean_fav_pct"] - 15:
            issues.append(("P1", "热门过度自信", f"预测{biases['mean_fav_pct']:.0f}%胜率, 实际{biases['fav_win_rate']:.0f}%, 屠杀模式可能过度放大"))

    # Check confidence tiers
    if len(tiers) >= 2:
        high_acc = tiers[0]["direction_accuracy"]
        low_acc = tiers[-1]["direction_accuracy"]
        if high_acc < low_acc:
            issues.append(("P0", "置信度反向", f"高置信准确{high_acc:.0f}% < 低置信准确{low_acc:.0f}%, 置信度标签失效"))

    issues.sort()

    out = "\n" + "═" * 72 + "\n"
    out += "  总  结  与  建  议\n"
    out += "═" * 72 + "\n"

    if not issues:
        out += "  ✅ 概率校准整体良好, 无需重大调整\n"
    else:
        out += f"  发现 {len(issues)} 个校准问题:\n\n"
        for priority, title, detail in issues:
            icon = "🔴" if priority == "P0" else "🟡"
            out += f"  {icon} [{priority}] {title}\n     {detail}\n\n"

    out += "─" * 72 + "\n"
    out += "  建议操作:\n"
    out += "    1. 持续关注平局Brier, 考虑在calibrator中增加Brier最小化目标\n"
    out += "    2. 热门过度自信可通过增大paradox_shift来对冲\n"
    out += "    3. 每轮赛后重新运行此审计, 追踪校准趋势\n"
    out += "═" * 72 + "\n"
    return out


# ========================
# Main
# ========================
def main():
    print(f"\n{'═' * 72}")
    print(f"  概率校准审计 v1.0 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═' * 72}\n")

    results = load_results()
    rows = build_rows(results)
    print(f"  加载 {len(rows)} 场已赛比赛, 重跑 predict() ...\n")

    # 一
    print("  一、可靠性图")
    reliability = compute_reliability(rows)
    print(render_reliability(reliability))

    # 二
    print("\n  二、Brier Score")
    brier = compute_brier(rows)
    print(render_brier(brier))

    # 三
    print("\n  三、系统性偏差")
    biases = detect_biases(rows)
    print(render_biases(biases))

    # 四
    print("\n  四、置信度分层")
    tiers = analyze_confidence(rows)
    print(render_confidence(tiers))

    # 五
    print(render_summary(brier, biases, tiers))


if __name__ == "__main__":
    main()
