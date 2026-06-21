# 2026世界杯预测·竞彩投注系统 规则总纲

## 核心原则（优先执行）

### 1. 赛果录入铁律
- **禁止 `--force` 跳过安全锁**：双源确认 FT（>95分钟 + API验证）+ 至少两个独立源交叉验证
- **FIFA 官网为首要赛程源**：`fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures`
- **赛后必须双重核验**：AP News + ESPN/Fox/Sky 中任选其一
- **半场比分 ≠ 全场比分**：必须检查分钟标记（如 45+3' 是半场非终场）
- **录入前确认时区**：所有时间以北京时间为准，注意 US EDT/PDT 换算

### 2. 预测准确性铁律
- **`fetch_live.py` 的 `finalize_match()` 必须调用 `predict()` 跑模型验证**，严禁硬编码 ✅/❌
- **`results.json` 的 `prediction_correct` 字段必须由模型对比实际赛果计算**
- **方向率** = 模型预测方向（主胜/平局/客胜）与比赛实际方向一致的比例
- **实时方向率**：25/33 = **76%**（截至 2026-06-21，P0+P2修复后）

### 3. 方案留底铁律 ⚠️ 最高优先级
- **`data/bet_plans_archive.json`**：首次生成后永久存档，永不可删除
- **每次重生成必须对比差异**：变更标注 📝 横幅（时间戳 + EV变化 + 调整项数）
- **已截止日期方案永久保留**：显示"⏰ 已截止投注"，不得移除Tab
- **HOT 标签**：推荐度最高的日期自动标注 🔥
- **方案一经生成即锁定**：后续数据更新导致方案变化时，标注变更但不删除旧内容
- **赛后复盘**：已截止日期在方案顶部展示预测 vs 实际赛果对比

### 4. 数据源优先级
| 优先级 | 源 | 用途 |
|--------|-----|------|
| 1 | nowscore.com (捷报比分) | 竞彩官方 SP/RQSPF/进球数/半全场/比分/单关标记 |
| 2 | FIFA.com | 赛程权威源 |
| 3 | AP News/ESPN/Sky Sports | 赛果交叉验证 |
| 4 | 网易彩票 sporttery.cn | SP 赔率（备用） |
| 5 | 懂球帝 dongqiudi.com | 球员/球队统计数据 |
| 6 | Polymarket/Oddschecker/Fox Sports | 参考概率（不整合） |

---

## 系统架构

```
数据层:  teams.json(48队) | sp.json(29场) | results.json(33场)
         groups.json(12组) | dongqiudi_stats.json(48队×9维)
         gossip.json(26队) | injuries.json(40条) | news.json(100条)
         bet_plans_archive.json(方案留底) | nowscore_odds.json(竞彩全玩法)

引擎层:
  hard_data.py    — 基础实力+状态+动量+轮次+伤病+防守韧性+进攻转化
  betting.py      — 赔率结构+漂移
  gossip.py       — 更衣室+政治+衰减 e^(-0.05×days)
  poisson.py      — 泊松矩阵 v2.3 (BASELINE_XG=1.35, 校准器→1.62)
  predictor.py    — 三层聚合(硬50%+外30%+八20%) + 动态SP先验(8-30%)
  calibrator.py   — 赛后自动校准
  lottery.py      — 购彩方案 v4.0 (正EV+四级池+200元预算)
  advanced_stats.py — 懂球帝数据(未来比赛启用)
  
因子: P0: 防守韧性+进攻转化+SP先验+屠杀+Delta感知平局+八卦减半+悖论削减
      P1: xG代理(30%)+风格相克+比分方向对齐
      P2: 球员可用性+体能耗损

输出层:
  dashboard.py    — 六大面板 HTML
  audit_v2.py     — 四层审计(A数据/B预测/C前瞻/D信息)
  audit_calibration.py — 概率校准审计(Brier/可靠性图/偏差检测)
  fetch_live.py   — 实时比分+完赛判定(双重安全锁)
  fetch_updates.py — 八卦衰减+伤病清理+源检查
  fetch_sp.py     — 网易SP抓取(需 Playwright .venv)
```

---

## 运行规则

### 日常更新流程
```bash
python3 fetch_updates.py --apply    # 八卦衰减 + 伤病清理 + 审计 + dashboard
python3 fetch_live.py               # 检查进行中比赛
```
完成后必须 `cp dashboard.html index.html && git add -f index.html && git commit && git push`

### SP 更新
```bash
.venv/bin/python fetch_sp.py        # 网易 SP 抓取
# 或手动从 nowscore 抓取竞彩全玩法
```

### 赛后处理
```bash
# 双源确认 FT 后:
python3 fetch_live.py --final MATCH_ID HOME_GOALS AWAY_GOALS
# 禁止 --force 除非双源确认完毕
```

### 审计
```bash
python3 audit_v2.py                 # 四层综合审计
python3 audit_calibration.py        # 概率校准审计
```

---

## 引擎关键参数

| 参数 | 值 | 说明 |
|------|-----|------|
| DRAW_BONUS.group_1 | 2.0 | 首轮平局加成（校准器→2.2） |
| DRAW_BONUS.group_2 | 1.6 | 次轮 |
| BASELINE_XG | 1.35 | 进球基线（校准器→1.62） |
| SP 先验权重 | 8-30% | 动态，偏差大→权重大 |
| 投注截止 | 开球前 1 分钟 | 竞彩实际规则 |
| 预算 | 200 元 | 四级池分配 |
| 校准器 | 每轮赛后自动运行 | 调整 BASELINE_XG/DRAW_BONUS/门槛 |

---

## 已知问题

- 模型系统性高估平局概率（vs Polymarket 差 10-21pp）
- 易受首轮赛果过度影响（如 NED-SWE 错判）
- Action Network + WorldCupWiki 过期源需手动更新
- SCO vs SC 队名不统一（已修复为 SCO）
- GitHub Pages 国内网络不可达（需外网）

---

## 禁止事项

- ❌ **修改或删除 `bet_plans_archive.json` 中已存档的任何方案（最高优先级）**
- ❌ `fetch_live.py --force` 绕过双源确认
- ❌ 硬编码 `prediction_correct` 字段
- ❌ 删除已截止日期的投注 Tab（保持永久可见）
- ❌ 用赛后校准过的模型回溯赛前预测准确性
- ❌ 单源确认 FT 即写入赛果（至少双源）
- ❌ 用 `dashboard.py` 重生成时覆盖方案留底（必须先比较差异再更新）
