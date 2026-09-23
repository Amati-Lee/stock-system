# -*- coding: utf-8 -*-
"""
download_margin.py — 下載融資融券餘額，存成 margin_history/margin_YYYYMMDD.json

用途：回測用的**另一條資料軸**（法人＝主力，融資＝散戶槓桿）。
⛔ 刻意**不寫進 pwa/ohlc**：
   1. 使用者不需要顯示在 PWA 上，沒必要讓所有人多下載欄位
   2. `download_ohlc.py` 的 merge_and_trim() 只保留 ('fi','ti','di')，
      寫進去的新欄位**會在下一次 pipeline 跑到同一天時被靜靜清掉**（無錯誤訊息）

用法：
    python download_margin.py                 # 只抓最新交易日
    python download_margin.py --days 130      # 依 OHLC 交易日曆回補最近 130 天
    python download_margin.py --days 130 --force   # 連已存在的日期也重抓

⛔⛔ 三個踩過的坑（見 reference_stock_margin_api）：
   1. TWSE 的 tables[0] 是彙總表（3 列），**tables[1] 才是個股表**，取錯不會報錯
   2. 兩邊欄位順序不同，TPEx 融券是「券賣 券買 券償」（賣在前）
   3. 外部 API 的日期一定要對一次 —— 回傳日期 != 查詢日期就丟掉
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import argparse
import json
import os
import ssl
import time
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, "margin_history")
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")
CAL_SOURCE = ["2330", "0050", "6488"]     # 交易日曆取這幾支的日期聯集

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

TWSE_URL = ("https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
            "?date={date}&selectType=ALL&response=json")
TPEX_URL = ("https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/"
            "margin_bal_result.php?l=zh-tw&o=json&d={roc}")

# 存檔欄位順序（陣列存，省空間）
FIELDS = ["mb", "mbuy", "msell", "mlimit", "sb", "ssell", "sbuy"]
#          融資餘額 融資買 融資賣 融資限額 融券餘額 券賣 券買


def num(s):
    s = str(s).replace(",", "").replace(" ", "").strip()
    if s in ("", "-", "--"):
        return 0
    try:
        return int(float(s))
    except ValueError:
        return None


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_twse(date_str):
    """回傳 (dict[code] -> list, 診斷字串)。日期對不上一律回空。"""
    data = fetch(TWSE_URL.format(date=date_str))
    if data.get("stat") != "OK":
        return {}, f"stat={data.get('stat')!r}"
    said = str(data.get("date") or "")
    if said and said != date_str:
        # ⛔ 外部 API 的日期一定要對一次（stk_quote_result 就是這樣咬人的）
        return {}, f"API 回傳 {said} != 查詢 {date_str}，丟棄"

    tabs = data.get("tables") or []
    # ⛔ 不可寫死 tables[0]（那是 3 列的彙總表）。取「有『代號』欄且列數最多」的那張。
    cand = [t for t in tabs if (t.get("fields") or [None])[0] == "代號"]
    if not cand:
        return {}, f"找不到個股表（共 {len(tabs)} 張表）"
    tbl = max(cand, key=lambda t: len(t.get("data") or []))

    out = {}
    for r in tbl.get("data") or []:
        code = str(r[0]).strip()
        if len(code) != 4 or not code.isdigit():
            continue
        try:
            mbuy, msell, mpay, mprev, mb, mlim = (num(r[i]) for i in range(2, 8))
            sbuy, ssell, spay, sprev, sb = (num(r[i]) for i in range(8, 13))
        except (IndexError, TypeError):
            continue
        if None in (mbuy, msell, mpay, mprev, mb, sbuy, ssell, spay, sprev, sb):
            continue
        out[code] = {"row": [mb, mbuy, msell, mlim, sb, ssell, sbuy],
                     "chk": (mprev + mbuy - msell - mpay, mb,
                             sprev + ssell - sbuy - spay, sb)}
    return out, f"{len(out)} 支"


def parse_tpex(date_str):
    roc = f"{int(date_str[:4]) - 1911}/{date_str[4:6]}/{date_str[6:8]}"
    data = fetch(TPEX_URL.format(roc=roc))
    said = str(data.get("date") or "")
    if said and said != date_str:
        return {}, f"API 回傳 {said} != 查詢 {date_str}，丟棄"

    tabs = data.get("tables") or []
    rows = []
    for t in tabs:
        if t.get("data"):
            rows = t["data"]
            break
    if not rows:
        rows = data.get("aaData") or []
    if not rows:
        return {}, "無資料"

    out = {}
    for r in rows:
        code = str(r[0]).strip()
        if len(code) != 4 or not code.isdigit():
            continue
        try:
            # ⚠️ 和 TWSE 順序不同：前餘額 資買 資賣 現償 餘額 屬證金 使用率 限額
            mprev, mbuy, msell, mpay, mb = (num(r[i]) for i in range(2, 7))
            mlim = num(r[9])
            # ⚠️ 融券是「券賣 券買 券償」——賣在前
            sprev, ssell, sbuy, spay, sb = (num(r[i]) for i in range(10, 15))
        except (IndexError, TypeError):
            continue
        if None in (mprev, mbuy, msell, mpay, mb, sprev, ssell, sbuy, spay, sb):
            continue
        out[code] = {"row": [mb, mbuy, msell, mlim, sb, ssell, sbuy],
                     "chk": (mprev + mbuy - msell - mpay, mb,
                             sprev + ssell - sbuy - spay, sb)}
    return out, f"{len(out)} 支"


def verify_identity(merged):
    """⭐ 欄位有沒有對錯，恆等式會說話：
         融資今日 = 前日 + 買進 − 賣出 − 現金償還
         融券今日 = 前日 + 券賣 − 券買 − 券償
       映射一旦寫錯，這裡就會大量不符。回傳 (不符筆數, 總筆數, 例子)"""
    bad, examples = 0, []
    for code, v in merged.items():
        m_calc, m_real, s_calc, s_real = v["chk"]
        if m_calc != m_real or s_calc != s_real:
            bad += 1
            if len(examples) < 3:
                examples.append(f"{code} 資{m_calc}vs{m_real} 券{s_calc}vs{s_real}")
    return bad, len(merged), examples


def trading_days(n):
    days = set()
    for c in CAL_SOURCE:
        p = os.path.join(OHLC_DIR, f"{c}.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                days |= {e["t"] for e in json.load(f)}
    return sorted(days)[-n:] if n else sorted(days)


def run_one(date_str, force=False):
    path = os.path.join(OUT_DIR, f"margin_{date_str}.json")
    if os.path.exists(path) and not force:
        return "skip", 0

    tw, tw_msg = parse_twse(date_str)
    time.sleep(1.2)
    tp, tp_msg = parse_tpex(date_str)
    time.sleep(1.2)

    merged = {**tw, **tp}
    if not merged:
        print(f"  {date_str}  ⚠ 無資料（TWSE {tw_msg}／TPEx {tp_msg}）")
        return "empty", 0

    bad, total, examples = verify_identity(merged)
    rate = bad / total * 100 if total else 0
    # ⛔ 恆等式大量不符 ＝ 欄位映射錯了，寧可不寫也不要存錯的
    if rate > 2.0:
        print(f"  {date_str}  ⛔ 恆等式不符 {bad}/{total} ({rate:.1f}%)，不寫入。例：{examples}")
        return "badfields", 0

    out = {
        "date": date_str,
        "count": {"twse": len(tw), "tpex": len(tp), "total": len(merged)},
        "identity_mismatch": bad,
        "fields": FIELDS,
        "data": {c: v["row"] for c, v in merged.items()},
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  {date_str}  上市 {len(tw)} ／上櫃 {len(tp)} ／共 {len(merged)}"
          f"　恆等式不符 {bad} ({rate:.2f}%)")
    return "ok", len(merged)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0, help="依 OHLC 交易日曆回補最近 N 天")
    ap.add_argument("--force", action="store_true", help="已存在的日期也重抓")
    args = ap.parse_args()

    if args.days:
        dates = trading_days(args.days)
    else:
        dates = trading_days(1)
    if not dates:
        print("⛔ 取不到交易日曆（pwa/ohlc 不存在？）")
        return

    print(f"融資融券下載：{len(dates)} 個日期（{dates[0]} ~ {dates[-1]}）"
          f"{'，--force 重抓' if args.force else '，已存在的跳過'}")
    tally = {}
    for i, d in enumerate(dates, 1):
        try:
            st, _ = run_one(d, args.force)
        except Exception as e:
            print(f"  {d}  ⚠ 例外 {type(e).__name__}: {e}")
            st = "error"
        tally[st] = tally.get(st, 0) + 1
        if st == "skip" and i % 20 == 0:
            print(f"  …已跳過 {tally.get('skip', 0)} 個既有日期")

    print(f"\n完成：{tally}")
    have = sorted(f[7:15] for f in os.listdir(OUT_DIR) if f.startswith("margin_")) \
        if os.path.isdir(OUT_DIR) else []
    print(f"margin_history 目前有 {len(have)} 天"
          + (f"（{have[0]} ~ {have[-1]}）" if have else ""))


if __name__ == "__main__":
    main()
