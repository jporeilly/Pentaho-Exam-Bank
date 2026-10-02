"""Question similarity: each question's nearest neighbour within its exam."""

from exam_bank.core import similarity
from exam_bank.core.bank import Question
from exam_bank.core.similarity import DUPLICATE, OVERLAP, analyse, band, question_text, words


def q(qid, stem, *, scenario="", key="k", keys=None, distractors=("w1", "w2", "w3")):
    return Question(
        id=qid, stem=stem, scenario=scenario, key=key, keys=list(keys or []),
        question_type="multi" if keys else "single", distractors=list(distractors),
    )


# The one genuine duplicate the calibration found: the same scenario
# reworded, the same key. It scored 0.62 among its 30-question exam.
DUP_A = q("a", "Which combination of transformation steps efficiently achieves both objectives?",
          scenario="A data analyst receives a flat file containing customer records, but suspects "
                   "there are duplicate customer IDs. The analyst needs to identify both the unique "
                   "customer IDs and the complete rows representing the duplicate records.",
          key="Sort rows, then Unique rows")
DUP_B = q("b", "Which combination of transformation steps efficiently achieves both objectives?",
          scenario="A data analyst is validating customer records received from multiple systems. "
                   "They need to identify the unique customer IDs and extract the rows where customer "
                   "IDs are duplicated.",
          key="Sort rows, then Unique rows")


def filler(n):
    """Unrelated questions, so IDF has an exam to be computed over."""
    topics = ["kafka offsets commit", "mondrian schema cube", "metadata concept mask",
              "cda datasource cache", "report band group header", "rjava libjri native",
              "mqtt retained will", "rabbitmq exchange binding", "ollama keep_alive model",
              "spoon preview hop", "carte server slave", "pentaho server port"]
    return [q(f"f{i}", f"What about {topics[i % len(topics)]} number {i}?", key=f"answer {i}")
            for i in range(n)]


def test_identical_questions_score_one_hundred_even_in_a_two_question_exam():
    """Plain IDF gives a word every question shares a weight of zero, which
    would score two identical questions 0. The smoothing exists for this."""
    r = analyse([q("x", "How is the cache refreshed?"), q("y", "How is the cache refreshed?")])
    assert r["nearest"]["x"] == {"id": "y", "score": 100, "band": "duplicate"}
    assert r["duplicates"] == 1 and r["max"] == 100


def test_the_reworded_duplicate_scores_in_the_duplicate_band():
    r = analyse([DUP_A, DUP_B, *filler(28)])
    assert r["nearest"]["a"]["id"] == "b"
    assert r["nearest"]["a"]["band"] == "duplicate"
    assert r["duplicates"] == 1
    pair = r["pairs"][0]
    assert {pair["a"], pair["b"]} == {"a", "b"}
    assert "unique" in pair["shared"] or "customer" in pair["shared"]


def test_unrelated_questions_are_distinct():
    r = analyse(filler(12))
    assert r["duplicates"] == 0 and r["overlaps"] == 0 and r["pairs"] == []
    assert all(n["band"] == "distinct" for n in r["nearest"].values())


def test_every_question_gets_a_nearest_neighbour_that_is_not_itself():
    qs = filler(6)
    r = analyse(qs)
    assert set(r["nearest"]) == {x.id for x in qs}
    assert all(n["id"] != qid for qid, n in r["nearest"].items())


def test_an_exam_of_one_or_none_has_nothing_to_compare():
    for qs in ([], [q("solo", "Only question?")]):
        r = analyse(qs)
        assert r["nearest"] == {} and r["pairs"] == [] and r["max"] == 0


def test_distractors_do_not_count_toward_similarity():
    """Two different questions sharing a stock set of wrong answers are not alike."""
    shared = ("the server must be restarted", "the cache must be cleared", "the port is wrong")
    a = q("a", "Which mask formats dates?", key="MM-dd-yyyy", distractors=shared)
    b = q("b", "Which exchange broadcasts to all queues?", key="fanout", distractors=shared)
    assert "restarted" not in question_text(a)
    assert analyse([a, b, *filler(8)])["nearest"]["a"]["score"] < OVERLAP * 100


def test_a_multi_select_is_compared_on_all_its_keys():
    m = q("m", "Which two settings bound memory?", keys=["prefetch limit", "concurrent batches"])
    assert "prefetch" in question_text(m) and "concurrent" in question_text(m)


def test_words_keep_dotted_and_underscored_identifiers_and_drop_stopwords():
    assert words("Call gbm.perf with num_predict and ${VAR} in the step") == \
        ["call", "gbm.perf", "num_predict", "var", "step"]


def test_pairs_are_capped_but_all_are_counted():
    same = [q(f"s{i}", "How is the cache refreshed after a publish?") for i in range(6)]
    r = analyse(same, pair_limit=3)
    assert len(r["pairs"]) == 3
    assert r["duplicates"] == 15          # 6 choose 2


def test_bands_follow_the_thresholds():
    assert band(DUPLICATE) == "duplicate"
    assert band(DUPLICATE - 0.01) == "overlap"
    assert band(OVERLAP) == "overlap"
    assert band(OVERLAP - 0.01) == "distinct"
    assert 0 < similarity.OVERLAP < similarity.DUPLICATE < 1


def test_the_band_follows_the_percentage_shown_not_the_raw_score():
    """0.3996 is displayed as 40%, so it must not be called distinct."""
    assert band(0.3996) == "overlap"
    assert band(0.5496) == "duplicate"
    assert band(0.3949) == "distinct"
