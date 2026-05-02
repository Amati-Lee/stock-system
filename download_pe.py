# -*- coding: utf-8 -*-
"""
download_pe.py — PE 河流位置計算
從 TWSE + TPEx 抓取本益比，維護歷史快取，計算 PE 在歷史區間的百分位
"""
import json
import os
import sys
import time
import glob
import urllib.request
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(SCRIPT_DIR, "pe_history.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "pwa", "pe_river.json")


def fetch_twse_pe(date_str):
    """TWSE 上市 PE ratio. date_str: YYYYMMDD"""
    url = f"https://www.twse.com.tw/exchangeReport/BWIBBU_d?response=json&date={date_str}&selectType=ALL"
    req = urllib.request.Request(url, headers={"User-Agent": "stock-system/1.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  TWSE {date_str} 失敗: {e}")
        return {}
    if data.get("stat") != "OK" or not data.get("data"):
        return {}
    result = {}
    for row in data["data"]:
        code = row[0].strip()
        try:
            # TWSE 欄位: 代號, 名稱, 收盤價, 殖利率, 股利年度, 本益比, PBR, 財報期
            pe_str = str(row[5]).strip().replace(",", "")
            pe = float(pe_str) if pe_str not in ("-", "", "0") else None
        except (ValueError, IndexError):
            continue
        if pe and pe > 0:
            result[code] = pe
    print(f"  TWSE {date_str}: {len(result)} 支")
    return result


def fetch_tpex_pe(date_str):
    """TPEx 上櫃 PE ratio. date_str: YYYYMMDD"""
    y = int(date_str[:4]) - 1911
    m = date_str[4:6]
    d = date_str[6:8]
    roc_date = f"{y}/{m}/{d}"
    url = f"https://www.tpex.org.tw/web/stock/aftertrading/peratio_analysis/pera_result.php?l=zh-tw&o=json&d={roc_date}&c=&s=0,asc,0"
    req = urllib.request.Request(url, headers={"User-Agent": "stock-system/1.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  TPEx {date_str} 失敗: {e}")
        return {}
    rows = []
    if data.get("aaData"):
        rows = data["aaData"]
    elif data.get("tables") and data["tables"]:
        rows = data["tables"][0].get("data", [])
    if not rows:
        return {}
    result = {}
    for row in rows:
        code = str(row[0]).strip()
        try:
            pe_str = str(row[2]).strip().replace(",", "")
            pe = float(pe_str) if pe_str not in ("-", "", "0", "N/A") else None
        except (ValueError, IndexError):
            continue
        if pe and pe > 0:
            result[code] = pe
    print(f"  TPEx {date_str}: {len(result)} 支")
    return result


def fetch_pe_for_date(date_str):
    """Fetch PE from both TWSE + TPEx, retrying previous days if needed.
    Both must return data to be considered a valid trading day."""
    d = datetime.strptime(date_str, "%Y%m%d")
    for attempt in range(7):
        ds = d.strftime("%Y%m%d")
        twse = fetch_twse_pe(ds)
        time.sleep(3)
        tpex = fetch_tpex_pe(ds)
        if twse and tpex:
            combined = {}
            combined.update(twse)
            combined.update(tpex)
            return ds, combined
        if twse or tpex:
            print(f"  {ds} 僅部分資料（TWSE:{len(twse)} TPEx:{len(tpex)}），往前一天")
        else:
            print(f"  {ds} 非交易日，往前一天")
        d -= timedelta(days=1)
        time.sleep(2)
    return None, {}


def get_backfill_targets(latest_date):
    """Generate monthly dates going back 36 months for initial backfill"""
    base = datetime.strptime(latest_date, "%Y%m%d")
    targets = []
    for months_back in range(1, 37):
        d = base - timedelta(days=months_back * 30)
        targets.append(d.strftime("%Y%m%d"))
    return targets


def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"dates": {}}


def save_cache(cache):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f)


def main():
    print("=" * 40)
    print("  PE 河流位置計算")
    print("=" * 40)

    # Find latest trading date from CSV
    csvs = sorted(glob.glob(os.path.join(SCRIPT_DIR, "stock_data_*.csv")))
    if not csvs:
        print("無 CSV 交易資料，跳過")
        return
    latest = os.path.basename(csvs[-1]).replace("stock_data_", "").replace(".csv", "")
    print(f"最新交易日: {latest}")

    cache = load_cache()
    dates_in_cache = set(cache["dates"].keys())

    # Check if today already cached
    need_today = latest not in dates_in_cache
    need_backfill = len(dates_in_cache) < 30

    if not need_today and not need_backfill:
        print(f"快取已有 {len(dates_in_cache)} 個日期（含 {latest}），無需抓取")
    else:
        dates_to_fetch = []
        if need_today:
            dates_to_fetch.append(latest)
        if need_backfill:
            for target in get_backfill_targets(latest):
                # Don't fetch dates already in cache (check nearby dates too)
                already = any(abs(int(target) - int(d)) < 5 for d in dates_in_cache)
                if not already and target not in [d[0] for d in dates_to_fetch if isinstance(d, tuple)]:
                    dates_to_fetch.append(target)

        print(f"需要抓取 {len(dates_to_fetch)} 個日期")
        for target in dates_to_fetch:
            print(f"\n抓取 {target}...")
            actual_date, pe_data = fetch_pe_for_date(target)
            if actual_date and pe_data:
                cache["dates"][actual_date] = pe_data
                save_cache(cache)
                print(f"  已存入 {actual_date} ({len(pe_data)} 支)")
            time.sleep(3)

    # Calculate PE river position
    if not cache["dates"]:
        print("無 PE 資料")
        return

    all_dates = sorted(cache["dates"].keys())
    latest_date = all_dates[-1]
    latest_pe = cache["dates"][latest_date]
    print(f"\n計算 PE 河流位置（基準日 {latest_date}，歷史 {len(all_dates)} 個日期）")

    result = {}
    for code, pe in latest_pe.items():
        hist = []
        for d in all_dates:
            if code in cache["dates"][d]:
                hist.append(cache["dates"][d][code])

        if len(hist) < 2:
            result[code] = {"pe": round(pe, 1), "pct": 50}
            continue

        pe_min = min(hist)
        pe_max = max(hist)
        if pe_max == pe_min:
            pct = 50
        else:
            pct = round((pe - pe_min) / (pe_max - pe_min) * 100)
            pct = max(0, min(100, pct))

        result[code] = {
            "pe": round(pe, 1),
            "low": round(pe_min, 1),
            "high": round(pe_max, 1),
            "pct": pct
        }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f)
    print(f"輸出: {OUTPUT_PATH} ({len(result)} 支)")


if __name__ == "__main__":
    main()
