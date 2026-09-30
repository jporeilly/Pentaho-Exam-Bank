# Settings

**System → Settings**, section by section, in the order the screen shows them.

- **Who you are** — your name, stamped on every review action so the history
  says who approved what.
- **The model** — the provider and model used by Generate, AI rewrite, AI check
  and AI Chat. For Ollama, its URL and context window; for a hosted provider,
  whether its API key is present. Keys are read from the environment
  (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) and never stored or shown.
- **Pentaho documentation** — whether AI Chat also searches docs.pentaho.com,
  the address of the docs site's MCP server, and whether that server is
  answering right now. See
  [The Pentaho docs connection](../ai/02-pentaho-docs-connection.md).
- **Where things are** — the Content Manager courses folder, and the database
  and config file paths.
- **Export and backups** — see below.
- **Quality** — how alike two questions must be before import calls them
  duplicates, and how much of a correct answer's wording docs.pentaho.com must
  carry for Import's docs check to count it as backed. Both run from 0 to 1;
  higher is stricter.
- **Defaults** — how many questions the Bank shows to a page, and the default
  difficulty and Bloom level.

A setting governed by an environment variable is shown but cannot be edited
here, and names the variable. Press **Save**; *Saved* confirms it.

## The Pentaho documentation section

- **Search docs.pentaho.com from AI Chat** — on by default. Off, AI Chat
  answers from this app's own documentation only, and nothing is sent to the
  docs site.
- **MCP server** — `https://docs.pentaho.com/~gitbook/mcp` by default.
- **Status** — checked when the screen opens: *Connected*, with the server's
  name and version, the tools it offers and how long it took to answer, or the
  reason it could not be reached. **Test connection** checks the address in the
  box, so a new address can be tried before it is saved.

## Export and backups

- **Default export format** — what the Bank's **Export** offers first, and what
  auto-export writes: CSV, JSON, QTI 2.1, Moodle XML, plain text or Word.
- **Export folder** — where auto-export writes. It is created the first time
  it is needed.
- **Export the whole bank to that folder after each change** — a couple of
  seconds after the last change (an edit, a status move, a delete, an import,
  a commit from Generate, a course sync, a restored backup), the whole bank is
  written to the folder in the default format, replacing the previous copy:
  `exam-bank.csv`, `exam-bank.json`, `exam-bank-qti.xml`,
  `exam-bank-moodle.xml`, `exam-bank-text.txt` or `exam-bank.docx`. It is a
  copy for people and tools outside the app. The line under the switch names
  the file and says when it was last written, or why it could not be.
- **Back up the bank automatically**, **Every (hours)**, **Keep the newest** —
  see [Backups](02-backups-and-deletion.md).
