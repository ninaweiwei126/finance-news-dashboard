#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史数据回填：美债收益率（按年全量）+ VIX（全历史）+ 各标的日 K。
用法: python3 scripts/backfill_history.py [--from-year 2015]
"""
import argparse
import json
import os
import sys
import functools

print = functools.partial(print, flush=True)
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from collector.common import fetch_with_status          # noqa: E402
from collector.macro import (                          # noqa: E402
    fetch_treasury, fetch_vix, HISTORY_DIR,
    _load_series, _save_series, _merge_series,
)
from collector.klines import update_history, HISTORY_DIR as KLINES_DIR  # noqa: E402

HISTORY_CONFIG = os.path.join(ROOT, "config", "history.json")


def load_history_config():
    with open(HISTORY_CONFIG, encoding="utf-8") as f:
        return json.load(f)


def backfill_macro(start_year):
    print(">> 回填美债收益率 ...")
    cur_year = datetime.now().year
    merged = {}
    for year in range(start_year, cur_year + 1):
        ok, res = fetch_with_status(f"ust_{year}", lambda y=year: fetch_treasury(year=y))
        if ok and res.get("series"):
            merged = _merge_series(merged, res["series"])
            print(f"   美债 {year}: {len(res['series'])} 条")
        else:
            err = res.get("error") if isinstance(res, dict) else str(res)
            print(f"   美债 {year}: 失败 {str(err)[:120]}")
    _save_series(os.path.join(HISTORY_DIR, "treasury.json"), "us_treasury", merged)
    print(f"   已写入 {len(merged)} 个交易日 -> data/history/macro/treasury.json")

    print(">> 回填 VIX ...")
    ok, res = fetch_with_status("cboe_vix", fetch_vix)
    if ok and res.get("series"):
        _save_series(os.path.join(HISTORY_DIR, "vix.json"), "cboe", res["series"])
        print(f"   已写入 {len(res['series'])} 个交易日 -> data/history/macro/vix.json")
    else:
        print("   VIX 回填失败:", str(res)[:200])


def backfill_klines():
    print(">> 回填日 K 线 ...")
    cfg = load_history_config()
    result = update_history(cfg.get("symbols", []))
    for symbol, info in result.items():
        if info.get("ok"):
            print(f"   {symbol}: {info['bars']} 根，最新 {info['latest']}")
        else:
            print(f"   {symbol}: 失败 {info.get('error')}")


def main():
    ap = argparse.ArgumentParser(description="回填历史数据")
    ap.add_argument("--from-year", type=int, default=2015, help="美债回填起始年（默认 2015）")
    args = ap.parse_args()
    backfill_macro(args.from_year)
    backfill_klines()
    print(">> 回填完成。")


if __name__ == "__main__":
    main()
