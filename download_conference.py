# -*- coding: utf-8 -*-
"""
download_conference.py — 法說會日期抓取
從公開資訊觀測站 (MOPS) 抓取近期法說會資訊，輸出 pwa/conferences.json
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "pwa", "conferences.json")
MOPS_URL = "https://mopsov.twse.com.tw/mops/web/ajax_t100sb02_1"


def fetch_month(typek, roc_year, month):
    """抓取一個月份的法說會資料"""
    form = f"encodeURIComponent=1&step=1&firstin=1&off=1&TYPEK={typek}&year={roc_year}&month={month:02d}".encode()
    req = urllib.request.Request(
        MOPS_URL, data=form,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://mopsov.twse.com.tw/mops/web/t100sb02_1",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.read().decode("utf-8")
    except Exception as e:
        print(f"    {typek} {roc_year}/{month:02d} 失敗: {e}")
        return ""


def parse_html(html):
    """解析 MOPS HTML，回傳 {code: {date, name, days}} """
    results = {}
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE)
    if not tables:
        return results

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    for tbl in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.DOTALL)
        for row in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            if len(cells) < 3:
                continue
            clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            code = clean[0]
            name = clean[1]
            date_str = clean[2]

            # 驗證：代號 4 位數、日期 ROC 格式
            if not re.match(r"^\d{4}$", code):
                continue
            m = re.match(r"^(\d{3})/(\d{2})/(\d{2})$", date_str)
            if not m:
                continue

            try:
                y = int(m.group(1)) + 1911
                mo = int(m.group(2))
                d = int(m.group(3))
                dt = datetime(y, mo, d)
            except ValueError:
                continue

            days = (dt - today).days

            # 只保留前 7 天到後 30 天的
            if days < -7 or days > 30:
                continue

            results[code] = {
                "date": dt.strftime("%Y-%m-%d"),
                "name": name,
                "days": days,
            }

    return results


def main():
    print("=" * 40)
    print("  法說會日期抓取")
    print("=" * 40)

    today = datetime.now()
    roc_y = today.year - 1911

    results = {}

    # 查詢當月 + 下月（上市 sii + 上櫃 otc）
    months = [(roc_y, today.month)]
    next_m = today + timedelta(days=30)
    if next_m.month != today.month:
        months.append((next_m.year - 1911, next_m.month))

    for typek, label in [("sii", "上市"), ("otc", "上櫃")]:
        for ry, mo in months:
            print(f"  抓取 {label} {ry}/{mo:02d}...")
            html = fetch_month(typek, ry, mo)
            if html:
                parsed = parse_html(html)
                results.update(parsed)
                print(f"    找到 {len(parsed)} 筆")
            time.sleep(2)

    # 輸出
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False)

    upcoming = sum(1 for v in results.values() if v["days"] >= 0)
    recent = sum(1 for v in results.values() if v["days"] < 0)
    print(f"\n輸出: {OUTPUT_PATH}")
    print(f"  即將到來: {upcoming} 場, 近期已開: {recent} 場, 共 {len(results)} 筆")


if __name__ == "__main__":
    main()
