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
- **Where things are** — the Content Manager courses folder, the export folder,
  and the database and config file paths.
- **Quality** — how alike two questions must be before import calls them
  duplicates, and how closely an imported answer must match its source text
  to count as validated. Both run from 0 to 1; higher is stricter.
- **Defaults** — questions per page, and the default difficulty and Bloom level.

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
