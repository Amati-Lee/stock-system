"""
stock_analyze.py — AI 個股分析
讀取 alerts.json，呼叫 Claude Haiku 產出結構化分析，寫入 pwa/analysis.json
"""
import json
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ALERTS_PATH = os.path.join(SCRIPT_DIR, "pwa", "alerts.json")
ANALYSIS_OUT = os.path.join(SCRIPT_DIR, "pwa", "analysis.json")
MODEL = "claude-haiku-4-5-20251001"
MAX_RETRIES = 2
TELEGRAM_URL = "https://pomodoro-bot.juria-orch.workers.dev"
TELEGRAM_CHAT_ID = "8786691885"


def load_alerts():
    if not os.path.exists(ALERTS_PATH):
        return None
    with open(ALERTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_csv_row(code):
    """從最新 CSV 取得該股票的完整技術指標"""
    import csv
    import glob
    csvs = sorted(glob.glob(os.path.join(SCRIPT_DIR, "stock_data_*.csv")))
    if not csvs:
        return {}
    with open(csvs[-1], "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("\u80a1\u7968\u4ee3\u865f", "").strip() == code:
                return dict(row)
    return {}


def load_ohlc_summary(code):
    """讀 OHLC 最近 5 日摘要"""
    path = os.path.join(SCRIPT_DIR, "pwa", "ohlc", f"{code}.json")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    recent = data[-5:] if len(data) >= 5 else data
    lines = []
    for d in recent:
        lines.append(f"  {d['t']}: O={d['o']} H={d['h']} L={d['l']} C={d['c']} V={d['v']}")
    return "\n".join(lines)


def build_prompt(alert, csv_row, ohlc_summary):
    """組裝單支股票的分析 prompt"""
    code = alert["code"]
    name = alert["name"]
    market = alert.get("market", "")
    reasons = "、".join(alert["reasons"])

    # 技術指標
    fields = []
    for key in ["收盤價", "K值", "D值", "RSI", "DIF", "MACD", "柱狀圖",
                 "BB上軌", "BB中軌", "BB下軌", "成交量張", "5日均量張", "量比",
                 "市值億", "本益比", "每股配息", "殖利率"]:
        val = csv_row.get(key, "")
        if val:
            fields.append(f"{key}: {val}")
    tech_str = "\n".join(fields) if fields else "無資料"

    return f"""你是台股分析師。請針對以下起飛警示股票，用繁體中文產出結構化分析。

股票: {code} {name} ({market})
警示得分: {alert['score']} 分
警示原因: {reasons}
當日收盤: {alert['close']}  漲跌: {alert['chg_pct']:+.2f}%
日均量: {alert['avg_volume']} 張  當日量: {alert['volume']} 張

技術指標:
{tech_str}

近5日K線:
{ohlc_summary}

請輸出以下 9 項分析（每項 1-3 句話，精簡直白）:
1. 公司定位：這家公司做什麼、在產業鏈的位置
2. 基本面優勢：從本益比、殖利率、市值等判斷
3. 風險因素：包括流動性、產業、財務等風險
4. 技術面判斷：從 KD/RSI/MACD/BB/量能判斷目前位階
5. 策略建議：分「穩健型」和「積極型」各一句
6. 看多論點：站在最有利的角度，列出 2-3 個值得買入的理由
7. 看空論點：站在最不利的角度，列出 2-3 個不該碰的理由
8. 綜合判斷：權衡多空後的結論（偏多/中性/偏空）+ 一句話理由
9. 結論：一句話直白講，值不值得追

請用純文字回覆，格式如下（不要加 markdown）:
公司定位: ...
基本面優勢: ...
風險因素: ...
技術面判斷: ...
穩健型策略: ...
積極型策略: ...
看多論點: ...
看空論點: ...
綜合判斷: ...
結論: ..."""


def parse_response(text):
    """解析 Claude 回覆為 dict"""
    result = {}
    key_map = {
        "公司定位": "position",
        "基本面優勢": "fundamental",
        "風險因素": "risk",
        "技術面判斷": "technical",
        "穩健型策略": "conservative",
        "積極型策略": "aggressive",
        "看多論點": "bull_case",
        "看空論點": "bear_case",
        "綜合判斷": "verdict",
        "結論": "conclusion",
    }
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        for zh_key, en_key in key_map.items():
            if line.startswith(zh_key):
                # 取冒號後面的內容
                content = line.split(":", 1)[-1].strip() if ":" in line else ""
                if not content:
                    content = line.split("：", 1)[-1].strip() if "：" in line else line
                result[en_key] = content
                break
    return result


def analyze_stock(client, alert, csv_row, ohlc_summary):
    """呼叫 Claude API 分析單支股票"""
    prompt = build_prompt(alert, csv_row, ohlc_summary)

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            return parse_response(text)
        except Exception as e:
            err_msg = str(e)
            # 帳單/權限錯誤，通知後中止（但保留已分析的結果）
            if "credit balance" in err_msg or "billing" in err_msg.lower():
                print(f"\n    API 餘額不足，中止分析")
                send_telegram("Anthropic API 餘額不足，AI 個股分析已停止。請至 console.anthropic.com 加值。")
                return "BILLING_ERROR"
            if attempt < MAX_RETRIES:
                print(f"    重試 ({attempt + 1}/{MAX_RETRIES})...")
                time.sleep(2)
            else:
                print(f"    分析失敗: {e}")
                return None


def main():
    # 從 .env 載入環境變數（本機用；GitHub Actions 用 secrets）
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass  # python-dotenv 未安裝時跳過（GitHub Actions 不需要）

    # 檢查 API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ANTHROPIC_API_KEY 未設定，跳過 AI 分析")
        return

    # 延遲 import（GitHub Actions 才裝 anthropic）
    try:
        from anthropic import Anthropic
    except ImportError:
        print("anthropic 套件未安裝，跳過 AI 分析")
        return

    alerts_data = load_alerts()
    if not alerts_data or not alerts_data.get("alerts"):
        print("無警示資料，跳過 AI 分析")
        return

    alerts = alerts_data["alerts"]
    today_date = alerts_data.get("date", "")

    # 載入舊分析（失敗時保留舊資料）
    old_results = {}
    old_date = ""
    if os.path.exists(ANALYSIS_OUT):
        try:
            with open(ANALYSIS_OUT, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            old_results = old_data.get("analysis", {})
            old_date = old_data.get("date", "")
        except Exception:
            pass

    # 防重複：今天已分析過且數量足夠且欄位完整，跳過
    required_fields = {"position", "fundamental", "risk", "technical",
                       "conservative", "aggressive", "bull_case", "bear_case",
                       "verdict", "conclusion"}
    complete_count = sum(1 for d in old_results.values()
                        if isinstance(d, dict) and required_fields.issubset(d.keys()))
    if old_date == today_date and complete_count >= len(alerts) * 0.8:
        print(f"AI 分析已是今日資料（{old_date}，{complete_count}/{len(alerts)} 支欄位完整），跳過")
        return

    # 找出今天尚未分析或欄位不完整的股票（避免重跑已付費的）
    already_done = set()
    if old_date == today_date:
        for code, data in old_results.items():
            if isinstance(data, dict) and required_fields.issubset(data.keys()):
                already_done.add(code)
    to_analyze = [a for a in alerts if a["code"] not in already_done]

    if not to_analyze:
        print(f"AI 分析：{len(alerts)} 支皆已完成，無需重跑")
        return

    print(f"AI 個股分析：{len(to_analyze)}/{len(alerts)} 支待分析（已完成 {len(already_done)} 支）")
    print(f"使用模型：{MODEL}")

    client = Anthropic(api_key=api_key)
    results = {}
    billing_error = False

    for i, alert in enumerate(to_analyze):
        code = alert["code"]
        name = alert["name"]
        print(f"  [{i+1}/{len(to_analyze)}] {code} {name}...", end=" ", flush=True)

        csv_row = load_csv_row(code)
        ohlc_summary = load_ohlc_summary(code)
        analysis = analyze_stock(client, alert, csv_row, ohlc_summary)

        if analysis == "BILLING_ERROR":
            billing_error = True
            break
        elif analysis:
            results[code] = analysis
            print("OK")
        else:
            print("SKIP")

        # 避免 rate limit
        if i < len(to_analyze) - 1:
            time.sleep(0.5)

    # 合併：保留今日已分析的 + 新分析的
    merged = dict(old_results) if old_date == today_date else {}
    merged.update(results)

    # 寫入
    output = {
        "date": alerts_data["date"],
        "model": MODEL,
        "count": len(merged),
        "analysis": merged,
    }
    os.makedirs(os.path.dirname(ANALYSIS_OUT), exist_ok=True)
    with open(ANALYSIS_OUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    if billing_error:
        print(f"\n餘額不足，已分析 {len(results)} 支，保留舊資料共 {len(merged)} 支")
    else:
        print(f"\n分析完成：{len(results)}/{len(alerts)} 支（合併後 {len(merged)} 支）")
    print(f"輸出：{ANALYSIS_OUT}")


def send_telegram(text):
    """發送 Telegram 通知"""
    import urllib.request
    try:
        data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode()
        req = urllib.request.Request(
            TELEGRAM_URL, data=data,
            headers={"Content-Type": "application/json", "User-Agent": "stock-system/1.0"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  Telegram 通知失敗: {e}")


if __name__ == "__main__":
    main()
