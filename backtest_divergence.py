"""
起飛警示回測 — 籌碼蓄勢策略
條件：Hurst > 0.6（強趨勢）+ 維持率 = 1.0（法人滿倉）+ 當日漲幅 < 3%（尚未噴出）
假說：趨勢明確、法人沒跑，還沒大漲的是進場機會
只讀不寫，不影響任何現有資料
"""
import json
import os
import glob
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ALERTS_DIR = os.path.join(SCRIPT_DIR, "alerts_history")
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")

HOLD_DAYS = [1, 3, 5, 10, 20]

# 篩選條件
HURST_MIN = 0.6
RETENTION_MIN = 1.0
CHG_MAX = 3.0          # 當日漲幅上限 (%)
RETENTION_MIN_PTS = 2  # 維持率最低資料點數（中小型股法人資料稀疏）
EXCLUDE_CODES = {"8473"}  # 排除問題股（森崴能源，即將下市）

ohlc_cache = {}


def load_ohlc(code):
    if code in ohlc_cache:
        return ohlc_cache[code]
    path = os.path.join(OHLC_DIR, f"{code}.json")
    if not os.path.exists(path):
        ohlc_cache[code] = None
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    ohlc_cache[code] = data
    return data


def find_next_open(ohlc_list, alert_date):
    """取得警示隔天的開盤價作為實際進場價"""
    dates = [r["t"] for r in ohlc_list]
    try:
        idx = dates.index(alert_date)
    except ValueError:
        later = [i for i, d in enumerate(dates) if d >= alert_date]
        if not later:
            return None, None
        idx = later[0]
    next_idx = idx + 1
    if next_idx >= len(ohlc_list):
        return None, None
    return ohlc_list[next_idx]["o"], next_idx


def find_close_after_n_days(ohlc_list, base_idx, n):
    """從 base_idx 起算 n 個交易日後的收盤價"""
    target_idx = base_idx + n
    if target_idx >= len(ohlc_list):
        return None
    return ohlc_list[target_idx]["c"]


def calc_retention(ohlc_list, alert_date, field, lookback=20):
    """籌碼維持率 = 累積買超 / 歷史峰值累積買超"""
    dates = [r["t"] for r in ohlc_list]
    try:
        idx = dates.index(alert_date)
    except ValueError:
        later = [i for i, d in enumerate(dates) if d >= alert_date]
        if not later:
            return None
        idx = later[0]

    start = max(0, idx - lookback + 1)
    window = ohlc_list[start:idx + 1]

    vals = [r.get(field) for r in window if field in r and r.get(field) is not None and r.get(field) != ""]
    if len(vals) < RETENTION_MIN_PTS:
        return None

    cum = 0
    peak = 0
    for v in vals:
        cum += v
        if cum > peak:
            peak = cum

    if peak <= 0:
        return None
    return round(cum / peak, 2)


def get_retention(ohlc_list, alert_date):
    """外資 + 投信取較高者"""
    r_fi = calc_retention(ohlc_list, alert_date, "fi")
    r_ti = calc_retention(ohlc_list, alert_date, "ti")
    if r_fi is not None and r_ti is not None:
        return max(r_fi, r_ti)
    return r_fi if r_fi is not None else r_ti


def main():
    alert_files = sorted(glob.glob(os.path.join(ALERTS_DIR, "alerts_*.json")))
    print(f"找到 {len(alert_files)} 天警示歷史")

    total_alerts = 0
    matched = []  # 符合條件的個案

    for af in alert_files:
        with open(af, "r", encoding="utf-8") as f:
            fdata = json.load(f)

        alert_date = fdata["date"].replace("-", "")
        alerts = fdata.get("alerts", [])

        for a in alerts:
            total_alerts += 1
            code = a["code"]
            if code in EXCLUDE_CODES:
                continue
            name = a.get("name", code)
            hurst = a.get("hurst")
            chg_pct = a.get("chg_pct", 0)

            # 條件 1: Hurst > 0.6
            if hurst is None or hurst < HURST_MIN:
                continue

            # 條件 2: 當日漲幅 < CHG_MAX（排除已噴出的）
            if chg_pct >= CHG_MAX:
                continue

            # 條件 3: 維持率
            ohlc_list = load_ohlc(code)
            if not ohlc_list:
                continue

            ret_val = get_retention(ohlc_list, alert_date)
            if ret_val is None or ret_val < RETENTION_MIN:
                continue

            # T+1 開盤價作為實際進場價
            entry_price, entry_idx = find_next_open(ohlc_list, alert_date)
            if entry_price is None or entry_price <= 0:
                continue

            # 從進場日起算未來報酬
            returns = {}
            for n in HOLD_DAYS:
                future_close = find_close_after_n_days(ohlc_list, entry_idx, n)
                if future_close is not None:
                    returns[n] = round((future_close - entry_price) / entry_price * 100, 2)

            matched.append({
                "date": fdata["date"],
                "code": code,
                "name": name,
                "close": a["close"],
                "entry": entry_price,
                "chg_pct": chg_pct,
                "hurst": hurst,
                "retention": ret_val,
                "score": a.get("score", ""),
                "returns": returns,
            })

    # === 輸出結果 ===
    print(f"總警示數: {total_alerts}")
    print(f"符合條件 (H>{HURST_MIN}, 維持率>={RETENTION_MIN}, 漲幅<{CHG_MAX}%): {len(matched)}")

    if not matched:
        print("\n沒有符合條件的樣本。考慮放寬條件：")
        print(f"  - HURST_MIN: {HURST_MIN} -> 0.55")
        print(f"  - RETENTION_MIN: {RETENTION_MIN} -> 0.9 或 0.8")
        return

    # 逐筆明細
    print(f"\n{'='*90}")
    print(f"  逐筆明細")
    print(f"{'='*90}")
    print(f"{'日期':>12} {'代碼':>6} {'名稱':>6} {'警示收盤':>8} {'T+1進場':>8} {'漲跌%':>7} {'H':>6} {'維持':>5}", end="")
    for n in HOLD_DAYS:
        print(f" {n}D報酬", end="")
    print()
    print("-" * 100)

    for m in sorted(matched, key=lambda x: x["date"]):
        print(f"  {m['date']:>10} {m['code']:>6} {m['name']:>6} {m['close']:>8.2f} {m['entry']:>8.2f} {m['chg_pct']:>+6.2f}% "
              f"{m['hurst']:>5.3f} {m['retention']:>5.2f}", end="")
        for n in HOLD_DAYS:
            r = m["returns"].get(n)
            if r is not None:
                print(f" {r:>+6.2f}%", end="")
            else:
                print(f"    N/A", end="")
        print()

    # 彙總統計
    print(f"\n{'='*90}")
    print(f"  彙總統計 (樣本={len(matched)})")
    print(f"{'='*90}")
    print(f"{'持有天數':>10} | {'樣本':>5} | {'勝率':>8} | {'平均報酬':>10} | {'中位數':>8} | {'最大獲利':>10} | {'最大虧損':>10}")
    print("-" * 90)

    for n in HOLD_DAYS:
        rets = [m["returns"][n] for m in matched if n in m["returns"]]
        if not rets:
            continue
        win = sum(1 for r in rets if r > 0) / len(rets) * 100
        avg = sum(rets) / len(rets)
        med = sorted(rets)[len(rets) // 2]
        mx = max(rets)
        mn = min(rets)
        print(f"  {n:>8}D | {len(rets):>5} | {win:>6.1f}% | {avg:>+9.2f}% | {med:>+7.2f}% | {mx:>+9.2f}% | {mn:>+9.2f}%")

    print("=" * 90)

    # 拆分：當日跌 vs 微漲
    group_down = [m for m in matched if m["chg_pct"] < 0]
    group_up = [m for m in matched if m["chg_pct"] >= 0]

    for label, group in [("當日下跌", group_down), ("當日平盤/微漲", group_up)]:
        print(f"\n{'='*90}")
        print(f"  {label} (樣本={len(group)})")
        print(f"{'='*90}")
        if not group:
            print("  (無樣本)")
            continue
        print(f"{'持有天數':>10} | {'樣本':>5} | {'勝率':>8} | {'平均報酬':>10} | {'中位數':>8} | {'最大獲利':>10} | {'最大虧損':>10}")
        print("-" * 90)
        for n in HOLD_DAYS:
            rets = [m["returns"][n] for m in group if n in m["returns"]]
            if not rets:
                continue
            win = sum(1 for r in rets if r > 0) / len(rets) * 100
            avg = sum(rets) / len(rets)
            med = sorted(rets)[len(rets) // 2]
            mx = max(rets)
            mn = min(rets)
            print(f"  {n:>8}D | {len(rets):>5} | {win:>6.1f}% | {avg:>+9.2f}% | {med:>+7.2f}% | {mx:>+9.2f}% | {mn:>+9.2f}%")
        print("=" * 90)

    # 放寬條件對照組
    print(f"\n--- 對照：放寬維持率至 >= 0.8 ---")
    relaxed = []
    ohlc_cache.clear()
    for af in alert_files:
        with open(af, "r", encoding="utf-8") as f:
            fdata = json.load(f)
        alert_date = fdata["date"].replace("-", "")
        for a in fdata.get("alerts", []):
            hurst = a.get("hurst")
            chg_pct = a.get("chg_pct", 0)
            if hurst is None or hurst < HURST_MIN or chg_pct >= CHG_MAX:
                continue
            ohlc_list = load_ohlc(a["code"])
            if not ohlc_list:
                continue
            ret_val = get_retention(ohlc_list, alert_date)
            if ret_val is None or ret_val < 0.8:
                continue
            entry_price, entry_idx = find_next_open(ohlc_list, alert_date)
            if entry_price is None or entry_price <= 0:
                continue
            returns = {}
            for n in HOLD_DAYS:
                fc = find_close_after_n_days(ohlc_list, entry_idx, n)
                if fc is not None:
                    returns[n] = round((fc - entry_price) / entry_price * 100, 2)
            relaxed.append(returns)

    if relaxed:
        print(f"樣本數: {len(relaxed)}")
        for n in HOLD_DAYS:
            rets = [r[n] for r in relaxed if n in r]
            if not rets:
                continue
            win = sum(1 for r in rets if r > 0) / len(rets) * 100
            avg = sum(rets) / len(rets)
            print(f"  {n:>3}D: 勝率 {win:.1f}%, 平均 {avg:+.2f}% (n={len(rets)})")


if __name__ == "__main__":
    main()
