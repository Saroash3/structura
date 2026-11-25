# Keeps Structura's backend and its ngrok tunnel running, with no windows.
# Started hidden at logon by deploy/start-hidden.vbs (Task Scheduler task "Structura Backend").
# Every 20 s it checks both and restarts whatever stopped. Logs: deploy/logs/.
$ErrorActionPreference = "SilentlyContinue"

$root    = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$logs    = Join-Path $PSScriptRoot "logs"
$ngrokCfg = Join-Path $env:LOCALAPPDATA "ngrok\structura.yml"
New-Item -ItemType Directory -Force $logs | Out-Null

# one supervisor at a time
$created = $false
$mutex = New-Object System.Threading.Mutex($true, "Global\StructuraSupervisor", [ref]$created)
if (-not $created) { exit 0 }

function Write-Log($msg) { Add-Content -Path (Join-Path $logs "supervisor.log") -Value "$(Get-Date -Format s)  $msg" }

function Test-Url($url) {
    try { (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 } catch { $false }
}

function Find-Ngrok {
    $cmd = Get-Command ngrok -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $hit = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter ngrok.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { return $hit.FullName }
    return $null
}

function Start-Backend {
    # stop a hung backend still holding the port
    Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)"
        if ($p.CommandLine -like "*uvicorn*main:app*") { Stop-Process -Id $p.ProcessId -Force }
    }
    Start-Process -FilePath (Join-Path $backend ".venv\Scripts\uvicorn.exe") -ArgumentList "main:app --port 8000" `
        -WorkingDirectory $backend -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "backend.out.log") -RedirectStandardError (Join-Path $logs "backend.log")
    Write-Log "started backend"
}

function Start-Tunnel {
    $ngrok = Find-Ngrok
    if (-not $ngrok) { Write-Log "ngrok not found"; return }
    # only the Structura tunnel (the other ngrok session, on port 8001, belongs to another app and is left alone)
    Get-CimInstance Win32_Process -Filter "Name='ngrok.exe'" | Where-Object { $_.CommandLine -like "*structura.yml*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Start-Process -FilePath $ngrok -ArgumentList "http 8000 --config `"$ngrokCfg`" --log `"$(Join-Path $logs 'ngrok.log')`"" `
        -WindowStyle Hidden
    Write-Log "started ngrok tunnel"
}

Write-Log "supervisor up"
while ($true) {
    if (-not (Test-Url "http://localhost:8000/health")) {
        Start-Sleep -Seconds 8   # it may just be starting
        if (-not (Test-Url "http://localhost:8000/health")) { Start-Backend; Start-Sleep -Seconds 15 }
    }
    if (-not (Test-Url "http://127.0.0.1:4041/api/tunnels")) { Start-Tunnel; Start-Sleep -Seconds 10 }
    Start-Sleep -Seconds 20
}
