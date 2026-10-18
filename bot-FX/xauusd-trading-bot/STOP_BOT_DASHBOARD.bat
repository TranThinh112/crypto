@echo off
setlocal EnableExtensions
title Trading Bot Forex - Stop Dashboard/API

set "API_PORT=8000"
set "FOUND="

echo ==========================================
echo     TRADING BOT FOREX - STOP SERVER
echo ==========================================
echo.
echo Dang tim Bot/API tren port %API_PORT%...

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%API_PORT%" ^| findstr "LISTENING"') do (
    set "FOUND=1"
    echo Dang tat process PID %%P...
    taskkill /PID %%P /F >nul 2>&1
    if errorlevel 1 (
        echo [LOI] Khong tat duoc PID %%P. Hay mo file nay bang Run as administrator.
    ) else (
        echo Da tat PID %%P.
    )
)

if not defined FOUND (
    echo Khong thay Bot/API dang chay tren port %API_PORT%.
)

echo.
echo Luu y: File nay chi tat Python API/dashboard, khong tat MT5.
echo.
pause
