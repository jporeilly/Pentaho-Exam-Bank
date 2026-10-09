"""How the seeded installer is wired into the packaging.

`npm run dist:seeded` adds the course text from stage-seed.mjs to the
installer. These pin the three things that keep that from leaking into the
plain installer or lingering after an uninstall. None can be proved by
building here - the installer is Windows-only - so they pin the wiring.
"""

import json
from pathlib import Path

DESKTOP = Path(__file__).resolve().parents[1] / "desktop"
CONF = json.loads((DESKTOP / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
SEEDED = json.loads((DESKTOP / "src-tauri" / "tauri.seeded.conf.json").read_text(encoding="utf-8"))
PKG = json.loads((DESKTOP / "package.json").read_text(encoding="utf-8"))
HOOKS = (DESKTOP / "src-tauri" / "nsis" / "hooks.nsh").read_text(encoding="utf-8")
COLLECT = (DESKTOP / "scripts" / "collect-installer.ps1").read_text(encoding="utf-8")


def test_the_seed_is_an_overlay_and_the_plain_installer_carries_none():
    assert "vendor/seed" not in CONF["bundle"]["resources"]
    assert SEEDED["bundle"]["resources"] == {"vendor/seed": "seed"}


def test_dist_seeded_stages_the_seed_before_it_bundles():
    dist = PKG["scripts"]["dist:seeded"]
    assert dist.index("stage:app") < dist.index("stage:seed") < dist.index("tauri:build:seeded")
    assert "tauri.seeded.conf.json" in PKG["scripts"]["tauri:build:seeded"]
    assert "-Suffix seeded" in PKG["scripts"]["collect:seeded"]


def test_the_seeded_installer_gets_its_own_file_name():
    # Or it overwrites the plain installer of the same version in dist\.
    assert '[string]$Suffix = ""' in COLLECT
    assert "-$Suffix-setup.exe" in COLLECT
    # The sidecar checksum must name the file it sits beside.
    assert 'Value "$hash  $finalName"' in COLLECT


def test_the_install_tree_copy_goes_on_upgrade_and_uninstall_but_the_authors_does_not():
    pre = HOOKS[HOOKS.index("NSIS_HOOK_PREINSTALL"):HOOKS.index("NSIS_HOOK_POSTINSTALL")]
    post = HOOKS[HOOKS.index("NSIS_HOOK_POSTUNINSTALL"):]
    assert 'RMDir /r "$INSTDIR\\seed"' in pre
    assert 'RMDir /r "$INSTDIR\\seed"' in post
    # What the author works in lives under %APPDATA%; neither hook may touch it.
    assert "$APPDATA" not in pre + post
