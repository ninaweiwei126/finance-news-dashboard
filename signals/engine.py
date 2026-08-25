# -*- coding: utf-8 -*-
"""信号计算编排：加载历史 -> 计算各持仓信号 -> 输出 data/signals/。"""

import json
import os
from datetime import datetime

from signals.scoring import sub_scores, macro_overlay, composite_score
from collector.macro import _load_series, _build_summary

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_CONFIG = os.path.join(ROOT, "config", "history.json")
KLINES_DIR = os.path.join(ROOT, "data", "history", "klines")
MACRO_DIR = os.path.join(ROOT, "data", "history", "macro")
SIGNALS_DIR = os.path.join(ROOT, "data", "signals")

HISTORY_NOTES = {
    "CRCL": "东财 K 线自 2025-06-05 起（约 14 个月），样本偏短",
    "SNDK": "2025-02-24 自西部数据分拆上市，样本偏短",
}


def _load_bars(symbol):
    path = os.path.join(KLINES_DIR, f"{symbol}.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("bars", [])
    except (OSError, ValueError):
        return []


def _build_macro_summary():
    t = _load_series(os.path.join(MACRO_DIR, "treasury.json"))
    v = _load_series(os.path.join(MACRO_DIR, "vix.json"))
    return _build_summary(t, v)


def compute_signals(macro_summary=None):
    """计算全部持仓信号。macro_summary 可传入 run_daily 已采集的结果，否则读历史文件。"""
    with open(HISTORY_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    holdings = [s for s in cfg.get("symbols", []) if s.get("group") == "holdings"]
    bench = next((s for s in cfg.get("symbols", []) if s.get("symbol") == "SPX"), None)
    bench_bars = _load_bars(bench["symbol"]) if bench else []

    overlay = macro_overlay(macro_summary if macro_summary is not None else _build_macro_summary())

    out_holdings = []
    for h in holdings:
        bars = _load_bars(h["symbol"])
        entry = {
            "symbol": h["symbol"], "name_cn": h.get("name_cn"),
            "bars": len(bars),
            "history_note": HISTORY_NOTES.get(h["symbol"]),
        }
        if len(bars) < 60:
            entry.update({"valid": False, "signal": "样本不足", "score": None,
                          "note": f"K 线仅 {len(bars)} 根，暂不计算"})
            out_holdings.append(entry)
            continue
        scores = sub_scores(bars, bench_bars)
        comp = composite_score(scores, overlay)
        last = bars[-1]
        entry.update({
            "valid": True,
            "date": last["date"],
            "price": last["close"],
            "change_pct": last.get("change_pct"),
            "sub_scores": {k: v for k, v in scores.items() if k != "valid"},
            "composite": comp,
            "signal": comp["signal"],
            "score": comp["adjusted"],
            "confidence": comp["confidence"],
            "action_tip": comp["action_tip"],
        })
        out_holdings.append(entry)

    latest_date = None
    for h in out_holdings:
        if h.get("date"):
            latest_date = max(latest_date, h["date"]) if latest_date else h["date"]

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": latest_date,
        "macro_overlay": overlay,
        "holdings": out_holdings,
    }


def save_signals(signals, signals_dir=SIGNALS_DIR):
    """写入 data/signals/latest.json 与按日文件。"""
    os.makedirs(signals_dir, exist_ok=True)
    latest_path = os.path.join(signals_dir, "latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)
    if signals.get("date"):
        day_path = os.path.join(signals_dir, f"{signals['date']}.json")
        with open(day_path, "w", encoding="utf-8") as f:
            json.dump(signals, f, ensure_ascii=False, indent=2)
    return latest_path
