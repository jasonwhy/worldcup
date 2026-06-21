# CRITICAL RULES — Highest Priority

## Betting Plan Archive (方案留底)
- `data/bet_plans_archive.json` stores ALL generated plans permanently
- **NEVER delete or modify archived plans** — only append new dates or add change annotations
- Each dashboard regeneration must compare new plan vs archive, show diff (📝), then save
- Expired dates show "⏰ 已截止投注" banner but remain visible
- This is the #1 non-negotiable rule

## Prediction Accuracy
- `fetch_live.py` must call `predict()` engine to determine ✅/❌ — never hardcode
- Current direction rate: 25/33 = 76% (P0: DRAW_BONUS 1.6/1.3 + P2: team draw factor)
- calibrator writes to `data/calibration.json` — does NOT mutate global variables

## Data Sources (priority order)
1. nowscore.com (竞彩 SP/RQSPF/进球/半全/比分)
2. FIFA.com (赛程权威)
3. AP/ESPN/Sky (赛果验证)
4. 网易彩票 (SP备用)
5. 懂球帝 (球员/球队数据)