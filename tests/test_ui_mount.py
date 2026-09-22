"""Serving the built UI must not change what the API answers.

These exist because adding the mount broke a security check on the first
run: `/api/courses/..%2F..%2Fetc/labs` is refused by the courses router's
traversal guard, fell through to the SPA catch-all, and came back 200
with index.html. A rejected traversal that answers 200 reads as a
traversal that worked.

Registering the catch-all AFTER the routers is not enough. That stops it
shadowing routes that EXIST; it does nothing for a route that exists and
REFUSES, because the refusal is a 404 and a 404 keeps looking.
"""

import io

import pytest
from fastapi.testclient import TestClient

from exam_bank.api import app as app_module
from exam_bank.api.app import app


@pytest.fixture
def client():
    return TestClient(app)


def _ui_is_built() -> bool:
    return (app_module._DIST / "index.html").is_file()


class TestTheApiStillWins:
    def test_an_unknown_api_path_is_404_not_the_app_shell(self, client):
        """The whole point. Without the guard this is 200 + index.html."""
        r = client.get("/api/there-is-no-such-endpoint")
        assert r.status_code == 404, (
            "an unknown /api path must 404; 200 here means the SPA catch-all "
            "is answering for the API"
        )
        assert "<!doctype html" not in r.text.lower(), (
            "the API answered with the app shell"
        )

    def test_a_refused_route_keeps_its_refusal(self, client):
        """A route that EXISTS and says no. This is the case that broke:
        the traversal guard's 404 is indistinguishable, to the router, from
        'no such route' - so the catch-all took it."""
        r = client.get("/api/courses/..%2F..%2Fetc/labs")
        assert r.status_code in (400, 404, 409)
        assert "<!doctype html" not in r.text.lower()

    def test_a_real_api_route_is_untouched(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        # Health reports the things the UI needs to decide what to show:
        # which provider, which database, which courses dir, and what the
        # launch handed over. Asserting on the KEYS rather than a status
        # field, because an index.html body would have none of them.
        assert {"version", "database", "provider", "courses"} <= set(r.json())


@pytest.mark.skipif(not _ui_is_built(), reason="frontend/dist not built")
class TestTheShellIsServed:
    def test_the_root_serves_the_app(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "<!doctype html" in r.text.lower()

    def test_a_deep_path_serves_the_app_so_reload_works(self, client):
        """A single-page app owns its own routes; reloading on one must not
        404 just because no file sits at that path."""
        r = client.get("/bank/some/deep/view")
        assert r.status_code == 200
        assert "<!doctype html" in r.text.lower()

    def test_a_real_file_is_served_as_itself(self, client):
        r = client.get("/favicon.ico")
        assert r.status_code == 200
        assert "<!doctype html" not in r.text[:200].lower()


def test_the_mount_is_conditional_on_a_build():
    """`mount_ui` returning False on an unbuilt tree is what keeps the dev
    flow working - Vite serves the UI and proxies /api here."""
    assert app_module.UI_MOUNTED is _ui_is_built()
