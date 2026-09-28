# The Pentaho Docs Connection

docs.pentaho.com is published with GitBook, which serves an MCP (Model Context
Protocol) server for it at `https://docs.pentaho.com/~gitbook/mcp`. MCP is a
standard way for an AI application to call tools another service offers; this
one offers a search of the whole documentation site.

AI Chat calls that server's **searchDocumentation** tool once for each
question, and gives the model the pages it returns alongside this app's own
documentation. See [AI Chat](01-ai-chat.md).

## Checking it

**System → Settings → Pentaho documentation** shows the connection's state when
the screen opens:

- **Connected** — the server's name and version, the tools it offers, and how
  long it took to answer. *Search tool available* confirms the one AI Chat
  uses is among them.
- **Not connected** — the reason: the address could not be reached, the server
  answered with an error, or it did not answer in time.

**Test connection** checks the address in the box, so a different address can
be tried before it is saved.

## Turning it off

Untick **Search docs.pentaho.com from AI Chat** and press **Save**. AI Chat then
answers from this app's documentation only, and nothing is sent to the docs
site. Tick it again to turn it back on.

## Another address

The **MCP server** box holds the address. Another GitBook site's MCP endpoint
has the same shape, `https://<site>/~gitbook/mcp`; whether it offers the search
tool AI Chat needs shows in the status once it is tested.

## How it is called

- **From the app's backend, not its window.** The docs server does not allow
  web pages from other sites to call it, which is normal for a public server,
  so a call from the app's window would be refused. The backend is not a web
  page and is not subject to that rule.
- **One request per question**, over HTTPS, answered in well under a second
  from a normal connection. It gives up after 15 seconds, and the answer goes
  ahead from this app's documentation.
- **The five best results** are used, each cut to 700 characters, so a small
  local model still has room for the question.
- **Only the question's text is sent** (for a short follow-up, with the question
  before it). Nothing from the bank is sent.

## If it will not connect

- **Could not reach the server** — no internet connection, or a firewall
  blocking the address. The app uses Windows' proxy settings, or the
  `HTTPS_PROXY` environment variable when it is set.
- **HTTP 4xx or 5xx** — the address is wrong, or the server is having trouble.
  Opened in a browser, the right address answers *405 Method Not Allowed* (it
  only takes the app's POST requests), which at least proves it is there.
- **Connected, but no search tool** — the address is an MCP server that is not
  a GitBook docs site. AI Chat cannot search it.
