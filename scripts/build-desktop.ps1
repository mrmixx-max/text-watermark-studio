# scripts/build-desktop.ps1
# Build the Windows desktop app + installer (PyInstaller -> Inno Setup).
#
# Usage:
#   .\scripts\build-desktop.ps1                # build with defaults
#   .\scripts\build-desktop.ps1 -SkipInno      # PyInstaller only (no installer)
#   .\scripts\build-desktop.ps1 -Clean         # clean dist/ first
#   .\scripts\build-desktop.ps1 -Python "py"   # use a specific Python launcher
#
# Produces:
#   dist/tws-desktop.exe   (PyInstaller onefile, windowed)
#   dist/TWS-Setup-2.4.1.exe (Inno Setup installer, if -SkipInno not set)

[CmdletBinding()]
param(
    [string]$Python = "python",
    [switch]$SkipInno,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$DistDir  = Join-Path $RepoRoot "dist"
$PackagingDir = Join-Path $RepoRoot "packaging"

# ---------------------------------------------------------------------------
# Helper: run a command and abort on failure.
# ---------------------------------------------------------------------------
function Invoke-Checked {
    param([string]$Command, [string]$Arguments, [string]$Phase)
    Write-Host "=== $Phase ===" -ForegroundColor Cyan
    Write-Host "$Command $Arguments" -ForegroundColor DarkGray
    & $Command $Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "$Phase failed (exit code $LASTEXITCODE)"
    }
}

# ---------------------------------------------------------------------------
# 0. Clean (optional)
# ---------------------------------------------------------------------------
if ($Clean -and (Test-Path $DistDir)) {
    Write-Host "=== Cleaning dist/ ===" -ForegroundColor Yellow
    Remove-Item -Recurse -Force $DistDir
}

if (-not (Test-Path $DistDir)) {
    New-Item -ItemType Directory -Path $DistDir | Out-Null
}

# ---------------------------------------------------------------------------
# 1. Ensure PyInstaller + PySide6 are installed
# ---------------------------------------------------------------------------
Write-Host "=== Checking build dependencies ===" -ForegroundColor Cyan
& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller + PySide6..." -ForegroundColor Yellow
    & $Python -m pip install --quiet PySide6 pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "pip install PySide6 pyinstaller failed" }
}

# Ensure the project is installed (editable) so the spec can import it.
& $Python -c "import ai_watermark_toolkit" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing project (editable)..." -ForegroundColor Yellow
    & $Python -m pip install --quiet -e $RepoRoot
    if ($LASTEXITCODE -ne 0) { throw "pip install -e . failed" }
}

# ---------------------------------------------------------------------------
# 2. Build standalone exe (PyInstaller, onefile, windowed)
# ---------------------------------------------------------------------------
$specPath = Join-Path $PackagingDir "tws-desktop.spec"
if (-not (Test-Path $specPath)) {
    throw "Spec file not found: $specPath"
}

Invoke-Checked -Command $Python -Arguments "-m PyInstaller `"$specPath`" --distpath `"$DistDir`" --workpath `"$RepoRoot\build`"" -Phase "PyInstaller build"

$exePath = Join-Path $DistDir "tws-desktop.exe"
if (-not (Test-Path $exePath)) {
    throw "PyInstaller did not produce $exePath"
}
Write-Host "=== PyInstaller OK: $exePath ===" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 3. Compile installer (Inno Setup) — optional
# ---------------------------------------------------------------------------
if (-not $SkipInno) {
    $iscc = $null
    $candidatePaths = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    foreach ($c in $candidatePaths) {
        if (Test-Path $c) { $iscc = $c; break }
    }
    if (-not $iscc) {
        # Try PATH
        $innoInPath = Get-Command iscc -ErrorAction SilentlyContinue
        if ($innoInPath) { $iscc = $innoInPath.Source }
    }
    if (-not $iscc) {
        Write-Warning "Inno Setup (ISCC.exe) not found. Skipping installer. Install via: choco install innosetup"
        Write-Host "=== Build complete (exe only, no installer) ===" -ForegroundColor Green
        exit 0
    }

    $issPath = Join-Path $PackagingDir "tws-setup.iss"
    if (-not (Test-Path $issPath)) {
        throw "Inno Setup script not found: $issPath"
    }

    # Pass the repo root so the ISS can resolve relative paths.
    Invoke-Checked -Command $iscc -Arguments "`"$issPath`" /O`"$DistDir`"" -Phase "Inno Setup compile"

    # Find the produced setup exe (name includes version)
    $setupExe = Get-ChildItem -Path $DistDir -Filter "TWS-Setup-*.exe" |
                Sort-Object LastWriteTime -Descending |
                Select-Object -First 1
    if (-not $setupExe) {
        throw "Inno Setup did not produce a TWS-Setup-*.exe in $DistDir"
    }
    Write-Host "=== Inno Setup OK: $($setupExe.FullName) ===" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# 4. Summary
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== Build artifacts ===" -ForegroundColor Cyan
Get-ChildItem -Path $DistDir -Filter "tws-desktop*" | ForEach-Object {
    $size = "{0:N1} MB" -f ($_.Length / 1MB)
    Write-Host "  $($_.Name)  ($size)"
}
if (-not $SkipInno) {
    Get-ChildItem -Path $DistDir -Filter "TWS-Setup-*" | ForEach-Object {
        $size = "{0:N1} MB" -f ($_.Length / 1MB)
        Write-Host "  $($_.Name)  ($size)"
    }
}
Write-Host "=== Done ===" -ForegroundColor Green
