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

    output = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "trade_date": trade_date,
        "count": len(merged),
        "data": merged,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)
    print(f"輸出: {OUT_PATH} ({len(merged)} stocks)")


if __name__ == "__main__":
    main()
