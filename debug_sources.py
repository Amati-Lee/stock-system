"""
debug_sources.py
偵察：看看哪種方式能成功取得台股清單
"""
import time

# ---- Test 1：yfinance 內部有沒有台股列表 ----
print("=" * 50)
print("[Test 1] yfinance 內部模組探索")
print("=" * 50)
try:
    import yfinance as yf
    # yfinance 有一個 tickers 模組，看看能不能用
    print(f"  yfinance 版本：{yf.__version__}")

    # 嘗試用 yfinance 下載一個已知股票來確認網路通
    df = yf.download("2330.TW", period="1d", progress=False)
    print(f"  2330.TW 下載測試：{'✅ 通' if not df.empty else '❌ 失敗'}")
except Exception as e:
    print(f"  ❌ {e}")

# ---- Test 2：看看 requests 套件能不能用（yfinance 內部用的） ----
print("\n" + "=" * 50)
print("[Test 2] requests 連網測試")
print("=" * 50)
try:
    import requests

    # 先試 Yahoo Finance 的台股列表頁
    url1 = "https://finance.yahoo.com/quote/2330.TW/"
    r = requests.get(url1, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    print(f"  Yahoo Finance 2330.TW：{r.status_code}")

    # 試看看能不能進入 Yahoo 的 screener API（這個可以篩選股票）
    # Yahoo 有個公開的 screener 可以按國家篩選
    url2 = "https://query2.finance.yahoo.com/v1/finance/screener"
    params = {
        "formatted": "true",
        "chrtsim": "false",
        "offset": "0",
        "count": "50",
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    r2 = requests.get(url2, params=params, headers=headers, timeout=10)
    print(f"  Yahoo Screener API：{r2.status_code}")

except ImportError:
    print("  ❌ requests 未安裝")
except Exception as e:
    print(f"  ❌ {e}")

# ---- Test 3：urllib 連網測試（看看連哪裡會失敗） ----
print("\n" + "=" * 50)
print("[Test 3] urllib 逐一測試各網站")
print("=" * 50)
import urllib.request

test_urls = [
    ("Google",          "https://www.google.com"),
    ("Yahoo Finance",   "https://finance.yahoo.com"),
    ("TWSE",            "https://www.twse.com.tw"),
    ("OTCBB",           "https://www.otcbb.tw"),
    ("Yahoo Query API", "https://query2.finance.yahoo.com"),
]

for name, url in test_urls:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            print(f"  {name:20s} ✅ {resp.status}")
    except Exception as e:
        print(f"  {name:20s} ❌ {e}")
    time.sleep(0.5)
