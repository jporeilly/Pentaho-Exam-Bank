<#
.SYNOPSIS
    Check an INSTALLED Pentaho Exam Bank, after running the installer.

.DESCRIPTION
    Read-only. Changes nothing, installs nothing, needs no elevation -
    reading HKLM does not require it, and neither does starting the app.

    What it checks, and why each one is here rather than assumed:

      1. The registry key, in BOTH views. An NSIS installer is a 32-bit
         process so its writes land in WOW6432Node; the Content Editor's
         backend is 64-bit Python and reads the 64-bit view FIRST. Writing
         one view leaves the Questions button unable to find an install
         that is plainly there.

      2. The launcher's NAME. The editor looks for exactly
         pentaho-exam-bank.exe or exam-bank.exe inside the registered
         directory (api\peb.py, _INSTALL_SHAPES). Cargo's default from the
         package name was pentaho-exam-bank-desktop.exe, which matches
         neither - the key is found, the directory opened, and the bank
         reported as not installed.

      3. NOTHING PRIVATE IN THE INSTALL. The staging script's import check
         once copied this machine's own config.json - naming its Ollama
         model and MCP servers - and a database into the tree that becomes
         the installer. That is fixed; this proves it stayed fixed in the
         artefact somebody actually ran.

      4. The app starts, serves, and keeps its data OUT of the install.
         utils\config.py creates its directories at import off the package
         root, which under Program Files raises PermissionError before the
         app can say anything. The shell sets PEB_STATE_DIR to move them.

      5. The Content Editor's OWN discovery, run through its own code
         rather than reimplemented here. A check that agrees with itself
         proves nothing; this asks the thing that actually decides.

.PARAMETER SkipLaunch
    Do not start the app. Use when something else is already on its port,
    or to keep the check to a few milliseconds.

.PARAMETER InstallDir
    Check this directory instead of the one the registry names. Mirrors the
    Content Editor's own PEB_INSTALL_DIR override, which exists for the same
    two reasons: a portable copy, and being able to test the rest of these
    checks before a real install has written anything to HKLM.

.NOTES
    Windows PowerShell 5.1+. ASCII-only on purpose.
#>
[CmdletBinding()]
param(
    [switch]$SkipLaunch,
    [string]$InstallDir = $env:PEB_INSTALL_DIR
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$script:Failures = 0
$script:Warnings = 0

function Head($m) { Write-Host ""; Write-Host "  $m" -ForegroundColor Cyan }
function Pass($m) { Write-Host "  [ok]   $m" -ForegroundColor Green }
function Fail($m) { $script:Failures++; Write-Host "  [FAIL] $m" -ForegroundColor Red }
function Warn($m) { $script:Warnings++; Write-Host "  [warn] $m" -ForegroundColor Yellow }
function Note($m) { Write-Host "         $m" -ForegroundColor DarkGray }

$KeyPath = "SOFTWARE\Pentaho\ExamBank"
# The two names the Content Editor accepts, in its own order.
$Shapes  = @("pentaho-exam-bank.exe", "exam-bank.exe")

Write-Host ""
Write-Host "  Pentaho Exam Bank - installed copy" -ForegroundColor White

# --- 1. the discovery key, in both views ---------------------------------
Head "Registry"

function Read-View($view) {
    # Opened through the .NET API because PowerShell's HKLM: drive follows
    # the process's own bitness and cannot be pointed at the other view -
    # which is the entire thing being tested.
    $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey(
        [Microsoft.Win32.RegistryHive]::LocalMachine, $view)
    try {
        $key = $base.OpenSubKey($KeyPath)
        if (-not $key) { return $null }
        try { return $key.GetValue("") } finally { $key.Close() }
    } finally { $base.Close() }
}

# Named $registered, NOT $installDir: PowerShell variable names are
# case-insensitive, so $installDir IS the -InstallDir parameter, and
# assigning $null here destroyed the override before it could be read.
$registered = $null
foreach ($view in @([Microsoft.Win32.RegistryView]::Registry64,
                    [Microsoft.Win32.RegistryView]::Registry32)) {
    $value = Read-View $view
    $label = if ($view -eq [Microsoft.Win32.RegistryView]::Registry64) { "64-bit view" } else { "32-bit view" }
    if ($value) {
        Pass "$label -> $value"
        if (-not $registered) { $registered = $value }
    } else {
        Fail "$label has no HKLM\$KeyPath default value"
        Note "The Content Editor reads both; a missing view is a button that"
        Note "cannot find an install that is there."
    }
}

if ($InstallDir) {
    # An override does not make a missing key acceptable - the Content Editor
    # still reads the registry - so the failures above stand. It only says
    # which directory the remaining checks run against.
    if (-not (Test-Path -LiteralPath $InstallDir)) {
        Fail "InstallDir does not exist: $InstallDir"
        Write-Host ""
        exit 1
    }
    $target = (Resolve-Path -LiteralPath $InstallDir).Path
    Note "checking $target (override)"
} elseif ($registered) {
    $target = $registered
} else {
    Fail "No install registered. Run the installer first."
    Write-Host ""
    exit 1
}
if (-not (Test-Path -LiteralPath $target)) {
    Fail "The key points at $target, which does not exist"
    Write-Host ""
    exit 1
}

# --- 2. the launcher's name ----------------------------------------------
Head "Launcher"

$launcher = $null
foreach ($shape in $Shapes) {
    $candidate = Join-Path $target $shape
    if (Test-Path -LiteralPath $candidate) { $launcher = $candidate; break }
}
if ($launcher) {
    Pass "$(Split-Path -Leaf $launcher) - a name the Content Editor accepts"
} else {
    Fail "No launcher the Content Editor recognises in $target"
    Note "It accepts: $($Shapes -join ', ')"
    Note "Present instead: $((Get-ChildItem -LiteralPath $target -Filter *.exe |
          Select-Object -ExpandProperty Name) -join ', ')"
}

foreach ($must in @("app\boot.py",
                    "app\exam_bank\api\app.py",
                    "app\frontend\dist\index.html",
                    "python\python.exe")) {
    if (Test-Path -LiteralPath (Join-Path $target $must)) {
        Pass $must
    } else {
        Fail "$must is missing from the install"
    }
}

# --- 3. nothing private shipped ------------------------------------------
Head "Nothing private in the install"

$leaked = @()
foreach ($never in @("app\assets", "app\.env", "app\exam_bank\gui", "app\venv")) {
    if (Test-Path -LiteralPath (Join-Path $target $never)) { $leaked += $never }
}
# A database or a config anywhere under app\ is somebody else's data.
#
# Filtered with Where-Object, not -Include: -Include is ignored unless the
# PATH itself ends in a wildcard, so with -LiteralPath it silently matches
# EVERY file. The first version of this check reported all 59 files in the
# install as private data, which is exactly as useless as reporting none.
$strays = @(Get-ChildItem -LiteralPath (Join-Path $target "app") -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -eq ".db" -or $_.Name -eq "config.json" -or $_.Name -eq ".env" })
if ($leaked.Count -eq 0 -and $strays.Count -eq 0) {
    Pass "no database, config or environment file shipped"
} else {
    foreach ($l in $leaked) { Fail "$l is in the install" }
    foreach ($s in $strays) { Fail "$($s.FullName) is in the install" }
    Note "The build machine's own settings reached the installer once before."
}

# --- 4. it starts, serves, and writes elsewhere --------------------------
if (-not $SkipLaunch) {
    Head "Starting it"

    if (-not $launcher) {
        Warn "skipped - no launcher to start"
    } else {
        $before = @(Get-Process -Name "pentaho-exam-bank" -ErrorAction SilentlyContinue |
                    Select-Object -ExpandProperty Id)
        # The backends running BEFORE this script touched anything. Without
        # this the orphan check below counts every backend from this install
        # - including the copy the user has open on their own screen - and
        # reports a working job object as a leak. It did exactly that the
        # first time the app was running during a verify.
        $beforeBackends = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
                            Where-Object { $_.CommandLine -and $_.CommandLine -like "*$target*boot.py*" } |
                            Select-Object -ExpandProperty ProcessId)
        if ($beforeBackends.Count -gt 0) {
            Note "$($beforeBackends.Count) backend(s) from this install were already running; not ours to judge"
        }
        Start-Process -FilePath $launcher | Out-Null

        # The port is chosen free at launch, so it is discovered from the
        # backend's command line rather than guessed.
        $port = $null
        $deadline = (Get-Date).AddSeconds(60)
        while ((Get-Date) -lt $deadline -and -not $port) {
            Start-Sleep -Milliseconds 700
            $cmd = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
                   Where-Object { $_.CommandLine -and $_.CommandLine -like "*$target*boot.py*" } |
                   Select-Object -First 1 -ExpandProperty CommandLine
            if ($cmd -and $cmd -match "--port\s+(\d+)") { $port = [int]$Matches[1] }
        }

        if (-not $port) {
            Fail "the backend never started (no boot.py process appeared)"
        } else {
            Pass "backend started on port $port using the vendored runtime"

            $health = $null
            $deadline = (Get-Date).AddSeconds(60)
            while ((Get-Date) -lt $deadline -and -not $health) {
                Start-Sleep -Milliseconds 700
                try {
                    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 3
                } catch { $health = $null }
            }

            if (-not $health) {
                Fail "it never answered on http://127.0.0.1:$port"
            } else {
                Pass "answering - version $($health.version)"

                # Kept for the courses section below, which runs after the
                # app has been closed again. Asked of the APP rather than read
                # out of the SQLite file: the app is the thing whose opinion
                # matters, and opening its database behind its back is how a
                # verifier ends up reporting on a file nobody uses.
                $script:bankQuestions = [int]$health.database.questions
                $script:bankCerts = [int]$health.database.certifications

                $dbPath = [string]$health.database.path
                if ($dbPath.ToLower().StartsWith($target.ToLower())) {
                    Fail "the database is INSIDE the install: $dbPath"
                    Note "Program Files is read-only for a normal user; this will"
                    Note "fail for anyone who is not an administrator."
                } else {
                    Pass "database outside the install - $dbPath"
                }

                try {
                    $root = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -TimeoutSec 5 -UseBasicParsing
                    if ($root.StatusCode -eq 200) {
                        Pass "the interface is served at the root"
                    } else {
                        Fail "the root returned $($root.StatusCode) - the front end was not staged"
                    }
                } catch {
                    Fail "the root did not respond - the front end was not staged"
                }
            }
        }

        # Leave the machine as it was found, and check the job object did its
        # job: killing the shell must take uvicorn with it.
        Get-Process -Name "pentaho-exam-bank" -ErrorAction SilentlyContinue |
            Where-Object { $before -notcontains $_.Id } |
            Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        $orphans = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
                     Where-Object { $_.CommandLine -and $_.CommandLine -like "*$target*boot.py*" } |
                     Where-Object { $beforeBackends -notcontains $_.ProcessId })
        if ($orphans.Count -eq 0) {
            Pass "closing it stopped the backend too"
        } else {
            Fail "$($orphans.Count) backend process(es) outlived the shell"
            Note "The kill-on-close job object is not holding; the next launch"
            Note "will find the port and the database still locked."
        }
    }
}

# --- 5. is this actually the build that was just made? -------------------
#
# Added after the script said "Everything checked out" about an install that
# was a day old and did not contain the feature being verified. Every check
# above passed honestly - they were all true of the OLD install. A verifier
# that cannot tell you WHICH build it just blessed is an instrument that
# reports on the wrong subject with total confidence.
#
# The reference is the launcher INSIDE the collected installer, not the one
# in target\release. The first version of this check compared against
# target\release and failed a perfectly correct install: Tauri REWRITES
# that file around bundling (same size, different bytes), so by the time a
# build finishes it no longer matches what the installer actually carries.
# A check proved able to fail but never proved able to pass is only half
# tested, and this was the half that was missing.
#
# Reading the launcher out of an NSIS archive needs 7-Zip. Where it is
# absent the check says so and skips, rather than pretending.
$distDir = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "dist"
$setup = $null
if (Test-Path -LiteralPath $distDir) {
    $setup = Get-ChildItem -LiteralPath $distDir -Filter "*-setup.exe" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
}
if ($setup -and $launcher) {
    Head "Which build is installed"
    $sevenZip = @(
        (Get-Command 7z -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        "$env:ProgramFiles\7-Zip\7z.exe"
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1

    if (-not $sevenZip) {
        Note "skipped - 7-Zip is needed to read the launcher out of $($setup.Name)"
    } else {
        $tmp = Join-Path $env:TEMP "peb-verify-$PID"
        New-Item -ItemType Directory -Path $tmp -Force | Out-Null
        try {
            & $sevenZip e -y -o"$tmp" $setup.FullName "pentaho-exam-bank.exe" | Out-Null
            $packaged = Join-Path $tmp "pentaho-exam-bank.exe"
            if (-not (Test-Path -LiteralPath $packaged)) {
                Warn "could not read the launcher out of $($setup.Name)"
            } elseif ((Get-FileHash -LiteralPath $packaged -Algorithm SHA256).Hash -eq
                      (Get-FileHash -LiteralPath $launcher -Algorithm SHA256).Hash) {
                Pass "the installed launcher is the one in $($setup.Name)"
            } else {
                Fail "the installed launcher is NOT the one in $($setup.Name)"
                Note "installed : $((Get-Item -LiteralPath $launcher).LastWriteTime)"
                Note "installer : $($setup.LastWriteTime)"
                Note "Every check above is true of the OLDER build. Run that"
                Note "installer and verify again."
            }
        } finally {
            Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

# --- 6. the courses the app will open on ---------------------------------
#
# The reason this section exists: the first install came up with every
# pane empty because the app's only rule for finding courses was "look for
# a sibling directory", which cannot hold under Program Files. The
# installer now searches, and a search that silently stopped running would
# look exactly like a machine that has no courses on it.
Head "Content Manager courses"

$prov = Join-Path $target "provisioning\find-courses.ps1"
if (Test-Path -LiteralPath $prov) {
    Pass "provisioning\find-courses.ps1 shipped"
} else {
    Fail "provisioning\find-courses.ps1 is not in the install"
    Note "The POSTINSTALL hook runs this by path; without it the hook is a"
    Note "no-op and the app falls back to asking in Settings."
}

# PcmRepo is written by that script, in the 64-bit view. Read both anyway:
# if it ever appears only in the 32-bit view, the 64-bit Python that reads
# it would not see it, and a silent half-write is worth a failure.
function Read-Hint($view) {
    $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey(
        [Microsoft.Win32.RegistryHive]::LocalMachine, $view)
    try {
        $key = $base.OpenSubKey($KeyPath)
        if (-not $key) { return $null }
        try { return $key.GetValue("PcmRepo") } finally { $key.Close() }
    } finally { $base.Close() }
}

$hint = Read-Hint ([Microsoft.Win32.RegistryView]::Registry64)
if (-not $hint) { $hint = Read-Hint ([Microsoft.Win32.RegistryView]::Registry32) }

if ($hint) {
    $coursesDir = Join-Path $hint "courses"
    $n = @(Get-ChildItem -LiteralPath $coursesDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "course.json") }).Count
    if ($n -gt 0) {
        Pass "the installer found $n course(s) - $hint"
    } else {
        # Recorded but useless. Worse than nothing: the app reports itself
        # configured and then finds no courses.
        Fail "PcmRepo points at $hint, which has no courses"
    }
} else {
    # NOT a failure. A machine with no Content Manager on it is a perfectly
    # valid install, and the app asks in Settings. Stated plainly so the
    # difference between "searched and found nothing" and "never searched"
    # is visible rather than inferred.
    Warn "no Content Manager checkout was recorded"
    Note "Fine if there is none on this machine - the app will ask in"
    Note "Settings. To see what the search itself finds:"
    Note "  powershell -File `"$prov`" -ReportOnly"
}

# Did the bank actually FILL? Added because this script twice reported an
# install perfect while saying nothing about the feature the release existed
# for. Finding the courses is the means; having the questions is the point,
# and the two are separately capable of failing.
if ($null -ne $script:bankQuestions) {
    if ($script:bankQuestions -gt 0) {
        Pass "the bank holds $($script:bankQuestions) question(s) across $($script:bankCerts) certification(s)"
    } elseif ($hint) {
        Fail "the bank is EMPTY although $hint was found"
        Note "A new install adopts the courses on first launch. An empty bank"
        Note "next to a found checkout means that did not happen - check the"
        Note "app log for 'First-run course adoption did not run'."
    } else {
        Note "the bank is empty, which is expected with no courses on this machine"
    }
}

# --- 7. the Content Editor's own verdict ---------------------------------
Head "The Content Editor's Questions button"

$editorRoots = @(
    (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "..\Pentaho-Content-Editor"),
    "C:\Projects\Pentaho-Content-Editor"
) | ForEach-Object { try { (Resolve-Path -LiteralPath $_ -ErrorAction Stop).Path } catch { $null } } |
    Where-Object { $_ } | Select-Object -Unique

$asked = $false
foreach ($root in $editorRoots) {
    $py = Join-Path $root "api\.venv\Scripts\python.exe"
    $peb = Join-Path $root "api\peb.py"
    if (-not (Test-Path -LiteralPath $py) -or -not (Test-Path -LiteralPath $peb)) { continue }

    # Its own code, not a reimplementation of it. A check that agrees with
    # itself proves nothing.
    #
    # peb.py sits in api\ and imports its siblings flatly (import core), so
    # that directory goes on sys.path exactly as the editor's own uvicorn
    # arranges with --app-dir. Without it this is a ModuleNotFoundError that
    # says nothing about the install.
    $apiDir = Join-Path $root "api"
    $probe = "import sys, json; sys.path.insert(0, sys.argv[1]); import peb; print(json.dumps(peb.status()))"
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = & $py -c $probe $apiDir 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    $asked = $true

    if ($code -ne 0) {
        Warn "could not ask the editor ($root)"
        $out | ForEach-Object { Note $_ }
        continue
    }
    try {
        $verdict = ("$out" | ConvertFrom-Json)
    } catch {
        Warn "the editor's answer was not JSON: $out"
        continue
    }

    if ($verdict.kind -eq "installed") {
        Pass "the editor finds it: $($verdict.detail)"
    } elseif ($verdict.kind -eq "checkout") {
        Warn "the editor is using the CHECKOUT, not the install"
        Note $verdict.detail
        Note "An install should win. Check the registry key above."
    } elseif ($verdict.kind -eq "broken") {
        Fail $verdict.detail
    } else {
        Fail "the editor cannot find the Exam Bank at all"
        Note $verdict.detail
    }
    break
}
if (-not $asked) {
    Warn "no Content Editor checkout found - skipped"
    Note "This is the check that matters most; run it where the editor is."
}

# --- verdict -------------------------------------------------------------
Write-Host ""
if ($script:Failures -eq 0 -and $script:Warnings -eq 0) {
    Write-Host "  Everything checked out." -ForegroundColor Green
} elseif ($script:Failures -eq 0) {
    Write-Host "  No failures, $($script:Warnings) warning(s)." -ForegroundColor Yellow
} else {
    Write-Host "  $($script:Failures) failure(s), $($script:Warnings) warning(s)." -ForegroundColor Red
}
Write-Host ""

exit ([math]::Min($script:Failures, 1))
