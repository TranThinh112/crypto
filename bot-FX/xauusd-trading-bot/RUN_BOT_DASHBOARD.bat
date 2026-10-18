@echo off
setlocal EnableExtensions
title Trading Bot Forex - Dashboard

cd /d "%~dp0"

set "PYTHON_EXE=C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe"
set "DASHBOARD_URL=http://127.0.0.1:8000/dashboard"
set "MT5_EXE="
set "MT5_WAIT_SECONDS=8"
set "AUTO_START_BOT=true"
set "SERVER_STDOUT=%CD%\logs\bot_server_stdout.log"
set "SERVER_STDERR=%CD%\logs\bot_server_error.log"

echo ==========================================
echo       TRADING BOT FOREX - STARTER
echo ==========================================
echo.

if not exist "%PYTHON_EXE%" (
    echo [LOI] Khong tim thay Python tai:
    echo %PYTHON_EXE%
    echo.
    echo Hay cai Python hoac sua duong dan PYTHON_EXE trong file BAT nay.
    echo.
    pause
    exit /b 1
)

if not exist "app\main.py" (
    echo [LOI] File nay phai nam trong thu muc xauusd-trading-bot.
    echo Thu muc hien tai:
    echo %CD%
    echo.
    pause
    exit /b 1
)

call :START_MT5

echo Kiem tra port 8000...
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if %ERRORLEVEL%==0 (
    echo Bot/API dang chay san tren port 8000.
    echo Gui lenh start bot neu bot chua chay...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-RestMethod -Method Post -Uri '%DASHBOARD_URL:/dashboard=/bot/start%' -TimeoutSec 8 | Out-Null } catch { Write-Host $_.Exception.Message }"
    echo Mo dashboard...
    start "" "%DASHBOARD_URL%"
    echo.
    echo Neu muon tat bot/API, hay chay STOP_BOT_DASHBOARD.bat.
    echo.
    pause
    exit /b 0
)

if not exist "logs" mkdir logs

echo Dang khoi dong bot/API o che do nen...
echo Dashboard se tu mo sau vai giay. Log server nam trong thu muc logs.
echo.
echo Luu y:
echo - MT5 da duoc mo tu dong neu tim thay terminal64.exe.
echo - Dang nhap dung tai khoan demo.
echo - Bat nut Algo Trading trong MT5.
echo - AUTO_START_BOT=true nen bot se tu start khi ket noi thanh cong.
echo.

start "" /min cmd /c "timeout /t 5 /nobreak >nul & start "" %DASHBOARD_URL%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -WorkingDirectory '%CD%' -FilePath '%PYTHON_EXE%' -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -RedirectStandardOutput '%SERVER_STDOUT%' -RedirectStandardError '%SERVER_STDERR%'"

echo.
echo Da gui lenh khoi dong Bot/API.
echo Co the dong cua so nay. Muon tat bot/API thi chay STOP_BOT_DASHBOARD.bat.
echo.
pause
exit /b 0

:START_MT5
if defined MT5_TERMINAL_PATH set "MT5_EXE=%MT5_TERMINAL_PATH%"

if not defined MT5_EXE if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if /I "%%~A"=="MT5_TERMINAL_PATH" if not "%%~B"=="" set "MT5_EXE=%%~B"
    )
)

if not defined MT5_EXE if exist "C:\Program Files\MetaTrader 5\terminal64.exe" set "MT5_EXE=C:\Program Files\MetaTrader 5\terminal64.exe"
if not defined MT5_EXE if exist "C:\Program Files (x86)\MetaTrader 5\terminal64.exe" set "MT5_EXE=C:\Program Files (x86)\MetaTrader 5\terminal64.exe"
if not defined MT5_EXE if exist "%LOCALAPPDATA%\Programs\MetaTrader 5\terminal64.exe" set "MT5_EXE=%LOCALAPPDATA%\Programs\MetaTrader 5\terminal64.exe"

if not defined MT5_EXE (
    echo [CANH BAO] Khong tim thay MT5 terminal64.exe.
    echo Hay sua MT5_TERMINAL_PATH trong file .env hoac mo MT5 thu cong.
    echo.
    exit /b 0
)

if not exist "%MT5_EXE%" (
    echo [CANH BAO] Duong dan MT5 khong ton tai:
    echo %MT5_EXE%
    echo Hay sua MT5_TERMINAL_PATH trong file .env hoac mo MT5 thu cong.
    echo.
    exit /b 0
)

echo Dang mo MetaTrader 5...
start "" "%MT5_EXE%"
echo Cho MT5 khoi dong %MT5_WAIT_SECONDS% giay...
timeout /t %MT5_WAIT_SECONDS% /nobreak >nul
echo.
exit /b 0
