"""
watchlist_check.py — 觀察清單條件檢查
讀取 watchlist_notes.json + 最新收盤價，檢查條件是否達成
輸出 pwa/watchlist_status.json，並在條件達成時發 Telegram 通知
"""
import json
import os
import csv
import glob
import urllib.request
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NOTES_PATH = os.path.join(SCRIPT_DIR, "watchlist_notes.json")
STATUS_OUT = os.path.join(SCRIPT_DIR, "pwa", "watchlist_status.json")
INST_PATH = os.path.join(SCRIPT_DIR, "pwa", "institutional.json")
TELEGRAM_URL = "https://pomodoro-bot.juria-orch.workers.dev"
TELEGRAM_CHAT_ID = "8786691885"


def load_institutional():
    """載入三大法人資料"""
    if not os.path.exists(INST_PATH):
        return {}
    with open(INST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("data", {})


WATCHLIST_API = "https://stock-watchlist.juria-orch.workers.dev/watchlist"


def load_notes():
    """合併本地 JSON + KV API，KV 優先（同 code 以 KV 為準）"""
    # 先讀本地
    local = {}
    if os.path.exists(NOTES_PATH):
        with open(NOTES_PATH, "r", encoding="utf-8") as f:
            local = json.load(f)
        print(f"  觀察清單：本地 {len(local)} 支")

    # 再讀 KV，合併（KV 覆蓋本地同 code）
    try:
        req = urllib.request.Request(WATCHLIST_API, headers={"User-Agent": "stock-system/1.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        kv = json.loads(resp.read().decode("utf-8"))
        if kv:
            print(f"  觀察清單：KV {len(kv)} 支")
            local.update(kv)
    except Exception as e:
        print(f"  KV 讀取失敗 ({e})，僅用本地")

    return local


def load_latest_prices():
    """從最新 CSV 取得收盤價"""
    csvs = sorted(glob.glob(os.path.join(SCRIPT_DIR, "stock_data_*.csv")))
    if not csvs:
        return {}, ""
    latest = csvs[-1]
    trade_date = os.path.basename(latest).replace("stock_data_", "").replace(".csv", "")
    prices = {}
    with open(latest, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row.get("\u80a1\u7968\u4ee3\u865f", "").strip()
            close = row.get("\u6536\u76e4\u50f9", "")
            if code and close:
                try:
                    prices[code] = float(close)
                except ValueError:
                    pass
    return prices, trade_date


def send_telegram(text):
    try:
        data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode()
        req = urllib.request.Request(
            TELEGRAM_URL, data=data,
            headers={"Content-Type": "application/json", "User-Agent": "stock-system/1.0"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
        print(f"  Telegram: OK")
    except Exception as e:
        print(f"  Telegram: {e}")


def main():
    notes = load_notes()
    if not notes:
        print("無觀察清單，跳過")
        return

    prices, trade_date = load_latest_prices()
    if not prices:
        print("無收盤價資料，跳過")
        return

    inst_data = load_institutional()

    today = datetime.now().strftime("%Y-%m-%d")
    print(f"觀察清單檢查：{len(notes)} 支，交易日 {trade_date}")

    results = {}
    notifications = []

    for code, note in notes.items():
        name = note.get("name", code)
        price = prices.get(code)
        if price is None:
            print(f"  {code} {name}: 無報價，跳過")
            continue

        # 法人資料
        inst = inst_data.get(code, {})

        entry = {
            "name": name,
            "price": price,
            "targets": {},
            "upcoming_dates": [],
            "watch": note.get("watch", []),
            "stop_loss": note.get("stop_loss"),
            "institutional": inst if inst else None,
            "triggered": [],
        }

        # 檢查目標價
        for label, target in note.get("targets", {}).items():
            target_price = target.get("price_below")
            if target_price is None:
                continue
            diff_pct = round((price - target_price) / target_price * 100, 1)
            hit = price <= target_price
            entry["targets"][label] = {
                "target_price": target_price,
                "diff_pct": diff_pct,
                "hit": hit,
                "note": target.get("note", ""),
            }
            if hit:
                entry["triggered"].append(label)
                notifications.append(
                    f"{code} {name} ${price} 到達【{label}】目標 ${target_price}（{target.get('note', '')}）"
                )

        # 檢查關鍵日期（未來 7 天內）
        for kd in note.get("key_dates", []):
            date_str = kd.get("date", "")
            if not date_str:
                continue
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d")
                days_left = (d - datetime.now()).days
                if -1 <= days_left <= 7:
                    entry["upcoming_dates"].append({
                        "date": date_str,
                        "event": kd.get("event", ""),
                        "days_left": days_left,
                    })
                if days_left == 0:
                    notifications.append(
                        f"{code} {name} 今天：{kd.get('event', '')}"
                    )
            except ValueError:
                pass

        # 停損檢查
        sl = note.get("stop_loss")
        if sl and price <= sl:
            entry["triggered"].append("stop_loss")
            notifications.append(
                f"{code} {name} ${price} 跌破停損 ${sl}"
            )

        # 法人動向自動檢查
        if inst:
            trust_val = inst.get("trust", 0)
            if trust_val > 0:
                entry["triggered"].append("trust_buy")
                notifications.append(
                    f"{code} {name} 投信買超 {trust_val} 張"
                )
            foreign_val = inst.get("foreign", 0)
            if foreign_val > 500:
                entry["triggered"].append("foreign_big_buy")
                notifications.append(
                    f"{code} {name} 外資大買 {foreign_val} 張"
                )

        results[code] = entry
        status = "HIT" if entry["triggered"] else "OK"
        print(f"  {code} {name}: ${price} [{status}]")

    # 寫入 PWA 資料
    output = {
        "date": today,
        "trade_date": trade_date,
        "count": len(results),
        "stocks": results,
    }
    os.makedirs(os.path.dirname(STATUS_OUT), exist_ok=True)
    with open(STATUS_OUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n輸出：{STATUS_OUT}")

    # 發送通知
    if notifications:
        msg = "📋 觀察清單提醒\n\n" + "\n".join(notifications)
        print(f"\n發送 {len(notifications)} 則通知...")
        send_telegram(msg)
    else:
        print("\n無觸發條件")


if __name__ == "__main__":
    main()
