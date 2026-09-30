# AI Chat

**Content → AI Chat** is a conversation with the configured model about two
things: how the Exam Bank works, and how Pentaho's products work. The second
is what you need when you write a question or check one: what port the server
listens on, which step does what, what changed in 11.0.

## Where the answers come from

Each question is first searched in two places:

- **This app's documentation** — the pages under **System → Documentation**.
- **docs.pentaho.com** — Pentaho's product documentation, searched through the
  docs site's MCP server. See [The Pentaho docs connection](02-pentaho-docs-connection.md).

The model is given what those searches found, told to answer only from it, and
told to cite what it used. If neither search finds anything, the model is not
asked at all, and the reply says what was searched and that nothing covered
the question. An answer from outside the documentation would read exactly like
one from inside it.

## The answer as it is written

The sources are listed as soon as the searches are done, and the answer then
appears as the model writes it, rather than all at once when it has finished -
which on a local model can take a minute. **Stop** ends it there: what was
written stays on screen, marked *Stopped before it finished*, and is not sent
back with a follow-up question. With Ollama, stopping also stops the model
working on it.

## Sources under an answer

Every answer lists what the model was given, numbered the way the answer cites
it:

- **A1, A2 …** are pages of this app's documentation. Pressing one opens that
  page in **Documentation**, at the heading the section came from.
- **P1, P2 …** are docs.pentaho.com pages. Pressing one opens the page in your
  browser.

A source the answer does not cite is shown fainter: the model was given it and
did not use it. Pressing a number inside the answer's text opens that source.

## Choosing where to search

The two switches above the question box choose the sources: **This app's docs**
and **docs.pentaho.com**. At least one must be on. With docs.pentaho.com off,
nothing about your question is sent to the docs site.

If the Pentaho docs connection is off in **Settings**, its switch cannot be
turned on here, and says so.

## When docs.pentaho.com cannot be reached

The answer goes ahead from this app's documentation, and a note under it says
docs.pentaho.com could not be searched and why: no network, a proxy, or the
server not answering within 15 seconds. **Settings → Pentaho documentation**
shows the connection's state and can test it.

## Follow-up questions

Earlier turns of the conversation go to the model with each new question, so a
follow-up such as "and on Linux?" has something to follow. A short follow-up is
also searched together with the question before it, which is what finds the
right pages for it.

**New conversation** clears the conversation. Until then it is kept on this
machine, in the app's own storage: it is not in the bank and not in backups.

## What leaves this machine

- With **docs.pentaho.com** on, the question's text is sent to the docs site to
  search it.
- The conversation and the documentation found for it go to the model. With
  Ollama that is this machine or the server named in Settings; with Anthropic
  or OpenAI it is their hosted service.

## Treat it as a second opinion

The model can misread a source or join two facts that do not belong together.
Before an answer goes into an exam question, open the source it cites and check
it. That is what the numbers are for.
