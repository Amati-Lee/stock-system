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
git pull --ff-only

for /f %%i in ('powershell -command "Get-Date -Format \"yyyyMMdd\""') do set TODAY=%%i

if exist "stock_data_%TODAY%.csv" (
    echo.
    echo ℹ️ 今日 CSV 已存在（GitHub Actions 已下載），跳過下載。
    echo.
    echo [Step 1.5] 下載 OHLC K線資料...
    echo.
    python download_ohlc.py
    echo.
    echo [Step 1.8] 起飛警示掃描...
    echo.
    python stock_alert.py
    echo.
    echo [Step 2] 產生本地資料（突破訊號 CSV + PWA）...
    echo.
    python generate_pwa.py
    echo.
    echo ✅ 完成！本地資料已產生，網站由 GitHub Actions 部署。
    echo.
    if not "%1"=="auto" pause
    exit /b 0
)

echo [Step 1] 下載數據 + 分析篩選...
echo.
python stock_system.py

if %errorlevel% neq 0 (
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
echo [Step 1.8] 起飛警示掃描...
echo.
python stock_alert.py

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
set CLOUDFLARE_API_TOKEN=7NRf_D8SLdWVPtgvM_otnp1AUVD8Cz_lF7Z8ixeC
set CLOUDFLARE_ACCOUNT_ID=49021099240f48de19359e92dd0732a0
npx wrangler pages deploy pwa --project-name=stock-viewer --branch=main

echo.
echo ✅ 完成！ %date% %time%
if not "%1"=="auto" pause
