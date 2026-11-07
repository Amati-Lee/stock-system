"""
debug_twse_api.py
偵察：嘗試幾個 TWSE 後端 API，看看哪個能回傳股票列表數據。
TWSE 的網頁是動態加載的，股票數據從後端 API 拿來的。
"""
import urllib.request
import ssl
import certifi
import json
import time

# ⛔ 不可改回「不傳 context 」的裸 urlopen。
#    Python 預設的 SSL context 在 Windows 上吃系統憑證庫，OpenSSL 3.0 會對
#    www.twse.com.tw / www.tpex.org.tw / mopsov.twse.com.tw 丟
#    "Missing Subject Key Identifier" → 本機跑永遠拿不到資料（CI 的 ubuntu 沒事，
#    所以這個 bug 被掩護了很久）。certifi 的 CA bundle 則全數通過。
SSL_CTX = ssl.create_default_context(cafile=certifi.where())


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
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
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
