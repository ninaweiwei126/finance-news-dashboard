# -*- coding: utf-8 -*-
"""回测引擎：逐日信号（无未来函数）-> 模拟交易（含成本）-> 指标/归因/区间分析。

约定：
- 信号在收盘后由当日及之前数据产生，次日（close→close）生效。
- 仓位映射：买入=100%，持有偏多=50%，其余=空仓（不做空）。
- 成本：每次调仓按 |Δ仓位| × 成本率 扣减（默认 5bp）。
"""
import bisect
import json
import math
import os
import statistics
from datetime import datetime

from signals.scoring import (WEIGHTS, precompute, _score_at, composite_score,
                             signal_from_score, macro_overlay_from_series)
from signals.engine import HISTORY_CONFIG, KLINES_DIR
from collector.macro import _load_series, HISTORY_DIR as MACRO_DIR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKTEST_DIR = os.path.join(ROOT, "data", "backtest")

WARMUP = 205          # 预热期：保证 SMA200 金叉检测（需 205 根）
DEFAULT_COST = 0.0005  # 每次调仓 5bp
HORIZON = 5            # 信号命中率判定：未来 5 个交易日


def _load_bars(symbol):
    path = os.path.join(KLINES_DIR, f"{symbol}.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("bars", [])
    except (OSError, ValueError):
        return []


def signal_series(pre, t_series, v_series, start_idx=WARMUP):
    """逐日生成综合信号（含当日宏观叠加），无未来函数。"""
    tdates = sorted(t_series) if t_series else []
    vdates = sorted(v_series) if v_series else []
    out = []
    for i in range(start_idx, pre["n"]):
        scores = _score_at(pre, i)
        overlay = macro_overlay_from_series(t_series, v_series, pre["bars"][i]["date"],
                                            tdates, vdates)
        comp = composite_score(scores, overlay)
        out.append({
            "i": i,
            "date": pre["bars"][i]["date"],
            "score": comp["adjusted"],
            "raw": comp["raw"],
            "signal": comp["signal"],
            "overlay_risk": overlay["risk"],
        })
    return out


def position_for(score):
    if score >= 0.45:
        return 1.0
    if score >= 0.15:
        return 0.5
    return 0.0


def simulate(closes, sig, start_idx=WARMUP, cost_rate=DEFAULT_COST):
    """模拟交易。sig: [{i, score}]；返回日收益序列与换手次数。"""
    by_i = {s["i"]: s for s in sig}
    rets = []
    prev_pos = 0.0
    trades = 0
    for i in range(start_idx, len(closes) - 1):
        s = by_i.get(i)
        pos = position_for(s["score"]) if s else 0.0
        ret = closes[i + 1] / closes[i] - 1.0
        turnover = abs(pos - prev_pos)
        if turnover > 0:
            trades += 1
        rets.append(pos * ret - turnover * cost_rate)
        prev_pos = pos
    return {"returns": rets, "trades": trades}


def metrics(rets):
    if not rets:
        return {}
    eq = 1.0
    for r in rets:
        eq *= (1 + r)
    total = eq - 1
    years = len(rets) / 252.0
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 and total > -1 else None
    mean = sum(rets) / len(rets)
    sd = statistics.pstdev(rets)
    sharpe = mean / sd * math.sqrt(252) if sd > 1e-12 else 0.0
    eqc = 1.0
    peak = 1.0
    mdd = 0.0
    for r in rets:
        eqc *= (1 + r)
        peak = max(peak, eqc)
        mdd = min(mdd, eqc / peak - 1)
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    pf = None
    if losses and abs(sum(losses)) > 1e-12:
        pf = sum(wins) / abs(sum(losses))
    elif wins:
        pf = float("inf")
    return {
        "total_return_pct": round(total * 100, 2),
        "cagr_pct": round(cagr * 100, 2) if cagr is not None else None,
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(mdd * 100, 2),
        "win_rate_daily": round(len(wins) / len(rets), 3),
        "avg_win_pct": round((sum(wins) / len(wins)) * 100, 2) if wins else 0.0,
        "avg_loss_pct": round((sum(losses) / len(losses)) * 100, 2) if losses else 0.0,
        "profit_factor": "inf" if pf == float("inf")
                     else (round(pf, 2) if pf is not None else "n/a"),
    }


def signal_hit_rates(sig, closes, horizon=HORIZON):
    """按信号类别统计方向命中率：买入/持有偏多 -> 未来5日上涨；卖出/持有偏空 -> 未来5日下跌。"""
    stats = {}
    for s in sig:
        label = s["signal"]
        if label not in ("买入", "持有偏多", "卖出", "持有偏空"):
            continue
        i = s["i"]
        if i + horizon >= len(closes):
            continue
        fwd = closes[i + horizon] / closes[i] - 1
        hit = fwd > 0 if label in ("买入", "持有偏多") else fwd < 0
        st = stats.setdefault(label, {"days": 0, "hits": 0})
        st["days"] += 1
        st["hits"] += int(hit)
    return {k: {"days": v["days"], "hit_rate": round(v["hits"] / v["days"], 3)}
            for k, v in stats.items() if v["days"] > 0}


def attribution(pre, t_series, v_series, start_idx=WARMUP):
    """每个子指标单独回测，找出真实贡献。"""
    out = []
    for key in WEIGHTS:
        sig = []
        for i in range(start_idx, pre["n"]):
            sc = _score_at(pre, i)[key]["score"]
            sig.append({"i": i, "score": sc, "signal": signal_from_score(sc)})
        res = simulate(pre["closes"], sig, start_idx, DEFAULT_COST)
        m = metrics(res["returns"])
        m["trades"] = res["trades"]
        m["signal_hit_rates"] = signal_hit_rates(sig, pre["closes"])
        m["indicator"] = key
        out.append(m)
    return out


def regime_analysis(pre, rets, t_series, v_series, start_idx=WARMUP):
    """分行情区间：低/高 VIX、低/高 10Y 收益率下的策略 vs 买入持有。"""
    closes = pre["closes"]
    tdates = sorted(t_series) if t_series else []
    vdates = sorted(v_series) if v_series else []
    conds = {"vix<20": [], "vix>=20": [], "10Y<4.3": [], "10Y>=4.3": []}
    for i in range(start_idx, len(closes) - 1):
        date = pre["bars"][i]["date"]
        vi = bisect.bisect_right(vdates, date) - 1
        vix = v_series[vdates[vi]].get("close") if vi >= 0 else None
        ti = bisect.bisect_right(tdates, date) - 1
        y10 = t_series[tdates[ti]].get("10Y") if ti >= 0 else None
        conds["vix<20"].append(vix is not None and vix < 20)
        conds["vix>=20"].append(vix is not None and vix >= 20)
        conds["10Y<4.3"].append(y10 is not None and y10 < 4.3)
        conds["10Y>=4.3"].append(y10 is not None and y10 >= 4.3)
    out = {}
    for name, cond in conds.items():
        if not any(cond):
            continue
        strat = 1.0
        bh = 1.0
        cnt = 0
        for k, c in enumerate(cond):
            if not c:
                continue
            strat *= (1 + rets[k])
            bh *= (1 + (closes[start_idx + k + 1] / closes[start_idx + k] - 1))
            cnt += 1
        out[name] = {
            "days": cnt,
            "strategy_return_pct": round((strat - 1) * 100, 2),
            "buy_hold_return_pct": round((bh - 1) * 100, 2),
        }
    return out


SAMPLE_NOTES = {
    "CRCL": "东财 K 线自 2025-06-05 起（约 14 个月），有效信号日仅约百个，统计结论仅供参考",
    "SNDK": "2025-02-24 分拆上市，有效信号日约 170 个，统计结论仅供参考",
}


def run_backtest(cost_rate=DEFAULT_COST):
    with open(HISTORY_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    holdings = [s for s in cfg.get("symbols", []) if s.get("group") == "holdings"]
    bench = next((s for s in cfg.get("symbols", []) if s.get("symbol") == "SPX"), None)
    bench_bars = _load_bars(bench["symbol"]) if bench else []

    t_series = _load_series(os.path.join(MACRO_DIR, "treasury.json"))
    v_series = _load_series(os.path.join(MACRO_DIR, "vix.json"))

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "methodology": {
            "warmup_days": WARMUP,
            "execution": "信号于收盘后产生、次日 close→close 生效（无未来函数）",
            "position": "买入=100% / 持有偏多=50% / 观望·偏空·卖出=空仓（不做空）",
            "cost": f"每次调仓 {int(cost_rate * 10000)}bp（另附 0/5/10bp 敏感性）",
            "hit_rate_horizon": f"信号命中率按未来 {HORIZON} 个交易日方向判定",
            "macro_overlay": "回测逐日套用当日宏观风险（10Y/VIX/曲线），与实时一致",
            "weights": "子指标权重为事前固定设定，未在历史数据上调参",
            "caveats": ["CRCL/SNDK 样本偏短，结论仅供参考",
                        "仅做多/空仓，未包含做空与融资成本",
                        "未包含跳空冲击与滑点（仅固定成本率）"],
        },
        "holdings": [],
    }

    for h in holdings:
        bars = _load_bars(h["symbol"])
        n = len(bars)
        entry = {
            "symbol": h["symbol"], "name_cn": h.get("name_cn"),
            "bars": n,
            "period": f"{bars[0]['date']} ~ {bars[-1]['date']}" if bars else "",
            "sample_note": SAMPLE_NOTES.get(h["symbol"]),
        }
        if n < WARMUP + 30:
            entry["valid"] = False
            entry["note"] = f"K 线不足（{n} 根，需 ≥{WARMUP + 30}）"
            report["holdings"].append(entry)
            continue
        entry["valid"] = True
        pre = precompute(bars, bench_bars)
        sig = signal_series(pre, t_series, v_series)
        closes = pre["closes"]

        res = simulate(closes, sig, WARMUP, cost_rate)
        strat = metrics(res["returns"])
        strat["trades"] = res["trades"]

        bh_rets = [closes[i + 1] / closes[i] - 1 for i in range(WARMUP, len(closes) - 1)]
        bh = metrics(bh_rets)

        cost_sens = {}
        for cr in (0.0, 0.0005, 0.001):
            r2 = simulate(closes, sig, WARMUP, cr)
            cost_sens[f"{int(cr * 10000)}bp"] = {
                "total_return_pct": metrics(r2["returns"]).get("total_return_pct"),
                "trades": r2["trades"],
            }

        entry.update({
            "strategy": strat,
            "buy_hold": bh,
            "vs_buy_hold_pp": round(strat.get("total_return_pct", 0)
                                    - bh.get("total_return_pct", 0), 2),
            "signal_stats": signal_hit_rates(sig, closes),
            "cost_sensitivity": cost_sens,
            "regimes": regime_analysis(pre, res["returns"], t_series, v_series),
            "indicator_attribution": attribution(pre, t_series, v_series),
            "latest_signal": sig[-1] if sig else None,
        })
        report["holdings"].append(entry)

    return report


def save_backtest(report, out_dir=BACKTEST_DIR):
    os.makedirs(out_dir, exist_ok=True)
    latest = os.path.join(out_dir, "latest.json")
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    day = datetime.now().strftime("%Y-%m-%d")
    day_path = os.path.join(out_dir, f"{day}.json")
    with open(day_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    return latest, day_path
