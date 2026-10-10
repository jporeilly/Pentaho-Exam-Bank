# AI Rewrite, Check, Explanation and Answer Key

Four buttons in the question editor. All need an AI model set up in
[Settings](../admin/01-settings.md), and none writes anything to the bank: each
proposes, you take the proposal into the editor, and you press **Save** if you
agree.

**AI rewrite** polishes the question to the
[house style](01-how-a-question-is-written.md#the-house-style). It proofreads
the scenario, the question and the answers - spelling, grammar, punctuation
and clumsy wording only, keeping what each one says - and rewrites the
explanation to say why the correct answer is right, in paragraphs with the
key terms in bold. The explanation is rewritten from the current one: it
keeps the facts about the correct answer and drops what it said about the
wrong options. The proposal shows the new scenario, question, options and
explanation. If the model broke the form anyway - say, put a question in the
scenario, or left an option labelled "Incorrect" - the proposal says so under
it. Press **Use this** to copy the proposal into the editor (still unsaved;
press Save if you agree), or **Discard**.

To rewrite many questions at once, use **AI rewrite all** in the Bank; see
[Rewriting every question at once](../guides/05-the-bank.md#rewriting-every-question-at-once).

**AI check answers** asks the model whether the question can be answered
correctly as written — for example, whether a distractor is also true — and
proofreads it. Beside its opinion you see the bank's own checks: whether the
question can be graded, and whether it follows the form. It is a second
opinion, not a guarantee.

**AI explanation** writes a new explanation to the house style: why the
correct answer is right, in one to three paragraphs with the key terms in
bold, naming an answer by its text (never by a letter — the options are
shuffled). It is written from the course page the question cites — or,
failing that, the pages of its module — and the proposal says which; for a
question with no course page it says so, and every fact needs checking. If
the text still labels options "Correct" and "Incorrect" or names one by its
letter, the proposal says so. Press **Use this explanation** to put it in the
Explanation field.

**AI answer key** decides which options are correct, from the same course
pages, and shows its reasoning option by option: the sentence it relied on,
where it found one. It picks exactly as many answers as the question asks for
("Which two …?" is two); an answer of another size is refused. Press **Use
this answer** to take the key into the editor. Its main use is a question
whose answer was **guessed at import**: a plain-text file marks no answers, so
the first option was taken. The editor says so at the top of such a question
until the answer is checked — by taking the AI answer key, or with **The
answer is right** when the guess was correct.
