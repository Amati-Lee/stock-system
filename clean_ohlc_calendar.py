# -*- coding: utf-8 -*-
"""
clean_ohlc_calendar.py — 清掉 pwa/ohlc 裡的假日期與錯價

背景：download_ohlc.py 的「TPEx 回補前 2 天」用日曆日往回推，而櫃買中心那支歷史 API
      查過去日期時**一律回傳最新交易日**的行情。舊版程式用「查詢日期」蓋章，於是：
        1. 週末被寫出整批假列（2026-07-18 起共 9 個週末、約 870 支上櫃股）
        2. 最近 1-2 個交易日的上櫃收盤被寫成後一天的價格（例：8/20 存的是 8/21 的價）
      根因已修（fetch_tpex_date 改用 API 回報的日期 + 呼叫端比對不符就跳過），
      這支負責清既有髒資料。

用法：
    python clean_ohlc_calendar.py            # 只檢查不改（預設）
    python clean_ohlc_calendar.py --apply    # 實際寫回

修法（分兩類，預設只動「確定是 bug」的那一類）：
    A. 週末列 → 直接刪（不是交易日，沒有正確值可還原）
    B. 價格對不上當日 CSV，**且剛好等於後面某個交易日的 CSV** → 這就是日期蓋章 bug 的指紋，
       以當日 CSV 修正 o/h/l/c/v（法人欄位保留）
    C. 其他對不上的（兩邊誰對不確定）→ 只列出來，不動。要一起修加 --repair-unknown
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import csv
import datetime
import glob
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")
APPLY = "--apply" in sys.argv
REPAIR_UNKNOWN = "--repair-unknown" in sys.argv
SHIFT_LOOKAHEAD = 5  # 往後找幾個交易日來認「日期蓋章」指紋


def load_csv_reference():
    """{date: {code: (o,h,l,c,v)}}，以每日 CSV 為權威"""
    ref = {}
    for path in sorted(glob.glob(os.path.join(SCRIPT_DIR, "stock_data_*.csv"))):
        date = os.path.basename(path)[11:19]
        day = {}
        try:
            with open(path, encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    code = (row.get("股票代號") or "").strip()
                    if not code:
                        continue
                    try:
                        o = float(row["開盤價"]); h = float(row["最高價"])
                        low = float(row["最低價"]); c = float(row["收盤價"])
                        v = int(float(row.get("成交量張") or 0))
                    except (ValueError, KeyError, TypeError):
                        continue
                    if o <= 0 or c <= 0:
                        continue
                    day[code] = (o, h, low, c, v)
        except OSError:
            continue
        if day:
            ref[date] = day
    return ref


def main():
    ref = load_csv_reference()
    print(f"CSV 權威日曆：{len(ref)} 天（{min(ref)} ~ {max(ref)}）")
    print("模式：" + ("實際寫回 (--apply)" if APPLY else "只檢查不改（加 --apply 才會寫）"))

    cal = sorted(ref)
    cal_idx = {d: i for i, d in enumerate(cal)}

    def looks_shifted(code, date, row):
        """這一列是不是「後面某個交易日的資料被蓋上這個日期」"""
        i = cal_idx.get(date)
        if i is None:
            return False
        for d2 in cal[i + 1:i + 1 + SHIFT_LOOKAHEAD]:
            t2 = ref[d2].get(code)
            if not t2:
                continue
            if (abs(row.get("o", 0) - t2[0]) <= 0.011 and abs(row.get("h", 0) - t2[1]) <= 0.011
                    and abs(row.get("l", 0) - t2[2]) <= 0.011 and abs(row.get("c", 0) - t2[3]) <= 0.011):
                return True
        return False

    files = sorted(glob.glob(os.path.join(OHLC_DIR, "*.json")))
    n_files = n_touched = n_weekend = n_fixed = 0
    weekend_dates, fixed_dates, unknown_dates = {}, {}, {}

    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                rows = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        n_files += 1
        out, changed = [], False
        for r in rows:
            t = r.get("t", "")
            if len(t) != 8 or not t.isdigit():
                out.append(r)
                continue
            if datetime.datetime.strptime(t, "%Y%m%d").weekday() >= 5:
                n_weekend += 1
                weekend_dates[t] = weekend_dates.get(t, 0) + 1
                changed = True
                continue                      # 週末列直接刪
            code = os.path.basename(path)[:-5]
            truth = ref.get(t, {}).get(code)
            if truth:
                o, h, low, c, v = truth
                if (abs(r.get("o", 0) - o) > 0.011 or abs(r.get("h", 0) - h) > 0.011
                        or abs(r.get("l", 0) - low) > 0.011 or abs(r.get("c", 0) - c) > 0.011):
                    if looks_shifted(code, t, r) or REPAIR_UNKNOWN:
                        r = dict(r)
                        r.update({"o": o, "h": h, "l": low, "c": c, "v": v})
                        n_fixed += 1
                        fixed_dates[t] = fixed_dates.get(t, 0) + 1
                        changed = True
                    else:
                        unknown_dates[t] = unknown_dates.get(t, 0) + 1
            out.append(r)
        if changed:
            n_touched += 1
            if APPLY:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n掃描 {n_files} 檔，其中 {n_touched} 檔需要處理")
    print(f"  刪除週末假列 {n_weekend} 列：")
    for d in sorted(weekend_dates):
        print(f"    {d} {weekend_dates[d]} 列")
    print(f"  依 CSV 修正「日期蓋章」錯價 {n_fixed} 列：")
    for d in sorted(fixed_dates):
        print(f"    {d} {fixed_dates[d]} 列")
    unk = sum(unknown_dates.values())
    print(f"  其他對不上、誰對不確定的 {unk} 列（未動，要修加 --repair-unknown）：")
    for d in sorted(unknown_dates):
        print(f"    {d} {unknown_dates[d]} 列")
    if not APPLY:
        print("\n（以上為試算，未寫回。確認後加 --apply）")


if __name__ == "__main__":
    main()
