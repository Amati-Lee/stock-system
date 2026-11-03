#!/usr/bin/env python3
"""
組出要部署到 Cloudflare Pages 的目錄 `_deploy/`。

## 為什麼需要這一支（2026-11-03）

Cloudflare Pages 免費方案一次部署上限 **20,000 個檔案**。
`pwa/ohlc/` 是「每支股票一個 JSON」，歷年累積到 **20,009 個**。
2026-10-28 那次部署是 `Uploaded 2434 files (17483 already uploaded)` ＝ **19,917**，
離上限只剩 83；10-29 跨過去之後**每天部署都失敗，但資料照常 commit**
⇒ 網站靜悄悄停在 10/28，使用者是看到三天前的股價才發現。

## ⛔ 為什麼不能直接刪 pwa/ohlc 裡的檔

- `download_ohlc.py` 的 `save_snapshot()` 是**從 `pwa/ohlc/` 壓出 `ohlc_snapshot.tar.gz`**
- workflow 的 `actions/cache` 也快取 `pwa/ohlc`

⇒ 刪了會讓歷史從快照與快取一起消失。**這裡只「複製要部署的」，來源完全不動。**

## 篩選規則：只部署「現在的資料裡真的有的代號」

每日 CSV 只有 **2,162 筆（全是 4 碼）**，而 `pwa/ohlc/` 有兩萬個——多出來的一萬八千個
是歷年累積、現在資料裡根本不存在的代號（權證為主）。前端只會對自己清單裡的代號開圖表，
所以取「目前各資料檔出現過的代號」聯集即可（2026-11-03 實測 2,168 個，只比 CSV 多 6 個）。

⭐ 比「用代號樣式猜權證」好：自我維護，不必判斷 `006208` 是 ETF、`2887B` 是特別股。
⭐ 抓不到 OHLC 時前端會顯示「無資料」不會出錯（index.html 的 fetch 有 catch）。
"""
import csv
import glob
import json
import os
import re
import shutil
import sys

try:                      # Windows 主控台預設 cp950
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SRC = "pwa"
DST = "_deploy"

PAGES_FILE_LIMIT = 20000               # Cloudflare Pages 免費方案硬上限
SAFE_LIMIT = PAGES_FILE_LIMIT - 1000   # 留餘裕，免得又悄悄逼近

SKIP_DIR_PREFIX = "ohlc_backup"        # 備份目錄一律不部署（含 ohlc_backup_YYYYMMDD）
CODE_RE = re.compile(r'"([0-9]{4}[A-Z]?)"')

CODE_SOURCES = [
    "watchlist.json",
    "pwa/alerts.json",
    "pwa/analysis.json",
    "pwa/watchlist_status.json",
    "pwa/institutional.json",
    "pwa/pe_river.json",
]


def collect_codes():
    """回傳 (代號集合, 逐來源統計)。⭐ 統計一定要印出來——守門員要說得出它看到多少東西。"""
    codes = set()
    report = []

    csvs = sorted(glob.glob("stock_data_*.csv"))
    if csvs:
        latest = csvs[-1]
        n = 0
        with open(latest, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f):
                if not row:
                    continue
                code = row[0].strip().strip('"')
                if not code or code == "股票代號":
                    continue
                codes.add(code)
                n += 1
        report.append((latest, n))
    else:
        report.append(("(找不到 stock_data_*.csv)", 0))

    for path in CODE_SOURCES:
        if not os.path.exists(path):
            report.append((path + "  (不存在)", 0))
            continue
        with open(path, "r", encoding="utf-8") as f:
            found = set(CODE_RE.findall(f.read()))
        codes |= found
        report.append((path, len(found)))

    return codes, report


def main() -> int:
    if not os.path.isdir(SRC):
        print(f"[X] 找不到 {SRC}/", file=sys.stderr)
        return 1

    codes, report = collect_codes()
    print("[*] 代號來源：")
    for name, n in report:
        print(f"      {name:<34} {n:>6}")
    print(f"      {'聯集':<34} {len(codes):>6}")

    if len(codes) < 500:
        print(
            f"\n[X] 只蒐集到 {len(codes)} 個代號，太少，不像是對的。\n"
            f"    照這樣部署會讓絕大多數股票的 K 線圖變成「無資料」。",
            file=sys.stderr,
        )
        return 1

    if os.path.isdir(DST):
        shutil.rmtree(DST)
    os.makedirs(DST)

    copied = 0            # 實際放進 _deploy 的檔案數
    ohlc_kept = 0         # 其中屬於 ohlc/ 的
    ohlc_skipped = 0      # 來源有、但代號不在聯集裡
    backup_skipped = 0    # ohlc_backup* 目錄裡的
    missing = 0           # 聯集裡有、但來源沒有 OHLC 檔

    for root, dirs, files in os.walk(SRC):
        pruned = [d for d in dirs if d.startswith(SKIP_DIR_PREFIX)]
        for d in pruned:
            for _, _, fs_ in os.walk(os.path.join(root, d)):
                backup_skipped += len(fs_)
            dirs.remove(d)

        rel = os.path.relpath(root, SRC)
        out_dir = DST if rel == "." else os.path.join(DST, rel)
        os.makedirs(out_dir, exist_ok=True)

        in_ohlc = os.path.basename(root) == "ohlc"
        for name in files:
            if in_ohlc and name.endswith(".json"):
                if os.path.splitext(name)[0] not in codes:
                    ohlc_skipped += 1
                    continue
                ohlc_kept += 1
            shutil.copy2(os.path.join(root, name), os.path.join(out_dir, name))
            copied += 1

    ohlc_dir = os.path.join(SRC, "ohlc")
    if os.path.isdir(ohlc_dir):
        have = {os.path.splitext(f)[0] for f in os.listdir(ohlc_dir) if f.endswith(".json")}
        missing = len(codes - have)

    print(f"\n[*] 組裝 {DST}/")
    print(f"      OHLC 保留            {ohlc_kept:>6}")
    print(f"      OHLC 排除（非現役）  {ohlc_skipped:>6}")
    print(f"      備份目錄排除          {backup_skipped:>6}")
    if missing:
        print(f"      [!] 聯集裡有 {missing} 個代號沒有 OHLC 檔（前端會顯示「無資料」）")
    print(f"      → 實際部署           {copied:>6}   （Pages 上限 {PAGES_FILE_LIMIT}）")

    # ⛔ 這個守門員必須會讓流程失敗。上一次就是「靜靜地超過上限」才拖了三天沒人發現。
    if copied >= SAFE_LIMIT:
        print(
            f"\n[X] 部署檔案數 {copied} 已達警戒線 {SAFE_LIMIT}（硬上限 {PAGES_FILE_LIMIT}）。\n"
            f"    再加下去部署會直接失敗，而資料仍會照常 commit ⇒ 網站會靜悄悄停在舊日期。\n"
            f"    處理方向：把 OHLC 併成分片檔（依代號前 2 碼約 110 檔），或升級方案。",
            file=sys.stderr,
        )
        return 1

    if copied == 0:
        print("\n[X] 一個檔都沒複製到，不可能是對的", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
