@echo off
chcp 65001 >nul
title 台股每日分析系統

cd /d D:\stock_system

REM 檢查是否為交易日（跳過週末 + 國定假日）
python -c "import datetime,sys; today=datetime.date.today(); wd=today.weekday(); holidays=[l.strip() for l in open('holidays.txt',encoding='utf-8') if l.strip() and not l.strip().startswith('#')]; is_holiday=str(today) in holidays; print(f'今天 {today} ({'週六' if wd==5 else '週日' if wd==6 else '國定假日'})，非交易日，跳過。') if wd>=5 or is_holiday else None; sys.exit(1 if wd>=5 or is_holiday else 0)"
if %errorlevel% neq 0 (
    if not "%1"=="auto" pause
    exit /b 0
)

echo ======================================================================
echo   台股每日分析系統
echo ======================================================================
echo.

echo [Step 0] 從 GitHub 同步最新資料...
echo.
git checkout -- ohlc_snapshot.tar.gz 2>nul
git pull --rebase || (
    echo ⚠️ pull --rebase 失敗，嘗試 reset 到 remote...
    git rebase --abort 2>nul
    git stash --include-untracked 2>nul
    git pull --rebase
    git stash pop 2>nul
)

for /f %%i in ('powershell -command "Get-Date -Format \"yyyyMMdd\""') do set TODAY=%%i

if exist "stock_data_%TODAY%.csv" (
    echo.
    echo ℹ️ 今日 CSV 已存在（GitHub Actions 已下載），跳過下載。
    echo.
    echo [Step 1.5] 下載 OHLC K線資料...
    echo.
    python download_ohlc.py
    echo.
    echo [Step 1.6] 下載三大法人資料...
    echo.
    python download_institutional.py
    echo.
    echo [Step 1.7] 下載 PE 河流位置...
    echo.
    python download_pe.py
    echo.
    echo [Step 1.75] 下載法說會日期...
    echo.
    python download_conference.py
    echo.
    echo [Step 1.76] 更新產業分類...
    echo.
    python download_industry.py
    echo.
    echo [Step 1.8] 起飛警示掃描...
    echo.
    python stock_alert.py
    echo.
    echo ℹ️ AI 分析 / 觀察清單已由 GitHub Actions 產生（git pull 取得），跳過。
    echo.
    echo [Step 2] 產生本地資料（突破訊號 CSV + PWA）...
    echo.
    python generate_pwa.py
    echo.
    echo [Step 3] 推送資料到 GitHub...
    echo.
    git add stock_data_*.csv stock_names_all.json stock_industry.json tw_stock_verified.txt watchlist.json ohlc_snapshot.tar.gz
    git add -f pwa/alerts.json pwa/analysis.json pwa/institutional.json pwa/watchlist_status.json pwa/pe_river.json pwa/conferences.json pwa/index.html pwa/sw.js
    git add -f pe_history.json
    git diff --cached --quiet || git commit -m "data: %TODAY:~0,4%-%TODAY:~4,2%-%TODAY:~6,2% stock update (local)"
    git pull --rebase -X theirs 2>nul
    git push 2>nul || echo ⚠️ push 失敗（可能無網路），下次同步
    echo.
    echo ✅ 完成！本地資料已產生並同步。
    echo.
    if not "%1"=="auto" pause
    exit /b 0
)

echo [Step 1] 下載數據 + 分析篩選...
echo.
python stock_system.py
set STOCK_EXIT=%errorlevel%

if %STOCK_EXIT% equ 2 (
    echo.
    echo ⚠️ 資料過期（API 尚未更新），跳過後續步驟
    if not "%1"=="auto" pause
    exit /b 0
)

if %STOCK_EXIT% neq 0 (
    echo.
    echo ❌ 執行失敗，請檢查網路連線
    if not "%1"=="auto" pause
    exit /b 1
)

echo.
echo [Step 1.5] 下載 OHLC K線資料...
echo.
python download_ohlc.py

echo.
echo [Step 1.6] 下載三大法人資料...
echo.
python download_institutional.py

echo.
echo [Step 1.7] 下載 PE 河流位置...
echo.
python download_pe.py

echo.
echo [Step 1.76] 更新產業分類...
echo.
python download_industry.py

echo.
echo [Step 1.8] 起飛警示掃描...
echo.
python stock_alert.py

echo.
echo [Step 1.9] AI 分析起飛警示個股...
echo.
python stock_analyze.py

echo.
echo [Step 1.95] 觀察清單條件檢查...
echo.
python watchlist_check.py

echo.
echo [Step 2] 產生手機版 PWA...
echo.
python generate_pwa.py

if %errorlevel% neq 0 (
    echo.
    echo ⚠️ PWA 產生失敗
    if not "%1"=="auto" pause
    exit /b 1
)

echo.
echo [Step 3] 部署到 Cloudflare...
echo.
REM CLOUDFLARE_API_TOKEN 和 CLOUDFLARE_ACCOUNT_ID 從 Windows 環境變數讀取
if not defined CLOUDFLARE_API_TOKEN (
    echo ⚠️ 未設定 CLOUDFLARE_API_TOKEN 環境變數，跳過部署
    if not "%1"=="auto" pause
    exit /b 1
)
npx wrangler pages deploy pwa --project-name=stock-viewer --branch=main

echo.
echo [Step 4] 推送資料到 GitHub...
echo.
git add stock_data_*.csv stock_names_all.json stock_industry.json tw_stock_verified.txt watchlist.json ohlc_snapshot.tar.gz
git add -f pwa/alerts.json pwa/analysis.json pwa/institutional.json pwa/watchlist_status.json pwa/pe_river.json pwa/conferences.json pwa/index.html pwa/sw.js
git add -f pe_history.json
git diff --cached --quiet || git commit -m "data: %TODAY:~0,4%-%TODAY:~4,2%-%TODAY:~6,2% stock update (local)"
git pull --rebase -X theirs 2>nul
git push 2>nul || echo ⚠️ push 失敗（可能無網路），下次同步

echo.
echo ✅ 完成！ %date% %time%
if not "%1"=="auto" pause
