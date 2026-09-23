# -*- coding: utf-8 -*-
"""
screen_persist.py — 新版條件的「現況篩選」：**持續狀態版**

⛔⛔ 和 screen_new.py 的根本差別：
   screen_new.py 問的是「今天有沒有發生交叉」（事件），
   這一支問的是「這個狀態已經**持續**幾天」（狀態）。
   使用者 2026-09-24 澄清：「不管 macd/rsi/dmi/kd 都不是當天，是持續發生就要提出注意」。
   ⇒ 交叉當天只有 3.7%（KD）、8.1%（RSI），那是事件的稀少性，不是訊號強度。

條件（N = 連續天數，見 --days）：
  1. KD 多方      K > D        連續 N 天
  2. MACD 零軸上  DIF > 0      連續 N 天
  3. DMI 多方     +DI > −DI    連續 N 天
  4. RSI 多方     RSI6 > RSI12 連續 N 天
  5. 籌碼反向     20 日內，三個都要成立：
                  (a) 法人買賣超**淨額 > 0**（零軸上）
                  (b) 融資餘額**淨變化 < 0**（零軸下）⛔ 使用者：「融資在零軸上我不要」
                  (c) 融資餘額線斜率 < MARG_SLOPE_MAX（強度，不要幾乎持平的）
                  ⛔⛔ 只用斜率會漏兩種：①斜率為負但淨額為正（34 支，如 1312 國喬
                     斜率 −0.48% 但融資淨 +612）②法人累積線斜率為正但淨額為負
                     （如 6223 旺矽 法人淨 −1,062）。
                     **斜率只看形狀，不看終點落在零軸哪一邊** —— 2026-09-24 使用者指出。
  6. 400張大戶    集保級距 12~15 合計 > 50%（週資料，狀態）

只讀不寫。⛔ 只回答「今天有幾支符合」，不回答「會不會賺錢」。
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import argparse
import glob
import json
import os

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")
MARGIN_DIR = os.path.join(SCRIPT_DIR, "margin_history")
HOLDERS_DIR = os.path.join(SCRIPT_DIR, "holders_history")

MARG_WINDOW = 20
MARG_SLOPE_MAX = -0.2      # 融資斜率門檻 %/日（使用者 2026-09-24 定）
BIG_HOLDER_MIN = 50.0      # 400 張大戶占比門檻 %

sys.path.insert(0, SCRIPT_DIR)
from backtest_dmi import dmi as dmi_last        # 已驗過的單點版，用來當回歸對照
from screen_new import ema, ewm_alpha, calc_rsi_series


# ---------------------------------------------------------------- 指標（序列版）
def kd_series(bars, period=9):
    """回傳與 bars 等長的 (K, D)，前 period-1 個為 None"""
    if len(bars) < period + 1:
        return [], []
    rsv = []
    for i in range(period - 1, len(bars)):
        w = bars[i - period + 1:i + 1]
        hi = max(b["h"] for b in w)
        lo = min(b["l"] for b in w)
        rsv.append(50.0 if hi == lo else 100.0 * (bars[i]["c"] - lo) / (hi - lo))
    k = ewm_alpha(rsv, 1 / 3)
    d = ewm_alpha(k, 1 / 3)
    pad = [None] * (period - 1)
    return pad + k, pad + d


def macd_dif_series(closes, fast=12, slow=26):
    if len(closes) < slow + 2:
        return []
    ef, es = ema(closes, fast), ema(closes, slow)
    return [a - b for a, b in zip(ef, es)]


def dmi_series(bars, period=14):
    """一次算完整條 +DI / −DI，與 bars 等長（前面不足處為 None）。
    ⭐ 最後一點必須和已驗過的 backtest_dmi.dmi() 一致 —— 下面有回歸對照。"""
    n = len(bars)
    if n < period * 2 + 1:
        return [], []
    trs, pdms, mdms = [], [], []
    for i in range(1, n):
        h, l = bars[i]["h"], bars[i]["l"]
        ph, pl, pc = bars[i - 1]["h"], bars[i - 1]["l"], bars[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        up, dn = h - ph, pl - l
        pdms.append(up if (up > dn and up > 0) else 0.0)
        mdms.append(dn if (dn > up and dn > 0) else 0.0)

    def wilder(seq):
        s = sum(seq[:period])
        out = [s]
        for x in seq[period:]:
            s = s - s / period + x
            out.append(s)
        return out

    tr_s, pdm_s, mdm_s = wilder(trs), wilder(pdms), wilder(mdms)
    # tr_s[j] 對應 bars 的索引 period + j
    pdi = [None] * n
    mdi = [None] * n
    for j, (tr, pd_, md) in enumerate(zip(tr_s, pdm_s, mdm_s)):
        idx = period + j
        if idx >= n or tr <= 0:
            continue
        pdi[idx] = 100.0 * pd_ / tr
        mdi[idx] = 100.0 * md / tr
    return pdi, mdi


def streak(flags):
    """從尾端往回數，連續為 True 的長度"""
    c = 0
    for v in reversed(flags):
        if v:
            c += 1
        else:
            break
    return c


def selftest(sample_bars):
    """⭐ 序列版的最後一點要和已驗過的單點版一致"""
    fails = []
    for code, bars in sample_bars:
        p_s, m_s = dmi_series(bars)
        if not p_s or p_s[-1] is None:
            continue
        p1, m1, _ = dmi_last(bars)
        if abs(p_s[-1] - p1) > 0.01 or abs(m_s[-1] - m1) > 0.01:
            fails.append(f"{code}: 序列版 +DI={p_s[-1]:.2f}/−DI={m_s[-1]:.2f} "
                         f"≠ 單點版 {p1}/{m1}")
    return fails


# ---------------------------------------------------------------- 主程式
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, nargs="*", default=[1, 3, 5, 10, 20],
                    help="要測試的「連續天數」清單")
    ap.add_argument("--show", type=int, default=5, help="列出名單的那個天數")
    args = ap.parse_args()

    mkt = json.load(open(os.path.join(SCRIPT_DIR, "stock_market_type.json"), encoding="utf-8"))
    names = json.load(open(os.path.join(SCRIPT_DIR, "stock_names_all.json"), encoding="utf-8"))

    margin = {}
    for p in sorted(glob.glob(os.path.join(MARGIN_DIR, "margin_*.json")))[-40:]:
        d = json.load(open(p, encoding="utf-8"))
        margin[d["date"]] = {c: dict(zip(d["fields"], r)) for c, r in d["data"].items()}
    hfiles = sorted(glob.glob(os.path.join(HOLDERS_DIR, "holders_*.json")))
    hd = json.load(open(hfiles[-1], encoding="utf-8"))
    holders = hd["data"]

    rows, sample = [], []
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
        closes = [b["c"] for b in bars]

        k, d_ = kd_series(bars)
        dif = macd_dif_series(closes)
        r6 = calc_rsi_series(closes, 6)
        r12 = calc_rsi_series(closes, 12)
        pdi, mdi = dmi_series(bars)
        if not (k and dif and r6 and r12 and pdi):
            continue
        if len(sample) < 20:
            sample.append((code, bars))

        m = min(len(k), len(dif), len(r6), len(r12), len(pdi), len(bars))
        f_kd = [k[i] is not None and d_[i] is not None and k[i] > d_[i] for i in range(m)]
        f_macd = [dif[i] > 0 for i in range(m)]
        f_rsi = [r6[i] is not None and r12[i] is not None and r6[i] > r12[i] for i in range(m)]
        f_dmi = [pdi[i] is not None and mdi[i] is not None and pdi[i] > mdi[i] for i in range(m)]

        # 條件 5（趨勢型，與天數無關）
        ts = [b["t"] for b in bars if b["t"] in margin and code in margin[b["t"]]][-MARG_WINDOW:]
        div, mpct = False, None
        if len(ts) >= 10:
            flows = {b["t"]: b.get("fi", 0) + b.get("ti", 0) for b in bars}
            cum, acc = [], 0
            for t in ts:
                acc += flows.get(t, 0)
                cum.append(acc)
            mbs = [margin[t][code]["mb"] for t in ts]
            x = np.arange(len(ts), dtype=float)
            isl = float(np.polyfit(x, np.array(cum, float), 1)[0])
            msl = float(np.polyfit(x, np.array(mbs, float), 1)[0])
            base = abs(float(np.mean(mbs)))
            mpct = (msl / base * 100) if base > 1e-9 else None
            inst_net = cum[-1]              # 法人 20 日淨額（零軸上為正）
            marg_net = mbs[-1] - mbs[0]     # 融資 20 日淨變化（零軸下為負）
            div = (inst_net > 0 and marg_net < 0            # 零軸方向
                   and isl > 0                              # 法人線在爬
                   and mpct is not None and mpct < MARG_SLOPE_MAX)   # 融資降得夠快

        h = holders.get(code)
        big = sum(h[0][11:]) if h else None
        rows.append({
            "code": code, "name": names.get(code, ""), "market": mkt[code],
            "close": closes[-1],
            "s_kd": streak(f_kd), "s_macd": streak(f_macd),
            "s_rsi": streak(f_rsi), "s_dmi": streak(f_dmi),
            "div": div, "mpct": mpct,
            "big": big, "c6": (big is not None and big > BIG_HOLDER_MIN),
        })

    fails = selftest(sample)
    print("=" * 112)
    print("  新版條件現況篩選 — **持續狀態版**   ⛔ 只回答「今天有幾支」，不回答「會不會賺」")
    print("=" * 112)
    if fails:
        print("⛔ DMI 序列版與已驗過的單點版對不上，結果不可信：")
        for f in fails:
            print("   -", f)
        return
    print(f"✅ DMI 序列版 vs 已驗過的單點版：{len(sample)} 支抽樣全部一致")
    print(f"母體 {len(rows)} 支　融資斜率門檻 {MARG_SLOPE_MAX}%/日　大戶門檻 {BIG_HOLDER_MIN}%")
    print(f"條件5（籌碼反向）單獨：{sum(1 for r in rows if r['div'])} 支"
          f"　條件6（大戶）單獨：{sum(1 for r in rows if r['c6'])} 支"
          f"　（這兩條與天數無關）")

    print("\n" + "-" * 112)
    print("【各條件「連續 N 天成立」的支數】")
    hdr = f"  {'條件':<22}" + "".join(f"{f'連{n}天':>10}" for n in args.days)
    print(hdr)
    for label, key in [("1. KD 多方 K>D", "s_kd"), ("2. MACD DIF>0", "s_macd"),
                       ("3. DMI +DI>−DI", "s_dmi"), ("4. RSI6>RSI12", "s_rsi")]:
        line = f"  {label:<22}"
        for n in args.days:
            line += f"{sum(1 for r in rows if r[key] >= n):>10}"
        print(line)

    print("\n" + "-" * 112)
    print("【四個技術條件同時連續 N 天，再加籌碼與大戶】")
    print(f"  {'連續天數':<10}{'四項皆連N天':>14}{'＋籌碼反向':>13}{'＋400張大戶>50%':>18}")
    for n in args.days:
        a = [r for r in rows if min(r["s_kd"], r["s_macd"], r["s_dmi"], r["s_rsi"]) >= n]
        b = [r for r in a if r["div"]]
        c = [r for r in b if r["c6"]]
        print(f"  {f'連 {n} 天':<10}{len(a):>14}{len(b):>13}{len(c):>18}")

    n = args.show
    hit = sorted([r for r in rows
                  if min(r["s_kd"], r["s_macd"], r["s_dmi"], r["s_rsi"]) >= n
                  and r["div"] and r["c6"]],
                 key=lambda x: -min(x["s_kd"], x["s_macd"], x["s_dmi"], x["s_rsi"]))
    print("\n" + "=" * 112)
    print(f"【全部條件、連續 {n} 天以上：{len(hit)} 支】")
    if hit:
        print(f"  {'代號':<7}{'名稱':<12}{'市場':<6}{'收盤':>9}"
              f"{'KD':>6}{'MACD':>7}{'DMI':>6}{'RSI':>6}{'最短':>6}"
              f"{'大戶%':>8}{'融資斜率':>10}")
        for r in hit:
            mn = min(r["s_kd"], r["s_macd"], r["s_dmi"], r["s_rsi"])
            print(f"  {r['code']:<7}{r['name']:<12}{r['market']:<6}{r['close']:>9.2f}"
                  f"{r['s_kd']:>6}{r['s_macd']:>7}{r['s_dmi']:>6}{r['s_rsi']:>6}{mn:>6}"
                  f"{r['big']:>8.2f}{r['mpct']:>9.2f}%")
    print("=" * 112)


if __name__ == "__main__":
    main()
