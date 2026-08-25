# -*- coding: utf-8 -*-
"""A股成交额追踪：上午 / 下午 / 全天 三段，每日两次快照。
数据源：新浪财经指数成交额（沪市 sh000001 / 深市 sz399001 / 创业板 sz399006）。
两市成交额 = 沪市 + 深市（与新闻口径一致）。
时间槽位：
  - morning：11:30 午盘收盘后 ~ 15:00 前（记录上午半场累计成交额）
  - close：15:00 全天收盘后（记录全天累计成交额）
  - 下午 = 全天 - 上午（两个槽位齐后自动计算）
"""

import json
import os
from datetime import datetime

from collector.sources.sina import fetch_quotes

INDEX_DEFS = [
    {"secid": "1.000001", "symbol": "000001.SS", "market": "cn", "is_index": True},  # 上证指数（沪市总量）
    {"secid": "0.399001", "symbol": "399001.SZ", "market": "cn", "is_index": True},  # 深证成指（深市总量）
    {"secid": "0.399006", "symbol": "399006.SZ", "market": "cn", "is_index": True},  # 创业板指（创业板，属深市）
]

MORNING_END = 11 * 60 + 30   # 11:30 午盘收盘
CLOSE_END = 15 * 60          # 15:00 全天收盘

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "volume")


def current_period(dt=None):
    """返回当前应记录的快照槽位：'morning' / 'close' / None（未到记录时段或非交易日）。"""
    dt = dt or datetime.now()
    if dt.weekday() >= 5:  # 周六/周日休市
        return None
    m = dt.hour * 60 + dt.minute
    if MORNING_END <= m < CLOSE_END:
        return "morning"
    if m >= CLOSE_END:
        return "close"
    return None


def fetch_turnover():
    """抓取各市场当前成交额（元）。"""
    rows = fetch_quotes(INDEX_DEFS)
    by_secid = {r["secid"]: r for r in rows}

    def amount(secid):
        r = by_secid.get(secid)
        return r.get("amount") if r else None

    return {"sh": amount("1.000001"), "sz": amount("0.399001"), "cyb": amount("0.399006")}


def ensure_snapshot(data_dir=None, now=None, quiet=True):
    """按当前时间取一次快照（幂等：同一槽位每天只记一次）。
    返回 (status, payload)：
      recorded / exists / skipped（含 reason）
    """
    now = now or datetime.now()
    period = current_period(now)
    if period is None:
        return "skipped", {"reason": "非记录时段或非交易日（周末/盘前/午间休市等）"}

    date = now.strftime("%Y-%m-%d")
    data_dir = data_dir or _DATA_DIR
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, f"{date}.json")
    rec = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
    if rec.get(period):
        return "exists", rec

    turn = fetch_turnover()
    if not turn["sh"] or turn["sh"] <= 0:
        return "skipped", {"reason": "成交额为 0，疑似休市/数据异常"}

    rec[period] = {
        "time": now.strftime("%H:%M:%S"),
        "sh_turnover_yi": round(turn["sh"] / 1e8, 2),
        "sz_turnover_yi": round(turn["sz"] / 1e8, 2),
        "cyb_turnover_yi": round(turn["cyb"] / 1e8, 2),
        "total_yi": round((turn["sh"] + turn["sz"]) / 1e8, 2),
    }
    rec["date"] = date
    _fill_afternoon(rec)
    _write(path, rec)
    _write_latest(rec)
    return "recorded", rec


def _fill_afternoon(rec):
    """下午 = 全天 - 上午（两个槽位齐后计算）。"""
    m = rec.get("morning")
    c = rec.get("close")
    if not (m and c):
        return
    after = {}
    for k in ("sh_turnover_yi", "sz_turnover_yi", "cyb_turnover_yi", "total_yi"):
        if m.get(k) is not None and c.get(k) is not None:
            after[k] = round(c[k] - m[k], 2)
    rec["afternoon"] = after


def _write(path, rec):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)


def _write_latest(rec):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "data", "latest_volume.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
