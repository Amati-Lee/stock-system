"""
全股票 Hurst + 籌碼 + 漲停 + 量增 組合回測
測試能否用這些條件取代起飛警示
只讀不寫
"""
import json
import os
import glob
import numpy as np
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")

HOLD_DAYS = [5, 10, 20]


def hurst_exponent(closes, min_window=10):
    prices = np.array(closes, dtype=float)
    if len(prices) < min_window * 4 + 1:
        return None
    ts = np.diff(np.log(prices))
    n = len(ts)
    if n < min_window * 4:
        return None
    max_k = n // min_window
    sizes = []
    rs_means = []
    for k in range(min_window, max_k * min_window + 1, min_window):
        rs_list = []
        for start in range(0, n - k + 1, k):
            segment = ts[start:start + k]
            mean = segment.mean()
            deviate = np.cumsum(segment - mean)
            r = deviate.max() - deviate.min()
            s = segment.std(ddof=1)
            if s > 0:
                rs_list.append(r / s)
        if rs_list:
            sizes.append(k)
            rs_means.append(np.mean(rs_list))
    if len(sizes) < 3:
        return None
    log_sizes = np.log(sizes)
    log_rs = np.log(rs_means)
    H = np.polyfit(log_sizes, log_rs, 1)[0]
    return round(float(H), 3)


def calc_retention(ohlc_list, idx, field, lookback=20):
    """籌碼維持率：累積買超 / 歷史峰值"""
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


def has_limit_up(ohlc_list, idx, lookback=10):
    """近 N 天內是否有漲停（漲幅 >= 9.5%）"""
    start = max(0, idx - lookback + 1)
    for i in range(start, idx + 1):
        if i == 0:
            continue
        prev_c = ohlc_list[i - 1]["c"]
        if prev_c > 0:
            chg = (ohlc_list[i]["c"] - prev_c) / prev_c * 100
            if chg >= 9.5:
                return True
    return False


def vol_ratio(ohlc_list, idx, avg_days=20):
    """當日量 / 近 N 日均量"""
    if idx < avg_days:
        return None
    cur_vol = ohlc_list[idx].get("v", 0)
    if cur_vol <= 0:
        return None
    vols = [ohlc_list[i].get("v", 0) for i in range(idx - avg_days, idx)]
    avg = sum(vols) / len(vols) if vols else 0
    if avg <= 0:
        return None
    return round(cur_vol / avg, 2)


def print_results(label, records):
    if not records:
        print(f"  {label}: 0 samples")
        return
    results = defaultdict(list)
    for rec in records:
        for n in HOLD_DAYS:
            if n in rec:
                results[n].append(rec[n])
    sample = len(results.get(HOLD_DAYS[0], []))
    line = f"  {label:<55} n={sample:>5}  |"
    for n in HOLD_DAYS:
        rets = results.get(n, [])
        if not rets:
            line += f"  {n}D: N/A          |"
            continue
        win = sum(1 for r in rets if r > 0) / len(rets) * 100
        avg = sum(rets) / len(rets)
        med = sorted(rets)[len(rets) // 2]
        line += f"  {n}D: {win:4.0f}% {avg:+6.1f}% (med{med:+5.1f}%) |"
    print(line)


def main():
    ohlc_files = sorted(glob.glob(os.path.join(OHLC_DIR, "*.json")))
    print(f"OHLC files: {len(ohlc_files)}")

    TEST_OFFSETS = list(range(20, 201, 5))  # 20, 25, 30, ... 200

    all_records = []
    skipped = 0

    for fi, fpath in enumerate(ohlc_files):
        if fi % 2000 == 0:
            print(f"  processing {fi}/{len(ohlc_files)}...")

        with open(fpath, "r", encoding="utf-8") as f:
            ohlc = json.load(f)

        if len(ohlc) < 120:
            skipped += 1
            continue

        closes_all = [r["c"] for r in ohlc]

        for offset in TEST_OFFSETS:
            test_idx = len(ohlc) - offset
            if test_idx < 80 or test_idx + max(HOLD_DAYS) >= len(ohlc):
                continue

            entry_price = closes_all[test_idx]
            if entry_price <= 0:
                continue

            # Hurst
            h = hurst_exponent(closes_all[:test_idx + 1])

            # Retention
            r_fi = calc_retention(ohlc, test_idx, "fi")
            r_ti = calc_retention(ohlc, test_idx, "ti")
            r_val = None
            if r_fi is not None and r_ti is not None:
                r_val = max(r_fi, r_ti)
            elif r_fi is not None:
                r_val = r_fi
            elif r_ti is not None:
                r_val = r_ti

            # Limit up
            limit_up_5 = has_limit_up(ohlc, test_idx, 5)
            limit_up_10 = has_limit_up(ohlc, test_idx, 10)

            # Volume ratio
            vr = vol_ratio(ohlc, test_idx)

            # Daily change
            chg = (closes_all[test_idx] - closes_all[test_idx - 1]) / closes_all[test_idx - 1] * 100 if test_idx > 0 else 0

            # Returns
            rets = {}
            for n in HOLD_DAYS:
                future_idx = test_idx + n
                if future_idx < len(ohlc):
                    rets[n] = (closes_all[future_idx] - entry_price) / entry_price * 100

            if not rets:
                continue

            rec = {
                "hurst": h,
                "retention": r_val,
                "limit_up_5": limit_up_5,
                "limit_up_10": limit_up_10,
                "vol_ratio": vr,
                "close": entry_price,
                "chg": chg,
            }
            rec.update(rets)
            all_records.append(rec)

    print(f"\nTotal samples: {len(all_records)} (skipped {skipped} short OHLC)")

    # ========== Analysis ==========
    print(f"\n{'=' * 140}")
    print("  Section 1: Hurst alone (all stocks)")
    print(f"{'=' * 140}")
    print_results("ALL", all_records)
    print()
    for h_label, h_fn in [
        ("H_trend (>=0.6)", lambda r: r["hurst"] is not None and r["hurst"] >= 0.6),
        ("H_weak (0.55-0.6)", lambda r: r["hurst"] is not None and 0.55 <= r["hurst"] < 0.6),
        ("H_random (0.45-0.55)", lambda r: r["hurst"] is not None and 0.45 <= r["hurst"] < 0.55),
        ("H_revert (<0.45)", lambda r: r["hurst"] is not None and r["hurst"] < 0.45),
    ]:
        print_results(h_label, [r for r in all_records if h_fn(r)])

    print(f"\n{'=' * 140}")
    print("  Section 2: Retention alone")
    print(f"{'=' * 140}")
    for label, fn in [
        ("R_high (>=0.8)", lambda r: r["retention"] is not None and r["retention"] >= 0.8),
        ("R_mid (0.5-0.8)", lambda r: r["retention"] is not None and 0.5 <= r["retention"] < 0.8),
        ("R_low (<0.5)", lambda r: r["retention"] is not None and r["retention"] < 0.5),
        ("R_none (no data)", lambda r: r["retention"] is None),
    ]:
        print_results(label, [r for r in all_records if fn(r)])

    print(f"\n{'=' * 140}")
    print("  Section 3: H_trend + R_high + extra conditions")
    print(f"{'=' * 140}")

    def base(r):
        return (r["hurst"] is not None and r["hurst"] >= 0.6 and
                r["retention"] is not None and r["retention"] >= 0.8)

    combos = [
        ("H_trend + R_high (base)", base),
        ("  + limit_up_5d", lambda r: base(r) and r["limit_up_5"]),
        ("  + limit_up_10d", lambda r: base(r) and r["limit_up_10"]),
        ("  + vol_ratio >= 1.5", lambda r: base(r) and r["vol_ratio"] is not None and r["vol_ratio"] >= 1.5),
        ("  + vol_ratio >= 2.0", lambda r: base(r) and r["vol_ratio"] is not None and r["vol_ratio"] >= 2.0),
        ("  + limit_up_10d + vol >= 1.5", lambda r: base(r) and r["limit_up_10"] and r["vol_ratio"] is not None and r["vol_ratio"] >= 1.5),
        ("  + limit_up_5d + vol >= 1.5", lambda r: base(r) and r["limit_up_5"] and r["vol_ratio"] is not None and r["vol_ratio"] >= 1.5),
        ("  + limit_up_10d + vol >= 1.5 + price 50-500", lambda r: base(r) and r["limit_up_10"] and r["vol_ratio"] is not None and r["vol_ratio"] >= 1.5 and 50 <= r["close"] < 500),
    ]
    for label, fn in combos:
        print_results(label, [r for r in all_records if fn(r)])

    # 也測 H_random (起飛警示最佳) 的組合做對比
    print(f"\n{'=' * 140}")
    print("  Section 4: H_random + R_high + extra (alert-style, for comparison)")
    print(f"{'=' * 140}")

    def base_random(r):
        return (r["hurst"] is not None and 0.45 <= r["hurst"] < 0.55 and
                r["retention"] is not None and r["retention"] >= 0.8)

    combos2 = [
        ("H_random + R_high (base)", base_random),
        ("  + limit_up_5d", lambda r: base_random(r) and r["limit_up_5"]),
        ("  + limit_up_10d", lambda r: base_random(r) and r["limit_up_10"]),
        ("  + vol_ratio >= 1.5", lambda r: base_random(r) and r["vol_ratio"] is not None and r["vol_ratio"] >= 1.5),
        ("  + limit_up_10d + vol >= 1.5", lambda r: base_random(r) and r["limit_up_10"] and r["vol_ratio"] is not None and r["vol_ratio"] >= 1.5),
        ("  + limit_up_10d + vol >= 1.5 + price 50-500", lambda r: base_random(r) and r["limit_up_10"] and r["vol_ratio"] is not None and r["vol_ratio"] >= 1.5 and 50 <= r["close"] < 500),
    ]
    for label, fn in combos2:
        print_results(label, [r for r in all_records if fn(r)])

    print(f"\n{'=' * 140}")
    print("  Section 5: No Hurst, just retention + limit_up + vol (baseline)")
    print(f"{'=' * 140}")

    combos3 = [
        ("R_high only", lambda r: r["retention"] is not None and r["retention"] >= 0.8),
        ("R_high + limit_up_10d", lambda r: r["retention"] is not None and r["retention"] >= 0.8 and r["limit_up_10"]),
        ("R_high + limit_up_10d + vol >= 1.5", lambda r: r["retention"] is not None and r["retention"] >= 0.8 and r["limit_up_10"] and r["vol_ratio"] is not None and r["vol_ratio"] >= 1.5),
        ("R_high + limit_up_10d + vol >= 1.5 + price 50-500", lambda r: r["retention"] is not None and r["retention"] >= 0.8 and r["limit_up_10"] and r["vol_ratio"] is not None and r["vol_ratio"] >= 1.5 and 50 <= r["close"] < 500),
    ]
    for label, fn in combos3:
        print_results(label, [r for r in all_records if fn(r)])

    print("=" * 140)


if __name__ == "__main__":
    main()
