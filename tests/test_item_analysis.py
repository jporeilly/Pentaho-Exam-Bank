"""Item analysis from the results Sheet's Detail tab (1.13.0).

A simulated cohort: 40 candidates whose ability runs evenly from weak to
strong, and one question built for each thing the analysis has to notice."""
import csv
import io

import pytest
from fastapi.testclient import TestClient

from exam_bank.core import item_analysis as ia
from exam_bank.core.bank import Certification, ExamBankDB, Question

COURSE = "developer-di-practitioner"
HEADER = ["Attempt ID", "Course ID", "Submitted at", "Email", "Question ID", "Module", "Prompt",
          "User answer", "Correct answer", "Was correct?"]


@pytest.fixture
def db(tmp_path):
    d = ExamBankDB(tmp_path / "ia.db")
    yield d
    d.close()


def seed(db):
    cert = Certification(name="DI Practitioner", source_type="pcm", source_ref=COURSE)
    db.save_certification(cert)
    qs = [
        Question(id="good", stem="Good?", key="K", distractors=["A", "B", "C"], pool_order=1),
        Question(id="miskeyed", stem="Miskeyed?", key="K", distractors=["Trap", "B", "C"], pool_order=2),
        Question(id="easy", stem="Easy?", key="K", distractors=["A", "B", "C"], pool_order=3),
        Question(id="dead", stem="Dead distractor?", key="K", distractors=["A", "B", "Nobody"], pool_order=4),
        Question(id="coin", stem="Coin?", key="K", distractors=["A", "B", "C"], pool_order=5),
        Question(id="multi", stem="Multi?", question_type="multi", key="Ka; with semicolon",
                 keys=["Ka; with semicolon", "Kb"], distractors=["X", "Y"], pool_order=6),
    ]
    for q in qs:
        q.certification_id = cert.id
        db.save(q)
    return cert


def cohort_csv(n=40, course=COURSE):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(HEADER)
    for i in range(n):
        ability = (i + 0.5) / n          # weak ... strong
        strong = ability > 0.5
        att = f"att-{course}-{i:02d}"
        email = f"candidate{i}@example.com"

        def row(qid, answer, correct_answer, right):
            w.writerow([att, course, "2026-10-08T10:00:00Z", email, qid, "m1", "prompt",
                        answer, correct_answer, "Y" if right else "N"])

        row("good", "K" if strong else "A", "K", strong)
        row("miskeyed", "Trap" if strong else "K", "K", not strong)
        row("easy", "K" if i != 0 else "A", "K", i != 0)
        row("dead", "K" if strong else ("A" if i % 2 else "B"), "K", strong)
        row("coin", "K" if i % 2 else "A", "K", bool(i % 2))
        multi_right = strong
        row("multi", "Ka; with semicolon; Kb" if multi_right else "X", "Ka; with semicolon; Kb", multi_right)
    return out.getvalue()


def item(report, qid):
    return next(it for it in report["exams"][0]["items"] if it["id"] == qid)


def texts(it):
    return " | ".join(f["text"] for f in it["flags"])


def test_parse_skips_email_and_needs_the_detail_columns():
    rows = ia.parse_detail_csv(cohort_csv(2))
    assert rows and all("email" not in r for r in rows)
    assert not any("@" in str(v) for r in rows for v in r.values())
    with pytest.raises(ia.ResultsImportError, match="Detail tab"):
        ia.parse_detail_csv("Attempt ID,Course ID\nx,y\n")


def test_an_unmarked_answer_is_neither_right_nor_wrong():
    # The results service writes "-" for an answer it could not mark.
    text = "\n".join([",".join(HEADER),
                      "a1,c,2026-10-08,x@example.com,q1,m1,p,Old option,K,-",
                      "a1,c,2026-10-08,x@example.com,q2,m1,p,K,K,Y"])
    rows = ia.parse_detail_csv(text)
    assert [r["question_id"] for r in rows] == ["q2"]


def test_import_is_idempotent(db):
    seed(db)
    first = ia.import_rows(db.conn, ia.parse_detail_csv(cohort_csv()))
    again = ia.import_rows(db.conn, ia.parse_detail_csv(cohort_csv()))
    assert first["added"] == 240 and first["attempts"] == 40
    assert again["added"] == 0 and again["totalResponses"] == 240


def test_the_analysis_notices_each_kind_of_question(db):
    seed(db)
    ia.import_rows(db.conn, ia.parse_detail_csv(cohort_csv()))
    r = ia.analyse(db)
    exam = r["exams"][0]
    assert exam["attempts"] == 40 and exam["name"] == "DI Practitioner"
    assert [it["id"] for it in exam["items"]] == ["good", "miskeyed", "easy", "dead", "coin", "multi"]

    good = item(r, "good")
    assert good["p"] == 0.5 and good["discrimination"] > 0.5
    assert good["upperP"] == 1.0 and good["lowerP"] == 0.0
    assert not [f for f in good["flags"] if f["level"] in ("warn", "bad")]

    miskeyed = item(r, "miskeyed")
    assert miskeyed["discrimination"] < 0
    assert "get it wrong more often" in texts(miskeyed)
    assert "prefer a distractor" in texts(miskeyed) and '"Trap"' in texts(miskeyed)

    easy = item(r, "easy")
    assert easy["p"] >= 0.9 and "Very easy" in texts(easy)
    assert easy["suggestedDifficulty"] == "Easy"

    dead = item(r, "dead")
    nobody = next(o for o in dead["options"] if o["text"] == "Nobody")
    assert nobody["chosen"] == 0 and 'rarely chosen (0 of 40): "Nobody"' in texts(dead)

    coin = item(r, "coin")
    assert abs(coin["discrimination"]) < 0.15 and "Barely separates" in texts(coin)

    # A key containing "; " is still one option, not two.
    multi = item(r, "multi")
    by_text = {o["text"]: o for o in multi["options"]}
    assert by_text["Ka; with semicolon"]["chosen"] == 20 and by_text["Kb"]["chosen"] == 20
    assert not any("no longer has" in f["text"] for f in multi["flags"])


def test_a_slightly_negative_score_is_weak_not_wrong(db, monkeypatch):
    # Over 40 candidates a correlation of -0.05 is noise: amber, not "check the key".
    seed(db)
    ia.import_rows(db.conn, ia.parse_detail_csv(cohort_csv()))
    monkeypatch.setattr(ia, "_pearson", lambda xs, ys: -0.05)
    coin = item(ia.analyse(db), "coin")
    assert "Barely separates" in texts(coin)
    assert not any(f["level"] == "bad" for f in coin["flags"])


def test_too_few_attempts_are_shown_not_judged(db):
    seed(db)
    ia.import_rows(db.conn, ia.parse_detail_csv(cohort_csv(6)))
    miskeyed = item(ia.analyse(db), "miskeyed")
    assert miskeyed["attempts"] == 6 and miskeyed["p"] is not None
    assert [f["level"] for f in miskeyed["flags"]] == ["info"]
    assert miskeyed["suggestedDifficulty"] is None


def test_an_edited_key_is_reported(db):
    seed(db)
    text = cohort_csv(4).replace(",K,Y", ",Old key,Y", 1)
    ia.import_rows(db.conn, ia.parse_detail_csv(text))
    r = ia.analyse(db)
    assert any("earlier correct answer" in f["text"] for it in r["exams"][0]["items"] for f in it["flags"])


def test_the_api(tmp_path):
    from exam_bank.api.app import app
    from exam_bank.api.deps import get_db

    path = tmp_path / "api.db"
    seed_db = ExamBankDB(path)
    cert = seed(seed_db)
    seed_db.close()

    def override():
        d = ExamBankDB(path)
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = override
    try:
        client = TestClient(app)
        bad = client.post("/api/results/import", json={"csv": "Name,Score\na,1\n"})
        assert bad.status_code == 422 and "Detail tab" in bad.json()["detail"]
        ok = client.post("/api/results/import", json={"csv": cohort_csv()}).json()
        assert ok["attempts"] == 40 and ok["courses"] == [COURSE]
        analysis = client.get("/api/results/analysis", params={"certification_id": cert.id}).json()
        assert analysis["exams"][0]["attempts"] == 40
        assert client.get("/api/results/analysis", params={"certification_id": "other"}).json()["exams"] == []
    finally:
        app.dependency_overrides.clear()
