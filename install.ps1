# Ember Council quick install for Windows. Run:  powershell -ExecutionPolicy Bypass -File install.ps1
# Checks Python 3.10+, optionally installs the extras (pypdf, keyring), detects Ollama, starts the server and opens the browser.
# Options: -Extras (install pypdf + keyring without asking)  -NoExtras  -NoStart (only check)  -Port 8000
param([switch]$Extras, [switch]$NoExtras, [switch]$NoStart, [int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# 1. Python 3.10+. Parse the real version output so the Microsoft Store "python" stub is not mistaken for Python.
function Find-Python {
  $cands = @()
  if (Get-Command py -ErrorAction SilentlyContinue) { $cands += ,@("py", "-3") }
  foreach ($n in @("python", "python3")) { if (Get-Command $n -ErrorAction SilentlyContinue) { $cands += ,@($n) } }
  foreach ($c in $cands) {
    $exe = $c[0]; $pre = @(); if ($c.Count -gt 1) { $pre = $c[1..($c.Count - 1)] }
    try { $v = (& $exe @pre --version 2>&1 | Out-String).Trim() } catch { continue }
    if ($v -match "^Python (\d+)\.(\d+)") {
      if ([int]$Matches[1] -gt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -ge 10)) { return ,(@($exe) + $pre) }
    }
  }
  return $null
}
$py = Find-Python
if (-not $py) {
  Write-Host "Python 3.10 or newer was not found." -ForegroundColor Red
  Write-Host "Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run this again."
  exit 1
}
$exe = $py[0]; $pre = @(); if ($py.Count -gt 1) { $pre = $py[1..($py.Count - 1)] }
Write-Host ("Python OK: " + (& $exe @pre --version 2>&1 | Out-String).Trim())

# 2. Optional extras. The core app needs nothing beyond Python.
$want = $Extras
if (-not $Extras -and -not $NoExtras -and [Environment]::UserInteractive) {
  $a = Read-Host "Install optional extras? pypdf lets Company Brain read PDFs; keyring keeps email passwords in Windows Credential Manager [y/N]"
  $want = ($a -match "^[yY]")
}
if ($want) {
  try { & $exe @pre -m pip install --user --disable-pip-version-check pypdf keyring; if ($LASTEXITCODE -ne 0) { throw "pip failed" } }
  catch { Write-Host "Could not install the extras. Ember Council still works without them." -ForegroundColor Yellow }
}

# 3. Ollama (a local engine keeps company data on this PC; recommended for regulated data).
$model = $null
try {
  $tags = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 2
  $chat = @($tags.models | Where-Object { $_.name -notmatch "embed" })  # embedding models cannot chat
  if ($chat.Count -gt 0) { $model = $chat[0].name }
  Write-Host ("Ollama is running" + $(if ($model) { " (model: $model)" } else { ", but no model is installed: run  ollama pull llama3.2" }))
} catch {
  if (Get-Command ollama -ErrorAction SilentlyContinue) { Write-Host "Ollama is installed but not running. Start it, then run  ollama pull llama3.2" }
  else { Write-Host "Ollama not found. For private, offline use install it from https://ollama.com and run  ollama pull llama3.2 (optional)." }
}
if ($model -and -not $env:OPENROUTER_API_KEY -and -not $env:LLM_BASE_URL) {
  $env:LLM_BASE_URL = "http://localhost:11434/v1"; $env:LLM_MODEL = $model; $env:LLM_API_KEY = "ollama"
  Write-Host "Using your local Ollama model for this session."
} elseif (-not $env:OPENROUTER_API_KEY -and -not $env:LLM_BASE_URL) {
  Write-Host "No model key found. Saved demo questions still replay for free. To ask new questions set OPENROUTER_API_KEY or use Ollama."
}

# 4. Pick a free port, start the server, open the browser.
function Test-Busy([int]$p) { $c = New-Object Net.Sockets.TcpClient; try { $c.Connect("127.0.0.1", $p); return $true } catch { return $false } finally { $c.Close() } }
$first = $Port
while ((Test-Busy $Port) -and $Port -lt $first + 20) { $Port++ }
$env:PORT = "$Port"
Write-Host "Self-check..."
& $exe @pre server.py --selftest | Select-Object -Last 1
if ($LASTEXITCODE -ne 0) { Write-Host "The self-test failed. See the messages above." -ForegroundColor Red; exit 1 }
if ($NoStart) { Write-Host "Checks passed (not starting the server: -NoStart)."; exit 0 }
Write-Host "Starting Ember Council at http://127.0.0.1:$Port  (close this window to stop it)"
Start-Job -ScriptBlock { param($u) Start-Sleep -Seconds 2; Start-Process $u } -ArgumentList "http://127.0.0.1:$Port" | Out-Null
& $exe @pre server.py
