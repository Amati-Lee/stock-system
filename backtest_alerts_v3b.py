"""
起飛警示回測 v3b — 比較有/無 Hurst 條件的差異
只讀不寫
"""
import json
import os
import glob
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
    if not records:
        print(f"  {label}: 0 筆")
        return
    results = defaultdict(list)
    for rec in records:
        for n in HOLD_DAYS:
            if n in rec["rets"]:
                results[n].append(rec["rets"][n])
    sample = len(results.get(HOLD_DAYS[0], []))
    line = f"  {label:<50} n={sample:>4}  |"
    for n in HOLD_DAYS:
        rets = results.get(n, [])
        if not rets:
            line += f"  {n}D: N/A        |"
            continue
        win = sum(1 for r in rets if r > 0) / len(rets) * 100
        avg = sum(rets) / len(rets)
        med = sorted(rets)[len(rets) // 2]
        line += f"  {n}D: {win:4.0f}% {avg:+6.1f}% (med{med:+5.1f}%) |"
    print(line)


def main():
    alert_files = sorted(glob.glob(os.path.join(ALERTS_DIR, "alerts_*.json")))
    print(f"{len(alert_files)} days\n")

    all_records = []

    for af in alert_files:
        with open(af, "r", encoding="utf-8") as f:
            fdata = json.load(f)
        alert_date = fdata["date"].replace("-", "")
        for a in fdata.get("alerts", []):
            code = a["code"]
            ohlc_list = load_ohlc(code)
            if not ohlc_list:
                continue

            # Retention
            r_foreign = calc_retention(ohlc_list, alert_date, "fi")
            r_trust = calc_retention(ohlc_list, alert_date, "ti")
            r_val = None
            if r_foreign is not None and r_trust is not None:
                r_val = max(r_foreign, r_trust)
            elif r_foreign is not None:
                r_val = r_foreign
            elif r_trust is not None:
                r_val = r_trust

            rets = {}
            for n in HOLD_DAYS:
                fc = find_close_after_n_days(ohlc_list, alert_date, n)
                if fc is not None:
                    rets[n] = (fc - a["close"]) / a["close"] * 100
            if not rets:
                continue

            vol_ratio = a["volume"] / a["avg_volume"] if a["avg_volume"] > 0 else 0
            h = a.get("hurst")

            all_records.append({
                "code": code,
                "close": a["close"],
                "chg_pct": a["chg_pct"],
                "hurst": h,
                "retention": r_val,
                "vol_ratio": vol_ratio,
                "market": a.get("market", ""),
                "rets": rets,
            })

    print(f"Total records: {len(all_records)}\n")
    print("=" * 140)

    # 最強策略條件（不含 Hurst）
    def best_no_hurst(r):
        return (r["retention"] is not None and r["retention"] >= 0.8 and
                "興櫃" not in r["market"] and
                100 <= r["close"] < 500 and
                1.5 <= r["vol_ratio"] < 3)

    # 最強策略條件（含 Hurst）
    def best_with_hurst(r):
        return (best_no_hurst(r) and
                r["hurst"] is not None and
                0.45 <= r["hurst"] < 0.55)

    # R_high 基礎（不含 Hurst）
    def r_high_only(r):
        return r["retention"] is not None and r["retention"] >= 0.8

    # R_high + H_random
    def r_high_h_random(r):
        return (r_high_only(r) and
                r["hurst"] is not None and
                0.45 <= r["hurst"] < 0.55)

    print("  A vs B: Hurst 有沒有差?")
    print("=" * 140)

    print("\n--- R_high alone vs R_high + H_random ---")
    print_results("R_high (no Hurst filter)", [r for r in all_records if r_high_only(r)])
    print_results("R_high + H_random (0.45-0.55)", [r for r in all_records if r_high_h_random(r)])
    # Also test other Hurst ranges with R_high
    print_results("R_high + H_trend (>=0.6)", [r for r in all_records if r_high_only(r) and r["hurst"] is not None and r["hurst"] >= 0.6])
    print_results("R_high + H_weak (0.55-0.6)", [r for r in all_records if r_high_only(r) and r["hurst"] is not None and 0.55 <= r["hurst"] < 0.6])
    print_results("R_high + H_revert (<0.45)", [r for r in all_records if r_high_only(r) and r["hurst"] is not None and r["hurst"] < 0.45])

    print("\n--- Best combo: with vs without Hurst ---")
    print_results("R_high+non-OTC+100-500+vol1.5-3x (no Hurst)", [r for r in all_records if best_no_hurst(r)])
    print_results("R_high+non-OTC+100-500+vol1.5-3x+H_random", [r for r in all_records if best_with_hurst(r)])
    # Without Hurst but exclude H_trend
    def best_exclude_trend(r):
        return (best_no_hurst(r) and
                (r["hurst"] is None or r["hurst"] < 0.6))
    print_results("R_high+non-OTC+100-500+vol1.5-3x+H<0.6", [r for r in all_records if best_exclude_trend(r)])

    print("=" * 140)


if __name__ == "__main__":
    main()
