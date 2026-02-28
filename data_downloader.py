"""
data_downloader.py
下載全部股票的完整技術指標數據到本地

執行一次後，之後就能快速篩選，不用重新計算
建議：每天收盤後執行一次更新數據
"""
import sys
sys.path.insert(0, '.')

from stock_system import (
    get_stock_name, download_stock, 
    calc_kd, calc_rsi, calc_macd,
    ScreenerConfig, get_stock_list
)
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import time

print("=" * 70)
print("  台股完整數據下載器")
print("=" * 70)
print()
print("說明：")
print("  下載全部上市＋上櫃股票的完整技術指標數據（深度掃描模式）")
print("  包含：KD、RSI、MACD、布林通道、成交量、市值、本益比、殖利率")
print("  存檔後可快速篩選，不用每次重新計算")
print()
print("預計時間：30-40 分鐘")
print("=" * 70)
print()

# 取得股票清單
cfg = ScreenerConfig(max_stocks=9999)
stocks = get_stock_list(cfg, deep=False)

if not stocks:
    print("❌ 無法取得股票清單")
    sys.exit(1)

print(f"📦 準備下載 {len(stocks)} 筆股票數據")
print()

# 準備存儲數據
all_data = []

# 計算日期範圍（需要足夠歷史數據計算指標）
end_date = datetime.now()
start_date = end_date - timedelta(days=90)  # 往前 90 天
start_str = start_date.strftime("%Y-%m-%d")
end_str = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")

print(f"📅 數據日期範圍：{start_str} ~ {end_date.strftime('%Y-%m-%d')}")
print()
print("開始下載...")
print()

success = 0
failed = 0

for i, ticker in enumerate(stocks, 1):
    print(f"⏳ ({i:>4}/{len(stocks)}) {ticker} ", end="", flush=True)
    
    try:
        # 下載歷史數據
        df = download_stock(ticker, start_str, end_str)
        
        if df is None or len(df) < 30:
            print("❌ 數據不足")
            failed += 1
            continue
        
        # 取得股票名稱
        name = get_stock_name(ticker)
        
        # ========== 計算技術指標 ==========
        
        # KD
        k, d = calc_kd(df, period=9)
        df["k"] = k
        df["d"] = d
        
        # RSI
        df["rsi"] = calc_rsi(df["close"], period=14)
        
        # MACD
        dif, macd, histogram = calc_macd(df["close"], fast=12, slow=26, signal=9)
        df["dif"] = dif
        df["macd"] = macd
        df["histogram"] = histogram
        
        # 布林通道
        df["bb_middle"] = df["close"].rolling(20).mean()
        df["bb_std"] = df["close"].rolling(20).std()
        df["bb_upper"] = df["bb_middle"] + (2.0 * df["bb_std"])
        df["bb_lower"] = df["bb_middle"] - (2.0 * df["bb_std"])
        
        # 成交量
        df["vol_ma5"] = df["volume"].rolling(5).mean()
        df["volume_ratio"] = df["volume"] / df["vol_ma5"]
        
        # 取最新一天數據
        latest = df.iloc[-1]
        
        # ========== 取得市場數據 ==========
        
        import io
        _orig_out, _orig_err = sys.stdout, sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            info = yf.Ticker(f"{ticker}.TW").info
        finally:
            sys.stdout, sys.stderr = _orig_out, _orig_err
        
        # 市值（億元）
        market_cap_raw = info.get("marketCap")
        market_cap = round(float(market_cap_raw) / 1e8, 2) if market_cap_raw else None
        
        # 本益比
        pe_ratio = info.get("trailingPE") or info.get("forwardPE")
        pe_ratio = round(float(pe_ratio), 2) if pe_ratio and pe_ratio > 0 else None
        
        # 現價
        price = info.get("regularMarketPrice") or info.get("previousClose")
        price = round(float(price), 2) if price else latest["close"]
        
        # 殖利率
        div_rate = info.get("dividendRate") or info.get("trailingAnnualDividendRate")
        div_rate = round(float(div_rate), 2) if div_rate and div_rate > 0 else None
        
        div_yield = None
        if price and div_rate and price > 0 and div_rate > 0:
            div_yield = round((div_rate / price) * 100, 2)
        
        # ========== 組合數據 ==========
        
        stock_data = {
            "股票代號": ticker,
            "股票名稱": name,
            "收盤價": round(float(latest["close"]), 2),
            "K值": round(float(latest["k"]), 2) if not pd.isna(latest["k"]) else None,
            "D值": round(float(latest["d"]), 2) if not pd.isna(latest["d"]) else None,
            "RSI": round(float(latest["rsi"]), 2) if not pd.isna(latest["rsi"]) else None,
            "DIF": round(float(latest["dif"]), 2) if not pd.isna(latest["dif"]) else None,
            "MACD": round(float(latest["macd"]), 2) if not pd.isna(latest["macd"]) else None,
            "柱狀圖": round(float(latest["histogram"]), 2) if not pd.isna(latest["histogram"]) else None,
            "BB上軌": round(float(latest["bb_upper"]), 2) if not pd.isna(latest["bb_upper"]) else None,
            "BB中軌": round(float(latest["bb_middle"]), 2) if not pd.isna(latest["bb_middle"]) else None,
            "BB下軌": round(float(latest["bb_lower"]), 2) if not pd.isna(latest["bb_lower"]) else None,
            "成交量張": int(latest["volume"] / 1000),
            "5日均量張": int(latest["vol_ma5"] / 1000) if not pd.isna(latest["vol_ma5"]) else None,
            "量比": round(float(latest["volume_ratio"]), 2) if not pd.isna(latest["volume_ratio"]) else None,
            "市值億": market_cap,
            "本益比": pe_ratio,
            "每股配息": div_rate,
            "殖利率": div_yield,
            "更新時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        all_data.append(stock_data)
        success += 1
        print(f"✅ ({success}/{len(stocks)})")
        
    except Exception as e:
        print(f"❌ 失敗: {str(e)[:30]}")
        failed += 1
    
    # 避免請求太快
    time.sleep(0.3)

# ========== 存檔 ==========

if all_data:
    df_all = pd.DataFrame(all_data)
    
    # 存成 CSV
    csv_filename = f"stock_data_{datetime.now().strftime('%Y%m%d')}.csv"
    df_all.to_csv(csv_filename, index=False, encoding="utf-8-sig")
    
    print()
    print("=" * 70)
    print(f"✅ 下載完成！")
    print(f"   成功：{success} 筆")
    print(f"   失敗：{failed} 筆")
    print(f"   檔案：{csv_filename}")
    print()
    print("📊 數據統計：")
    print(f"   總筆數：{len(df_all)}")
    print(f"   檔案大小：{df_all.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB")
    print()
    print("💡 接下來可使用 quick_filter.py 快速篩選！")
    print("=" * 70)
else:
    print()
    print("❌ 無數據可存")
