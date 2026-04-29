@echo off
chcp 65001 >nul
echo ========================================
echo   台股趨勢分析（從 GitHub 取最新資料）
echo ========================================
echo.

cd /d D:\stock_system

echo [1/2] 拉取最新資料...
git pull --quiet
if errorlevel 1 (
    echo Git pull 失敗
    pause
    exit /b 1
)

echo [2/2] 執行趨勢分析...
python trend_analyzer.py

echo.
echo 完成！
pause
