# 全球市场金融资讯日报 + 持仓信号看板（数据层）

每日自动采集**全球核心成分股 / 蓝筹股 / 科技股**走势与要闻，覆盖 **雅虎财经、东方财富、Investing.com、TradingView** 等公开渠道，
**多源交叉核实**后提炼 **Top 5** 并按时间排序，生成可视化日报网页。

同时采集**美债收益率（美国财政部官方）**与 **VIX（Cboe 官方）**，并维护**持仓与基准指数的日 K 线历史**，
为后续"市场情绪 + 美债 + 持仓买卖信号"看板及历史回测提供数据基础。

## 功能

- 📈 8 大指数快照（上证 / 深证 / 创业板 / 恒生 / 国企 / 纳指100 / 标普500 / 道指）
- 🏢 57 只核心股票（美股科技+蓝筹 25、港股 12、A股 20），含价格、涨跌幅、成交量、市值、PE
- 📰 多源新闻采集：东方财富要闻 + 7x24 快讯、Yahoo Finance、Investing.com RSS
- ✅ 信息核实：价格/涨跌幅合理性检查 + 多源一致性校验 + 新闻时效校验；每条附 `verified` 状态
- 🏆 每日提炼 Top 5（按关联标的、宏观相关性、时效打分），按时间排序
- 🇺🇸 宏观快照：美债 2/5/10/30 年期收益率（美国财政部官方）+ 日/周变化 + 10Y−2Y 利差；VIX（Cboe 官方）+ 日变化
- 🎯 持仓信号：NVDA/GOOGL/CRCL/SNDK 各 8 个子指标（趋势/均线排列/MACD/RSI/位置/量能/相对强度/波动率）加权评分，叠加宏观风险（美债 10Y 主导 + VIX）后给出 买入/持有/观望/减仓 信号，每个子指标可展开查看
- 🔬 回测验证：滚动样本外逐日信号（无未来函数）+ 交易成本，输出 总收益/年化/Sharpe/最大回撤/命中率/分指标归因/分行情区间/成本敏感性
- 🕘 历史数据：持仓与基准（NVDA/GOOGL/CRCL/SNDK/SPX/NDX）日 K 线 + 美债/VIX 全历史，供指标计算与回测
- 🎨 深/浅双主题，纯静态前端，零依赖

## 持仓标的说明（重要）

| 你的说法 | 看板跟踪代码 | 说明 |
| --- | --- | --- |
| 英伟达 | NVDA | 东财 105.NVDA |
| 谷歌 | GOOGL | 东财 105.GOOGL |
| Circle | **CRCL** | **Circle Internet Group**（稳定币 USDC 发行方，NYSE: CRCL）；东财 106.CRCL。注意：`CIRC` 是另一家公司 Circle8 Group（仙股），勿混淆 |
| 闪迪 | SNDK | 东财 105.SNDK，2025-02 从西部数据分拆上市 |

## 数据源说明

| 渠道 | 用途 | 境内直连 |
| --- | --- | --- |
| 东方财富 | 行情(主) + 新闻 + 7x24 快讯 + **日 K 线历史** | ✅ 可用 |
| 雅虎财经 | 行情(次) + 新闻 | ❌ 常被拦截，自动降级 |
| Investing.com | 新闻 RSS | ❌ 常被拦截，自动降级 |
| TradingView | 行情(次，交叉验证) | ❌ 常被拦截，自动降级 |
| 腾讯证券 / 新浪财经 | 行情（交叉核实，稳定） | ✅ 可用 |
| **美国财政部** | 美债收益率（官方 XML，2/5/10/30Y 等） | ⚠️ 视网络，海外/部分网络可用 |
| **Cboe** | VIX 日频全历史（官方 CSV，1990 至今） | ⚠️ 视网络，海外/部分网络可用 |

被拦截的源会**优雅降级**：主源东方财富照常工作，报告中标注各源状态。
在海外网络（或 GitHub Actions，见 `.github/workflows/daily.yml`）下四源可同时生效，交叉验证更充分。

> 东财对部分网络（如海外）会拒绝 Python 标准库的 HTTP/1.1 请求；K 线采集已内置 curl 自动回退，
> 任一路径失败只影响对应标的并记录状态，不中断整体。

## 快速开始

```bash
# 1) 回填历史数据（首次必做；之后每日由 run_daily 增量更新）
python3 scripts/backfill_history.py --from-year 2015

# 2) 采集（联网，含行情/新闻/宏观/K线更新）
python3 run_daily.py

# 3) 本地预览
bash scripts/serve.sh          # http://localhost:8000/web/  （日报）
                               # http://localhost:8000/web/dashboard.html（信号看板）

# 4)（可选）重新运行回测
python3 scripts/run_backtest.py
```

> 纯 Python 标准库，无需 pip 安装（仅东财 K 线回退路径用到系统自带 curl）。

## 每日自动运行

### macOS（launchd）
```bash
bash scripts/setup_launchd.sh 17 30   # 每天 17:30（A股/港股收盘后）采集
```
日志：`data/daily.log`；卸载：`launchctl unload ~/Library/LaunchAgents/com.weijin.finance-news-daily.plist`

### 任何系统（cron）
```bash
30 17 * * * cd "/Users/weijin/Documents/ChatGPT/codex project1 finance news website" && python3 run_daily.py >> data/daily.log 2>&1
```

### GitHub Actions（可选，海外网络四源全开）
把 `.github/workflows/daily.yml` 推送到 GitHub 仓库即每天自动采集并提交 `data/`。

## 项目结构

```
config/watchlist.json      # 观察清单（指数 + 各市场核心股，含 CRCL/SNDK）
config/history.json        # 历史数据配置（持仓 + 基准的 K 线起止/代码）
collector/                 # 采集：行情/新闻/宏观/K线 编排 + 各源适配器
  sources/eastmoney.py     #   东方财富（主）
  sources/yahoo.py         #   雅虎财经
  sources/investing.py     #   Investing.com
  sources/tradingview.py   #   TradingView
  sources/tencent.py       #   腾讯证券
  sources/sina.py          #   新浪财经
  macro.py                 #   美债收益率（美国财政部）+ VIX（Cboe）
  klines.py                #   日 K 线历史（东财 kline + curl 回退）
signals/                   # 信号计算：指标 -> 评分 -> 宏观叠加 -> 信号
  indicators.py             #   技术指标纯函数（SMA/EMA/RSI/MACD/ATR/布林/OBV）
  scoring.py                #   子指标打分 + 综合评分 + 宏观风险叠加
  engine.py                 #   编排：加载历史 -> 输出持仓信号
verify/verifier.py         # 核实：合理性 + 多源一致性
digest/digester.py         # 提炼：Top5 打分 + 按时间排序 + 涨跌榜
run_daily.py               # 主入口（行情/新闻/宏观/K线 一体）
scripts/backfill_history.py# 历史回填（美债按年 + VIX 全量 + 日K）
scripts/run_backtest.py    # 运行回测 -> data/backtest/
backtest/                  # 回测引擎（信号序列/模拟/指标/归因/区间）
scripts/                   # 运行/预览/定时任务脚本
data/daily/YYYY-MM-DD.json # 每日报告（含 macro 摘要）
data/latest.json           # 最新报告（前端读取）
data/history/macro/        # 美债 treasury.json、VIX vix.json（全历史）
data/history/klines/       # 每标的一个 JSON（NVDA/GOOGL/CRCL/SNDK/SPX/NDX）
data/signals/latest.json    # 最新持仓信号（前端看板后续读取）
data/backtest/latest.json   # 回测结果（策略 vs 买入持有 + 归因）
web/                       # 前端（design-tokens + 模板）
  index.html                #   资讯日报页（指数/行情/Top5/成交额）
  dashboard.html            #   持仓信号看板（宏观+美债+持仓+回测准确率）
  css/dashboard.css         #   看板页样式
  js/dashboard.js           #   看板页渲染（读 data/signals、data/backtest、data/history/macro）
design-tokens.md           # 设计规范（CSS 变量唯一事实来源）
```

## 核实规则（verify/verifier.py）

- 行情：价格 > 0；单日涨跌幅 ≤ 40%；多源价格偏差 ≤ 1%、涨跌幅偏差 ≤ 1pp 视为一致
- 新闻：标题 ≥ 8 字；时间可解析且不严重超前；超过 48h 标记"非当日"
- 每条输出 `verified` 与 `verification_notes`，前端以 ✓/⚠ 呈现

## 免责声明

数据来自公开渠道，仅供个人研究参考，不构成投资建议。采集频率请遵守各网站服务条款。
