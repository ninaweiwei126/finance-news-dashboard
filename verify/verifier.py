# -*- coding: utf-8 -*-
"""信息核实：
1) 行情：价格/涨跌幅合理性 + 多源一致性（同一标的多个数据源偏差在容忍范围内才算通过）。
2) 新闻：标题长度、时间有效性、是否重复。
每个条目附 verified 布尔值与核实说明，供前端/用户判断。
"""

from datetime import datetime, timedelta

# 多源行情一致性容忍度
PRICE_TOL = 0.01       # 价格相对偏差 1%
PCT_TOL = 1.0          # 涨跌幅绝对偏差 1 个百分点
MAX_PCT = 40.0         # 单日涨跌幅上限（超过视为异常/可能除权）
MIN_PRICE = 0.01
NEWS_MIN_TITLE = 8
NEWS_MAX_AGE_HOURS = 48


def verify_quotes(quotes):
    """核实行情列表，返回带 verified/notes 的新列表。"""
    out = []
    for q in quotes:
        notes = []
        ok = True
        price = q.get("price")
        pct = q.get("change_pct")

        # 合理性
        if price is None or price <= MIN_PRICE:
            ok = False
            notes.append(f"价格异常({price})")
        if pct is not None and abs(pct) > MAX_PCT:
            ok = False
            notes.append(f"涨跌幅异常({pct}%)")
        if q.get("change") is not None and price:
            est = q["change"] / (price - q["change"]) * 100 if (price - q["change"]) else None
            if est is not None and pct is not None and abs(est - pct) > 2.0:
                notes.append("涨跌额与涨跌幅不一致")

        # 多源一致性
        srcs = q.get("quotes", {})
        cross_checked = len(srcs) >= 2
        conflicted = False
        if cross_checked:
            prices = [v.get("price") for v in srcs.values() if v.get("price")]
            pcts = [v.get("change_pct") for v in srcs.values() if v.get("change_pct") is not None]
            if len(prices) >= 2:
                mx, mn = max(prices), min(prices)
                if mn and (mx - mn) / mn > PRICE_TOL:
                    ok = False
                    conflicted = True
                    notes.append(f"多源价格偏差{(mx-mn)/mn*100:.2f}%超过容忍")
            if len(pcts) >= 2:
                mx, mn = max(pcts), min(pcts)
                if mx - mn > PCT_TOL:
                    ok = False
                    conflicted = True
                    notes.append(f"多源涨跌幅偏差{mx-mn:.2f}pp超过容忍")
            if not conflicted:
                notes.append(f"多源一致({len(srcs)}个源)")
        else:
            notes.append(f"单一来源({q.get('primary_source')})，未交叉验证")

        q = dict(q)
        q["cross_checked"] = cross_checked
        # verified = 合理性通过 且 多源交叉验证一致（严格模式）
        q["verified"] = ok and cross_checked and not conflicted
        q["verification_notes"] = notes
        out.append(q)
    return out


def verify_news(items, now=None):
    """核实新闻列表。now 为可选 datetime（便于测试）。"""
    now = now or datetime.now()
    out = []
    for it in items:
        notes = []
        ok = True
        title = (it.get("title") or "").strip()
        if len(title) < NEWS_MIN_TITLE:
            ok = False
            notes.append("标题过短")
        dt = it.get("_dt")
        if dt is None:
            ok = False
            notes.append("时间缺失/无法解析")
        else:
            age = now - dt
            if age < -timedelta(hours=1):
                ok = False
                notes.append("时间在未来，疑似异常")
            elif age > timedelta(hours=NEWS_MAX_AGE_HOURS):
                notes.append(f"时间超过{NEWS_MAX_AGE_HOURS}h，可能非当日新闻")
        if it.get("source") == "investing" and not it.get("url"):
            notes.append("investing 条目缺少原文链接")
        it = dict(it)
        it["verified"] = ok
        it["verification_notes"] = notes
        out.append(it)
    return out


def summarize(quotes, news):
    """生成核实统计。"""
    q_ok = sum(1 for q in quotes if q.get("verified"))
    n_ok = sum(1 for n in news if n.get("verified"))
    return {
        "quotes_total": len(quotes),
        "quotes_verified": q_ok,
        "news_total": len(news),
        "news_verified": n_ok,
    }
