"""
download_global.py — 下載全球關鍵指標（VIX、費半、美元指數）
輸出 pwa/global_indicators.json，供 AI 分析時當背景資訊
"""
import json
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "pwa", "global_indicators.json")

INDICATORS = [
    {"symbol": "^VIX", "name": "VIX", "label": "VIX 恐慌指數"},
    {"symbol": "^SOX", "name": "SOX", "label": "費城半導體指數"},
    {"symbol": "DX-Y.NYB", "name": "DXY", "label": "美元指數"},
]


def fetch_indicators():
    import yfinance as yf

    results = {}
    for ind in INDICATORS:
        try:
            t = yf.Ticker(ind["symbol"])
            h = t.history(period="5d")
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
            for idx, row in h.iterrows():
                recent.append({
                    "date": idx.strftime("%Y-%m-%d"),
                    "close": round(float(row["Close"]), 2),
                })

            results[ind["name"]] = {
                "label": ind["label"],
                "close": close,
                "prev_close": prev_close,
                "chg_pct": chg,
                "date": trade_date,
                "recent": recent,
            }
            sign = "+" if chg >= 0 else ""
            print(f"  {ind['label']}: {close} ({sign}{chg}%) [{trade_date}]")
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
