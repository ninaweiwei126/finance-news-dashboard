# -*- coding: utf-8 -*-
"""新闻采集编排：多源采集 -> 去重 -> 关联观察清单标的。
带整体时间预算；不可达的源快速跳过。"""

import re
import time
from datetime import datetime

from collector.sources import eastmoney, investing, yahoo

NEWS_BUDGET = 60  # 秒


def _normalize_title(title):
    return re.sub(r"[\W_]+", "", title or "").lower()


def _parse_time(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


MACRO_KEYWORDS = [
    "美联储", "央行", "加息", "降息", "通胀", "CPI", "PPI", "PMI",
    "GDP", "非农", "失业", "利率", "美债", "国债", "收益率",
    "美股", "港股", "A股", "上证", "创业板", "恒生", "纳指", "标普", "道指",
    "牛市", "熊市", "反弹", "大跌", "大涨", "财报", "业绩",
    "英伟达", "苹果", "微软", "特斯拉", "腾讯", "阿里", "中概", "半导体", "AI",
    "关税", "制裁", "油价", "黄金", "美元", "人民币", "汇率",
]


def collect_news(watchlist):
    kw_map = {}
    for market, rows in watchlist["stocks"].items():
        for r in rows:
            for kw in (r.get("name_cn"), r.get("name_en")):
                if kw:
                    kw_map.setdefault(str(kw).lower(), r["symbol"])
    for r in watchlist.get("indices", []):
        for kw in (r.get("name_cn"), r.get("name_en")):
            if kw:
                kw_map.setdefault(str(kw).lower(), r["symbol"])

    secids = [r["secid"] for rows in watchlist["stocks"].values() for r in rows]
    deadline = time.monotonic() + NEWS_BUDGET

    em = eastmoney.collect_all(secids)
    inv = investing.collect_all()
    # yahoo 行情不需要（避免重复探测开销），仅尝试新闻
    yq = yahoo.collect_all([], deadline=deadline, news_query="stock market")
    yq.setdefault("news", [])

    raw_items = em.get("news", []) + em.get("flash", []) + inv.get("news", []) + yq.get("news", [])
    status = {
        "eastmoney": _status(em),
        "investing": _status(inv),
        "yahoo": _status(yq),
    }

    seen = {}
    items = []
    for it in raw_items:
        title = (it.get("title") or "").strip()
        if not title or len(title) < 8:
            continue
        key = _normalize_title(title)
        if not key or key in seen:
            continue
        seen[key] = True
        related = _find_related(title, it.get("summary") or "", kw_map)
        it["related_symbols"] = related
        it["related_names"] = [_name_for(kw_map, s) for s in related]
        it["_dt"] = _parse_time(it.get("time"))
        items.append(it)
    return {"items": items, "status": status}


def _name_for(kw_map, symbol):
    for kw, sym in kw_map.items():
        if sym == symbol:
            return kw
    return symbol


def _find_related(title, summary, kw_map):
    text = (title + " " + summary).lower()
    found = set()
    for kw, sym in kw_map.items():
        if kw in text:
            found.add(sym)
    return sorted(found)


def _status(res):
    ok = bool(res.get("quotes") or res.get("news") or res.get("flash"))
    err = None
    for k in ("quotes", "news", "flash"):
        v = res.get(k)
        if isinstance(v, dict) and v.get("error"):
            err = v["error"]
    return {"ok": ok, "error": err}
