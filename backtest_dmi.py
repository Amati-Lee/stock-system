# -*- coding: utf-8 -*-
"""
backtest_dmi.py — 用 DMI（+DI / −DI / ADX）當篩選條件，看樣本內外表現

⚠️ 專案裡原本**沒有任何 DMI/ADX 程式碼**（2026-09-24 全庫 grep 過），這支是新寫的。
   DMI 不是存起來的欄位，是從 pwa/ohlc 的 h/l/c 現算的。

⛔⛔ 命名地雷：OHLC 裡的 `di` 欄位是**自營商買賣超**（dealer institutional），
     跟 DMI 的 DI（Directional Indicator）完全無關。本檔一律用 `pdi`/`mdi`/`adx`。

和 backtest_review.py 共用兩個前提：
  1. 自建交易日曆（平日 + 至少 N 支有資料），⛔ 不用「往後數 N 列」
  2. 每筆警示的指標只用 `t <= alert_date` 的資料算，無 lookahead

只讀不寫。
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import datetime
import glob
import json
import math
import os
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ALERTS_DIR = os.path.join(SCRIPT_DIR, "alerts_history")
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")

HOLD_DAYS = [5, 10, 20]
SPLIT_DATE = "20260715"
BENCH_CODE = "0050"
MIN_STOCKS_PER_DAY = 300
DMI_PERIOD = 14
MIN_BARS = 40          # 14 個 TR + 14 個 DX 平滑，再留餘裕

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


# ---------------------------------------------------------------- DMI
def dmi(bars, period=DMI_PERIOD):
    """Wilder 原始定義的 +DI / −DI / ADX。bars = [{h,l,c}, ...] 由舊到新。
    回傳最後一根的 (pdi, mdi, adx)，資料不足回 (None, None, None)。"""
    n = len(bars)
    if n < period * 2 + 1:
        return None, None, None

    trs, pdms, mdms = [], [], []
    for i in range(1, n):
        h, l = bars[i]["h"], bars[i]["l"]
        ph, pl, pc = bars[i - 1]["h"], bars[i - 1]["l"], bars[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        up, dn = h - ph, pl - l
        pdms.append(up if (up > dn and up > 0) else 0.0)
        mdms.append(dn if (dn > up and dn > 0) else 0.0)

    def wilder(seq):
        """Wilder 平滑：先取前 period 個的和，之後 S = S - S/period + x"""
        s = sum(seq[:period])
        out = [s]
        for x in seq[period:]:
            s = s - s / period + x
            out.append(s)
        return out

    tr_s, pdm_s, mdm_s = wilder(trs), wilder(pdms), wilder(mdms)

    dxs = []
    for tr, pd_, md in zip(tr_s, pdm_s, mdm_s):
        if tr <= 0:
            continue
        p = 100.0 * pd_ / tr
        m = 100.0 * md / tr
        dxs.append((p, m, 100.0 * abs(p - m) / (p + m) if (p + m) > 0 else 0.0))
    if len(dxs) < period:
        return None, None, None

    pdi, mdi_, _ = dxs[-1]
    adx = sum(d[2] for d in dxs[:period]) / period
    for d in dxs[period:]:
        adx = (adx * (period - 1) + d[2]) / period
    return round(pdi, 2), round(mdi_, 2), round(adx, 2)


def selftest():
    """⛔ 指標自己要先證明算得對，不然下面的分組全是噪音。"""
    fails = []
    # ① 收在最高、無跳空的上漲 → TR 就等於 +DM ⇒ +DI 正好 100
    up = [{"h": 100 + i, "l": 99 + i, "c": 100 + i} for i in range(60)]
    p, m, a = dmi(up)
    if not (p == 100 and m == 0 and a == 100):
        fails.append(f"收最高上漲: +DI={p} −DI={m} ADX={a}（期望 100 / 0 / 100）")
    # ② 收在最低、無跳空的下跌 → 反過來
    dn = [{"h": 200 - i, "l": 199 - i, "c": 199 - i} for i in range(60)]
    p, m, a = dmi(dn)
    if not (m == 100 and p == 0 and a == 100):
        fails.append(f"收最低下跌: +DI={p} −DI={m} ADX={a}（期望 0 / 100 / 100）")
    # ③ ⭐ 跳空上漲：TR 會把缺口算進去，所以 +DI **不是** 100。
    #    每根 h=101+2i, l=100+2i, c=100.5+2i ⇒ TR=2.5、+DM=2 ⇒ +DI=80 才是對的。
    #    （2026-09-24 我第一版把期望寫成 >90，被這組擋下來——錯的是期望不是實作）
    gap = [{"h": 100 + i * 2 + 1, "l": 100 + i * 2, "c": 100 + i * 2 + 0.5} for i in range(60)]
    p, m, a = dmi(gap)
    if not (p == 80 and m == 0 and a == 100):
        fails.append(f"跳空上漲: +DI={p} −DI={m} ADX={a}（期望 80 / 0 / 100）")
    # 完全橫盤（每根一樣）→ 沒有方向，ADX 應該是 0
    flat = [{"h": 101, "l": 99, "c": 100} for _ in range(60)]
    p, m, a = dmi(flat)
    if not (a is not None and a < 1 and p < 1 and m < 1):
        fails.append(f"橫盤: +DI={p} −DI={m} ADX={a}（期望全部 ~0）")
    # 資料不足 → 要回 None，不可硬算
    if dmi([{"h": 1, "l": 1, "c": 1}] * 10) != (None, None, None):
        fails.append("資料不足時沒有回 None")
    return fails


# ---------------------------------------------------------------- 統計
def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - half) / d * 100, (c + half) / d * 100)


class Series:
    def __init__(self, rows, cal_set):
        self.rows = [r for r in rows if r["t"] in cal_set]
        self.by_date = {r["t"]: r for r in self.rows}
        self.dates = [r["t"] for r in self.rows]

    def close_on(self, date):
        r = self.by_date.get(date)
        return r["c"] if r else None

    def close_at_or_before(self, date, not_before):
        import bisect
        i = bisect.bisect_right(self.dates, date) - 1
        if i < 0:
            return None
        return self.rows[i]["c"] if self.dates[i] > not_before else None

    def bars_upto(self, date):
        import bisect
        i = bisect.bisect_right(self.dates, date)
        return self.rows[:i]

    def window_before(self, date, n):
        import bisect
        i = bisect.bisect_right(self.dates, date)
        return self.rows[max(0, i - n):i]


def calc_retention(series, date, field, lookback=20):
    vals = [r[field] for r in series.window_before(date, lookback) if field in r]
    if len(vals) < 5:
        return None
    cum = peak = 0
    for v in vals:
        cum += v
        if cum > peak:
            peak = cum
    return round(cum / peak, 2) if peak > 0 else None


def stat_line(label, records, width=30):
    line = f"  {label:<{width}}"
    if not records:
        return line + "  （0 筆）"
    for n in HOLD_DAYS:
        rets = [r["rets"][n] for r in records if n in r["rets"]]
        exs = [r["excess"][n] for r in records if n in r["excess"]]
        if not rets:
            line += f" | {n}D n=   0" + " " * 34
            continue
        k = sum(1 for x in rets if x > 0)
        lo, hi = wilson(k, len(rets))
        line += (f" | {n}D n={len(rets):>4} 勝{k / len(rets) * 100:3.0f}%[{lo:.0f}-{hi:.0f}] "
                 f"報{sum(rets) / len(rets):+5.1f}% 超額{(sum(exs) / len(exs) if exs else float('nan')):+5.1f}%")
    return line


def main():
    print("=" * 150)
    print("  DMI（+DI / −DI / ADX）當篩選條件 — 樣本內／樣本外")
    print("=" * 150)

    fails = selftest()
    if fails:
        print("⛔ DMI 實作自我測試沒過，結果不可信：")
        for f in fails:
            print("   -", f)
        return
    print("✅ DMI 實作自我測試通過（單調漲／單調跌／橫盤／資料不足 四組）")

    codes = set()
    for af in sorted(glob.glob(os.path.join(ALERTS_DIR, "alerts_*.json"))):
        with open(af, "r", encoding="utf-8") as f:
            for a in json.load(f).get("alerts", []):
                codes.add(a["code"])
    codes.add(BENCH_CODE)

    c = Counter()
    for code in codes:
        o = load_ohlc(code)
        if o:
            for r in o:
                c[r["t"]] += 1
    cal = sorted(d for d, n in c.items() if n >= MIN_STOCKS_PER_DAY and is_weekday(d))
    cal_set, cal_idx = set(cal), {d: i for i, d in enumerate(cal)}
    print(f"交易日曆：{cal[0]} ~ {cal[-1]}，{len(cal)} 個交易日")

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
        v = series.close_on(target)
        return v if v is not None else series.close_at_or_before(target, date)

    recs = []
    no_dmi = 0
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
                v = fwd(s, date, n)
                if v is None:
                    continue
                r = (v - a["close"]) / a["close"] * 100
                rets[n] = r
                if bench:
                    b0, bc = bench.close_on(date), fwd(bench, date, n)
                    if b0 and bc:
                        exs[n] = r - (bc - b0) / b0 * 100
            if not rets:
                continue
            bars = s.bars_upto(date)          # ⚠️ 只到警示日當天，無 lookahead
            if len(bars) < MIN_BARS:
                no_dmi += 1
                continue
            pdi, mdi_, adx = dmi(bars)
            if pdi is None:
                no_dmi += 1
                continue
            rf, rt = calc_retention(s, date, "fi"), calc_retention(s, date, "ti")
            cand = [x for x in (rf, rt) if x is not None]
            recs.append({
                "code": a["code"], "date": date, "market": a.get("market", ""),
                "close": a["close"], "score": a["score"],
                "pdi": pdi, "mdi": mdi_, "adx": adx,
                "retention": max(cand) if cand else None,
                "hurst": a.get("hurst"),
                "rets": rets, "excess": exs,
            })

    IS = [r for r in recs if r["date"] <= SPLIT_DATE]
    OOS = [r for r in recs if r["date"] > SPLIT_DATE]
    print(f"可用警示 {len(recs)} 筆（樣本內 {len(IS)}／樣本外 {len(OOS)}）；"
          f"因歷史不足算不出 DMI 而丟棄 {no_dmi} 筆")

    adxs = sorted(r["adx"] for r in recs)
    print(f"ADX 分佈：中位數 {adxs[len(adxs)//2]:.1f}，"
          f"10/25/75/90 百分位 = {adxs[len(adxs)//10]:.1f} / {adxs[len(adxs)//4]:.1f}"
          f" / {adxs[len(adxs)*3//4]:.1f} / {adxs[len(adxs)*9//10]:.1f}")

    groups = [
        ("全部警示（不篩）", lambda r: True),
        ("ADX < 20（無趨勢）", lambda r: r["adx"] < 20),
        ("ADX 20–25", lambda r: 20 <= r["adx"] < 25),
        ("ADX 25–40（趨勢確立）", lambda r: 25 <= r["adx"] < 40),
        ("ADX >= 40（極強趨勢）", lambda r: r["adx"] >= 40),
        ("+DI > −DI（多方）", lambda r: r["pdi"] > r["mdi"]),
        ("+DI <= −DI（空方）", lambda r: r["pdi"] <= r["mdi"]),
        ("ADX>=25 且 +DI>−DI", lambda r: r["adx"] >= 25 and r["pdi"] > r["mdi"]),
        ("ADX<20 且 +DI>−DI（蓄勢型）", lambda r: r["adx"] < 20 and r["pdi"] > r["mdi"]),
        ("ADX>=25 且 +DI>−DI 且 R_high",
         lambda r: r["adx"] >= 25 and r["pdi"] > r["mdi"]
         and r["retention"] is not None and r["retention"] >= 0.8),
        # ⭐ 排除型：不挑贏家，只剔掉一個明確爛的子集。
        #    比「選股條件」穩健，因為它不需要那個子集在下一段期間繼續是贏家，
        #    只需要它繼續是輸家。
        ("★排除 ADX>=40（其餘全收）", lambda r: r["adx"] < 40),
        ("★排除 ADX>=40 且 R_high",
         lambda r: r["adx"] < 40 and r["retention"] is not None and r["retention"] >= 0.8),
    ]

    for title, subset in [("【全期間】", recs), (f"【樣本內 <={SPLIT_DATE}】", IS),
                          (f"【樣本外 >{SPLIT_DATE}】", OOS)]:
        print("\n" + "-" * 150)
        print(title)
        for label, fn in groups:
            print(stat_line(label, [r for r in subset if fn(r)]))

    print("\n" + "=" * 150)
    print("【樣本內 vs 樣本外：10D 勝率是否翻掉】⭐ 基準不動但分組互換 ＝ 關係不穩定")
    print(f"  {'分組':<30}{'樣本內':>10}{'樣本外':>10}{'差':>9}")
    for label, fn in groups:
        a = [r["rets"][10] for r in IS if fn(r) and 10 in r["rets"]]
        b = [r["rets"][10] for r in OOS if fn(r) and 10 in r["rets"]]
        if not a or not b:
            continue
        wa = sum(1 for x in a if x > 0) / len(a) * 100
        wb = sum(1 for x in b if x > 0) / len(b) * 100
        print(f"  {label:<30}{wa:>9.0f}%{wb:>9.0f}%{wb - wa:>+8.0f}pt")
    print("=" * 150)


if __name__ == "__main__":
    main()
