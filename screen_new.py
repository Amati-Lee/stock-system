# -*- coding: utf-8 -*-
"""
screen_new.py — 新版起飛警示條件的「現況篩選」

⛔⛔ 這支**只回答「今天有幾支符合」**，不回答「這組條件會不會賺錢」。
   後者需要預先登記 + 樣本外驗證，⛔ 不要拿這裡的名單當績效證據。

六個條件（定義寫死在這裡，要改就改這裡並同時改註解）：
  1. KD 黃金交叉    K 上穿 D（今天 K>D 且 昨天 K<=D）；KD(9)，K=RSV的ewm(1/3)、D=K的ewm(1/3)
                    ⭐ 與 stock_system.py 的 calc_kd 同定義
  2. MACD 零軸以上  DIF > 0（另外分開報「MACD線>0」與「兩者皆>0」，因為講法不只一種）
  3. DMI 多方       +DI > −DI（Wilder 14）
  4. RSI 黃金交叉   RSI6 上穿 RSI12（另外分開報「RSI14 上穿 50」）
  5. 融資法人反向   **20 個交易日**內：法人持股累積線的回歸斜率 > 0 **且**
                    融資餘額線的回歸斜率 < 0 ＝ 兩條線走勢相反
                    ⛔⛔ 舊版用「頭尾兩點相減、5 日窗口」，**會被單日雜訊騙**：
                    6870 騰雲 5 日頭尾剛好切在一個小凹陷 → 判成反向，
                    但它 20 日融資其實暴增 43%（1,327→1,902 張）、法人只買 110 張。
                    使用者 2026-09-24 當場抓到。改成看整段斜率後正確排除。
  6. 400張大戶>50%  集保級距 12~15 占比合計 > 50%
                    ⭐ 級距區間已用資料實證（每人平均持股落在宣稱區間內，15/15 通過）

只讀不寫。
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import glob
import json
import os

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")
MARGIN_DIR = os.path.join(SCRIPT_DIR, "margin_history")
HOLDERS_DIR = os.path.join(SCRIPT_DIR, "holders_history")

MARG_WINDOW = 20        # 條件 5 的窗口（交易日）
MARG_SLOPE_MAX = -0.2   # 融資斜率門檻（%/日）；要比這個更負才算「散戶真的在退」

sys.path.insert(0, SCRIPT_DIR)
from backtest_dmi import dmi           # 已含自我測試的 Wilder DMI


# ---------------------------------------------------------------- 指標
def ema(vals, span):
    a = 2.0 / (span + 1)
    out, s = [], None
    for v in vals:
        s = v if s is None else a * v + (1 - a) * s
        out.append(s)
    return out


def ewm_alpha(vals, alpha, seed=50.0):
    out, s = [], seed
    for v in vals:
        s = alpha * v + (1 - alpha) * s
        out.append(s)
    return out


def calc_kd(bars, period=9):
    """與 stock_system.py 同定義：RSV → K(ewm 1/3) → D(ewm 1/3)"""
    if len(bars) < period + 2:
        return None, None, None, None
    rsv = []
    for i in range(period - 1, len(bars)):
        w = bars[i - period + 1:i + 1]
        hi = max(b["h"] for b in w)
        lo = min(b["l"] for b in w)
        rsv.append(50.0 if hi == lo else 100.0 * (bars[i]["c"] - lo) / (hi - lo))
    k = ewm_alpha(rsv, 1 / 3)
    d = ewm_alpha(k, 1 / 3)
    return k[-1], d[-1], k[-2], d[-2]


def calc_rsi_series(closes, period):
    """Wilder RSI，回傳整條序列（前 period 個為 None）"""
    if len(closes) < period + 1:
        return []
    gains, losses = [], []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    out = [None] * period
    out.append(100.0 if al == 0 else 100 - 100 / (1 + ag / al))
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
        out.append(100.0 if al == 0 else 100 - 100 / (1 + ag / al))
    return out


def calc_macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal + 2:
        return None
    ef, es = ema(closes, fast), ema(closes, slow)
    dif = [a - b for a, b in zip(ef, es)]
    sig = ema(dif, signal)
    return dif[-1], sig[-1], dif[-1] - sig[-1]


def selftest():
    """⛔ 指標先證明自己算得對，不然下面的名單沒有意義"""
    f = []
    up = [float(100 + i) for i in range(80)]
    dn = [float(300 - i) for i in range(80)]
    r = calc_rsi_series(up, 14)
    if not (r[-1] is not None and r[-1] > 99.9):
        f.append(f"RSI 單調漲應 ~100，得 {r[-1]}")
    r = calc_rsi_series(dn, 14)
    if not (r[-1] is not None and r[-1] < 0.1):
        f.append(f"RSI 單調跌應 ~0，得 {r[-1]}")
    m = calc_macd(up)
    if not (m and m[0] > 0):
        f.append(f"MACD 單調漲 DIF 應 >0，得 {m}")
    m = calc_macd(dn)
    if not (m and m[0] < 0):
        f.append(f"MACD 單調跌 DIF 應 <0，得 {m}")
    bars_up = [{"h": 100 + i, "l": 99 + i, "c": 100 + i} for i in range(40)]
    k, d, pk, pd_ = calc_kd(bars_up)
    if not (k and k > 90 and d > 80):
        f.append(f"KD 單調漲應偏高，得 K={k} D={d}")
    bars_dn = [{"h": 200 - i, "l": 199 - i, "c": 199 - i} for i in range(40)]
    k, d, _, _ = calc_kd(bars_dn)
    if not (k is not None and k < 10):
        f.append(f"KD 單調跌應偏低，得 K={k}")
    return f


# ---------------------------------------------------------------- 資料
def main():
    fails = selftest()
    print("=" * 108)
    print("  新版條件現況篩選  ⛔ 只回答「今天有幾支符合」，不回答「會不會賺錢」")
    print("=" * 108)
    if fails:
        print("⛔ 指標自我測試沒過，結果不可信：")
        for x in fails:
            print("   -", x)
        return
    print("✅ 指標自我測試通過（RSI／MACD／KD 各驗單調漲與單調跌）")

    mkt = json.load(open(os.path.join(SCRIPT_DIR, "stock_market_type.json"), encoding="utf-8"))
    names = json.load(open(os.path.join(SCRIPT_DIR, "stock_names_all.json"), encoding="utf-8"))

    # 融資
    mfiles = sorted(glob.glob(os.path.join(MARGIN_DIR, "margin_*.json")))
    margin = {}
    mdates = []
    for p in mfiles[-30:]:
        d = json.load(open(p, encoding="utf-8"))
        mdates.append(d["date"])
        fi = d["fields"]
        margin[d["date"]] = {c: dict(zip(fi, r)) for c, r in d["data"].items()}
    mdates.sort()

    # 大戶
    hfiles = sorted(glob.glob(os.path.join(HOLDERS_DIR, "holders_*.json")))
    if not hfiles:
        print("⛔ 沒有 holders_history，條件 6 無法計算")
        return
    hd = json.load(open(hfiles[-1], encoding="utf-8"))
    holders = hd["data"]
    print(f"資料基準：融資 {mdates[-1]}　大戶 {hd['date']}（週資料）")

    rows = []
    for path in glob.glob(os.path.join(OHLC_DIR, "*.json")):
        code = os.path.basename(path)[:-5]
        if len(code) != 4 or not code.isdigit():
            continue
        m = mkt.get(code)
        if m not in ("上市", "上櫃"):
            continue
        try:
            bars = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if len(bars) < 60:
            continue
        closes = [b["c"] for b in bars]
        last_t = bars[-1]["t"]

        k, d, pk, pd_ = calc_kd(bars)
        if k is None:
            continue
        macd = calc_macd(closes)
        if macd is None:
            continue
        r6 = calc_rsi_series(closes, 6)
        r12 = calc_rsi_series(closes, 12)
        r14 = calc_rsi_series(closes, 14)
        if not r6 or not r12 or not r14 or r12[-1] is None or r12[-2] is None:
            continue
        pdi, mdi, adx = dmi(bars)
        if pdi is None:
            continue

        # 條件 5：20 日內「法人持股累積線」上升 且「融資餘額線」下降
        # ⛔ 不可用頭尾兩點相減 —— 見檔頭說明（6870 的教訓）
        ts5 = [b["t"] for b in bars if b["t"] in margin and code in margin[b["t"]]][-20:]
        inst_slope = marg_slope = marg_pct = None
        mb_now = mb_prev = None
        if len(ts5) >= 10:
            flows = {b["t"]: b.get("fi", 0) + b.get("ti", 0) for b in bars}
            cum, acc = [], 0
            for t in ts5:
                acc += flows.get(t, 0)
                cum.append(acc)
            mbs = [margin[t][code]["mb"] for t in ts5]
            x = np.arange(len(ts5), dtype=float)
            inst_slope = float(np.polyfit(x, np.array(cum, float), 1)[0])
            marg_slope = float(np.polyfit(x, np.array(mbs, float), 1)[0])
            base = abs(float(np.mean(mbs)))
            marg_pct = (marg_slope / base * 100) if base > 1e-9 else None
            mb_prev, mb_now = mbs[0], mbs[-1]
        # 強度門檻：融資斜率要 < −0.2%/日。使用者 2026-09-24 定的 ——
        # 名單裡出現過 −0.06%/日 這種「幾乎是平的」也被算成下降，那不叫散戶退場。
        diverge = (inst_slope is not None and inst_slope > 0
                   and marg_pct is not None and marg_pct < MARG_SLOPE_MAX)

        # 條件 6：400 張以上（級距 12~15）
        h = holders.get(code)
        big = sum(h[0][11:]) if h else None

        rows.append({
            "code": code, "name": names.get(code, ""), "market": m, "t": last_t,
            "close": closes[-1],
            "c1": (k > d and pk <= pd_),
            "c2_dif": macd[0] > 0, "c2_sig": macd[1] > 0,
            "c3": pdi > mdi,
            "c4_r612": (r6[-1] > r12[-1] and r6[-2] <= r12[-2]),
            "c4_r50": (r14[-1] > 50 and r14[-2] <= 50),
            "c5": diverge,
            "c6": (big is not None and big > 50),
            "big": big, "adx": adx, "k": k, "d": d, "dif": macd[0],
            "r6": r6[-1], "r12": r12[-1],
            "inst_slope": inst_slope, "marg_slope": marg_slope, "marg_pct": marg_pct,
            "mb_now": mb_now, "mb_prev": mb_prev,
        })

    tdates = {}
    for r in rows:
        tdates[r["t"]] = tdates.get(r["t"], 0) + 1
    print(f"母體：{len(rows)} 支（上市 {sum(1 for r in rows if r['market']=='上市')}／"
          f"上櫃 {sum(1 for r in rows if r['market']=='上櫃')}）"
          f"　最新價格日 {max(tdates, key=tdates.get)}")
    print(f"⚠️ 配不到大戶資料的 {sum(1 for r in rows if r['big'] is None)} 支、"
          f"配不到融資的 {sum(1 for r in rows if r['mb_now'] is None)} 支"
          f"（那是真的沒有，不是漏抓）")

    conds = [
        ("1. KD 黃金交叉（K上穿D）", lambda r: r["c1"]),
        ("2. MACD 零軸以上（DIF>0）", lambda r: r["c2_dif"]),
        ("3. DMI +DI > −DI", lambda r: r["c3"]),
        ("4. RSI 黃金交叉（RSI6上穿RSI12）", lambda r: r["c4_r612"]),
        (f"5. 法人升、融資斜率<{MARG_SLOPE_MAX}%/日", lambda r: r["c5"]),
        ("6. 400張大戶 > 50%", lambda r: r["c6"]),
    ]

    print("\n" + "-" * 108)
    print("【各條件單獨】")
    for label, fn in conds:
        n = sum(1 for r in rows if fn(r))
        print(f"  {label:<34} {n:>5} 支  ({n/len(rows)*100:5.1f}%)")

    print("\n  其他講法（供你挑定義）：")
    for label, key in [("MACD 訊號線 >0", "c2_sig"), ("RSI14 上穿 50", "c4_r50")]:
        n = sum(1 for r in rows if r[key])
        print(f"  {label:<34} {n:>5} 支  ({n/len(rows)*100:5.1f}%)")

    print("\n" + "-" * 108)
    print("【逐條疊加（漏斗）】⭐ 看它在哪一條崩掉")
    cur = rows
    for label, fn in conds:
        before = len(cur)
        cur = [r for r in cur if fn(r)]
        print(f"  +{label:<34} {before:>5} → {len(cur):>5} 支"
              + ("  ⛔ 歸零" if not cur else ""))
        if not cur:
            break

    if cur:
        print("\n" + "=" * 108)
        print(f"【六條全中：{len(cur)} 支】")
        print(f"  {'代號':<7}{'名稱':<12}{'市場':<6}{'收盤':>9}{'K':>7}{'D':>7}"
              f"{'DIF':>8}{'RSI6':>7}{'RSI12':>7}{'ADX':>7}{'大戶%':>8}")
        for r in sorted(cur, key=lambda x: -x["big"]):
            print(f"  {r['code']:<7}{r['name']:<12}{r['market']:<6}{r['close']:>9.2f}"
                  f"{r['k']:>7.1f}{r['d']:>7.1f}{r['dif']:>8.2f}{r['r6']:>7.1f}"
                  f"{r['r12']:>7.1f}{r['adx']:>7.1f}{r['big']:>8.2f}")

    # 放寬一條看看
    print("\n" + "-" * 108)
    print("【少一條會變幾支】（拿掉某一條，其餘五條都要中）")
    for i, (label, _) in enumerate(conds):
        rest = [c for j, c in enumerate(conds) if j != i]
        n = sum(1 for r in rows if all(fn(r) for _, fn in rest))
        print(f"  拿掉「{label:<34}」→ {n:>5} 支")
    print("=" * 108)


if __name__ == "__main__":
    main()
