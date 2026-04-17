"""
股票起飛警示系統 — 多條件複合篩選
讀取 OHLC 歷史 + 每日指標，計算警示分數
輸出 pwa/alerts.json
"""
import json
import os
import glob
import csv
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OHLC_DIR = os.path.join(SCRIPT_DIR, "pwa", "ohlc")
ALERTS_OUT = os.path.join(SCRIPT_DIR, "pwa", "alerts.json")
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "watchlist.json")
MARKET_TYPE_PATH = os.path.join(SCRIPT_DIR, "stock_market_type.json")
THRESHOLD = 8  # 警示門檻


def load_ohlc(code):
    """讀取單支股票的 OHLC 歷史"""
    path = os.path.join(OHLC_DIR, f"{code}.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_latest_csv():
    """讀取最新的每日 CSV，回傳 {code: row_dict}"""
    csvs = sorted(glob.glob(os.path.join(SCRIPT_DIR, "stock_data_*.csv")))
    if not csvs:
        return {}
    latest = csvs[-1]
    result = {}
    with open(latest, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row.get("股票代號", "").strip()
            if code:
                result[code] = row
    return result


def safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def compute_ma(closes, period):
    """計算移動平均線，回傳最後一個值"""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def has_limit_up(ohlc, days=10):
    """過去 N 日內是否有漲停（漲幅 >= 9.5%）"""
    recent = ohlc[-days:] if len(ohlc) >= days else ohlc
    for i, d in enumerate(recent):
        if i == 0 and len(ohlc) <= days:
            continue  # 第一筆沒有前一日
        # 找前一日收盤
        idx_in_full = len(ohlc) - len(recent) + i
        if idx_in_full == 0:
            continue
        prev_close = ohlc[idx_in_full - 1]["c"]
        if prev_close <= 0:
            continue
        chg_pct = (d["c"] - prev_close) / prev_close * 100
        if chg_pct >= 9.5:
            return True
    return False


def compute_avg_volume(ohlc, period=20):
    """計算 N 日平均成交量"""
    if len(ohlc) < period + 1:
        # 不夠長就用全部（扣掉今天）
        vols = [d["v"] for d in ohlc[:-1]] if len(ohlc) > 1 else []
    else:
        vols = [d["v"] for d in ohlc[-(period + 1):-1]]
    return sum(vols) / len(vols) if vols else 0


def is_crossing_above_ma(ohlc, period):
    """今日向上穿越 MA（昨日收盤 < MA，今日收盤 > MA）"""
    if len(ohlc) < period + 1:
        return False
    closes = [d["c"] for d in ohlc]
    ma_today = sum(closes[-period:]) / period
    ma_yesterday = sum(closes[-(period + 1):-1]) / period
    today_close = closes[-1]
    yesterday_close = closes[-2]
    return yesterday_close < ma_yesterday and today_close > ma_today


def is_new_high(ohlc, period):
    """今日收盤創 N 日新高"""
    if len(ohlc) < period:
        return False
    highs = [d["h"] for d in ohlc[-period:]]
    return ohlc[-1]["c"] >= max(highs) * 0.98  # 接近最高也算


def score_stock(code, ohlc, daily_row):
    """計算單支股票的警示分數"""
    if len(ohlc) < 20:
        return None

    closes = [d["c"] for d in ohlc]
    today = ohlc[-1]
    today_close = today["c"]
    today_vol = today["v"]

    # === 前提：收盤 > MA240（年線），不符合直接排除 ===
    ma240 = compute_ma(closes, 240)
    if ma240 is not None and today_close <= ma240:
        return None
    # 如果不夠 240 天資料，用現有最長 MA 當替代（寬鬆處理）
    if ma240 is None:
        longest = len(closes)
        if longest >= 120:
            ma_long = compute_ma(closes, longest)
            if ma_long and today_close <= ma_long:
                return None

    score = 0
    reasons = []

    # 1. 10日內有漲停 (+3)
    if has_limit_up(ohlc, 10):
        score += 3
        reasons.append("10日內漲停")

    # 2. 爆量：今日量 > 20日均量 × 3 (+3)
    avg_vol = compute_avg_volume(ohlc, 20)
    if avg_vol > 0:
        vol_ratio = today_vol / avg_vol
        if vol_ratio >= 3:
            score += 3
            reasons.append(f"爆量{vol_ratio:.1f}倍")
        elif vol_ratio >= 1.5:
            score += 1
            reasons.append(f"增量{vol_ratio:.1f}倍")

    # 3. 突破箱型：創20日新高 (+2)
    if is_new_high(ohlc, 20):
        score += 2
        reasons.append("突破20日高")

    # 4. 創60日新高 (+2)
    if is_new_high(ohlc, 60):
        score += 2
        reasons.append("創60日新高")

    # 5. 向上穿越 MA20 (+2)
    if is_crossing_above_ma(ohlc, 20):
        score += 2
        reasons.append("穿越MA20")

    # 6. 向上穿越 MA10 (+1)
    if is_crossing_above_ma(ohlc, 10):
        score += 1
        reasons.append("穿越MA10")

    # 7. 突破布林上軌 (+1)
    if daily_row:
        bb_upper = safe_float(daily_row.get("BB上軌"))
        if bb_upper > 0 and today_close > bb_upper:
            score += 1
            reasons.append("突破布林上軌")

    # 8. KD 黃金交叉 (+1)
    if daily_row:
        kd_status = daily_row.get("KD狀態", "")
        signals = daily_row.get("訊號", "")
        if "KD黃金交叉" in signals or "KD 黃金交叉" in signals:
            score += 1
            reasons.append("KD黃金交叉")

    # 9. MACD 黃金交叉 (+1)
    if daily_row:
        signals = daily_row.get("訊號", "")
        if "MACD" in signals and ("黃金" in signals or "翻多" in signals):
            score += 1
            reasons.append("MACD黃金交叉")

    if score < THRESHOLD:
        return None

    # 計算漲跌幅
    prev_close = ohlc[-2]["c"] if len(ohlc) >= 2 else today["o"]
    chg_pct = (today_close - prev_close) / prev_close * 100 if prev_close > 0 else 0

    return {
        "code": code,
        "name": daily_row.get("股票名稱", "") if daily_row else "",
        "close": today_close,
        "chg_pct": round(chg_pct, 2),
        "volume": today_vol,
        "avg_volume": round(avg_vol),
        "score": score,
        "reasons": reasons,
    }


def main():
    print("=" * 50)
    print("股票起飛警示系統")
    print("=" * 50)

    # 掃描全市場：讀取 pwa/ohlc/ 目錄下所有 OHLC 檔案
    if not os.path.isdir(OHLC_DIR):
        print(f"找不到 OHLC 目錄：{OHLC_DIR}")
        return
    ohlc_files = [f for f in os.listdir(OHLC_DIR) if f.endswith(".json")]
    codes = [f.replace(".json", "") for f in ohlc_files]
    print(f"全市場掃描：{len(codes)} 支股票")

    # 載入每日 CSV
    daily_data = load_latest_csv()
    print(f"每日資料：{len(daily_data)} 支股票")

    # 載入市場分類
    mkt_map = {}
    if os.path.exists(MARKET_TYPE_PATH):
        with open(MARKET_TYPE_PATH, "r", encoding="utf-8") as f:
            mkt_map = json.load(f)
        print(f"市場分類：{len(mkt_map)} 支股票")

    # 掃描全部
    alerts = []
    scanned = 0
    for code in codes:
        ohlc = load_ohlc(code)
        if not ohlc:
            continue
        scanned += 1
        daily_row = daily_data.get(code)
        result = score_stock(code, ohlc, daily_row)
        if result:
            result["market"] = mkt_map.get(code, "")
            alerts.append(result)

    # 按分數排序
    alerts.sort(key=lambda x: x["score"], reverse=True)

    # 輸出
    today_str = datetime.now().strftime("%Y-%m-%d")
    output = {
        "date": today_str,
        "threshold": THRESHOLD,
        "scanned": scanned,
        "alerts": alerts,
    }

    os.makedirs(os.path.dirname(ALERTS_OUT), exist_ok=True)
    with open(ALERTS_OUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n掃描完成：{scanned} 支")
    print(f"警示門檻：>= {THRESHOLD} 分")
    print(f"觸發警示：{len(alerts)} 支")
    if alerts:
        print()
        for a in alerts:
            reasons_str = "、".join(a["reasons"])
            print(f"  ★ {a['code']} {a['name']}  ${a['close']}  "
                  f"{a['chg_pct']:+.2f}%  得分:{a['score']}  "
                  f"[{reasons_str}]")
    print(f"\n輸出：{ALERTS_OUT}")


if __name__ == "__main__":
    main()
