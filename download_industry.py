"""
download_industry.py — 從 TWSE/TPEx 抓取股票產業分類
輸出 stock_industry.json: { "2330": "半導體", "4571": "電機機械", ... }
"""
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "stock_industry.json")

# TWSE 產業代碼對照表
INDUSTRY_MAP = {
    "01": "水泥", "02": "食品", "03": "塑膠", "04": "紡織纖維",
    "05": "電機機械", "06": "電器電纜", "08": "玻璃陶瓷", "09": "造紙",
    "10": "鋼鐵", "11": "橡膠", "12": "汽車", "14": "建材營造",
    "15": "航運", "16": "觀光餐旅", "17": "金融保險", "18": "貿易百貨",
    "20": "其他", "21": "化學", "22": "生技醫療", "23": "油電燃氣",
    "24": "半導體", "25": "電腦及週邊設備", "26": "光電", "27": "通信網路",
    "28": "電子零組件", "29": "電子通路", "30": "資訊服務", "31": "其他電子",
    "32": "文化創意", "33": "農業科技", "35": "綠能環保", "36": "數位雲端",
    "37": "運動休閒", "38": "居家生活", "91": "存託憑證",
}


def fetch_twse():
    """上市公司產業別"""
    import requests
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    resp = requests.get(url, timeout=30, headers={"User-Agent": "stock-system/1.0"})
    resp.raise_for_status()
    result = {}
    for row in resp.json():
        code = row.get("公司代號", "").strip()
        ind_code = row.get("產業別", "").strip()
        if code and ind_code:
            result[code] = INDUSTRY_MAP.get(ind_code, f"未知({ind_code})")
    return result


def fetch_tpex():
    """上櫃公司產業別"""
    import requests
    url = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
    resp = requests.get(url, timeout=30, headers={"User-Agent": "stock-system/1.0"})
    resp.raise_for_status()
    result = {}
    for row in resp.json():
        code = row.get("SecuritiesCompanyCode", "").strip()
        ind_code = row.get("SecuritiesIndustryCode", "").strip()
        if code and ind_code:
            result[code] = INDUSTRY_MAP.get(ind_code, f"未知({ind_code})")
    return result


def main():
    print("下載產業分類...")
    merged = {}

    try:
        twse = fetch_twse()
        print(f"  上市: {len(twse)} 家")
        merged.update(twse)
    except Exception as e:
        print(f"  上市抓取失敗: {e}")

    try:
        tpex = fetch_tpex()
        print(f"  上櫃: {len(tpex)} 家")
        merged.update(tpex)
    except Exception as e:
        print(f"  上櫃抓取失敗: {e}")

    if not merged:
        print("無資料，不覆寫")
        return

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"完成: {len(merged)} 家 -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
