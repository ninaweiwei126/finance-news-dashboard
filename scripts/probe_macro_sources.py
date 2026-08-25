#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测境内可用宏观数据接口（美债收益率 + VIX 等）。
用法: python3 scripts/probe_macro_sources.py
输出: 每个候选 URL 的 HTTP 状态 + 响应片段，便于确认可用源。
"""
import gzip
import io
import json
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TIMEOUT = 8

CANDIDATES = {
    "vix": [
        ("eastmoney_100.VIX", "https://push2.eastmoney.com/api/qt/stock/get?secid=100.VIX&fields=f43,f57,f58,f60,f169,f170&fltt=2",
         {"Referer": "https://quote.eastmoney.com/"}),
        ("sina_gb_vix", "https://hq.sinajs.cn/list=gb_vix",
         {"Referer": "https://finance.sina.com.cn"}),
        ("tencent_usVIX", "https://qt.gtimg.cn/q=usVIX", {}),
        ("eastmoney_100.VIX_ulist", "https://push2.eastmoney.com/api/qt/ulist.np/get?secids=100.VIX&fields=f1,f2,f3,f4,f12,f13,f14,f2,f4&fltt=2",
         {"Referer": "https://quote.eastmoney.com/"}),
    ],
    "yield": [
        ("eastmoney_100.US10Y", "https://push2.eastmoney.com/api/qt/stock/get?secid=100.US10Y&fields=f43,f57,f58,f60,f169,f170&fltt=2",
         {"Referer": "https://quote.eastmoney.com/"}),
        ("eastmoney_100.UST10Y", "https://push2.eastmoney.com/api/qt/stock/get?secid=100.UST10Y&fields=f43,f57,f58,f60,f169,f170&fltt=2",
         {"Referer": "https://quote.eastmoney.com/"}),
        ("eastmoney_100.US10YR", "https://push2.eastmoney.com/api/qt/stock/get?secid=100.US10YR&fields=f43,f57,f58,f60,f169,f170&fltt=2",
         {"Referer": "https://quote.eastmoney.com/"}),
        ("eastmoney_100.US2Y", "https://push2.eastmoney.com/api/qt/stock/get?secid=100.US2Y&fields=f43,f57,f58,f60,f169,f170&fltt=2",
         {"Referer": "https://quote.eastmoney.com/"}),
        ("eastmoney_ulist_4yields",
         "https://push2.eastmoney.com/api/qt/ulist.np/get?secids=100.US2Y,100.US5Y,100.US10Y,100.US30Y&fields=f1,f2,f3,f4,f12,f13,f14&fltt=2",
         {"Referer": "https://quote.eastmoney.com/"}),
        ("eastmoney_global_bond_ulist",
         "https://push2.eastmoney.com/api/qt/ulist.np/get?secids=100.UST10Y,100.UST30Y,100.UST2Y,100.UST5Y&fields=f1,f2,f3,f4,f12,f13,f14&fltt=2",
         {"Referer": "https://quote.eastmoney.com/"}),
        ("sina_globalbd_10y", "https://hq.sinajs.cn/list=globalbd_10y",
         {"Referer": "https://finance.sina.com.cn"}),
        ("sina_globalbd_us10y", "https://hq.sinajs.cn/list=globalbd_us10y",
         {"Referer": "https://finance.sina.com.cn"}),
        ("tencent_us10Y", "https://qt.gtimg.cn/q=us10Y", {}),
        ("tencent_zt_10y", "https://qt.gtimg.cn/q=zt10Y", {}),
    ],
}


def probe(url, headers):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **headers})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                raw = gzip.decompress(raw)
            text = raw.decode("utf-8", errors="replace")[:400]
            return resp.status, text
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:150]}"


def main():
    for group, items in CANDIDATES.items():
        print(f"\n===== {group} =====")
        for name, url, headers in items:
            status, text = probe(url, headers)
            print(f"\n--- {name} ---")
            print(f"  status: {status}")
            print(f"  body: {text!r}")


if __name__ == "__main__":
    main()
