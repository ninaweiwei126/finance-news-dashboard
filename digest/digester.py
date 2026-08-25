# -*- coding: utf-8 -*-
"""每日提炼：从已核实新闻中打分选出 Top5，按时间排序。
打分规则：关联标的命中 + 宏观相关 + 时效性 + 来源可信度。
"""

from datetime import datetime

SOURCE_WEIGHT = {
    "eastmoney": 1.0,
    "investing": 1.0,
    "yahoo": 1.0,
}
MACRO_KEYWORDS = [
    "美联储", "央行", "加息", "降息", "通胀", "CPI", "PPI", "PMI",
    "非农", "失业", "利率", "美债", "国债", "收益率", "关税", "制裁",
    "油价", "黄金", "美元", "人民币", "汇率", "财报", "业绩", "半导体",
]


def _score(item, now):
    s = 0.0
    # 时效性：越新越高（24h 内满分，超过递减）
    dt = item.get("_dt")
    if dt:
        age_h = (now - dt).total_seconds() / 3600
        if age_h < 0:
            s += 2.0
        elif age_h <= 24:
            s += 2.0 - age_h / 24
        else:
            s += max(0.0, 0.5 - (age_h - 24) / 48)
    # 关联标的
    s += min(len(item.get("related_symbols", [])) * 2.0, 6.0)
    # 宏观关键词
    text = (item.get("title", "") + " " + item.get("summary", ""))
    s += sum(1.0 for kw in MACRO_KEYWORDS if kw in text)
    # 来源权重
    s += SOURCE_WEIGHT.get(item.get("source"), 0.5)
    # 快讯（带时间戳滚动）优先
    if item.get("source") == "eastmoney" and item.get("sub_source"):
        s += 0.5
    return round(s, 2)


def build_digest(news_items, top_n=5, sort_order="asc"):
    """输入已核实新闻，输出 TopN 提炼结果（按时间排序）。
    sort_order: 'asc' 按时间先后（默认，构成当日时间线），'desc' 最新在前。
    """
    now = datetime.now()
    candidates = [it for it in news_items if it.get("verified") and it.get("_dt")]
    for it in candidates:
        it["_score"] = _score(it, now)
    candidates.sort(key=lambda x: x["_score"], reverse=True)
    top = candidates[:top_n]
    top.sort(key=lambda x: (x["_dt"] is None, x["_dt"] or datetime.min),
             reverse=(sort_order == "desc"))
    result = []
    for it in top:
        result.append({
            "rank": len(result) + 1,
            "title": it.get("title"),
            "summary": it.get("summary", "")[:500],
            "time": it.get("time"),
            "source": it.get("source"),
            "sub_source": it.get("sub_source"),
            "url": it.get("url"),
            "related_symbols": it.get("related_symbols", []),
            "related_names": it.get("related_names", []),
            "score": it.get("_score"),
            "verified": True,
        })
    return result


def market_movers(quotes, top_n=5):
    """提炼各市场涨跌幅最大的标的（用于快报的“市场表现”小节）。"""
    by_market = {}
    for q in quotes:
        if q.get("is_index") or q.get("price") is None:
            continue
        by_market.setdefault(q.get("market"), []).append(q)
    out = {}
    for market, rows in by_market.items():
        rows = sorted(rows, key=lambda x: x.get("change_pct") or 0, reverse=True)
        out[market] = {
            "top_gainers": [
                {"symbol": r["symbol"], "name_cn": r["name_cn"], "change_pct": r["change_pct"]}
                for r in rows[:top_n]
            ],
            "top_losers": [
                {"symbol": r["symbol"], "name_cn": r["name_cn"], "change_pct": r["change_pct"]}
                for r in rows[-top_n:][::-1]
            ],
        }
    return out
