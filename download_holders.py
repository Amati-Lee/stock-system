# -*- coding: utf-8 -*-
"""
download_holders.py — 集保戶股權分散表（大戶持股），存成 holders_history/holders_YYYYMMDD.json

⛔⛔ TDCC OpenData 的 `scaDate` 參數**完全無效**，不管給哪一天都回最新一期，
     而且 HTTP 200、CSV 格式正確、六萬多列 —— **看起來完全成功**。
     （2026-09-24 實測：指定 0911／0821／0424，三次都回 0918）
   ⇒ 本檔**絕不用查詢日期蓋章**，一律以 CSV 自己的「資料日期」為準。
     和櫃買 stk_quote_result 是同一個病，見 reference_stock_ohlc_tpex_date。

⭐ 因此也**沒有回補功能**：官方 bulk 只給最新一週，歷史只能單支查（全市場 ×25 週
   ≈ 5 萬次請求，不可接受）。這支只能從現在開始每週累積。

⭐ 排程策略：**每天跑，只有出現新一期才寫檔**。
   理由：發布時差不確定（週五的資料不知道週一還是週三才出），
   與其猜星期幾而猜錯漏掉，不如每天問一次——成本是一個請求。

用法：
    python download_holders.py            # 有新一期就存，沒有就跳過
    python download_holders.py --force    # 已存在也重寫
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import argparse
import csv
import io
import json
import os
import ssl
import urllib.request
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, "holders_history")
URL = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

LEVELS = 15          # 持股分級 1~15，15 = 1,000,001 股以上（千張大戶）
MIN_STOCKS = 1000    # 少於這個數就當抓壞了，不寫


def fetch_csv():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180, context=SSL_CTX) as r:
        raw = r.read()
    # ⚠️ TDCC 回的是 CSV 不是 JSON，而且帶 BOM
    return raw.decode("utf-8-sig", errors="replace"), len(raw)


def parse(text):
    """回傳 (資料日期集合, {code: {level: (人數, 股數, 占比)}})"""
    by_code = defaultdict(dict)
    dates = set()
    for row in csv.DictReader(io.StringIO(text)):
        d = (row.get("資料日期") or "").strip()
        code = (row.get("證券代號") or "").strip()
        lv = (row.get("持股分級") or "").strip()
        if not (d and code and lv.isdigit()):
            continue
        dates.add(d)
        try:
            people = int(float((row.get("人數") or "0").replace(",", "")))
            shares = int(float((row.get("股數") or "0").replace(",", "")))
            pct = float((row.get("占集保庫存數比例%") or "0").replace(",", ""))
        except ValueError:
            continue
        by_code[code][int(lv)] = (people, shares, pct)
    return dates, by_code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    text, nbytes = fetch_csv()
    dates, by_code = parse(text)
    print(f"下載 {nbytes/1024/1024:.1f} MB，解析出 {len(by_code)} 支股票")

    if not dates:
        print("⛔ 解析不出任何資料日期，不寫入")
        return
    if len(dates) != 1:
        # 正常情況只會有一個日期；多個代表格式變了，先停下來別亂存
        print(f"⛔ 同一份檔案出現 {len(dates)} 個資料日期 {sorted(dates)}，格式可能變了，不寫入")
        return
    date = dates.pop()
    print(f"⭐ 資料日期（以 CSV 自己說的為準，不是我們指定的）：{date}")

    # 只留 4 碼純數字的股票（濾掉 ETF/權證/TDR 等）
    stocks = {c: v for c, v in by_code.items() if len(c) == 4 and c.isdigit()}
    print(f"   其中 4 碼股票 {len(stocks)} 支（其餘 {len(by_code)-len(stocks)} 支為 ETF／權證等）")

    if len(stocks) < MIN_STOCKS:
        print(f"⛔ 只有 {len(stocks)} 支，低於門檻 {MIN_STOCKS}，不寫入（避免壞資料蓋掉好的）")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"holders_{date}.json")
    if os.path.exists(path) and not args.force:
        have = sorted(f[8:16] for f in os.listdir(OUT_DIR) if f.startswith("holders_"))
        print(f"✅ {date} 已經有了，跳過（目前累積 {len(have)} 期"
              + (f"：{have[0]} ~ {have[-1]}）" if have else "）"))
        return

    # 存法：每支股票兩個長度 15 的陣列 —— 占比% 與 人數。
    # 保留完整 15 級距而不是只存「大戶比例」，這樣日後改定義不用重抓
    # （反正官方歷史抓不回來，這是一次性的機會）
    data = {}
    incomplete = 0
    for code, lv in stocks.items():
        if len(lv) < LEVELS:
            incomplete += 1
        pct = [round(lv.get(i, (0, 0, 0.0))[2], 2) for i in range(1, LEVELS + 1)]
        ppl = [lv.get(i, (0, 0, 0.0))[0] for i in range(1, LEVELS + 1)]
        data[code] = [pct, ppl]

    out = {
        "date": date,
        "count": len(data),
        "incomplete": incomplete,
        "levels": LEVELS,
        "note": "每支股票 = [占集保庫存數比例%(1~15), 人數(1~15)]；級距15 = 1,000,001股以上",
        "data": data,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(path) / 1024
    print(f"✅ 寫入 {path}（{size:.0f} KB，{len(data)} 支，級距不齊 {incomplete} 支）")

    # 抽樣讓人眼睛能檢查
    for c in ("2330", "6488"):
        if c in data:
            pct = data[c][0]
            print(f"   {c}：千張大戶(級距15) {pct[14]:.2f}%　"
                  f"400張以上(12~15) {sum(pct[11:]):.2f}%　"
                  f"合計 {sum(pct):.2f}%")

    have = sorted(f[8:16] for f in os.listdir(OUT_DIR) if f.startswith("holders_"))
    print(f"   holders_history 累積 {len(have)} 期：{have[0]} ~ {have[-1]}")


if __name__ == "__main__":
    main()
