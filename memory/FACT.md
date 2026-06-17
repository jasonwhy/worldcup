# 2026 World Cup Prediction System — Architecture Decisions

## Data Sync Architecture (v4.3)
- **results.json**: Single source of truth for match results. dashboard.py reads dynamically, no hardcoded lists.
- **news.json**: Centralized news store. All 7 dashboard panels read from JSON files.
- **injuries.json**: 28 entries across 11 teams. `return_date` drives auto-clean.
- **gossip.json**: 18 teams tracked. Uses `original_score` field to prevent double-decay.

## Real-Time Update (v4.3)
- **auto_refresh()**: Runs before every dashboard generation — applies gossip time decay (14-day half-life, e^(-0.05*days)) based on `original_score` not current score; cleans injuries with passed return_date.
- **--watch mode**: File watcher monitors data/*.json every 2 seconds. On change, auto-regenerates dashboard.html.
- **--serve + --watch**: Combined mode — HTTP server + file watcher for live development.
- Browser auto-refresh: 60 seconds (was 5 min).

## Key Design Rules
1. Gossip decay MUST use `original_score` field, not current score, to prevent repeated decay.
2. All JSON files are source of truth — dashboard.py has zero hardcoded data.
3. `audit_sync.py` validates cross-file consistency (results ↔ groups, JSON ↔ dashboard.py).
4. `fetch_updates.py` is the manual update helper; auto_refresh() handles automated decay/clean.

## Media Sources
- 18 sources tracked in sources.json (16 active, 1 stale, 1 blocked)
- Action Network: stale 5 days (injury data)
- 竞彩网 (sporttery.cn): blocked by WAF
- 网易彩票 (sports.163.com/caipiao): primary SP source
