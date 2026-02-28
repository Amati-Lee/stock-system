"""
偵察腳本 — 請先執行這個，將輸出結果貼給我看。
目的：確認 yfinance 下載的數據是否正常、漲幅計算是否正確。
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# ---- 參數：和 stock_system 一致 ----
TICKER   = "2330"        # 用台積電來測 (幾乎每天都有數據)
START    = "2026-01-21"
END      = "2026-02-01"  # yfinance 的 end 是不含的

print("=" * 60)
print(f" 偵察：{TICKER}.TW")
print(f" 日期範圍：{START} ~ {END}")
print("=" * 60)

# ---- Step 1：下載 ----
df = yf.download(f"{TICKER}.TW", start=START, end=END, progress=False, auto_adjust=True)

print(f"\n[1] 原始 df.shape : {df.shape}")
print(f"[1] 原始 df.columns : {list(df.columns)}")
print(f"[1] columns 類型 : {type(df.columns)}")

if df.empty:
    print("\n❌ DataFrame 是空的！yfinance 沒有回傳數據。")
    print("   可能原因：日期範圍無交易日、或網路/API 問題。")
else:
    print(f"\n[1] 原始數據（前5行）：")
    print(df.head())

# ---- Step 2：處理 MultiIndex ----
print("\n" + "-" * 60)
if isinstance(df.columns, pd.MultiIndex):
    print("[2] 檢偵到 MultiIndex，正在扁平化...")
    df.columns = df.columns.get_level_values(0)
else:
    print("[2] columns 不是 MultiIndex")

df.columns = df.columns.str.lower()
print(f"[2] 處理後 columns : {list(df.columns)}")
print(f"\n[2] 處理後數據：")
print(df)

# ---- Step 3：計算漲幅 ----
print("\n" + "-" * 60)
if "close" in df.columns and len(df) >= 2:
    df["prev_close"] = df["close"].shift(1)
    df["chg_pct"]    = (df["close"] - df["prev_close"]) / df["prev_close"] * 100

    print("[3] 漲幅計算結果：")
    print(df[["close", "prev_close", "chg_pct"]])

    print(f"\n[3] 最大漲幅 : {df['chg_pct'].max():.2f}%")
    print(f"[3] 最小漲幅 : {df['chg_pct'].min():.2f}%")

    # 列出所有漲幅 >= 5% 的日子（放低門檻看看）
    hits = df[df["chg_pct"] >= 5.0]
    print(f"\n[3] 漲幅 >= 5% 的日子 : {len(hits)} 天")
    if not hits.empty:
        print(hits[["close", "chg_pct"]])

    hits10 = df[df["chg_pct"] >= 10.0]
    print(f"[3] 漲幅 >= 10% 的日子 : {len(hits10)} 天")
else:
    print("[3] ❌ 無法計算漲幅（close 欄位遺失或數據不足）")

# ---- Step 4：檢查 close 的 dtype ----
print("\n" + "-" * 60)
if "close" in df.columns:
    print(f"[4] close dtype : {df['close'].dtype}")
    print(f"[4] close 的前幾個值 : {df['close'].tolist()}")
    # 如果 dtype 是 object 或有巢套，這裡會顯示出來

print("\n" + "=" * 60)
print(" 請將以上全部輸出貼給我看 🙏")
print("=" * 60)