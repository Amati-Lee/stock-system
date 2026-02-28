"""
debug_limit_up.py
測試特定股票是否有漲停紀錄
"""
import sys
sys.path.insert(0, '.')

from stock_system import download_stock, check_limit_up, check_dividend, ScreenerConfig
from datetime import datetime, timedelta

# 你說昨天漲停的股票
test_stocks = ["7799", "6651", "9950", "6492", "6683", "5245", "5309", "6521", "1454", "3363", "5386", "6189"]

cfg = ScreenerConfig(
    lookback_days=10,
    filter_limit_up=True,
    limit_up_pct=9.0,
    filter_dividend=True,
    min_dividend_yield=4.5
)

end_date = datetime.now().strftime("%Y-%m-%d")
start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

print(f"測試日期範圍：{start_date} ~ {end_date}")
print(f"漲停門檻：{cfg.limit_up_pct}%")
print(f"殖利率門檻：{cfg.min_dividend_yield}%")
print("=" * 80)

for ticker in test_stocks:
    print(f"\n📌 {ticker}")
    
    # 檢查漲停
    df = download_stock(ticker, start_date, end_date)
    if df is not None and len(df) > 0:
        lu = check_limit_up(df, cfg)
        if lu:
            print(f"  ✅ 漲停：{lu['date']} 漲幅 {lu['chg_pct']}%")
        else:
            print(f"  ❌ 無漲停紀錄")
            # 印出最大漲幅
            df["prev_close"] = df["close"].shift(1)
            df["chg_pct"] = (df["close"] - df["prev_close"]) / df["prev_close"] * 100
            max_chg = df["chg_pct"].max()
            print(f"     期間最大漲幅：{max_chg:.2f}%")
    else:
        print(f"  ❌ 無法取得數據")
    
    # 檢查殖利率
    div = check_dividend(cfg, ticker)
    if div:
        print(f"  ✅ 殖利率：{div['dividend_yield']}%")
    else:
        print(f"  ❌ 殖利率不足 4.5%（或無數據）")

print("\n" + "=" * 80)
print("結論：只有同時符合【漲停 AND 殖利率 >= 4.5%】的股票才會被選中")
