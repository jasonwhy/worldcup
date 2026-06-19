"""
后验校准器 v1.0
===============
每轮赛后自动运行, 对比实际vs预测, 修正系统性偏差。

运行: calibrator.calibrate()
- 重跑所有已赛预测
- 检测进球偏差/平局偏差/方向偏差
- 自动调整 BASELINE_XG / DRAW_BONUS / 阈值
- 输出校准报告
"""
import json, math
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"

def load(n):
    with open(DATA / n) as f:
        return json.load(f)

def calibrate(verbose=True):
    """赛后自动校准, 返回调整建议"""
    results = load("results.json")
    if len(results["matches"]) < 10:
        return {"status": "insufficient", "msg": "至少需要10场赛果"}

    from .predictor import predict

    # == 收集对比数据 ==
    actual_goals = 0
    pred_goals = 0
    actual_draws = 0
    pred_draws_as_top = 0
    direction_correct = 0
    direction_total = 0
    score_top1_hits = 0
    score_top3_hits = 0
    n = 0

    for m in results["matches"]:
        mid = f"{m['home']}-{m['away']}"
        try:
            p = predict(mid)
            if "error" in p: continue
            r = p["prediction"]
            n += 1

            # 进球对比
            ah, aa = map(int, m["score"].split("-"))
            actual_goals += ah + aa
            ph, pa = map(int, r["top_scores"][0]["score"].split("-"))
            pred_goals += ph + pa

            # 平局对比
            actual_draw = (ah == aa)
            pred_top_draw = (r["top_scores"][0]["score"].split("-")[0] ==
                             r["top_scores"][0]["score"].split("-")[1])
            if actual_draw:
                actual_draws += 1

            # 方向对比
            actual_dir = "home" if ah > aa else ("away" if aa > ah else "draw")
            pred_dir = "home" if r["win_pct"] > r["lose_pct"] else ("away" if r["lose_pct"] > r["win_pct"] else "draw")
            if actual_dir == pred_dir:
                direction_correct += 1
            direction_total += 1

            # 比分命中
            if m["score"] == r["top_scores"][0]["score"]:
                score_top1_hits += 1
            if m["score"] in [s["score"] for s in r["top_scores"][:3]]:
                score_top3_hits += 1

        except Exception as e:
            pass

    if n == 0:
        return {"status": "error", "msg": "无有效对比数据"}

    adjustments = []

    # 1. 进球偏差: 预测偏低>25% → 上调BASELINE_XG
    goal_ratio = actual_goals / max(1, pred_goals)
    if goal_ratio > 1.20:
        factor = min(1.20, goal_ratio * 0.85 + 0.15)  # 保守上调
        adjustments.append({
            "param": "BASELINE_XG",
            "old": 1.35,
            "new": round(1.35 * factor, 2),
            "reason": f"进球偏低{goal_ratio-1:+.0%}, 上调xG基线"
        })
    elif goal_ratio < 0.80:
        factor = max(0.85, goal_ratio)
        adjustments.append({
            "param": "BASELINE_XG",
            "old": 1.35,
            "new": round(1.35 * factor, 2),
            "reason": f"进球偏高{goal_ratio-1:+.0%}, 下调xG基线"
        })

    # 2. 平局偏差: 实际平局率超过预测→上调group_1 DRAW_BONUS
    pred_draw_rate = sum(1 for m in results["matches"]
                         if m["prediction_correct"] == "✅" and
                         m["score"].split("-")[0] == m["score"].split("-")[1]) / max(1, len(results["matches"]))
    actual_draw_rate = actual_draws / n
    if actual_draw_rate > 0.30 and pred_draw_rate < actual_draw_rate - 0.05:
        from .poisson import DRAW_BONUS
        old = DRAW_BONUS["group_1"]
        DRAW_BONUS["group_1"] = round(old * 1.10, 2)
        DRAW_BONUS["group_2"] = round(DRAW_BONUS["group_2"] * 1.05, 2)
        adjustments.append({
            "param": "DRAW_BONUS.group_1",
            "old": old,
            "new": DRAW_BONUS["group_1"],
            "reason": f"平局率偏高{actual_draw_rate:.0%} vs 预测{pred_draw_rate:.0%}"
        })

    # 3. 方向偏差: 持续跌破70%→降低保守阈值 (仅当方向样本>=20)
    dir_acc = direction_correct / max(1, direction_total)
    if dir_acc < 0.70 and direction_total >= 20:
        from .lottery import THRESHOLD
        old_t = THRESHOLD["conservative_min_delta"]
        THRESHOLD["conservative_min_delta"] = max(8, old_t - 1)
        adjustments.append({
            "param": "conservative_min_delta",
            "old": old_t,
            "new": THRESHOLD["conservative_min_delta"],
            "reason": f"方向准确率{dir_acc:.0%}偏低, 微调门槛"
        })

    # 输出报告
    report = {
        "status": "done",
        "matches_analyzed": n,
        "metrics": {
            "goal_ratio": round(goal_ratio, 2),
            "actual_goals_per_match": round(actual_goals / n, 1),
            "pred_goals_per_match": round(pred_goals / n, 1),
            "actual_draw_rate": f"{actual_draw_rate:.0%}",
            "direction_accuracy": f"{dir_acc:.0%}",
            "score_top1_rate": f"{score_top1_hits/n:.0%}",
            "score_top3_rate": f"{score_top3_hits/n:.0%}",
        },
        "adjustments": adjustments
    }

    if verbose:
        print("=" * 60)
        print(f"  后验校准器 v1.0 ({n}场已赛)")
        print("=" * 60)
        print(f"  进球比: 实际{actual_goals/n:.1f}/场 vs 预测{pred_goals/n:.1f}/场 ({goal_ratio:+.0%})")
        print(f"  平局率: 实际{actual_draw_rate:.0%}")
        print(f"  方向: {dir_acc:.0%}")
        print(f"  比分Top3: {score_top3_hits/n:.0%}")
        if adjustments:
            print(f"\n  🔧 {len(adjustments)}项调整:")
            for adj in adjustments:
                print(f"    {adj['param']}: {adj['old']} → {adj['new']} ({adj['reason']})")
        else:
            print(f"  ✅ 无需调整, 模型参数合理")
        print("=" * 60)

    return report


if __name__ == "__main__":
    calibrate(verbose=True)
