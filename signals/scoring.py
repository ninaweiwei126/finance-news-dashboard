# -*- coding: utf-8 -*-
"""评分与信号：子指标打分（-1..+1）-> 加权综合 -> 宏观风险叠加 -> 买卖信号。

提供两套入口，共用同一打分实现（_score_at）：
- sub_scores(bars, bench_bars)：实时/最新一天打分
- precompute(bars, bench_bars) + _score_at(pre, i)：回测用，任意历史日期打分（无未来函数）
"""

from signals.indicators import sma, rsi, macd, atr, bollinger, obv

# 子指标权重（合计 1.0）
WEIGHTS = {
    "trend_ma": 0.20,          # 价格相对 20/50/200 均线
    "ma_alignment": 0.10,      # 均线排列 + 金叉死叉
    "macd": 0.15,              # MACD 动量
    "rsi": 0.10,               # RSI 超买超卖
    "position": 0.10,          # 布林带 %B + 52 周位置
    "volume": 0.10,            # 量能确认 + OBV
    "relative_strength": 0.15, # 相对标普500
    "atr": 0.10,               # 波动率（ATR）
}


def _clip(v, lo=-1.0, hi=1.0):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _roll(values, n, fn):
    """滚动窗口聚合。out[i] = fn(values[i-n+1..i])，预热期为 None。"""
    out = [None] * len(values)
    if n <= 0 or len(values) < n:
        return out
    for i in range(n - 1, len(values)):
        out[i] = fn(values[i - n + 1:i + 1])
    return out


def _roll_mean(values, n):
    return _roll(values, n, lambda seg: sum(seg) / len(seg))


def precompute(bars, bench_bars=None):
    """预计算全部指标数组（数组在索引 i 处只依赖 i 及之前的数据，无未来函数）。"""
    closes = [b["close"] for b in bars]
    vols = [b["volume"] for b in bars]
    n = len(closes)

    ml, sl, hg = macd(closes)
    mid_b, up_b, lo_b = bollinger(closes)

    pre = {
        "bars": bars,
        "closes": closes,
        "n": n,
        "s20": sma(closes, 20),
        "s50": sma(closes, 50),
        "s200": sma(closes, 200),
        "rsi14": rsi(closes),
        "ml": ml, "sl": sl, "hg": hg,
        "atr14": atr(bars),
        "mid_b": mid_b, "up_b": up_b, "lo_b": lo_b,
        "vol5": _roll_mean(vols, 5),
        "vol20": _roll_mean(vols, 20),
        "obv": obv(bars),
        "hi52": _roll(closes, 252, max),
        "lo52": _roll(closes, 252, min),
        "bench_closes": _align_bench(bars, bench_bars),
    }
    return pre


def _align_bench(bars, bench_bars):
    """将基准收盘价按日期对齐到 bars（缺失时沿用上一个已知值）。"""
    if not bench_bars:
        return None
    by_date = {b["date"]: b["close"] for b in bench_bars}
    out = []
    last = None
    for b in bars:
        v = by_date.get(b["date"])
        if v is not None:
            last = v
        out.append(last)
    return out


def _score_at(pre, i):
    """在索引 i 处计算 8 个子指标评分与明细。"""
    closes = pre["closes"]
    p = closes[i]
    s20 = pre["s20"][i]
    s50 = pre["s50"][i]
    s200 = pre["s200"][i]

    # 1) 趋势：相对均线的偏离（权重 20/35/40）
    d20 = (p / s20 - 1) * 100 if s20 else None
    d50 = (p / s50 - 1) * 100 if s50 else None
    d200 = (p / s200 - 1) * 100 if s200 else None
    trend_score = (_clip(d20 / 6.0) * 0.25 + _clip(d50 / 10.0) * 0.35
                   + (_clip(d200 / 20.0) if d200 is not None else 0.0) * 0.40)

    # 2) 均线排列 + 金叉/死叉（近 5 日）
    align = 0.0
    cross = None
    cross_days = None
    if s200 is not None:
        align = 0.5 if s50 > s200 else -0.5
        for back in range(1, 6):
            s50b, s200b = pre["s50"][i - back], pre["s200"][i - back]
            s50b1, s200b1 = pre["s50"][i - back - 1], pre["s200"][i - back - 1]
            if None in (s50b, s200b, s50b1, s200b1):
                continue
            if s50b > s200b and s50b1 <= s200b1:
                cross, cross_days = "golden", back - 1
                align += 0.5
                break
            if s50b < s200b and s50b1 >= s200b1:
                cross, cross_days = "death", back - 1
                align -= 0.5
                break

    # 3) MACD
    ml_i, sl_i = pre["ml"][i], pre["sl"][i]
    macd_diff = (ml_i - sl_i) if (ml_i is not None and sl_i is not None) else 0.0
    hist_now = pre["hg"][i] if pre["hg"][i] is not None else 0.0
    hist_prev = pre["hg"][i - 1] if i > 0 and pre["hg"][i - 1] is not None else 0.0
    macd_score = (_clip((macd_diff / p) * 100 / 2.0) * 0.5
                  + _clip(((hist_now - hist_prev) / p) * 100 / 2.0) * 0.5)

    # 4) RSI（均值回归视角：超买偏空、超卖偏多）
    rsi14 = pre["rsi14"][i]
    rsi_score = _clip((50.0 - rsi14) / 25.0)

    # 5) 位置：52 周分位 + 布林带 %B
    hi52, lo52 = pre["hi52"][i], pre["lo52"][i]
    pos52 = (p - lo52) / (hi52 - lo52) if (hi52 and lo52 and hi52 > lo52) else 0.5
    up_b, lo_b = pre["up_b"][i], pre["lo_b"][i]
    pct_b = (p - lo_b) / (up_b - lo_b) if (up_b and lo_b and up_b > lo_b) else 0.5
    position_score = 0.5 * _clip((pos52 - 0.5) * 2.0) + 0.5 * _clip((pct_b - 0.5) * 2.0)

    # 6) 量能：放量确认 + OBV 趋势
    vol5, vol20 = pre["vol5"][i], pre["vol20"][i]
    vol_ratio = vol5 / vol20 if vol20 else 1.0
    chg = pre["bars"][i].get("change_pct") or 0.0
    if vol_ratio > 1.3:
        confirm = 0.5 if chg > 0 else -0.5
    else:
        confirm = 0.0
    obv_chg = pre["obv"][i] - (pre["obv"][i - 20] if i >= 20 else pre["obv"][0])
    obv_trend = _clip(obv_chg / (vol20 * 5.0)) if vol20 else 0.0
    volume_score = 0.5 * obv_trend + 0.5 * confirm

    # 7) 相对强度 vs 标普500
    bc = pre["bench_closes"]
    rs20 = rs60 = None
    if bc and i >= 60 and bc[i] and bc[i - 20] and bc[i - 60] and closes[i - 20] and closes[i - 60]:
        rs20 = (p / closes[i - 20] - 1) * 100 - (bc[i] / bc[i - 20] - 1) * 100
        rs60 = (p / closes[i - 60] - 1) * 100 - (bc[i] / bc[i - 60] - 1) * 100
    rs_score = (_clip(rs20 / 5.0) * 0.5 + _clip(rs60 / 10.0) * 0.5) if rs20 is not None else 0.0

    # 8) 波动率 ATR（越低越利于趋势持有）
    atr14 = pre["atr14"][i]
    atr_pct = (atr14 / p) * 100 if atr14 else None
    atr_score = _clip((2.5 - (atr_pct or 5.0)) / 2.5)

    return {
        "trend_ma": {"score": round(_clip(trend_score), 3), "d20": round(d20, 2) if d20 is not None else None,
                     "d50": round(d50, 2) if d50 is not None else None,
                     "d200": round(d200, 2) if d200 is not None else None},
        "ma_alignment": {"score": round(_clip(align), 3), "sma50": round(s50, 2),
                         "sma200": round(s200, 2) if s200 else None,
                         "cross": cross, "cross_days": cross_days},
        "macd": {"score": round(_clip(macd_score), 3),
                 "macd_line": round(ml_i, 3) if ml_i is not None else None,
                 "signal": round(sl_i, 3) if sl_i is not None else None,
                 "hist": round(hist_now, 3), "hist_change": round(hist_now - hist_prev, 3)},
        "rsi": {"score": round(_clip(rsi_score), 3), "rsi": round(rsi14, 1) if rsi14 is not None else None},
        "position": {"score": round(_clip(position_score), 3), "pos52": round(pos52, 3),
                     "pct_b": round(pct_b, 3),
                     "high52": round(hi52, 2) if hi52 else None,
                     "low52": round(lo52, 2) if lo52 else None},
        "volume": {"score": round(_clip(volume_score), 3), "vol_ratio": round(vol_ratio, 2),
                   "obv_trend": round(obv_trend, 3)},
        "relative_strength": {"score": round(_clip(rs_score), 3),
                              "rs20": round(rs20, 2) if rs20 is not None else None,
                              "rs60": round(rs60, 2) if rs60 is not None else None},
        "atr": {"score": round(_clip(atr_score), 3),
                "atr_pct": round(atr_pct, 2) if atr_pct is not None else None},
    }


def sub_scores(sym_bars, bench_bars):
    """实时打分：最新一天的 8 个子指标评分。"""
    n = len(sym_bars)
    if n < 60:
        return {"valid": False, "note": f"样本不足（{n} 根，需 ≥60）"}
    pre = precompute(sym_bars, bench_bars)
    scores = _score_at(pre, n - 1)
    scores["valid"] = True
    return scores


def _diff_bp(cur, prev):
    if not cur or not prev:
        return None
    out = {}
    for k in ("2Y", "5Y", "10Y", "30Y"):
        if cur.get(k) is not None and prev.get(k) is not None:
            out[k] = round((cur[k] - prev[k]) * 100, 1)
    return out or None


def macro_overlay(macro_summary):
    """宏观风险叠加：美债 10Y 水平/变化速度/曲线 + VIX。返回 {risk, risk_level, components}。"""
    base = {"risk": 0.0, "risk_level": "低", "components": {}, "active": False}
    if not macro_summary:
        return base
    t = macro_summary.get("treasury") or {}
    v = macro_summary.get("vix") or {}
    comps = {}

    y10 = (t.get("yields") or {}).get("10Y")
    if y10 is not None:
        if y10 >= 5.0:
            lv = 1.0
        elif y10 >= 4.7:
            lv = 0.75
        elif y10 >= 4.3:
            lv = 0.5
        elif y10 >= 4.0:
            lv = 0.25
        else:
            lv = 0.0
        comps["treasury_10y"] = {"value": y10, "risk": lv}

    c1 = t.get("change_1d_bp") or {}
    c5 = t.get("change_5d_bp") or {}
    speed = 0.0
    if c1.get("10Y") is not None and c1["10Y"] >= 12:
        speed = max(speed, 0.5)
    if c5.get("10Y") is not None and c5["10Y"] >= 25:
        speed = max(speed, 0.5)
    if speed:
        comps["yield_speed"] = {"risk": speed}

    spread = t.get("spread_10y_2y")
    if spread is not None:
        if spread < -0.5:
            s_risk = 0.6
        elif spread < 0.0:
            s_risk = 0.3
        elif spread > 0.75:
            s_risk = 0.2
        else:
            s_risk = 0.0
        comps["curve_spread"] = {"value": spread, "risk": s_risk}

    vix = v.get("close")
    if vix is not None:
        if vix >= 50:
            vr = 1.0
        elif vix >= 35:
            vr = 0.8
        elif vix >= 25:
            vr = 0.6
        elif vix >= 20:
            vr = 0.4
        elif vix >= 15:
            vr = 0.2
        else:
            vr = 0.0
        comps["vix"] = {"value": vix, "risk": vr}

    if not comps:
        return base
    # 固定权重：10Y 收益率是主导因子（50%），VIX 30%，速度/曲线各 10%
    comp_weight = {"treasury_10y": 0.5, "vix": 0.3, "yield_speed": 0.1, "curve_spread": 0.1}
    wsum = sum(comp_weight[k] for k in comps if k in comp_weight) or 1.0
    risk = sum(comp_weight[k] * comps[k]["risk"] for k in comps if k in comp_weight) / wsum
    if risk >= 0.75:
        label = "极高"
    elif risk >= 0.55:
        label = "高"
    elif risk >= 0.35:
        label = "中高"
    elif risk >= 0.15:
        label = "中低"
    else:
        label = "低"
    return {"risk": round(risk, 3), "risk_level": label, "components": comps,
            "active": risk >= 0.35}


def macro_overlay_from_series(t_series, v_series, date, tdates=None, vdates=None):
    """按指定日期构建宏观快照并套用叠加（回测用，无未来函数）。"""
    snapshot = {"treasury": None, "vix": None}

    if t_series:
        if tdates is None:
            tdates = sorted(t_series)
        import bisect
        ti = bisect.bisect_right(tdates, date) - 1
        if ti >= 0:
            cur = t_series[tdates[ti]]
            prev1 = t_series[tdates[ti - 1]] if ti >= 1 else None
            prev5 = t_series[tdates[ti - 5]] if ti >= 5 else None
            snapshot["treasury"] = {
                "date": tdates[ti],
                "yields": {k: cur.get(k) for k in ("2Y", "5Y", "10Y", "30Y")},
                "change_1d_bp": _diff_bp(cur, prev1),
                "change_5d_bp": _diff_bp(cur, prev5),
            }
            if cur.get("10Y") is not None and cur.get("2Y") is not None:
                snapshot["treasury"]["spread_10y_2y"] = round(cur["10Y"] - cur["2Y"], 2)

    if v_series:
        if vdates is None:
            vdates = sorted(v_series)
        import bisect
        vi = bisect.bisect_right(vdates, date) - 1
        if vi >= 0:
            cur = v_series[vdates[vi]].get("close")
            prev = None
            for j in range(vi - 1, -1, -1):
                if v_series[vdates[j]].get("close") is not None:
                    prev = v_series[vdates[j]]["close"]
                    break
            snapshot["vix"] = {"date": vdates[vi], "close": cur}
            if cur is not None and prev is not None:
                snapshot["vix"]["change_1d"] = round(cur - prev, 2)

    return macro_overlay(snapshot)


def signal_from_score(score):
    if score >= 0.45:
        return "买入"
    if score >= 0.15:
        return "持有偏多"
    if score > -0.15:
        return "观望"
    if score > -0.45:
        return "持有偏空"
    return "卖出"


ACTION_TIPS = {
    "买入": "信号偏多：趋势/动量共振，可关注分批介入机会，设好止损",
    "持有偏多": "信号偏多但不强：持有为主，回踩不破关键均线可考虑加仓",
    "观望": "信号中性：多空不明显，等待方向明朗",
    "持有偏空": "信号偏空但不强：降低仓位，反弹至压力位可考虑减仓",
    "卖出": "信号偏空：趋势/动量走弱，注意控制回撤风险",
}


def composite_score(scores, overlay):
    """加权综合 + 宏观风险打折。"""
    raw = sum(WEIGHTS[k] * scores[k]["score"] for k in WEIGHTS if k in scores)
    risk = overlay.get("risk", 0.0)
    adjusted = raw * (1 - 0.5 * risk)
    signal = signal_from_score(adjusted)
    tip = ACTION_TIPS[signal]
    if risk >= 0.5:
        tip += "（宏观风险较高，建议控制整体仓位）"
    return {
        "raw": round(raw, 3),
        "adjusted": round(adjusted, 3),
        "signal": signal,
        "confidence": round(abs(adjusted), 3),
        "action_tip": tip,
    }
