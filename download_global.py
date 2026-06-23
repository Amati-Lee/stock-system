"""
download_global.py — 下載全球關鍵指標（三大指數、VIX、費半、美元指數）
輸出 pwa/global_indicators.json，供 AI 分析時當背景資訊
"""
import json
import os
from datetime import datetime
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "pwa", "global_indicators.json")

INDICATORS = [
    {"symbol": "^DJI", "name": "DJI", "label": "道瓊工業指數"},
    {"symbol": "^GSPC", "name": "SPX", "label": "S&P 500"},
    {"symbol": "^IXIC", "name": "NASDAQ", "label": "NASDAQ 綜合指數"},
    {"symbol": "^VIX", "name": "VIX", "label": "VIX 恐慌指數"},
    {"symbol": "^SOX", "name": "SOX", "label": "費城半導體指數"},
    {"symbol": "DX-Y.NYB", "name": "DXY", "label": "美元指數"},
]

# 需要計算 Hurst 的指數（用較長歷史）
HURST_TARGETS = ["DJI", "SPX", "NASDAQ", "SOX"]


def hurst_exponent(closes, min_window=10):
    """R/S 法計算 Hurst 指數（使用對數報酬率）"""
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


def fetch_indicators():
    import yfinance as yf

    results = {}
    for ind in INDICATORS:
        try:
            # Hurst 需要較長歷史，其他只需 5 日
            need_hurst = ind["name"] in HURST_TARGETS
            period = "1y" if need_hurst else "5d"
            t = yf.Ticker(ind["symbol"])
            h = t.history(period=period)
            if h.empty:
                print(f"  {ind['name']}: 無資料")
                continue
            last = h.iloc[-1]
            prev = h.iloc[-2] if len(h) >= 2 else last
            close = round(float(last["Close"]), 2)
            prev_close = round(float(prev["Close"]), 2)
            chg = round((close - prev_close) / prev_close * 100, 2)
            trade_date = h.index[-1].strftime("%Y-%m-%d")

            # 最近 5 日收盤
            recent = []
            for idx, row in h.tail(5).iterrows():
                recent.append({
                    "date": idx.strftime("%Y-%m-%d"),
                    "close": round(float(row["Close"]), 2),
                })

            entry = {
                "label": ind["label"],
                "close": close,
                "prev_close": prev_close,
                "chg_pct": chg,
                "date": trade_date,
                "recent": recent,
            }

            # 計算 Hurst
            if need_hurst:
                all_closes = [float(row["Close"]) for _, row in h.iterrows()]
                hv = hurst_exponent(all_closes)
                entry["hurst"] = hv
                h_str = f" H={hv}" if hv else ""
            else:
                h_str = ""

            results[ind["name"]] = entry
            sign = "+" if chg >= 0 else ""
            print(f"  {ind['label']}: {close} ({sign}{chg}%){h_str} [{trade_date}]")
        except Exception as e:
            print(f"  {ind['name']}: 錯誤 {e}")

    return results


def main():
    print("=" * 50)
    print("全球關鍵指標下載")
    print("=" * 50)

    results = fetch_indicators()
    if not results:
        print("全部失敗，跳過寫入")
        return

    output = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "indicators": results,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n輸出：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
