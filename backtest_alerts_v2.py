"""
起飛警示回測 v2 — Hurst × 籌碼維持率 交叉分析
只讀不寫，不影響任何現有資料
"""
import json
import os
import glob
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ALERTS_DIR = os.path.join(SCRIPT_DIR, "alerts_history")
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")

HOLD_DAYS = [5, 10, 20]

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


def find_close_after_n_days(ohlc_list, alert_date, n):
    dates = [r["t"] for r in ohlc_list]
    try:
        idx = dates.index(alert_date)
    except ValueError:
        later = [i for i, d in enumerate(dates) if d >= alert_date]
        if not later:
            return None
        idx = later[0]
    target_idx = idx + n
    if target_idx >= len(ohlc_list):
        return None
    return ohlc_list[target_idx]["c"]


def calc_retention(ohlc_list, alert_date, field, lookback=20):
    """計算 alert_date 當天往前 lookback 天的籌碼維持率
    維持率 = 累積買超 / 歷史峰值累積買超
    """
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

    # 需要至少 5 天資料
    vals = [r.get(field) for r in window if field in r]
    if len(vals) < 5:
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


def classify_hurst(h):
    if h is None:
        return None
    if h >= 0.6:
        return "H_trend"       # 趨勢持續
    elif h >= 0.55:
        return "H_weak_trend"  # 弱趨勢
    elif h >= 0.45:
        return "H_random"      # 隨機漫步
    else:
        return "H_revert"      # 均值回歸


def classify_retention(r):
    if r is None:
        return None
    if r >= 0.8:
        return "R_high"  # 法人持續抱
    elif r >= 0.5:
        return "R_mid"   # 部分獲利了結
    else:
        return "R_low"   # 大幅出貨


def print_group_table(group_results, title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")
    print(f"{'分組':>12} | {'樣本':>5} |", end="")
    for n in HOLD_DAYS:
        print(f"  {n}D勝率  {n}D報酬 |", end="")
    print()
    print("-" * 70)

    groups = sorted(group_results.keys())
    for g in groups:
        data = group_results[g]
        sample = len(data.get(HOLD_DAYS[0], []))
        if sample == 0:
            continue
        print(f"  {g:>10} | {sample:>5} |", end="")
        for n in HOLD_DAYS:
            rets = data.get(n, [])
            if not rets:
                print(f"    N/A     N/A |", end="")
                continue
            win = sum(1 for r in rets if r > 0) / len(rets) * 100
            avg = sum(rets) / len(rets)
            print(f"  {win:5.1f}% {avg:+6.2f}% |", end="")
        print()
    print("=" * 70)


def main():
    alert_files = sorted(glob.glob(os.path.join(ALERTS_DIR, "alerts_*.json")))
    print(f"找到 {len(alert_files)} 天警示歷史")

    # 各分組的結果
    hurst_groups = defaultdict(lambda: defaultdict(list))
    retain_groups = defaultdict(lambda: defaultdict(list))
    cross_groups = defaultdict(lambda: defaultdict(list))

    total = 0
    has_hurst = 0
    has_retain = 0
    has_both = 0

    for af in alert_files:
        with open(af, "r", encoding="utf-8") as f:
            fdata = json.load(f)

        alert_date = fdata["date"].replace("-", "")
        alerts = fdata.get("alerts", [])

        for a in alerts:
            code = a["code"]
            entry_price = a["close"]
            total += 1

            ohlc_list = load_ohlc(code)
            if not ohlc_list:
                continue

            # Hurst
            h = a.get("hurst")
            h_class = classify_hurst(h)

            # 籌碼維持率（外資 + 投信取較高者）
            r_foreign = calc_retention(ohlc_list, alert_date, "fi")
            r_trust = calc_retention(ohlc_list, alert_date, "ti")
            r_val = None
            if r_foreign is not None and r_trust is not None:
                r_val = max(r_foreign, r_trust)
            elif r_foreign is not None:
                r_val = r_foreign
            elif r_trust is not None:
                r_val = r_trust
            r_class = classify_retention(r_val)

            if h_class:
                has_hurst += 1
            if r_class:
                has_retain += 1
            if h_class and r_class:
                has_both += 1

            # 計算報酬
            for n in HOLD_DAYS:
                future_close = find_close_after_n_days(ohlc_list, alert_date, n)
                if future_close is None:
                    continue
                ret = (future_close - entry_price) / entry_price * 100

                if h_class:
                    hurst_groups[h_class][n].append(ret)
                if r_class:
                    retain_groups[r_class][n].append(ret)
                if h_class and r_class:
                    cross_key = f"{h_class}+{r_class}"
                    cross_groups[cross_key][n].append(ret)

    print(f"總警示: {total}")
    print(f"有 Hurst: {has_hurst} ({has_hurst/total*100:.0f}%)")
    print(f"有籌碼: {has_retain} ({has_retain/total*100:.0f}%)")
    print(f"兩者都有: {has_both} ({has_both/total*100:.0f}%)")

    print_group_table(hurst_groups, "按 Hurst 指數分組")
    print_group_table(retain_groups, "按籌碼維持率分組")
    print_group_table(cross_groups, "Hurst × 籌碼維持率 交叉分析")


if __name__ == "__main__":
    main()
