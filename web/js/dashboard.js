/* 信号看板渲染：读取 data/signals、data/backtest、data/history/macro 并渲染。 */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);

  /* ---------- 工具 ---------- */
  const fmtPct = (v) => (v == null ? "—" : (v > 0 ? "+" : "") + Number(v).toFixed(2) + "%");
  const fmtNum = (v, d = 2) => (v == null ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));
  const fmtBp = (v) => (v == null ? "—" : (v > 0 ? "+" : "") + Number(v).toFixed(1) + "bp");
  const fmtRate = (v) => (v == null ? "—" : (v * 100).toFixed(1) + "%");
  const pctClass = (v) => (v == null ? "pct-flat" : v > 0 ? "pct-up" : v < 0 ? "pct-down" : "pct-flat");

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function riskCls(level) {
    if (level === "极高") return "risk-extreme";
    if (level === "高") return "risk-high";
    if (level === "中高") return "risk-mid";
    return "risk-low";
  }

  function sigCls(label) {
    if (label === "买入") return "sig-buy";
    if (label === "持有偏多") return "sig-hold-long";
    if (label === "持有偏空") return "sig-hold-short";
    if (label === "卖出") return "sig-sell";
    return "sig-watch";
  }

  function spark(values, color, w = 520, h = 110) {
    const v = (values || []).filter((x) => x != null);
    if (v.length < 2) return "";
    const min = Math.min(...v), max = Math.max(...v), range = (max - min) || 1;
    const pad = 4;
    const pts = v.map((x, i) => {
      const px = pad + (i / (v.length - 1)) * (w - pad * 2);
      const py = h - pad - ((x - min) / range) * (h - pad * 2);
      return `${px.toFixed(1)},${py.toFixed(1)}`;
    }).join(" ");
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>`;
  }

  async function loadJSON(path) {
    const res = await fetch(path, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  /* ---------- 主题 ---------- */
  function initTheme() {
    const saved = localStorage.getItem("theme") || "dark";
    document.body.dataset.theme = saved;
    $("#themeBtn").textContent = saved === "dark" ? "☀️ 浅色" : "🌙 深色";
    $("#themeBtn").addEventListener("click", () => {
      const next = document.body.dataset.theme === "dark" ? "light" : "dark";
      document.body.dataset.theme = next;
      localStorage.setItem("theme", next);
      $("#themeBtn").textContent = next === "dark" ? "☀️ 浅色" : "🌙 深色";
    });
  }

  /* ---------- 宏观仪表盘 ---------- */
  function renderMacro(signals, tSeries, vSeries) {
    const grid = $("#macroGrid");
    const overlay = signals.macro_overlay || {};
    const risk = overlay.risk || 0;
    const level = overlay.risk_level || "低";
    const comps = overlay.components || {};

    $("#macroRiskBadge").textContent = `宏观风险：${level}`;
    $("#macroRiskBadge").className = `risk-badge ${riskCls(level)}`;
    $("#macroSub").textContent = `数据截至 ${signals.date || "--"} · 10Y 收益率主导（50%）+ VIX（30%）`;

    const t10 = comps.treasury_10y ? comps.treasury_10y.value : null;
    const vix = comps.vix ? comps.vix.value : null;
    const spread = comps.curve_spread ? comps.curve_spread.value : null;

    const t10Level = t10 == null ? "—" : t10 >= 5 ? "极高" : t10 >= 4.7 ? "高" : t10 >= 4.3 ? "中高" : t10 >= 4.0 ? "中低" : "低";
    const vixLevel = vix == null ? "—" : vix >= 25 ? "高波动" : vix >= 15 ? "中波动" : "低波动";

    grid.innerHTML = `
      <div class="macro-card">
        <div class="label">10Y 美债收益率</div>
        <div class="value">${fmtNum(t10, 2)}<span class="unit">%</span></div>
        <div class="delta ${riskCls(t10Level).replace("risk-", "") === "extreme" ? "" : ""}">${t10Level}区间</div>
        <div class="extra">${comps.yield_speed ? "⚠ 收益率急涨" : "变化速度正常"}</div>
      </div>
      <div class="macro-card">
        <div class="label">VIX 恐慌指数</div>
        <div class="value">${fmtNum(vix, 2)}</div>
        <div class="delta">${vixLevel}</div>
        <div class="extra">Cboe 官方 · 日频收盘</div>
      </div>
      <div class="macro-card">
        <div class="label">10Y − 2Y 利差</div>
        <div class="value" style="font-size:var(--text-xl)">${fmtNum(spread, 2)}<span class="unit">pp</span></div>
        <div class="delta ${pctClass(spread)}">${spread != null && spread < 0 ? "收益率曲线倒挂" : "曲线正常"}</div>
        <div class="extra">倒挂预示增长担忧</div>
      </div>
      <div class="macro-card">
        <div class="label">宏观风险综合评分</div>
        <div class="value">${(risk * 100).toFixed(0)}<span class="unit">/100</span></div>
        <div class="risk-bar-wrap"><div class="risk-bar"><div class="marker" style="left:${(risk * 100).toFixed(1)}%"></div></div></div>
        <div class="extra">≥35 触发风险警示（当前${overlay.active ? "已触发" : "未触发"}）</div>
      </div>`;
  }

  /* ---------- 美债面板 ---------- */
  function renderYields(tSeries) {
    const body = $("#yieldBody");
    const series = (tSeries && tSeries.series) || {};
    const dates = Object.keys(series).sort();
    if (!dates.length) { body.innerHTML = '<div class="empty">暂无美债数据（请先运行回填脚本）</div>'; return; }
    const latest = dates[dates.length - 1];
    const rec = series[latest];
    const prev = (n) => { const d = dates[dates.length - 1 - n]; return d ? series[d] : null; };
    const p1 = prev(1), p5 = prev(5);
    const bp1 = (k) => (p1 && rec[k] != null && p1[k] != null ? (rec[k] - p1[k]) * 100 : null);
    const bp5 = (k) => (p5 && rec[k] != null && p5[k] != null ? (rec[k] - p5[k]) * 100 : null);

    const tenors = [["2Y", "2 年"], ["5Y", "5 年"], ["10Y", "10 年"], ["30Y", "30 年"]];
    $("#yieldSub").textContent = `美国财政部官方 · 数据截至 ${latest}`;

    const rows = tenors.map(([k, name]) => `
      <tr>
        <td class="tenor">${name}</td>
        <td class="num">${fmtNum(rec[k], 2)}%</td>
        <td class="num ${pctClass(bp1(k))}">${fmtBp(bp1(k))}</td>
        <td class="num ${pctClass(bp5(k))}">${fmtBp(bp5(k))}</td>
      </tr>`).join("");

    const curveKeys = ["1M", "2M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"];
    const curveLatest = curveKeys.map((k) => rec[k]).filter((x) => x != null);
    const monthAgo = prev(21);
    const curveOld = monthAgo ? curveKeys.map((k) => monthAgo[k]).filter((x) => x != null) : null;

    body.innerHTML = `
      <div>
        <table class="yield-table">
          <thead><tr><th>期限</th><th class="num">收益率</th><th class="num">较昨日</th><th class="num">较一周</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div class="chart-box">
        <div>
          <div class="chart-title">10Y / 30Y 近 90 个交易日</div>
          <div class="chart">${spark(dates.slice(-90).map((d) => series[d]["10Y"]), "#3b82f6")}</div>
          <div class="chart">${spark(dates.slice(-90).map((d) => series[d]["30Y"]), "#8b5cf6")}</div>
          <div class="chart-legend"><span><span class="dot" style="background:#3b82f6"></span>10Y</span><span><span class="dot" style="background:#8b5cf6"></span>30Y</span></div>
        </div>
        <div>
          <div class="chart-title">收益率曲线（${latest} <b style="color:#3b82f6">●</b> / 一个月前 <b style="color:#94a3b8">●</b>）</div>
          <div class="chart">${curvePolyline(curveLatest, "#3b82f6")}${curveOld ? curvePolyline(curveOld, "#94a3b8", true) : ""}</div>
          <div class="chart-legend">${curveKeys.filter((_, i) => i % 2 === 0 || curveKeys[i] === "1Y").map((k) => `<span>${k}</span>`).join("")}</div>
        </div>
      </div>`;
  }

  function curvePolyline(vals, color, faint) {
    if (!vals || vals.length < 2) return "";
    const w = 520, h = 110, pad = 6;
    const min = Math.min(...vals), max = Math.max(...vals), range = (max - min) || 1;
    const pts = vals.map((x, i) => {
      const px = pad + (i / (vals.length - 1)) * (w - pad * 2);
      const py = h - pad - ((x - min) / range) * (h - pad * 2);
      return `${px.toFixed(1)},${py.toFixed(1)}`;
    }).join(" ");
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="position:absolute;top:0;left:0"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5" vector-effect="non-scaling-stroke" ${faint ? 'stroke-dasharray="4 3"' : ""}/></svg>`;
  }

  /* ---------- 持仓信号 ---------- */
  const SUB_LABELS = {
    trend_ma: "均线趋势", ma_alignment: "均线排列", macd: "MACD", rsi: "RSI",
    position: "价格位置", volume: "量能", relative_strength: "相对强度", atr: "波动率",
  };

  function subDetail(key, v) {
    switch (key) {
      case "trend_ma": return `20日偏离 ${v.d20}% · 50日 ${v.d50}% · 200日 ${v.d200}%`;
      case "ma_alignment":
        return `50日均线 ${fmtNum(v.sma50)} · 200日均线 ${fmtNum(v.sma200)} · ${v.cross === "golden" ? "金叉" : v.cross === "death" ? "死叉" : "无交叉"}`;
      case "macd": return `MACD线 ${fmtNum(v.macd_line)} · 信号线 ${fmtNum(v.signal)} · 柱 ${fmtNum(v.hist)}（变化 ${fmtNum(v.hist_change)}）`;
      case "rsi": return `RSI(14) = ${fmtNum(v.rsi, 1)}（70+ 超买 / 30- 超卖）`;
      case "position": return `52周分位 ${v.pos52} · 布林 %B ${v.pct_b} · 52周高 ${fmtNum(v.high52)} / 低 ${fmtNum(v.low52)}`;
      case "volume": return `5日/20日量比 ${fmtNum(v.vol_ratio)} · OBV 趋势 ${v.obv_trend}`;
      case "relative_strength": return `20日相对收益 ${v.rs20}pp · 60日相对收益 ${v.rs60}pp（vs 标普500）`;
      case "atr": return `ATR(14) 占价格 ${v.atr_pct}%`;
      default: return JSON.stringify(v);
    }
  }

  function renderHoldings(signals) {
    const grid = $("#holdingsGrid");
    const holdings = (signals.holdings || []).filter((h) => h.valid);
    if (!holdings.length) {
      grid.innerHTML = '<div class="empty">暂无信号（请先运行 run_daily.py）</div>';
      return;
    }
    $("#signalSub").textContent = `数据截至 ${signals.date || "--"} · 8 个子指标加权 + 宏观风险叠加`;

    grid.innerHTML = holdings.map((h) => {
      const subs = h.sub_scores || {};
      const rows = Object.keys(SUB_LABELS).filter((k) => subs[k]).map((k) => {
        const s = subs[k];
        const sc = s.score || 0;
        const width = Math.min(Math.abs(sc) * 50, 50);
        const fill = sc >= 0
          ? `<span class="fill pos" style="width:${width.toFixed(1)}%"></span>`
          : `<span class="fill neg" style="width:${width.toFixed(1)}%"></span>`;
        return `
        <div class="sub-item" data-key="${k}">
          <button class="sub-head" type="button">
            <span class="sub-name">${SUB_LABELS[k]}</span>
            <span class="sub-bar">${fill}</span>
            <span class="sub-val">${sc > 0 ? "+" : ""}${sc.toFixed(2)}</span>
            <span class="chev">▾</span>
          </button>
          <div class="sub-detail">${esc(subDetail(k, s))}</div>
        </div>`;
      }).join("");

      const score = h.score || 0;
      const markerLeft = Math.min(Math.max((score + 1) / 2 * 100, 0), 100);
      return `
      <div class="holding-card">
        <div class="holding-head">
          <div>
            <div class="sym">${esc(h.symbol)}</div>
            <div class="cn">${esc(h.name_cn)}</div>
          </div>
          <div class="price">
            <div class="p">${fmtNum(h.price)}</div>
            <div class="chg ${pctClass(h.change_pct)}">${fmtPct(h.change_pct)}</div>
          </div>
          <span class="signal-badge ${sigCls(h.signal)}">${esc(h.signal)}</span>
        </div>
        <div class="holding-score">
          <div class="score-row">
            <span>偏空</span>
            <div class="score-bar"><div class="marker" style="left:${markerLeft.toFixed(1)}%"></div></div>
            <span>偏多</span>
            <span style="font-family:var(--font-mono);width:52px;text-align:right">${score > 0 ? "+" : ""}${score.toFixed(2)}</span>
          </div>
          <div class="score-row" style="justify-content:flex-end">置信度 ${(h.confidence || 0).toFixed(2)}</div>
        </div>
        <div class="holding-tip">${esc(h.action_tip || "")}</div>
        ${h.history_note ? `<div class="holding-note">⚠ ${esc(h.history_note)}</div>` : ""}
        <div class="sub-list">${rows}</div>
      </div>`;
    }).join("");

    grid.querySelectorAll(".sub-head").forEach((btn) => {
      btn.addEventListener("click", () => btn.closest(".sub-item").classList.toggle("open"));
    });
  }

  /* ---------- 回测 ---------- */
  function renderBacktest(bt) {
    const body = $("#btBody");
    if (!bt || !bt.holdings) {
      body.innerHTML = '<div class="empty">暂无回测数据（请先运行 scripts/run_backtest.py）</div>';
      return;
    }
    $("#btSub").textContent = `生成于 ${bt.generated_at || "--"} · 滚动样本外 · 含成本 · 无未来函数`;
    const holdings = bt.holdings.filter((h) => h.valid);

    body.innerHTML = holdings.map((h) => {
      const s = h.strategy || {}, bh = h.buy_hold || {};
      const attr = (h.indicator_attribution || []).slice().sort((a, b) => (b.total_return_pct || 0) - (a.total_return_pct || 0));
      const attrRows = attr.map((a) => {
        const hr = a.signal_hit_rates || {};
        const buy = hr["买入"] ? hr["买入"].hit_rate : null;
        const hold = hr["持有偏多"] ? hr["持有偏多"].hit_rate : null;
        return `<tr>
          <td>${esc(a.indicator)}</td>
          <td class="num ${pctClass(a.total_return_pct)}">${fmtPct(a.total_return_pct)}</td>
          <td class="num">${a.sharpe}</td>
          <td class="num">${a.trades}</td>
          <td class="num">${buy == null ? "—" : fmtRate(buy)}</td>
          <td class="num">${hold == null ? "—" : fmtRate(hold)}</td>
        </tr>`;
      }).join("");

      const stats = h.signal_stats || {};
      const hitChips = Object.keys(stats).map((k) => `<span class="hit-chip">${esc(k)} <b>${fmtRate(stats[k].hit_rate)}</b>（${stats[k].days}次）</span>`).join("");

      const cost = h.cost_sensitivity || {};
      const costChips = Object.keys(cost).map((k) => `<span class="hit-chip">成本${k} <b>${cost[k].total_return_pct == null ? "—" : cost[k].total_return_pct + "%"}</b></span>`).join("");

      const regs = h.regimes || {};
      const regRows = Object.keys(regs).map((k) => `<tr>
        <td>${esc(k)}</td>
        <td class="num">${regs[k].days}</td>
        <td class="num ${pctClass(regs[k].strategy_return_pct)}">${fmtPct(regs[k].strategy_return_pct)}</td>
        <td class="num ${pctClass(regs[k].buy_hold_return_pct)}">${fmtPct(regs[k].buy_hold_return_pct)}</td>
      </tr>`).join("");

      return `
      <div class="bt-block">
        <div class="bt-head">
          <h3>${esc(h.name_cn)} <span style="font-family:var(--font-mono)">${esc(h.symbol)}</span></h3>
          <span class="card-sub">${esc(h.period || "")}</span>
          ${h.sample_note ? `<span class="bt-note">⚠ ${esc(h.sample_note)}</span>` : ""}
        </div>
        <div class="metrics-grid">
          <div class="metric"><div class="m-label">策略总收益</div><div class="m-val ${pctClass(s.total_return_pct)}">${fmtPct(s.total_return_pct)}</div><div class="m-sub">年化 ${fmtPct(s.cagr_pct)}</div></div>
          <div class="metric"><div class="m-label">买入持有总收益</div><div class="m-val ${pctClass(bh.total_return_pct)}">${fmtPct(bh.total_return_pct)}</div><div class="m-sub">年化 ${fmtPct(bh.cagr_pct)}</div></div>
          <div class="metric"><div class="m-label">超额收益</div><div class="m-val ${pctClass(h.vs_buy_hold_pp)}">${fmtPct(h.vs_buy_hold_pp)}</div><div class="m-sub">相对买入持有</div></div>
          <div class="metric"><div class="m-label">Sharpe</div><div class="m-val">${s.sharpe == null ? "—" : s.sharpe}</div><div class="m-sub">年化</div></div>
          <div class="metric"><div class="m-label">策略最大回撤</div><div class="m-val" style="color:var(--color-danger)">${fmtPct(s.max_drawdown_pct)}</div><div class="m-sub">买入持有 ${fmtPct(bh.max_drawdown_pct)}</div></div>
          <div class="metric"><div class="m-label">换手</div><div class="m-val">${s.trades == null ? "—" : s.trades}</div><div class="m-sub">次调仓</div></div>
        </div>
        <div class="hit-chips">${hitChips || '<span class="card-sub">无多空信号样本</span>'}</div>
        <div class="hit-chips">${costChips || ""}</div>
        <div class="bt-grid2" style="margin-top:var(--space-4)">
          <div>
            <div class="card-sub" style="margin-bottom:8px">分行情区间（策略 vs 买入持有）</div>
            ${regRows ? `<table class="attr-table"><thead><tr><th>区间</th><th class="num">天数</th><th class="num">策略</th><th class="num">买入持有</th></tr></thead><tbody>${regRows}</tbody></table>` : '<div class="empty">无</div>'}
          </div>
          <div>
            <div class="card-sub" style="margin-bottom:8px">分指标归因（按总收益排序）</div>
            <table class="attr-table">
              <thead><tr><th>指标</th><th class="num">总收益</th><th class="num">Sharpe</th><th class="num">换手</th><th class="num">买入命中</th><th class="num">偏多命中</th></tr></thead>
              <tbody>${attrRows}</tbody>
            </table>
          </div>
        </div>
      </div>`;
    }).join("");

    const m = bt.methodology || {};
    body.insertAdjacentHTML("beforeend", `
      <div class="bt-method">
        <b>回测方法：</b>${esc(m.execution || "")} · ${esc(m.position || "")} · ${esc(m.cost || "")} · ${esc(m.hit_rate_horizon || "")} · ${esc(m.macro_overlay || "")} · ${esc(m.weights || "")}<br>
        <b>局限：</b>${(m.caveats || []).map(esc).join("；")}
      </div>`);
  }

  /* ---------- 加载 ---------- */
  async function load() {
    let signals = null, bt = null, tSeries = null, vSeries = null;
    try {
      const [s, b, t, v] = await Promise.all([
        loadJSON("../data/signals/latest.json").catch(() => null),
        loadJSON("../data/backtest/latest.json").catch(() => null),
        loadJSON("../data/history/macro/treasury.json").catch(() => null),
        loadJSON("../data/history/macro/vix.json").catch(() => null),
      ]);
      signals = s; bt = b; tSeries = t; vSeries = v;
    } catch (e) { /* 单个文件失败由 catch 兜底 */ }

    if (!signals && !bt) {
      $("#dateChip").textContent = "数据未生成";
      $("#macroGrid").innerHTML = `<div class="empty">无法加载数据：请先运行 <code>python3 run_daily.py</code> 与 <code>python3 scripts/run_backtest.py</code>，再刷新页面。</div>`;
      $("#yieldBody").innerHTML = `<div class="empty">无法加载美债数据（请先运行回填脚本）</div>`;
      $("#holdingsGrid").innerHTML = "";
      $("#btBody").innerHTML = "";
      return;
    }

    $("#dateChip").textContent = (signals && signals.date) || (bt && bt.generated_at) || "";
    document.title = `${$("#dateChip").textContent || ""} 持仓信号看板`;

    if (signals) {
      renderMacro(signals, tSeries, vSeries);
      renderHoldings(signals);
    } else {
      $("#macroGrid").innerHTML = `<div class="empty">暂无信号数据（请先运行 run_daily.py）</div>`;
      $("#holdingsGrid").innerHTML = `<div class="empty">暂无信号数据</div>`;
      $("#macroRiskBadge").textContent = "--";
    }
    renderYields(tSeries);
    renderBacktest(bt);
  }

  initTheme();
  load();
})();
