<#
.SYNOPSIS
    Vendor a self-contained Python runtime into the installer.

.DESCRIPTION
    Downloads the official Windows "embeddable package" into
    src-tauri\vendor\python and installs the bank's runtime requirements
    alongside it, so the shipped app depends on no Python already on the
    machine. That is the point of packaging this at all: an author on a
    locked-down laptop cannot create a venv, and telling them to install
    Python first is the wall this removes.

    Why the embeddable zip rather than PyInstaller: the suite standard
    (see the PDC Glossary Generator, whose driver set PyInstaller
    genuinely mishandles). A vendored tree is just files - what was tested
    is what ships - and one packaging recipe across these apps beats a
    second one that can drift.

    requirements-dev.txt is deliberately NOT installed. pytest cannot run
    inside a shipped app, and it is the reason that file exists.

    Idempotent - skips the download when the pinned version and the
    requirements hash are both already staged.

.PARAMETER Version
    Python version to vendor. Keep this on a version with wheels for
    every dependency.

.PARAMETER Force
    Re-download and rebuild even when the stamp matches.

.NOTES
    Windows PowerShell 5.1+. ASCII-only on purpose.
#>
[CmdletBinding()]
param(
    [string]$Version = "3.12.8",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$desktopDir = Split-Path -Parent $PSScriptRoot
$vendorDir  = Join-Path $desktopDir "src-tauri\vendor\python"
$stampFile  = Join-Path $vendorDir ".version"
$repoRoot   = Split-Path -Parent $desktopDir
$reqFile    = Join-Path $repoRoot "requirements.txt"

function Say($m)  { Write-Host "  $m" }
function Ok($m)   { Write-Host "  [ok] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!]  $m" -ForegroundColor Yellow }

Write-Host ""
Write-Host "  Vendoring Python $Version" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $reqFile)) {
    throw "requirements.txt not found at $reqFile"
}

# The stamp covers the runtime AND the requirements: a dependency added
# without a Python bump must still trigger a rebuild, or the installer
# silently ships the previous dependency set.
$reqHash = (Get-FileHash -LiteralPath $reqFile -Algorithm SHA256).Hash
$stamp = "$Version+$reqHash"

if ((-not $Force) -and (Test-Path -LiteralPath $stampFile)) {
    $existing = (Get-Content -LiteralPath $stampFile -Raw).Trim()
    if ($existing -eq $stamp) {
        Ok "already staged (Python $Version, requirements unchanged)"
        exit 0
    }
    Say "stamp differs - rebuilding"
}

if (Test-Path -LiteralPath $vendorDir) {
    Remove-Item -LiteralPath $vendorDir -Recurse -Force
}
New-Item -ItemType Directory -Path $vendorDir -Force | Out-Null

$zipName = "python-$Version-embed-amd64.zip"
$url = "https://www.python.org/ftp/python/$Version/$zipName"
$zipPath = Join-Path $env:TEMP $zipName

Say "downloading $url"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
Ok "downloaded ($([math]::Round((Get-Item $zipPath).Length / 1MB, 1)) MB)"

Expand-Archive -LiteralPath $zipPath -DestinationPath $vendorDir -Force
Remove-Item -LiteralPath $zipPath -Force
Ok "extracted to src-tauri\vendor\python"

# The embeddable distribution ships isolated: python*._pth lists the
# search path and comments out "import site", which disables
# site-packages entirely. Without this edit pip installs succeed and then
# nothing can be imported.
$pth = Get-ChildItem -LiteralPath $vendorDir -Filter "python*._pth" | Select-Object -First 1
if (-not $pth) { throw "no python*._pth in the embeddable package - layout changed?" }
$lines = Get-Content -LiteralPath $pth.FullName
$patched = $lines | ForEach-Object {
    if ($_ -match '^\s*#\s*import\s+site\s*$') { "import site" } else { $_ }
}
if ($patched -notcontains "Lib\site-packages") { $patched += "Lib\site-packages" }
Set-Content -LiteralPath $pth.FullName -Value $patched -Encoding ASCII
Ok "enabled site-packages in $($pth.Name)"

$py = Join-Path $vendorDir "python.exe"

# get-pip, because the embeddable package deliberately ships without it.
$getPip = Join-Path $env:TEMP "get-pip.py"
Say "installing pip"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip -UseBasicParsing
& $py $getPip --no-warn-script-location | Out-Null
if ($LASTEXITCODE -ne 0) { throw "get-pip failed" }
Remove-Item -LiteralPath $getPip -Force
Ok "pip installed"

Say "installing requirements (this takes a few minutes)"
& $py -m pip install --no-warn-script-location --disable-pip-version-check -r $reqFile
if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements.txt failed" }

# Prove every dependency the app actually reaches for resolves now,
# rather than discovering it on an author's machine. `multipart` is the
# one worth naming: nothing imports it directly, FastAPI needs it for the
# Import pane's upload, and it was missing from requirements.txt
# altogether until this packaging work went looking.
& $py -c "import sys, uvicorn, fastapi, multipart, httpx, anthropic, openai, fpdf, docx, openpyxl, PIL, dotenv; print('imports ok on Python ' + sys.version.split()[0])"
if ($LASTEXITCODE -ne 0) { throw "the vendored runtime cannot import the bank's dependencies" }

Set-Content -LiteralPath $stampFile -Value $stamp -Encoding ASCII
$size = [math]::Round(((Get-ChildItem -LiteralPath $vendorDir -Recurse -File |
        Measure-Object -Property Length -Sum).Sum / 1MB), 0)
Ok "vendored runtime ready - $size MB"
Write-Host ""

# pip leaves its own exit code behind, and PowerShell surfaces the LAST
# native exit code as the script's - so a successful run would look like
# a failure to npm and abort the tauri build.
exit 0
