# -*- coding: utf-8 -*-
"""
backtest_stops.py — 加上停損／停利，看結論會不會變

前面所有回測都是「固定持有 N 天、無風控」。賺賠比 1.69 配上停損會是完全不同的東西，
這一塊一直沒測過。

⛔⛔ 關鍵設計：**同一組停損停利也要跑在全市場基準上**。
   停損本身就會改變報酬分布（砍掉左尾），如果基準也一樣變好，
   那改善就跟訊號無關 —— 只是風控的效果。不比基準就會把風控的功勞記到訊號頭上。

進場：訊號日隔一個交易日**開盤**
出場（每天依序判斷，最長持有 MAX_HOLD 個交易日）：
   1. 當日 low <= 停損價 → 以停損價出場
   2. 當日 high >= 停利價 → 以停利價出場
   3. 到期 → 收盤價出場
⚠️ 同一天同時觸及停損與停利時，**保守假設先觸停損**（我們沒有日內資料，無法知道先後）。
⚠️ 假設停損停利都能在該價位成交 —— 跳空時會比這樂觀，實際會更差。
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import argparse
import glob
import json
import os
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")
MAX_HOLD = 20
MIN_STOCKS_PER_DAY = 300
BASE_SAMPLE = 5          # 基準每 N 天取樣一次

sys.path.insert(0, SCRIPT_DIR)
from screen_persist import kd_series, macd_dif_series, dmi_series
from screen_new import calc_rsi_series


def simulate(bmap, cal, cidx, t, stop, target):
    """回傳 (報酬%, 持有天數, 出場原因) 或 None
    stop/target 為 None 表示不設"""
    i = cidx.get(t)
    if i is None or i + 1 >= len(cal):
        return None
    entry_bar = bmap.get(cal[i + 1])
    if not entry_bar or entry_bar["o"] <= 0:
        return None
    ep = entry_bar["o"]
    sp = ep * (1 - stop / 100) if stop else None
    tp = ep * (1 + target / 100) if target else None

    for h in range(1, MAX_HOLD + 1):
        if i + 1 + h - 1 >= len(cal):
            return None
        b = bmap.get(cal[i + h])          # 進場當天也算第 1 天
        if not b:
            continue
        if sp is not None and b["l"] <= sp:
            return ((sp - ep) / ep * 100, h, "停損")
        if tp is not None and b["h"] >= tp:
            return ((tp - ep) / ep * 100, h, "停利")
    last = bmap.get(cal[i + MAX_HOLD])
    if not last:
        return None
    return ((last["c"] - ep) / ep * 100, MAX_HOLD, "到期")


def stats(results):
    if not results:
        return None
    rs = [r[0] for r in results]
    win = [x for x in rs if x > 0]
    loss = [x for x in rs if x <= 0]
    aw = sum(win) / len(win) if win else 0.0
    al = abs(sum(loss) / len(loss)) if loss else 0.0
    p = len(win) / len(rs)
    return {
        "n": len(rs), "win": p * 100, "aw": aw, "al": al,
        "pr": (aw / al) if al > 0 else float("inf"),
        "ev": sum(rs) / len(rs),
        "hold": sum(r[1] for r in results) / len(results),
        "stop_pct": sum(1 for r in results if r[2] == "停損") / len(results) * 100,
        "tp_pct": sum(1 for r in results if r[2] == "停利") / len(results) * 100,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persist", type=int, default=5)
    args = ap.parse_args()
    N = args.persist

    mkt = json.load(open(os.path.join(SCRIPT_DIR, "stock_market_type.json"), encoding="utf-8"))
    store, cnt = {}, Counter()
    for path in glob.glob(os.path.join(OHLC_DIR, "*.json")):
        code = os.path.basename(path)[:-5]
        if len(code) != 4 or not code.isdigit() or mkt.get(code) not in ("上市", "上櫃"):
            continue
        try:
            bars = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if len(bars) < 80:
            continue
        store[code] = bars
        for b in bars:
            cnt[b["t"]] += 1
    cal = sorted(d for d, n in cnt.items() if n >= MIN_STOCKS_PER_DAY)
    cidx = {d: i for i, d in enumerate(cal)}
    print(f"母體 {len(store)} 支，交易日曆 {cal[0]} ~ {cal[-1]}（{len(cal)} 天）")

    # 蒐集訊號日
    sig, base = [], []
    for code, bars in store.items():
        bmap = {b["t"]: b for b in bars}
        closes = [b["c"] for b in bars]
        k, d_ = kd_series(bars)
        dif = macd_dif_series(closes)
        r6, r12 = calc_rsi_series(closes, 6), calc_rsi_series(closes, 12)
        pdi, mdi = dmi_series(bars)
        if not (k and dif and r6 and r12 and pdi):
            continue
        m = min(len(k), len(dif), len(r6), len(r12), len(pdi), len(bars))
        f_kd = [k[i] is not None and d_[i] is not None and k[i] > d_[i] for i in range(m)]
        f_md = [dif[i] > 0 for i in range(m)]
        f_rs = [r6[i] is not None and r12[i] is not None and r6[i] > r12[i] for i in range(m)]
        f_dm = [pdi[i] is not None and mdi[i] is not None and pdi[i] > mdi[i] for i in range(m)]
        for i in range(60, m):
            t = bars[i]["t"]
            if cidx.get(t) is None or cidx[t] + 1 + MAX_HOLD >= len(cal):
                continue
            if i % BASE_SAMPLE == 0:
                base.append((code, bmap, t))
            if (all(f_kd[i - N + 1:i + 1]) and all(f_md[i - N + 1:i + 1])
                    and all(f_rs[i - N + 1:i + 1]) and all(f_dm[i - N + 1:i + 1])):
                sig.append((code, bmap, t))

    print(f"訊號（四項連{N}天）{len(sig):,} 筆；基準（每{BASE_SAMPLE}天取樣）{len(base):,} 筆")

    GRID = [(None, None), (3, None), (5, None), (7, None), (10, None),
            (None, 10), (5, 10), (5, 15), (7, 10), (7, 15), (10, 15), (10, 20)]

    for tag, pool in (("【訊號組：四項技術持續】", sig), ("【對照：全市場基準】", base)):
        print("\n" + "=" * 122)
        print(f"  {tag}")
        print("=" * 122)
        print(f"  {'停損':>6}{'停利':>6}{'n':>8}{'勝率':>8}{'平均贏':>9}{'平均輸':>9}"
              f"{'賺賠比':>8}{'期望值':>9}{'平均持有':>9}{'停損出場':>9}{'停利出場':>9}")
        for stop, target in GRID:
            res = []
            for code, bmap, t in pool:
                r = simulate(bmap, cal, cidx, t, stop, target)
                if r:
                    res.append(r)
            s = stats(res)
            if not s:
                continue
            print(f"  {(f'{stop}%' if stop else '—'):>6}{(f'{target}%' if target else '—'):>6}"
                  f"{s['n']:>8,}{s['win']:>7.0f}%{s['aw']:>8.1f}%{-s['al']:>8.1f}%"
                  f"{s['pr']:>8.2f}{s['ev']:>8.2f}%{s['hold']:>9.1f}"
                  f"{s['stop_pct']:>8.0f}%{s['tp_pct']:>8.0f}%")
    print("\n" + "=" * 122)
    print("  ⛔ 看的是「訊號組的期望值 − 基準的期望值」。")
    print("     兩邊一起變好 ＝ 是風控的功勞，不是訊號的功勞。")
    print("=" * 122)


if __name__ == "__main__":
    main()
