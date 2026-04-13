param(
    [string]$BackendDir,
    [string]$LogDir
)

$python  = Join-Path $BackendDir "venv\Scripts\python.exe"
$logOut  = Join-Path $LogDir "backend.log"
$logErr  = Join-Path $LogDir "backend-error.log"
$pidFile = Join-Path $LogDir "backend.pid"

$p = Start-Process `
    -FilePath $python `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000" `
    -WorkingDirectory $BackendDir `
    -NoNewWindow `
    -RedirectStandardOutput $logOut `
    -RedirectStandardError  $logErr `
    -PassThru

if (-not $p) {
    Write-Host "FAILED: Start-Process returned null"
    exit 1
}

$p.Id | Out-File $pidFile -Encoding ascii -NoNewline -Force
Write-Host ("     Started PID " + $p.Id)
