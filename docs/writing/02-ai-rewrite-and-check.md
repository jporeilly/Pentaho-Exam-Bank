# AI Rewrite, Check, Explanation and Answer Key

Four buttons in the question editor. All need an AI model set up in
[Settings](../admin/01-settings.md), and none writes anything to the bank: each
proposes, you take the proposal into the editor, and you press **Save** if you
agree.

**AI rewrite** asks the model for a better version of the question. The model
is told the house form: the scenario is statements that set the scene, the
question is only the question. The proposal shows the new scenario, question
and options. If the model broke the form anyway — say, put a question in the
scenario — the proposal says so under it. Press **Use this** to copy the
proposal into the editor (still unsaved; press Save if you agree), or
**Discard**.

**AI check answers** asks the model whether the question can be answered
correctly as written — for example, whether a distractor is also true — and
proofreads it. Beside its opinion you see the bank's own checks: whether the
question can be graded, and whether it follows the form. It is a second
opinion, not a guarantee.

**AI explanation** writes the explanation: why each correct answer is right
and each distractor wrong, naming every option by its text (never by a letter
— the options are shuffled). It is written from the course page the question
cites — or, failing that, the pages of its module — and the proposal says
which; for a question with no course page it says so, and every fact needs
checking. If the text never names one of the options, the proposal lists it.
Press **Use this explanation** to put it in the Explanation field.

**AI answer key** decides which options are correct, from the same course
pages, and shows its reasoning option by option: the sentence it relied on,
where it found one. It picks exactly as many answers as the question asks for
("Which two …?" is two); an answer of another size is refused. Press **Use
this answer** to take the key into the editor. Its main use is a question
whose answer was **guessed at import**: a plain-text file marks no answers, so
the first option was taken. The editor says so at the top of such a question
until the answer is checked — by taking the AI answer key, or with **The
answer is right** when the guess was correct.
