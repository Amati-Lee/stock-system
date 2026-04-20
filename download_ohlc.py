# -*- coding: utf-8 -*-
"""
download_ohlc.py
從每日 CSV 建構 OHLC 歷史資料，存為個別 JSON 檔案供 K 線圖使用。
取代舊版 yfinance 下載方式，純本地檔案 I/O，無網路依賴。
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import csv
import glob
import json
import os
import time
from datetime import datetime, timedelta

OUTPUT_DIR = "pwa/ohlc"
HISTORY_DAYS = 548  # ~18 個月


def scan_csvs(since_date=None):
    """
    掃描所有 stock_data_*.csv，收集每支股票的 OHLC。
    since_date: "YYYYMMDD" 字串，只處理此日期之後的 CSV（加速增量更新）。
    回傳 dict[code] -> list[{t, o, h, l, c, v}]
    """
    files = sorted(glob.glob("stock_data_*.csv"))
    if since_date:
        files = [f for f in files if f.replace('stock_data_', '').replace('.csv', '') > since_date]

    if not files:
        return {}

    result = {}  # code -> list of entries
    for fpath in files:
        try:
            with open(fpath, encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    code = row['股票代號'].strip().split('.')[0]
                    trade_date = row.get('交易日', '').strip()
                    if not trade_date:
                        continue
                    t = trade_date.replace('-', '')

                    try:
                        o = round(float(row['開盤價']), 2)
                        h = round(float(row['最高價']), 2)
                        l = round(float(row['最低價']), 2)
                        c = round(float(row['收盤價']), 2)
                        v = int(float(row['成交量張'].replace(',', '')))
                    except (ValueError, KeyError):
                        continue

                    if o <= 0 or c <= 0:
                        continue

                    if code not in result:
                        result[code] = []
                    result[code].append({'t': t, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v})
        except Exception as e:
            print(f"  ⚠ 讀取 {fpath} 失敗: {e}")

    return result


def load_existing_ohlc():
    """
    讀取現有 pwa/ohlc/*.json。
    回傳 (dict[code] -> list[entries], latest_dates dict[code] -> "YYYYMMDD")
    """
    existing = {}
    latest_dates = {}
    if not os.path.isdir(OUTPUT_DIR):
        return existing, latest_dates

    for fname in os.listdir(OUTPUT_DIR):
        if not fname.endswith('.json'):
            continue
        code = fname[:-5]
        fpath = os.path.join(OUTPUT_DIR, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                entries = json.load(f)
            if entries:
                existing[code] = entries
                latest_dates[code] = max(e['t'] for e in entries)
        except Exception:
            continue

    return existing, latest_dates


def merge_and_trim(existing_entries, new_entries, cutoff):
    """
    合併既有與新 OHLC 資料，去重（新資料優先），排序，裁剪過期資料。
    cutoff: "YYYYMMDD" 字串
    """
    # 用 dict 去重，新資料覆蓋舊資料
    by_date = {}
    for e in existing_entries:
        by_date[e['t']] = e
    for e in new_entries:
        by_date[e['t']] = e

    # 排序 + 裁剪
    merged = sorted(by_date.values(), key=lambda x: x['t'])
    return [e for e in merged if e['t'] >= cutoff]


def main():
    start = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. 載入現有 OHLC
    print("載入現有 OHLC...")
    existing, latest_dates = load_existing_ohlc()
    print(f"  現有: {len(existing)} 支股票")

    # 2. 決定要掃描哪些 CSV（增量）
    since_date = None
    if latest_dates:
        # 從最舊的 "最新日期" 開始掃，確保所有股票都補到
        since_date = min(latest_dates.values())
        print(f"  增量模式: 掃描 {since_date} 之後的 CSV")
    else:
        print("  全量模式: 掃描所有 CSV")

    # 3. 掃描 CSV
    print("掃描 CSV 檔案...")
    csv_data = scan_csvs(since_date)
    total_new_entries = sum(len(v) for v in csv_data.values())
    print(f"  CSV: {len(csv_data)} 支股票, {total_new_entries} 筆資料")

    # 4. 合併 + 裁剪
    cutoff = (datetime.now() - timedelta(days=HISTORY_DAYS)).strftime('%Y%m%d')
    all_codes = sorted(set(list(existing.keys()) + list(csv_data.keys())))
    print(f"合併中... ({len(all_codes)} 支股票, 裁剪 < {cutoff})")

    written = 0
    for code in all_codes:
        old = existing.get(code, [])
        new = csv_data.get(code, [])

        if not old and not new:
            continue

        merged = merge_and_trim(old, new, cutoff)
        if not merged:
            continue

        fpath = os.path.join(OUTPUT_DIR, f"{code}.json")
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, separators=(',', ':'))
        written += 1

    elapsed = time.time() - start
    print()
    print(f"完成！{written} 支股票, 耗時 {elapsed:.1f}s")
    print(f"檔案: {OUTPUT_DIR}/")


if __name__ == '__main__':
    main()
