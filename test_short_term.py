"""
test_short_term.py
短線操作訊號測試

兩種短線做多訊號：
1. KD 黃金交叉 — K 向上突破 D，趨勢轉多
2. 布林通道接近上軌 — 價格強勢，準備突破
"""
import sys
import os
sys.path.insert(0, '.')

from stock_system import ScreenerConfig, run_screener, export_to_excel
from datetime import datetime

print("=" * 70)
print("  短線操作訊號篩選器")
print("=" * 70)
print()
print("策略選項：")
print("  1. KD 黃金交叉 — K 向上突破 D，趨勢轉多（短線買進）")
print("  2. 布林通道上軌 — 價格接近上軌，強勢突破（追強勢）")
print("  3. 兩者皆符合 — 雙重確認的短線訊號（更可靠）")
print()
print("=" * 70)
print()

# 選擇策略
strategy = input("選擇策略 [1]: ").strip() or "1"

if strategy not in ["1", "2", "3"]:
    print("❌ 無效選項")
    sys.exit(1)

strategy_names = {
    "1": "KD黃金交叉",
    "2": "布林上軌突破",
    "3": "KD黃金交叉 + 布林上軌"
}

print(f"\n✅ 已選擇：{strategy_names[strategy]}")
print()

cfg = ScreenerConfig(
    lookback_days=30,          # 回溯 30 天
    filter_kd_golden=(strategy in ["1", "3"]),
    filter_bb_upper=(strategy in ["2", "3"]),
    kd_period=9,
    bbands_period=20,
    bbands_std=2.0,
    max_stocks=9999
)

print("開始掃描...")
print()

# 檢查是否已有股票清單
cache_exists = os.path.exists("tw_stock_verified.txt")
results = run_screener(cfg, deep=not cache_exists)

if results:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"short_term_{timestamp}.xlsx"
    export_to_excel(results, cfg, filename)
    print(f"\n✅ 找到 {len(results)} 筆短線訊號股票")
    print(f"📊 Excel 報表已生成：{filename}")
    
    print()
    print("=" * 70)
    print("💡 操作建議：")
    if strategy == "1":
        print("  - KD 黃金交叉適合短線進場")
        print("  - 建議搭配量能確認")
        print("  - 設定停損點（約 5-8%）")
    elif strategy == "2":
        print("  - 接近上軌表示強勢")
        print("  - 適合追強勢股")
        print("  - 注意回測壓力")
    else:
        print("  - 雙重確認訊號較可靠")
        print("  - 短線操作首選")
        print("  - 設定停損停利")
    print("=" * 70)
else:
    print("\n❌ 無符合條件的股票")
