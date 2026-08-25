#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日金融资讯采集主入口：
采集行情+新闻 -> 核实 -> 提炼 Top5 -> 生成 JSON 报告（data/daily + data/latest）。
用法: python3 run_daily.py [--date YYYY-MM-DD] [--out DIR]
"""
import argparse
import json
import os
import sys
import functools

print = functools.partial(print, flush=True)
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collector.quotes import collect_quotes          # noqa: E402
from collector.news import collect_news              # noqa: E402
from verify.verifier import verify_quotes, verify_news, summarize  # noqa: E402
from digest.digester import build_digest, market_movers  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
WATCHLIST = os.path.join(ROOT, "config", "watchlist.json")
DATA_DIR = os.path.join(ROOT, "data", "daily")


def load_watchlist():
    with open(WATCHLIST, "r", encoding="utf-8") as f:
        return json.load(f)


def run(day=None, out_dir=None):
    watchlist = load_watchlist()
    day = day or datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] 开始采集 {day} ...")

    # 1) 行情
    print(">> 采集行情 ...")
    quotes_res = collect_quotes(watchlist)
    quotes = verify_quotes(quotes_res["quotes"])
    print(f"   行情 {len(quotes)} 条（核实通过 {sum(1 for q in quotes if q['verified'])}）")

    # 2) 新闻
    print(">> 采集新闻 ...")
    news_res = collect_news(watchlist)
    news_items = verify_news(news_res["items"])
    print(f"   新闻 {len(news_items)} 条（核实通过 {sum(1 for n in news_items if n['verified'])}）")

    # 3) 提炼 Top5
    print(">> 提炼 Top5 ...")
    top5 = build_digest(news_items, top_n=5)
    movers = market_movers(quotes, top_n=5)
    for t in top5:
        print(f"   #{t['rank']} [{t['time']}] {t['title']}")

    # 4) 指数快照
    indices = [q for q in quotes if q.get("is_index")]

    # 5) 汇总报告
    report = {
        "date": day,
        "generated_at": now_str,
        "title": f"{day} 全球市场金融资讯日报",
        "market_overview": _index_snapshot(indices),
        "top5": top5,
        "market_movers": movers,
        "quotes": {m: _clean_list([q for q in quotes if q.get("market") == m])
                   for m in ("us", "hk", "cn")},
        "sources_status": {**quotes_res["status"], **news_res["status"]},
        "verification_stats": summarize(quotes, news_items),
        "watchlist_meta": watchlist.get("meta"),
    }

    # 6) 写文件
    out_dir = out_dir or DATA_DIR
    os.makedirs(out_dir, exist_ok=True)
    daily_path = os.path.join(out_dir, f"{day}.json")
    with open(daily_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    latest_path = os.path.join(ROOT, "data", "latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f">> 已生成: {daily_path}")
    print(f">> 已生成: {latest_path}")
    print(">> 数据源状态: " + json.dumps(report["sources_status"], ensure_ascii=False))
    return report


def _index_snapshot(indices):
    out = []
    for q in indices:
        out.append({
            "symbol": q["symbol"], "name_cn": q["name_cn"], "name_en": q.get("name_en"),
            "price": q.get("price"), "change_pct": q.get("change_pct"),
            "change": q.get("change"), "verified": q.get("verified"),
            "sources": q.get("sources_ok", []),
        })
    return out


def _clean_list(rows):
    out = []
    for q in rows:
        out.append({
            "symbol": q["symbol"], "secid": q["secid"],
            "name_cn": q["name_cn"], "name_en": q.get("name_en"),
            "market": q["market"], "currency": q.get("currency"),
            "tags": q.get("tags", []),
            "price": q.get("price"), "change": q.get("change"),
            "change_pct": q.get("change_pct"),
            "high": q.get("high"), "low": q.get("low"), "open": q.get("open"),
            "prev_close": q.get("prev_close"),
            "mkt_cap": q.get("mkt_cap"), "pe": q.get("pe"),
            "sources": q.get("sources_ok", []),
            "verified": q.get("verified"),
            "cross_checked": q.get("cross_checked", False),
            "verification_notes": q.get("verification_notes", []),
        })
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="每日金融资讯采集")
    ap.add_argument("--date", help="指定日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--out", help="输出目录（默认 data/daily）")
    args = ap.parse_args()
    run(day=args.date, out_dir=args.out)
