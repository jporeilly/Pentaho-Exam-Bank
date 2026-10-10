"""The writing standard's mechanical half: tidy() and style_notes() (1.15.0).

The cases are the bank's own: a 2026-10 survey of its 489 questions found
single quotes doing six jobs, "Stream Lookup" beside PDI's "Stream lookup",
curly quotes and contractions. tidy() may only make changes that cannot alter
what a sentence says; everything else is a note for the author.
"""

from exam_bank.core.bank import Question
from exam_bank.core.pdi_names import JOB_ENTRIES, STEPS
from exam_bank.core.writing_style import style_notes, text_notes, tidy, tidy_question


# --- PDI's names ---------------------------------------------------------------


def test_the_names_are_pdis_own_sentence_case():
    for name in ("Stream lookup", "Filter rows", "Text file input", "Select values",
                 "Insert / update", "Row normaliser", "JSON input", "ETL metadata injection"):
        assert name in STEPS
    assert "Set variables" in JOB_ENTRIES
    assert "Stream Lookup" not in STEPS


def test_a_title_case_step_name_takes_pdis_spelling():
    assert tidy("Add a Stream Lookup step.") == "Add a Stream lookup step."
    assert tidy("Two Stream Lookups in a row.") == "Two Stream lookups in a row."
    assert tidy("A Text File Input step reads it.") == "A Text file input step reads it."
    assert tidy("Use Insert / Update here.") == "Use Insert / update here."


def test_a_step_name_written_as_an_idea_or_in_capitals_is_left_alone():
    # Lower case is the idea, not the step; capitals are SQL.
    assert tidy("PDI performs a merge join on the keys.") == "PDI performs a merge join on the keys."
    assert tidy("The query ends with GROUP BY region.") == "The query ends with GROUP BY region."


# --- Quotes ---------------------------------------------------------------------


def test_quotes_come_off_a_step_name():
    assert tidy("The 'Calculator' step runs next.") == "The Calculator step runs next."
    assert tidy("A 'Stream Lookup' step joins them.") == "A Stream lookup step joins them."
    assert tidy("Before the 'Table input' step.") == "Before the Table input step."


def test_a_quoted_name_or_path_becomes_code():
    assert tidy("Read the 'region_code' field.") == "Read the `region_code` field."
    assert tidy("Use '$.customers[*].region_code' here.") == "Use `$.customers[*].region_code` here."
    assert tidy("Edit 'kettle.properties' first.") == "Edit `kettle.properties` first."
    assert tidy(r"Open '%APPDATA%\Pentaho' now.") == r"Open `%APPDATA%\Pentaho` now."
    assert tidy("Set '${INPUT_DIR}' once.") == "Set `${INPUT_DIR}` once."


def test_an_ordinary_quoted_word_is_left_for_the_author():
    # 'sales' could be a key (code) or an ordinary word (no quotes): only a
    # reader can tell, so tidy leaves it and the notes say so.
    assert tidy("It enriches 'sales' records.") == "It enriches 'sales' records."
    assert any("Single quotes around 'sales'" in n for n in text_notes("It enriches 'sales' records."))


def test_apostrophes_are_not_quotes():
    text = "The customer's record and the customers' rows."
    assert tidy(text) == text
    assert text_notes(text) == []


def test_curly_quotes_are_made_straight():
    assert tidy("The client’s team said “done”.") == "The client's team said \"done\"."


def test_code_is_never_touched():
    text = "Run `echo 'Stream Lookup'  can't` as is."
    assert tidy(text) == text


# --- Contractions and spacing -------------------------------------------------------


def test_nt_is_written_out_keeping_the_capital():
    assert tidy("It doesn't stop. Can't be undone. It won't.") == \
        "It does not stop. Cannot be undone. It will not."


def test_a_quotation_keeps_its_contractions():
    text = 'Users report "can\'t get on the VPN" since Monday.'
    assert tidy(text) == text


def test_contractions_tidy_cannot_settle_are_noted_but_a_possessive_is_not():
    assert any("it's" in n for n in text_notes("If it's empty, the step stops."))
    assert text_notes("IT's budget pays for it.") == []


def test_runs_of_spaces_close_up_but_paragraphs_survive():
    assert tidy("One  two.\n\nThree   four.  ") == "One two.\n\nThree four."


# --- tidy_question --------------------------------------------------------------------


def test_every_copy_of_an_answer_is_tidied_alike():
    q = Question(id="q", stem="Which step joins them?", question_type="single",
                 key="A 'Stream Lookup' step", distractors=["A 'Merge Join' step", "A Dummy step"],
                 option_order=["A 'Merge Join' step", "A 'Stream Lookup' step", "A Dummy step"],
                 explanation="")
    t = tidy_question(q)
    assert t.key == "A Stream lookup step"
    assert t.distractors == ["A Merge join step", "A Dummy step"]
    assert sorted(t.option_order) == sorted([t.key, *t.distractors]), "the order must still name the answers"
    assert q.key == "A 'Stream Lookup' step", "the question given is not changed"


# --- style_notes ---------------------------------------------------------------------


def _q(**over):
    base = dict(id="q", scenario="A team loads orders nightly.", stem="Which step filters them?",
                question_type="single", key="Filter rows", distractors=["Sort rows", "Select values"],
                explanation="**Filter rows** keeps the rows that match a condition.")
    base.update(over)
    return Question(**base)


def test_a_question_to_the_standard_has_no_notes():
    assert style_notes(_q()) == []


def test_answers_that_mix_sentences_and_phrases_are_noted():
    notes = style_notes(_q(key="Filter rows.", distractors=["Sort rows", "Select values"]))
    assert ("options", next(m for f, m in notes if "full stop" in m)) in notes


def test_a_value_in_double_quotes_is_noted():
    notes = style_notes(_q(scenario='The flag is set to "true" when it fails.'))
    assert any(f == "scenario" and '"true"' in m for f, m in notes)


def test_bold_outside_the_explanation_is_noted_where_it_is():
    notes = style_notes(_q(key="**Filter rows**"))
    assert [f for f, m in notes if "Bold" in m] == ["options"]
    notes = style_notes(_q(scenario="A team loads **orders** nightly."))
    assert [f for f, m in notes if "Bold" in m] == ["scenario"]


# --- From the first live trial (2026-10-10) --------------------------------------


def test_a_number_in_a_sentence_comes_out_of_code():
    assert tidy("A price of `49.99` and a quantity of `2`.") == "A price of 49.99 and a quantity of 2."
    assert tidy("It returns `-1` and `1,000`.") == "It returns -1 and 1,000."
    assert tidy("Set `retries=2` first.") == "Set `retries=2` first."


def test_an_ordinary_word_in_code_is_noted():
    assert any("`customer` data" in n for n in text_notes("It loads `customer` data nightly."))
    assert text_notes("Read the `region_code` field and the `customers` array.") == []


def test_code_in_the_correct_answer_alone_is_noted():
    q = _q(key="Sort on `region_code` first.", distractors=["Use a bigger buffer.", "Read both at once."])
    assert any(f == "options" and "gives it away" in m for f, m in style_notes(q))
    fair = _q(key="Sort on `region_code` first.",
              distractors=["Index `sales_id` first.", "Read both at once."])
    assert not any("gives it away" in m for f, m in style_notes(fair))


def test_code_that_marks_the_correct_answer_comes_off_it_in_every_copy():
    q = _q(key="Sort on `region_code` first.", distractors=["Use a bigger buffer.", "Read both at once."],
           option_order=["Use a bigger buffer.", "Sort on `region_code` first.", "Read both at once."],
           scenario="Both files are keyed on `region_code`.")
    t = tidy_question(q)
    assert t.key == "Sort on region_code first."
    assert "Sort on region_code first." in t.option_order
    assert t.scenario == "Both files are keyed on `region_code`.", "only the answers are evened out"
    assert not any("gives it away" in m for f, m in style_notes(t))


def test_code_shared_by_right_and_wrong_answers_stays():
    q = _q(key="`$.customers[*].region_code`", distractors=["`$.region_code[*]`", "`$.customers.region_code`"])
    assert tidy_question(q).key == "`$.customers[*].region_code`"
