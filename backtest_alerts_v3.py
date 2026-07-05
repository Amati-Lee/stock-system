"""
起飛警示回測 v3 — 在 H_random + R_high 基礎上加精選條件
只讀不寫
"""
import json
import os
import glob
import numpy as np
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ALERTS_DIR = os.path.join(SCRIPT_DIR, "alerts_history")
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")

HOLD_DAYS = [5, 10, 20]

ohlc_cache = {}


def load_ohlc(code):
    if code in ohlc_cache:
        return ohlc_cache[code]
    path = os.path.join(OHLC_DIR, f"{code}.json")
    if not os.path.exists(path):
        ohlc_cache[code] = None
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    ohlc_cache[code] = data
    return data


def find_close_after_n_days(ohlc_list, alert_date, n):
    dates = [r["t"] for r in ohlc_list]
    try:
        idx = dates.index(alert_date)
    except ValueError:
        later = [i for i, d in enumerate(dates) if d >= alert_date]
        if not later:
            return None
        idx = later[0]
    target_idx = idx + n
    if target_idx >= len(ohlc_list):
        return None
    return ohlc_list[target_idx]["c"]


def calc_retention(ohlc_list, alert_date, field, lookback=20):
    dates = [r["t"] for r in ohlc_list]
    try:
        idx = dates.index(alert_date)
    except ValueError:
        later = [i for i, d in enumerate(dates) if d >= alert_date]
        if not later:
            return None
        idx = later[0]
    start = max(0, idx - lookback + 1)
    window = ohlc_list[start:idx + 1]
    vals = [r.get(field) for r in window if field in r]
    if len(vals) < 5:
        return None
    cum = 0
    peak = 0
    for v in vals:
        cum += v
        if cum > peak:
            peak = cum
    if peak <= 0:
        return None
    return round(cum / peak, 2)


def print_results(label, records):
    """印出一組 records 的績效"""
    if not records:
        print(f"  {label}: 0 筆")
        return

    results = defaultdict(list)
    for rec in records:
        for n in HOLD_DAYS:
            if n in rec["rets"]:
                results[n].append(rec["rets"][n])

    sample = len(results.get(HOLD_DAYS[0], []))
    line = f"  {label:<40} n={sample:>4}  |"
    for n in HOLD_DAYS:
        rets = results.get(n, [])
        if not rets:
            line += f"  {n}D: N/A        |"
            continue
        win = sum(1 for r in rets if r > 0) / len(rets) * 100
        avg = sum(rets) / len(rets)
        med = sorted(rets)[len(rets) // 2]
        line += f"  {n}D: {win:4.0f}% {avg:+6.1f}% (中{med:+5.1f}%) |"
    print(line)


def main():
    alert_files = sorted(glob.glob(os.path.join(ALERTS_DIR, "alerts_*.json")))
    print(f"找到 {len(alert_files)} 天警示歷史\n")

    # 收集所有符合 base 條件 (H_random + R_high) 的記錄
    all_base = []

    for af in alert_files:
        with open(af, "r", encoding="utf-8") as f:
            fdata = json.load(f)

        alert_date = fdata["date"].replace("-", "")
        alerts = fdata.get("alerts", [])

        for a in alerts:
            code = a["code"]
            h = a.get("hurst")
            if h is None or not (0.45 <= h < 0.55):
                continue

            ohlc_list = load_ohlc(code)
            if not ohlc_list:
                continue

            # 籌碼維持率
            r_foreign = calc_retention(ohlc_list, alert_date, "fi")
            r_trust = calc_retention(ohlc_list, alert_date, "ti")
            r_val = None
            if r_foreign is not None and r_trust is not None:
                r_val = max(r_foreign, r_trust)
            elif r_foreign is not None:
                r_val = r_foreign
            elif r_trust is not None:
                r_val = r_trust

            if r_val is None or r_val < 0.8:
                continue

            # 計算報酬
            rets = {}
            for n in HOLD_DAYS:
                fc = find_close_after_n_days(ohlc_list, alert_date, n)
                if fc is not None:
                    rets[n] = (fc - a["close"]) / a["close"] * 100

            if not rets:
                continue

            vol_ratio = a["volume"] / a["avg_volume"] if a["avg_volume"] > 0 else 0
            market = a.get("market", "")

            all_base.append({
                "code": code,
                "date": alert_date,
                "close": a["close"],
                "chg_pct": a["chg_pct"],
                "score": a["score"],
                "hurst": h,
                "retention": r_val,
                "vol_ratio": vol_ratio,
                "market": market,
                "rets": rets,
            })

    print(f"H_random + R_high 基礎樣本: {len(all_base)} 筆\n")
    print("=" * 120)
    print("  基礎 vs 各精選條件")
    print("=" * 120)

    # 基礎
    print_results("基礎 (H_random + R_high)", all_base)
    print("-" * 120)

    # --- 條件 1: 股價區間 ---
    print("\n【股價區間】")
    for lo, hi, label in [(0, 50, "<50"), (50, 100, "50-100"), (100, 300, "100-300"),
                           (300, 500, "300-500"), (500, 9999, ">500")]:
        subset = [r for r in all_base if lo <= r["close"] < hi]
        print_results(f"  股價 {label}", subset)

    # --- 條件 2: 量比 ---
    print("\n【量比 (volume / avg_volume)】")
    for lo, hi, label in [(1.0, 1.5, "1-1.5x"), (1.5, 3.0, "1.5-3x"),
                           (3.0, 5.0, "3-5x"), (5.0, 999, ">5x")]:
        subset = [r for r in all_base if lo <= r["vol_ratio"] < hi]
        print_results(f"  量比 {label}", subset)

    # --- 條件 3: 當日漲幅 ---
    print("\n【當日漲幅】")
    for lo, hi, label in [(-99, 3, "<3%"), (3, 5, "3-5%"), (5, 7, "5-7%"),
                           (7, 10, "7-10%"), (10, 99, "漲停10%+")]:
        subset = [r for r in all_base if lo <= r["chg_pct"] < hi]
        print_results(f"  漲幅 {label}", subset)

    # --- 條件 4: 市場別 ---
    print("\n【市場別】")
    markets = set(r["market"] for r in all_base)
    for m in sorted(markets):
        subset = [r for r in all_base if r["market"] == m]
        label = m if m else "未知"
        print_results(f"  {label}", subset)

    # --- 條件 5: 分數 ---
    print("\n【分數】")
    for s_lo, s_hi, label in [(8, 9, "8分"), (9, 10, "9分"), (10, 11, "10分"), (11, 99, "11+分")]:
        subset = [r for r in all_base if s_lo <= r["score"] < s_hi]
        print_results(f"  {label}", subset)

    # === 組合策略測試 ===
    print("\n" + "=" * 120)
    print("  最佳組合候選")
    print("=" * 120)

    combos = [
        ("排除興櫃", lambda r: "興櫃" not in r["market"]),
        ("排除興櫃 + 股價>=50", lambda r: "興櫃" not in r["market"] and r["close"] >= 50),
        ("排除興櫃 + 量比1.5-5x", lambda r: "興櫃" not in r["market"] and 1.5 <= r["vol_ratio"] < 5),
        ("排除興櫃 + 漲幅<7%", lambda r: "興櫃" not in r["market"] and r["chg_pct"] < 7),
        ("排除興櫃 + 股價50-500 + 量比1.5-5x", lambda r: "興櫃" not in r["market"] and 50 <= r["close"] < 500 and 1.5 <= r["vol_ratio"] < 5),
        ("排除興櫃 + 股價50-500 + 漲幅<7%", lambda r: "興櫃" not in r["market"] and 50 <= r["close"] < 500 and r["chg_pct"] < 7),
        ("排除興櫃 + 量比1.5-5x + 漲幅<7%", lambda r: "興櫃" not in r["market"] and 1.5 <= r["vol_ratio"] < 5 and r["chg_pct"] < 7),
        ("排除興櫃 + 股價50-500 + 量比1.5-5x + 漲幅<7%", lambda r: "興櫃" not in r["market"] and 50 <= r["close"] < 500 and 1.5 <= r["vol_ratio"] < 5 and r["chg_pct"] < 7),
        ("排除興櫃 + 股價100-500 + 量比1.5-3x", lambda r: "興櫃" not in r["market"] and 100 <= r["close"] < 500 and 1.5 <= r["vol_ratio"] < 3),
        ("排除興櫃 + 股價100-500 + 量比1.5-3x + 漲幅<7%", lambda r: "興櫃" not in r["market"] and 100 <= r["close"] < 500 and 1.5 <= r["vol_ratio"] < 3 and r["chg_pct"] < 7),
    ]

    for label, fn in combos:
        subset = [r for r in all_base if fn(r)]
        print_results(label, subset)

    print("=" * 120)


if __name__ == "__main__":
    main()
