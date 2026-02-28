"""
test_trend.py
測試趨勢分析功能（複製今天數據並模擬變化）
"""
import pandas as pd
import glob
import shutil
from datetime import datetime, timedelta
import numpy as np

print("=" * 70)
print("  趨勢分析測試模式")
print("=" * 70)
print()

# 找到今天的數據
files = glob.glob("stock_data_*.csv")
if not files:
    print("❌ 找不到數據檔案，請先執行 data_downloader.py")
    exit(1)

today_file = max(files)
print(f"📊 找到數據：{today_file}")

# 提取日期
date_str = today_file.replace("stock_data_", "").replace(".csv", "")
date_obj = datetime.strptime(date_str, "%Y%m%d")
yesterday_date = date_obj - timedelta(days=1)
yesterday_file = f"stock_data_{yesterday_date.strftime('%Y%m%d')}.csv"

print(f"⏳ 生成測試數據：{yesterday_file}")

# 載入今天的數據
df = pd.read_csv(today_file, encoding="utf-8-sig")
print(f"   載入：{len(df)} 筆股票")

# 設定隨機種子（確保每次結果一致）
np.random.seed(42)

# 模擬昨天的數據（價格和指標都稍微不同）
print(f"⏳ 模擬昨天數據變化...")

if '收盤價' in df.columns:
    # 價格：-3% ~ +3% 隨機變化
    random_changes = np.random.uniform(-0.03, 0.03, len(df))
    df['收盤價'] = (df['收盤價'] * (1 + random_changes)).round(2)

if 'K值' in df.columns:
    # K值：-5 ~ +5 隨機變化
    random_changes = np.random.uniform(-5, 5, len(df))
    df['K值'] = (df['K值'] + random_changes).clip(0, 100).round(2)

if 'D值' in df.columns:
    # D值：-5 ~ +5 隨機變化
    random_changes = np.random.uniform(-5, 5, len(df))
    df['D值'] = (df['D值'] + random_changes).clip(0, 100).round(2)

if 'RSI' in df.columns:
    # RSI：-5 ~ +5 隨機變化
    random_changes = np.random.uniform(-5, 5, len(df))
    df['RSI'] = (df['RSI'] + random_changes).clip(0, 100).round(2)

if 'BB位置' in df.columns:
    # BB位置：-10 ~ +10 隨機變化
    random_changes = np.random.uniform(-10, 10, len(df))
    df['BB位置'] = (df['BB位置'] + random_changes).clip(0, 100).round(2)

if '量比' in df.columns:
    # 量比：-0.5 ~ +0.5 隨機變化
    random_changes = np.random.uniform(-0.5, 0.5, len(df))
    df['量比'] = (df['量比'] + random_changes).clip(0.1, 10).round(2)

# 儲存為「昨天」的數據
df.to_csv(yesterday_file, index=False, encoding="utf-8-sig")

print(f"✅ 測試數據生成完成")
print()
print("=" * 70)
print("📝 現在可以執行：")
print()
print("   python trend_analyzer.py")
print()
print("=" * 70)
print("⚠️  注意事項：")
print("   • 這是測試數據，不是真實歷史數據")
print("   • 用於測試功能是否正常運作")
print("   • 明天開始下載後，就會有真實比對數據")
print("   • 測試完可刪除：" + yesterday_file)
print("=" * 70)
