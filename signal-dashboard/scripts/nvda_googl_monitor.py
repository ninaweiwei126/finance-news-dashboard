#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import multi_signal_monitor as engine

BASE = Path(__file__).resolve().parent
engine.SYMBOLS = [
    {"symbol": "NVDA", "name": "NVIDIA", "asset": "stocks"},
    {"symbol": "GOOGL", "name": "Google", "asset": "stocks", "lookback": 252},
]
engine.DASHBOARD = BASE / "nvda-googl-dashboard.html"
engine.STATUS_JSON = BASE / "nvda_googl_status.json"
engine.BACKTEST_CSV = BASE / "nvda_googl_5y_backtest_trades.csv"
engine.APP_TITLE = "NVDA + GOOGL 每日信号"
engine.APP_SHORT_TITLE = "NVDA/GOOGL"
engine.APP_SUBTITLE = "NVDA 通用 10% · GOOGL 20% 大调整"
engine.APP_FOOTER = "NVDA 使用 10% 回撤规则；GOOGL 使用 20% + MA200 + 放量规则。数据源 Nasdaq，不构成投资建议。"
engine.MANIFEST_FILE = "nvda-googl-manifest.webmanifest"
engine.SW_FILE = "nvda-googl-sw.js"


def main() -> None:
    parser = argparse.ArgumentParser(description="NVDA + GOOGL daily signal monitor")
    parser.add_argument("--lookback", type=int, default=engine.LOOKBACK_DAYS)
    args = parser.parse_args()
    engine.run_once(args.lookback)


if __name__ == "__main__":
    main()
