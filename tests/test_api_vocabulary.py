"""GET /api/vocabulary: the bank's fixed lists, as the server validates them.

Five screens typed their own copies until 1.9.0, and the Admin bulk delete's
had drifted (four of six statuses). They now read this.
"""

from fastapi.testclient import TestClient

from exam_bank.api.app import app
from exam_bank.core.bank import BLOOM_LEVELS, DIFFICULTIES, STATUS_LABELS, STATUSES


def test_the_vocabulary_is_the_lists_the_server_checks_against():
    body = TestClient(app).get("/api/vocabulary").json()

    assert body == {
        "statuses": STATUSES,
        "statusLabels": STATUS_LABELS,
        "difficulties": DIFFICULTIES,
        "bloomLevels": BLOOM_LEVELS,
    }
    assert set(body["statusLabels"]) == set(body["statuses"])
