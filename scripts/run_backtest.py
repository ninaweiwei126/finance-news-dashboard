#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行回测：逐日信号 -> 模拟交易 -> 输出 data/backtest/latest.json。
用法: python3 scripts/run_backtest.py
"""
import functools
import json
import os
import sys

print = functools.partial(print, flush=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backtest.engine import run_backtest, save_backtest  # noqa: E402


def main():
    report = run_backtest()
    latest, day_path = save_backtest(report)
    print(">> 回测完成")
    print(f">> 已生成: {latest}")
    print(f">> 已生成: {day_path}")
    print()
    for h in report["holdings"]:
        if not h.get("valid"):
            print(f"{h['symbol']}: {h.get('note')}")
            continue
        s, bh = h["strategy"], h["buy_hold"]
        print(f"== {h['symbol']} {h.get('name_cn')}（{h['period']}）")
        print(f"   策略: 总收益 {s['total_return_pct']}% | 年化 {s['cagr_pct']}% | "
              f"Sharpe {s['sharpe']} | 最大回撤 {s['max_drawdown_pct']}% | 换手 {s['trades']} 次")
        print(f"   买入持有: 总收益 {bh['total_return_pct']}% | 年化 {bh['cagr_pct']}% | "
              f"最大回撤 {bh['max_drawdown_pct']}%")
        print(f"   超额(pp): {h['vs_buy_hold_pp']}")
        print("   信号命中率:", json.dumps(h["signal_stats"], ensure_ascii=False))
        print("   成本敏感性:", json.dumps(h["cost_sensitivity"], ensure_ascii=False))
        if h.get("sample_note"):
            print("   ⚠", h["sample_note"])


if __name__ == "__main__":
    main()
