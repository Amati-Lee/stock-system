"""
debug_twse_api.py
偵察：嘗試幾個 TWSE 後端 API，看看哪個能回傳股票列表數據。
TWSE 的網頁是動態加載的，股票數據從後端 API 拿來的。
"""
import urllib.request
import json
import time

def try_url(name, url, headers=None):
    """嘗試請求一個 URL，印出狀態和回傳內容的前 500 字"""
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://www.twse.com.tw/"
        }
    print(f"\n{'─' * 55}")
    print(f"  {name}")
    print(f"  URL: {url}")
    print(f"{'─' * 55}")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            print(f"  狀態：✅ {resp.status}")
            print(f"  長度：{len(body)} 字元")
            print(f"  前 500 字：")
            print(f"  {body[:500]}")
    except Exception as e:
        print(f"  狀態：❌ {e}")
    time.sleep(0.5)

# TWSE 已知的後端 API 列表
try_url(
    "TWSE 上市股票列表 API (v1)",
    "https://www.twse.com.tw/api/en/listed/listedCompanies"
)

try_url(
    "TWSE 上市股票列表 API (v2 - board=TPE)",
    "https://www.twse.com.tw/en/listed/listedCompanies?board=TPE"
)

try_url(
    "TWSE 股票基本資訊 API",
    "https://www.twse.com.tw/api/en/listed/stock/listedStockCompanies"
)

try_url(
    "TWSE listed stock codes JSON",
    "https://www.twse.com.tw/api/en/listed/stock/listedStockCompanies?_=1"
)

# 這個 API 是 TWSE 網頁動態加載時實際打的後端
try_url(
    "TWSE 網頁動態加載 API (known endpoint)",
    "https://www.twse.com.tw/api/en/listed/stock/listedStockCompanies?_=1738000000000",
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://www.twse.com.tw/en/listed/listedCompanies",
        "Accept": "application/json"
    }
)
