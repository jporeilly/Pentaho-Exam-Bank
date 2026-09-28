"""Searching the app's own documentation.

The two things that decide whether this is useful are tokenising and stop
words, and both were wrong before: words kept their attached punctuation and
markdown, so most occurrences were invisible, and ranking was dominated by the
common words of the question rather than its subject.
"""

import pytest

from exam_bank.core import docs

GUIDE = """\
Pentaho Exam Bank helps you build certification exams.

## Importing Existing Questions

Drop a **CSV** into the Import pane. Every `certification` is matched by name,
and a duplicate is flagged rather than imported.

## Two Independent Checks

You should do a check, and then do a check again, so that there is a check on
the check that you did.

## Database Backup & Restore

Take a backup before deleting anything. Restoring one replaces the live
database (a backup of the current database is taken first).
"""

README = """\
# Exam Bank

A tool for question banks.

## Installing

Run the installer.
"""


@pytest.fixture
def sections(tmp_path):
    (tmp_path / "HOW_TO_GUIDE.md").write_text(GUIDE, encoding="utf-8")
    (tmp_path / "README.md").write_text(README, encoding="utf-8")
    return docs.load_sections(tmp_path)


def headings(results):
    return [s.heading for s in results]


# --- tokenising ------------------------------------------------------------


def test_punctuation_and_markdown_do_not_hide_a_word():
    """The defect this replaces. In the real guide "certification" appears 88
    times as text and 34 times as a bare whitespace token — the rest carry a
    full stop, asterisks or backticks, and were invisible to the matcher."""
    text = "**certification**, `certification`, (certification) and certification."

    # Four occurrences, every one of them wearing different punctuation. A
    # whitespace split recovers none of them.
    assert docs.tokens(text).count("certification") == 4
    assert text.lower().split().count("certification") == 0, "the old matcher saw none"


def test_tokens_are_lower_cased():
    assert docs.tokens("CSV Import") == ["csv", "import"]


def test_numbers_survive():
    """Version numbers and step numbers are real search terms."""
    assert "2" in docs.tokens("Step 2: pick a course")


# --- what a query is ranked on ---------------------------------------------


def test_common_words_are_dropped_from_a_query():
    assert docs.query_terms("How do I import a CSV?") == ["import", "csv"]


def test_a_query_of_only_common_words_keeps_them():
    """Better to rank on the words available than on nothing at all."""
    assert docs.query_terms("what is it") == ["what", "is", "it"]


def test_an_empty_query_finds_nothing(sections):
    assert docs.search("", sections) == []
    assert docs.search("   ", sections) == []


# --- ranking ---------------------------------------------------------------


def test_a_question_is_ranked_on_its_subject_not_its_grammar(sections):
    """"How do I import a CSV?" used to rank "Two Independent Checks" top —
    that section contains do, a and I, and nothing about importing."""
    results = docs.search("How do I import a CSV?", sections)

    assert headings(results)[0] == "Importing Existing Questions"
    assert "Two Independent Checks" not in headings(results)


def test_a_heading_match_outranks_a_body_mention(sections):
    results = docs.search("backup", sections)

    assert headings(results)[0] == "Database Backup & Restore"


def test_a_single_word_query_works(sections):
    """The commonest way to search a document."""
    assert headings(docs.search("importing", sections)) == ["Importing Existing Questions"]


def test_covering_more_of_the_question_beats_repeating_one_term(sections):
    """Scored on distinct terms: a section saying "check" six times must not
    outrank one that covers both words of the query."""
    results = docs.search("check database", sections)

    assert headings(results)[0] == "Database Backup & Restore"


def test_nothing_matching_returns_nothing(sections):
    assert docs.search("kubernetes helm chart", sections) == []


def test_results_are_limited(sections):
    assert len(docs.search("a check database certification csv", sections, limit=2)) == 2


# --- splitting -------------------------------------------------------------


def test_every_heading_becomes_a_section(sections):
    assert "Importing Existing Questions" in headings(sections)
    assert "Installing" in headings(sections)


def test_text_before_the_first_heading_is_kept(sections):
    """In a README that is the part saying what the thing is, which is
    exactly what a newcomer searches for."""
    preamble = [s for s in sections if s.heading == "How-To Guide"]

    assert preamble and "certification exams" in preamble[0].text


def test_sections_know_which_document_they_came_from(sections):
    installing = next(s for s in sections if s.heading == "Installing")

    assert installing.document == "README"


def test_a_missing_document_is_skipped_not_fatal(tmp_path):
    """The app is usable without its README; a docs pane that fails whole
    because one file was not shipped is not."""
    (tmp_path / "README.md").write_text(README, encoding="utf-8")

    found = docs.load_sections(tmp_path)

    assert found and all(s.document == "README" for s in found)


def test_no_documents_at_all_is_an_empty_list(tmp_path):
    assert docs.load_sections(tmp_path) == []


# --- what the model is given ----------------------------------------------


def test_the_context_is_the_sections_themselves(sections):
    """Returned rather than pre-formatted, so the caller can show an author
    which parts of the documentation an answer was built from."""
    chosen = docs.context_for("import a CSV", sections)

    assert chosen and all(isinstance(s, docs.DocSection) for s in chosen)


def test_the_context_stays_within_its_budget(sections):
    chosen = docs.context_for("check certification database csv", sections, budget=200)
    spent = sum(len(s.heading) + len(s.text) for s in chosen)

    assert chosen, "a tiny budget must still yield the best single section"
    assert spent <= 200 or len(chosen) == 1


def test_a_query_matching_nothing_yields_no_context(sections):
    """Which is what lets the caller refuse to answer instead of letting the
    model invent one."""
    assert docs.context_for("kubernetes helm chart", sections) == []


def test_a_snippet_is_cut_at_a_word(sections):
    long_text = docs.DocSection("d", "h", "word " * 200)

    assert long_text.snippet.endswith("…")
    assert not long_text.snippet.rstrip("…").endswith("wor")


# --- stemming ----------------------------------------------------------------


@pytest.mark.parametrize("a, b", [
    ("publish", "publishing"), ("publish", "published"), ("course", "courses"),
    ("approve", "approved"), ("status", "statuses"), ("write", "writing"),
    ("backup", "backups"), ("class", "classes"),
])
def test_forms_of_one_word_meet(a, b):
    """Found on the real docs: "publish push courses repo" ranked a Changelog
    list above *Publishing to a Course*, which matched none of the words exactly."""
    assert docs.stem(a) == docs.stem(b)


@pytest.mark.parametrize("word", ["bank", "11", "api", "use"])
def test_short_words_and_numbers_are_left_alone(word):
    assert docs.stem(word) == word


def test_stemming_lets_a_plural_query_find_a_singular_heading(sections):
    assert headings(docs.search("backups", sections))[0] == "Database Backup & Restore"


# --- pages ---------------------------------------------------------------------


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "README.md").write_text("# Pentaho Exam Bank\n\nWhat it is.\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [1.0.0]\n\nFirst.\n", encoding="utf-8")
    for folder, name, text in [
        ("guides", "02-second.md", "# Second\n\nTwo.\n"),
        ("guides", "01-first.md", "# First\n\n| a | b |\n\n**The** first [page](x.md).\n"),
        ("admin", "01-settings.md", "No title line here.\n"),
        ("elsewhere", "01-x.md", "# Not served\n"),
    ]:
        (tmp_path / "docs" / folder).mkdir(parents=True, exist_ok=True)
        (tmp_path / "docs" / folder / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_pages_run_start_here_then_folders_then_project(tree):
    slugs = [p.slug for p in docs.list_pages(tree)]

    assert slugs == ["README", "docs/guides/01-first", "docs/guides/02-second",
                     "docs/admin/01-settings", "CHANGELOG"]


def test_a_page_without_a_title_line_is_named_from_its_file(tree):
    page = docs.find_page("docs/admin/01-settings", tree)

    assert page.title == "Settings"


def test_a_summary_skips_tables_and_strips_markdown(tree):
    assert docs.find_page("docs/guides/01-first", tree).summary == "The first page."


def test_find_page_only_finds_listed_pages(tree):
    assert docs.find_page("docs/elsewhere/01-x", tree) is None
    assert docs.find_page("../README", tree) is None


# --- headings ------------------------------------------------------------------


@pytest.mark.parametrize("text, anchor", [
    ("What it connects to", "what-it-connects-to"),
    ("Courses: Adopting a Course's Exam", "courses-adopting-a-courses-exam"),
    ("AI & Docs", "ai--docs"),
    ("The `exam.json` file", "the-examjson-file"),
    ("[1.6.0] - 2026-09-28", "160---2026-09-28"),
])
def test_heading_ids_follow_githubs_rule(text, anchor):
    """So README.md#what-it-connects-to works on GitHub and in the app alike."""
    assert docs.slugify_heading(text) == anchor


def test_a_hash_inside_a_code_block_is_not_a_heading():
    text = "## Real\n\n```bash\n# a comment\n```\n\n### Also real\n"

    assert [h["text"] for h in docs.headings(text)] == ["Real", "Also real"]


def test_sections_carry_their_page_and_anchor():
    found = docs.split_sections("Page", "Intro.\n\n## Deep Dive\n\nBody.\n", "docs/guides/01-x")

    assert [(s.heading, s.anchor, s.slug) for s in found] == [
        ("Page", "", "docs/guides/01-x"),
        ("Deep Dive", "deep-dive", "docs/guides/01-x"),
    ]
