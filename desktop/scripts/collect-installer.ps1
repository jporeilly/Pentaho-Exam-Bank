<#
.SYNOPSIS
    Copy the freshly built installer out of Tauri's nested output into dist\.

.DESCRIPTION
    Tauri leaves the installer at

        desktop\src-tauri\target\release\bundle\nsis\<name>_<version>_x64-setup.exe

    which is a long path inside build output that `cargo clean` will happily
    delete. This copies it to dist\ at the repo root - the same short,
    memorable path every app in this suite collects to.

    VERSIONED, and deliberately so. The filename Tauri produces carries the
    version, and this keeps it, so builds accumulate side by side rather than
    overwriting each other: you can hand someone 0.1.0 while 0.2.0 is being
    tested, and an installer that is "the one from Tuesday" is identifiable
    without opening it. The version comes from tauri.conf.json.

    A sidecar .sha256 goes beside each one. An installer is 38 MB of
    executable that people are asked to run as administrator; being able to
    say what was built, and to check a copy is that, is worth two lines.

    WHY dist\ AT THE REPO ROOT and not somewhere under desktop\: the two
    other dist folders here are inputs to the build. frontend\dist is the
    React bundle that stage-app.ps1 packages, and desktop\dist is the Tauri
    startup page. The Content Editor put its installers in its Vite output
    once and shipped a 29 MB copy of the installer INSIDE the installer,
    found only by listing the artifact. Nothing stages the repo root, so
    this folder cannot be swallowed the same way.

.NOTES
    Windows PowerShell 5.1+. ASCII-only on purpose.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$desktopDir = Split-Path -Parent $PSScriptRoot
$repoRoot   = Split-Path -Parent $desktopDir
$nsisDir    = Join-Path $desktopDir "src-tauri\target\release\bundle\nsis"
$distDir    = Join-Path $repoRoot "dist"

function Ok($m)   { Write-Host "  [ok] $m" -ForegroundColor Green }
function Say($m)  { Write-Host "  $m" }

Write-Host ""
Write-Host "  Collecting the installer" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $nsisDir)) {
    throw "no bundle output at $nsisDir - run 'npm run tauri:build' first"
}

$exe = Get-ChildItem -LiteralPath $nsisDir -Filter "*-setup.exe" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $exe) {
    throw "no *-setup.exe in $nsisDir - run 'npm run tauri:build' first"
}

# The built installer must match the version the config declares. They come
# apart when tauri.conf.json is bumped and the build is not re-run, which
# hands someone an installer whose name says one thing and whose contents say
# another - the kind of mistake that is only found much later, by whoever is
# trying to reproduce a bug.
$conf = Get-Content -LiteralPath (Join-Path $desktopDir "src-tauri\tauri.conf.json") -Raw | ConvertFrom-Json
$declared = $conf.version
if ($exe.Name -notmatch [regex]::Escape("_${declared}_")) {
    throw ("the newest installer is $($exe.Name) but tauri.conf.json declares " +
           "$declared - rebuild before collecting")
}

New-Item -ItemType Directory -Force -Path $distDir | Out-Null
$final = Join-Path $distDir $exe.Name
Copy-Item -LiteralPath $exe.FullName -Destination $final -Force

$hash = (Get-FileHash -LiteralPath $final -Algorithm SHA256).Hash
Set-Content -LiteralPath "$final.sha256" -Value "$hash  $($exe.Name)" -Encoding ASCII

$size = [math]::Round((Get-Item -LiteralPath $final).Length / 1MB, 1)
Ok "$($exe.Name) - $size MB"
Say "sha256  $hash"
Say "path    $final"

$others = @(Get-ChildItem -LiteralPath $distDir -Filter "*-setup.exe" |
            Where-Object { $_.Name -ne $exe.Name } |
            Sort-Object LastWriteTime -Descending)
if ($others.Count -gt 0) {
    Write-Host ""
    Say "also in dist\:"
    $others | ForEach-Object {
        Say ("  {0}  ({1} MB, {2})" -f $_.Name,
             [math]::Round($_.Length / 1MB, 1),
             $_.LastWriteTime.ToString("yyyy-MM-dd HH:mm"))
    }
}
Write-Host ""

exit 0
