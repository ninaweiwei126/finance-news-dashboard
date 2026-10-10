#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import multi_signal_monitor as engine

DOCS = ROOT / "docs"
engine.SYMBOLS = [
    {"symbol": "NVDA", "name": "NVIDIA", "asset": "stocks"},
    {"symbol": "GOOGL", "name": "Google", "asset": "stocks", "lookback": 252},
]
engine.DASHBOARD = DOCS / "nvda-googl-dashboard.html"
engine.STATUS_JSON = DOCS / "nvda_googl_status.json"
engine.BACKTEST_CSV = DOCS / "nvda_googl_5y_backtest_trades.csv"
engine.APP_TITLE = "NVDA + GOOGL 每日信号"
engine.APP_SHORT_TITLE = "NVDA/GOOGL"
engine.APP_SUBTITLE = "NVDA 通用 10% · GOOGL 20% 大调整"
engine.APP_FOOTER = "NVDA 使用 10% 回撤规则；GOOGL 使用 20% + MA200 + 放量规则。数据源 Nasdaq，不构成投资建议。"
engine.MANIFEST_FILE = "nvda-googl-manifest.webmanifest"
engine.SW_FILE = "nvda-googl-sw.js"
engine.run_once()
