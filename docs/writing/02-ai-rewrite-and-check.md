# AI Rewrite and AI Check

Both need an AI model set up in [Settings](../admin/01-settings.md). Neither writes anything
to the bank.

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
