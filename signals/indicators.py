# -*- coding: utf-8 -*-
"""技术指标纯函数库（纯标准库，无 numpy）。
所有函数返回与输入等长的列表，预热期(数据不足)为 None。
bars: [{date, open, close, high, low, volume, amount, change_pct}] 按日期升序。
"""


def sma(values, n):
    """简单移动平均。"""
    out = [None] * len(values)
    if n <= 0 or len(values) < n:
        return out
    s = sum(values[:n])
    out[n - 1] = s / n
    for i in range(n, len(values)):
        s += values[i] - values[i - n]
        out[i] = s / n
    return out


def ema(values, n):
    """指数移动平均（以首段 SMA 为种子）。"""
    out = [None] * len(values)
    if n <= 0 or len(values) < n:
        return out
    k = 2.0 / (n + 1)
    seed = sum(values[:n]) / n
    out[n - 1] = seed
    prev = seed
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes, n=14):
    """Wilder RSI。"""
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    avg_g, avg_l = gains / n, losses / n
    out[n] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        g = max(d, 0.0)
        l = max(-d, 0.0)
        avg_g = (avg_g * (n - 1) + g) / n
        avg_l = (avg_l * (n - 1) + l) / n
        out[i] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return out


def macd(closes, fast=12, slow=26, signal=9):
    """MACD。返回 (macd_line, signal_line, histogram)。"""
    n = len(closes)
    ef = ema(closes, fast)
    es = ema(closes, slow)
    macd_line = [(ef[i] - es[i]) if (ef[i] is not None and es[i] is not None) else None
                 for i in range(n)]
    sig = [None] * n
    hist = [None] * n
    start = next((i for i, v in enumerate(macd_line) if v is not None), None)
    if start is None or n - start < signal:
        return macd_line, sig, hist
    seg = macd_line[start:]
    k = 2.0 / (signal + 1)
    seed = sum(seg[:signal]) / signal
    sig[start + signal - 1] = seed
    prev = seed
    for i in range(1, len(seg) - signal + 1):
        prev = seg[signal - 1 + i] * k + prev * (1 - k)
        sig[start + signal - 1 + i] = prev
    for i in range(n):
        if macd_line[i] is not None and sig[i] is not None:
            hist[i] = macd_line[i] - sig[i]
    return macd_line, sig, hist


def atr(bars, n=14):
    """平均真实波幅（SMA 平滑）。"""
    out = [None] * len(bars)
    if len(bars) <= n:
        return out
    trs = [0.0] * len(bars)
    trs[0] = bars[0]["high"] - bars[0]["low"]
    for i in range(1, len(bars)):
        h = bars[i]["high"]
        l = bars[i]["low"]
        pc = bars[i - 1]["close"]
        trs[i] = max(h - l, abs(h - pc), abs(l - pc))
    s = sum(trs[1:n + 1])
    out[n] = s / n
    for i in range(n + 1, len(bars)):
        s += trs[i] - trs[i - n]
        out[i] = s / n
    return out


def bollinger(closes, n=20, k=2.0):
    """布林带。返回 (mid, upper, lower)。"""
    mid = sma(closes, n)
    up = [None] * len(closes)
    lo = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        seg = closes[i - n + 1:i + 1]
        m = mid[i]
        var = sum((x - m) ** 2 for x in seg) / n
        sd = var ** 0.5
        up[i] = m + k * sd
        lo[i] = m - k * sd
    return mid, up, lo


def obv(bars):
    """能量潮。"""
    out = [0.0] * len(bars)
    for i in range(1, len(bars)):
        if bars[i]["close"] > bars[i - 1]["close"]:
            out[i] = out[i - 1] + bars[i]["volume"]
        elif bars[i]["close"] < bars[i - 1]["close"]:
            out[i] = out[i - 1] - bars[i]["volume"]
        else:
            out[i] = out[i - 1]
    return out
