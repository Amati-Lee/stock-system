# -*- coding: utf-8 -*-
"""
margin_stats.py — 融資融券的**描述統計**（第 3 步）

⛔⛔ 這支刻意**不做任何 IS/OOS 勝率比較、不做分組報酬**。
   理由：現在急著找「能用的篩選條件」，正是蓄勢紅框和 ADX 組合栽掉的路徑。
   先搞清楚「這是什麼資料、和既有的重不重複」，篩選留到預先登記之後。

回答兩個問題：
  1. 覆蓋率夠不夠（多少警示配得到融資資料）
  2. ⭐ **融資是不是一條新的資訊軸** —— 和法人維持率／Hurst／ADX 的秩相關有多高
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import glob
import json
import os
from collections import defaultdict

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MARGIN_DIR = os.path.join(SCRIPT_DIR, "margin_history")
ALERTS_DIR = os.path.join(SCRIPT_DIR, "alerts_history")
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")


def load_margin():
    """回傳 (dates 由早到晚, {code: {date: {欄位}}})"""
    by_code = defaultdict(dict)
    dates = []
    for p in sorted(glob.glob(os.path.join(MARGIN_DIR, "margin_*.json"))):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        dates.append(d["date"])
        fields = d["fields"]
        for code, row in d["data"].items():
            by_code[code][d["date"]] = dict(zip(fields, row))
    return sorted(dates), by_code


def pct(vals, ps=(10, 25, 50, 75, 90)):
    if not vals:
        return "（無資料）"
    a = np.array(vals, dtype=float)
    return "  ".join(f"p{p}={np.percentile(a, p):+.2f}" for p in ps)


def spearman(x, y):
    """秩相關，不依賴 scipy。回傳 (rho, n)"""
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None
             and np.isfinite(a) and np.isfinite(b)]
    if len(pairs) < 30:
        return None, len(pairs)
    a = np.array([p[0] for p in pairs], dtype=float)
    b = np.array([p[1] for p in pairs], dtype=float)

    def rank(v):
        order = v.argsort()
        r = np.empty(len(v), dtype=float)
        r[order] = np.arange(len(v), dtype=float)
        # 處理並列：同值取平均秩
        _, inv, cnt = np.unique(v, return_inverse=True, return_counts=True)
        sums = np.zeros(len(cnt))
        np.add.at(sums, inv, r)
        return (sums / cnt)[inv]

    ra, rb = rank(a), rank(b)
    if ra.std() == 0 or rb.std() == 0:
        return None, len(pairs)
    return float(np.corrcoef(ra, rb)[0, 1]), len(pairs)


def calc_retention(rows, field, lookback=20):
    vals = [r[field] for r in rows[-lookback:] if field in r]
    if len(vals) < 5:
        return None
    cum = peak = 0
    for v in vals:
        cum += v
        if cum > peak:
            peak = cum
    return round(cum / peak, 2) if peak > 0 else None


def main():
    mdates, margin = load_margin()
    if not mdates:
        print("⛔ margin_history 是空的，先跑 download_margin.py --days 130")
        return
    print("=" * 96)
    print("  融資融券 — 描述統計（⛔ 本檔不做任何勝率／分組報酬比較）")
    print("=" * 96)
    print(f"融資資料：{len(mdates)} 天  {mdates[0]} ~ {mdates[-1]}，"
          f"涵蓋 {len(margin)} 支股票")
    midx = {d: i for i, d in enumerate(mdates)}

    # ---- 警示配對 ----
    alerts = []
    for af in sorted(glob.glob(os.path.join(ALERTS_DIR, "alerts_*.json"))):
        with open(af, encoding="utf-8") as f:
            fd = json.load(f)
        date = fd["date"].replace("-", "")
        for a in fd.get("alerts", []):
            alerts.append((a["code"], date, a))

    def mb_change(code, date, n):
        """融資餘額相對 n 個「有融資資料的日子」前的變化率(%)"""
        h = margin.get(code)
        if not h or date not in h:
            return None
        i = midx.get(date)
        if i is None or i - n < 0:
            return None
        prev = h.get(mdates[i - n])
        if not prev or not prev["mb"]:
            return None
        return (h[date]["mb"] - prev["mb"]) / prev["mb"] * 100

    rows = []
    matched = 0
    for code, date, a in alerts:
        h = margin.get(code)
        if not h or date not in h:
            continue
        matched += 1
        cur = h[date]
        mb, sb, mlim = cur["mb"], cur["sb"], cur["mlimit"]
        rows.append({
            "code": code, "date": date,
            "mb": mb,
            "chg5": mb_change(code, date, 5),
            "chg20": mb_change(code, date, 20),
            "sratio": (sb / mb * 100) if mb else None,      # 券資比 %
            "muse": (mb / mlim * 100) if mlim else None,    # 資使用率 %
            "hurst": a.get("hurst"),
            "score": a.get("score"),
            "chg_pct": a.get("chg_pct"),
        })

    print(f"警示共 {len(alerts)} 筆，配得到融資資料 {matched} 筆 "
          f"（{matched / len(alerts) * 100:.1f}%）")
    print("⚠️ 配不到的主要是興櫃與無信用交易資格的股票 —— 那是真的沒有融資，不是漏抓")

    print("\n【分佈】（單位 %）")
    print(f"  融資餘額 5 日變化   {pct([r['chg5'] for r in rows if r['chg5'] is not None])}")
    print(f"  融資餘額 20 日變化  {pct([r['chg20'] for r in rows if r['chg20'] is not None])}")
    print(f"  券資比              {pct([r['sratio'] for r in rows if r['sratio'] is not None])}")
    print(f"  資使用率            {pct([r['muse'] for r in rows if r['muse'] is not None])}")

    # ---- 和既有指標的相關性 ----
    print("\n" + "=" * 96)
    print("  ⭐ 融資是不是一條新的資訊軸？（Spearman 秩相關）")
    print("     |rho| < 0.2 ＝ 幾乎獨立，值得加；> 0.5 ＝ 高度重疊，加了是白加")
    print("=" * 96)

    # 補上法人維持率與 ADX（從 OHLC 現算）
    sys.path.insert(0, SCRIPT_DIR)
    from backtest_dmi import dmi

    ohlc_cache = {}

    def get_rows(code):
        if code not in ohlc_cache:
            p = os.path.join(OHLC_DIR, f"{code}.json")
            ohlc_cache[code] = json.load(open(p, encoding="utf-8")) \
                if os.path.exists(p) else None
        return ohlc_cache[code]

    for r in rows:
        o = get_rows(r["code"])
        if not o:
            r["ret_fi"] = r["adx"] = None
            continue
        upto = [x for x in o if x["t"] <= r["date"]]
        r["ret_fi"] = calc_retention(upto, "fi")
        r["adx"] = dmi(upto)[2] if len(upto) >= 40 else None

    targets = [
        ("法人維持率 R", "ret_fi"),
        ("Hurst", "hurst"),
        ("ADX", "adx"),
        ("警示分數", "score"),
        ("當日漲幅", "chg_pct"),
    ]
    mine = [("融資 5 日變化", "chg5"), ("融資 20 日變化", "chg20"),
            ("券資比", "sratio"), ("資使用率", "muse")]

    print(f"  {'':<16}" + "".join(f"{t[0]:>14}" for t in targets))
    for mlabel, mkey in mine:
        line = f"  {mlabel:<16}"
        for _, tkey in targets:
            rho, n = spearman([r[mkey] for r in rows], [r[tkey] for r in rows])
            line += f"{(f'{rho:+.2f}' if rho is not None else '—'):>14}"
        print(line)
    n_ok = sum(1 for r in rows if r["chg20"] is not None and r["ret_fi"] is not None)
    print(f"\n  （相關性以兩邊都有值的樣本計算，例如融資20日×法人維持率 n={n_ok}）")
    print("=" * 96)


if __name__ == "__main__":
    main()
