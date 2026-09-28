# Install & Setup

Three ways to run the Exam Bank. Most people want the first. For what the app
does and why, see [`README.md`](README.md); for using it, see
[`HOW_TO_GUIDE.md`](HOW_TO_GUIDE.md).

- [1. Author — install it](#1-author--install-it)
- [2. Author — run it from a checkout](#2-author--run-it-from-a-checkout)
- [3. Developer — work on it](#3-developer--work-on-it)
- [What it connects to](#what-it-connects-to)
- [Troubleshooting](#troubleshooting)

---

## 1. Author — install it

Run `Pentaho Exam Bank_<version>_x64-setup.exe`. It installs **per machine**
into `C:\Program Files\Pentaho Exam Bank`, so Windows asks for elevation. It
carries its own Python; nothing else needs installing for the bank, import,
export, the report and publishing.

At install time it looks for the Pentaho Content Manager's `courses/` folder
and records it, so the app opens knowing where the courses are. Settings shows
the folder and can change it.

Open it from the desktop shortcut, or from the **Questions** button in the
Pentaho Content Editor, which opens it on the course you are editing.

Everything the installed app keeps is per user, in
`%APPDATA%\com.pentaho.exam-bank\`:

| Path | Holds |
| ---- | ----- |
| `db\exam_bank.db` | the exam bank (SQLite) |
| `db\backups\` | backups, from Admin → *Back up now*, and one taken before every restore |
| `config\config.json` | settings — your name, provider, model, the courses folder |

The installer never ships a database: an installed app starts with an empty
bank and adopts the courses' exams (Courses → *Check courses for questions*).

To check an installed copy, run `desktop\scripts\verify-install.ps1` from a
checkout: it confirms the launcher, the bundled Python and the interface are
present, starts the app, and reports the version it answers with.

---

## 2. Author — run it from a checkout

**Prerequisite:** Python 3.10 or newer on `PATH`, and [Node.js](https://nodejs.org)
for the first build of the interface.

```bat
git clone https://github.com/jporeilly/Pentaho-Exam-Bank.git
cd Pentaho-Exam-Bank
install.bat
run.bat
```

`install.bat` creates `venv\`, installs `requirements.txt`, and lays down the
`assets\` data directories. `run.bat` starts the app on port 7788 and opens it
in a browser; the first run builds the interface, which takes about a minute.
It releases the port from any previous run first, and repairs the venv if
dependencies have gone missing.

A checkout keeps its state in the repo's own `assets\` (gitignored) — the same
layout as the table above, under `assets\` instead of `%APPDATA%`. **It is a
different bank from the installed app's.** Set `PEB_STATE_DIR` to
`%APPDATA%\com.pentaho.exam-bank` to point a checkout at the installed bank.

### Just the API

```bat
run-api.bat
```

Use this for only the API — driving it from a REST client, or developing the
front end. `QB_API_PORT` overrides the port, and extra arguments pass through
(`run-api.bat --reload`). Or without the launcher:

```bat
venv\Scripts\python.exe -m exam_bank.api --port 9000
```

Interactive documentation is at `/docs` on whichever port it is using.

> The API has **no authentication**, so it binds loopback only. Anything that
> can reach it can read the bank, change it, and spend the machine's model
> time. `--host` refuses a non-loopback address unless you also pass
> `--allow-remote`.

---

## 3. Developer — work on it

```bat
git clone https://github.com/jporeilly/Pentaho-Exam-Bank.git
cd Pentaho-Exam-Bank
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pytest -q
cd frontend && npm install && npx vitest run
```

The repo root is the source root, so `exam_bank` imports as a package from
there — do not add an `__init__.py` at the repo root, which is what used to make
`C:\Projects` itself a source root.

**Building the installer:** `cd desktop && npm run dist` builds the interface,
fetches the vendored Python, stages the app, runs the Tauri build and collects
the installer. The release steps, version carriers included, are in
[`VERSION.md`](VERSION.md).

**Adopting from the command line:** `scripts\migrate_pcm_exams.py <slug>` brings
a course's `exam.json` into the bank, ids and order intact, the same as
Courses → *Adopt into the bank*. `--clean` empties the bank first, after a
timestamped backup.

---

## What it connects to

| Thing | Needed for | Without it |
| ----- | ---------- | ---------- |
| **Pentaho Content Manager** `courses/` folder | adopting, generating from and publishing to courses | no course sources or publishing; the bank, import and export still work |
| **An AI model** | Generate, AI rewrite, AI check, AI Chat | no AI; everything else still works |
| **docs.pentaho.com** over HTTPS | AI Chat's answers about Pentaho's products | AI Chat answers from this app's own docs; Settings turns the connection off |
| **git**, with credentials for the courses repo | *Publish and push* | publishing still writes the course; the push is not offered |

**AI.** Ollama is the default, expected at `http://localhost:11434`. Install it
from <https://ollama.com> and pull a model — `ollama pull llama3.2:3b` is a
reasonable CPU-sized start. A hosted provider needs its key in the environment
(`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`); the app never stores or shows a key.

**git.** The push uses git on `PATH`, else the MinGit the Content Manager or the
Content Editor ships, and the machine's own git credentials. The repo is
`courses_repo_url` in the settings file, Pentaho-Courses by default.

**docs.pentaho.com.** AI Chat searches Pentaho's product documentation through
the docs site's MCP server, `https://docs.pentaho.com/~gitbook/mcp`, from the
app's backend. It needs outbound HTTPS; a proxy set in Windows or in
`HTTPS_PROXY` is used. **Settings → Pentaho documentation** shows whether the
server answers, and turns the connection off. Details:
[`docs/ai/02-pentaho-docs-connection.md`](docs/ai/02-pentaho-docs-connection.md).

---

## Troubleshooting

**The status bar's Exam Bank version is red.** The interface and the backend
are different builds — close the app completely and reopen it; if it
persists, reinstall.

**An installed app and a checkout show different questions.** They are two
banks: `%APPDATA%\com.pentaho.exam-bank` and the checkout's `assets\`. See
[running from a checkout](#2-author--run-it-from-a-checkout).

**`run.bat` says dependencies are missing.** It repairs the venv itself. If it
cannot, delete `venv\` and re-run `install.bat`.

**A checkout shows a stale interface after an update.** Hard-reload (Ctrl+F5).

**A rename or delete fails with "device or resource busy".** On this machine
IObit Malware Fighter scans the tree after a test run and briefly holds
directories. It clears — retry rather than force it.

**Tests pass but a checkout cannot find its data.** Check `PROJECT_ROOT`
resolves to the repo root:

```bat
venv\Scripts\python.exe -c "from exam_bank.utils.config import PROJECT_ROOT; print(PROJECT_ROOT)"
```
