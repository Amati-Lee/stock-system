"""
debug_dividend.py
偵察：直接印出 yfinance 對每筆股票回傳的所有股息相關欄位，
看看數值到底長什麼樣子。
"""

import yfinance as yf
import logging, warnings

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")

# 正常的兩筆 + 異常的兩筆，一起對比
TICKERS = ["2385", "2474", "2368", "2316"]

# 我們要看的欄位
KEYS = [
    "dividendYield",
    "trailingAnnualDividendYield",
    "trailingAnnualDividendRate",
    "dividendRate",
    "regularMarketPrice",
    "previousClose",
    "fiftyTwoWeekHigh",
    "fiftyTwoWeekLow",
    "marketCap",
    "shortName",
]

for t in TICKERS:
    print(f"\n{'=' * 50}")
    print(f"  {t}.TW")
    print(f"{'=' * 50}")
    try:
        info = yf.Ticker(f"{t}.TW").info
        for k in KEYS:
            val = info.get(k)
            print(f"  {k:>40} : {val}")
    except Exception as e:
        print(f"  ❌ 取得失敗：{e}")
