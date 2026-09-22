# -*- coding: utf-8 -*-
"""
backfill_otc_ohlc.py
回補上櫃股 OHLC 歷史資料（從櫃買中心歷史 API）
只補不足 60 筆的上櫃股，不動已正常的資料
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
import os
import time
import requests
from datetime import datetime, timedelta

OHLC_DIR = "pwa/ohlc"
MARKET_FILE = "stock_market_type.json"
MIN_ENTRIES = 60

# 櫃買中心歷史收盤行情
TPEX_HISTORY_URL = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&d={roc_date}&stkno=&o=json"


def to_roc_date(dt):
    """datetime -> '115/04/20' 格式"""
    roc_year = dt.year - 1911
    return f"{roc_year}/{dt.month:02d}/{dt.day:02d}"


def safe_float(val):
    if isinstance(val, (int, float)):
        return float(val)
    return float(str(val).replace(",", "").strip())


def fetch_tpex_history(date_dt):
    """抓指定日期的櫃買中心全市場收盤行情"""
    roc_date = to_roc_date(date_dt)
    url = TPEX_HISTORY_URL.format(roc_date=roc_date)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if data.get("stat") != "ok":
        return {}
    tables = data.get("tables", [])
    if not tables or not tables[0].get("data"):
        return {}

    rows = tables[0]["data"]
    western_date = date_dt.strftime("%Y%m%d")
    result = {}
    for row in rows:
        try:
            code = str(row[0]).strip()
            if not code or not code[0].isdigit():
                continue
            c = safe_float(row[2])   # 收盤
            o = safe_float(row[4])   # 開盤
            h = safe_float(row[5])   # 最高
            low = safe_float(row[6]) # 最低
            v_str = str(row[8]).replace(",", "").strip()
            v = int(float(v_str)) // 1000  # 成交股數 -> 張
        except (ValueError, IndexError):
            continue

        if o <= 0 or c <= 0:
            continue

        result[code] = {"t": western_date, "o": round(o, 2), "h": round(h, 2),
                        "l": round(low, 2), "c": round(c, 2), "v": v}

    return result


def main():
    market = json.load(open(MARKET_FILE, encoding="utf-8"))
    otc_codes = set(k for k, v in market.items() if v == "上櫃")

    # 找出不足 MIN_ENTRIES 的上櫃股
    short_codes = {}
    for code in otc_codes:
        path = os.path.join(OHLC_DIR, f"{code}.json")
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            entries = json.load(f)
        if len(entries) < MIN_ENTRIES:
            short_codes[code] = entries

    print(f"不足 {MIN_ENTRIES} 筆的上櫃股: {len(short_codes)} 支")
    if not short_codes:
        print("全部已足夠，無需回補")
        return

    # 找出最早的 OHLC 日期（回補目標：從這之前開始往回抓）
    earliest = min(e[0]["t"] for e in short_codes.values())
    print(f"現有最早日期: {earliest}")

    # 計算需要回補的天數
    need_days = MIN_ENTRIES - min(len(e) for e in short_codes.values()) + 10  # 多抓 10 天緩衝
    print(f"預計回補 ~{need_days} 個交易日")

    # 生成日期清單（從 earliest 往前推）
    earliest_dt = datetime.strptime(earliest, "%Y%m%d")
    dates_to_fetch = []
    dt = earliest_dt - timedelta(days=1)
    calendar_days = need_days * 2  # 交易日約是日曆天的一半
    for _ in range(calendar_days):
        if dt.weekday() < 5:  # 排除週末
            dates_to_fetch.append(dt)
        dt -= timedelta(days=1)

    dates_to_fetch.reverse()  # 從早到晚
    print(f"將嘗試抓取 {len(dates_to_fetch)} 個日期")

    # 逐日抓取
    new_data = {}  # code -> list of entries
    fetched_dates = 0
    for date_dt in dates_to_fetch:
        date_str = date_dt.strftime("%Y%m%d")
        print(f"  抓取 {date_str} ...", end=" ", flush=True)
        try:
            day_data = fetch_tpex_history(date_dt)
        except Exception as e:
            print(f"失敗: {e}")
            time.sleep(3)
            continue

        if not day_data:
            print("無資料 (非交易日)")
            time.sleep(1)
            continue

        count = 0
        for code in short_codes:
            if code in day_data:
                if code not in new_data:
                    new_data[code] = []
                new_data[code].append(day_data[code])
                count += 1

        fetched_dates += 1
        print(f"OK, {count} 支匹配")
        time.sleep(1.5)  # 避免被封

    print(f"\n抓取完成: {fetched_dates} 個交易日")
    print(f"有新資料的股票: {len(new_data)} 支")

    # Merge 到現有 OHLC
    updated = 0
    for code, existing in short_codes.items():
        additions = new_data.get(code, [])
        if not additions:
            continue

        # 合併: 用 dict 去重，現有資料優先（保留法人欄位）
        by_date = {}
        for e in additions:
            by_date[e["t"]] = e
        for e in existing:
            # 現有資料覆蓋（保留 fi/ti/di）
            by_date[e["t"]] = e

        merged = sorted(by_date.values(), key=lambda x: x["t"])

        # 驗證
        old_len = len(existing)
        new_len = len(merged)
        if new_len < old_len:
            print(f"  {code}: 合併後筆數減少 ({old_len} -> {new_len})，跳過！")
            continue

        # 存檔
        path = os.path.join(OHLC_DIR, f"{code}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False)
        updated += 1

        if updated <= 5:
            print(f"  {code}: {old_len} -> {new_len} 筆")

    print(f"\n更新完成: {updated} 支")

    # 驗證結果
    still_short = 0
    for code in short_codes:
        path = os.path.join(OHLC_DIR, f"{code}.json")
        d = json.load(open(path))
        if len(d) < MIN_ENTRIES:
            still_short += 1
    print(f"仍不足 {MIN_ENTRIES} 筆: {still_short} 支")


if __name__ == "__main__":
    main()
