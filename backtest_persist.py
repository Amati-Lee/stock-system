# -*- coding: utf-8 -*-
"""
backtest_persist.py — 「持續狀態 + 量」的進場點回測

條件：KD多方 / MACD DIF>0 / DMI多方 / RSI6>RSI12 **四項同時連續 N 天**
      ＋ 當日量比 ≥ 門檻（量比 = 當日量 ÷ 前 20 日均量，⛔ 不含當日，避免自我污染）
進場：訊號日的**隔一個交易日開盤**（訊號是用收盤算的，當日收盤進場不切實際）
出場：持有 5／10／20 個交易日後的收盤
基準：0050 同期，算超額報酬

⛔⛔ 三件事一定要一起講：
  1. **條件 6（400張大戶）完全無法回測** —— holders_history 只有 1 期
  2. **條件 5（籌碼反向）只有 90 個進場日**，樣本太少，本檔預設不納入（--chips 才加）
  3. **這些條件是今天看著資料設計出來的**，所以整段都算樣本內。
     這裡的勝率**不是**「未來會賺多少」的估計，只是「過去長這樣」。

⛔ 掃門檻是為了看**形狀**（有沒有單調關係），不是為了挑最高的那個。
   挑最高的那個上線＝蓄勢紅框的死法。
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import argparse
import glob
import json
import math
import os
from collections import Counter

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")
MARGIN_DIR = os.path.join(SCRIPT_DIR, "margin_history")

HOLD_DAYS = [5, 10, 20]
BENCH = "0050"
VOL_LOOKBACK = 20
MIN_STOCKS_PER_DAY = 300

sys.path.insert(0, SCRIPT_DIR)
from screen_persist import kd_series, macd_dif_series, dmi_series, streak
from screen_new import calc_rsi_series


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - half) / d * 100, (c + half) / d * 100)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persist", type=int, default=5, help="四項條件要連續幾天")
    ap.add_argument("--chips", action="store_true", help="加上條件5（樣本會掉到 90 天）")
    args = ap.parse_args()

    mkt = json.load(open(os.path.join(SCRIPT_DIR, "stock_market_type.json"), encoding="utf-8"))

    # ---- 交易日曆（平日 + 夠多股票有資料）----
    cnt = Counter()
    store = {}
    for path in glob.glob(os.path.join(OHLC_DIR, "*.json")):
        code = os.path.basename(path)[:-5]
        if len(code) != 4 or not code.isdigit():
            continue
        if mkt.get(code) not in ("上市", "上櫃") and code != BENCH:
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
    print(f"交易日曆 {cal[0]} ~ {cal[-1]}，{len(cal)} 天；母體 {len(store)} 支")

    # ---- 融資（只在 --chips 時用）----
    margin = {}
    if args.chips:
        for p in sorted(glob.glob(os.path.join(MARGIN_DIR, "margin_*.json"))):
            d = json.load(open(p, encoding="utf-8"))
            margin[d["date"]] = {c: dict(zip(d["fields"], r)) for c, r in d["data"].items()}
        print(f"融資資料 {len(margin)} 天（條件5 會把可用區間縮到這裡面）")

    def fwd(code, sig_date, hold):
        """訊號日 → 隔日開盤進場 → 持有 hold 個交易日後收盤出場"""
        i = cidx.get(sig_date)
        if i is None or i + 1 + hold >= len(cal):
            return None
        bars = {b["t"]: b for b in store.get(code, [])}
        ein, eout = cal[i + 1], cal[i + 1 + hold]
        a, b = bars.get(ein), bars.get(eout)
        if not a or not b or a["o"] <= 0:
            return None
        return (b["c"] - a["o"]) / a["o"] * 100

    def fwd_bench(sig_date, hold):
        i = cidx.get(sig_date)
        if i is None or i + 1 + hold >= len(cal):
            return None
        a, b = bench.get(cal[i + 1]), bench.get(cal[i + 1 + hold])
        if not a or not b or a["o"] <= 0:
            return None
        return (b["c"] - a["o"]) / a["o"] * 100

    # ---- 逐股產生訊號 ----
    signals = []
    N = args.persist
    for code, bars in store.items():
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

        for i in range(max(60, N), m):
            if not (all(f_kd[i - N + 1:i + 1]) and all(f_md[i - N + 1:i + 1])
                    and all(f_rs[i - N + 1:i + 1]) and all(f_dm[i - N + 1:i + 1])):
                continue
            # 量比：前 20 日均量，⛔ 不含當日
            prev = [bars[j]["v"] for j in range(max(0, i - VOL_LOOKBACK), i)]
            if len(prev) < VOL_LOOKBACK:
                continue
            avg = sum(prev) / len(prev)
            if avg <= 0:
                continue
            vr = bars[i]["v"] / avg
            t = bars[i]["t"]

            chips_ok = None
            if args.chips:
                ts = [b["t"] for b in bars[:i + 1]
                      if b["t"] in margin and code in margin[b["t"]]][-20:]
                if len(ts) < 10:
                    continue
                flows = {b["t"]: b.get("fi", 0) + b.get("ti", 0) for b in bars}
                cum, acc = [], 0
                for tt in ts:
                    acc += flows.get(tt, 0)
                    cum.append(acc)
                mbs = [margin[tt][code]["mb"] for tt in ts]
                x = np.arange(len(ts), dtype=float)
                isl = float(np.polyfit(x, np.array(cum, float), 1)[0])
                msl = float(np.polyfit(x, np.array(mbs, float), 1)[0])
                base = abs(float(np.mean(mbs)))
                mp = (msl / base * 100) if base > 1e-9 else None
                chips_ok = (isl > 0 and mp is not None and mp < -0.2)
                if not chips_ok:
                    continue

            rets, exs = {}, {}
            for h in HOLD_DAYS:
                r = fwd(code, t, h)
                bch = fwd_bench(t, h)
                if r is None:
                    continue
                rets[h] = r
                if bch is not None:
                    exs[h] = r - bch
            if rets:
                signals.append({"code": code, "t": t, "vr": vr,
                                "rets": rets, "excess": exs})

    if not signals:
        print("⛔ 沒有任何訊號")
        return
    dates = sorted({s["t"] for s in signals})
    print(f"\n訊號共 {len(signals)} 筆，分布在 {len(dates)} 個交易日"
          f"（{dates[0]} ~ {dates[-1]}），條件＝四項皆連續 {N} 天"
          + ("＋籌碼反向" if args.chips else ""))

    # ---- 全市場基準（同期間、同進出場規則，不篩任何條件）----
    print("\n" + "=" * 118)
    print("  ⛔ 掃門檻是看形狀，不是挑最高的那個上線")
    print("=" * 118)
    print(f"  {'量比門檻':<18}{'n':>7}", end="")
    for h in HOLD_DAYS:
        print(f"{f'{h}D勝率':>10}{f'{h}D報酬':>10}{f'{h}D超額':>10}", end="")
    print()
    print("-" * 118)

    buckets = [("不設門檻（全部訊號）", lambda v: True),
               ("量比 >= 1.0", lambda v: v >= 1.0),
               ("量比 >= 1.2", lambda v: v >= 1.2),
               ("量比 >= 1.5", lambda v: v >= 1.5),
               ("量比 >= 2.0", lambda v: v >= 2.0),
               ("量比 >= 3.0", lambda v: v >= 3.0),
               ("量比 1.5~3.0（溫和增量）", lambda v: 1.5 <= v < 3.0),
               ("量比 < 1.0（量縮）", lambda v: v < 1.0)]
    for label, fn in buckets:
        sub = [s for s in signals if fn(s["vr"])]
        print(f"  {label:<18}{len(sub):>7}", end="")
        for h in HOLD_DAYS:
            rs = [s["rets"][h] for s in sub if h in s["rets"]]
            es = [s["excess"][h] for s in sub if h in s["excess"]]
            if not rs:
                print(f"{'—':>10}{'—':>10}{'—':>10}", end="")
                continue
            w = sum(1 for x in rs if x > 0) / len(rs) * 100
            print(f"{w:>9.0f}%{sum(rs)/len(rs):>9.1f}%"
                  f"{(sum(es)/len(es) if es else float('nan')):>9.1f}%", end="")
        print()

    # 量比分佈
    vs = sorted(s["vr"] for s in signals)
    print(f"\n  訊號的量比分佈：中位數 {vs[len(vs)//2]:.2f}，"
          f"25/75/90 百分位 = {vs[len(vs)//4]:.2f} / {vs[len(vs)*3//4]:.2f} / {vs[len(vs)*9//10]:.2f}")

    # ---- 穩定性：前後半段 ----
    mid = dates[len(dates) // 2]
    print("\n" + "=" * 118)
    print(f"  【穩定性】把期間對半切（切點 {mid}）—— ⭐ 兩半差很多就別信")
    print("=" * 118)
    print(f"  {'量比門檻':<18}{'前半n':>7}{'前半10D勝率':>13}{'後半n':>7}{'後半10D勝率':>13}{'差':>8}")
    for label, fn in buckets[:7]:
        a = [s["rets"][10] for s in signals if fn(s["vr"]) and s["t"] <= mid and 10 in s["rets"]]
        b = [s["rets"][10] for s in signals if fn(s["vr"]) and s["t"] > mid and 10 in s["rets"]]
        if not a or not b:
            continue
        wa = sum(1 for x in a if x > 0) / len(a) * 100
        wb = sum(1 for x in b if x > 0) / len(b) * 100
        print(f"  {label:<18}{len(a):>7}{wa:>12.0f}%{len(b):>7}{wb:>12.0f}%{wb-wa:>+7.0f}pt")
    print("=" * 118)


if __name__ == "__main__":
    main()
