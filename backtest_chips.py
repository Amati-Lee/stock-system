# -*- coding: utf-8 -*-
"""
backtest_chips.py — 把「四項技術面」和「籌碼反向」拆開測，看加值來自哪一邊

⛔ 四組必須在**同一段期間**比，否則比較是混淆的。
   期間由融資資料決定（margin_history 只有 130 天）⇒ 全部組別都限制在同一個窗口。

四組：
  A. 全市場基準      所有股票所有日子（每 2 天取樣），同樣的進出場規則
  B. 只有籌碼反向    法人淨>0 且 融資淨<0 且 融資斜率<-0.2%/日（20 日窗口）
  C. 只有技術持續    KD／MACD／DMI／RSI 四項皆連續 N 天
  D. 兩者都要

進場：訊號日隔一個交易日開盤　出場：持有 5/10/20 個交易日後收盤　基準：0050

⛔ 這些條件是看著今天的資料設計的 ⇒ 整段都算樣本內。
   這裡的勝率不是「未來會賺多少」，只是「過去長這樣」。
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import argparse
import glob
import json
import math
import os
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")
MARGIN_DIR = os.path.join(SCRIPT_DIR, "margin_history")

HOLD_DAYS = [5, 10, 20]
BENCH = "0050"
W = 20                       # 籌碼窗口
MARG_SLOPE_MAX = -0.2
MIN_STOCKS_PER_DAY = 300

sys.path.insert(0, SCRIPT_DIR)
from screen_persist import kd_series, macd_dif_series, dmi_series
from screen_new import calc_rsi_series

# 固定 x = 0..W-1 的回歸分母，先算好
_XS = list(range(W))
_XM = sum(_XS) / W
_DEN = sum((x - _XM) ** 2 for x in _XS)


def slope(ys):
    """封閉解線性回歸斜率（x 固定 0..n-1）"""
    n = len(ys)
    if n < 5:
        return None
    xm = (n - 1) / 2
    ym = sum(ys) / n
    den = sum((i - xm) ** 2 for i in range(n))
    if den == 0:
        return None
    return sum((i - xm) * (ys[i] - ym) for i in range(n)) / den


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - half) / d * 100, (c + half) / d * 100)


def report(title, recs, bench_note=""):
    print(f"  {title:<26}", end="")
    if not recs:
        print("（0 筆）")
        return
    for h in HOLD_DAYS:
        rs = [r["rets"][h] for r in recs if h in r["rets"]]
        es = [r["excess"][h] for r in recs if h in r["excess"]]
        if not rs:
            print(f"{'—':>32}", end="")
            continue
        k = sum(1 for x in rs if x > 0)
        lo, hi = wilson(k, len(rs))
        print(f" | {h}D n={len(rs):>5} 勝{k/len(rs)*100:3.0f}%[{lo:.0f}-{hi:.0f}]"
              f" 報{sum(rs)/len(rs):+5.1f}% 超額{(sum(es)/len(es) if es else float('nan')):+5.1f}%", end="")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persist", type=int, default=5)
    args = ap.parse_args()
    N = args.persist

    mkt = json.load(open(os.path.join(SCRIPT_DIR, "stock_market_type.json"), encoding="utf-8"))

    store, cnt = {}, Counter()
    for path in glob.glob(os.path.join(OHLC_DIR, "*.json")):
        code = os.path.basename(path)[:-5]
        if len(code) != 4 or not code.isdigit() or mkt.get(code) not in ("上市", "上櫃"):
            continue
        try:
            bars = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if len(bars) < 80:
            continue
        store[code] = bars
        for b in bars:
            cnt[b["t"]] += 1
    bench_bars = json.load(open(os.path.join(OHLC_DIR, f"{BENCH}.json"), encoding="utf-8"))
    for b in bench_bars:
        cnt[b["t"]] += 1
    cal = sorted(d for d, n in cnt.items() if n >= MIN_STOCKS_PER_DAY)
    cidx = {d: i for i, d in enumerate(cal)}
    bench = {b["t"]: b for b in bench_bars}

    margin = {}
    for p in sorted(glob.glob(os.path.join(MARGIN_DIR, "margin_*.json"))):
        d = json.load(open(p, encoding="utf-8"))
        margin[d["date"]] = {c: dict(zip(d["fields"], r)) for c, r in d["data"].items()}
    mdays = sorted(margin)

    # 可用進場日：融資已累積滿 W 天，且還有 20 日前瞻報酬
    first_ok = mdays[W - 1]
    lo = cidx.get(first_ok, 0)
    hi = len(cal) - 1 - max(HOLD_DAYS)
    window = [cal[i] for i in range(lo, hi + 1) if cal[i] in margin]
    print("=" * 128)
    print("  籌碼反向 vs 技術持續 —— 拆開測，同一段期間")
    print("=" * 128)
    print(f"共同進場區間：{window[0]} ~ {window[-1]}，{len(window)} 個交易日"
          f"（由融資資料的 {len(mdays)} 天決定）")

    wset = set(window)

    def fwd(bmap, t, h):
        i = cidx[t]
        if i + 1 + h >= len(cal):
            return None
        a, b = bmap.get(cal[i + 1]), bmap.get(cal[i + 1 + h])
        if not a or not b or a["o"] <= 0:
            return None
        return (b["c"] - a["o"]) / a["o"] * 100

    bench_cache = {}

    def fwd_b(t, h):
        key = (t, h)
        if key not in bench_cache:
            bench_cache[key] = fwd(bench, t, h)
        return bench_cache[key]

    A, B, C, D = [], [], [], []
    for code, bars in store.items():
        bmap = {b["t"]: b for b in bars}
        closes = [b["c"] for b in bars]
        k, d_ = kd_series(bars)
        dif = macd_dif_series(closes)
        r6, r12 = calc_rsi_series(closes, 6), calc_rsi_series(closes, 12)
        pdi, mdi = dmi_series(bars)
        if not (k and dif and r6 and r12 and pdi):
            continue
        m = min(len(k), len(dif), len(r6), len(r12), len(pdi), len(bars))
        f_kd = [k[i] is not None and d_[i] is not None and k[i] > d_[i] for i in range(m)]
        f_md = [dif[i] > 0 for i in range(m)]
        f_rs = [r6[i] is not None and r12[i] is not None and r6[i] > r12[i] for i in range(m)]
        f_dm = [pdi[i] is not None and mdi[i] is not None and pdi[i] > mdi[i] for i in range(m)]

        # 這支在融資資料裡有哪些日子（依序）
        mts = [b["t"] for b in bars if b["t"] in margin and code in margin[b["t"]]]
        mpos = {t: j for j, t in enumerate(mts)}
        flows = {b["t"]: b.get("fi", 0) + b.get("ti", 0) for b in bars}

        for i in range(60, m):
            t = bars[i]["t"]
            if t not in wset:
                continue
            rets, exs = {}, {}
            for h in HOLD_DAYS:
                r = fwd(bmap, t, h)
                if r is None:
                    continue
                rets[h] = r
                bb = fwd_b(t, h)
                if bb is not None:
                    exs[h] = r - bb
            if not rets:
                continue
            rec = {"code": code, "t": t, "rets": rets, "excess": exs}

            # A：全市場基準（每 2 天取樣，控制樣本量）
            if i % 2 == 0:
                A.append(rec)

            # B：籌碼反向
            chips = False
            j = mpos.get(t)
            if j is not None and j >= W - 1:
                ts = mts[j - W + 1:j + 1]
                acc, cum = 0, []
                for tt in ts:
                    acc += flows.get(tt, 0)
                    cum.append(acc)
                mbs = [margin[tt][code]["mb"] for tt in ts]
                isl = slope(cum)
                msl = slope(mbs)
                base = abs(sum(mbs) / len(mbs))
                mp = (msl / base * 100) if (msl is not None and base > 1e-9) else None
                chips = (cum[-1] > 0 and mbs[-1] - mbs[0] < 0 and isl is not None
                         and isl > 0 and mp is not None and mp < MARG_SLOPE_MAX)
            if chips:
                B.append(rec)

            # C：技術持續
            tech = (all(f_kd[i - N + 1:i + 1]) and all(f_md[i - N + 1:i + 1])
                    and all(f_rs[i - N + 1:i + 1]) and all(f_dm[i - N + 1:i + 1]))
            if tech:
                C.append(rec)
            if tech and chips:
                D.append(rec)

    print(f"\n訊號數：基準(每2天取樣) {len(A):,}　籌碼 {len(B):,}　"
          f"技術連{N}天 {len(C):,}　兩者皆 {len(D):,}")
    print("-" * 128)
    report("A 全市場基準", A)
    report("B 只有籌碼反向", B)
    report(f"C 只有技術持續{N}天", C)
    report("D 籌碼 ＋ 技術", D)
    print("=" * 128)

    # 加值分解：相對基準的勝率差
    print("\n【相對基準的勝率差】正＝有加值")
    base_w = {}
    for h in HOLD_DAYS:
        rs = [r["rets"][h] for r in A if h in r["rets"]]
        base_w[h] = sum(1 for x in rs if x > 0) / len(rs) * 100 if rs else None
    for label, g in [("B 只有籌碼", B), (f"C 只有技術{N}天", C), ("D 兩者皆", D)]:
        line = f"  {label:<16}"
        for h in HOLD_DAYS:
            rs = [r["rets"][h] for r in g if h in r["rets"]]
            if not rs or base_w[h] is None:
                line += f"{'—':>12}"
                continue
            w = sum(1 for x in rs if x > 0) / len(rs) * 100
            line += f"{w - base_w[h]:>+10.0f}pt"
        print(line + "   （5D / 10D / 20D）")
    print("=" * 128)


if __name__ == "__main__":
    main()
