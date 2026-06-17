"""
起飛警示回測分析 — 只讀不寫，不影響任何現有資料
讀取 alerts_history/*.json + pwa/ohlc/*.json
計算警示後 1/3/5/10/20 天的報酬率與勝率
"""
import json
import os
import glob
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ALERTS_DIR = os.path.join(SCRIPT_DIR, "alerts_history")
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")

HOLD_DAYS = [1, 3, 5, 10, 20]

ohlc_cache = {}


def load_ohlc(code):
    if code in ohlc_cache:
        return ohlc_cache[code]
    path = os.path.join(OHLC_DIR, f"{code}.json")
    if not os.path.exists(path):
        ohlc_cache[code] = {}
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # t -> {c, h, l} mapping
    by_date = {r["t"]: r for r in data}
    ohlc_cache[code] = by_date
    return by_date


def find_close_after_n_days(ohlc_by_date, alert_date, n):
    """找到 alert_date 之後第 n 個交易日的收盤價"""
    dates = sorted(ohlc_by_date.keys())
    try:
        idx = dates.index(alert_date)
    except ValueError:
        # alert_date 不在 OHLC 裡，找最近的下一個交易日
        later = [d for d in dates if d >= alert_date]
        if not later:
            return None
        idx = dates.index(later[0])

    target_idx = idx + n
    if target_idx >= len(dates):
        return None
    return ohlc_by_date[dates[target_idx]]["c"]


def main():
    alert_files = sorted(glob.glob(os.path.join(ALERTS_DIR, "alerts_*.json")))
    print(f"找到 {len(alert_files)} 天警示歷史")

    # score -> hold_days -> [return_pct, ...]
    results = defaultdict(lambda: defaultdict(list))
    # 追蹤最大漲跌幅
    best_worst = defaultdict(lambda: {"best": None, "worst": None})
    total_alerts = 0
    skipped = 0

    for af in alert_files:
        with open(af, "r", encoding="utf-8") as f:
            data = json.load(f)

        alert_date = data["date"].replace("-", "")
        alerts = data.get("alerts", [])

        for a in alerts:
            code = a["code"]
            score = a["score"]
            entry_price = a["close"]
            total_alerts += 1

            ohlc = load_ohlc(code)
            if not ohlc:
                skipped += 1
                continue

            for n in HOLD_DAYS:
                future_close = find_close_after_n_days(ohlc, alert_date, n)
                if future_close is None:
                    continue
                ret = (future_close - entry_price) / entry_price * 100
                results[score][n].append(ret)

                # 追蹤 best/worst (用 5 天報酬)
                if n == 5:
                    key = f"{code}"
                    bw = best_worst[score]
                    if bw["best"] is None or ret > bw["best"][1]:
                        bw["best"] = (f"{code} ({alert_date})", ret)
                    if bw["worst"] is None or ret < bw["worst"][1]:
                        bw["worst"] = (f"{code} ({alert_date})", ret)

    print(f"總警示: {total_alerts}, 無 OHLC 跳過: {skipped}\n")

    # 輸出結果
    scores = sorted(results.keys(), reverse=True)

    # 總覽表
    print("=" * 80)
    print(f"{'分數':>4} | {'樣本':>5} |", end="")
    for n in HOLD_DAYS:
        print(f"  {n}D勝率  {n}D報酬 |", end="")
    print()
    print("-" * 80)

    for score in scores:
        data = results[score]
        # 用最短天期的樣本數
        sample = len(data[HOLD_DAYS[0]]) if HOLD_DAYS[0] in data else 0
        print(f"  {score:>2} | {sample:>5} |", end="")
        for n in HOLD_DAYS:
            rets = data.get(n, [])
            if not rets:
                print(f"    N/A     N/A |", end="")
                continue
            win_rate = sum(1 for r in rets if r > 0) / len(rets) * 100
            avg_ret = sum(rets) / len(rets)
            print(f"  {win_rate:5.1f}% {avg_ret:+6.2f}% |", end="")
        print()

    print("=" * 80)

    # 全部合計
    print(f"\n{'ALL':>4} |", end="")
    all_sample = sum(len(results[s].get(HOLD_DAYS[0], [])) for s in scores)
    print(f" {all_sample:>5} |", end="")
    for n in HOLD_DAYS:
        all_rets = []
        for s in scores:
            all_rets.extend(results[s].get(n, []))
        if not all_rets:
            print(f"    N/A     N/A |", end="")
            continue
        win_rate = sum(1 for r in all_rets if r > 0) / len(all_rets) * 100
        avg_ret = sum(all_rets) / len(all_rets)
        print(f"  {win_rate:5.1f}% {avg_ret:+6.2f}% |", end="")
    print()

    # Best/Worst per score (5D)
    print(f"\n--- 5 日報酬 Best / Worst ---")
    for score in scores:
        bw = best_worst[score]
        b = bw["best"]
        w = bw["worst"]
        b_str = f"{b[0]} {b[1]:+.1f}%" if b else "N/A"
        w_str = f"{w[0]} {w[1]:+.1f}%" if w else "N/A"
        print(f"  {score}分: Best={b_str}  Worst={w_str}")

    # 門檻建議
    print(f"\n--- 門檻建議 ---")
    for score in scores:
        rets_5d = results[score].get(5, [])
        if not rets_5d:
            continue
        win = sum(1 for r in rets_5d if r > 0) / len(rets_5d) * 100
        avg = sum(rets_5d) / len(rets_5d)
        n = len(rets_5d)
        if win >= 60 and avg > 0:
            verdict = "KEEP"
        elif win >= 50:
            verdict = "BORDERLINE"
        else:
            verdict = "CONSIDER REMOVING"
        print(f"  {score}分 (n={n}): 勝率{win:.0f}% 均報酬{avg:+.2f}% -> {verdict}")


if __name__ == "__main__":
    main()
