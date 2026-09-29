# Troubleshooting

**"Saved" never appeared.** Fixed in 1.6.0: the message now stays until your
next edit. Check the status bar says 1.6.0 or later.

**An approved question cannot be sent back.** Fixed in 1.6.0: Approved can
move to SME Review, Draft or Retired.

**The Exam Bank version in the status bar is red.** The interface and the
backend are different builds. Close the app completely and open it again; if it
persists, reinstall.

**"Two Content Manager checkouts disagree."** The app was opened for a course
from one Content Manager folder while Settings points at another. Fix the
courses folder in Settings.

**"No AI model is configured."** Choose a provider and model in Settings.

**"The model did not return a usable question."** Try again, or a larger model.

**A sync shows questions as Changed.** They were edited in the bank after they
came from the course, or moved along the course order to make room for a new
question. They are left alone unless you tick *Replace*, and publishing the
course brings them level.

**A question has an id like `03f2c063-39c7-…` and no Order.** It was generated
or imported into a course before 1.7.1, which filed it with a random id and no
place. From a checkout, `scripts\file_into_courses.py` shows what it would
change and `--apply` files every such question (after a backup); one already
published under its id is left alone.

**Publish is refused.** The plan says why: too few questions for the draw with
the chosen statuses, or, for a push, one of the reasons under
[Publishing to a Course](../guides/09-publishing.md).

**AI Chat says docs.pentaho.com could not be searched.** The answer came from
this app's documentation only. **Settings → Pentaho documentation** tests the
connection and names the reason; [The Pentaho docs connection](../ai/02-pentaho-docs-connection.md)
lists the usual ones.

**AI Chat says nothing covers the question.** Neither source had anything on
it, so the model was not asked. Try the words the screens or the product
documentation use — "draw" rather than "number of questions", "publish" rather
than "upload".

**AI Chat's docs.pentaho.com switch cannot be turned on.** The connection is
off in **Settings → Pentaho documentation**.
