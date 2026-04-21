# -*- coding: utf-8 -*-
"""
download_ohlc.py
建構 OHLC 歷史資料，存為個別 JSON 檔案供 K 線圖使用。
資料來源：
  1. 證交所 MI_INDEX + 櫃買中心 OpenAPI（最新交易日，自動下載）
  2. 本地 stock_data_*.csv（歷史補充）
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import csv
import glob
import json
import os
import time
from datetime import datetime, timedelta

try:
    import requests
except ImportError:
    requests = None

OUTPUT_DIR = "pwa/ohlc"
HISTORY_DAYS = 548  # ~18 個月

# 證交所 MI_INDEX（收盤後即時更新，比 OpenAPI 快）
TWSE_MI_INDEX = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={date}&type=ALLBUT0999"
# 櫃買中心 OpenAPI（收盤後即時更新）
TPEX_API = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"


def roc_to_western(roc_date):
    """民國日期 '1150421' → 西元 '20260421'"""
    roc_date = roc_date.strip()
    if len(roc_date) == 7 and roc_date.isdigit():
        year = int(roc_date[:3]) + 1911
        return f"{year}{roc_date[3:]}"
    return roc_date


def safe_float(val):
    """解析數字字串，移除逗號"""
    return float(str(val).replace(",", ""))


def fetch_twse(date_str):
    """
    從證交所 MI_INDEX 下載指定日期全市場 OHLCV。
    date_str: "YYYYMMDD"
    回傳 (dict[code] -> {t,o,h,l,c,v}, actual_date)
    """
    url = TWSE_MI_INDEX.format(date=date_str)
    try:
        resp = requests.get(url, timeout=30)
    except requests.exceptions.SSLError:
        resp = requests.get(url, timeout=30, verify=False)
    resp.raise_for_status()
    data = resp.json()

    if data.get("stat") != "OK":
        return {}, None

    # 找股票收盤行情表（tables 中 fields 包含「證券代號」的那個）
    stock_table = None
    for table in data.get("tables", []):
        fields = table.get("fields", [])
        if "證券代號" in fields and "開盤價" in fields:
            stock_table = table
            break

    if not stock_table:
        return {}, None

    fields = stock_table["fields"]
    idx_code = fields.index("證券代號")
    idx_open = fields.index("開盤價")
    idx_high = fields.index("最高價")
    idx_low = fields.index("最低價")
    idx_close = fields.index("收盤價")
    idx_vol = fields.index("成交股數")

    # 從 title 抽日期，例如 "115年04月21日 每日收盤行情..."
    title = stock_table.get("title", "")
    actual_date = date_str  # fallback
    if "年" in title and "月" in title and "日" in title:
        try:
            y = int(title.split("年")[0].strip()[-3:]) + 1911
            m = int(title.split("年")[1].split("月")[0].strip())
            d = int(title.split("月")[1].split("日")[0].strip())
            actual_date = f"{y}{m:02d}{d:02d}"
        except (ValueError, IndexError):
            pass

    result = {}
    for row in stock_table.get("data", []):
        try:
            code = row[idx_code].strip()
            o = round(safe_float(row[idx_open]), 2)
            h = round(safe_float(row[idx_high]), 2)
            low = round(safe_float(row[idx_low]), 2)
            c = round(safe_float(row[idx_close]), 2)
            v = int(safe_float(row[idx_vol])) // 1000  # 股→張
        except (ValueError, IndexError):
            continue
        if o <= 0 or c <= 0:
            continue
        result[code] = {"t": actual_date, "o": o, "h": h, "l": low, "c": c, "v": v}

    return result, actual_date


def fetch_tpex():
    """
    從櫃買中心 OpenAPI 下載最新一天全市場 OHLCV。
    回傳 (dict[code] -> {t,o,h,l,c,v}, trade_date)
    """
    resp = requests.get(TPEX_API, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    result = {}
    trade_date = None
    for row in data:
        code = row.get("SecuritiesCompanyCode", "").strip()
        if not code:
            continue
        try:
            o = round(float(row["Open"]), 2)
            h = round(float(row["High"]), 2)
            low = round(float(row["Low"]), 2)
            c = round(float(row["Close"]), 2)
            v = int(float(row["TradingShares"])) // 1000  # 股→張
            t = roc_to_western(row.get("Date", ""))
        except (ValueError, KeyError):
            continue
        if o <= 0 or c <= 0:
            continue
        if trade_date is None:
            trade_date = t
        result[code] = {"t": t, "o": o, "h": h, "l": low, "c": c, "v": v}

    return result, trade_date


def fetch_from_api():
    """
    從證交所/櫃買中心下載最新全市場 OHLCV。
    回傳 (dict[code] -> list[{t,o,h,l,c,v}], trade_date_str)
    """
    if requests is None:
        print("  ⚠ requests 未安裝，跳過 API 下載")
        return {}, None

    result = {}
    trade_date = None

    # --- TWSE (上市) via MI_INDEX ---
    today_str = datetime.now().strftime("%Y%m%d")
    try:
        twse_data, twse_date = fetch_twse(today_str)
        if twse_data:
            trade_date = twse_date
            for code, entry in twse_data.items():
                result[code] = [entry]
            print(f"  TWSE: {len(twse_data)} 支 (日期: {twse_date})")
        else:
            print(f"  TWSE: 無資料 (可能非交易日)")
    except Exception as e:
        print(f"  ⚠ TWSE API 失敗: {e}")

    # --- TPEx (上櫃) ---
    try:
        tpex_data, tpex_date = fetch_tpex()
        if tpex_data:
            for code, entry in tpex_data.items():
                result[code] = [entry]
            print(f"  TPEx: {len(tpex_data)} 支 (日期: {tpex_date})")
            if tpex_date and (trade_date is None or tpex_date > trade_date):
                trade_date = tpex_date
        else:
            print(f"  TPEx: 無資料")
    except Exception as e:
        print(f"  ⚠ TPEx API 失敗: {e}")

    return result, trade_date


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
                    td = row.get('交易日', '').strip()
                    if not td:
                        continue
                    t = td.replace('-', '')

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
    by_date = {}
    for e in existing_entries:
        by_date[e['t']] = e
    for e in new_entries:
        by_date[e['t']] = e

    merged = sorted(by_date.values(), key=lambda x: x['t'])
    return [e for e in merged if e['t'] >= cutoff]


def main():
    start = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. 載入現有 OHLC
    print("載入現有 OHLC...")
    existing, latest_dates = load_existing_ohlc()
    print(f"  現有: {len(existing)} 支股票")

    # 2. 從證交所/櫃買中心 API 下載最新資料
    print("從證交所/櫃買中心下載最新資料...")
    api_data, api_date = fetch_from_api()

    # 3. 掃描 CSV 補充歷史（增量）
    since_date = None
    if latest_dates:
        since_date = min(latest_dates.values())
        print(f"  增量 CSV: 掃描 {since_date} 之後")
    else:
        print("  全量 CSV: 掃描所有")
    csv_data = scan_csvs(since_date)
    if csv_data:
        total_new = sum(len(v) for v in csv_data.values())
        print(f"  CSV: {len(csv_data)} 支, {total_new} 筆")
    else:
        print("  CSV: 無新資料")

    # 4. 合併 API + CSV（API 資料優先，覆蓋同日 CSV）
    merged_new = {}
    for code, entries in csv_data.items():
        merged_new[code] = entries
    for code, entries in api_data.items():
        if code not in merged_new:
            merged_new[code] = []
        merged_new[code].extend(entries)

    # 5. 合併到 OHLC + 裁剪
    cutoff = (datetime.now() - timedelta(days=HISTORY_DAYS)).strftime('%Y%m%d')
    all_codes = sorted(set(list(existing.keys()) + list(merged_new.keys())))
    print(f"合併中... ({len(all_codes)} 支股票, 裁剪 < {cutoff})")

    written = 0
    for code in all_codes:
        old = existing.get(code, [])
        new = merged_new.get(code, [])

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
    if api_date:
        print(f"API 日期: {api_date}")
    print(f"檔案: {OUTPUT_DIR}/")


if __name__ == '__main__':
    main()
