# -*- coding: utf-8 -*-
"""新浪财经行情（hq.sinajs.cn）：单请求全量、国内稳定，作为交叉核实源。
响应为 GBK 编码；不同市场字段格式不同，按前缀解析。
"""

from collector.common import http_get_bytes, fetch_with_status

NAME = "sina"

API = "https://hq.sinajs.cn/list={codes}"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}

# watchlist symbol -> 新浪代码
INDEX_CODES = {
    "000001.SS": "sh000001",   # 上证指数
    "399001.SZ": "sz399001",   # 深证成指
    "399006.SZ": "sz399006",   # 创业板指
    "^HSI": "hkHSI",           # 恒生指数
    "^HSCE": "hkHSCEI",        # 国企指数
    "^NDX": "gb_ndx",          # 纳斯达克100
    "^GSPC": "gb_inx",         # 标普500
    "^DJI": "gb_dji",          # 道琼斯
}


def _to_sina(market, symbol):
    if market == "us":
        return f"gb_{symbol.lower()}"
    if market == "hk":
        return f"hk{symbol.split('.')[0].zfill(5)}"
    if market == "cn":
        code = symbol.split(".")[0]
        return f"sh{code}" if symbol.endswith("SS") else f"sz{code}"
    return symbol


def _to_num(v):
    try:
        f = float(v)
        return f if f != 0 else None
    except (ValueError, TypeError):
        return None


def _parse_cn(parts):
    """A股/国内指数：名称,今开,昨收,现价,最高,最低,...,成交量(股),成交额,...,日期,时间"""
    price = _to_num(parts[3])
    if price is None:
        return None
    return {
        "name_cn": parts[0],
        "price": price,
        "open": _to_num(parts[1]),
        "prev_close": _to_num(parts[2]),
        "high": _to_num(parts[4]),
        "low": _to_num(parts[5]),
        "volume": _to_num(parts[8]),
        "amount": _to_num(parts[9]),
        "time": (parts[30] + " " + parts[31]) if len(parts) > 31 else None,
    }


def _parse_hk(parts):
    """港股：英文名,中文名,今开,昨收,最高,最低,现价,涨跌,涨跌幅%"""
    price = _to_num(parts[6])
    if price is None:
        return None
    prev = _to_num(parts[3])
    return {
        "name_cn": parts[1],
        "price": price,
        "open": _to_num(parts[2]),
        "prev_close": prev,
        "high": _to_num(parts[4]),
        "low": _to_num(parts[5]),
        "change": _to_num(parts[7]),
        "change_pct": _to_num(parts[8]),
        "volume": _to_num(parts[11]) if len(parts) > 11 else None,
        "time": (parts[17] + " " + parts[18]) if len(parts) > 18 else None,
    }


def _parse_us(parts):
    """美股/美股指数：名称,价格,涨跌幅%,时间,涨跌额,今开,最高,最低,...,成交量"""
    price = _to_num(parts[1])
    if price is None:
        return None
    prev = None
    if parts[4] and price:
        try:
            prev = price - float(parts[4])
        except ValueError:
            prev = None
    return {
        "name_cn": parts[0],
        "price": price,
        "change": _to_num(parts[4]),
        "change_pct": _to_num(parts[2]),
        "prev_close": prev,
        "open": _to_num(parts[5]),
        "high": _to_num(parts[6]),
        "low": _to_num(parts[7]),
        "volume": _to_num(parts[10]) if len(parts) > 10 else None,
        "time": parts[3],
    }


def fetch_quotes(defs):
    if not defs:
        return []
    codes, mapping = [], []
    for d in defs:
        tc = INDEX_CODES.get(d["symbol"]) if d.get("is_index") else _to_sina(d["market"], d["symbol"])
        if tc:
            codes.append(tc)
            mapping.append((tc, d))
    raw = http_get_bytes(API.format(codes=",".join(codes)),
                         headers=HEADERS, timeout=12, retries=1).decode("gbk", errors="replace")
    by_code = {}
    for line in raw.split(";"):
        line = line.strip()
        if not line.startswith("var hq_str_") or "=" not in line:
            continue
        key, _, payload = line.partition("=")
        code = key[len("var hq_str_"):]
        parts = payload.strip().strip('"').split(",")
        if not parts or not parts[0]:
            continue
        if code.startswith("gb_"):
            parsed = _parse_us(parts)
        elif code.startswith("hk"):
            parsed = _parse_hk(parts)
        else:
            parsed = _parse_cn(parts)
        if parsed:
            parsed["symbol"] = code
            by_code[code] = parsed
    out = []
    for tc, d in mapping:
        p = by_code.get(tc)
        if not p:
            continue
        p = dict(p)
        p["secid"] = d["secid"]
        p["source"] = NAME
        out.append(p)
    return out


def collect_all(defs):
    result = {"quotes": [], "news": [], "flash": []}
    ok, v = fetch_with_status(NAME, lambda: fetch_quotes(defs))
    if ok:
        result["quotes"] = v
    return result
