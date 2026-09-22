# -*- coding: utf-8 -*-
"""
backtest_review.py — 起飛警示篩選條件「回溯檢視」（calendar-clean 版）

和既有 backtest_alerts_v*.py 的差別：
1. **交易日曆修正**：`pwa/ohlc` 從 2026-07-18 起被寫入週末假列（TPEx 回補用日曆日推算日期，
   見 download_ohlc.py 的 tpex_dates），約 870 支上櫃股受影響。舊腳本用「往後數 N 列」算報酬，
   會把假列當成交易日 → 7/18 之後的持有期被縮短、Hurst/維持率也算在髒序列上。
   本腳本自建交易日曆（平日 + 至少 N 支股票有資料），一律用「日曆上的第 N 個交易日」查價。
2. **Hurst 重算**：用清乾淨的序列重算每筆警示的 Hurst，和 alert 檔裡存的值對照，
   量化髒資料對「蓄勢紅框」分類的污染程度。
3. **樣本內／樣本外分開**（切點預設 2026-07-15＝蓄勢紅框上線日）。
4. **對 0050 算超額報酬** + 勝率 Wilson 95% CI + 標示資料截斷。

只讀不寫。
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import datetime
import glob
import json
import math
import os

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ALERTS_DIR = os.path.join(SCRIPT_DIR, "alerts_history")
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")

HOLD_DAYS = [5, 10, 20]
SPLIT_DATE = "20260715"     # <= 樣本內（條件由這段資料挑出）， > 樣本外
BENCH_CODE = "0050"
MIN_STOCKS_PER_DAY = 300    # 一天要有這麼多支有資料才算交易日

ohlc_cache = {}


def load_ohlc(code):
    if code in ohlc_cache:
        return ohlc_cache[code]
    path = os.path.join(OHLC_DIR, f"{code}.json")
    if not os.path.exists(path):
        ohlc_cache[code] = None
        return None
    with open(path, "r", encoding="utf-8") as f:
        ohlc_cache[code] = json.load(f)
    return ohlc_cache[code]


def is_weekday(d):
    return datetime.datetime.strptime(d, "%Y%m%d").weekday() < 5


def build_calendar(codes):
    """交易日 = 平日 且 至少 MIN_STOCKS_PER_DAY 支股票當天有資料"""
    from collections import Counter
    c = Counter()
    for code in codes:
        o = load_ohlc(code)
        if not o:
            continue
        for r in o:
            c[r["t"]] += 1
    cal = sorted(d for d, n in c.items() if n >= MIN_STOCKS_PER_DAY and is_weekday(d))
    dropped = sorted(d for d, n in c.items() if n >= MIN_STOCKS_PER_DAY and not is_weekday(d))
    thin = sorted(d for d, n in c.items() if n < MIN_STOCKS_PER_DAY and is_weekday(d) and d >= cal[0])
    return cal, dropped, thin


def hurst_exponent(closes, min_window=10):
    """與 stock_alert.py 同一份實作（R/S 法、對數報酬）"""
    prices = np.array(closes, dtype=float)
    if len(prices) < min_window * 4 + 1:
        return None
    ts = np.diff(np.log(prices))
    n = len(ts)
    if n < min_window * 4:
        return None
    max_k = n // min_window
    sizes, rs_means = [], []
    for k in range(min_window, max_k * min_window + 1, min_window):
        rs_list = []
        for start in range(0, n - k + 1, k):
            seg = ts[start:start + k]
            dev = np.cumsum(seg - seg.mean())
            r = dev.max() - dev.min()
            s = seg.std(ddof=1)
            if s > 0:
                rs_list.append(r / s)
        if rs_list:
            sizes.append(k)
            rs_means.append(float(np.mean(rs_list)))
    if len(sizes) < 2:
        return None
    H = np.polyfit(np.log(sizes), np.log(rs_means), 1)[0]
    return round(float(H), 3)


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - half) / d * 100, (c + half) / d * 100)


class Series:
    """一支股票清乾淨後的序列（只留交易日曆上的日期）"""

    def __init__(self, rows, cal_set):
        self.rows = [r for r in rows if r["t"] in cal_set]
        self.by_date = {r["t"]: r for r in self.rows}
        self.dates = [r["t"] for r in self.rows]

    def close_on(self, date):
        r = self.by_date.get(date)
        return r["c"] if r else None

    def close_at_or_before(self, date, not_before):
        """target 當天沒開（停牌等）→ 往前找最近一天，但不能早於 not_before"""
        import bisect
        i = bisect.bisect_right(self.dates, date) - 1
        if i < 0:
            return None
        d = self.dates[i]
        return self.rows[i]["c"] if d > not_before else None

    def window_before(self, date, n):
        import bisect
        i = bisect.bisect_right(self.dates, date)
        return self.rows[max(0, i - n):i]

    def closes_upto(self, date):
        import bisect
        i = bisect.bisect_right(self.dates, date)
        return [r["c"] for r in self.rows[:i]]


def calc_retention(series, date, field, lookback=20):
    window = series.window_before(date, lookback)
    vals = [r[field] for r in window if field in r]
    if len(vals) < 5:
        return None
    cum = peak = 0
    for v in vals:
        cum += v
        if cum > peak:
            peak = cum
    if peak <= 0:
        return None
    return round(cum / peak, 2)


# ---------------------------------------------------------------- 資料組裝
def build_records(cal, cal_set, cal_idx):
    bench_rows = load_ohlc(BENCH_CODE)
    bench = Series(bench_rows, cal_set) if bench_rows else None
    series_cache = {}

    def get_series(code):
        if code not in series_cache:
            rows = load_ohlc(code)
            series_cache[code] = Series(rows, cal_set) if rows else None
        return series_cache[code]

    def fwd(series, date, n):
        i = cal_idx.get(date)
        if i is None or i + n >= len(cal):
            return None
        target = cal[i + n]
        c = series.close_on(target)
        if c is None:
            c = series.close_at_or_before(target, date)
        return c

    recs = []
    for af in sorted(glob.glob(os.path.join(ALERTS_DIR, "alerts_*.json"))):
        with open(af, "r", encoding="utf-8") as f:
            fdata = json.load(f)
        date = fdata["date"].replace("-", "")
        if date not in cal_set:
            continue
        for a in fdata.get("alerts", []):
            s = get_series(a["code"])
            if not s or not s.rows:
                continue
            rets, exs = {}, {}
            for n in HOLD_DAYS:
                c = fwd(s, date, n)
                if c is None:
                    continue
                r = (c - a["close"]) / a["close"] * 100
                rets[n] = r
                if bench:
                    b0 = bench.close_on(date)
                    bc = fwd(bench, date, n)
                    if b0 and bc:
                        exs[n] = r - (bc - b0) / b0 * 100
            if not rets:
                continue
            rf = calc_retention(s, date, "fi")
            rt = calc_retention(s, date, "ti")
            cand = [x for x in (rf, rt) if x is not None]
            closes = s.closes_upto(date)
            h_clean = hurst_exponent(closes) if len(closes) >= 60 else None
            recs.append({
                "code": a["code"], "date": date, "close": a["close"],
                "chg_pct": a["chg_pct"], "score": a["score"],
                "hurst_stored": a.get("hurst"), "hurst": h_clean,
                "retention": max(cand) if cand else None,
                "vol_ratio": (a["volume"] / a["avg_volume"]) if a.get("avg_volume") else 0,
                "market": a.get("market", ""),
                "rets": rets, "excess": exs,
            })
    return recs


# ---------------------------------------------------------------- 輸出
def stat_line(label, records, hkey="hurst", width=32):
    line = f"  {label:<{width}}"
    if not records:
        return line + "  （0 筆）"
    for n in HOLD_DAYS:
        rets = [r["rets"][n] for r in records if n in r["rets"]]
        exs = [r["excess"][n] for r in records if n in r["excess"]]
        if not rets:
            line += f" | {n}D n=  0 " + " " * 38
            continue
        k = sum(1 for r in rets if r > 0)
        lo, hi = wilson(k, len(rets))
        avg = sum(rets) / len(rets)
        exavg = sum(exs) / len(exs) if exs else float("nan")
        line += (f" | {n}D n={len(rets):>4} 勝{k / len(rets) * 100:3.0f}%[{lo:.0f}-{hi:.0f}] "
                 f"報{avg:+5.1f}% 超額{exavg:+5.1f}%")
    return line


def strats(hkey):
    hr = lambda r: r[hkey] is not None and 0.45 <= r[hkey] <= 0.55
    rh = lambda r: r["retention"] is not None and r["retention"] >= 0.8
    return [
        ("全部警示（不篩）", lambda r: True),
        ("H_random 0.45-0.55", hr),
        ("H_trend >=0.6", lambda r: r[hkey] is not None and r[hkey] >= 0.6),
        ("R_high >=0.8（不看 Hurst）", rh),
        ("★蓄勢紅框 H_random+R_high", lambda r: hr(r) and rh(r)),
        ("★紅框+排興櫃+100-500+量1.5-3x", lambda r: hr(r) and rh(r) and "興櫃" not in r["market"]
            and 100 <= r["close"] < 500 and 1.5 <= r["vol_ratio"] < 3),
        ("紅框+排興櫃+50-500+量1.5-5x", lambda r: hr(r) and rh(r) and "興櫃" not in r["market"]
            and 50 <= r["close"] < 500 and 1.5 <= r["vol_ratio"] < 5),
    ]


def main():
    codes = set()
    for af in sorted(glob.glob(os.path.join(ALERTS_DIR, "alerts_*.json"))):
        with open(af, "r", encoding="utf-8") as f:
            for a in json.load(f).get("alerts", []):
                codes.add(a["code"])
    codes.add(BENCH_CODE)

    cal, dropped, thin = build_calendar(codes)
    cal_set = set(cal)
    cal_idx = {d: i for i, d in enumerate(cal)}

    print("=" * 146)
    print("  起飛警示回溯檢視（交易日曆修正版）")
    print("=" * 146)
    print(f"交易日曆：{cal[0]} ~ {cal[-1]}，{len(cal)} 個交易日")
    print(f"  排除的週末假列日期（{len(dropped)} 天）：{', '.join(dropped)}")
    print(f"  排除的資料過薄平日（{len(thin)} 天）：{', '.join(thin) if thin else '無'}")

    recs = build_records(cal, cal_set, cal_idx)

    # Hurst 污染
    print("\n" + "=" * 146)
    print("【Hurst 污染檢查】alert 檔存的值 vs 用乾淨序列重算")
    print("-" * 146)
    both = [r for r in recs if r["hurst_stored"] is not None and r["hurst"] is not None]
    for tag, sub in [("樣本內 <=" + SPLIT_DATE, [r for r in both if r["date"] <= SPLIT_DATE]),
                     ("樣本外 >" + SPLIT_DATE, [r for r in both if r["date"] > SPLIT_DATE])]:
        for mk in ["上市", "上櫃"]:
            g = [r for r in sub if r["market"] == mk]
            if not g:
                continue
            diff = [abs(r["hurst_stored"] - r["hurst"]) for r in g]
            moved = sum(1 for d in diff if d >= 0.02)
            was = sum(1 for r in g if 0.45 <= r["hurst_stored"] <= 0.55)
            now = sum(1 for r in g if 0.45 <= r["hurst"] <= 0.55)
            flip = sum(1 for r in g if (0.45 <= r["hurst_stored"] <= 0.55)
                       != (0.45 <= r["hurst"] <= 0.55))
            print(f"  {tag:<18}{mk}  n={len(g):>4}  平均|差|={sum(diff) / len(diff):.3f}  "
                  f"差>=0.02 的 {moved:>4} 筆({moved / len(g) * 100:.0f}%)  "
                  f"H_random 判定 {was}→{now}，翻掉 {flip} 筆({flip / len(g) * 100:.0f}%)")

    is_recs = [r for r in recs if r["date"] <= SPLIT_DATE]
    oos_recs = [r for r in recs if r["date"] > SPLIT_DATE]
    print(f"\n樣本內 n={len(is_recs)}  樣本外 n={len(oos_recs)}   基準={BENCH_CODE}")
    for n in HOLD_DAYS:
        have = [r["date"] for r in recs if n in r["rets"]]
        print(f"  {n:>2}D 報酬可得 {len(have)} 筆，最晚警示日 {max(have) if have else '—'}")

    for hkey, htag in [("hurst", "重算 Hurst（乾淨）"), ("hurst_stored", "原存 Hurst（含髒資料）")]:
        print("\n" + "=" * 146)
        print(f"  ▼ 用「{htag}」分組")
        for title, subset in [("【全期間】", recs), (f"【樣本內 <={SPLIT_DATE}】", is_recs),
                              (f"【樣本外 >{SPLIT_DATE}】", oos_recs)]:
            print("-" * 146)
            print(title)
            for label, fn in strats(hkey):
                print(stat_line(label, [r for r in subset if fn(r)]))

    # 篩選增益（用重算 Hurst）
    print("\n" + "=" * 146)
    print("【篩選增益】蓄勢紅框（重算 Hurst） 相對 同期全部警示（正＝篩選有用）")
    print("-" * 146)
    red = dict(strats("hurst"))["★蓄勢紅框 H_random+R_high"]
    print(f"  {'半月':<10}", end="")
    for n in HOLD_DAYS:
        print(f"{'n':>6}{str(n) + 'D勝率差':>11}{'報酬差':>10}", end="")
    print()
    halves = sorted(set(r["date"][:6] + ("A" if int(r["date"][6:]) <= 15 else "B") for r in recs))
    for hk in halves:
        ym, half = hk[:6], hk[6]
        sub = [r for r in recs if r["date"][:6] == ym
               and ("A" if int(r["date"][6:]) <= 15 else "B") == half]
        picks = [r for r in sub if red(r)]
        print(f"  {hk:<10}", end="")
        for n in HOLD_DAYS:
            pr = [r["rets"][n] for r in picks if n in r["rets"]]
            ar = [r["rets"][n] for r in sub if n in r["rets"]]
            if not pr or not ar:
                print(f"{len(pr):>6}{'—':>11}{'—':>10}", end="")
                continue
            pw = sum(1 for x in pr if x > 0) / len(pr) * 100
            aw = sum(1 for x in ar if x > 0) / len(ar) * 100
            print(f"{len(pr):>6}{pw - aw:>+10.0f}pt{sum(pr) / len(pr) - sum(ar) / len(ar):>+9.1f}%", end="")
        print("  (OOS)" if hk >= "202607B" else "")
    print("=" * 146)


if __name__ == "__main__":
    main()
