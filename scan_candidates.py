"""
每日全股票掃描 — 計算 Hurst / 籌碼維持率 / 漲停 / 量比
存到 candidates_history/scan_YYYYMMDD.json，供日後回測用
只寫當天的掃描結果，不修改任何現有資料
"""
import json
import os
import glob
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")
OUT_DIR = os.path.join(SCRIPT_DIR, "candidates_history")


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


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    ohlc_files = sorted(glob.glob(os.path.join(OHLC_DIR, "*.json")))
    if not ohlc_files:
        print("No OHLC files found")
        return

    # 從任一 OHLC 取最新日期
    with open(os.path.join(OHLC_DIR, "2330.json"), "r", encoding="utf-8") as f:
        sample = json.load(f)
    scan_date = sample[-1]["t"]
    print(f"Scan date: {scan_date}")

    out_path = os.path.join(OUT_DIR, f"scan_{scan_date}.json")
    if os.path.exists(out_path):
        print(f"Already exists: {out_path}")
        return

    results = []
    computed = 0

    for fpath in ohlc_files:
        code = os.path.basename(fpath).replace(".json", "")

        with open(fpath, "r", encoding="utf-8") as f:
            ohlc = json.load(f)

        if len(ohlc) < 60:
            continue

        idx = len(ohlc) - 1
        close = ohlc[idx]["c"]
        if close <= 0:
            continue

        # Hurst
        closes = [r["c"] for r in ohlc]
        h = hurst_exponent(closes)

        # Retention
        r_fi = calc_retention(ohlc, idx, "fi")
        r_ti = calc_retention(ohlc, idx, "ti")
        r_val = None
        if r_fi is not None and r_ti is not None:
            r_val = max(r_fi, r_ti)
        elif r_fi is not None:
            r_val = r_fi
        elif r_ti is not None:
            r_val = r_ti

        # Limit up (10 days)
        limit_up = False
        start = max(0, idx - 9)
        for i in range(start, idx + 1):
            if i == 0:
                continue
            prev_c = ohlc[i - 1]["c"]
            if prev_c > 0 and (ohlc[i]["c"] - prev_c) / prev_c * 100 >= 9.5:
                limit_up = True
                break

        # Volume ratio (20-day avg)
        vr = None
        if idx >= 20:
            cur_vol = ohlc[idx].get("v", 0)
            if cur_vol > 0:
                vols = [ohlc[i].get("v", 0) for i in range(idx - 20, idx)]
                avg = sum(vols) / len(vols)
                if avg > 0:
                    vr = round(cur_vol / avg, 2)

        # Daily change
        chg = round((close - ohlc[idx - 1]["c"]) / ohlc[idx - 1]["c"] * 100, 2) if idx > 0 and ohlc[idx - 1]["c"] > 0 else None

        rec = {"code": code, "close": close}
        if h is not None:
            rec["hurst"] = h
        if r_val is not None:
            rec["ret"] = r_val
        if limit_up:
            rec["lu10"] = True
        if vr is not None:
            rec["vr"] = vr
        if chg is not None:
            rec["chg"] = chg

        results.append(rec)
        computed += 1

    output = {"date": scan_date, "count": len(results), "stocks": results}

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)

    print(f"Scanned: {computed} stocks")
    print(f"Output: {out_path} ({os.path.getsize(out_path) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
