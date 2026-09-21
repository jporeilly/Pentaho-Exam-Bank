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
git clone https://github.com/jporeilly/Pentaho-Question-Bank.git
cd Pentaho-Question-Bank
install.bat
```

`install.bat` creates `venv\`, installs `requirements.txt`, and lays down the
`assets\` data directories. Then:

```bat
run.bat
```

That starts the NiceGUI app on <http://localhost:7777> and opens a browser.
`run.bat` kills any previous instance on that port first, and repairs the venv
if dependencies have gone missing.

Everything the app keeps lives under `assets\`, which is **gitignored**:

| Path | Holds |
| ---- | ----- |
| `assets\db\question_bank.db` | the question bank (SQLite) |
| `assets\db\backups\` | database backups, including one taken before every `--clean` |
| `assets\config\config.json` | settings — provider, model, the PCM courses path |
| `assets\questions\` | import staging and backups |

> The database is not in git. It is the one thing here that cannot be rebuilt
> from the repo, so back it up if it holds work you care about.

---

## 2. Developer — work on it

```bat
git clone https://github.com/jporeilly/Pentaho-Question-Bank.git
cd Pentaho-Question-Bank
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pytest -q
```

Run the app from source with `venv\Scripts\python.exe main.py`.

The repo root is the source root, so `question_bank` imports as a package from
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

**The browser shows a stale UI after an update.** NiceGUI's service worker
caches aggressively. Hard-reload (Ctrl+F5), or start on a different port.

**`run.bat` says dependencies are missing.** It repairs the venv itself. If it
cannot, delete `venv\` and re-run `install.bat`.

**A rename or delete fails with "device or resource busy".** On this machine
IObit Malware Fighter scans the tree after a test run and briefly holds
directories. It clears — retry rather than force it.

**Tests pass but the app cannot find its data.** Check `PROJECT_ROOT` resolves
to the repo root:

```bat
venv\Scripts\python.exe -c "from question_bank.utils.config import PROJECT_ROOT; print(PROJECT_ROOT)"
```
