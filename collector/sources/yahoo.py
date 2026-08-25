# -*- coding: utf-8 -*-
"""雅虎财经：行情 + 新闻。
注意：国内网络通常被拦截（403/429）。带"连通性探测 + 失败快速跳过"，
在不可达环境下秒级降级，不影响主源。
"""

import re
import time
import urllib.request
from datetime import datetime, timezone

from collector.common import http_get, http_get_json, fetch_with_status, USER_AGENT

NAME = "yahoo"

CHART_API = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d"
SEARCH_API = "https://query1.finance.yahoo.com/v1/finance/search?q={q}&newsCount={n}"
PROBE_TIMEOUT = 5      # 连通性探测超时（短）
REQ_TIMEOUT = 8        # 正式请求超时

_cookie_jar = None
_cookie_ts = 0.0
_BLOCKED = None        # None=未探测 True=被拦截 False=可用


def _get_cookies():
    global _cookie_jar, _cookie_ts
    now = time.time()
    if _cookie_jar and now - _cookie_ts < 3600:
        return _cookie_jar
    try:
        req = urllib.request.Request("https://fc.yahoo.com", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
            jar = {}
            for c in resp.headers.get_all("Set-Cookie") or []:
                m = re.match(r"\s*([^=;]+)=([^;]*)", c)
                if m:
                    jar[m.group(1)] = m.group(2)
            _cookie_jar = jar
            _cookie_ts = now
            return jar
    except Exception:
        return {}


def _headers():
    cookies = _get_cookies()
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    return {"User-Agent": USER_AGENT, "Cookie": cookie_str}


def _probe():
    """快速连通性探测：一次请求决定是否整体跳过。"""
    global _BLOCKED
    if _BLOCKED is not None:
        return _BLOCKED
    try:
        http_get_json(
            CHART_API.format(sym="AAPL"), headers=_headers(),
            timeout=PROBE_TIMEOUT, retries=0)
        _BLOCKED = False
    except Exception:
        _BLOCKED = True
    return _BLOCKED


def _to_symbol(sym):
    s = str(sym).upper()
    if "." in s:
        left, right = s.split(".", 1)
        if left.isdigit() and right == "SS":
            return left + ".SS"
        if left.isdigit() and right == "SZ":
            return left + ".SZ"
        if left.isdigit() and right == "HK":
            return left + ".HK"
        if right == "GSPC":
            return "%5EGSPC"
        if right == "DJI":
            return "%5EDJI"
        if right == "HSI":
            return "%5EHSI"
        if right == "HSCE":
            return "%5EHSCE"
        if right == "NDX":
            return "%5ENDX"
        return left + "." + right
    return s


def fetch_quote(symbol, secid=None):
    sym = _to_symbol(symbol)
    data = http_get_json(CHART_API.format(sym=sym), headers=_headers(),
                         timeout=REQ_TIMEOUT, retries=0)
    res = data.get("chart", {}).get("result")
    if not res:
        return None
    r = res[0]
    meta = r.get("meta", {})
    close = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if close is None or prev in (None, 0):
        return None
    change = close - prev
    pct = round(change / prev * 100, 2)
    return {
        "secid": secid,
        "symbol": sym,
        "price": round(close, 4),
        "change": round(change, 4),
        "change_pct": round(pct, 4),
        "time": _fmt_ts(meta.get("regularMarketTime")),
        "source": NAME,
    }


def _fmt_ts(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def fetch_quotes(symbols, deadline=None):
    """批量行情。deadline: time.monotonic() 截止时间，超时立即停止。"""
    if _probe():
        return []
    out = []
    for item in symbols:
        if deadline and time.monotonic() > deadline:
            break
        try:
            q = fetch_quote(item["symbol"], item.get("secid"))
            if q:
                out.append(q)
        except Exception:
            continue
    return out


def fetch_news(query="stock market", count=15):
    if _probe():
        return []
    try:
        data = http_get_json(SEARCH_API.format(q=query, n=count),
                             headers=_headers(), timeout=REQ_TIMEOUT, retries=0)
    except Exception:
        return []
    out = []
    for n in data.get("news", []):
        title = (n.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "title": title,
            "summary": (n.get("summary") or "")[:300],
            "time": _fmt_ts(n.get("providerPublishTime")),
            "source": NAME,
            "sub_source": (n.get("publisher") or "Yahoo Finance"),
            "url": n.get("link"),
        })
    return out


def collect_all(symbols, deadline=None, news_query="stock market"):
    result = {"quotes": [], "news": [], "flash": []}
    ok_q, v_q = fetch_with_status(NAME, lambda: fetch_quotes(symbols, deadline))
    if ok_q:
        result["quotes"] = v_q
    ok_n, v_n = fetch_with_status(NAME, lambda: fetch_news(news_query))
    if ok_n:
        result["news"] = v_n
    return result
