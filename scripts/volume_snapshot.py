#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A股成交额快照：上午(11:30后) / 全天(15:00后)，每日各记一次。
用法: python3 scripts/volume_snapshot.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from collector.volume import ensure_snapshot  # noqa: E402

if __name__ == "__main__":
    status, payload = ensure_snapshot()
    if status == "recorded":
        slot = payload.get("morning") or payload.get("close") or {}
        print(f"[OK] 已记录 {payload['date']} 快照：两市成交额 {slot.get('total_yi')} 亿元"
              f"（沪 {slot.get('sh_turnover_yi')} / 深 {slot.get('sz_turnover_yi')}）")
    elif status == "exists":
        print(f"[SKIP] 今日该时段快照已存在（{payload.get('date')}）")
    else:
        print(f"[SKIP] {payload.get('reason')}")
