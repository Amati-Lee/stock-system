# -*- coding: utf-8 -*-
"""
backfill_stocks.py
為指定股票補齊所有既有 CSV 日期的資料，並附加到每個 CSV 中
"""
import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

from stock_system import get_stock_name, download_stock, calc_kd, calc_rsi, calc_macd
import pandas as pd
import yfinance as yf
import glob
import os
import io
from datetime import datetime, timedelta
import time

# ====== 要補的股票 ======
NEW_STOCKS = ["3349", "7709", "3710", "3228", "7770", "3552", "7734"]

# ====== 找出所有 CSV ======
csv_files = sorted(glob.glob("stock_data_*.csv"))
print(f"找到 {len(csv_files)} 個 CSV 檔案")
print(f"要補的股票: {NEW_STOCKS}")
print()

# ====== 對每支股票下載 90 天歷史資料 ======
end_date = datetime.now() + timedelta(days=1)
start_date = end_date - timedelta(days=250)  # 多抓一點確保覆蓋所有 CSV 日期
start_str = start_date.strftime("%Y-%m-%d")
end_str = end_date.strftime("%Y-%m-%d")

stock_history = {}  # {code: DataFrame with indicators}

for code in NEW_STOCKS:
    print(f"下載 {code} 歷史資料...", end=" ", flush=True)
    try:
        df = download_stock(code, start_str, end_str)
        if df is None or len(df) < 5:
            print("資料不足，跳過")
            continue

        # 計算技術指標
        k, d = calc_kd(df, period=9)
        df["k"] = k
        df["d"] = d
        df["rsi"] = calc_rsi(df["close"], period=14)
        dif, macd, histogram = calc_macd(df["close"], fast=12, slow=26, signal=9)
        df["dif"] = dif
        df["macd"] = macd
        df["histogram"] = histogram
        df["bb_middle"] = df["close"].rolling(20).mean()
        df["bb_std"] = df["close"].rolling(20).std()
        df["bb_upper"] = df["bb_middle"] + (2.0 * df["bb_std"])
        df["bb_lower"] = df["bb_middle"] - (2.0 * df["bb_std"])
        df["vol_ma5"] = df["volume"].rolling(5).mean()
        df["volume_ratio"] = df["volume"] / df["vol_ma5"]

        stock_history[code] = df
        print(f"OK ({len(df)} 天)")

        # 取得市場資料
        _orig_out, _orig_err = sys.stdout, sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            info = yf.Ticker(f"{code}.TW").info
            if not info.get("regularMarketPrice"):
                info = yf.Ticker(f"{code}.TWO").info
        finally:
            sys.stdout, sys.stderr = _orig_out, _orig_err

        stock_history[code + "_info"] = info
        time.sleep(0.5)

    except Exception as e:
        print(f"失敗: {e}")

print(f"\n成功下載 {len([k for k in stock_history if '_info' not in k])} 支股票")
print()

# ====== 對每個 CSV 補資料 ======
total_added = 0

for csv_file in csv_files:
    # 讀取 CSV 中的交易日
    existing = pd.read_csv(csv_file, encoding="utf-8-sig")
    if "交易日" not in existing.columns:
        print(f"  {csv_file}: 無交易日欄位，跳過")
        continue

    trade_date_str = str(existing["交易日"].iloc[0])  # e.g. "2026-03-18"
    try:
        trade_date = pd.Timestamp(trade_date_str)
    except:
        print(f"  {csv_file}: 無法解析交易日 {trade_date_str}，跳過")
        continue

    # 檢查哪些股票已存在
    existing_codes = set(existing["股票代號"].astype(str).tolist())
    to_add = [c for c in NEW_STOCKS if c not in existing_codes and c in stock_history]

    if not to_add:
        print(f"  {csv_file} ({trade_date_str}): 無需補充")
        continue

    new_rows = []
    for code in to_add:
        df = stock_history[code]
        info = stock_history.get(code + "_info", {})
        name = get_stock_name(code)

        # 找到該交易日的資料
        # df.index 是日期型
        target = None
        for idx in df.index:
            if str(idx.date()) == trade_date_str:
                target = df.loc[idx]
                break

        if target is None:
            # 找不到精確日期，跳過
            continue

        market_cap_raw = info.get("marketCap")
        market_cap = round(float(market_cap_raw) / 1e8, 2) if market_cap_raw else None
        pe_ratio = info.get("trailingPE") or info.get("forwardPE")
        pe_ratio = round(float(pe_ratio), 2) if pe_ratio and pe_ratio > 0 else None
        price = round(float(target["close"]), 2)
        div_rate = info.get("dividendRate") or info.get("trailingAnnualDividendRate")
        div_rate = round(float(div_rate), 2) if div_rate and div_rate > 0 else None
        div_yield = round((div_rate / price) * 100, 2) if price and div_rate and price > 0 and div_rate > 0 else None

        row = {
            "股票代號": code,
            "股票名稱": name,
            "收盤價": price,
            "K值": round(float(target["k"]), 2) if not pd.isna(target["k"]) else None,
            "D值": round(float(target["d"]), 2) if not pd.isna(target["d"]) else None,
            "RSI": round(float(target["rsi"]), 2) if not pd.isna(target["rsi"]) else None,
            "DIF": round(float(target["dif"]), 2) if not pd.isna(target["dif"]) else None,
            "MACD": round(float(target["macd"]), 2) if not pd.isna(target["macd"]) else None,
            "柱狀圖": round(float(target["histogram"]), 2) if not pd.isna(target["histogram"]) else None,
            "BB上軌": round(float(target["bb_upper"]), 2) if not pd.isna(target["bb_upper"]) else None,
            "BB中軌": round(float(target["bb_middle"]), 2) if not pd.isna(target["bb_middle"]) else None,
            "BB下軌": round(float(target["bb_lower"]), 2) if not pd.isna(target["bb_lower"]) else None,
            "成交量張": int(target["volume"] / 1000),
            "5日均量張": int(target["vol_ma5"] / 1000) if not pd.isna(target["vol_ma5"]) else None,
            "量比": round(float(target["volume_ratio"]), 2) if not pd.isna(target["volume_ratio"]) else None,
            "市值億": market_cap,
            "本益比": pe_ratio,
            "每股配息": div_rate,
            "殖利率": div_yield,
            "交易日": trade_date_str,
            "更新時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        new_rows.append(row)

    if new_rows:
        df_new = pd.DataFrame(new_rows)
        combined = pd.concat([existing, df_new], ignore_index=True)
        combined.to_csv(csv_file, index=False, encoding="utf-8-sig")
        codes_added = [r["股票代號"] for r in new_rows]
        print(f"  {csv_file} ({trade_date_str}): +{len(new_rows)} 筆 ({', '.join(codes_added)})")
        total_added += len(new_rows)

print()
print(f"完成！共補充 {total_added} 筆資料")
