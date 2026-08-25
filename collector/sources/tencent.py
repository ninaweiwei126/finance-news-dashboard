# -*- coding: utf-8 -*-
"""腾讯证券行情（qt.gtimg.cn）：单请求全量、国内稳定，作为行情主源。
字段为 GBK 管道分隔，核心索引固定。
"""

from collector.common import http_get_bytes, fetch_with_status

NAME = "tencent"

API = "https://qt.gtimg.cn/q={codes}"

# 指数映射：watchlist symbol -> 腾讯代码
INDEX_CODES = {
    "000001.SS": "sh000001",   # 上证指数
    "399001.SZ": "sz399001",   # 深证成指
    "399006.SZ": "sz399006",   # 创业板指
    "^HSI": "hkHSI",           # 恒生指数
    "^HSCE": "hkHSCEI",        # 国企指数
    "^NDX": "usNDX",           # 纳斯达克100
    "^GSPC": "usINX",          # 标普500
    "^DJI": "usDJI",           # 道琼斯
}


def _to_tencent(market, symbol):
    """watchlist symbol -> 腾讯代码"""
    if market == "us":
        return f"us{symbol}"
    if market == "hk":
        return f"hk{symbol.split('.')[0].zfill(5)}"  # 港股代码 5 位
    if market == "cn":
        code = symbol.split(".")[0]
        return f"sh{code}" if symbol.endswith("SS") else f"sz{code}"
    return symbol


def _parse_line(name, payload):
    """解析单行 v_xxx="1~名称~代码~..." """
    parts = payload.split("~")
    if len(parts) < 35:
        return None
    def num(i):
        try:
            v = parts[i].strip()
            return float(v) if v else None
        except (ValueError, IndexError):
            return None
    price = num(3)
    if price is None or price <= 0:
        return None
    return {
        "symbol": name,           # 腾讯代码，如 usAAPL
        "name_cn": parts[1],
        "price": price,
        "prev_close": num(4),
        "open": num(5),
        "volume": num(6),
        "time": _norm_time(parts[30]) if len(parts) > 30 else None,
        "change": num(31),
        "change_pct": num(32),
        "high": num(33),
        "low": num(34),
        "source": NAME,
    }


def _norm_time(s):
    if not s:
        return None
    s = s.strip()
    if len(s) == 14 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}:{s[12:14]}"
    return s.replace("/", "-")


def fetch_quotes(defs):
    """defs: [{market, symbol, secid, is_index}]"""
    if not defs:
        return []
    codes = []
    mapping = []  # (tencent_code, def)
    for d in defs:
        if d.get("is_index"):
            tc = INDEX_CODES.get(d["symbol"])
        else:
            tc = _to_tencent(d["market"], d["symbol"])
        if tc:
            codes.append(tc)
            mapping.append((tc, d))
    raw = http_get_bytes(API.format(codes=",".join(codes)),
                          headers={"User-Agent": "Mozilla/5.0"}, timeout=12, retries=1
                          ).decode("gbk", errors="replace")
    by_code = {}
    for line in raw.split(";"):
        line = line.strip()
        if not line.startswith("v_") or "=" not in line:
            continue
        key, _, payload = line.partition("=")
        code = key[2:]
        payload = payload.strip().strip('"')
        parsed = _parse_line(code, payload)
        if parsed:
            by_code[code] = parsed
    out = []
    for tc, d in mapping:
        p = by_code.get(tc)
        if not p:
            continue
        p = dict(p)
        p["secid"] = d["secid"]
        out.append(p)
    return out


def collect_all(defs):
    result = {"quotes": [], "news": [], "flash": []}
    ok, v = fetch_with_status(NAME, lambda: fetch_quotes(defs))
    if ok:
        result["quotes"] = v
    return result
