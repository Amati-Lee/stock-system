"""
test_resonance.py
測試技術指標共振策略（五大指標）
"""
import sys
import os
sys.path.insert(0, '.')

from stock_system import ScreenerConfig, run_screener, export_to_excel
from datetime import datetime

print("=" * 70)
print("  技術指標共振策略測試（五大指標同時成立）")
print("=" * 70)
print()
print("策略說明：")
print("  五大指標必須同時出現買進訊號：")
print("  1. KD 指標：K < 20 且 D < 20（超賣）或 K 向上突破 D（黃金交叉）")
print("  2. RSI 指標：RSI < 30（超賣）")
print("  3. 布林通道：價格接近下軌（準備反彈）且通道不縮窄")
print("  4. 量能：今日量 >= 5日均量 * 1.5（量能放大）")
print("  5. MACD：DIF 向上突破 MACD（黃金交叉）或柱狀圖由負轉正")
print()
print("  ✅ 五個指標全部成立 → 強力共振訊號，準備反彈")
print()
print("=" * 70)
print()

cfg = ScreenerConfig(
    lookback_days=60,          # 回溯 60 天取得足夠數據
    filter_resonance=True,     # 開啟共振策略
    
    # KD 參數
    kd_period=9,               # KD 週期
    kd_oversold_k=20,          # K 超賣閾值
    kd_oversold_d=20,          # D 超賣閾值
    
    # RSI 參數
    rsi_period=14,             # RSI 週期
    rsi_oversold=30,           # RSI 超賣閾值
    
    # MACD 參數
    macd_fast=12,              # 快線週期
    macd_slow=26,              # 慢線週期
    macd_signal=9,             # 訊號線週期
    
    # 布林通道參數
    bbands_period=20,          # 布林通道週期
    bbands_std=2.0,            # 標準差倍數
    
    # 量能參數
    volume_surge_ratio=1.5,    # 量能放大倍數
    
    max_stocks=9999            # 掃描全部股票
)

print("開始掃描...")
print()

# 檢查是否已有股票清單
cache_exists = os.path.exists("tw_stock_verified.txt")

if cache_exists:
    # 已有清單，直接使用（快速）
    print("💡 提示：已有股票清單，將直接使用")
    print("   如需重新驗證全範圍，請刪除 tw_stock_verified.txt 後重新執行")
    print()
    results = run_screener(cfg, deep=False)
else:
    # 第一次執行，需要建立清單（約 30 分鐘）
    print("⚠️  第一次執行，需要驗證全範圍股票（約 30 分鐘）")
    print("   之後就會使用已驗證清單，不需要再等待")
    print()
    results = run_screener(cfg, deep=True)

if results:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"resonance_report_{timestamp}.xlsx"
    export_to_excel(results, cfg, filename)
    print(f"\n✅ 找到 {len(results)} 筆五指標共振訊號股票")
    print(f"📊 Excel 報表已生成：{filename}")
else:
    print("\n❌ 無符合條件的股票")
    print("   （五個指標要同時成立非常嚴格，可能一筆都沒有）")
