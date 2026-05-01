# voider — Windows setup
# - Verifies Ollama is installed + running
# - Lets you pick a model from a curated list (good tool-use models first)
# - Pulls the model
# - Creates a Python venv and installs deps
# - Writes config.local.json

$ErrorActionPreference = "Stop"
$script:RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $script:RepoRoot

function Write-Step([string]$msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "  ok: $msg" -ForegroundColor Green }
function Write-Warn2([string]$msg){ Write-Host "  warn: $msg" -ForegroundColor Yellow }
function Write-Err2([string]$msg) { Write-Host "  err: $msg" -ForegroundColor Red }

# --- Ollama -----------------------------------------------------------------
Write-Step "Checking for Ollama"
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Write-Err2 "Ollama is not installed."
    Write-Host "  Install it from https://ollama.com/download then re-run setup.ps1."
    Write-Host "  Or with winget:  winget install Ollama.Ollama"
    exit 1
}
Write-Ok "Found ollama at $($ollama.Source)"

Write-Step "Checking that the Ollama service responds"
$ollamaHost = "http://localhost:11434"
$ok = $false
for ($i = 0; $i -lt 10; $i++) {
    try {
        $null = Invoke-RestMethod -Uri "$ollamaHost/api/tags" -TimeoutSec 2
        $ok = $true; break
    } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $ok) {
    Write-Warn2 "Ollama isn't responding on $ollamaHost. Trying to start it..."
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 2
    try {
        $null = Invoke-RestMethod -Uri "$ollamaHost/api/tags" -TimeoutSec 5
        $ok = $true
    } catch {}
}
if (-not $ok) {
    Write-Err2 "Couldn't reach Ollama at $ollamaHost. Start it manually (`ollama serve`) and re-run."
    exit 1
}
Write-Ok "Ollama is up."

# --- Model picker -----------------------------------------------------------
# Curated for: strong tool-calling, fits on a typical dev machine.
$Catalog = @(
    [pscustomobject]@{ Name = "qwen2.5:7b";   Size = "~4.7 GB"; Notes = "recommended — strong tool use, balanced speed/quality" },
    [pscustomobject]@{ Name = "qwen2.5:3b";   Size = "~1.9 GB"; Notes = "small + fast, decent tool use" },
    [pscustomobject]@{ Name = "qwen2.5:14b";  Size = "~9 GB";   Notes = "higher quality, needs ~16 GB RAM / decent GPU" },
    [pscustomobject]@{ Name = "llama3.1:8b";  Size = "~4.7 GB"; Notes = "popular general model, good tool use" },
    [pscustomobject]@{ Name = "llama3.2:3b";  Size = "~2 GB";   Notes = "small + fast" },
    [pscustomobject]@{ Name = "mistral:7b";   Size = "~4.1 GB"; Notes = "solid baseline" },
    [pscustomobject]@{ Name = "phi3.5:3.8b";  Size = "~2.2 GB"; Notes = "small, good reasoning for size" }
)

Write-Step "Already-pulled models"
$installed = @()
try {
    $tags = Invoke-RestMethod -Uri "$ollamaHost/api/tags" -TimeoutSec 5
    if ($tags.models) { $installed = $tags.models | ForEach-Object { $_.name } }
} catch {}
if ($installed.Count -gt 0) {
    $installed | ForEach-Object { Write-Host "  - $_" }
} else {
    Write-Host "  (none yet)"
}

Write-Step "Pick a model to use with voider"
$idx = 1
foreach ($m in $Catalog) {
    $tag = if ($installed -contains $m.Name) { "[installed]" } else { "" }
    Write-Host ("  {0,2}) {1,-16} {2,-9} {3} {4}" -f $idx, $m.Name, $m.Size, $m.Notes, $tag)
    $idx++
}
Write-Host ("  {0,2}) custom model name…" -f $idx)

$choice = Read-Host "Enter number"
$selected = $null
if ([int]::TryParse($choice, [ref]([int]$null))) {
    $n = [int]$choice
    if ($n -ge 1 -and $n -le $Catalog.Count) {
        $selected = $Catalog[$n - 1].Name
    } elseif ($n -eq $Catalog.Count + 1) {
        $selected = (Read-Host "Enter ollama model tag (e.g. 'mistral-nemo:12b')").Trim()
    }
}
if (-not $selected) {
    Write-Err2 "Invalid choice."
    exit 1
}

if ($installed -notcontains $selected) {
    Write-Step "Pulling $selected (this can take a while)"
    & ollama pull $selected
    if ($LASTEXITCODE -ne 0) {
        Write-Err2 "ollama pull failed."
        exit 1
    }
}
Write-Ok "Model ready: $selected"

# --- Python venv ------------------------------------------------------------
Write-Step "Setting up Python virtual environment"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $python) {
    Write-Err2 "Python 3.11+ is required. Install from https://python.org or:  winget install Python.Python.3.12"
    exit 1
}

if (-not (Test-Path ".venv")) {
    & $python.Source -m venv .venv
}
$venvPy = Join-Path $script:RepoRoot ".venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r requirements.txt
Write-Ok "Dependencies installed."

# --- Write config -----------------------------------------------------------
Write-Step "Writing config.local.json"
$cfg = [ordered]@{
    model       = $selected
    ollama_url  = $ollamaHost
    host        = "127.0.0.1"
    port        = 8765
}
$cfg | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path (Join-Path $script:RepoRoot "config.local.json")
Write-Ok "Wrote config.local.json"

Write-Host ""
Write-Host "All set. Start voider with:" -ForegroundColor Green
Write-Host "    ./run.ps1" -ForegroundColor Green
Write-Host "Then open http://localhost:8765" -ForegroundColor Green
