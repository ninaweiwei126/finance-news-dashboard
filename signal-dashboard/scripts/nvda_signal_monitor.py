#!/usr/bin/env python3
"""NVDA 10% drawdown + KDJ signal monitor.

Data source: Nasdaq public quote/historical endpoints.
This script builds a self-contained dashboard and status JSON.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import sys
import time
from collections import OrderedDict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent
DASHBOARD_PATH = BASE_DIR / "nvda-signal-dashboard.html"
STATUS_PATH = BASE_DIR / "nvda_signal_status.json"
HISTORY_PATH = BASE_DIR / "nvda_signal_history.csv"
LOOKBACK_DAYS = 60
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nasdaq.com/market-activity/stocks/nvda",
}


def fetch_json(url: str) -> dict:
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=25) as response:
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


def fetch_history(start: date, end: date) -> list[dict]:
    url = (
        "https://api.nasdaq.com/api/quote/NVDA/historical"
        f"?assetclass=stocks&fromdate={start.isoformat()}&todate={end.isoformat()}&limit=3000"
    )
    payload = fetch_json(url)
    rows = (((payload.get("data") or {}).get("tradesTable") or {}).get("rows") or [])
    bars = []
    for row in rows:
        try:
            dt = datetime.strptime(row["date"], "%m/%d/%Y").date()
            bars.append({
                "date": dt,
                "open": parse_money(row["open"]),
                "high": parse_money(row["high"]),
                "low": parse_money(row["low"]),
                "close": parse_money(row["close"]),
                "volume": int(parse_money(row["volume"]) or 0),
            })
        except (KeyError, TypeError, ValueError):
            continue
    bars = [b for b in bars if None not in (b["open"], b["high"], b["low"], b["close"])]
    bars.sort(key=lambda x: x["date"])
    return bars


def fetch_quote() -> dict:
    payload = fetch_json("https://api.nasdaq.com/api/quote/NVDA/info?assetclass=stocks")
    data = payload.get("data") or {}
    primary = data.get("primaryData") or {}
    timestamp = None
    raw_ts = primary.get("lastTradeTimestamp")
    if raw_ts:
        try:
            timestamp = datetime.strptime(raw_ts, "%b %d, %Y").date()
        except ValueError:
            timestamp = None
    return {
        "price": parse_money(primary.get("lastSalePrice")),
        "timestamp": timestamp,
        "is_realtime": bool(primary.get("isRealTime")),
        "market_status": data.get("marketStatus"),
        "volume": int(parse_money(primary.get("volume")) or 0),
    }


def append_quote_bar(bars: list[dict], quote: dict) -> list[dict]:
    price = quote.get("price")
    quote_date = quote.get("timestamp")
    if price is None or quote_date is None:
        return bars
    if bars and quote_date <= bars[-1]["date"]:
        bars[-1]["close"] = price
        if quote.get("volume"):
            bars[-1]["volume"] = quote["volume"]
        return bars
    bars.append({
        "date": quote_date,
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": quote.get("volume") or 0,
        "provisional": True,
    })
    return bars


def kdj(bars: list[dict], period: int = 9) -> list[dict]:
    k_value = 50.0
    d_value = 50.0
    out = []
    for index, bar in enumerate(bars):
        window = bars[max(0, index - period + 1): index + 1]
        lowest = min(item["low"] for item in window)
        highest = max(item["high"] for item in window)
        rsv = 50.0 if highest == lowest else (bar["close"] - lowest) / (highest - lowest) * 100
        k_value = (2 / 3) * k_value + (1 / 3) * rsv
        d_value = (2 / 3) * d_value + (1 / 3) * k_value
        j_value = 3 * k_value - 2 * d_value
        out.append({**bar, "K": k_value, "D": d_value, "J": j_value, "RSV": rsv})
    return out


def add_moving_averages(bars: list[dict], periods=(20, 50, 200)) -> list[dict]:
    closes = [item["close"] for item in bars]
    for index, bar in enumerate(bars):
        for period in periods:
            bar[f"ma{period}"] = (
                sum(closes[index - period + 1:index + 1]) / period
                if index >= period - 1 else None
            )
    return bars


def weekly_bars(bars: list[dict]) -> list[dict]:
    grouped: OrderedDict[date, list[dict]] = OrderedDict()
    for bar in bars:
        monday = bar["date"] - timedelta(days=bar["date"].weekday())
        grouped.setdefault(monday, []).append(bar)
    weeks = []
    for monday, items in grouped.items():
        weeks.append({
            "week_start": monday,
            "date": items[-1]["date"],
            "open": items[0]["open"],
            "high": max(item["high"] for item in items),
            "low": min(item["low"] for item in items),
            "close": items[-1]["close"],
            "volume": sum(item["volume"] for item in items),
            "partial": items[-1].get("provisional", False) or items[-1]["date"].weekday() != 4,
        })
    return weeks


def get_state(drawdown: float, daily_j: float, weekly_j: float) -> dict:
    if drawdown <= -10 and daily_j < 0 and weekly_j < 0:
        return {
            "code": "green",
            "label": "绿灯 · 双周期超卖",
            "color": "#039855",
            "reason": "回撤达到 10%，且日 J < 0、周 J < 0，进入双周期超卖机会区",
        }
    if drawdown <= -10 and daily_j < 0:
        return {
            "code": "yellow",
            "label": "黄灯 · 日线超卖",
            "color": "#d99a00",
            "reason": "回撤达到 10%，日 J < 0，但周 J 尚未转负",
        }
    if drawdown <= -10:
        return {
            "code": "attention",
            "label": "注意 · 跌幅到位",
            "color": "#f79009",
            "reason": "从参考高点回撤达到 10%，但日 J 尚未转负",
        }
    return {
        "code": "red",
        "label": "红灯 · 等待",
        "color": "#d92d20",
        "reason": "从参考高点回撤不足 10%，继续等待",
    }


def build_history_events(daily: list[dict], weeks_kdj: list[dict], lookback_days: int) -> list[dict]:
    events: list[dict] = []
    active: dict | None = None
    for index, row in enumerate(daily):
        if row["date"].year < 2026:
            continue
        window = daily[max(0, index - lookback_days + 1): index + 1]
        reference = max(window, key=lambda item: item["high"])
        drawdown = (row["close"] / reference["high"] - 1) * 100
        week_start = row["date"] - timedelta(days=row["date"].weekday())
        week = next((item for item in weeks_kdj if item["week_start"] == week_start), weeks_kdj[-1])
        state = get_state(drawdown, row["J"], week["J"])
        if state["code"] == "red":
            active = None
            continue
        event = {
            "date": row["date"].isoformat(),
            "last_date": row["date"].isoformat(),
            "state": state["label"],
            "state_code": state["code"],
            "price": f"{row['close']:.2f}",
            "drawdown_pct": f"{drawdown:.2f}",
            "daily_K": f"{row['K']:.2f}",
            "daily_D": f"{row['D']:.2f}",
            "daily_J": f"{row['J']:.2f}",
            "weekly_K": f"{week['K']:.2f}",
            "weekly_D": f"{week['D']:.2f}",
            "weekly_J": f"{week['J']:.2f}",
            "reference_high": f"{reference['high']:.2f}",
            "reference_high_date": reference["date"].isoformat(),
            "trigger_price": f"{reference['high'] * 0.9:.2f}",
            "updated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        }
        if active and active["state_code"] == event["state_code"] and (row["date"] - date.fromisoformat(active["last_date"])).days <= 7:
            active["last_date"] = event["last_date"]
            if abs(float(event["drawdown_pct"])) > abs(float(active["drawdown_pct"])):
                active.update(event)
                active["date"] = active.get("first_date", event["date"])
        else:
            event["first_date"] = event["date"]
            active = event
            events.append(active)
    return events


def write_history(rows: list[dict]) -> None:
    fieldnames = [
        "date", "last_date", "first_date", "state", "state_code", "price", "drawdown_pct",
        "daily_K", "daily_D", "daily_J", "weekly_K", "weekly_D", "weekly_J",
        "reference_high", "reference_high_date", "trigger_price", "updated_at",
    ]
    with HISTORY_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def svg_escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def svg_line(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    return "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def tick_values(low: float, high: float, count: int = 5) -> list[float]:
    if high <= low:
        return [low]
    return [low + (high - low) * idx / (count - 1) for idx in range(count)]


def build_price_svg(
    daily: list[dict],
    events: list[dict],
    reference: dict,
    trigger_price: float,
    current_price: float,
    days: int = 120,
    symbol: str = "NVDA",
) -> str:
    bars = daily[-days:]
    if not bars:
        return ""
    width, height = 1000, 510
    left, right, top = 64, 20, 22
    price_bottom = 356
    volume_top, volume_bottom = 396, 466
    plot_w = width - left - right
    date_min, date_max = bars[0]["date"].toordinal(), bars[-1]["date"].toordinal()
    x = lambda value: left + (value.toordinal() - date_min) / max(1, date_max - date_min) * plot_w

    values = []
    for bar in bars:
        values.extend([bar["high"], bar["low"]])
        for key in ("ma20", "ma50", "ma200"):
            if bar.get(key):
                values.append(bar[key])
    values.extend([reference["high"], trigger_price, current_price])
    y_min, y_max = min(values), max(values)
    pad = (y_max - y_min) * 0.06 or 1
    y_min -= pad
    y_max += pad
    y = lambda value: price_bottom - (value - y_min) / max(0.0001, y_max - y_min) * (price_bottom - top)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{svg_escape(symbol)} 日K线、成交量、均线和信号">',
        '<rect x="0" y="0" width="1000" height="510" fill="transparent"/>',
    ]
    for tick in tick_values(y_min, y_max, 5):
        yy = y(tick)
        parts.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{width-right}" y2="{yy:.2f}" stroke="#e4e7ec" stroke-width="1" stroke-dasharray="2 5"/>')
        parts.append(f'<text x="{left-8}" y="{yy+4:.2f}" text-anchor="end" font-size="12" fill="#667085">${tick:.0f}</text>')
    for idx in range(6):
        value = date_min + (date_max - date_min) * idx / 5
        dt = date.fromordinal(round(value))
        xx = left + plot_w * idx / 5
        parts.append(f'<line x1="{xx:.2f}" y1="{top}" x2="{xx:.2f}" y2="{volume_bottom}" stroke="#f2f4f7" stroke-width="1"/>')
        parts.append(f'<text x="{xx:.2f}" y="489" text-anchor="middle" font-size="12" fill="#667085">{dt.month}/{dt.day}</text>')

    candle_w = max(1.4, min(7.0, plot_w / len(bars) * 0.68))
    for bar in bars:
        xx = x(bar["date"])
        color = "#d92d20" if bar["close"] >= bar["open"] else "#039855"
        parts.append(f'<line x1="{xx:.2f}" y1="{y(bar["high"]):.2f}" x2="{xx:.2f}" y2="{y(bar["low"]):.2f}" stroke="{color}" stroke-width="1"/>')
        y_open, y_close = y(bar["open"]), y(bar["close"])
        body_y, body_h = min(y_open, y_close), max(1.2, abs(y_open - y_close))
        parts.append(f'<rect x="{xx-candle_w/2:.2f}" y="{body_y:.2f}" width="{candle_w:.2f}" height="{body_h:.2f}" fill="{color}"/>')

    for key, color in (("ma20", "#2e90fa"), ("ma50", "#f79009"), ("ma200", "#9b79ec")):
        points = [(x(bar["date"]), y(bar[key])) for bar in bars if bar.get(key)]
        parts.append(f'<path d="{svg_line(points)}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')

    ref_y = y(reference["high"])
    trigger_y = y(trigger_price)
    parts.append(f'<line x1="{left}" y1="{ref_y:.2f}" x2="{width-right}" y2="{ref_y:.2f}" stroke="#d92d20" stroke-width="1.5" stroke-dasharray="7 5"/>')
    parts.append(f'<text x="{width-right-4}" y="{ref_y-6:.2f}" text-anchor="end" font-size="12" fill="#d92d20">参考高点 ${reference["high"]:.2f}</text>')
    parts.append(f'<line x1="{left}" y1="{trigger_y:.2f}" x2="{width-right}" y2="{trigger_y:.2f}" stroke="#f79009" stroke-width="1.5" stroke-dasharray="7 5"/>')
    parts.append(f'<text x="{width-right-4}" y="{trigger_y-6:.2f}" text-anchor="end" font-size="12" fill="#f79009">10% 触发 ${trigger_price:.2f}</text>')

    event_by_date = {item["date"]: item for item in events}
    for bar in bars:
        event = event_by_date.get(bar["date"].isoformat())
        if not event:
            continue
        code = event["state_code"]
        color = {"green": "#039855", "yellow": "#d99a00", "attention": "#f79009"}.get(code, "#667085")
        marker_y = y(bar["high"]) - 12
        parts.append(f'<circle cx="{x(bar["date"]):.2f}" cy="{marker_y:.2f}" r="5" fill="{color}" stroke="#ffffff" stroke-width="1.5"><title>{svg_escape(event["state"])}</title></circle>')

    v_max = max(bar["volume"] for bar in bars) or 1
    for bar in bars:
        xx = x(bar["date"])
        vh = (bar["volume"] / v_max) * (volume_bottom - volume_top)
        color = "#d92d20" if bar["close"] >= bar["open"] else "#039855"
        parts.append(f'<rect x="{xx-candle_w/2:.2f}" y="{volume_bottom-vh:.2f}" width="{candle_w:.2f}" height="{vh:.2f}" fill="{color}" fill-opacity="0.64"/>')
    parts.append(f'<text x="{left-8}" y="{volume_top+12}" text-anchor="end" font-size="12" fill="#667085">{v_max/1e6:.0f}M</text>')
    parts.append(f'<text x="{left}" y="{volume_top-8}" font-size="12" fill="#667085">成交量</text>')
    parts.append(f'<line x1="{left}" y1="{price_bottom+3}" x2="{width-right}" y2="{price_bottom+3}" stroke="#d0d5dd" stroke-width="1"/>')
    parts.append('</svg>')
    return "".join(parts)


def build_kdj_svg(
    rows: list[dict],
    events: list[dict],
    title: str,
    x_min: date,
    x_max: date,
    weekly_cross: dict[str, float] | None = None,
    height: int = 220,
    symbol: str = "NVDA",
) -> str:
    if not rows:
        return ""
    width = 1000
    left, right, top, bottom = 64, 20, 20, 42
    plot_w, plot_h = width - left - right, height - top - bottom
    dmin, dmax = x_min.toordinal(), x_max.toordinal()
    x = lambda value: left + (value.toordinal() - dmin) / max(1, dmax - dmin) * plot_w
    y_min, y_max = -30.0, 110.0
    y = lambda value: top + (y_max - value) / (y_max - y_min) * plot_h
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{svg_escape(symbol)} {svg_escape(title)}">']
    parts.append(f'<text x="{left}" y="14" font-size="13" font-weight="600" fill="#344054">{svg_escape(title)}</text>')
    for tick in (0, 20, 80, 100):
        yy = y(tick)
        color = "#f79009" if tick in (0, 20) else "#d0d5dd"
        parts.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{width-right}" y2="{yy:.2f}" stroke="{color}" stroke-width="1" stroke-dasharray="4 5"/>')
        parts.append(f'<text x="{left-8}" y="{yy+4:.2f}" text-anchor="end" font-size="12" fill="#667085">{tick}</text>')
    for idx in range(6):
        value = dmin + (dmax - dmin) * idx / 5
        dt = date.fromordinal(round(value))
        xx = left + plot_w * idx / 5
        parts.append(f'<line x1="{xx:.2f}" y1="{top}" x2="{xx:.2f}" y2="{top+plot_h}" stroke="#f2f4f7" stroke-width="1"/>')
        parts.append(f'<text x="{xx:.2f}" y="{height-14}" text-anchor="middle" font-size="12" fill="#667085">{dt.month}/{dt.day}</text>')
    for key, color in (("K", "#2e90fa"), ("D", "#f79009"), ("J", "#9b79ec")):
        points = [(x(row["date"]), y(row[key])) for row in rows]
        parts.append(f'<path d="{svg_line(points)}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
    event_dates = {item["date"] for item in events}
    for row in rows:
        key = row["date"].isoformat()
        weekly_j = None
        if weekly_cross:
            monday = row["date"] - timedelta(days=row["date"].weekday())
            weekly_j = weekly_cross.get(monday.isoformat())
        if row["J"] < 0:
            color = "#039855" if weekly_j is not None and weekly_j < 0 else "#d99a00"
            radius = 5.5 if color == "#039855" else 4
            parts.append(f'<circle cx="{x(row["date"]):.2f}" cy="{y(row["J"]):.2f}" r="{radius}" fill="{color}" stroke="#ffffff" stroke-width="1.2"><title>J={row["J"]:.1f}</title></circle>')
    parts.append('</svg>')
    return "".join(parts)


def build_weekly_kdj_svg(weeks: list[dict], x_min: date, x_max: date, height: int = 220, symbol: str = "NVDA") -> str:
    rows = [item for item in weeks if x_min <= item["date"] <= x_max]
    if not rows:
        return ""
    width = 1000
    left, right, top, bottom = 64, 20, 20, 42
    plot_w, plot_h = width - left - right, height - top - bottom
    dmin, dmax = x_min.toordinal(), x_max.toordinal()
    x = lambda value: left + (value.toordinal() - dmin) / max(1, dmax - dmin) * plot_w
    y_min, y_max = -30.0, 110.0
    y = lambda value: top + (y_max - value) / (y_max - y_min) * plot_h
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{svg_escape(symbol)} 周线 KDJ">']
    parts.append(f'<text x="{left}" y="14" font-size="13" font-weight="600" fill="#344054">周线 KDJ 9,3,3</text>')
    for tick in (0, 20, 80, 100):
        yy = y(tick)
        color = "#f79009" if tick in (0, 20) else "#d0d5dd"
        parts.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{width-right}" y2="{yy:.2f}" stroke="{color}" stroke-width="1" stroke-dasharray="4 5"/>')
        parts.append(f'<text x="{left-8}" y="{yy+4:.2f}" text-anchor="end" font-size="12" fill="#667085">{tick}</text>')
    for idx in range(6):
        value = dmin + (dmax - dmin) * idx / 5
        dt = date.fromordinal(round(value))
        xx = left + plot_w * idx / 5
        parts.append(f'<line x1="{xx:.2f}" y1="{top}" x2="{xx:.2f}" y2="{top+plot_h}" stroke="#f2f4f7" stroke-width="1"/>')
        parts.append(f'<text x="{xx:.2f}" y="{height-14}" text-anchor="middle" font-size="12" fill="#667085">{dt.month}/{dt.day}</text>')
    for key, color in (("K", "#2e90fa"), ("D", "#f79009"), ("J", "#9b79ec")):
        points = [(x(row["date"]), y(row[key])) for row in rows]
        parts.append(f'<path d="{svg_line(points)}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
    for row in rows:
        if row["J"] < 0:
            parts.append(f'<circle cx="{x(row["date"]):.2f}" cy="{y(row["J"]):.2f}" r="5" fill="#039855" stroke="#ffffff" stroke-width="1.2"><title>周J={row["J"]:.1f}</title></circle>')
    parts.append('</svg>')
    return "".join(parts)


def signal_condition(row: dict, tier: str) -> bool:
    drawdown = row["drawdown_pct"]
    if drawdown > -10:
        return False
    if tier == "attention":
        return True
    if tier == "yellow":
        return row["J"] < 0
    if tier == "green":
        return row["J"] < 0 and row["wk_J"] < 0
    raise ValueError(tier)


def backtest_tier(daily: list[dict], tier: str, start: date, target: float = 0.10, stop: float = 0.10, horizon: int = 60) -> dict:
    trades = []
    index = 0
    while index < len(daily):
        row = daily[index]
        if row["date"] < start or not signal_condition(row, tier):
            index += 1
            continue
        if index + 1 >= len(daily):
            index += 1
            continue
        entry_index = index + 1
        entry = daily[entry_index]["open"]
        target_price = entry * (1 + target)
        stop_price = entry * (1 - stop)
        outcome = "pending"
        exit_index = min(len(daily) - 1, entry_index + horizon)
        target_index = None
        stop_index = None
        max_favorable = -999.0
        max_adverse = 999.0
        for probe in range(entry_index, min(len(daily), entry_index + horizon + 1)):
            bar = daily[probe]
            max_favorable = max(max_favorable, (bar["high"] / entry - 1) * 100)
            max_adverse = min(max_adverse, (bar["low"] / entry - 1) * 100)
            hit_target = bar["high"] >= target_price
            hit_stop = bar["low"] <= stop_price
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
        exit_price = daily[exit_index]["close"]
        trades.append({
            "signal_date": row["date"].isoformat(),
            "entry_date": daily[entry_index]["date"].isoformat(),
            "entry": entry,
            "outcome": outcome,
            "exit_date": daily[exit_index]["date"].isoformat(),
            "exit": exit_price,
            "ret": (exit_price / entry - 1) * 100,
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
        "tier": tier,
        "entries": len(trades),
        "resolved": len(resolved),
        "wins": len(wins),
        "losses": len(losses),
        "timeouts": len(timeouts),
        "win_rate": len(wins) / len(resolved) * 100 if resolved else 0,
        "invalid_rate": (len(losses) + len(timeouts)) / len(resolved) * 100 if resolved else 0,
        "avg_return": sum(item["ret"] for item in resolved) / len(resolved) if resolved else 0,
        "avg_mfe": sum(item["mfe"] for item in resolved) / len(resolved) if resolved else 0,
        "worst_mae": min((item["mae"] for item in resolved), default=0),
        "trades": trades,
    }


def build_backtest(daily: list[dict], start: date) -> dict:
    result = {
        tier: backtest_tier(daily, tier, start, target=0.10, stop=0.10, horizon=60)
        for tier in ("attention", "yellow", "green")
    }
    result["period_start"] = start.isoformat()
    result["period_end"] = daily[-1]["date"].isoformat()
    return result


def money(value: float) -> str:
    return f"${value:,.2f}"


def pct(value: float) -> str:
    return f"{value:+.2f}%"


def build_dashboard(status: dict, chart_data: dict) -> str:
    status_json = json.dumps(status, ensure_ascii=False, indent=2)
    recent = status["recent_rows"]
    rule_rows = [
        ("红灯 · 等待", "未达到 10% 回撤", "继续等待"),
        ("注意", "从参考高点回撤 ≥ 10%", "跌幅条件出现"),
        ("黄灯", "回撤 ≥ 10% 且日 J < 0", "等待周 J 转负"),
        ("绿灯", "回撤 ≥ 10% 且日 J < 0 且周 J < 0", "双周期超卖机会"),
    ]

    def dot_class(name: str) -> str:
        if name.startswith("红灯"):
            return "red"
        if name == "注意":
            return "attention"
        if name == "黄灯":
            return "yellow"
        return "green"

    rules_html = "".join(
        f"<tr><td><span class='dot {dot_class(name)}'></span>{name}</td><td>{html.escape(desc)}</td><td>{html.escape(action)}</td></tr>"
        for name, desc, action in rule_rows
    )
    recent_html = "".join(
        "<tr>"
        f"<td>{row['date']}</td><td>{money(row['close'])}</td><td>{pct(row['drawdown_pct'])}</td>"
        f"<td>{row['K']:.1f}</td><td>{row['D']:.1f}</td><td>{row['J']:.1f}</td>"
        f"<td>{row['weekly_K']:.1f}</td><td>{row['weekly_D']:.1f}</td><td>{row['weekly_J']:.1f}</td>"
        "</tr>"
        for row in recent
    )
    history_rows = status.get("history_rows", [])[-10:]
    history_html = "".join(
        "<tr>"
        f"<td>{html.escape(row.get('date',''))}</td><td>{html.escape(row.get('state',''))}</td>"
        f"<td>{html.escape(row.get('price',''))}</td><td>{html.escape(row.get('drawdown_pct',''))}%</td>"
        f"<td>{html.escape(row.get('daily_J',''))}</td><td>{html.escape(row.get('weekly_J',''))}</td>"
        "</tr>"
        for row in reversed(history_rows)
    )
    if not history_html:
        history_html = "<tr><td colspan='6' class='muted'>暂无历史触发记录</td></tr>"

    chart_daily = [
        {**row, "date": date.fromisoformat(row["date"])}
        for row in chart_data.get("daily", [])
    ]
    chart_weekly = [
        {**row, "date": date.fromisoformat(row["date"]), "week_start": date.fromisoformat(row["week_start"])}
        for row in chart_data.get("weekly", [])
    ]
    events = chart_data.get("events", [])
    if chart_daily:
        x_min, x_max = chart_daily[0]["date"], chart_daily[-1]["date"]
        weekly_cross = {row["week_start"].isoformat(): row["J"] for row in chart_weekly}
        current_reference = {
            "date": date.fromisoformat(status["reference_high_date"]),
            "high": status["reference_high"],
        }
        price_svg = build_price_svg(chart_daily, events, current_reference, status["trigger_price"], status["price"])
        daily_kdj_svg = build_kdj_svg(chart_daily, events, "日线 KDJ 9,3,3", x_min, x_max, weekly_cross)
        weekly_kdj_svg = build_weekly_kdj_svg(chart_weekly, x_min, x_max)
        chart_html = f"""
  <section>
    <h3>K线与 KDJ 联动</h3>
    <div class="chart-legend">
      <span><i style="background:#d92d20"></i>上涨 K</span>
      <span><i style="background:#039855"></i>下跌 K</span>
      <span><i style="background:#2e90fa"></i>MA20 / K</span>
      <span><i style="background:#f79009"></i>MA50 / D</span>
      <span><i style="background:#9b79ec"></i>MA200 / J</span>
      <span><i class="ring" style="background:#039855"></i>双周期 J&lt;0</span>
    </div>
    <div class="chart-scroll">
      {price_svg}
      {daily_kdj_svg}
      {weekly_kdj_svg}
    </div>
  </section>
"""
    else:
        chart_html = ""

    bt = status.get("backtest", {})
    tier_labels = {"attention": "注意", "yellow": "黄灯", "green": "绿灯"}
    tier_colors = {"attention": "var(--attention)", "yellow": "var(--yellow)", "green": "var(--green)"}
    bt_cards = "".join(
        f'<div class="card"><div class="label">{tier_labels.get(tier,tier)}</div>'
        f'<div class="value" style="color:{tier_colors.get(tier,"inherit")}">{bt.get(tier,{}).get("win_rate",0):.1f}%</div>'
        f'<div class="note">有效 {bt.get(tier,{}).get("wins",0)} / 无效 {bt.get(tier,{}).get("losses",0)+bt.get(tier,{}).get("timeouts",0)} / 共 {bt.get(tier,{}).get("resolved",0)}</div></div>'
        for tier in ("attention", "yellow", "green")
    )
    green_trades = bt.get("green", {}).get("trades", [])
    green_trade_rows = "".join(
        f'<tr><td>{html.escape(item["signal_date"])}</td><td>{html.escape(item["entry_date"])}</td>'
        f'<td>{"有效" if item["outcome"]=="win" else "无效" if item["outcome"]=="loss" else "超时"}</td>'
        f'<td>{item["mae"]:.1f}%</td><td>{item["mfe"]:.1f}%</td>'
        f'<td>{item["target_days"] if item["target_days"] is not None else "-"}</td></tr>'
        for item in green_trades
    )
    if not green_trade_rows:
        green_trade_rows = "<tr><td colspan='6' class='muted'>暂无绿灯样本</td></tr>"
    backtest_html = f"""
  <section>
    <h3>5 年回测概览</h3>
    <div class="sub" style="margin:-4px 0 12px">口径：信号日收盘触发，下一交易日开盘买入；60 个交易日内先到 +10% 为有效，先触及 -10% 或到期未到 +10% 为无效。</div>
    <div class="grid" style="grid-template-columns:repeat(3,minmax(0,1fr));margin-bottom:14px">{bt_cards}</div>
    <table>
      <thead><tr><th>信号日</th><th>买入日</th><th>结果</th><th>最大浮亏</th><th>最大浮盈</th><th>到 +10% 天数</th></tr></thead>
      <tbody>{green_trade_rows}</tbody>
    </table>
  </section>
"""
    source_note = "实时行情" if status["is_realtime"] else "延迟/收盘行情"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#111318">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="NVDA信号">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icon-192.png">
<title>NVDA 10% + KDJ 策略指标</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: light-dark(#f7f8fa, #111318);
  --panel: light-dark(#ffffff, #1b1d23);
  --text: light-dark(#1a1c1f, #f5f6f7);
  --muted: light-dark(#667085, #a6acb8);
  --line: light-dark(#e4e7ec, #30343d);
  --green: #039855;
  --attention: #f79009;
  --yellow: #d99a00;
  --red: #d92d20;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; padding: 28px 18px 48px;
  background: var(--bg); color: var(--text);
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif;
}}
.wrap {{ max-width: 1080px; margin: 0 auto; }}
h1 {{ margin: 0 0 4px; font-size: 24px; letter-spacing: -.02em; }}
.sub {{ color: var(--muted); margin-bottom: 22px; }}
.status {{
  display: flex; align-items: center; justify-content: space-between; gap: 18px;
  padding: 20px 22px; margin-bottom: 18px; border-radius: 16px;
  background: {status['state_color']}; color: #fff; box-shadow: 0 8px 28px rgb(0 0 0 / 10%);
}}
.status h2 {{ margin: 0 0 3px; font-size: 22px; }}
.status p {{ margin: 0; opacity: .92; }}
.status .price {{ text-align: right; white-space: nowrap; }}
.status .price strong {{ display: block; font-size: 28px; }}
.grid {{ display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; margin-bottom: 18px; }}
.card, section {{ background: var(--panel); border: 1px solid var(--line); border-radius: 14px; }}
.card {{ padding: 15px; }}
.card .label {{ color: var(--muted); font-size: 12px; }}
.card .value {{ font-size: 21px; font-weight: 650; margin-top: 5px; }}
.card .note {{ color: var(--muted); font-size: 11px; margin-top: 4px; }}
section {{ padding: 18px; margin-top: 14px; overflow-x: auto; }}
section h3 {{ margin: 0 0 12px; font-size: 16px; }}
table {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
th, td {{ padding: 9px 8px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ color: var(--muted); font-size: 12px; font-weight: 550; }}
.muted {{ color: var(--muted); }}
.dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 7px; }}
.dot.green {{ background: var(--green); }} .dot.attention {{ background: var(--attention); }}
.dot.yellow {{ background: var(--yellow); }} .dot.red {{ background: var(--red); }}
.kdj {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; }}
.kdj div {{ border: 1px solid var(--line); border-radius: 10px; padding: 12px; }}
.kdj b {{ display: block; font-size: 20px; }}
.chart-legend {{ display: flex; flex-wrap: wrap; gap: 14px; color: var(--muted); font-size: 12px; margin-bottom: 10px; }}
.chart-legend span {{ display: inline-flex; align-items: center; gap: 5px; }}
.chart-legend i {{ display: inline-block; width: 14px; height: 3px; border-radius: 2px; }}
.chart-legend i.ring {{ width: 9px; height: 9px; border: 2px solid #fff; border-radius: 50%; }}
.chart-scroll {{ overflow-x: auto; padding-bottom: 4px; }}
.chart-scroll svg {{ display: block; min-width: 760px; width: 100%; height: auto; }}
details {{ margin-top: 16px; }}
pre {{ overflow: auto; padding: 14px; border-radius: 10px; background: light-dark(#f2f4f7,#101116); }}
footer {{ color: var(--muted); font-size: 12px; margin-top: 18px; }}
@media (max-width: 760px) {{
  body {{ padding: 18px 12px 36px; }}
  .grid {{ grid-template-columns: repeat(2, minmax(0,1fr)); }}
  .status {{ align-items: flex-start; flex-direction: column; }}
  .status .price {{ text-align: left; }}
  section {{ padding: 14px; }}
}}
@media (max-width: 480px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
  <h1>NVDA 10% + KDJ 策略指标</h1>
  <div class="sub">参考高点：最近 {status['lookback_days']} 个交易日最高价 · 数据源：Nasdaq · 更新时间：{html.escape(status['updated_at'])}</div>

  <div class="status">
    <div>
      <h2>{html.escape(status['state_label'])}</h2>
      <p>{html.escape(status['state_reason'])}</p>
    </div>
    <div class="price">
      <span>最新价格</span>
      <strong>{money(status['price'])}</strong>
      <span>{html.escape(status['date'])} · {source_note}</span>
    </div>
  </div>

  <div class="grid">
    <div class="card"><div class="label">参考高点</div><div class="value">{money(status['reference_high'])}</div><div class="note">{html.escape(status['reference_high_date'])}</div></div>
    <div class="card"><div class="label">当前回撤</div><div class="value">{pct(status['drawdown_pct'])}</div><div class="note">距离 10% 触发线 {pct(status['distance_to_trigger_pct'])}</div></div>
    <div class="card"><div class="label">10% 触发价</div><div class="value">{money(status['trigger_price'])}</div><div class="note">低于该价位进入“注意”</div></div>
    <div class="card"><div class="label">信号组合</div><div class="value">{'日J<0' if status['daily_j'] < 0 else '日J≥0'} / {'周J<0' if status['weekly_j'] < 0 else '周J≥0'}</div><div class="note">绿灯需要两者同时为负</div></div>
  </div>

  {chart_html}
  {backtest_html}

  <section>
    <h3>日线 KDJ 9,3,3</h3>
    <div class="kdj">
      <div><span class="muted">K</span><b>{status['daily_k']:.1f}</b></div>
      <div><span class="muted">D</span><b>{status['daily_d']:.1f}</b></div>
      <div><span class="muted">J</span><b style="color:{'var(--green)' if status['daily_j'] < 0 else 'inherit'}">{status['daily_j']:.1f}</b></div>
    </div>
  </section>

  <section>
    <h3>周线 KDJ 9,3,3</h3>
    <div class="kdj">
      <div><span class="muted">K</span><b>{status['weekly_k']:.1f}</b></div>
      <div><span class="muted">D</span><b>{status['weekly_d']:.1f}</b></div>
      <div><span class="muted">J</span><b style="color:{'var(--green)' if status['weekly_j'] < 0 else 'inherit'}">{status['weekly_j']:.1f}</b></div>
    </div>
    <div class="sub" style="margin:10px 0 0">当前周截至 {html.escape(status['week_date'])}；上周确认 J：{status['last_week_j']:.1f}</div>
  </section>

  <section>
    <h3>规则与状态</h3>
    <table>
      <thead><tr><th>状态</th><th>条件</th><th>含义</th></tr></thead>
      <tbody>{rules_html}</tbody>
    </table>
  </section>

  <section>
    <h3>最近 20 个交易日事实</h3>
    <table>
      <thead><tr><th>日期</th><th>收盘</th><th>距高点</th><th>日K</th><th>日D</th><th>日J</th><th>周K</th><th>周D</th><th>周J</th></tr></thead>
      <tbody>{recent_html}</tbody>
    </table>
  </section>

  <section>
    <h3>历史触发记录</h3>
    <table>
      <thead><tr><th>日期</th><th>状态</th><th>价格</th><th>回撤</th><th>日J</th><th>周J</th></tr></thead>
      <tbody>{history_html}</tbody>
    </table>
  </section>

  <details>
    <summary>查看原始状态数据</summary>
    <pre>{html.escape(status_json)}</pre>
  </details>

  <footer>提示：指标只做事实状态识别，不构成投资建议。涨跌停、跳空、数据延迟与强平规则都可能改变实际结果。</footer>
</div>
<script>
if ("serviceWorker" in navigator) navigator.serviceWorker.register("./sw.js");
const isStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
if (isStandalone) setInterval(() => window.location.reload(), 300000);
</script>
</body>
</html>
"""


def compute_status(lookback_days: int = LOOKBACK_DAYS) -> dict:
    today = date.today()
    history = fetch_history(today - timedelta(days=2600), today)
    quote = fetch_quote()
    history = append_quote_bar(history, quote)
    if not history:
        raise RuntimeError("No historical data returned")
    daily = add_moving_averages(kdj(history))
    weeks = weekly_bars(daily)
    weeks_kdj = kdj(weeks)
    week_by_start = {week["week_start"]: week for week in weeks_kdj}
    for index, row in enumerate(daily):
        week = week_by_start[row["date"] - timedelta(days=row["date"].weekday())]
        row["wk_K"], row["wk_D"], row["wk_J"] = week["K"], week["D"], week["J"]
        rolling = daily[max(0, index - 59): index + 1]
        reference_row = max(rolling, key=lambda item: item["high"])
        row["reference_high"] = reference_row["high"]
        row["reference_high_date"] = reference_row["date"].isoformat()
        row["drawdown_pct"] = (row["close"] / reference_row["high"] - 1) * 100

    backtest_start = today - timedelta(days=365 * 5 + 2)
    backtest = build_backtest(daily, backtest_start)
    current_week_start = today - timedelta(days=today.weekday())
    current_week = next((w for w in reversed(weeks_kdj) if w["week_start"] == current_week_start), weeks_kdj[-1])
    last_week = next((w for w in reversed(weeks_kdj) if w["week_start"] < current_week["week_start"]), None)

    latest = daily[-1]
    lookback = daily[-lookback_days:]
    reference = max(lookback, key=lambda row: row["high"])
    price = latest["close"]
    drawdown = (price / reference["high"] - 1) * 100
    trigger_price = reference["high"] * 0.90
    distance = (price / trigger_price - 1) * 100
    state = get_state(drawdown, latest["J"], current_week["J"])
    recent_rows = []
    for row in daily[-20:]:
        week_start = row["date"] - timedelta(days=row["date"].weekday())
        week = next((w for w in weeks_kdj if w["week_start"] == week_start), current_week)
        recent_rows.append({
            "date": row["date"].isoformat(),
            "close": row["close"],
            "drawdown_pct": (row["close"] / reference["high"] - 1) * 100,
            "K": row["K"], "D": row["D"], "J": row["J"],
            "weekly_K": week["K"], "weekly_D": week["D"], "weekly_J": week["J"],
        })
    history_events = build_history_events(daily, weeks_kdj, lookback_days)
    chart_data = {
        "daily": [
            {
                "date": row["date"].isoformat(),
                "open": row["open"], "high": row["high"], "low": row["low"], "close": row["close"],
                "volume": row["volume"], "K": row["K"], "D": row["D"], "J": row["J"],
                "ma20": row.get("ma20"), "ma50": row.get("ma50"), "ma200": row.get("ma200"),
            }
            for row in daily[-120:]
        ],
        "weekly": [
            {
                "date": row["date"].isoformat(),
                "week_start": row["week_start"].isoformat(),
                "K": row["K"], "D": row["D"], "J": row["J"],
            }
            for row in weeks_kdj[-30:]
        ],
        "events": history_events,
    }
    return {
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
        "distance_to_trigger_pct": distance,
        "daily_k": latest["K"],
        "daily_d": latest["D"],
        "daily_j": latest["J"],
        "weekly_k": current_week["K"],
        "weekly_d": current_week["D"],
        "weekly_j": current_week["J"],
        "week_date": current_week["date"].isoformat(),
        "last_week_j": last_week["J"] if last_week else float("nan"),
        "state_code": state["code"],
        "state_label": state["label"],
        "state_color": state["color"],
        "state_reason": state["reason"],
        "recent_rows": recent_rows,
        "history_rows": history_events,
        "backtest": backtest,
        "chart_data": chart_data,
    }


def atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def run_once(lookback_days: int) -> dict:
    status = compute_status(lookback_days)
    chart_data = status.pop("chart_data", {})
    write_history(status.get("history_rows", []))
    atomic_write_text(STATUS_PATH, json.dumps(status, ensure_ascii=False, indent=2))
    atomic_write_text(DASHBOARD_PATH, build_dashboard(status, chart_data))
    print(f"{status['date']} {status['state_label']} | price={money(status['price'])} | drawdown={pct(status['drawdown_pct'])} | dailyJ={status['daily_j']:.1f} | weeklyJ={status['weekly_j']:.1f}")
    print(DASHBOARD_PATH)
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description="NVDA drawdown + KDJ signal monitor")
    parser.add_argument("--watch", action="store_true", help="keep refreshing")
    parser.add_argument("--interval", type=int, default=60, help="refresh interval in seconds")
    parser.add_argument("--lookback", type=int, default=LOOKBACK_DAYS, help="reference high lookback in trading days")
    args = parser.parse_args()
    if not args.watch:
        run_once(args.lookback)
        return
    while True:
        try:
            run_once(args.lookback)
        except Exception as exc:
            print(f"update failed: {exc}", file=sys.stderr)
        time.sleep(max(15, args.interval))


if __name__ == "__main__":
    main()
