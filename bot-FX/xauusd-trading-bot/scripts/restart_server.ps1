param(
    [int]$Port = 8000
)

$python = 'C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe'
$wd = 'C:\Users\Admin\Documents\bot forex\xauusd-trading-bot'
$stdout = Join-Path $wd 'logs\bot_server_stdout.log'
$stderr = Join-Path $wd 'logs\bot_server_error.log'

$listener = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object State -eq Listen | Select-Object -First 1
if ($listener) {
    Stop-Process -Id $listener.OwningProcess -Force
    Start-Sleep -Seconds 2
}

Start-Process -WindowStyle Hidden -WorkingDirectory $wd -FilePath $python -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$Port" -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Start-Sleep -Seconds 5

try {
    Invoke-RestMethod "http://127.0.0.1:$Port/status" | ConvertTo-Json -Depth 5
} catch {
    $_.Exception.Message
}
