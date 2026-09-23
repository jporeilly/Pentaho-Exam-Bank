"""Where the app writes, as opposed to where its code lives.

These are the same directory in a checkout and different ones in an install,
and `config.py` creates its directories at IMPORT — so getting it wrong is not
a degraded feature, it is a `PermissionError` three frames into pathlib before
the app can say anything at all.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from exam_bank.utils import config

REPO = Path(__file__).resolve().parents[1]


def test_a_checkout_keeps_its_assets_directory(monkeypatch):
    """Unset is every development machine, and must behave exactly as before."""
    monkeypatch.delenv("PEB_STATE_DIR", raising=False)

    assert config.state_dir() == config.PROJECT_ROOT / "assets"


def test_the_environment_can_move_it(monkeypatch, tmp_path):
    """How an install points this at %LOCALAPPDATA%."""
    monkeypatch.setenv("PEB_STATE_DIR", str(tmp_path / "state"))

    assert config.state_dir() == tmp_path / "state"


def test_whitespace_is_not_a_setting(monkeypatch):
    monkeypatch.setenv("PEB_STATE_DIR", "   ")

    assert config.state_dir() == config.PROJECT_ROOT / "assets"


def test_the_code_root_is_not_the_state_root(monkeypatch, tmp_path):
    """PROJECT_ROOT stays where the code is: `core/docs.py` reads the shipped
    guide from it, and that ships read-only beside the package."""
    monkeypatch.setenv("PEB_STATE_DIR", str(tmp_path))

    assert config.PROJECT_ROOT != config.state_dir()
    assert (config.PROJECT_ROOT / "exam_bank").is_dir()


@pytest.mark.skipif(sys.platform != "win32", reason="icacls is Windows-only")
def test_the_package_imports_under_a_read_only_root(tmp_path):
    """The install case, reproduced rather than reasoned about.

    Stages the package under a directory the user may read and execute but
    not write - which is what Program Files is - and imports it with the
    state directory pointed elsewhere. Without `PEB_STATE_DIR` this same
    import raises PermissionError on `assets`.
    """
    root = tmp_path / "app"
    shutil.copytree(REPO / "exam_bank", root / "exam_bank",
                    ignore=shutil.ignore_patterns("__pycache__"))
    state = tmp_path / "state"

    subprocess.run(
        ["icacls", str(root), "/inheritance:r", "/grant:r", f"{os.environ['USERNAME']}:(OI)(CI)RX"],
        capture_output=True, check=False,
    )
    try:
        probe = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "import exam_bank.utils.config as c; print(c.DB_PATH)"
        )
        env = {**os.environ, "PEB_STATE_DIR": str(state)}
        result = subprocess.run(
            [sys.executable, "-B", "-c", probe, str(root)],
            capture_output=True, text=True, env=env,
        )

        assert result.returncode == 0, result.stderr[-600:]
        assert str(state) in result.stdout
        # And nothing was created in the read-only tree.
        assert not (root / "assets").exists()
    finally:
        subprocess.run(["icacls", str(root), "/reset", "/t"],
                       capture_output=True, check=False)


@pytest.mark.skipif(sys.platform != "win32", reason="icacls is Windows-only")
def test_without_the_override_a_read_only_root_still_fails(tmp_path):
    """The other half: proving the guard above is the thing doing the work,
    not something incidental about the temporary directory."""
    root = tmp_path / "app"
    shutil.copytree(REPO / "exam_bank", root / "exam_bank",
                    ignore=shutil.ignore_patterns("__pycache__"))

    subprocess.run(
        ["icacls", str(root), "/inheritance:r", "/grant:r", f"{os.environ['USERNAME']}:(OI)(CI)RX"],
        capture_output=True, check=False,
    )
    try:
        probe = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "import exam_bank.utils.config"
        )
        env = {k: v for k, v in os.environ.items() if k != "PEB_STATE_DIR"}
        result = subprocess.run(
            [sys.executable, "-B", "-c", probe, str(root)],
            capture_output=True, text=True, env=env,
        )

        assert result.returncode != 0
        assert "PermissionError" in result.stderr or "Access is denied" in result.stderr
    finally:
        subprocess.run(["icacls", str(root), "/reset", "/t"],
                       capture_output=True, check=False)
