#!/bin/bash
# 世界杯数据自动更新脚本
# 用法: ./auto_update.sh 或 crontab -e 添加定时任务

cd "$(dirname "$0")"

echo "[$(date '+%H:%M:%S')] 开始自动更新..."

# 1. 抓取最新比分
python3 fetch_live.py 2>&1 | grep -E "✅|🏁|进行中|无进行中" || true

# 2. 八卦衰减+伤病清理
python3 fetch_updates.py --apply 2>&1 | grep -E "衰减|清理|完成" || true

# 3. 更新draw_factors
python3 -c "
import json
results = json.load(open('data/results.json'))
team_stats = {}
for m in results['matches']:
    h, a = m['home'], m['away']
    hg, ag = map(int, m['score'].split('-'))
    for tid, gf, ga in [(h, hg, ag), (a, ag, hg)]:
        if tid not in team_stats: team_stats[tid] = {'p': 0, 'd': 0}
        team_stats[tid]['p'] += 1
        if gf == ga: team_stats[tid]['d'] += 1
GLOBAL_RATE = 0.30; PRIOR = 3
draw_factors = {}
for tid, s in team_stats.items():
    smoothed = (s['d'] + PRIOR * GLOBAL_RATE) / (s['p'] + PRIOR)
    draw_factors[tid] = round(smoothed / GLOBAL_RATE, 2)
json.dump(draw_factors, open('data/draw_factors.json', 'w'), indent=2)
" 2>/dev/null

# 4. 重新生成dashboard
python3 dashboard.py > /dev/null 2>&1

# 5. 部署到GitHub Pages
cp dashboard.html index.html
git add -f index.html data/*.json 2>/dev/null
if ! git diff --cached --quiet; then
    git commit -m "Auto-update: $(date '+%m/%d %H:%M') refresh" > /dev/null 2>&1
    git push 2>&1 | grep -E "main|error" || true
fi

echo "[$(date '+%H:%M:%S')] 更新完成"
