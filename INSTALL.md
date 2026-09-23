# Install & Setup

Two paths today. There is **no Windows installer yet** — that arrives in 1.0.0
with the restack ([`PLAN.md`](PLAN.md)), so for now the app runs from a checkout
on the author's machine. For what the app does and why, see
[`README.md`](README.md).

- [1. Author — run the app](#1-author--run-the-app)
- [2. Developer — work on it](#2-developer--work-on-it)
- [What it connects to](#what-it-connects-to)
- [Troubleshooting](#troubleshooting)

---

## 1. Author — run the app

**Prerequisite:** Python 3.10 or newer on `PATH`.

```bat
git clone https://github.com/jporeilly/Pentaho-Exam-Bank.git
cd Pentaho-Exam-Bank
install.bat
```

`install.bat` creates `venv\`, installs `requirements.txt`, and lays down the
`assets\` data directories. Then:

```bat
run.bat
```

That starts one thing:

| | Port | What |
| --- | ---- | ---- |
| **Exam Bank** | 7788 | The app, which opens in a browser |

One server. The API serves the React interface from `frontend/dist` at its own
root, so the interface and the API are the same process on the same port. The
NiceGUI layer that used to run alongside it on 7777 has been removed.

The first run builds the interface if it has never been built — that needs
[Node.js](https://nodejs.org) and takes about a minute. After that it starts
immediately.

`run.bat` releases the port from any previous run first, and repairs the venv
if dependencies have gone missing.

### Just the API

```bat
run-api.bat
```

Use this when you want only the API — driving it from a REST client, or
developing the front end. `QB_API_PORT` overrides the port, and any extra
arguments are passed through:

```bat
run-api.bat --reload
```

Or without the launcher:

```bat
venv\Scripts\python.exe -m exam_bank.api --port 9000
```

Interactive documentation is at `/docs` on whichever port it is using.

> The API has **no authentication**, so it binds loopback only. Anything that
> can reach it can read the bank, change it, and spend the machine's model
> time. `--host` refuses a non-loopback address unless you also pass
> `--allow-remote`.

Everything the app keeps lives under `assets\`, which is **gitignored**:

| Path | Holds |
| ---- | ----- |
| `assets\db\exam_bank.db` | the exam bank (SQLite) |
| `assets\db\backups\` | database backups, including one taken before every `--clean` |
| `assets\config\config.json` | settings — provider, model, the PCM courses path |
| `assets\questions\` | import staging and backups |

> The database is not in git. It is the one thing here that cannot be rebuilt
> from the repo, so back it up if it holds work you care about.

---

## 2. Developer — work on it

```bat
git clone https://github.com/jporeilly/Pentaho-Exam-Bank.git
cd Pentaho-Exam-Bank
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pytest -q
```

Run the app from source with `venv\Scripts\python.exe main.py`.

The repo root is the source root, so `exam_bank` imports as a package from
there — do not add an `__init__.py` at the repo root, which is what used to make
`C:\Projects` itself a source root.

### Adopting a course's questions

Brings a PCM course's `exam.json` into the bank, ids and order intact:

```bat
venv\Scripts\python.exe scripts\migrate_pcm_exams.py pdi-2hr-lab
```

Add `--clean` to empty the bank first — it takes a timestamped database backup
into `assets\db\backups\` before deleting anything. Pass several slugs to adopt
several courses in one run.

---

## What it connects to

| Thing | Needed for | Without it |
| ----- | ---------- | ---------- |
| **Pentaho Content Manager** checkout | generating from, and adopting, course content | Course sources are unavailable; PPTX and docs sources still work |
| **Ollama** (local, free) | AI generation and refinement | Generation is unavailable; the bank, import and export all still work |
| **Pentaho docs MCP** | grounding questions in the published docs | Docs-sourced generation is unavailable |

The Content Manager is found as a **sibling directory** —
`..\Pentaho-Content-Manager\courses` — or at the path set in
`assets\config\config.json`. Nothing caches a resolved course slug: a stored
slug that quietly stopped resolving is how the bank's original certifications
died when the courses were renamed under them.

Ollama is expected at `http://localhost:11434`. Install it from
<https://ollama.com>, then pull a model — `ollama pull llama3.2:3b` is a
reasonable CPU-sized starting point.

---

## Troubleshooting

**The browser shows a stale UI after an update.** The front end's service worker
caches aggressively. Hard-reload (Ctrl+F5), or start on a different port.

**`run.bat` says dependencies are missing.** It repairs the venv itself. If it
cannot, delete `venv\` and re-run `install.bat`.

**A rename or delete fails with "device or resource busy".** On this machine
IObit Malware Fighter scans the tree after a test run and briefly holds
directories. It clears — retry rather than force it.

**Tests pass but the app cannot find its data.** Check `PROJECT_ROOT` resolves
to the repo root:

```bat
venv\Scripts\python.exe -c "from exam_bank.utils.config import PROJECT_ROOT; print(PROJECT_ROOT)"
```
