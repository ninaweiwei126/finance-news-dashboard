# -*- coding: utf-8 -*-
"""TradingView：行情（scanner API，用于跨源核实行情）。
无公开新闻 API。国内网络常不可达；单次 POST、失败快速跳过。
"""

import time

from collector.common import http_post_json, fetch_with_status

NAME = "tradingview"

SCAN_URL = "https://scanner.tradingview.com/{region}/scan"
REQ_TIMEOUT = 10
REQ_RETRIES = 0

_REGIONS = {"us": "america", "hk": "asia", "cn": "china"}


def _tv_symbol(market, symbol):
    if market == "us":
        nasdaq = {"AAPL", "GOOGL", "META", "AMZN", "NVDA", "TSLA", "MSFT", "NFLX", "AVGO", "INTC"}
        return f"NASDAQ:{symbol}" if symbol in nasdaq else f"NYSE:{symbol}"
    if market == "hk":
        return f"HKEX:{symbol.split('.')[0].zfill(4)}"
    if market == "cn":
        code = symbol.split(".")[0]
        return f"SSE:{code}" if symbol.endswith("SS") else f"SZSE:{code}"
    return symbol


def fetch_quotes(symbols, deadline=None):
    out = []
    by_region = {}
    for item in symbols:
        region = _REGIONS.get(item.get("market", "us"), "america")
        by_region.setdefault(region, []).append(item)
    for region, items in by_region.items():
        if deadline and time.monotonic() > deadline:
            break
        tickers = [_tv_symbol(i["market"], i["symbol"]) for i in items]
        payload = {
            "symbols": {"tickers": tickers, "query": {"types": []}},
            "columns": ["name", "close", "change", "change_abs", "description"],
        }
        try:
            data = http_post_json(SCAN_URL.format(region=region), payload,
                                  timeout=REQ_TIMEOUT, retries=REQ_RETRIES)
        except Exception:
            continue
        for row in (data.get("data") or []):
            vals = row.get("d", [])
            if len(vals) < 4 or vals[1] is None:
                continue
            out.append({
                "symbol": (row.get("s", "") or "").split(":")[-1],
                "price": vals[1],
                "change": vals[3],
                "change_pct": vals[2],
                "source": NAME,
            })
    return out


def collect_all(symbols, deadline=None):
    result = {"quotes": [], "news": [], "flash": []}
    ok, v = fetch_with_status(NAME, lambda: fetch_quotes(symbols, deadline))
    if ok:
        result["quotes"] = v
    return result
