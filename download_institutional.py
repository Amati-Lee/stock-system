"""
download_institutional.py — 下載三大法人買賣超資料
從 TWSE/TPEx 公開 API 取得當日三大法人個股買賣超
輸出 pwa/institutional.json
"""
import json
import os
import glob
import urllib.request
import ssl
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(SCRIPT_DIR, "pwa", "institutional.json")

# 建立不驗證 SSL 的 context（TWSE 偶爾憑證問題）
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def get_trade_date():
    """從最新 CSV 檔名取得交易日 YYYYMMDD"""
    csvs = sorted(glob.glob(os.path.join(SCRIPT_DIR, "stock_data_*.csv")))
    if not csvs:
        return datetime.now().strftime("%Y%m%d")
    return os.path.basename(csvs[-1]).replace("stock_data_", "").replace(".csv", "")


def fetch_twse(date_str):
    """
    上市三大法人買賣超 (TWSE T86)
    date_str: YYYYMMDD
    回傳 {code: {foreign, trust, dealer, total}}
    """
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALLBUT0999&response=json"
    result = {}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30, context=SSL_CTX)
        data = json.loads(resp.read().decode("utf-8"))

        if data.get("stat") != "OK" or "data" not in data:
            print(f"  TWSE T86: stat={data.get('stat', 'N/A')}")
            return result

        for row in data["data"]:
            code = str(row[0]).strip()
            if len(code) != 4:
                continue
            try:
                # 欄位: 證券代號, 證券名稱, 外陸資買進, 外陸資賣出, 外陸資買賣超,
                #       外資自營買進, 外資自營賣出, 外資自營買賣超,
                #       投信買進, 投信賣出, 投信買賣超,
                #       自營商買賣超, 自營(自行)買賣超, 自營(避險)買賣超,
                #       三大法人買賣超合計
                def parse_int(s):
                    return int(str(s).replace(",", "").replace(" ", ""))

                foreign = parse_int(row[4])   # 外陸資買賣超（股）
                trust = parse_int(row[10])     # 投信買賣超（股）
                dealer = parse_int(row[11])    # 自營商買賣超（股）
                total = parse_int(row[-1])     # 三大法人合計（股）

                result[code] = {
                    "foreign": round(foreign / 1000),   # 轉換為張
                    "trust": round(trust / 1000),
                    "dealer": round(dealer / 1000),
                    "total": round(total / 1000),
                }
            except (ValueError, IndexError):
                continue

        print(f"  TWSE: {len(result)} stocks")
    except Exception as e:
        print(f"  TWSE error: {e}")
    return result


def fetch_tpex(date_str):
    """
    上櫃三大法人買賣超 (TPEx)
    date_str: YYYYMMDD -> 轉為民國年 YYY/MM/DD
    回傳 {code: {foreign, trust, dealer, total}}
    """
    # 轉民國年
    y = int(date_str[:4]) - 1911
    tw_date = f"{y}/{date_str[4:6]}/{date_str[6:8]}"
    url = f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={tw_date}"
    result = {}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30, context=SSL_CTX)
        data = json.loads(resp.read().decode("utf-8"))

        # 新版 API: tables[0].data
        tables = data.get("tables", [])
        rows = tables[0].get("data", []) if tables else []
        if not rows:
            # fallback 舊版
            rows = data.get("aaData", [])
        if not rows:
            print(f"  TPEx: no data")
            return result

        for row in rows:
            code = str(row[0]).strip()
            if len(code) != 4:
                continue
            try:
                def parse_int(s):
                    return int(str(s).replace(",", "").replace(" ", ""))

                # 24 欄: 代號, 名稱,
                #   外資(不含自營) 買/賣/淨 [2-4],
                #   外資自營 買/賣/淨 [5-7],
                #   外資合計 買/賣/淨 [8-10],
                #   投信 買/賣/淨 [11-13],
                #   自營(自行) 買/賣/淨 [14-16],
                #   自營(避險) 買/賣/淨 [17-19],
                #   自營合計 買/賣/淨 [20-22],
                #   三大法人合計 [23]
                foreign = parse_int(row[10])   # 外資合計淨買（股）
                trust = parse_int(row[13])     # 投信淨買（股）
                dealer = parse_int(row[22])    # 自營合計淨買（股）
                total = parse_int(row[23])     # 三大法人合計（股）

                result[code] = {
                    "foreign": round(foreign / 1000),
                    "trust": round(trust / 1000),
                    "dealer": round(dealer / 1000),
                    "total": round(total / 1000),
                }
            except (ValueError, IndexError):
                continue

        print(f"  TPEx: {len(result)} stocks")
    except Exception as e:
        print(f"  TPEx error: {e}")
    return result


HISTORY_DAYS = 5  # 保留最近幾個交易日


def load_existing():
    """讀取現有 institutional.json，回傳 (dates, data) 或空值"""
    if not os.path.exists(OUT_PATH):
        return [], {}
    try:
        with open(OUT_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)
        # 新格式: dates + data with arrays
        if "dates" in existing:
            return existing["dates"], existing["data"]
        # 舊格式: 單日，轉換為新格式
        if "trade_date" in existing and "data" in existing:
            td = existing["trade_date"]
            old_data = {}
            for code, vals in existing["data"].items():
                old_data[code] = {
                    "foreign": [vals.get("foreign", 0)],
                    "trust": [vals.get("trust", 0)],
                    "dealer": [vals.get("dealer", 0)],
                    "total": [vals.get("total", 0)],
                }
            return [td], old_data
    except Exception as e:
        print(f"  讀取舊檔失敗: {e}")
    return [], {}


def main():
    trade_date = get_trade_date()
    print(f"下載三大法人資料: {trade_date}")

    twse = fetch_twse(trade_date)
    tpex = fetch_tpex(trade_date)

    # 合併
    merged = {**twse, **tpex}
    if not merged:
        print("無法取得法人資料")
        return

    # 累積多日資料
    dates, hist_data = load_existing()

    # 如果今天已經在裡面，先移除（重跑時覆蓋）
    if trade_date in dates:
        idx = dates.index(trade_date)
        dates.pop(idx)
        for code in hist_data:
            for key in ("foreign", "trust", "dealer", "total"):
                arr = hist_data[code].get(key, [])
                if idx < len(arr):
                    arr.pop(idx)

    # 把今天加到最前面（index 0 = 最新）
    dates.insert(0, trade_date)

    # 收集所有曾出現的股票代碼
    all_codes = set(hist_data.keys()) | set(merged.keys())

    new_data = {}
    for code in all_codes:
        old = hist_data.get(code, {})
        today = merged.get(code, {})
        new_data[code] = {
            "foreign": [today.get("foreign", 0)] + old.get("foreign", []),
            "trust": [today.get("trust", 0)] + old.get("trust", []),
            "dealer": [today.get("dealer", 0)] + old.get("dealer", []),
            "total": [today.get("total", 0)] + old.get("total", []),
        }

    # 只保留最近 N 天
    if len(dates) > HISTORY_DAYS:
        dates = dates[:HISTORY_DAYS]
        for code in new_data:
            for key in ("foreign", "trust", "dealer", "total"):
                new_data[code][key] = new_data[code][key][:HISTORY_DAYS]

    output = {
        "dates": dates,
        "count": len(new_data),
        "data": new_data,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)
    print(f"輸出: {OUT_PATH} ({len(new_data)} stocks, {len(dates)} days: {', '.join(dates)})")

    # 注入法人資料到 OHLC JSON
    inject_to_ohlc(merged, trade_date)


def inject_to_ohlc(inst_data, trade_date):
    """把法人買賣超注入到每支股票的 OHLC JSON（累積歷史）"""
    ohlc_dir = os.path.join(SCRIPT_DIR, "pwa", "ohlc")
    if not os.path.isdir(ohlc_dir):
        print("  OHLC 目錄不存在，跳過注入")
        return

    injected = 0
    for code, inst in inst_data.items():
        ohlc_path = os.path.join(ohlc_dir, f"{code}.json")
        if not os.path.exists(ohlc_path):
            continue
        try:
            with open(ohlc_path, "r", encoding="utf-8") as f:
                ohlc = json.load(f)
            if not ohlc:
                continue

            # 找到對應交易日的記錄，注入法人資料
            updated = False
            for entry in ohlc:
                if entry.get("t") == trade_date:
                    entry["fi"] = inst["foreign"]  # 外資
                    entry["ti"] = inst["trust"]     # 投信
                    entry["di"] = inst["dealer"]    # 自營
                    updated = True
                    break

            if updated:
                with open(ohlc_path, "w", encoding="utf-8") as f:
                    json.dump(ohlc, f, ensure_ascii=False)
                injected += 1
        except Exception:
            continue

    print(f"  法人注入 OHLC: {injected} stocks")


if __name__ == "__main__":
    main()
