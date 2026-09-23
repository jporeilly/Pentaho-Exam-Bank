<#
.SYNOPSIS
    Stage the Python backend + built React UI for bundling.

.DESCRIPTION
    Copies exam_bank\ and frontend\dist\ into src-tauri\vendor\app, which
    tauri.conf.json's bundle.resources maps to "app" inside the install.

    The staged tree MIRRORS the repo layout:

        app\boot.py               (desktop launcher - see desktop\boot.py)
        app\exam_bank\api\app.py
        app\frontend\dist\index.html

    That is not cosmetic. api\app.py resolves the built UI as
    parents[2]\frontend\dist - two levels above itself - so flattening the
    tree would leave the server running with no interface to serve, which
    looks exactly like a crash and is not one.

    What must NOT ship, and why each one is listed:

      assets        the author's own question bank, its backups, and a
                    config.json naming their provider, model and courses
                    directory. A second author would inherit the first
                    one's setup - and on the first run of this script,
                    did: see Assert-NothingPrivate below.
      .env          environment overrides, same reason.
      venv          the dev environment. The staged tree runs on the
                    VENDORED runtime; a bundled dev venv is tens of
                    megabytes of the wrong Python. The PDC Policy
                    installer shipped exactly that for four releases
                    because nobody listed the artifact.
      __pycache__   bytecode the installer never shipped is a file the
                    uninstaller leaves behind.
      gui           deleted in Phase 3, but excluded anyway: a stale
                    checkout on a build machine would otherwise ship
                    10,000 lines of dead NiceGUI.
      test_*.py     the tests import pytest, which is deliberately not in
                    the vendored runtime - they could never run there.

.NOTES
    Windows PowerShell 5.1+. ASCII-only on purpose.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
# Without this an undefined variable expands to empty and robocopy just
# returns exit 16 - which is how a staging destination silently became "".
Set-StrictMode -Version Latest

$desktopDir = Split-Path -Parent $PSScriptRoot
$repoRoot   = Split-Path -Parent $desktopDir
$srcPkg     = Join-Path $repoRoot "exam_bank"
$srcUi      = Join-Path $repoRoot "frontend\dist"
$stageDir   = Join-Path $desktopDir "src-tauri\vendor\app"
$stagePkg   = Join-Path $stageDir "exam_bank"
$stageUi    = Join-Path $stageDir "frontend\dist"

function Ok($m)   { Write-Host "  [ok] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!]  $m" -ForegroundColor Yellow }

# Prove nothing private or environmental is in the staged tree.
#
# Called TWICE - after copying, and again after the import check - because
# the check itself creates files. Importing utils\config.py builds its
# directories at import AND runs a migration that copies
# ~\.question_bank\ into them, so the first version of this script staged
# the build machine's own config.json (its Ollama model, its MCP servers)
# and a database into the installer. Asserting only before the probe could
# never have caught it.
function Assert-NothingPrivate($when) {
    foreach ($never in @((Join-Path $stageDir "assets"),
                         (Join-Path $stageDir ".env"),
                         (Join-Path $stagePkg "gui"),
                         (Join-Path $stagePkg "venv"))) {
        if (Test-Path -LiteralPath $never) {
            throw "$never reached the staging tree ($when) - fix the exclude list"
        }
    }
}

Write-Host ""
Write-Host "  Staging the app" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath (Join-Path $srcPkg "api\app.py"))) {
    throw "exam_bank\api\app.py not found - is $repoRoot the repo root?"
}
if (-not (Test-Path -LiteralPath (Join-Path $srcUi "index.html"))) {
    throw "frontend\dist\index.html not found - run 'npm run build' in frontend\ first"
}

if (Test-Path -LiteralPath $stageDir) { Remove-Item -LiteralPath $stageDir -Recurse -Force }
New-Item -ItemType Directory -Path $stageDir -Force | Out-Null

# robocopy: mirror of a clean tree. Exit codes 0-7 are success (8+ is a
# real failure) - a quirk worth pinning, because treating any non-zero as
# failure makes every build look broken.
#
# /XD names are RELATIVE on purpose: an absolute path matches only the
# top-level directory, so any subpackage __pycache__ from the dev checkout
# would ship into Program Files, where the uninstaller leaves it behind
# (found on PDC-Insights 1.17.0).
& robocopy $srcPkg $stagePkg "/E" "/NFL" "/NDL" "/NJH" "/NJS" "/NP" `
    "/XD" "__pycache__" ".pytest_cache" "venv" ".venv" "gui" `
    "/XF" "test_*.py" | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed staging exam_bank (exit $LASTEXITCODE)" }

# /XF *.exe: the UI is HTML, CSS and JavaScript. Anything executable in
# there arrived by accident - as a collected installer did once, when the
# UI and the installers shared dist\, putting a 29 MB copy of the
# installer inside the installer.
& robocopy $srcUi $stageUi "/E" "/NFL" "/NDL" "/NJH" "/NJS" "/NP" "/XF" "*.exe" | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed staging the UI (exit $LASTEXITCODE)" }

# boot.py puts the app root on sys.path before importing the package. The
# embeddable runtime's ._pth replaces sys.path outright, so without this
# the server cannot import exam_bank whatever directory it is given.
Copy-Item -LiteralPath (Join-Path $desktopDir "boot.py") -Destination (Join-Path $stageDir "boot.py") -Force

# The documentation the AI & Docs pane reads. core\docs.py loads these
# from PROJECT_ROOT, which inside an install is the app root - so without
# them that pane is empty and says the app has no documentation.
foreach ($doc in @("HOW_TO_GUIDE.md", "README.md", "CHANGELOG.md")) {
    $src = Join-Path $repoRoot $doc
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $stageDir $doc) -Force
    } else {
        Warn "$doc is missing - the AI & Docs pane will not find it"
    }
}

Assert-NothingPrivate "after copying"

# The paths the shell and the server actually depend on. Assert them here,
# where the fix is obvious, rather than at first launch on someone else's
# laptop.
foreach ($must in @((Join-Path $stagePkg "api\app.py"),
                    (Join-Path $stagePkg "api\routers\questions.py"),
                    (Join-Path $stagePkg "core\bank.py"),
                    (Join-Path $stagePkg "core\publisher.py"),
                    (Join-Path $stagePkg "utils\config.py"),
                    (Join-Path $stageUi  "index.html"),
                    (Join-Path $stageDir "boot.py"))) {
    if (-not (Test-Path -LiteralPath $must)) { throw "staging incomplete: $must is missing" }
}

# Prove the staged tree can actually be imported, using the runtime that
# will ship with it. File-existence checks cannot catch a module excluded
# by mistake; this can, and it costs a couple of seconds.
$vendorPy = Join-Path $desktopDir "src-tauri\vendor\python\python.exe"
if (Test-Path -LiteralPath $vendorPy) {
    $probe = "import sys; sys.path.insert(0, sys.argv[1]); import exam_bank.api.app as a; print('import ok, ui mounted:', a.UI_MOUNTED)"
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    # PEB_STATE_DIR sends everything this import WRITES to a scratch
    # directory - see Assert-NothingPrivate for what happened without it.
    $prevState = $env:PEB_STATE_DIR
    $env:PEB_STATE_DIR = Join-Path $env:TEMP "peb-stage-check"
    # -B: do NOT write bytecode. Without it this check compiles
    # __pycache__ into the tree robocopy just finished excluding it from,
    # and those .pyc files then ship.
    $out = & $vendorPy -B -c $probe $stageDir 2>&1
    $code = $LASTEXITCODE
    $env:PEB_STATE_DIR = $prevState
    $ErrorActionPreference = $prevEap
    if ($code -ne 0) {
        $out | ForEach-Object { Warn $_ }
        throw "the staged tree cannot import exam_bank.api.app - a module is missing from the stage"
    }
    # The UI mount is the difference between a working install and one that
    # 404s at its own root, so the probe reports it and this checks it
    # rather than only that the import succeeded.
    if ("$out" -notmatch "ui mounted:\s*True") {
        $out | ForEach-Object { Warn $_ }
        throw "the staged tree imports but does not mount the UI - frontend\dist is in the wrong place"
    }
    Get-ChildItem -LiteralPath $stageDir -Recurse -Directory -Filter "__pycache__" |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
    Ok "staged tree imports cleanly and mounts the UI on the vendored runtime"
} else {
    Warn "no vendored runtime yet - skipping the import check (run fetch:python first)"
}

Assert-NothingPrivate "after the import check"

$count = (Get-ChildItem -LiteralPath $stageDir -Recurse -File).Count
$size = [math]::Round(((Get-ChildItem -LiteralPath $stageDir -Recurse -File |
        Measure-Object -Property Length -Sum).Sum / 1MB), 1)
Ok "staged $count file(s), $size MB to src-tauri\vendor\app"
Write-Host ""

# robocopy returns 1 for "files were copied" and PowerShell surfaces the
# LAST native exit code as the script's, so a successful run would look
# like a failure to npm and abort the tauri build.
exit 0
