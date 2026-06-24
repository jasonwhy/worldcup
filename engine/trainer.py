#!/usr/bin/env python3
"""
模型训练器 v1.0
用48场已赛数据网格搜索最优参数组合
目标: 最大化方向正确率 + 比分Top3命中率
"""
import json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from engine.predictor import predict

DATA = Path(__file__).parent.parent / "data"

def load(n):
    with open(DATA / n) as f: return json.load(f)

def evaluate_model(params: dict) -> dict:
    """
    用当前参数重跑所有已赛，计算评分
    params: {baseline_xg, draw_bonus_g1, draw_bonus_g2, dispersion, dc_rho}
    """
    # 临时修改参数
    import engine.poisson as poisson
    orig_xg = poisson.BASELINE_XG
    orig_db = dict(poisson.DRAW_BONUS)

    poisson.BASELINE_XG = params.get("baseline_xg", 2.0)
    if "draw_bonus_g1" in params:
        poisson.DRAW_BONUS["group_1"] = params["draw_bonus_g1"]
    if "draw_bonus_g2" in params:
        poisson.DRAW_BONUS["group_2"] = params["draw_bonus_g2"]

    results = load("results.json")
    direction_correct = 0
    total = 0
    score_top3 = 0
    goal_mae = 0.0

    for m in results["matches"]:
        mid = f"{m['home']}-{m['away']}"
        try:
            p = predict(mid)
            if "error" in p: continue
            r = p["prediction"]
            total += 1

            # 方向
            ah, aa = map(int, m["score"].split("-"))
            w, d, l = r["win_pct"], r["draw_pct"], r["lose_pct"]
            if ah > aa: actual_dir = "home"
            elif aa > ah: actual_dir = "away"
            else: actual_dir = "draw"
            if w > d and w > l: pred_dir = "home"
            elif l > w and l > d: pred_dir = "away"
            else: pred_dir = "draw"
            if pred_dir == actual_dir: direction_correct += 1

            # 比分Top3
            actual_score = m["score"]
            for s in r["top_scores"][:3]:
                if s["score"] == actual_score: score_top3 += 1; break

            # 进球误差
            goal_mae += abs(ah + aa - r["total_xg"])
        except: pass

    # 恢复参数
    poisson.BASELINE_XG = orig_xg
    poisson.DRAW_BONUS.update(orig_db)
    # Restore from calibration file
    calib = DATA / "calibration.json"
    if calib.exists():
        c = json.load(open(calib))
        if "baseline_xg" in c: poisson.BASELINE_XG = c["baseline_xg"]
        if "draw_bonus" in c: poisson.DRAW_BONUS.update(c["draw_bonus"])

    return {
        "n": total,
        "direction": direction_correct / max(1, total),
        "score_top3": score_top3 / max(1, total),
        "goal_mae": goal_mae / max(1, total),
        "score": (direction_correct / max(1, total)) * 0.6 + (score_top3 / max(1, total)) * 0.3 + max(0, 1 - goal_mae / max(1, total) / 5) * 0.1,
    }


def grid_search():
    """网格搜索最优参数"""
    print("=" * 60)
    print("  模型训练器 v1.0 — 48场数据网格搜索")
    print("=" * 60)

    # 搜索空间
    baseline_xg_range = [1.6, 1.8, 2.0, 2.2, 2.4]
    draw_g1_range = [1.2, 1.4, 1.6, 1.8, 2.0, 2.2]
    draw_g2_range = [1.0, 1.2, 1.4, 1.6, 1.8]

    best = None
    best_score = 0
    total_combos = len(baseline_xg_range) * len(draw_g1_range) * len(draw_g2_range)
    i = 0

    for xg in baseline_xg_range:
        for g1 in draw_g1_range:
            for g2 in draw_g2_range:
                i += 1
                params = {"baseline_xg": xg, "draw_bonus_g1": g1, "draw_bonus_g2": g2}
                result = evaluate_model(params)
                if result["score"] > best_score:
                    best_score = result["score"]
                    best = {**params, **result}

                if i % 30 == 0:
                    print(f"  进度: {i}/{total_combos} ... 当前最优: {best['direction']*100:.0f}%方向 {best_score:.3f}分")

    print(f"\n{'='*60}")
    print(f"🏆 最优参数 (评分={best_score:.3f}):")
    print(f"  BASELINE_XG: {best['baseline_xg']}")
    print(f"  DRAW_BONUS group_1: {best['draw_bonus_g1']}")
    print(f"  DRAW_BONUS group_2: {best['draw_bonus_g2']}")
    print(f"  方向正确率: {best['direction']*100:.0f}% ({int(best['direction']*best['n'])}/{best['n']})")
    print(f"  比分Top3: {best['score_top3']*100:.0f}%")
    print(f"  进球MAE: {best['goal_mae']:.2f}")

    # 写入校准文件
    calib_data = {
        "baseline_xg": best["baseline_xg"],
        "draw_bonus": {"group_1": best["draw_bonus_g1"], "group_2": best["draw_bonus_g2"]},
        "thresholds": {"conservative_min_delta": 8},
        "direction_rate": f"{best['direction']*100:.0f}%",
        "trained_at": f"{best['n']} matches",
    }
    json.dump(calib_data, open(DATA / "calibration.json", "w"), indent=2)
    print(f"\n✅ calibration.json 已更新")
    return best


def evaluate_current():
    """评估当前参数"""
    print("📊 当前模型评估...")
    r = evaluate_model({})
    print(f"  方向: {r['direction']*100:.0f}% | 比分Top3: {r['score_top3']*100:.0f}% | 进球MAE: {r['goal_mae']:.2f}")
    return r


if __name__ == "__main__":
    evaluate_current()
    print()
    best = grid_search()
