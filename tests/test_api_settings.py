"""Reading and changing the app's configuration, over HTTP.

Two properties matter more than the rest and are asserted from several angles:
an API key is never accepted or returned, and only an allowlisted field can be
written. `config` is a module-level singleton whose `save()` writes the whole
dataclass, so a browser able to PUT arbitrary keys into it could quietly
rewrite state the app manages for itself.
"""

import json

import pytest
from fastapi.testclient import TestClient

from exam_bank.api.app import app
from exam_bank.utils import config as config_module
from exam_bank.utils.config import config


@pytest.fixture(autouse=True)
def sandboxed_config(tmp_path, monkeypatch):
    """Point `save()` at a temporary file and put every value back afterwards.

    `config` is a singleton and `save()` writes to the real config file, so
    without this a test run would rewrite the developer's own settings — and
    the failure would be invisible until they next opened the app.
    """
    before = {f: getattr(config, f) for f in config.__dataclass_fields__}
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    yield tmp_path / "config.json"
    for field, value in before.items():
        setattr(config, field, value)


@pytest.fixture
def client():
    return TestClient(app)


def put(client, **settings):
    return client.put("/api/settings", json={"settings": settings})


# --- what is exposed -------------------------------------------------------


def test_the_current_settings_are_returned(client):
    body = client.get("/api/settings").json()

    assert "sme_name" in body["settings"]
    assert body["settings"]["ai_provider"] in body["choices"]["providers"]


def test_provider_keys_are_booleans_and_nothing_else(client, monkeypatch):
    """The one thing this endpoint must never do. A settings form that could
    return a key would put it in a browser; one that accepted a key would
    write it to a plain file in the project directory."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-never-be-returned")

    raw = client.get("/api/settings").text

    assert json.loads(raw)["providerKeys"]["anthropic"] is True
    assert "sk-should-never-be-returned" not in raw


def test_no_setting_is_named_like_a_key(client):
    """A key could only be stored by adding a field for it, so the allowlist
    is the thing to assert on."""
    fields = client.get("/api/settings").json()["settings"]

    assert not [f for f in fields if "key" in f.lower() or "secret" in f.lower()]


def test_the_paths_it_reads_and_writes_are_shown(client):
    paths = client.get("/api/settings").json()["paths"]

    assert paths["database"].endswith(".db")
    assert paths["config"].endswith(".json")


# --- changing a setting ----------------------------------------------------


def test_a_setting_is_saved_and_written_to_disk(client, sandboxed_config):
    response = put(client, sme_name="Jo Bloggs")

    assert response.status_code == 200
    assert response.json()["settings"]["sme_name"] == "Jo Bloggs"
    assert json.loads(sandboxed_config.read_text(encoding="utf-8"))["sme_name"] == "Jo Bloggs"


def test_fields_that_were_not_sent_are_left_alone(client):
    before = client.get("/api/settings").json()["settings"]["questions_per_page"]
    put(client, sme_name="Only this")

    assert client.get("/api/settings").json()["settings"]["questions_per_page"] == before


def test_the_active_sme_joins_the_saved_list(client):
    """Matching what the app does at startup — otherwise a name typed here is
    forgotten on the next restart."""
    put(client, sme_name="Newly Typed")

    assert "Newly Typed" in config.sme_names


# --- what it refuses -------------------------------------------------------


def test_a_field_the_app_manages_itself_cannot_be_written(client):
    """`file_certifications` maps a source file to its certification. Nothing
    would report it being clobbered."""
    response = put(client, file_certifications={"evil.pptx": "cert-1"})

    assert response.status_code == 400
    assert "file_certifications" in response.json()["detail"]


def test_an_unknown_field_is_refused_rather_than_ignored(client):
    response = put(client, not_a_setting="x")

    assert response.status_code == 400


def test_one_bad_value_changes_none_of_the_others(client):
    """A half-applied save is the kind of thing an author only notices later,
    when the half that did not apply matters."""
    before = client.get("/api/settings").json()["settings"]["sme_name"]

    response = put(client, sme_name="Should Not Stick", ai_provider="nonsense")

    assert response.status_code == 400
    assert client.get("/api/settings").json()["settings"]["sme_name"] == before


def test_an_unknown_provider_is_refused(client):
    response = put(client, ai_provider="gemini")

    assert response.status_code == 400
    assert "ollama" in response.json()["detail"]

    put(client, ai_provider="ollama").raise_for_status()


@pytest.mark.parametrize("value", [1.5, -0.2, 100])
def test_a_threshold_outside_0_to_1_is_refused(client, value):
    """0.85 is a similarity score. 85 would match nothing and report no
    duplicates at all, which looks like a clean bank."""
    response = put(client, duplicate_threshold=value)

    assert response.status_code == 400
    assert "between 0 and 1" in response.json()["detail"]


def test_a_valid_threshold_is_accepted(client):
    assert put(client, duplicate_threshold=0.9).status_code == 200


def test_a_courses_directory_that_does_not_exist_is_refused(client, tmp_path):
    """Saved silently, it would list no courses and look like an empty
    Content Manager rather than a typo."""
    response = put(client, pcm_courses_dir=str(tmp_path / "not-here"))

    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]

    assert put(client, pcm_courses_dir=str(tmp_path)).status_code == 200


def test_clearing_the_courses_directory_is_allowed(client):
    """Empty means unconfigured, which the app already reports properly."""
    assert put(client, pcm_courses_dir="").status_code == 200


def test_an_unsupported_page_size_is_refused(client):
    response = put(client, questions_per_page=7)

    assert response.status_code == 400


# --- settings the environment governs --------------------------------------


def test_an_env_overridden_field_is_reported(client, monkeypatch):
    """Such a field cannot be changed here in any lasting way: it is written
    to config.json and overridden again on the next load, so the author sets
    it, sees it saved, restarts, and finds it reverted."""
    monkeypatch.setenv("OLLAMA_MODEL", "governed-elsewhere")

    body = client.get("/api/settings").json()

    assert "ollama_model" in body["envOverridden"]
    assert body["envNames"]["ollama_model"] == "OLLAMA_MODEL"


def test_nothing_is_reported_as_overridden_when_the_environment_is_clean(
    client, monkeypatch
):
    for name in ("OLLAMA_URL", "OLLAMA_MODEL", "OLLAMA_NUM_CTX", "OLLAMA_ENABLED"):
        monkeypatch.delenv(name, raising=False)

    assert client.get("/api/settings").json()["envOverridden"] == []


# --- the Pentaho docs connection -------------------------------------------------


def test_the_docs_connection_is_on_by_default_and_shown():
    from exam_bank.utils.config import AppConfig

    fresh = AppConfig()
    assert fresh.docs_mcp_enabled is True
    assert fresh.docs_mcp_url == "https://docs.pentaho.com/~gitbook/mcp"


def test_the_docs_connection_can_be_turned_off_and_readdressed(client):
    response = put(client, docs_mcp_enabled=False, docs_mcp_url="https://other.example/~gitbook/mcp")

    assert response.status_code == 200
    body = response.json()["settings"]
    assert body["docs_mcp_enabled"] is False
    assert body["docs_mcp_url"] == "https://other.example/~gitbook/mcp"


@pytest.mark.parametrize("url", ["", "docs.pentaho.com", "ftp://docs.pentaho.com/mcp", "file:///etc/passwd"])
def test_a_docs_address_that_is_not_http_is_refused(client, url):
    response = put(client, docs_mcp_url=url)

    assert response.status_code == 400
    assert "Pentaho docs MCP server" in response.json()["detail"]
