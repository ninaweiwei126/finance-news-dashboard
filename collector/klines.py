# -*- coding: utf-8 -*-
"""日 K 线历史采集：东方财富 kline 接口（境内可用），增量合并到 data/history/klines/。
每个标的一个 JSON：{"symbol","name","updated","bars":[{date,open,close,high,low,volume,amount,change_pct}]}
"""
import json
import os
import subprocess
from datetime import datetime
from urllib.parse import urlencode

from collector.common import http_get_json, fetch_with_status

NAME = "eastmoney_kline"

KLINE_API = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
HEADERS = {"Referer": "https://quote.eastmoney.com/"}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_DIR = os.path.join(ROOT, "data", "history", "klines")




def _fetch_kline_json(url):
    """东财对部分网络（如海外）拒绝 HTTP/1.1 请求，标准库失败时回退 curl。"""
    try:
        return http_get_json(url, headers=HEADERS, timeout=15, retries=1)
    except Exception:
        try:
            out = subprocess.run(
                ["curl", "-sS", "--compressed", "--max-time", "30",
                 "-A", "Mozilla/5.0", "-e", "https://quote.eastmoney.com/", url],
                capture_output=True, timeout=35)
            return json.loads(out.stdout.decode("utf-8", errors="replace"))
        except Exception:
            raise

def fetch_kline(secid, beg="20250101", end=None, fqt=1, klt=101):
    """拉取单个标的日 K。fqt=1 前复权；返回 {"secid","name","bars": {date: bar}}"""
    end = end or datetime.now().strftime("%Y%m%d")
    params = {
        "secid": secid, "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "klt": klt, "fqt": fqt, "beg": beg, "end": end,
    }
    url = f"{KLINE_API}?{urlencode(params)}"
    data = _fetch_kline_json(url)
    d = data.get("data") or {}
    bars = {}
    prev_close = None
    for line in d.get("klines") or []:
        p = line.split(",")
        if len(p) < 8:
            continue
        date = p[0]
        try:
            o, c, h, l = float(p[1]), float(p[2]), float(p[3]), float(p[4])
            vol, amt = float(p[5]), float(p[6])
        except ValueError:
            continue
        chg = round((c / prev_close - 1) * 100, 2) if prev_close else None
        bars[date] = {
            "date": date, "open": o, "close": c, "high": h, "low": l,
            "volume": vol, "amount": amt, "change_pct": chg,
        }
        prev_close = c
    return {"secid": secid, "name": d.get("name"), "bars": bars}


def _load_bars(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {b["date"]: b for b in data.get("bars", [])}
    except (OSError, ValueError, TypeError):
        return {}


def _save_bars(path, symbol, name, bars):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "symbol": symbol, "name": name,
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "bars": [bars[k] for k in sorted(bars)],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)


def update_history(symbols, history_dir=HISTORY_DIR):
    """按 config/history.json 增量更新各标的日 K。永不抛异常；返回每标的处理结果。"""
    os.makedirs(history_dir, exist_ok=True)
    result = {}
    for sym in symbols or []:
        symbol, secid = sym.get("symbol"), sym.get("secid")
        if not symbol or not secid:
            continue
        start = sym.get("start", "20250101")
        path = os.path.join(history_dir, f"{symbol}.json")
        ok, res = fetch_with_status(
            f"{NAME}:{symbol}",
            lambda s=secid, b=start: fetch_kline(s, beg=b))
        if not ok:
            result[symbol] = {
                "ok": False,
                "error": (res.get("error") if isinstance(res, dict) else str(res))[:200],
                "bars": 0,
            }
            continue
        bars = _load_bars(path)
        bars.update(res.get("bars", {}))
        _save_bars(path, symbol, res.get("name"), bars)
        result[symbol] = {
            "ok": True, "bars": len(bars),
            "latest": sorted(bars)[-1] if bars else None,
        }
    return result
