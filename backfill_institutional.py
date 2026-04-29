"""
backfill_institutional.py — 回補歷史法人買賣超到 OHLC
抓過去 N 天的三大法人資料，注入到 pwa/ohlc/*.json
用法: python backfill_institutional.py [天數，預設60]
"""
import json
import os
import sys
import time
import urllib.request
import ssl
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def fetch_twse(date_str):
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALLBUT0999&response=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30, context=SSL_CTX)
        data = json.loads(resp.read().decode("utf-8"))
        if data.get("stat") != "OK" or "data" not in data:
            return {}
        result = {}
        for row in data["data"]:
            code = str(row[0]).strip()
            if len(code) != 4:
                continue
            try:
                def p(s): return int(str(s).replace(",", "").replace(" ", ""))
                result[code] = {
                    "fi": round(p(row[4]) / 1000),
                    "ti": round(p(row[10]) / 1000),
                    "di": round(p(row[11]) / 1000),
                }
            except (ValueError, IndexError):
                continue
        return result
    except Exception:
        return {}


def fetch_tpex(date_str):
    y = int(date_str[:4]) - 1911
    tw_date = f"{y}/{date_str[4:6]}/{date_str[6:8]}"
    url = f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={tw_date}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30, context=SSL_CTX)
        data = json.loads(resp.read().decode("utf-8"))
        tables = data.get("tables", [])
        rows = tables[0].get("data", []) if tables else []
        if not rows:
            rows = data.get("aaData", [])
        if not rows:
            return {}
        result = {}
        for row in rows:
            code = str(row[0]).strip()
            if len(code) != 4:
                continue
            try:
                def p(s): return int(str(s).replace(",", "").replace(" ", ""))
                result[code] = {
                    "fi": round(p(row[10]) / 1000),
                    "ti": round(p(row[13]) / 1000),
                    "di": round(p(row[22]) / 1000),
                }
            except (ValueError, IndexError):
                continue
        return result
    except Exception:
        return {}


def inject_to_ohlc(inst_data, trade_date):
    injected = 0
    for code, inst in inst_data.items():
        ohlc_path = os.path.join(OHLC_DIR, f"{code}.json")
        if not os.path.exists(ohlc_path):
            continue
        try:
            with open(ohlc_path, "r", encoding="utf-8") as f:
                ohlc = json.load(f)
            updated = False
            for entry in ohlc:
                if entry.get("t") == trade_date:
                    if "fi" not in entry:  # 不覆蓋已有資料
                        entry["fi"] = inst["fi"]
                        entry["ti"] = inst["ti"]
                        entry["di"] = inst["di"]
                        updated = True
                    break
            if updated:
                with open(ohlc_path, "w", encoding="utf-8") as f:
                    json.dump(ohlc, f, ensure_ascii=False)
                injected += 1
        except Exception:
            continue
    return injected


def get_trading_dates(days):
    """從 OHLC 檔案取得實際交易日列表"""
    sample = os.path.join(OHLC_DIR, "2330.json")
    if not os.path.exists(sample):
        return []
    with open(sample, "r", encoding="utf-8") as f:
        ohlc = json.load(f)
    dates = [e["t"] for e in ohlc]
    return dates[-days:]


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 60

    if not os.path.isdir(OHLC_DIR):
        print("OHLC 目錄不存在")
        return

    dates = get_trading_dates(days)
    if not dates:
        print("無法取得交易日列表")
        return

    print(f"回補法人資料: {len(dates)} 個交易日 ({dates[0]} ~ {dates[-1]})")
    print()

    total_injected = 0
    for i, date_str in enumerate(dates):
        print(f"  [{i+1}/{len(dates)}] {date_str} ...", end=" ", flush=True)

        twse = fetch_twse(date_str)
        time.sleep(1)  # 避免被擋
        tpex = fetch_tpex(date_str)
        time.sleep(1)

        merged = {**twse, **tpex}
        if not merged:
            print("no data (holiday?)")
            continue

        injected = inject_to_ohlc(merged, date_str)
        total_injected += injected
        print(f"TWSE:{len(twse)} TPEx:{len(tpex)} -> injected:{injected}")

    print(f"\n完成! 共注入 {total_injected} 筆")


if __name__ == "__main__":
    main()
