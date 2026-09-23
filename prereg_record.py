# -*- coding: utf-8 -*-
"""
prereg_record.py — 預先登記的每日記錄器

⛔⛔ 這支**只記錄「今天有哪些股票符合哪個假設」，不計算任何報酬**。
   報酬要到 PREREGISTRATION.md 訂的開盲日之後，才由另一支程式從 OHLC 回算。
   在開盲前算報酬 ＝ 偷看 ＝ 這次驗證作廢。

規則凍結於 PREREGISTRATION.md（2026-09-24）。
⛔ **修改本檔的任何判定邏輯，等同修改預先登記，會讓已累積的記錄失效。**
   要改只能作廢重開一份新的預先登記。

輸出：prereg_log/prereg_YYYYMMDD.json（每日一檔，由 CI commit，git 時間戳即防竄改證據）
用法：python prereg_record.py [--force]
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import argparse
import glob
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")
MARGIN_DIR = os.path.join(SCRIPT_DIR, "margin_history")
HOLDERS_DIR = os.path.join(SCRIPT_DIR, "holders_history")
OUT_DIR = os.path.join(SCRIPT_DIR, "prereg_log")

# ===== 以下數值凍結於 PREREGISTRATION.md，⛔ 不得修改 =====
BIG_HOLDER_MIN = 50.0     # H1：400 張大戶（級距 12~15）占比門檻 %
ADX_EXCLUDE = 40.0        # H2：ADX >= 此值者排除
CHIP_WINDOW = 20          # H3：籌碼窗口（交易日）
CHIP_SLOPE_MAX = -0.2     # H3：融資餘額線斜率門檻 %/日
# =========================================================

sys.path.insert(0, SCRIPT_DIR)
from screen_persist import dmi_series


def slope(ys):
    n = len(ys)
    if n < 5:
        return None
    xm = (n - 1) / 2
    ym = sum(ys) / n
    den = sum((i - xm) ** 2 for i in range(n))
    if den == 0:
        return None
    return sum((i - xm) * (ys[i] - ym) for i in range(n)) / den


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    mkt = json.load(open(os.path.join(SCRIPT_DIR, "stock_market_type.json"), encoding="utf-8"))

    margin = {}
    for p in sorted(glob.glob(os.path.join(MARGIN_DIR, "margin_*.json")))[-60:]:
        d = json.load(open(p, encoding="utf-8"))
        margin[d["date"]] = {c: dict(zip(d["fields"], r)) for c, r in d["data"].items()}
    hfiles = sorted(glob.glob(os.path.join(HOLDERS_DIR, "holders_*.json")))
    if not hfiles:
        print("⛔ 沒有 holders_history，H1 無法判定，不記錄")
        return
    hd = json.load(open(hfiles[-1], encoding="utf-8"))
    holders = hd["data"]

    # 以最新的 OHLC 日期為記錄日
    ref = json.load(open(os.path.join(OHLC_DIR, "2330.json"), encoding="utf-8"))
    date = ref[-1]["t"]

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"prereg_{date}.json")
    if os.path.exists(path) and not args.force:
        have = sorted(f[7:15] for f in os.listdir(OUT_DIR) if f.startswith("prereg_"))
        print(f"✅ {date} 已記錄，跳過（累積 {len(have)} 天：{have[0]} ~ {have[-1]}）")
        return

    h1, h2, h3 = [], [], []
    universe = 0
    no_holder = no_margin = 0

    for p in glob.glob(os.path.join(OHLC_DIR, "*.json")):
        code = os.path.basename(p)[:-5]
        if len(code) != 4 or not code.isdigit() or mkt.get(code) not in ("上市", "上櫃"):
            continue
        try:
            bars = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if len(bars) < 80 or bars[-1]["t"] != date:
            continue
        universe += 1

        # H1：400 張大戶 > 50%
        h = holders.get(code)
        if h is None:
            no_holder += 1
        elif sum(h[0][11:]) > BIG_HOLDER_MIN:
            h1.append(code)

        # H2：排除 ADX >= 40（記錄的是「通過排除後留下的」）
        pdi, mdi = dmi_series(bars)
        adx_ok = False
        if pdi and pdi[-1] is not None:
            # 重算 ADX（dmi_series 只回 DI，ADX 另外算）
            from backtest_dmi import dmi as dmi_last
            _, _, adx = dmi_last(bars)
            if adx is not None and adx < ADX_EXCLUDE:
                adx_ok = True
        if adx_ok:
            h2.append(code)

        # H3：籌碼反向（零軸版）
        ts = [b["t"] for b in bars if b["t"] in margin and code in margin[b["t"]]][-CHIP_WINDOW:]
        if len(ts) < 10:
            no_margin += 1
        else:
            flows = {b["t"]: b.get("fi", 0) + b.get("ti", 0) for b in bars}
            acc, cum = 0, []
            for t in ts:
                acc += flows.get(t, 0)
                cum.append(acc)
            mbs = [margin[t][code]["mb"] for t in ts]
            isl, msl = slope(cum), slope(mbs)
            base = abs(sum(mbs) / len(mbs))
            mp = (msl / base * 100) if (msl is not None and base > 1e-9) else None
            if (cum[-1] > 0 and mbs[-1] - mbs[0] < 0 and isl is not None and isl > 0
                    and mp is not None and mp < CHIP_SLOPE_MAX):
                h3.append(code)

    out = {
        "date": date,
        "prereg": "PREREGISTRATION.md 2026-09-24",
        "frozen": {"BIG_HOLDER_MIN": BIG_HOLDER_MIN, "ADX_EXCLUDE": ADX_EXCLUDE,
                   "CHIP_WINDOW": CHIP_WINDOW, "CHIP_SLOPE_MAX": CHIP_SLOPE_MAX},
        "source": {"holders_date": hd["date"], "margin_latest": max(margin) if margin else None},
        "universe": universe,
        "missing": {"holders": no_holder, "margin": no_margin},
        "H1_big_holder": sorted(h1),
        "H2_adx_ok": sorted(h2),
        "H3_chip_diverge": sorted(h3),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    inter = sorted(set(h1) & set(h2))
    print(f"✅ {date} 已記錄　母體 {universe} 支")
    print(f"   H1 大戶>50%        {len(h1):>5} 支（大戶資料日 {hd['date']}）")
    print(f"   H2 ADX<40（留下）   {len(h2):>5} 支")
    print(f"   H3 籌碼反向        {len(h3):>5} 支")
    print(f"   H1∩H2（H4 用）     {len(inter):>5} 支")
    print(f"   配不到：大戶 {no_holder} 支、融資 {no_margin} 支")
    have = sorted(f[7:15] for f in os.listdir(OUT_DIR) if f.startswith("prereg_"))
    print(f"   累積 {len(have)} 天：{have[0]} ~ {have[-1]}")
    print("\n⛔ 本檔不計算任何報酬。開盲日與判定標準見 PREREGISTRATION.md")


if __name__ == "__main__":
    main()
