@echo off
chcp 65001 >nul
title 台股每日分析系統

echo ======================================================================
echo   台股每日分析系統
echo ======================================================================
echo.

cd /d D:\stock_system

echo [Step 0] 從 GitHub 同步最新資料...
echo.
git pull --ff-only

for /f %%i in ('powershell -command "Get-Date -Format \"yyyyMMdd\""') do set TODAY=%%i

if exist "stock_data_%TODAY%.csv" (
    echo.
    echo ✅ 今日資料 stock_data_%TODAY%.csv 已存在（GitHub Actions 已處理），跳過。
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
npx wrangler pages deploy pwa --project-name=stock-viewer

echo.
echo ✅ 完成！ %date% %time%
if not "%1"=="auto" pause
