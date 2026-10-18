@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0"
set "PORT=8013"
set "LOGDIR=%ROOT%logs"
set "STOPLOG=%LOGDIR%\bot-stop.log"

cd /d "%ROOT%"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo [%date% %time%] Stopping Crypto Spot AI Bot...>"%STOPLOG%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$targets=@(); $targets += Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*uvicorn*spot_ai_bot.main:app*' }; $ports = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue; foreach ($port in $ports) { $proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $port.OwningProcess); if ($proc -and $proc.Name -like 'python*') { $targets += $proc } }; $targets | Sort-Object ProcessId -Unique | ForEach-Object { Add-Content -Encoding UTF8 '%STOPLOG%' ('Stopping PID ' + $_.ProcessId + ': ' + $_.CommandLine); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo [%date% %time%] Stop command completed.>>"%STOPLOG%"
endlocal
exit /b 0
