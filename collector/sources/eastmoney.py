# -*- coding: utf-8 -*-
"""东方财富：行情（单只接口，交叉核实）+ 新闻 + 7x24 快讯。"""

import time

from collector.common import http_get_json, fetch_with_status

NAME = "eastmoney"

QUOTE_API = "https://push2.eastmoney.com/api/qt/stock/get"
QUOTE_FIELDS = "f43,f57,f58,f60,f169,f170,f44,f45,f46,f47,f48,f162,f116,f117"
# f43 最新价 / f57 代码 / f58 名称 / f60 昨收 / f169 涨跌额 / f170 涨跌幅%
# f44 最高 / f45 最低 / f46 今开 / f47 成交量 / f48 成交额 / f162 PE(TTM) / f116 总市值 / f117 流通市值

NEWS_API = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
FLASH_API = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"

NEWS_COLUMNS = [345, 346]
NEWS_FIELDS = "code,showTime,title,summary,column,source"
FLASH_FIELDS = "code,showTime,title,summary,column,source"

REQ_DELAY = 0.25    # 单只请求间隔（秒），避免被限流
REQ_TIMEOUT = 6     # 单只请求超时（秒）
CONSEC_FAIL_MAX = 5 # 连续失败达到该次数即中止（防止被限流后长时间空转）
PER_SYMBOL_MAX = 63


def _get_json(url, params, timeout=8, retries=1):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return http_get_json(f"{url}?{qs}",
                         headers={"Referer": "https://finance.eastmoney.com/"},
                         timeout=timeout, retries=retries)


def fetch_quotes(secids):
    """逐只拉取行情（东财批量接口不稳定，单只接口稳定）。
    自动限速；失败跳过，不中断整体。"""
    out = []
    consec_fail = 0
    for i, secid in enumerate(secids[:PER_SYMBOL_MAX]):
        try:
            data = _get_json(QUOTE_API, {
                "secid": secid, "fields": QUOTE_FIELDS, "fltt": 2,
            }, timeout=REQ_TIMEOUT, retries=0)
            r = data.get("data") or {}
            if not r.get("f57"):
                continue
            consec_fail = 0
            out.append({
                "secid": secid,
                "symbol": str(r.get("f57") or ""),
                "name_cn": r.get("f58"),
                "price": r.get("f43"),
                "prev_close": r.get("f60"),
                "change": r.get("f169"),
                "change_pct": r.get("f170"),
                "high": r.get("f44"),
                "low": r.get("f45"),
                "open": r.get("f46"),
                "volume": r.get("f47"),
                "amount": r.get("f48"),
                "pe": r.get("f162"),
                "mkt_cap": r.get("f116"),
                "float_cap": r.get("f117"),
                "source": NAME,
            })
        except Exception:
            consec_fail += 1
            if consec_fail >= CONSEC_FAIL_MAX:
                break
            continue
        if i < len(secids) - 1:
            time.sleep(REQ_DELAY)
    return out


def _parse_news_item(r, url_tpl):
    title = (r.get("title") or "").strip()
    summary = (r.get("summary") or "").strip()
    code = r.get("code") or ""
    return {
        "title": title or summary[:80],
        "summary": summary,
        "time": r.get("showTime"),
        "source": NAME,
        "sub_source": r.get("source") or "东方财富",
        "url": url_tpl.format(code=code) if code else None,
    }


def fetch_news(limit_per_column=10):
    items = []
    for col in NEWS_COLUMNS:
        try:
            data = _get_json(NEWS_API, {
                "client": "web", "biz": "web_news_col", "column": col, "order": 1,
                "needInteractData": 0, "page_index": 1, "page_size": limit_per_column,
                "req_trace": 1, "fields": NEWS_FIELDS,
            })
            for r in (data.get("data") or {}).get("list") or []:
                items.append(_parse_news_item(r, "https://finance.eastmoney.com/a/{code}.html"))
        except Exception:
            continue
    return items


def fetch_flash(page_size=40):
    data = _get_json(FLASH_API, {
        "client": "web", "biz": "web_724", "fastColumn": 102,
        "sortEnd": "", "pageSize": page_size, "req_trace": 1, "fields": FLASH_FIELDS,
    })
    items = []
    for r in (data.get("data") or {}).get("fastNewsList") or []:
        items.append(_parse_news_item(r, "https://finance.eastmoney.com/a/{code}.html"))
    return items


def collect_all(secids):
    result = {"quotes": [], "news": [], "flash": []}
    ok_q, v_q = fetch_with_status(NAME, lambda: fetch_quotes(secids))
    if ok_q:
        result["quotes"] = v_q
    ok_n, v_n = fetch_with_status(NAME, lambda: fetch_news())
    if ok_n:
        result["news"] = v_n
    ok_f, v_f = fetch_with_status(NAME, lambda: fetch_flash())
    if ok_f:
        result["flash"] = v_f
    return result
