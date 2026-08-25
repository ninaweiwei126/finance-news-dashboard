# 全球市场金融资讯日报

每日自动采集**全球核心成分股 / 蓝筹股 / 科技股**走势与要闻，覆盖 **雅虎财经、东方财富、Investing.com、TradingView** 等公开渠道，
**多源交叉核实**后提炼 **Top 5** 并按时间排序，生成可视化日报网页。

## 功能

- 📈 8 大指数快照（上证 / 深证 / 创业板 / 恒生 / 国企 / 纳指100 / 标普500 / 道指）
- 💰 A股成交额追踪：沪市 / 深市 / 创业板 / 两市合计，分**上午 / 下午 / 全天**三段，每日两次更新（11:35、15:05）
- 🏢 55 只核心股票（美股科技+蓝筹 23、港股 12、A股 20），含价格、涨跌幅、成交量、市值、PE
- 📰 多源新闻采集：东方财富要闻 + 7x24 快讯、Yahoo Finance、Investing.com RSS
- ✅ 信息核实：价格/涨跌幅合理性检查 + 多源一致性校验 + 新闻时效校验；每条附 `verified` 状态
- 🏆 每日提炼 Top 5（按关联标的、宏观相关性、时效打分），按时间排序
- 🎨 深/浅双主题，纯静态前端，零依赖

## 数据源说明

| 渠道 | 用途 | 境内直连 |
| --- | --- | --- |
| 腾讯证券 | 行情(主，单请求全量) | ✅ 可用 |
| 新浪财经 | 行情(交叉核实) | ✅ 可用 |
| 东方财富 | 行情(交叉核实) + 要闻 + 7x24 快讯 | ✅ 可用 |
| 雅虎财经 | 行情(次) + 新闻 | ❌ 常被拦截，自动降级 |
| Investing.com | 新闻 RSS | ❌ 常被拦截，自动降级 |
| TradingView | 行情(次，交叉验证) | ❌ 常被拦截，自动降级 |

境内网络下**腾讯 + 新浪 + 东方财富**三源交叉核实行情（多源偏差 ≤ 1% 才算通过），新闻与快讯以东方财富为主。
被拦截的源会**优雅降级**，报告中标注各源状态；在海外网络（或 GitHub Actions，见 `.github/workflows/daily.yml`）下 Yahoo/Investing/TradingView 也会自动生效。

## 快速开始

```bash
# 1) 采集（联网）
python3 run_daily.py

# 2) 本地预览
bash scripts/serve.sh          # http://localhost:8000/web/
```

> 纯 Python 标准库，无需 pip 安装。

## 每日自动运行

### macOS（launchd）
```bash
bash scripts/setup_launchd.sh 17 30          # 每天 17:30（A股/港股收盘后）采集
bash scripts/setup_volume_launchd.sh         # 成交额追踪：每天 11:35（上午）与 15:05（全天）各一次
```
日志：`data/daily.log`、`data/volume.log`；卸载对应 plist：
`launchctl unload ~/Library/LaunchAgents/com.weijin.finance-news-daily.plist`
`launchctl unload ~/Library/LaunchAgents/com.weijin.finance-volume-snapshot.plist`

### 任何系统（cron）
```bash
30 17 * * * cd "/Users/weijin/Documents/ChatGPT/codex project1 finance news website" && python3 run_daily.py >> data/daily.log 2>&1
35 11 * * 1-5 cd "/Users/weijin/Documents/ChatGPT/codex project1 finance news website" && python3 scripts/volume_snapshot.py >> data/volume.log 2>&1
 5 15 * * 1-5 cd "/Users/weijin/Documents/ChatGPT/codex project1 finance news website" && python3 scripts/volume_snapshot.py >> data/volume.log 2>&1
```

### GitHub Actions（可选，海外网络四源全开）
把 `.github/workflows/daily.yml` 推送到 GitHub 仓库即每天自动采集并提交 `data/`。

## 项目结构

```
config/watchlist.json      # 观察清单（指数 + 各市场核心股）
collector/volume.py        # A股成交额追踪（上午/下午/全天，每日两次快照）
collector/                 # 采集：行情/新闻编排 + 各源适配器
  sources/tencent.py       #   腾讯证券（行情主源）
  sources/sina.py          #   新浪财经（行情交叉核实）
  sources/eastmoney.py     #   东方财富（行情交叉核实 + 新闻/快讯）
  sources/yahoo.py         #   雅虎财经
  sources/investing.py     #   Investing.com
  sources/tradingview.py   #   TradingView
verify/verifier.py         # 核实：合理性 + 多源一致性
digest/digester.py         # 提炼：Top5 打分 + 按时间排序 + 涨跌榜
run_daily.py               # 主入口
data/daily/YYYY-MM-DD.json # 每日报告
data/latest.json           # 最新报告（前端读取）
data/volume/YYYY-MM-DD.json# 成交额快照（上午/全天 + 自动算下午）
data/latest_volume.json    # 最新成交额数据（前端读取）
web/                       # 前端（design-tokens + 模板）
design-tokens.md           # 设计规范（CSS 变量唯一事实来源）
scripts/volume_snapshot.py # 成交额快照（11:35 / 15:05 两次）
scripts/setup_volume_launchd.sh  # 成交额定时任务安装
scripts/                   # 运行/预览/定时任务脚本
```

## 核实规则（verify/verifier.py）

- 行情：价格 > 0；单日涨跌幅 ≤ 40%；**多源价格偏差 ≤ 1%、涨跌幅偏差 ≤ 1pp 才判定“多源通过”**，单源仅标记“待核”
- 新闻：标题 ≥ 8 字；时间可解析且不严重超前；超过 48h 标记"非当日"
- 每条输出 `verified` 与 `verification_notes`，前端以 ✓/⚠ 呈现

## 免责声明

数据来自公开渠道，仅供个人研究参考，不构成投资建议。采集频率请遵守各网站服务条款。
