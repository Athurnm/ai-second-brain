# AI Second Brain - one-command bootstrap for Windows (PowerShell)
# Level 0 gets you a working conversational brain in ~15 minutes.
# Connectors (Google, Slack, ...) come later via docs/SETUP.md.
#
# Usage:  .\install.ps1
# Safe to re-run: it never overwrites a file you already customized.

$ErrorActionPreference = "Stop"

function ok   { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function warn { param($msg) Write-Host "  [..] $msg" -ForegroundColor Yellow }
function fail { param($msg) Write-Host "  [!!] $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "AI Second Brain - bootstrap" -ForegroundColor Cyan
Write-Host "===========================" -ForegroundColor Cyan

# 1. Prerequisites -------------------------------------------------------
Write-Host ""
Write-Host "[1/4] Checking prerequisites"

$missing = $false

# git
if (Get-Command git -ErrorAction SilentlyContinue) {
    $gitVer = (git --version) -replace "git version ", ""
    ok "git $gitVer"
} else {
    fail "git not found - install it from https://git-scm.com/download/win"
    $missing = $true
}

# python (try 'python' then 'python3')
$pythonCmd = $null
foreach ($cmd in @("python", "python3")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        $pyVer = & $cmd --version 2>&1
        ok "$pyVer"
        $pythonCmd = $cmd
        break
    }
}
if (-not $pythonCmd) {
    warn "python not found - only needed for connectors (Level 1+). Level 0 works without it."
}

# Claude Code CLI
if (Get-Command claude -ErrorAction SilentlyContinue) {
    $claudeVer = (claude --version 2>&1 | Select-Object -First 1)
    ok "Claude Code $claudeVer"
} else {
    warn "Claude Code CLI not found."
    warn "Install: npm install -g @anthropic-ai/claude-code"
    warn "You can finish this script now and install Claude Code after."
}

if ($missing) {
    Write-Host ""
    fail "Fix the items above, then re-run: .\install.ps1"
    exit 1
}

# 2. Brain file ----------------------------------------------------------
Write-Host ""
Write-Host "[2/4] Creating your brain file"

if (Test-Path "CLAUDE.md") {
    ok "CLAUDE.md already exists - keeping yours"
} elseif (Test-Path "CLAUDE.md.template") {
    Copy-Item "CLAUDE.md.template" "CLAUDE.md"
    ok "CLAUDE.md created from template - open it and fill in who you are"
} else {
    fail "CLAUDE.md.template missing - are you running this from the repo root?"
    exit 1
}

# 3. Environment file ----------------------------------------------------
Write-Host ""
Write-Host "[3/4] Creating your .env"

if (Test-Path ".env") {
    ok ".env already exists - keeping yours"
} elseif (Test-Path ".env.example") {
    Copy-Item ".env.example" ".env"
    ok ".env created - fill in API keys later, only for the connectors you use"
} else {
    warn ".env.example missing - skipped"
}

# 4. Python dependencies (optional, for connectors) ----------------------
Write-Host ""
Write-Host "[4/4] Python dependencies (optional - connectors only)"

if ($pythonCmd -and (Test-Path "requirements.txt")) {
    try {
        & $pythonCmd -m pip install -r requirements.txt --quiet 2>&1 | Out-Null
        ok "Python dependencies installed"
    } catch {
        warn "pip install failed or was skipped - fine for Level 0."
        warn "Retry later with: python -m pip install -r requirements.txt"
    }
} else {
    warn "Skipped (no python or no requirements.txt) - fine for Level 0."
}

# Done -------------------------------------------------------------------
Write-Host ""
Write-Host "Done. Next steps:" -ForegroundColor Cyan
Write-Host "  1. Open CLAUDE.md and describe yourself: role, projects, house rules"
Write-Host "     (docs/CUSTOMIZING.md explains every section)"
Write-Host "  2. Run:  claude"
Write-Host "  3. Say:  'Read CLAUDE.md and introduce yourself as my second brain.'"
Write-Host ""
Write-Host "When you want it connected to Google Docs, Slack, calendars, and meetings:"
Write-Host "  docs/SETUP.md - the full guide, connector by connector."
Write-Host ""
