"""
全股票 Hurst 回測 — 用全部自選股測試 Hurst 分組的後續報酬
不限於起飛警示，看 Hurst 本身對一般股票是否有預測力
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


def classify_hurst(h):
    if h is None:
        return None
    if h >= 0.6:
        return "H_trend (>=0.6)"
    elif h >= 0.55:
        return "H_weak (0.55-0.6)"
    elif h >= 0.45:
        return "H_random (0.45-0.55)"
    else:
        return "H_revert (<0.45)"


def main():
    ohlc_files = sorted(glob.glob(os.path.join(OHLC_DIR, "*.json")))
    print(f"OHLC files: {len(ohlc_files)}")

    # 用最近的交易日作為基準日，往前取多個測試日
    # 每支股票在每個測試日都算一次 Hurst，看之後 N 天報酬
    # 測試日：從倒數第 21 天開始，每 5 天取一個，共取多個樣本點
    TEST_OFFSETS = [20, 25, 30, 35, 40, 45, 50, 55, 60]

    hurst_groups = defaultdict(lambda: defaultdict(list))
    total = 0
    computed = 0

    for fpath in ohlc_files:
        with open(fpath, "r", encoding="utf-8") as f:
            ohlc = json.load(f)

        if len(ohlc) < 120:
            continue

        total += 1
        closes_all = [r["c"] for r in ohlc]

        for offset in TEST_OFFSETS:
            if offset + max(HOLD_DAYS) >= len(ohlc):
                continue

            # 在 ohlc[-offset] 這天計算 Hurst（用之前的資料）
            test_idx = len(ohlc) - offset
            closes_before = closes_all[:test_idx + 1]
            entry_price = closes_all[test_idx]

            h = hurst_exponent(closes_before)
            if h is None:
                continue

            h_class = classify_hurst(h)
            computed += 1

            for n in HOLD_DAYS:
                future_idx = test_idx + n
                if future_idx >= len(ohlc):
                    continue
                ret = (closes_all[future_idx] - entry_price) / entry_price * 100
                hurst_groups[h_class][n].append(ret)

    print(f"Stocks with enough data: {total}")
    print(f"Total samples: {computed}")

    print(f"\n{'=' * 90}")
    print(f"  全股票 Hurst 分組後續報酬（非警示，一般股票）")
    print(f"{'=' * 90}")
    print(f"  {'分組':<25} | {'樣本':>6} |", end="")
    for n in HOLD_DAYS:
        print(f"  {n}D win    {n}D avg    {n}D med  |", end="")
    print()
    print("-" * 90)

    for g in sorted(hurst_groups.keys()):
        data = hurst_groups[g]
        sample = len(data.get(HOLD_DAYS[0], []))
        if sample == 0:
            continue
        print(f"  {g:<25} | {sample:>6} |", end="")
        for n in HOLD_DAYS:
            rets = data.get(n, [])
            if not rets:
                print(f"    N/A              |", end="")
                continue
            win = sum(1 for r in rets if r > 0) / len(rets) * 100
            avg = sum(rets) / len(rets)
            med = sorted(rets)[len(rets) // 2]
            print(f"  {win:4.0f}%  {avg:+6.2f}%  {med:+5.1f}% |", end="")
        print()

    print("=" * 90)
    print(f"\nTest offsets: {TEST_OFFSETS} (days before latest)")
    print(f"Each stock tested at {len(TEST_OFFSETS)} time points")


if __name__ == "__main__":
    main()
