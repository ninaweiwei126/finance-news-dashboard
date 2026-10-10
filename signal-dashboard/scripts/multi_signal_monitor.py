#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import sys
import time
from collections import OrderedDict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

from nvda_signal_monitor import (
    add_moving_averages,
    atomic_write_text,
    backtest_tier,
    build_kdj_svg,
    build_price_svg,
    build_weekly_kdj_svg,
    get_state,
    kdj,
    money,
    pct,
    weekly_bars,
)

BASE = Path(__file__).resolve().parent
DASHBOARD = BASE / "market-signal-dashboard.html"
STATUS_JSON = BASE / "market_signal_status.json"
BACKTEST_CSV = BASE / "market_5y_backtest_trades.csv"
APP_TITLE = "多标的 10% + KDJ 信号"
APP_SHORT_TITLE = "市场信号"
APP_SUBTITLE = "NVDA · TSLA · GOOGL · META · QQQ"
APP_FOOTER = "各标的按各自策略窗口：GOOGL 使用 20% 大调整规则，其余标的默认使用 10% 回撤规则。数据源 Nasdaq，不构成投资建议。"
MANIFEST_FILE = "market-manifest.webmanifest"
SW_FILE = "market-sw.js"
LOOKBACK_DAYS = 60
SYMBOLS = [
    {"symbol": "NVDA", "name": "NVIDIA", "asset": "stocks"},
    {"symbol": "TSLA", "name": "Tesla", "asset": "stocks"},
    {"symbol": "GOOGL", "name": "Google", "asset": "stocks", "lookback": 252},
    {"symbol": "META", "name": "Meta", "asset": "stocks"},
    {"symbol": "QQQ", "name": "Nasdaq 100 ETF", "asset": "etf"},
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def fetch_json(url: str, referer: str) -> dict:
    headers = {**HEADERS, "Referer": referer}
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_money(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    if text in {"", "N/A", "NA", "None", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fetch_history(spec: dict, start: date, end: date) -> list[dict]:
    symbol, asset = spec["symbol"], spec["asset"]
    url = (
        f"https://api.nasdaq.com/api/quote/{symbol}/historical"
        f"?assetclass={asset}&fromdate={start.isoformat()}&todate={end.isoformat()}&limit=3000"
    )
    referer = f"https://www.nasdaq.com/market-activity/{'etf' if asset == 'etf' else 'stocks'}/{symbol.lower()}/historical"
    payload = fetch_json(url, referer)
    rows = (((payload.get("data") or {}).get("tradesTable") or {}).get("rows") or [])
    bars = []
    for row in rows:
        try:
            bars.append({
                "date": datetime.strptime(row["date"], "%m/%d/%Y").date(),
                "open": parse_money(row["open"]),
                "high": parse_money(row["high"]),
                "low": parse_money(row["low"]),
                "close": parse_money(row["close"]),
                "volume": int(parse_money(row["volume"]) or 0),
            })
        except (KeyError, TypeError, ValueError):
            continue
    bars = [bar for bar in bars if None not in (bar["open"], bar["high"], bar["low"], bar["close"])]
    bars.sort(key=lambda item: item["date"])
    return bars


def fetch_quote(spec: dict) -> dict:
    symbol, asset = spec["symbol"], spec["asset"]
    url = f"https://api.nasdaq.com/api/quote/{symbol}/info?assetclass={asset}"
    referer = f"https://www.nasdaq.com/market-activity/{'etf' if asset == 'etf' else 'stocks'}/{symbol.lower()}"
    payload = fetch_json(url, referer)
    data = payload.get("data") or {}
    primary = data.get("primaryData") or {}
    timestamp = None
    raw = primary.get("lastTradeTimestamp")
    if raw:
        try:
            timestamp = datetime.strptime(raw, "%b %d, %Y").date()
        except ValueError:
            pass
    return {
        "price": parse_money(primary.get("lastSalePrice")),
        "timestamp": timestamp,
        "is_realtime": bool(primary.get("isRealTime")),
        "market_status": data.get("marketStatus"),
        "volume": int(parse_money(primary.get("volume")) or 0),
    }


def append_quote_bar(bars: list[dict], quote: dict) -> list[dict]:
    price, quote_date = quote.get("price"), quote.get("timestamp")
    if price is None or quote_date is None:
        return bars
    if bars and quote_date <= bars[-1]["date"]:
        bars[-1]["close"] = price
        if quote.get("volume"):
            bars[-1]["volume"] = quote["volume"]
        return bars
    bars.append({"date": quote_date, "open": price, "high": price, "low": price, "close": price, "volume": quote.get("volume") or 0, "provisional": True})
    return bars


def build_events(daily: list[dict], start: date, custom_googl: bool = False) -> list[dict]:
    events = []
    active = None
    for index, row in enumerate(daily):
        if row["date"] < start:
            continue
        state = googl_state(daily, index) if custom_googl else get_state(row["drawdown_pct"], row["J"], row["wk_J"])
        if state["code"] == "red":
            active = None
            continue
        event = {
            "date": row["date"].isoformat(),
            "last_date": row["date"].isoformat(),
            "state": state["label"],
            "state_code": state["code"],
            "price": f"{row['close']:.2f}",
            "drawdown_pct": f"{row['drawdown_pct']:.2f}",
            "daily_K": f"{row['K']:.2f}",
            "daily_D": f"{row['D']:.2f}",
            "daily_J": f"{row['J']:.2f}",
            "weekly_K": f"{row['wk_K']:.2f}",
            "weekly_D": f"{row['wk_D']:.2f}",
            "weekly_J": f"{row['wk_J']:.2f}",
            "reference_high": f"{row['reference_high']:.2f}",
            "reference_high_date": row["reference_high_date"],
        }
        if active and active["state_code"] == event["state_code"] and (row["date"] - date.fromisoformat(active["last_date"])).days <= 7:
            active["last_date"] = event["last_date"]
            if abs(float(event["drawdown_pct"])) > abs(float(active["drawdown_pct"])):
                first = active.get("first_date", event["date"])
                active.update(event)
                active["first_date"] = first
        else:
            event["first_date"] = event["date"]
            active = event
            events.append(active)
    return events


def recent_ma200_touch(daily: list[dict], index: int, window: int = 20, pct: float = 0.05) -> bool:
    for row in daily[max(0, index - window + 1): index + 1]:
        ma200 = row.get("ma200")
        if not ma200:
            continue
        if abs(row["close"] / ma200 - 1) <= pct:
            return True
        if row["low"] <= ma200 * (1 + pct) and row["high"] >= ma200 * (1 - pct):
            return True
    return False


def googl_condition(daily: list[dict], index: int, tier: str, volume_multiple: float = 1.2) -> bool:
    row = daily[index]
    if row["drawdown_pct"] > -20:
        return False
    if tier == "attention":
        return True
    if not (row["J"] < 0 and row["vol_ratio"] >= volume_multiple and recent_ma200_touch(daily, index)):
        return False
    if tier == "yellow":
        return True
    return row["wk_J"] < 0


def googl_state(daily: list[dict], index: int) -> dict:
    row = daily[index]
    if googl_condition(daily, index, "green"):
        return {"code": "green", "label": "绿灯 · 双周期超卖", "color": "#039855", "reason": "回撤超过 20%，日周 J < 0，触及 MA200 且低点放量"}
    if googl_condition(daily, index, "yellow"):
        return {"code": "yellow", "label": "黄灯 · 日线超卖", "color": "#d99a00", "reason": "回撤超过 20%，日 J < 0，触及 MA200 且低点放量"}
    if row["drawdown_pct"] <= -20:
        return {"code": "attention", "label": "注意 · 跌幅到位", "color": "#f79009", "reason": "从一年高点回撤超过 20%"}
    return {"code": "red", "label": "红灯 · 等待", "color": "#d92d20", "reason": "从一年高点回撤不足 20%，继续等待"}


def backtest_custom(daily: list[dict], tier: str, start: date, condition, target: float = 0.10, stop: float = 0.10, horizon: int = 60) -> dict:
    trades = []
    index = 0
    while index < len(daily):
        row = daily[index]
        if row["date"] < start or not condition(daily, index, tier):
            index += 1
            continue
        if index + 1 >= len(daily):
            break
        entry_index = index + 1
        entry = daily[entry_index]["open"]
        target_price, stop_price = entry * (1 + target), entry * (1 - stop)
        outcome = "pending"
        exit_index = min(len(daily) - 1, entry_index + horizon)
        target_index = stop_index = None
        max_favorable, max_adverse = -999.0, 999.0
        for probe in range(entry_index, min(len(daily), entry_index + horizon + 1)):
            bar = daily[probe]
            max_favorable = max(max_favorable, (bar["high"] / entry - 1) * 100)
            max_adverse = min(max_adverse, (bar["low"] / entry - 1) * 100)
            hit_target, hit_stop = bar["high"] >= target_price, bar["low"] <= stop_price
            if hit_target and hit_stop:
                if bar["open"] >= target_price:
                    outcome, target_index, exit_index = "win", probe, probe
                else:
                    outcome, stop_index, exit_index = "loss", probe, probe
                break
            if hit_target:
                outcome, target_index, exit_index = "win", probe, probe
                break
            if hit_stop:
                outcome, stop_index, exit_index = "loss", probe, probe
                break
        else:
            last_index = min(len(daily) - 1, entry_index + horizon)
            outcome = "timeout" if last_index - entry_index >= horizon else "pending"
            exit_index = last_index
        trades.append({
            "signal_date": row["date"].isoformat(),
            "entry_date": daily[entry_index]["date"].isoformat(),
            "entry": entry,
            "outcome": outcome,
            "exit_date": daily[exit_index]["date"].isoformat(),
            "exit": daily[exit_index]["close"],
            "ret": (daily[exit_index]["close"] / entry - 1) * 100,
            "days": exit_index - entry_index,
            "mfe": max_favorable,
            "mae": max_adverse,
            "target_days": target_index - entry_index if target_index is not None else None,
            "stop_days": stop_index - entry_index if stop_index is not None else None,
            "drawdown": row["drawdown_pct"],
            "daily_j": row["J"],
            "weekly_j": row["wk_J"],
        })
        index = exit_index + 1
    resolved = [item for item in trades if item["outcome"] != "pending"]
    wins = [item for item in resolved if item["outcome"] == "win"]
    losses = [item for item in resolved if item["outcome"] == "loss"]
    timeouts = [item for item in resolved if item["outcome"] == "timeout"]
    return {
        "tier": tier, "entries": len(trades), "resolved": len(resolved), "wins": len(wins),
        "losses": len(losses), "timeouts": len(timeouts),
        "win_rate": len(wins) / len(resolved) * 100 if resolved else 0,
        "invalid_rate": (len(losses) + len(timeouts)) / len(resolved) * 100 if resolved else 0,
        "avg_return": sum(item["ret"] for item in resolved) / len(resolved) if resolved else 0,
        "avg_mfe": sum(item["mfe"] for item in resolved) / len(resolved) if resolved else 0,
        "worst_mae": min((item["mae"] for item in resolved), default=0),
        "trades": trades,
    }


def compute_symbol(spec: dict, default_lookback: int = LOOKBACK_DAYS) -> tuple[dict, dict]:
    lookback_days = int(spec.get("lookback", default_lookback))
    today = date.today()
    history = fetch_history(spec, today - timedelta(days=2600), today)
    quote = fetch_quote(spec)
    history = append_quote_bar(history, quote)
    if not history:
        raise RuntimeError(f"No data for {spec['symbol']}")
    daily = add_moving_averages(kdj(history))
    weeks = weekly_bars(daily)
    weeks_kdj = kdj(weeks)
    week_by_start = {week["week_start"]: week for week in weeks_kdj}
    for index, row in enumerate(daily):
        week = week_by_start[row["date"] - timedelta(days=row["date"].weekday())]
        row["wk_K"], row["wk_D"], row["wk_J"] = week["K"], week["D"], week["J"]
        rolling = daily[max(0, index - lookback_days + 1): index + 1]
        reference_row = max(rolling, key=lambda item: item["high"])
        row["reference_high"] = reference_row["high"]
        row["reference_high_date"] = reference_row["date"].isoformat()
        row["drawdown_pct"] = (row["close"] / reference_row["high"] - 1) * 100
        row["vol20"] = sum(item["volume"] for item in daily[max(0, index - 19): index + 1]) / min(20, index + 1)
        row["vol_ratio"] = row["volume"] / row["vol20"] if row["vol20"] else None

    current_week_start = today - timedelta(days=today.weekday())
    current_week = next((week for week in reversed(weeks_kdj) if week["week_start"] == current_week_start), weeks_kdj[-1])
    last_week = next((week for week in reversed(weeks_kdj) if week["week_start"] < current_week["week_start"]), None)
    latest = daily[-1]
    lookback = daily[-lookback_days:]
    reference = max(lookback, key=lambda item: item["high"])
    price = latest["close"]
    drawdown = (price / reference["high"] - 1) * 100
    custom_googl = spec["symbol"] == "GOOGL"
    trigger_price = reference["high"] * (0.80 if custom_googl else 0.90)
    backtest_start = today - timedelta(days=365 * 5 + 2)
    if custom_googl:
        state = googl_state(daily, len(daily) - 1)
        backtest = {tier: backtest_custom(daily, tier, backtest_start, googl_condition) for tier in ("attention", "yellow", "green")}
    else:
        state = get_state(drawdown, latest["J"], current_week["J"])
        backtest = {tier: backtest_tier(daily, tier, backtest_start, target=0.10, stop=0.10, horizon=60) for tier in ("attention", "yellow", "green")}
    backtest["period_start"] = backtest_start.isoformat()
    backtest["period_end"] = latest["date"].isoformat()
    events = build_events(daily, backtest_start, custom_googl)
    status = {
        "symbol": spec["symbol"],
        "name": spec["name"],
        "asset": spec["asset"],
        "date": latest["date"].isoformat(),
        "updated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "price": price,
        "is_realtime": quote.get("is_realtime", False),
        "market_status": quote.get("market_status"),
        "lookback_days": lookback_days,
        "reference_high": reference["high"],
        "reference_high_date": reference["date"].isoformat(),
        "drawdown_pct": drawdown,
        "trigger_price": trigger_price,
        "distance_to_trigger_pct": (price / trigger_price - 1) * 100,
        "daily_k": latest["K"],
        "daily_d": latest["D"],
        "daily_j": latest["J"],
        "weekly_k": current_week["K"],
        "weekly_d": current_week["D"],
        "weekly_j": current_week["J"],
        "week_date": current_week["date"].isoformat(),
        "last_week_j": last_week["J"] if last_week else 0,
        "state_code": state["code"],
        "state_label": state["label"],
        "state_color": state["color"],
        "state_reason": state["reason"],
        "strategy_label": "GOOGL 20% + KDJ + MA200 + 放量" if custom_googl else "通用 10% + 日/周 J",
        "drawdown_threshold": 20 if custom_googl else 10,
        "history_rows": events,
        "backtest": backtest,
    }
    chart_data = {
        "daily": [{k: row.get(k) for k in ("date", "open", "high", "low", "close", "volume", "K", "D", "J", "ma20", "ma50", "ma200")} for row in daily[-120:]],
        "weekly": [{"date": row["date"].isoformat(), "week_start": row["week_start"].isoformat(), "K": row["K"], "D": row["D"], "J": row["J"]} for row in weeks_kdj[-30:]],
        "events": events,
    }
    for item in chart_data["daily"]:
        item["date"] = item["date"].isoformat()
    return status, chart_data


def render_panel(status: dict, chart_data: dict, active: bool) -> str:
    daily = [{**row, "date": date.fromisoformat(row["date"])} for row in chart_data["daily"]]
    weekly = [{**row, "date": date.fromisoformat(row["date"]), "week_start": date.fromisoformat(row["week_start"])} for row in chart_data["weekly"]]
    events = chart_data["events"]
    x_min, x_max = daily[0]["date"], daily[-1]["date"]
    weekly_cross = {row["week_start"].isoformat(): row["J"] for row in weekly}
    reference = {"date": date.fromisoformat(status["reference_high_date"]), "high": status["reference_high"]}
    price_svg = build_price_svg(daily, events, reference, status["trigger_price"], status["price"], symbol=status["symbol"])
    daily_svg = build_kdj_svg(daily, events, "日线 KDJ 9,3,3", x_min, x_max, weekly_cross, symbol=status["symbol"])
    weekly_svg = build_weekly_kdj_svg(weekly, x_min, x_max, symbol=status["symbol"])
    bt = status["backtest"]
    tier_labels = {"attention": "注意", "yellow": "黄灯", "green": "绿灯"}
    tier_rows = "".join(
        f"<tr><td>{tier_labels[tier]}</td><td>{bt[tier]['entries']}</td><td>{bt[tier]['wins']}</td>"
        f"<td>{bt[tier]['losses'] + bt[tier]['timeouts']}</td><td>{bt[tier]['win_rate']:.1f}%</td></tr>"
        for tier in ("attention", "yellow", "green")
    )
    green_rows = "".join(
        f"<tr><td>{html.escape(item['signal_date'])}</td><td>{html.escape(item['entry_date'])}</td>"
        f"<td>{'有效' if item['outcome']=='win' else '无效' if item['outcome']=='loss' else '超时'}</td>"
        f"<td>{item['mae']:.1f}%</td><td>{item['mfe']:.1f}%</td>"
        f"<td>{item['target_days'] if item['target_days'] is not None else '-'}</td></tr>"
        for item in bt["green"]["trades"]
    ) or "<tr><td colspan='6' class='muted'>暂无绿灯样本</td></tr>"
    recent_rows = status["history_rows"][-10:]
    recent_html = "".join(
        f"<tr><td>{html.escape(row['date'])}</td><td>{html.escape(row['state'])}</td><td>{html.escape(row['price'])}</td>"
        f"<td>{html.escape(row['drawdown_pct'])}%</td><td>{html.escape(row['daily_J'])}</td><td>{html.escape(row['weekly_J'])}</td></tr>"
        for row in reversed(recent_rows)
    ) or "<tr><td colspan='6' class='muted'>暂无触发记录</td></tr>"
    style = "" if active else " style='display:none'"
    threshold = int(status.get("drawdown_threshold", 10))
    backtest_note = (
        "GOOGL：跌幅≥20%；触及 MA200 附近；日 J<0；成交量≥1.2倍20日均量；绿灯再叠加周 J<0。"
        if status["symbol"] == "GOOGL" else
        "下一交易日开盘买入，60 天内先到 +10% 为有效，先到 -10% 或到期为无效。"
    )
    return f"""
<div class="panel" data-panel="{status['symbol']}"{style}>
  <div class="status" style="background:{status['state_color']}">
    <div><h2>{status['symbol']} · {html.escape(status['state_label'])}</h2><p>{html.escape(status['state_reason'])}</p></div>
    <div class="price"><span>{html.escape(status['name'])} · {html.escape(status['date'])}</span><strong>{money(status['price'])}</strong><span>参考高点 {money(status['reference_high'])}</span></div>
  </div>
  <div class="grid">
    <div class="card"><div class="label">当前回撤</div><div class="value">{pct(status['drawdown_pct'])}</div></div>
    <div class="card"><div class="label">{threshold}% 触发价</div><div class="value">{money(status['trigger_price'])}</div><div class="note">距触发 {pct(status['distance_to_trigger_pct'])}</div></div>
    <div class="card"><div class="label">日线 J</div><div class="value">{status['daily_j']:.1f}</div><div class="note">K {status['daily_k']:.1f} / D {status['daily_d']:.1f}</div></div>
    <div class="card"><div class="label">周线 J</div><div class="value">{status['weekly_j']:.1f}</div><div class="note">K {status['weekly_k']:.1f} / D {status['weekly_d']:.1f}</div></div>
  </div>
  <section><h3>K 线与 KDJ 联动</h3><div class="chart-legend">
    <span><i style="background:#d92d20"></i>上涨 K</span><span><i style="background:#039855"></i>下跌 K</span>
    <span><i style="background:#2e90fa"></i>MA20 / K</span><span><i style="background:#f79009"></i>MA50 / D</span>
    <span><i style="background:#9b79ec"></i>MA200 / J</span><span><i class="ring" style="background:#039855"></i>双周期 J&lt;0</span>
  </div><div class="chart-scroll">{price_svg}{daily_svg}{weekly_svg}</div></section>
  <section><h3>5 年回测概览</h3><div class="sub">{backtest_note}</div>
    <table><thead><tr><th>级别</th><th>次数</th><th>有效</th><th>无效</th><th>胜率</th></tr></thead><tbody>{tier_rows}</tbody></table>
    <h4>绿灯明细</h4><table><thead><tr><th>信号日</th><th>买入日</th><th>结果</th><th>最大浮亏</th><th>最大浮盈</th><th>到 +10% 天数</th></tr></thead><tbody>{green_rows}</tbody></table>
  </section>
  <section><h3>近期触发记录</h3><table><thead><tr><th>日期</th><th>状态</th><th>价格</th><th>回撤</th><th>日J</th><th>周J</th></tr></thead><tbody>{recent_html}</tbody></table></section>
</div>
"""


def build_dashboard(statuses: list[dict], charts: dict[str, dict]) -> str:
    nav = "".join(
        f'<button type="button" class="tab{" active" if idx==0 else ""}" data-symbol="{status["symbol"]}"><b>{status["symbol"]}</b><span class="tab-dot" style="background:{status["state_color"]}"></span><small>{html.escape(status["state_label"].split(" · ")[0])}</small></button>'
        for idx, status in enumerate(statuses)
    )
    panels = "".join(render_panel(status, charts[status["symbol"]], idx == 0) for idx, status in enumerate(statuses))
    updated = statuses[0]["updated_at"] if statuses else ""
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#111318"><meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="{APP_SHORT_TITLE}">
<link rel="manifest" href="{MANIFEST_FILE}"><link rel="apple-touch-icon" href="icon-192.png">
<title>{APP_TITLE}</title>
<style>
:root{{color-scheme:light dark;--bg:light-dark(#f7f8fa,#111318);--panel:light-dark(#fff,#1b1d23);--text:light-dark(#1a1c1f,#f5f6f7);--muted:light-dark(#667085,#a6acb8);--line:light-dark(#e4e7ec,#30343d)}}
*{{box-sizing:border-box}}body{{margin:0;padding:26px 16px 48px;background:var(--bg);color:var(--text);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}
.wrap{{max-width:1120px;margin:0 auto}}h1{{margin:0 0 4px;font-size:24px}}.sub{{color:var(--muted);font-size:12px}}header{{margin-bottom:16px}}.tabs{{display:flex;gap:8px;overflow-x:auto;padding:10px 0 4px}}
.tab{{appearance:none;border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:12px;padding:9px 12px;min-width:92px;text-align:left;cursor:pointer;opacity:.58}}.tab.active{{opacity:1;border-color:currentColor}}.tab b{{display:block;font-size:14px}}.tab small{{color:var(--muted)}}.tab-dot{{float:right;width:10px;height:10px;border-radius:50%;margin-top:-20px}}
.status{{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:20px 22px;border-radius:16px;color:#fff;margin-bottom:14px}}.status h2{{margin:0 0 3px;font-size:22px}}.status p{{margin:0;opacity:.93}}.price{{text-align:right;white-space:nowrap}}.price strong{{display:block;font-size:28px}}
.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:14px}}.card,section{{background:var(--panel);border:1px solid var(--line);border-radius:14px}}.card{{padding:14px}}.card .label{{color:var(--muted);font-size:12px}}.card .value{{font-size:21px;font-weight:650;margin-top:4px}}.card .note{{color:var(--muted);font-size:11px}}
section{{padding:17px;margin-top:14px;overflow-x:auto}}section h3{{margin:0 0 10px;font-size:16px}}section h4{{margin:16px 0 8px;font-size:14px}}table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}th,td{{padding:8px 7px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}th:first-child,td:first-child{{text-align:left}}th{{color:var(--muted);font-size:12px}}
.chart-legend{{display:flex;flex-wrap:wrap;gap:13px;color:var(--muted);font-size:12px;margin-bottom:8px}}.chart-legend span{{display:inline-flex;align-items:center;gap:5px}}.chart-legend i{{width:14px;height:3px;border-radius:2px}}.chart-legend i.ring{{width:9px;height:9px;border:2px solid #fff;border-radius:50%}}.chart-scroll{{overflow-x:auto}}.chart-scroll svg{{display:block;min-width:760px;width:100%;height:auto}}
.muted{{color:var(--muted)}}footer{{color:var(--muted);font-size:12px;margin-top:16px}}
@media(max-width:760px){{body{{padding:18px 10px 36px}}.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.status{{align-items:flex-start;flex-direction:column}}.price{{text-align:left}}.tab{{min-width:82px}}}}
@media(max-width:480px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap"><header><h1>{APP_TITLE}</h1><div class="sub">{APP_SUBTITLE} · 数据更新 {html.escape(updated)}</div><div class="tabs">{nav}</div></header>{panels}<footer>{APP_FOOTER}</footer></div>
<script>
document.querySelectorAll('.tab').forEach(btn=>btn.addEventListener('click',()=>{{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===btn));document.querySelectorAll('.panel').forEach(p=>p.style.display=p.dataset.panel===btn.dataset.symbol?'':'none');}}));
if('serviceWorker' in navigator) navigator.serviceWorker.register('./{SW_FILE}');
const standalone=window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;
if(standalone) setInterval(()=>location.reload(),300000);
</script></body></html>"""


def write_backtest_csv(statuses: list[dict]) -> None:
    import csv
    rows = []
    for status in statuses:
        for tier in ("attention", "yellow", "green"):
            for trade in status["backtest"][tier]["trades"]:
                rows.append({"symbol": status["symbol"], "tier": tier, **trade})
    if not rows:
        return
    with BACKTEST_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run_once(lookback_days: int = LOOKBACK_DAYS) -> list[dict]:
    statuses, charts = [], {}
    for spec in SYMBOLS:
        status, chart = compute_symbol(spec, lookback_days)
        statuses.append(status)
        charts[status["symbol"]] = chart
        print(f"{status['symbol']} {status['state_label']} price={money(status['price'])} dd={pct(status['drawdown_pct'])} dailyJ={status['daily_j']:.1f} weeklyJ={status['weekly_j']:.1f}", flush=True)
    atomic_write_text(STATUS_JSON, json.dumps(statuses, ensure_ascii=False, indent=2))
    atomic_write_text(DASHBOARD, build_dashboard(statuses, charts))
    write_backtest_csv(statuses)
    print(DASHBOARD)
    return statuses


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-symbol drawdown + KDJ monitor")
    parser.add_argument("--lookback", type=int, default=LOOKBACK_DAYS)
    args = parser.parse_args()
    run_once(args.lookback)


if __name__ == "__main__":
    main()
