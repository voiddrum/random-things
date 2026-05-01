# voider — launch the server.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $repo

$venvPy = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "Virtual env not found. Run ./setup.ps1 first." -ForegroundColor Red
    exit 1
}

# Make sure Ollama is up (best-effort).
try { $null = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 }
catch {
    Write-Host "Ollama not responding — starting it in the background." -ForegroundColor Yellow
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 2
}

& $venvPy -m voider
