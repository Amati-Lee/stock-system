# -*- coding: utf-8 -*-
"""
download_ohlc.py
下載所有股票的 OHLC 歷史資料，存為個別 JSON 檔案供 K 線圖使用
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
import math
import os
import time
import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

OUTPUT_DIR = "pwa/ohlc"
PERIOD = "18mo"
MAX_WORKERS = 8


def get_all_stock_codes():
    """從最新 CSV 取得所有股票代號"""
    import glob
    files = sorted(glob.glob("stock_data_*.csv"), reverse=True)
    if not files:
        return []
    df = pd.read_csv(files[0], encoding="utf-8-sig")
    codes = df['股票代號'].astype(str).str.strip().tolist()
    # 去掉小數點（如 "2330.0" → "2330"）
    codes = [c.split('.')[0] for c in codes]
    return sorted(set(codes))


def get_market_map():
    """讀取市場分類"""
    path = "stock_market_type.json"
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def download_one(code, mkt_map):
    """下載單支股票的 OHLC（使用 Ticker.history，thread-safe）"""
    mkt = mkt_map.get(code, '')
    if mkt in ('上櫃', '興櫃'):
        suffixes = ['.TWO', '.TW']
    else:
        suffixes = ['.TW', '.TWO']

    for suffix in suffixes:
        try:
            ticker = yf.Ticker(f"{code}{suffix}")
            hist = ticker.history(period=PERIOD, auto_adjust=False)
            if hist is not None and len(hist) >= 5:
                entries = []
                for idx, row in hist.iterrows():
                    o = float(row['Open'])
                    h = float(row['High'])
                    l = float(row['Low'])
                    c = float(row['Close'])
                    v_raw = float(row['Volume'])
                    if any(math.isnan(x) for x in [o, h, l, c]):
                        continue
                    entries.append({
                        't': idx.strftime('%Y%m%d'),
                        'o': round(o, 2),
                        'h': round(h, 2),
                        'l': round(l, 2),
                        'c': round(c, 2),
                        'v': int(v_raw / 1000) if not math.isnan(v_raw) else 0
                    })
                return code, entries
        except Exception:
            continue
    return code, None


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    codes = get_all_stock_codes()
    mkt_map = get_market_map()
    print(f"共 {len(codes)} 支股票，使用 {MAX_WORKERS} 線程下載")
    print(f"輸出目錄: {OUTPUT_DIR}/")
    print()

    # 跳過非今天下載的舊檔（今天的一律重抓，確保拿到收盤價）
    today = datetime.now().strftime('%Y%m%d')
    skip = 0
    to_download = []
    for code in codes:
        fpath = os.path.join(OUTPUT_DIR, f"{code}.json")
        if os.path.exists(fpath):
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime('%Y%m%d')
            if mtime != today:
                skip += 1
                continue
        to_download.append(code)

    if skip:
        print(f"跳過 {skip} 支（今天已下載），剩餘 {len(to_download)} 支")

    ok = 0
    fail = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(download_one, code, mkt_map): code for code in to_download}
        for future in as_completed(futures):
            code, entries = future.result()
            if entries:
                fpath = os.path.join(OUTPUT_DIR, f"{code}.json")
                with open(fpath, 'w', encoding='utf-8') as f:
                    json.dump(entries, f, ensure_ascii=False, separators=(',', ':'))
                ok += 1
            else:
                fail += 1

            total = ok + fail
            if total % 50 == 0:
                elapsed = time.time() - start
                rate = total / elapsed if elapsed > 0 else 0
                eta = (len(to_download) - total) / rate if rate > 0 else 0
                print(f"  {total}/{len(to_download)} (成功 {ok}, 失敗 {fail}) — {elapsed:.0f}s, ETA {eta:.0f}s")

    elapsed = time.time() - start
    print()
    print(f"完成！成功 {ok}, 失敗 {fail}, 耗時 {elapsed:.0f}s")
    print(f"檔案: {OUTPUT_DIR}/")


if __name__ == '__main__':
    main()
