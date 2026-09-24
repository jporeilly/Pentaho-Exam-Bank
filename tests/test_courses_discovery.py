"""Finding the Content Manager's courses.

The rule used to be "look for a sibling directory", which is right for every
checkout and can never work in an install: the code lives under Program Files,
so the sibling searched was `C:\\Program Files\\Pentaho Exam Bank\\
Pentaho-Content-Manager`. The first install opened with every pane empty and
nothing on screen explaining why.
"""

import sys

import pytest

from exam_bank.utils import config


@pytest.fixture
def courses(tmp_path):
    """A directory that looks like a Content Manager checkout."""
    repo = tmp_path / "Pentaho-Content-Manager"
    (repo / "courses" / "a-course").mkdir(parents=True)
    (repo / "courses" / "a-course" / "course.json").write_text("{}", encoding="utf-8")
    return repo


@pytest.fixture(autouse=True)
def no_registry(monkeypatch):
    """Silence the machine's real registry unless a test asks for it.

    Without this these tests pass or fail depending on whether the developer
    happens to have the Content Editor installed, which is the definition of
    a test that proves nothing.
    """
    monkeypatch.setattr(config, "_installer_hint", lambda: None)
    monkeypatch.delenv("PCM_REPO", raising=False)


def test_the_environment_wins(monkeypatch, courses):
    monkeypatch.setenv("PCM_REPO", str(courses))

    assert config._default_pcm_courses_dir() == str(courses / "courses")


def test_an_environment_value_pointing_nowhere_is_ignored(monkeypatch, tmp_path):
    """Not trusted blindly: a stale PCM_REPO would otherwise pin the app to a
    directory that no longer exists, with no fallback.

    PROJECT_ROOT is moved too. Without that the sibling rule finds this
    developer's own Pentaho-Content-Manager checkout and the test passes or
    fails on what happens to sit next to this one.
    """
    monkeypatch.setenv("PCM_REPO", str(tmp_path / "gone"))
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path / "app")

    assert config._default_pcm_courses_dir() == ""


def test_an_installer_hint_is_used(monkeypatch, courses):
    monkeypatch.setattr(config, "_installer_hint", lambda: courses)

    assert config._default_pcm_courses_dir() == str(courses / "courses")


def test_the_environment_beats_the_hint(monkeypatch, tmp_path, courses):
    other = tmp_path / "Elsewhere"
    (other / "courses" / "c").mkdir(parents=True)
    monkeypatch.setenv("PCM_REPO", str(other))
    monkeypatch.setattr(config, "_installer_hint", lambda: courses)

    assert config._default_pcm_courses_dir() == str(other / "courses")


def test_nothing_found_is_empty_not_a_guess(monkeypatch, tmp_path):
    """An install with no Content Manager on the machine. Empty means
    unconfigured, which the UI already reports properly - a guessed path
    would fail later and further from the cause."""
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path / "app")

    assert config._default_pcm_courses_dir() == ""


@pytest.mark.skipif(sys.platform != "win32", reason="the registry is Windows-only")
def test_the_hint_reader_ignores_a_path_without_courses(monkeypatch, tmp_path):
    """A hint recorded against a checkout that has since moved or been
    emptied is worse than no hint: it would be reported as configured."""
    empty = tmp_path / "moved-away"
    empty.mkdir()

    class FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import winreg

    monkeypatch.setattr(config, "_installer_hint", config._installer_hint)
    monkeypatch.setattr(winreg, "OpenKey", lambda *a, **k: FakeKey())
    monkeypatch.setattr(winreg, "QueryValueEx", lambda *a: (str(empty), 1))

    assert config._installer_hint() is None


def test_an_empty_saved_value_does_not_pin_the_app_to_unconfigured(
    tmp_path, monkeypatch, courses
):
    """A config written before the installer learned to look, or migrated
    from a checkout, holds "" - and a saved empty string would override the
    default forever. It is the absence of a choice, not a choice.

    Driven through PCM_REPO rather than by replacing
    `_default_pcm_courses_dir`: the dataclass captured that function as its
    `default_factory` when the class was defined, so monkeypatching the
    module attribute changes nothing the field will ever call. The first
    draft of this test did exactly that and proved nothing.
    """
    cfg = tmp_path / "config.json"
    cfg.write_text('{"pcm_courses_dir": "", "sme_name": "Jo"}', encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_FILE", cfg)
    monkeypatch.setenv("PCM_REPO", str(courses))

    loaded = config.AppConfig.load()

    assert loaded.pcm_courses_dir == str(courses / "courses")
    assert loaded.sme_name == "Jo", "the rest of the file must still load"


def test_a_real_saved_value_is_respected(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"pcm_courses_dir": "D:\\\\mine\\\\courses"}', encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_FILE", cfg)

    assert config.AppConfig.load().pcm_courses_dir == r"D:\mine\courses"
