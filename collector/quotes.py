# -*- coding: utf-8 -*-
"""行情采集编排：多源采集 -> 按标的合并 -> 输出统一结构。
主源：腾讯证券（单请求全量、稳定）；交叉核实：东方财富、雅虎、TradingView。
带整体时间预算；不可达的源快速跳过。"""

import time

from collector.sources import eastmoney, tencent, sina, yahoo, tradingview

QUOTES_BUDGET = 150  # 秒


def _all_stock_defs(watchlist):
    out = []
    for market, rows in watchlist["stocks"].items():
        for r in rows:
            out.append({
                "secid": r["secid"], "symbol": r["symbol"], "name_cn": r["name_cn"],
                "name_en": r["name_en"], "market": market, "currency": r["currency"],
                "tags": r.get("tags", []),
            })
    return out


def _all_index_defs(watchlist):
    out = []
    for r in watchlist.get("indices", []):
        out.append({
            "secid": r["secid"], "symbol": r["symbol"], "name_cn": r["name_cn"],
            "name_en": r["name_en"], "market": r["market"], "currency": r.get("currency", ""),
            "tags": ["指数"], "is_index": True,
        })
    return out


def _merge_quote(defn, sources):
    rec = dict(defn)
    rec["quotes"] = {}
    rec["sources_ok"] = []
    for sq in sources:
        rec["quotes"][sq["source"]] = sq
        rec["sources_ok"].append(sq["source"])
    if not rec["quotes"]:
        return None
    primary = (rec["quotes"].get("tencent")
               or rec["quotes"].get("sina")
               or rec["quotes"].get("eastmoney")
               or rec["quotes"].get("yahoo")
               or rec["quotes"].get("tradingview"))
    rec["primary_source"] = primary["source"]
    for k in ("price", "change", "change_pct", "high", "low", "open",
              "prev_close", "volume", "amount", "turnover", "pe", "mkt_cap",
              "time"):
        v = primary.get(k)
        if v is not None:
            rec[k] = v
    return rec


def _norm_symbol(s):
    return s.replace(":", "").upper().split(".")[0]


def collect_quotes(watchlist):
    stocks = _all_stock_defs(watchlist)
    indices = _all_index_defs(watchlist)
    all_defs = stocks + indices
    stock_secids = [d["secid"] for d in stocks]
    deadline = time.monotonic() + QUOTES_BUDGET

    status = {}

    # 主源：腾讯（一次请求全量）
    tq = tencent.collect_all(all_defs)
    status["tencent"] = _status_from(tq, "tencent")

    # 交叉核实：新浪（稳定）
    sq = sina.collect_all(all_defs)
    status["sina"] = _status_from(sq, "sina")

    # 交叉核实：东方财富（单只接口，限速）
    eq = eastmoney.collect_all(stock_secids + [d["secid"] for d in indices])
    status["eastmoney"] = _status_from(eq, "eastmoney")

    # 交叉核实：雅虎 / TradingView（海外/代理可用）
    yq = yahoo.collect_all(all_defs, deadline=deadline)
    status["yahoo"] = _status_from(yq, "yahoo")
    tv = tradingview.collect_all(stocks, deadline=deadline)
    status["tradingview"] = _status_from(tv, "tradingview")

    tencent_by_secid = {q["secid"]: q for q in tq["quotes"]}
    sina_by_secid = {q["secid"]: q for q in sq["quotes"]}
    em_by_secid = {q["secid"]: q for q in eq["quotes"]}
    yahoo_by_sym = {_norm_symbol(q["symbol"]): q for q in yq["quotes"]}
    tv_by_sym = {_norm_symbol(q["symbol"]): q for q in tv["quotes"]}

    merged = []
    for d in all_defs:
        sources = []
        if d["secid"] in tencent_by_secid:
            sources.append(tencent_by_secid[d["secid"]])
        if d["secid"] in sina_by_secid:
            sources.append(sina_by_secid[d["secid"]])
        if d["secid"] in em_by_secid:
            sources.append(em_by_secid[d["secid"]])
        core = _norm_symbol(d["symbol"])
        if core in yahoo_by_sym:
            sources.append(yahoo_by_sym[core])
        if core in tv_by_sym:
            sources.append(tv_by_sym[core])
        rec = _merge_quote(d, sources)
        if rec:
            merged.append(rec)

    return {"quotes": merged, "status": status}


def _status_from(res, name):
    if isinstance(res, dict) and res.get("error"):
        return {"ok": False, "error": res["error"]}
    ok = bool(res.get("quotes") or res.get("news") or res.get("flash"))
    err = None
    for k in ("quotes", "news", "flash"):
        v = res.get(k)
        if isinstance(v, dict) and v.get("error"):
            err = v["error"]
    return {"ok": ok, "error": err}
