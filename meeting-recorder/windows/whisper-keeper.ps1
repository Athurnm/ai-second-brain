# whisper-keeper.ps1 -- keep whisper-server.exe alive for the Vexa meeting bots.
#
# Why this exists: whisper-server is a plain console process on Windows. The old
# setup relied on a Startup shortcut (runs once at logon, no crash recovery) plus
# WSL reaching back in over PowerShell interop to restart it. When interop breaks
# or the process dies mid-day, every Vexa bot silently produces an EMPTY transcript.
# This keeper is idempotent and safe to run on a schedule: it starts whisper-server
# only if port 8083 is not already listening, so a running server is never disturbed.
#
# Run manually:   powershell -ExecutionPolicy Bypass -File C:\tools\whisper-keeper.ps1
# Installed by:   install-whisper-service.ps1  (Scheduled Task, every 3 min + at logon)

$ErrorActionPreference = 'Stop'
$Port    = 8083
$Exe     = 'C:\tools\whisper.cpp-src\build\bin\whisper-server.exe'
$Model   = 'C:\tools\whisper.cpp-src\models\ggml-large-v3-turbo.bin'
$LogDir  = 'C:\tools\whisper-logs'
$LogFile = Join-Path $LogDir 'keeper.log'

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
function Log($msg) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg" | Add-Content -Path $LogFile }

# Already listening? Nothing to do.
$listening = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($listening) { exit 0 }

if (-not (Test-Path $Exe))   { Log "MISSING exe:   $Exe";   exit 1 }
if (-not (Test-Path $Model)) { Log "MISSING model: $Model"; exit 1 }

# Kill any zombie whisper-server that is running but not listening (crashed socket).
Get-Process whisper-server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# --host 0.0.0.0 is REQUIRED: binding to 127.0.0.1 would hide the server from WSL
# (the Vexa container reaches it via the WSL gateway IP, not localhost).
$args = @(
  '-m', $Model,
  '--host', '0.0.0.0',
  '--port', "$Port",
  '--inference-path', '/v1/audio/transcriptions'
)
$out = Join-Path $LogDir 'whisper-server.out.log'
$err = Join-Path $LogDir 'whisper-server.err.log'
Start-Process -FilePath $Exe -ArgumentList $args -WindowStyle Hidden `
  -RedirectStandardOutput $out -RedirectStandardError $err

# Confirm it came up.
$ok = $false
foreach ($i in 1..10) {
  Start-Sleep -Seconds 2
  if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) { $ok = $true; break }
}
if ($ok) { Log "STARTED whisper-server on 0.0.0.0:$Port" }
else     { Log "FAILED to start whisper-server (see whisper-server.err.log)" }
