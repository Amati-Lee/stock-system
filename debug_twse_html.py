"""
debug_twse_html.py
偵察：抓回 TWSE 網頁，印出裡面包含股票代號的部分，
看看HTML結構長什麼樣子才能寫正確的解析。
"""
import urllib.request
import re

url = "https://www.twse.com.tw/en/listed/listedCompanies"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.twse.com.tw/"
}

req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=15) as resp:
    body = resp.read().decode("utf-8")

print(f"網頁總長度：{len(body)} 字元\n")

# --- 找看看有沒有 <option> ---
options = re.findall(r'<option[^>]*>.*?</option>', body, re.DOTALL)
print(f"找到 <option> 標籤：{len(options)} 個")
if options:
    print("前 10 個：")
    for o in options[:10]:
        print(f"  {o}")

# --- 找看看有沒有 2330 出現在哪裡 ---
print(f"\n--- '2330' 出現的位置 ---")
for m in re.finditer(r'.{0,80}2330.{0,80}', body):
    print(f"  ...{m.group()}...")
    # 只印前 5 次
    if m.start() > 5000:
        break

# --- 看看有沒有 table 或其他包含股票列表的結構 ---
print(f"\n--- 網頁裡的 <table> 數量 ---")
tables = re.findall(r'<table', body)
print(f"  找到 {len(tables)} 個 <table>")

# --- 看看有沒有 JSON 數據藏在 script 裡 ---
print(f"\n--- <script> 裡有沒有股票數據 ---")
scripts = re.findall(r'<script[^>]*>(.*?)</script>', body, re.DOTALL)
for i, s in enumerate(scripts):
    if '2330' in s or 'stock' in s.lower():
        print(f"  script[{i}] 包含相關內容，前 300 字：")
        print(f"  {s[:300]}")
        print()
