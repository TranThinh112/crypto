@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0"
set "HOST=127.0.0.1"
set "PORT=8013"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "SYSTEM_PYTHON=py -3"
set "BUNDLED_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "REQ=%ROOT%requirements.txt"
set "ENVFILE=%ROOT%.env"
set "LOGDIR=%ROOT%logs"
set "OUTLOG=%LOGDIR%\bot-out.log"
set "ERRLOG=%LOGDIR%\bot-err.log"
set "INSTALL_MARKER=%ROOT%.venv\.requirements-installed"
set "DASHBOARD=http://%HOST%:%PORT%/"
set "HEALTH_URL=http://%HOST%:%PORT%/health"
set "CONFIG_URL=http://%HOST%:%PORT%/config/summary"
set "JOBS_URL=http://%HOST%:%PORT%/scheduler/jobs"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

cd /d "%ROOT%"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo ==========================================
echo Crypto Spot AI Bot
echo ==========================================
echo Root: %ROOT%
echo Dashboard: %DASHBOARD%
echo Mode: background service
echo.

if not exist "%ENVFILE%" (
  echo Missing .env file.
  echo Create .env first, or copy .env.example to .env and fill credentials.
  echo.
  pause
  exit /b 1
)

set "VENV_OK=0"
if exist "%PYTHON%" (
  "%PYTHON%" -c "import sys; print(sys.version)" >nul 2>nul
  if not errorlevel 1 set "VENV_OK=1"
)

if "%VENV_OK%"=="0" (
  echo Virtual environment missing or broken. Rebuilding .venv...
  if exist "%BUNDLED_PYTHON%" (
    "%BUNDLED_PYTHON%" -m venv "%ROOT%.venv" --clear
  ) else (
    %SYSTEM_PYTHON% -m venv "%ROOT%.venv" --clear
  )
  if errorlevel 1 (
    echo Failed to create .venv. Please install Python 3, or make sure bundled Codex Python is available.
    pause
    exit /b 1
  )
  if exist "%INSTALL_MARKER%" del "%INSTALL_MARKER%" >nul 2>nul
)

if not exist "%REQ%" (
  echo Missing requirements.txt.
  pause
  exit /b 1
)

if not exist "%INSTALL_MARKER%" (
  echo Installing dependencies...
  "%PYTHON%" -m pip install --upgrade pip
  if errorlevel 1 (
    echo Failed to upgrade pip.
    pause
    exit /b 1
  )
  "%PYTHON%" -m pip install -r "%REQ%"
  if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
  )
  echo installed>"%INSTALL_MARKER%"
)

echo Stopping old bot processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*uvicorn*spot_ai_bot.main:app*' -and $_.Name -notlike 'powershell*' -and $_.Name -notlike 'cmd*' }; foreach ($x in $p) { Stop-Process -Id $x.ProcessId -Force }"

echo Clearing old startup logs...
if exist "%OUTLOG%" del "%OUTLOG%" >nul 2>nul
if exist "%ERRLOG%" del "%ERRLOG%" >nul 2>nul

echo Starting bot in background...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%PYTHON%' -ArgumentList '-m','uvicorn','spot_ai_bot.main:app','--host','%HOST%','--port','%PORT%' -WorkingDirectory '%ROOT%' -WindowStyle Hidden -RedirectStandardOutput '%OUTLOG%' -RedirectStandardError '%ERRLOG%'"

echo Waiting for bot health...
set "READY=0"
for /L %%i in (1,1,20) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-RestMethod '%HEALTH_URL%' -TimeoutSec 5 | Out-Null; exit 0 } catch { exit 1 }"
  if not errorlevel 1 (
    set "READY=1"
    goto :BOT_READY
  )
  timeout /t 2 /nobreak >nul
)

:BOT_READY
if "%READY%"=="0" (
  echo [%date% %time%] Bot started, but health check did not respond yet.>>"%OUTLOG%"
  echo [%date% %time%] Check logs: "%OUTLOG%" "%ERRLOG%">>"%OUTLOG%"
) else (
  echo [%date% %time%] Bot is running at %DASHBOARD%>>"%OUTLOG%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { (Invoke-RestMethod '%JOBS_URL%' -TimeoutSec 10).jobs | ForEach-Object { Add-Content -Encoding UTF8 '%OUTLOG%' ('  ' + $_.id + ' -> ' + $_.next_run_time) } } catch { Add-Content -Encoding UTF8 '%OUTLOG%' '  Could not read scheduler jobs yet.' }"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $c=Invoke-RestMethod '%CONFIG_URL%' -TimeoutSec 10; Add-Content -Encoding UTF8 '%OUTLOG%' ('  GPT_5_4_Manager: ' + $c.gpt_5_4_manager_enabled + ' / configured=' + $c.gpt_5_4_manager_configured); Add-Content -Encoding UTF8 '%OUTLOG%' ('  GPT_Crypto: ' + $c.gpt_crypto_enabled + ' / configured=' + $c.gpt_crypto_configured); Add-Content -Encoding UTF8 '%OUTLOG%' ('  GPT_Fork: ' + $c.gpt_fork_enabled + ' / configured=' + $c.gpt_fork_configured) } catch { Add-Content -Encoding UTF8 '%OUTLOG%' '  Could not read AI role summary yet.' }"
)

start "" "%DASHBOARD%"

endlocal
exit /b 0
