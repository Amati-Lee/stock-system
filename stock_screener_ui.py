"""
台股互動式篩選器 — stock_screener_ui.py
提供互動式選單，讓使用者自訂篩選條件
"""

import sys
import os

# 匯入主系統
sys.path.insert(0, os.path.dirname(__file__))
from stock_system import ScreenerConfig, run_screener, export_to_excel
from datetime import datetime


def print_header():
    """印出標題"""
    print("\n" + "=" * 60)
    print("  台股互動式篩選器")
    print("=" * 60)


def get_float_input(prompt: str, default: float, min_val: float = None, max_val: float = None) -> float:
    """取得浮點數輸入，帶預設值"""
    while True:
        try:
            val = input(f"{prompt} [預設: {default}]: ").strip()
            if not val:
                return default
            val = float(val)
            if min_val is not None and val < min_val:
                print(f"❌ 數值不可小於 {min_val}")
                continue
            if max_val is not None and val > max_val:
                print(f"❌ 數值不可大於 {max_val}")
                continue
            return val
        except ValueError:
            print("❌ 請輸入有效數字")


def get_int_input(prompt: str, default: int, min_val: int = None, max_val: int = None) -> int:
    """取得整數輸入，帶預設值"""
    while True:
        try:
            val = input(f"{prompt} [預設: {default}]: ").strip()
            if not val:
                return default
            val = int(val)
            if min_val is not None and val < min_val:
                print(f"❌ 數值不可小於 {min_val}")
                continue
            if max_val is not None and val > max_val:
                print(f"❌ 數值不可大於 {max_val}")
                continue
            return val
        except ValueError:
            print("❌ 請輸入有效整數")


def get_yes_no(prompt: str, default: bool = True) -> bool:
    """取得是/否輸入"""
    default_str = "Y" if default else "N"
    while True:
        val = input(f"{prompt} (Y/N) [預設: {default_str}]: ").strip().upper()
        if not val:
            return default
        if val in ("Y", "YES", "是"):
            return True
        elif val in ("N", "NO", "否"):
            return False
        else:
            print("❌ 請輸入 Y 或 N")


def interactive_screener():
    """互動式篩選介面"""
    print_header()
    print("\n請設定篩選條件（直接按 Enter 使用預設值）\n")

    # ============================================================
    # 基本篩選條件
    # ============================================================
    print("【基本條件】")
    print("-" * 60)
    
    # 現價範圍
    use_price_filter = get_yes_no("是否篩選現價範圍？", default=False)
    min_price = 0.0
    max_price = 9999.0
    if use_price_filter:
        min_price = get_float_input("  最低價格（元）", 10.0, min_val=0)
        max_price = get_float_input("  最高價格（元）", 200.0, min_val=min_price)
    
    # 市值範圍
    use_market_cap = get_yes_no("是否篩選市值範圍？", default=False)
    min_market_cap = 10.0
    max_market_cap = 10000.0
    if use_market_cap:
        min_market_cap = get_float_input("  最低市值（億元）", 50.0, min_val=0)
        max_market_cap = get_float_input("  最高市值（億元）", 5000.0, min_val=min_market_cap)
    
    print()

    # ============================================================
    # 殖利率篩選
    # ============================================================
    print("【殖利率篩選】")
    print("-" * 60)
    filter_dividend = get_yes_no("是否開啟殖利率篩選？", default=True)
    min_dividend_yield = 5.0
    if filter_dividend:
        min_dividend_yield = get_float_input("  最低殖利率（%）", 5.0, min_val=0, max_val=100)
    
    print()

    # ============================================================
    # 本益比篩選
    # ============================================================
    print("【本益比篩選】")
    print("-" * 60)
    filter_pe = get_yes_no("是否開啟本益比篩選？", default=False)
    min_pe = 0.0
    max_pe = 50.0
    if filter_pe:
        min_pe = get_float_input("  最低本益比", 0.0, min_val=0)
        max_pe = get_float_input("  最高本益比", 30.0, min_val=min_pe)
    
    print()

    # ============================================================
    # 成交量篩選
    # ============================================================
    print("【成交量篩選】")
    print("-" * 60)
    filter_volume = get_yes_no("是否開啟成交量篩選？", default=False)
    min_volume = 1000
    if filter_volume:
        min_volume = get_int_input("  最低日均量（張）", 1000, min_val=0)
    
    print()

    # ============================================================
    # 漲停篩選
    # ============================================================
    print("【漲停篩選】")
    print("-" * 60)
    filter_limit_up = get_yes_no("是否開啟漲停篩選？", default=False)
    lookback_days = 10
    limit_up_pct = 8.0
    if filter_limit_up:
        lookback_days = get_int_input("  回溯天數", 10, min_val=1, max_val=60)
        limit_up_pct = get_float_input("  漲停門檻（%）", 8.0, min_val=5, max_val=10)
    
    print()

    # ============================================================
    # RSI+MA 策略篩選
    # ============================================================
    print("【RSI+MA 策略篩選】")
    print("-" * 60)
    filter_rsi_ma = get_yes_no("是否開啟 RSI+MA 策略篩選？", default=False)
    rsi_period = 14
    ma_period = 20
    rsi_oversold = 30.0
    if filter_rsi_ma:
        rsi_period = get_int_input("  RSI 週期", 14, min_val=5, max_val=30)
        ma_period = get_int_input("  MA 週期", 20, min_val=5, max_val=60)
        rsi_oversold = get_float_input("  RSI 超賣閾值", 30.0, min_val=10, max_val=50)
    
    print()

    # ============================================================
    # 布林通道篩選
    # ============================================================
    print("【布林通道開口向上篩選】")
    print("-" * 60)
    filter_bbands = get_yes_no("是否開啟布林通道篩選？", default=False)
    bbands_period = 20
    bbands_std = 2.0
    bbands_expand_min = 0.05
    if filter_bbands:
        bbands_period = get_int_input("  布林通道週期", 20, min_val=10, max_val=50)
        bbands_std = get_float_input("  標準差倍數", 2.0, min_val=1.0, max_val=3.0)
        bbands_expand_min = get_float_input("  開口擴張門檻（%）", 5.0, min_val=1, max_val=20) / 100
    
    print()

    # ============================================================
    # 排序設定
    # ============================================================
    print("【排序設定】")
    print("-" * 60)
    print("排序欄位選項：")
    print("  1. 殖利率 (dividend_yield)")
    print("  2. 市值 (market_cap)")
    print("  3. 本益比 (pe_ratio)")
    print("  4. 成交量 (volume)")
    print("  5. 不排序")
    
    sort_choice = get_int_input("請選擇排序欄位 (1-5)", 1, min_val=1, max_val=5)
    sort_by_map = {
        1: "dividend_yield",
        2: "market_cap",
        3: "pe_ratio",
        4: "volume",
        5: ""
    }
    sort_by = sort_by_map[sort_choice]
    sort_desc = True
    if sort_by:
        sort_desc = get_yes_no(f"  是否由大到小排序？", default=True)

    print()

    # ============================================================
    # 建立設定並執行
    # ============================================================
    print("=" * 60)
    print("開始篩選...")
    print("=" * 60)

    cfg = ScreenerConfig(
        lookback_days=lookback_days,
        filter_limit_up=filter_limit_up,
        filter_dividend=filter_dividend,
        filter_rsi_ma=filter_rsi_ma,
        filter_bbands=filter_bbands,
        filter_volume=filter_volume,
        filter_market_cap=use_market_cap,
        filter_pe_ratio=filter_pe,
        limit_up_pct=limit_up_pct,
        min_dividend_yield=min_dividend_yield,
        rsi_period=rsi_period,
        ma_period=ma_period,
        rsi_oversold=rsi_oversold,
        bbands_period=bbands_period,
        bbands_std=bbands_std,
        bbands_expand_min=bbands_expand_min,
        min_volume=min_volume,
        min_market_cap=min_market_cap,
        max_market_cap=max_market_cap,
        min_pe_ratio=min_pe,
        max_pe_ratio=max_pe,
        max_stocks=9999,
        sort_by=sort_by,
        sort_desc=sort_desc
    )

    # 執行篩選
    results = run_screener(cfg, deep=False)

    # 如果有設定價格範圍，額外過濾
    if use_price_filter and results:
        filtered = []
        for r in results:
            price = None
            if r.dividend:
                price = r.dividend.get("price")
            if price and min_price <= price <= max_price:
                filtered.append(r)
        
        removed = len(results) - len(filtered)
        results = filtered
        if removed > 0:
            print(f"\n💰 價格篩選：移除 {removed} 筆不在 {min_price}~{max_price} 元範圍內的股票")
            print(f"   剩餘：{len(results)} 筆")

    # 生成 Excel
    if results:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"stock_report_{timestamp}.xlsx"
        export_to_excel(results, cfg, filename)
        print(f"\n✅ 篩選完成！共 {len(results)} 筆結果")
    else:
        print("\n❌ 無符合條件的股票")


if __name__ == "__main__":
    try:
        interactive_screener()
    except KeyboardInterrupt:
        print("\n\n❌ 使用者中斷")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 發生錯誤：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
