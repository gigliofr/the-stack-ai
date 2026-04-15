param(
    [int]$PreferredApiPort = 18000,
    [int]$PreferredUiPort = 8601,
    [string]$BindHost = "127.0.0.1",
    [switch]$Headless
)

$ErrorActionPreference = "Stop"

function Get-FreePort {
    param([int]$Preferred)

    $inUse = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $Preferred }
    if (-not $inUse) {
        return $Preferred
    }

    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $port = ($listener.LocalEndpoint).Port
    $listener.Stop()
    return $port
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$Retries = 30,
        [int]$DelayMs = 500
    )

    for ($i = 0; $i -lt $Retries; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        } catch {
            # keep retrying
        }
        Start-Sleep -Milliseconds $DelayMs
    }

    return $false
}

$pythonExe = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$pythonExe = [System.IO.Path]::GetFullPath($pythonExe)
if (-not (Test-Path $pythonExe)) {
    throw "Python executable non trovato in .venv: $pythonExe"
}

$apiPort = Get-FreePort -Preferred $PreferredApiPort
$uiPort = Get-FreePort -Preferred $PreferredUiPort

$apiArgs = @("-m", "uvicorn", "src.api_server:app", "--host", $BindHost, "--port", "$apiPort")
$uiArgs = @("-m", "streamlit", "run", "src/app_ui.py", "--server.port", "$uiPort")
if ($Headless) {
    $uiArgs += @("--server.headless", "true")
}

$apiProcess = Start-Process -FilePath $pythonExe -ArgumentList $apiArgs -WorkingDirectory (Join-Path $PSScriptRoot "..") -PassThru
$uiProcess = Start-Process -FilePath $pythonExe -ArgumentList $uiArgs -WorkingDirectory (Join-Path $PSScriptRoot "..") -PassThru

$apiHealthUrl = "http://$BindHost`:$apiPort/health"
$uiUrl = "http://localhost:$uiPort"

$apiReady = Wait-HttpOk -Url $apiHealthUrl
$uiReady = Wait-HttpOk -Url $uiUrl

if (-not $apiReady) {
    Write-Host "[WARN] API non ancora pronta su $apiHealthUrl" -ForegroundColor Yellow
} else {
    Write-Host "[OK] API pronta su $apiHealthUrl" -ForegroundColor Green
}

if (-not $uiReady) {
    Write-Host "[WARN] UI non ancora pronta su $uiUrl" -ForegroundColor Yellow
} else {
    Write-Host "[OK] UI pronta su $uiUrl" -ForegroundColor Green
}

Write-Host "" 
Write-Host "API URL: http://$BindHost`:$apiPort" -ForegroundColor Cyan
Write-Host "UI URL:  $uiUrl" -ForegroundColor Cyan
Write-Host "" 
Write-Host "Process IDs:" -ForegroundColor Cyan
Write-Host "- API PID: $($apiProcess.Id)"
Write-Host "- UI PID:  $($uiProcess.Id)"
Write-Host "" 
Write-Host "Per fermare i processi:" -ForegroundColor Cyan
Write-Host "Stop-Process -Id $($apiProcess.Id),$($uiProcess.Id)"
