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
import shutil
import time
from datetime import datetime, timedelta

try:
    import requests
except ImportError:
    requests = None

OUTPUT_DIR = "pwa/ohlc"
BACKUP_DIR = "pwa/ohlc_backup"
HEALTH_FILE = "pwa/ohlc_backup/health.json"
SNAPSHOT_FILE = "ohlc_snapshot.tar.gz"  # commit 到 git，cache miss 時兜底
HISTORY_DAYS = 548  # ~18 個月
HEALTHY_DAYS_TO_BACKUP = 3  # 連續健康 N 天才更新備份
SNAPSHOT_MIN_STOCKS = 5000  # snapshot 最少要有這麼多支才算有效

# 證交所 MI_INDEX（收盤後即時更新，比 OpenAPI 快）
TWSE_MI_INDEX = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={date}&type=ALLBUT0999"
# 櫃買中心 OpenAPI（收盤後即時更新）
TPEX_API = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
# 櫃買中心歷史收盤行情（用於回補前幾天資料）
TPEX_HISTORY = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&d={roc_date}&stkno=&o=json"


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


def fetch_tpex_date(date_str):
    """
    從櫃買中心歷史 API 下載指定日期全市場 OHLCV。
    date_str: "YYYYMMDD"
    回傳 (dict[code] -> {t,o,h,l,c,v}, actual_date)
    """
    dt = datetime.strptime(date_str, "%Y%m%d")
    roc_year = dt.year - 1911
    roc_date = f"{roc_year}/{dt.month:02d}/{dt.day:02d}"
    url = TPEX_HISTORY.format(roc_date=roc_date)
    try:
        resp = requests.get(url, timeout=30)
    except requests.exceptions.SSLError:
        resp = requests.get(url, timeout=30, verify=False)
    resp.raise_for_status()
    data = resp.json()

    if data.get("stat") != "ok":
        return {}, None
    tables = data.get("tables", [])
    if not tables or not tables[0].get("data"):
        return {}, None

    result = {}
    actual_date = date_str
    for row in tables[0]["data"]:
        try:
            code = row[0].strip()
            if not code or len(code) != 4:
                continue
            o = round(safe_float(row[4]), 2)
            h = round(safe_float(row[5]), 2)
            low = round(safe_float(row[6]), 2)
            c = round(safe_float(row[2]), 2)
            v = int(safe_float(row[8])) // 1000
        except (ValueError, IndexError):
            continue
        if o <= 0 or c <= 0:
            continue
        result[code] = {"t": date_str, "o": o, "h": h, "l": low, "c": c, "v": v}

    return result, date_str if result else None


def fetch_from_api():
    """
    從證交所/櫃買中心下載最新全市場 OHLCV。
    同時抓前 1-2 天的 TWSE 資料，修正可能的盤前舊資料。
    回傳 (dict[code] -> list[{t,o,h,l,c,v}], trade_date_str)
    """
    if requests is None:
        print("  ⚠ requests 未安裝，跳過 API 下載")
        return {}, None

    result = {}
    trade_date = None

    # --- TWSE (上市) via MI_INDEX ---
    # 抓今天 + 前 2 天，確保前一交易日收盤價正確（修正盤前 CSV 的舊資料）
    today = datetime.now()
    twse_dates = [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(3)]
    for date_str in twse_dates:
        try:
            twse_data, twse_date = fetch_twse(date_str)
            if twse_data:
                if trade_date is None or (twse_date and twse_date > trade_date):
                    trade_date = twse_date
                for code, entry in twse_data.items():
                    if code not in result:
                        result[code] = []
                    result[code].append(entry)
                if date_str == twse_dates[0]:
                    print(f"  TWSE: {len(twse_data)} 支 (日期: {twse_date})")
                else:
                    print(f"  TWSE 回補: {len(twse_data)} 支 (日期: {twse_date})")
            elif date_str == twse_dates[0]:
                print(f"  TWSE: 無資料 (可能非交易日)")
        except Exception as e:
            if date_str == twse_dates[0]:
                print(f"  ⚠ TWSE API 失敗: {e}")

    # --- TPEx (上櫃) ---
    # 先抓最新一天，再回補前 2 天
    try:
        tpex_data, tpex_date = fetch_tpex()
        if tpex_data:
            for code, entry in tpex_data.items():
                if code not in result:
                    result[code] = []
                result[code].append(entry)
            print(f"  TPEx: {len(tpex_data)} 支 (日期: {tpex_date})")
            if tpex_date and (trade_date is None or tpex_date > trade_date):
                trade_date = tpex_date
        else:
            print(f"  TPEx: 無資料")
    except Exception as e:
        print(f"  ⚠ TPEx API 失敗: {e}")

    # TPEx 回補前 2 天
    tpex_dates = [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(1, 3)]
    for date_str in tpex_dates:
        try:
            tpex_hist, tpex_hist_date = fetch_tpex_date(date_str)
            if tpex_hist:
                for code, entry in tpex_hist.items():
                    if code not in result:
                        result[code] = []
                    result[code].append(entry)
                print(f"  TPEx 回補: {len(tpex_hist)} 支 (日期: {tpex_hist_date})")
        except Exception:
            pass

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
        t = e['t']
        if t in by_date:
            # 保留舊資料的法人欄位（fi/ti/di）
            old = by_date[t]
            for k in ('fi', 'ti', 'di'):
                if k in old and k not in e:
                    e[k] = old[k]
        by_date[t] = e

    merged = sorted(by_date.values(), key=lambda x: x['t'])
    return [e for e in merged if e['t'] >= cutoff]


def save_snapshot():
    """將 pwa/ohlc/ 壓縮為 ohlc_snapshot.tar.gz（commit 到 git 當備份）"""
    import tarfile
    count = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith('.json')])
    if count < SNAPSHOT_MIN_STOCKS:
        print(f"  ⚠ 只有 {count} 支，不更新 snapshot（需 >= {SNAPSHOT_MIN_STOCKS}）")
        return False
    # 深度檢查：至少 500 支有 >= 20 筆，避免淺資料覆蓋好的 snapshot
    deep = 0
    for fname in os.listdir(OUTPUT_DIR):
        if not fname.endswith('.json'):
            continue
        try:
            fpath = os.path.join(OUTPUT_DIR, fname)
            with open(fpath, 'r', encoding='utf-8') as f:
                entries = json.load(f)
            if len(entries) >= 20:
                deep += 1
        except Exception:
            continue
    if deep < 500:
        print(f"  ⚠ 只有 {deep} 支有 >= 20 筆歷史，不更新 snapshot（避免覆蓋好的備份）")
        return False
    tmp = SNAPSHOT_FILE + ".tmp"
    with tarfile.open(tmp, "w:gz") as tar:
        tar.add(OUTPUT_DIR, arcname="ohlc")
    os.replace(tmp, SNAPSHOT_FILE)
    size_mb = os.path.getsize(SNAPSHOT_FILE) / 1024 / 1024
    print(f"  📦 snapshot 已更新: {count} 支, {size_mb:.1f} MB → {SNAPSHOT_FILE}")
    return True


def restore_from_snapshot():
    """從 ohlc_snapshot.tar.gz 還原（cache miss 時的兜底）"""
    import tarfile
    if not os.path.exists(SNAPSHOT_FILE):
        print(f"  ⚠ 無 {SNAPSHOT_FILE} 可還原")
        return False
    size_mb = os.path.getsize(SNAPSHOT_FILE) / 1024 / 1024
    with tarfile.open(SNAPSHOT_FILE, "r:gz") as tar:
        tar.extractall("pwa")  # extracts ohlc/ into pwa/ohlc/
    count = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith('.json')])
    print(f"  🔄 從 snapshot 還原: {count} 支 ({size_mb:.1f} MB)")
    return count >= SNAPSHOT_MIN_STOCKS


def check_ohlc_health(api_date):
    """
    檢查 OHLC 是否健康：
    - 至少 1000 支股票有 api_date 的資料
    回傳 healthy_count
    """
    if not api_date or not os.path.isdir(OUTPUT_DIR):
        return 0
    count = 0
    for fname in os.listdir(OUTPUT_DIR):
        if not fname.endswith('.json'):
            continue
        fpath = os.path.join(OUTPUT_DIR, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                entries = json.load(f)
            if entries and entries[-1]['t'] == api_date:
                count += 1
        except Exception:
            continue
    return count


def load_health():
    """讀取健康狀態紀錄"""
    if os.path.exists(HEALTH_FILE):
        try:
            with open(HEALTH_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"consecutive": 0, "last_healthy": "", "last_backup": ""}


def save_health(health):
    """儲存健康狀態紀錄"""
    os.makedirs(os.path.dirname(HEALTH_FILE), exist_ok=True)
    with open(HEALTH_FILE, 'w', encoding='utf-8') as f:
        json.dump(health, f, ensure_ascii=False, indent=2)


def backup_ohlc(api_date):
    """將 OHLC 複製到備份資料夾"""
    if os.path.isdir(BACKUP_DIR):
        # 只刪 JSON 檔，保留 health.json
        for f in os.listdir(BACKUP_DIR):
            if f.endswith('.json') and f != 'health.json':
                os.remove(os.path.join(BACKUP_DIR, f))
    else:
        os.makedirs(BACKUP_DIR, exist_ok=True)

    count = 0
    for f in os.listdir(OUTPUT_DIR):
        if f.endswith('.json'):
            shutil.copy2(os.path.join(OUTPUT_DIR, f), os.path.join(BACKUP_DIR, f))
            count += 1

    health = load_health()
    health["last_backup"] = api_date
    save_health(health)
    print(f"  📦 備份完成: {count} 支股票 → {BACKUP_DIR}/")


def restore_from_backup():
    """從備份還原 OHLC"""
    if not os.path.isdir(BACKUP_DIR):
        print("  ⚠ 無備份可還原")
        return False

    backup_files = [f for f in os.listdir(BACKUP_DIR)
                    if f.endswith('.json') and f != 'health.json']
    if len(backup_files) < 100:
        print(f"  ⚠ 備份檔案太少 ({len(backup_files)})，跳過還原")
        return False

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    count = 0
    for f in backup_files:
        shutil.copy2(os.path.join(BACKUP_DIR, f), os.path.join(OUTPUT_DIR, f))
        count += 1

    health = load_health()
    print(f"  🔄 已從備份還原: {count} 支股票 (備份日期: {health.get('last_backup', '?')})")
    return True


def main():
    start = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. 載入現有 OHLC（cache miss 或淺資料時自動從 snapshot 還原）
    print("載入現有 OHLC...")
    existing, latest_dates = load_existing_ohlc()

    # 檢查是否需要從 snapshot 還原（stock 數不足 OR 資料太淺）
    need_restore = False
    if len(existing) < SNAPSHOT_MIN_STOCKS:
        print(f"  現有 {len(existing)} 支不足（cache miss？），嘗試從 snapshot 還原...")
        need_restore = True
    else:
        deep_count = sum(1 for entries in existing.values() if len(entries) >= 20)
        if deep_count < 500:
            print(f"  現有 {len(existing)} 支但只有 {deep_count} 支有 >= 20 筆歷史（淺資料），從 snapshot 還原...")
            need_restore = True

    if need_restore:
        if restore_from_snapshot():
            existing, latest_dates = load_existing_ohlc()

    print(f"  現有: {len(existing)} 支股票")

    # 2. 從證交所/櫃買中心 API 下載最新資料
    print("從證交所/櫃買中心下載最新資料...")
    api_data, api_date = fetch_from_api()

    # 3. 掃描 CSV 補充歷史（增量，但偵測淺資料時全量補齊）
    since_date = None
    if latest_dates:
        # 檢查 OHLC 深度：如果大量股票不到 20 筆，強制全量掃描
        shallow_count = sum(1 for code, entries in existing.items() if len(entries) < 20)
        deep_count = len(existing) - shallow_count
        if deep_count < 1000:
            print(f"  ⚠ OHLC 太淺: {shallow_count}/{len(existing)} 支不到 20 筆，強制全量 CSV 掃描")
            since_date = None
        else:
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

    # 6. 健��檢查 + 備份���理
    if api_date:
        healthy_count = check_ohlc_health(api_date)
        health = load_health()
        is_healthy = healthy_count >= 1000

        if is_healthy:
            if health.get("last_healthy", "") >= api_date:
                # 同一天重複跑，不累加
                pass
            else:
                health["consecutive"] = health.get("consecutive", 0) + 1
                health["last_healthy"] = api_date
                save_health(health)

            print(f"  ✅ 健康: {healthy_count} 支有 {api_date} 資料 "
                  f"(連續 {health['consecutive']} 天)")

            if health["consecutive"] >= HEALTHY_DAYS_TO_BACKUP:
                backup_ohlc(api_date)
                health = load_health()  # 重新讀取（backup_ohlc 已更新 last_backup）
                health["consecutive"] = 0
                save_health(health)
        else:
            print(f"  ⚠ 異常: 只有 {healthy_count} 支有 {api_date} 資料")
            if restore_from_backup():
                # 還原後重新跑合併
                health["consecutive"] = 0
                save_health(health)

    # 7. 更新 git snapshot（寫入數 >= 5000 才更新，避免壞資料覆蓋好的）
    if written >= SNAPSHOT_MIN_STOCKS:
        save_snapshot()

    elapsed = time.time() - start
    print()
    print(f"完成！{written} 支股票, 耗時 {elapsed:.1f}s")
    if api_date:
        print(f"API 日期: {api_date}")
    print(f"檔案: {OUTPUT_DIR}/")


if __name__ == '__main__':
    main()
