#!/usr/bin/env python3
"""复盘已完成的16场比赛"""
import sys
sys.path.insert(0, '/Users/xiaochen/Documents/2026/worldcup')
from engine import predict

matches = [
    ('MEX-RSA', '2-0'),
    ('KOR-CZE', '2-1'),
    ('CAN-BIH', '1-1'),
    ('USA-PAR', '4-1'),
    ('HAI-SCO', '0-1'),
    ('AUS-TUR', '2-0'),
    ('BRA-MAR', '1-1'),
    ('QAT-SUI', '1-1'),
    ('GER-CUW', '7-1'),
    ('NED-JPN', '2-2'),
    ('CIV-ECU', '1-0'),
    ('SWE-TUN', '5-1'),
    ('ESP-CPV', '0-0'),
    ('BEL-EGY', '1-1'),
    ('KSA-URU', '1-1'),
    ('IRN-NZL', '2-2'),
]

total = len(matches)
dir_correct = 0
score_top1 = 0
score_top3 = 0
cold_hit = 0
cold_total = 0

print(f"{'比赛':<10} {'实际':<6} {'模型胜/平/负':<18} {'方向':<5} {'Top比分':<6} {'Top3':<28} {'Δ':>6} {'冷门':<6} {'判向':>4} {'比分':>4}")
print('=' * 115)

for mid, actual in matches:
    p = predict(mid)
    r = p['prediction']
    w, d, l = r['win_pct'], r['draw_pct'], r['lose_pct']

    # Model direction
    if w > d and w > l:
        model_dir = 'HOME'
    elif l > w and l > d:
        model_dir = 'AWAY'
    else:
        model_dir = 'DRAW'

    h_name = p['home']['name'][:6]
    a_name = p['away']['name'][:6]

    # Actual direction
    ah, aa = map(int, actual.split('-'))
    if ah > aa:
        act_dir = 'HOME'
    elif aa > ah:
        act_dir = 'AWAY'
    else:
        act_dir = 'DRAW'

    dir_ok = (model_dir == act_dir)
    if dir_ok:
        dir_correct += 1

    top1 = r['top_scores'][0]['score']
    top3 = [s['score'] for s in r['top_scores'][:3]]
    s1_ok = (top1 == actual)
    s3_ok = (actual in top3)
    if s1_ok:
        score_top1 += 1
    if s3_ok:
        score_top3 += 1

    alert = r['cold_alert'][:5].strip()
    is_draw_or_upset = (act_dir == 'DRAW' and model_dir != 'DRAW') or (act_dir != model_dir and model_dir != 'DRAW')
    has_alert = '高' in alert or '中' in alert
    if has_alert:
        cold_total += 1
        if is_draw_or_upset:
            cold_hit += 1

    top3_str = ', '.join(top3)
    delta_str = f"{p['delta']:+.1f}"
    print(f"{h_name}-{a_name:<4} {actual:<6} {w:.0f}%/{d:.0f}%/{l:.0f}% {model_dir:<5} {top1:<6} {top3_str:<28} {delta_str:>6} {alert:<6} {'✅' if dir_ok else '❌':>4} {'✅' if s1_ok else '❌':>4}")

print('=' * 115)
print(f"\n方向正确率: {dir_correct}/{total} = {dir_correct/total*100:.1f}%")
print(f"Top1比分命中: {score_top1}/{total} = {score_top1/total*100:.1f}%")
print(f"Top3比分命中: {score_top3}/{total} = {score_top3/total*100:.1f}%")
if cold_total > 0:
    print(f"冷门预警命中: {cold_hit}/{cold_total} (冷门/平局被预警覆盖)")
print(f"\n本届首轮异常: 16场中{sum(1 for _,a in matches if a.endswith('1') or a in ['0-0','2-2'])}场平局 = 50% (历史均值~25%)")
