/* 前端渲染：读取 data/latest.json 并渲染日报。 */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const state = { data: null, market: "us" };

  /* ---------- 主题 ---------- */
  function initTheme() {
    const saved = localStorage.getItem("theme");
    const theme = saved || "dark";
    document.body.dataset.theme = theme;
    $("#themeBtn").textContent = theme === "dark" ? "☀️ 浅色" : "🌙 深色";
    $("#themeBtn").addEventListener("click", () => {
      const next = document.body.dataset.theme === "dark" ? "light" : "dark";
      document.body.dataset.theme = next;
      localStorage.setItem("theme", next);
      $("#themeBtn").textContent = next === "dark" ? "☀️ 浅色" : "🌙 深色";
    });
  }

  /* ---------- 工具 ---------- */
  const fmtPct = (v) => (v == null ? "—" : (v > 0 ? "+" : "") + Number(v).toFixed(2) + "%");
  const fmtNum = (v, d = 2) => (v == null ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));
  const pctClass = (v) => (v == null ? "pct-flat" : v > 0 ? "pct-up" : v < 0 ? "pct-down" : "pct-flat");

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  /* ---------- 指数横条 ---------- */
  function renderIndices(data) {
    const el = $("#indicesStrip");
    if (!data.market_overview || !data.market_overview.length) {
      el.innerHTML = '<div class="empty">暂无指数数据</div>';
      return;
    }
    el.innerHTML = data.market_overview.map((ix) => `
      <div class="index-card">
        <div class="name">${esc(ix.name_cn)}</div>
        <div class="val">${fmtNum(ix.price)}</div>
        <div class="pct ${pctClass(ix.change_pct)}">${fmtPct(ix.change_pct)}</div>
      </div>`).join("");
  }

  /* ---------- Top5 ---------- */
  function renderTop5(data) {
    const el = $("#top5Body");
    const items = data.top5 || [];
    if (!items.length) {
      el.innerHTML = '<div class="empty">今日暂无通过核实的精选条目</div>';
      return;
    }
    el.innerHTML = '<div class="timeline">' + items.map((it) => `
      <div class="tl-item">
        <div class="tl-time">${esc(it.time || "时间未知")}</div>
        <h3><span class="tl-rank">#${it.rank}</span>${esc(it.title)}</h3>
        ${it.summary ? `<p>${esc(it.summary)}</p>` : ""}
        <div class="tl-meta">
          <span class="tag src">${esc(it.sub_source || it.source)}</span>
          ${(it.related_names || []).map((n) => `<span class="tag">${esc(n)}</span>`).join("")}
          ${it.url ? `<a href="${esc(it.url)}" target="_blank" rel="noopener">原文 ↗</a>` : ""}
        </div>
      </div>`).join("") + "</div>";
  }

  /* ---------- 行情表 ---------- */
  function renderQuotes(data) {
    const rows = (data.quotes && data.quotes[state.market]) || [];
    const body = $("#quotesBody");
    $("#quotesSub").textContent = `${rows.length} 只 · 涨跌幅 · 多源核实`;
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="5"><div class="empty">暂无数据</div></td></tr>';
      return;
    }
    body.innerHTML = rows.map((q) => {
      const badge = q.verified
        ? '<span class="badge-verified">✓ 多源通过</span>'
        : (q.cross_checked
            ? '<span class="badge-single" style="color:var(--color-danger)">✗ 源不一致</span>'
            : '<span class="badge-single">⚠ 单源待核</span>');
      return `<tr>
        <td><div class="stock-name">${esc(q.name_cn)}</div><div class="stock-sym">${esc(q.symbol)}</div></td>
        <td class="num">${fmtNum(q.price)}</td>
        <td class="num ${pctClass(q.change)}">${q.change == null ? "—" : (q.change > 0 ? "+" : "") + fmtNum(q.change)}</td>
        <td class="num ${pctClass(q.change_pct)}">${fmtPct(q.change_pct)}</td>
        <td>${badge}</td>
      </tr>`;
    }).join("");
  }

  /* ---------- 领涨/领跌 ---------- */
  function renderMovers(data) {
    const el = $("#moversGrid");
    const m = data.market_movers && data.market_movers[state.market];
    if (!m) { el.innerHTML = '<div class="empty">暂无数据</div>'; return; }
    const li = (list) => list.map((x) => `
      <div class="mover">
        <span class="m-name">${esc(x.name_cn)} <span class="stock-sym">${esc(x.symbol)}</span></span>
        <span class="m-val ${pctClass(x.change_pct)}">${fmtPct(x.change_pct)}</span>
      </div>`).join("");
    el.innerHTML = `
      <div>
        <div class="card-sub" style="margin-bottom:8px">领涨 TOP5</div>
        <div class="mover-list">${li(m.top_gainers || [])}</div>
      </div>
      <div>
        <div class="card-sub" style="margin-bottom:8px">领跌 TOP5</div>
        <div class="mover-list">${li(m.top_losers || [])}</div>
      </div>`;
  }

  /* ---------- 数据源状态 ---------- */
  function renderSources(data) {
    const grid = $("#srcGrid");
    const st = data.sources_status || {};
    const names = { tencent: "腾讯证券", sina: "新浪财经", eastmoney: "东方财富", yahoo: "雅虎财经", investing: "Investing.com", tradingview: "TradingView", ust_treasury: "美国财政部", cboe_vix: "Cboe VIX" };
    const entries = Object.entries(st);
    if (!entries.length) { grid.innerHTML = '<div class="empty">无状态</div>'; return; }
    grid.innerHTML = entries.map(([k, v]) => {
      let cls = "deg", label = "降级/未用";
      if (v.ok) { cls = "ok"; label = "正常"; }
      else if (v.error && /403|429|拦截|block/i.test(v.error)) { cls = "deg"; label = "被拦截(国内网络)"; }
      else if (v.error) { cls = "err"; label = "异常"; }
      return `<div class="src-card">
        <div class="s-name">${esc(names[k] || k)}</div>
        <div class="s-status ${cls}">${label}${v.error ? ` · ${esc(v.error.slice(0, 60))}` : ""}</div>
      </div>`;
    }).join("");
    const stats = data.verification_stats || {};
    $("#sourceNote").textContent = `${stats.news_verified}/${stats.news_total} 条新闻通过核实`;
    const ts = data.generated_at ? `生成于 ${data.generated_at}` : "";
    $("#footNote").textContent = `数据由本地脚本每日采集，信息经过多源交叉核实与合理性检查；部分公开渠道（如雅虎财经/Investing.com/TradingView）在境内网络可能受限而自动降级。${ts}`;
  }


  /* ---------- A股成交额追踪 ---------- */
  const fmtYi = (v) => (v == null ? "—" : Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 }) + " 亿");

  function renderVolume(d) {
    const el = $("#volumeBody");
    const dateChip = $("#volumeDateChip");
    if (!d || !d.date) {
      el.innerHTML = '<div class="empty">暂无成交额数据 — 每日 11:35 / 15:05 自动采集</div>';
      dateChip.textContent = "--";
      return;
    }
    dateChip.textContent = d.date;
    const m = d.morning || {};
    const c = d.close || {};
    const a = d.afternoon || {};
    const row = (label, src, cls) => `<tr${cls ? ` class="${cls}"` : ""}>
      <td>${label}</td>
      <td class="num">${src && src.sh_turnover_yi != null ? fmtYi(src.sh_turnover_yi) : '<span class="vol-null">待更新</span>'}</td>
      <td class="num">${src && src.sz_turnover_yi != null ? fmtYi(src.sz_turnover_yi) : '<span class="vol-null">待更新</span>'}</td>
      <td class="num">${src && src.cyb_turnover_yi != null ? fmtYi(src.cyb_turnover_yi) : '<span class="vol-null">待更新</span>'}</td>
      <td class="num">${src && src.total_yi != null ? fmtYi(src.total_yi) : '<span class="vol-null">待更新</span>'}</td>
    </tr>`;

    // 下午段 = close - morning（后端算好放 afternoon）
    const hasAfternoon = a && a.total_yi != null;
    const totalFull = c.total_yi;
    const morningTotal = m.total_yi;
    const afternoonTotal = hasAfternoon ? a.total_yi : null;

    let bar = "";
    if (morningTotal != null && (afternoonTotal != null || totalFull != null)) {
      const pm = afternoonTotal != null ? afternoonTotal : Math.max(0, totalFull - morningTotal);
      const sum = morningTotal + pm;
      const pctM = sum > 0 ? (morningTotal / sum * 100) : 0;
      bar = `
        <div class="vol-bar-wrap">
          <div class="vol-bar-label"><span>上午 ${fmtYi(morningTotal)}</span><span>下午 ${fmtYi(pm)}</span></div>
          <div class="vol-bar"><div class="seg-morning" style="width:${pctM.toFixed(1)}%"></div><div class="seg-afternoon" style="width:${(100 - pctM).toFixed(1)}%"></div></div>
          <div class="vol-legend"><span><span class="dot morning"></span>上午</span><span><span class="dot afternoon"></span>下午</span></div>
        </div>`;
    }

    const notes = [];
    if (m.time) notes.push(`上午快照 ${m.time}`);
    if (c.time) notes.push(`全天快照 ${c.time}`);
    if (!hasAfternoon) notes.push("下午 = 全天 − 上午，待 15:05 全天快照后自动计算");

    el.innerHTML = `<div class="vol-grid">
      <table class="vol-table">
        <thead><tr><th>时段</th><th class="num">沪市</th><th class="num">深市</th><th class="num">创业板</th><th class="num">两市合计</th></tr></thead>
        <tbody>
          ${row("上午", m)}
          ${row("下午", hasAfternoon ? a : null)}
          ${row("全天", c, "vol-total")}
        </tbody>
      </table>
      ${bar}
      <div class="vol-update-note">${esc(notes.join(" · "))}</div>
    </div>`;
  }

  async function loadVolume() {
    try {
      const res = await fetch("../data/latest_volume.json", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      renderVolume(await res.json());
    } catch (e) {
      renderVolume(null);
    }
  }

  /* ---------- 加载数据 ---------- */
  async function load() {
    try {
      const res = await fetch("../data/latest.json", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      state.data = await res.json();
      const d = state.data;
      $("#dateChip").textContent = d.date || "";
      document.title = `${d.date || ""} 全球市场金融资讯日报`;
      renderIndices(d);
      renderTop5(d);
      renderQuotes(d);
      renderMovers(d);
      renderSources(d);
    } catch (e) {
      $("#dateChip").textContent = "数据未生成";
      $("#top5Body").innerHTML = `<div class="empty">无法加载数据：${esc(e.message)}<br><br>请先运行 <code>python3 run_daily.py</code> 生成 data/latest.json，再刷新页面。</div>`;
      $("#quotesBody").innerHTML = `<tr><td colspan="5"><div class="empty">无法加载数据</div></td></tr>`;
      $("#srcGrid").innerHTML = `<div class="empty">无法加载数据源状态</div>`;
    }
  }

  /* ---------- 事件 ---------- */
  document.querySelectorAll("#marketTabs .tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#marketTabs .tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.market = btn.dataset.market;
      if (state.data) { renderQuotes(state.data); renderMovers(state.data); }
    });
  });

  initTheme();
  load();
  loadVolume();
})();
