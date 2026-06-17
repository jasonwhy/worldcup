# 信息源汇总与抓取更新任务

> 最后更新：2026-06-16 | 覆盖源：10个

---

## 一、官方数据源

| # | 源 | URL | 数据类型 | 更新频率 | 抓取方式 |
|---|-----|-----|---------|---------|---------|
| 1 | **FIFA官网** | fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026 | 赛程/积分/球队/新闻 | 每场后 | web_search + web_fetch |
| 2 | **FIFA Match Schedule PDF** | digitalhub.fifa.com | 淘汰赛对阵路径 | 一次性 | 已提取到PREDICTION_SYSTEM.md §六 |

## 二、体育媒体源

| # | 源 | URL | 数据类型 | 更新频率 | 抓取方式 |
|---|-----|-----|---------|---------|---------|
| 3 | **ESPN** | espn.com/soccer/worldcup/ | 赛果/分析/Power Rankings/Elo评分/伤病追踪 | 每日 | web_search + web_fetch |
| 4 | **Fox Sports** | foxsports.com/soccer/fifa-world-cup/ | Lalas排名/赔率面板/金靴追踪/独家场外 | 每日 | web_search + web_fetch |
| 5 | **Yahoo Sports** | sports.yahoo.com/soccer/world-cup/ | Power Rankings (Paul Carr)/预测/独家新闻 | 赛前+每轮后 | web_search + web_fetch |
| 6 | **BBC Sport** | bbc.com/sport/football | 比赛报告/英国队深度 | 每日 | web_search |
| 7 | **NBC Sports** | nbcsports.com/soccer | 金靴追踪/赛果 | 每日 | web_search |

## 三、博彩数据源

| # | 源 | URL | 数据类型 | 更新频率 | 抓取方式 |
|---|-----|-----|---------|---------|---------|
| 8 | **bet365** | bet365.com | 48队夺冠赔率/单场盘口 | 实时 | web_search聚合 |
| 9 | **FanDuel** | sportsbook.fanduel.com | 晋级/四强/决赛赔率 (Fox Sports引用) | 每日 | Fox Sports赔率面板间接获取 |
| 10 | **DraftKings** | sportsbook.draftkings.com | 夺冠赔率/金靴赔率 | 每日 | web_search聚合 |

## 三-补充、中国竞彩官方数据

| # | 源 | URL | 数据类型 | 更新频率 | 抓取方式 |
|---|-----|-----|---------|---------|---------|
| 11 | **网易彩票** ⭐ | sports.163.com/caipiao/bet/football | 竞彩官方SP全量+让球盘+多日预告 | 每日 | web_search ✅已确认可用 |
| 12 | **新浪彩票** | lotto.sina.cn | 竞彩官方SP值+详细分析文章 | 每场赛前 | web_search |
| 12 | **wc-2026.com** | wc-2026.com/world-cup-odds/ | 48队实时赔率聚合 (含欧赔/亚盘) | 实时 | web_search |
| 13 | **中彩网** | jc.zhcw.com | 混合过关计算器+API数据 | 实时 | JS渲染(受限) |

## 四-补充、球队动态追踪源 ★新增

| # | 源 | URL | 数据类型 | 更新频率 | 抓取方式 |
|---|-----|-----|---------|---------|---------|
| 14 | **SquadWire** | squadwire.app | AI聚合48队68记者源·伤病·阵容预测·赛前发布会 | 每日 | web_search + web_fetch |
| 15 | **WorldCupWiki** | worldcupwiki.com | 48队伤病清单·伤停状态·复出时间线 | 每日 | web_search |
| 16 | **Action Network** | actionnetwork.com/worldcup | 伤病报告·具体伤种·复出预估日期 | 每日 | web_search |
| 17 | **Ge.Globo** | ge.globo.com | 巴西/葡萄牙语系球队深度报道·发布会·阵容 | 每日 | web_search |
| 18 | **网易体育** | 163.com/dy | 中文球队新闻·赛前发布会·伤病更新 | 每日 | web_search |
| 19 | **新华社** | xinhuanet.com | 中文官方球队动态·权威伤病确认 | 赛前 | web_search |
| 20 | **出奇网** | chuqi.com | 中文专家方案·球队分析·冷门预警 | 每场赛前 | web_search |

> 注: lottery.gov.cn 和 sporttery.cn 被境外IP限制。新浪彩票每日发布竞彩官方SP值分析文章，是最可靠的中国竞彩赔率间接获取渠道。

## 四、数据抓取任务清单

### 每日必做（赛前2小时 + 赛后1小时）

```
□ [赛后] 更新 groups.json 积分榜 (来源: FIFA.com Standings)
□ [赛后] 更新 injuries.json 伤病 (来源: ESPN伤病追踪器)
□ [赛后] 更新 gossip.json 场外事件 (来源: ESPN/Fox/Yahoo新闻线)
□ [赛后] 运行 audit_system.py 验证数据完整性
□ [赛前] 更新 teams.json 赔率字段 (来源: Fox Odds面板)
□ [赛前] 运行 python main.py --today 生成当日预测+投注方案
□ [赛前] 运行 audit_lottery.py 验证投注方案合规
```

### 每轮结束后

```
□ 更新 teams.json 中所有48队的 recent_5 和 recent_10 数据
□ 更新 teams.json 中所有48队的 key_players 追踪
□ 重新校准 betting.py 中的赔率漂移阈值
□ 重新校准 poisson.py 中的 DRAW_BONUS 系数
□ 更新 PREDICTION_SYSTEM.md 中的小组预测
□ 更新 ESPN专家预测参考层 (来源: ESPN Power Rankings)
□ 更新 Fox Sports专家预测参考层 (来源: Lalas Rankings)
```

### 淘汰赛阶段额外任务

```
□ 加载 3.4节淘汰赛对阵路径
□ 新增 disciplinary.json 红黄牌停赛追踪
□ 启用 poisson.py 中淘汰赛模式 (DRAW_BONUS["ko"]=0.8)
□ 启用 penalty_shootout 子模块
```

## 五、数据文件对应关系

| 数据文件 | 写入来源 | 关键字段 |
|---------|---------|---------|
| teams.json | FIFA排名 + Elo + Transfermarkt + bet365/DK | fifa_rank, elo_rating, recent_5/10, odds, odds_history |
| groups.json | FIFA.com Standings | standings各队p/w/d/l/gf/ga/gd |
| injuries.json | ESPN伤病追踪 + Yahoo独家 + 队报 | player, role, status, irreplaceability |
| gossip.json | ESPN/Fox/Yahoo新闻线 + X/Reddit | locker_room, political, player_off_field, date |
| PREDICTION_SYSTEM.md | 全部源综合 | 小组预测/冠军推演/八卦预判 |

## 六、已确认的数据可靠性排序

| 可靠性 | 源 | 原因 |
|--------|-----|------|
| ★★★★★ | FIFA.com | 官方权威, 赛果/积分不可争议 |
| ★★★★★ | bet365/FanDuel/DraftKings | 真金白银, 赔率即是市场共识 |
| ★★★★☆ | ESPN分析数据 (Elo/xG) | 数据驱动, 方法透明 |
| ★★★★☆ | Fox Sports赔率面板 | 引用FanDuel一手数据 |
| ★★★☆☆ | ESPN/Fox/Yahoo专家排名 | 主观但有参考价值 |
| ★★★☆☆ | BBC/NBC比赛报告 | 事实准确, 分析主观 |
| ★★☆☆☆ | Yahoo独家八卦 | 独家但需交叉验证 |

## 七、API/抓取限制

| 源 | 限制 | 解决方案 |
|-----|------|---------|
| FIFA.com | Cookie墙, 直接fetch超时 | web_search替代, 抓取搜索引擎缓存内容 |
| bet365 | 动态加载, JS渲染 | web_search聚合博彩新闻站 |
| ESPN | 部分文章付费墙 | 搜索引擎摘要+公开报道 |
| sporttery.cn | 中国境外IP限制 | 规则已学习, 无需实时拉取 |
| 实时比分API | 需付费 | 目前用搜索引擎弥补 |

## 八、系统命令速查

```bash
# 数据维护
python audit_system.py          # 系统完整性审计
python audit_lottery.py         # 投注方案合规审计
python audit_matches.py         # 所有已赛比赛复盘

# 预测输出
python main.py --today          # 今日8场预测+自动投注方案
python main.py --rank           # 48队总排名
python main.py --group I        # 单组分析
python main.py --gossip IRN     # 球队八卦风控
python main.py FRA-SEN          # 单场完整预测

# 投注方案
python main.py --lottery "FRA-SEN,IRQ-NOR,..."     # 自定义场次
python main.py --lottery "FRA-SEN,..." 200         # 自定义预算
```
