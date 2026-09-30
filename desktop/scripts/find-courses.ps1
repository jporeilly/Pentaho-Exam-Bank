<#
.SYNOPSIS
    Record a Pentaho Content Manager checkout found on this machine.

.DESCRIPTION
    Run by the installer. The Exam Bank generates questions FROM a Content
    Manager course and publishes them back into one, so without a courses
    directory it opens with nothing to do and no way to say why - which is
    exactly what the first install did.

    Written to HKLM, and that is forced rather than lazy. The installer runs
    ELEVATED, so its %APPDATA% belongs to the elevating account, which on a
    managed laptop is an admin who will never run this app. A machine-wide
    hint that the app reads as a CANDIDATE is the honest way round it: the app
    still decides, and the author can still change it in Settings.

    The VALUE is the repo root, not the courses directory, because that is
    what the Content Editor already stores under its own key. One search per
    machine then answers for both apps, and the bank reads the editor's hint
    when only the editor has been installed.

    Finds nothing? Exit 1, quietly. The app falls back to PCM_REPO, to the
    editor's hint, and to a sibling checkout, and Settings has a field for it.
    This is an optimisation, never a requirement, and it must never fail an
    install.

.NOTES
    Windows PowerShell 5.1+. ASCII-only on purpose.
#>
[CmdletBinding()]
param(
    [string]$KeyPath = "SOFTWARE\Pentaho\ExamBank",
    # Report what the search found and write nothing. The write needs
    # elevation, which the installer has and a developer checking this
    # script does not - without a way to run the search alone, the only
    # way to test it is to install.
    [switch]$ReportOnly,
    # Search these roots instead of the list below. For tests: the default
    # list includes C:\Projects, so a test run against it passes or fails on
    # whatever checkouts this machine happens to hold.
    [string[]]$Roots
)

# Deliberately NOT "Stop". A provisioning step that throws takes the install
# with it, and the worst this can legitimately do is find nothing.
$ErrorActionPreference = "Continue"

# One level deep, and only these roots. A recursive hunt across a home
# directory is how an installer ends up waiting on OneDrive or a mapped drive
# while the user watches a progress bar that has stopped.
if (-not $Roots) {
    $Roots = @(
        "C:\Projects",
        (Join-Path $env:USERPROFILE "Projects"),
        (Join-Path $env:USERPROFILE "source\repos"),
        (Join-Path $env:USERPROFILE "git"),
        (Join-Path $env:USERPROFILE "Documents"),
        $env:USERPROFILE
    )
}
$Roots = @($Roots | Where-Object { $_ -and (Test-Path -LiteralPath $_) })

function Test-Checkout($path) {
    # courses/ is the whole requirement. The bank reads course.json and the
    # lab guides and writes exam.json; it never calls the authoring scripts,
    # so a content-only clone is perfectly usable and refusing one would
    # trade a working app for a tidier check.
    $courses = Join-Path $path "courses"
    if (-not (Test-Path -LiteralPath $courses)) { return $null }
    $count = @(Get-ChildItem -LiteralPath $courses -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "course.json") }).Count
    if ($count -eq 0) { return $null }
    # A git worktree has a .git FILE ("gitdir: ...") where a main checkout
    # has a .git directory. A worktree is a branch in flight - on the dev
    # machine, an unmerged release that predates a course rename - so it
    # ranks below any main checkout. A copy with no .git at all is not a
    # worktree: courses/ is still the whole requirement.
    $worktree = Test-Path -LiteralPath (Join-Path $path ".git") -PathType Leaf
    return [pscustomobject]@{ Path = $path; Courses = $count; Worktree = $worktree }
}

$found = @()
foreach ($root in $Roots) {
    # The obvious name first, then anything else one level down that happens
    # to hold courses - a clone renamed on checkout is common.
    $named = Join-Path $root "Pentaho-Content-Manager"
    if (Test-Path -LiteralPath $named) {
        $hit = Test-Checkout $named
        if ($hit) { $found += $hit }
    }
    try {
        foreach ($child in (Get-ChildItem -LiteralPath $root -Directory -ErrorAction Stop |
                            Select-Object -First 120)) {
            if ($child.Name.StartsWith(".")) { continue }
            if ($child.FullName -eq $named) { continue }
            $hit = Test-Checkout $child.FullName
            if ($hit) { $found += $hit }
        }
    } catch {
        continue   # unreadable root: skip it, never fail the install
    }
}

# A main checkout beats a worktree whatever the counts; then the most courses
# wins; among equals, the first found. That last key is spelled out because
# Sort-Object in Windows PowerShell 5.1 is not stable: without it a tie went
# to whichever candidate the sort left on top, which on the dev machine was
# the worktree.
for ($i = 0; $i -lt $found.Count; $i++) {
    $found[$i] | Add-Member -NotePropertyName Order -NotePropertyValue $i
}
$best = $found | Sort-Object -Property @(
    @{ Expression = { $_.Worktree } },
    @{ Expression = { -$_.Courses } },
    @{ Expression = { $_.Order } }
) | Select-Object -First 1

if (-not $best) {
    Write-Host "No Content Manager courses found - the Exam Bank will ask in Settings."
    exit 1
}

# Say what was passed over, so an install log explains a choice that looks
# wrong next to a checkout with more courses.
if (-not $best.Worktree) {
    foreach ($skipped in @($found | Where-Object { $_.Worktree })) {
        Write-Host "Passed over git worktree $($skipped.Path) ($($skipped.Courses) courses)."
    }
}

if ($ReportOnly) {
    Write-Host "Would record $($best.Path) ($($best.Courses) courses) under HKLM\$KeyPath"
    exit 0
}

try {
    # The 64-bit view explicitly. This script is launched by a 32-bit NSIS
    # process, so a plain HKLM:\SOFTWARE write is redirected into
    # WOW6432Node - where a 64-bit reader looking only at the native view
    # will not see it.
    $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey(
        [Microsoft.Win32.RegistryHive]::LocalMachine,
        [Microsoft.Win32.RegistryView]::Registry64)
    $key = $base.CreateSubKey($KeyPath)
    $key.SetValue("PcmRepo", $best.Path)
    $key.Close()
    $base.Close()
    Write-Host "Content Manager found at $($best.Path) ($($best.Courses) courses)."
    exit 0
} catch {
    Write-Host "Could not record the Content Manager location: $_"
    exit 1
}
