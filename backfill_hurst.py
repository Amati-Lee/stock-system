"""
回填歷史 alert 的 Hurst 指數 — 從 OHLC 重新計算
對 alerts_history/*.json 中 hurst 為 null 的警示補算
"""
import json
import os
import glob
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ALERTS_DIR = os.path.join(SCRIPT_DIR, "alerts_history")
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")


def hurst_exponent(closes, min_window=10):
    """R/S 法計算 Hurst 指數（與 stock_alert.py 相同）"""
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


def load_ohlc_closes(code, alert_date):
    """讀取 alert_date 當天（含）之前的所有收盤價"""
    path = os.path.join(OHLC_DIR, f"{code}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    closes = [r["c"] for r in data if r["t"] <= alert_date]
    return closes if len(closes) >= 60 else None


def main():
    alert_files = sorted(glob.glob(os.path.join(ALERTS_DIR, "alerts_*.json")))
    print(f"找到 {len(alert_files)} 個警示檔案")

    total_filled = 0
    total_already = 0
    total_failed = 0
    files_modified = 0

    for af in alert_files:
        with open(af, "r", encoding="utf-8") as f:
            data = json.load(f)

        alert_date = data["date"].replace("-", "")
        alerts = data.get("alerts", [])
        modified = False

        for a in alerts:
            if a.get("hurst") is not None:
                total_already += 1
                continue

            closes = load_ohlc_closes(a["code"], alert_date)
            if closes is None:
                total_failed += 1
                continue

            h = hurst_exponent(closes)
            if h is not None:
                a["hurst"] = h
                modified = True
                total_filled += 1
            else:
                total_failed += 1

        if modified:
            with open(af, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            files_modified += 1

    print(f"已有 Hurst: {total_already}")
    print(f"新補算: {total_filled}")
    print(f"無法計算（OHLC 不足）: {total_failed}")
    print(f"修改了 {files_modified} 個檔案")


if __name__ == "__main__":
    main()
