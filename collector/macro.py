# -*- coding: utf-8 -*-
"""宏观数据采集：美债收益率（U.S. Treasury 官方 XML）+ VIX（Cboe 官方 CSV）。
均为官方源、提供日频历史；增量合并后写入 data/history/macro/。
"""
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from collector.common import http_get, fetch_with_status

NAME = "macro"

TREASURY_XML = ("https://home.treasury.gov/resource-center/data-chart-center/"
                "interest-rates/pages/xml?data=daily_treasury_yield_curve")
CBOE_VIX_CSV = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_DIR = os.path.join(ROOT, "data", "history", "macro")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 财政部 XML 标签 -> 短键
YIELD_TAGS = {
    "BC_1MONTH": "1M", "BC_2MONTH": "2M", "BC_3MONTH": "3M", "BC_6MONTH": "6M",
    "BC_1YEAR": "1Y", "BC_2YEAR": "2Y", "BC_3YEAR": "3Y", "BC_5YEAR": "5Y",
    "BC_7YEAR": "7Y", "BC_10YEAR": "10Y", "BC_20YEAR": "20Y", "BC_30YEAR": "30Y",
}
ATOM = "{http://www.w3.org/2005/Atom}"
DS = "{http://schemas.microsoft.com/ado/2007/08/dataservices}"
MD = "{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}"


def _to_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_treasury_xml(text):
    """解析财政部 Atom XML -> {date: {1M:.., 2Y:.., ...}}"""
    root = ET.fromstring(text)
    out = {}
    for entry in root.findall(f"{ATOM}entry"):
        props = entry.find(f"{ATOM}content/{MD}properties")
        if props is None:
            continue
        rec = {}
        for child in props:
            tag = child.tag
            if tag.startswith(DS):
                rec[tag[len(DS):]] = (child.text or "").strip()
        date = (rec.get("NEW_DATE") or "")[:10]
        if not date:
            continue
        row = {}
        for tag, key in YIELD_TAGS.items():
            v = _to_num(rec.get(tag))
            if v is not None:
                row[key] = v
        if row:
            out[date] = row
    return out


def fetch_treasury(year=None, months_back=2):
    """拉取美债收益率。
    year 指定则拉整年（回填用）；否则拉最近 months_back 个月（日报用）。
    返回 {"series": {date: {key: yield}}}
    """
    series = {}
    if year is not None:
        url = f"{TREASURY_XML}&field_tdr_date_value={year}"
        text = http_get(url, headers={"User-Agent": UA}, timeout=20, retries=2)
        series.update(_parse_treasury_xml(text))
        return {"series": series}

    now = datetime.now()
    for back in range(months_back):
        ym = (now - timedelta(days=back * 32)).strftime("%Y%m")
        url = f"{TREASURY_XML}&field_tdr_date_value_month={ym}"
        try:
            text = http_get(url, headers={"User-Agent": UA}, timeout=20, retries=1)
            series.update(_parse_treasury_xml(text))
        except Exception:  # noqa: BLE001 单月失败不影响其他
            continue
    return {"series": series}


def fetch_vix():
    """拉取 Cboe VIX 全历史 CSV -> {"series": {date: {open,high,low,close}}}"""
    text = http_get(CBOE_VIX_CSV, headers={"User-Agent": UA}, timeout=30, retries=2)
    series = {}
    for i, line in enumerate(text.splitlines()):
        line = line.strip()
        if i == 0 or not line:
            continue
        parts = line.split(",")
        if len(parts) < 5:
            continue
        try:
            d = datetime.strptime(parts[0].strip(), "%m/%d/%Y").strftime("%Y-%m-%d")
            close = _to_num(parts[4])
            if close is None:
                continue
            series[d] = {
                "open": _to_num(parts[1]), "high": _to_num(parts[2]),
                "low": _to_num(parts[3]), "close": close,
            }
        except ValueError:
            continue
    return {"series": series}


def _load_series(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("series", {})
    except (OSError, ValueError):
        return {}


def _save_series(path, source, series):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "series": {k: series[k] for k in sorted(series)},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)


def _merge_series(old, new):
    out = dict(old or {})
    out.update(new or {})
    return out


def _prev_record(series, date, n):
    """返回 date 往前第 n 个有记录（允许非交易日）的记录。"""
    dates = sorted(d for d in series if d < date)
    if not dates:
        return None
    return series.get(dates[-1])


def _diff_bp(cur, prev):
    """当前 vs 前值，单位基点（bp）。"""
    if not cur or not prev:
        return None
    out = {}
    for k in ("2Y", "5Y", "10Y", "30Y"):
        if cur.get(k) is not None and prev.get(k) is not None:
            out[k] = round((cur[k] - prev[k]) * 100, 1)
    return out or None


def _build_summary(t_series, v_series):
    """构建日报可用的宏观摘要（美债最新值 + 变化 + VIX）。"""
    summary = {"treasury": None, "vix": None}

    if t_series:
        dates = sorted(t_series)
        latest = dates[-1]
        cur = t_series[latest]
        prev1 = _prev_record(t_series, latest, 1)
        prev5 = _prev_record(t_series, latest, 5)
        summary["treasury"] = {
            "date": latest,
            "yields": {k: cur.get(k) for k in ("2Y", "5Y", "10Y", "30Y")},
            "change_1d_bp": _diff_bp(cur, prev1),
            "change_5d_bp": _diff_bp(cur, prev5),
        }
        if cur.get("10Y") is not None and cur.get("2Y") is not None:
            summary["treasury"]["spread_10y_2y"] = round(cur["10Y"] - cur["2Y"], 2)

    if v_series:
        dates = sorted(v_series)
        latest = dates[-1]
        cur = v_series[latest].get("close")
        prev = None
        for d in reversed(dates[:-1]):
            if v_series[d].get("close") is not None:
                prev = v_series[d]["close"]
                break
        summary["vix"] = {"date": latest, "close": cur}
        if cur is not None and prev is not None:
            summary["vix"]["change_1d"] = round(cur - prev, 2)

    return summary


def collect_macro(history_dir=HISTORY_DIR):
    """采集宏观数据并增量写盘。永不抛异常；返回摘要 + 各源状态。"""
    os.makedirs(history_dir, exist_ok=True)
    status = {}

    # 美债收益率
    t_path = os.path.join(history_dir, "treasury.json")
    t_series = _load_series(t_path)
    ok_t, tres = fetch_with_status("ust_treasury", fetch_treasury)
    status["ust_treasury"] = {"ok": ok_t, "error": None if ok_t else str(tres)[:200]}
    if ok_t:
        t_series = _merge_series(t_series, tres.get("series", {}))
        _save_series(t_path, "us_treasury", t_series)

    # VIX
    v_path = os.path.join(history_dir, "vix.json")
    v_series = _load_series(v_path)
    ok_v, vres = fetch_with_status("cboe_vix", fetch_vix)
    status["cboe_vix"] = {"ok": ok_v, "error": None if ok_v else str(vres)[:200]}
    if ok_v:
        v_series = _merge_series(v_series, vres.get("series", {}))
        _save_series(v_path, "cboe", v_series)

    summary = _build_summary(t_series, v_series)
    return {"summary": summary, "status": status}
