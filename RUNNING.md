# How to run this app (SQLite, no PostgreSQL needed)

Verified working on this machine on 2026-08-27. No code was changed to make
this work — only configuration and installing dependencies.

---

## TL;DR — it is running right now

| Service | URL |
|---|---|
| Dashboard | <http://localhost:5173> |
| API | <http://localhost:8000> |
| API docs | <http://localhost:8000/docs> |

Two terminals, one command each:

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

```bash
cd frontend && npm run dev
```

---

## First-time setup

### 1. Install Python packages

```bash
pip install -r requirements.txt
```

### 2. Use SQLite instead of PostgreSQL

The project defaults to PostgreSQL. To run without it, `.env` needs this line
(already added for you):

```
DATABASE_URL=sqlite:///fallback.db
```

That is the only change required. Comment it out later if you start using
PostgreSQL — the `POSTGRES_*` settings above it take over again.

### 3. Check everything

```bash
python doctor.py
```

Fix anything it flags. `python doctor.py --fix` installs missing packages and
creates missing tables.

### 4. Install frontend packages

```bash
cd frontend
npm install
```

---

## Building the database from scratch

Only needed if `fallback.db` is missing or you want to start clean. Skip it
otherwise — the database already has data.

```bash
python doctor.py --fix --yes
```

```bash
python -m backend.seed
```

```bash
python -m backend.run_pipeline
```

```bash
set PYTHONIOENCODING=utf-8
```

```bash
python -m backend.run_engine
```

> ### ⚠️ Why `PYTHONIOENCODING=utf-8` is needed
>
> `backend/run_engine.py` prints emoji (🧠 📥 ⚙️ 💾 🎉). Windows terminals
> default to the cp1252 codepage, which cannot encode them, so the script
> **crashes** with:
>
> ```
> UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f9e0'
> ```
>
> Setting the encoding first fixes it without touching the file. This is a
> pre-existing issue in that script, unrelated to the RAG.
>
> In PowerShell use `$env:PYTHONIOENCODING="utf-8"` instead of `set`.
> On Git Bash / macOS / Linux use `export PYTHONIOENCODING=utf-8`.

Expected result: 5 employees, 5 capabilities, 6 modules, 4 services,
106 evidence records, 18 capability scores.

---

## Running the app

**Terminal 1 — backend:**

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

Wait for `Application startup complete.`

**Terminal 2 — frontend:**

```bash
cd frontend && npm run dev
```

Then open <http://localhost:5173>.

The dashboard shows the five capabilities and who covers each. The
**Simulation** tab lets you mark an engineer unavailable and see the coverage
impact.

To stop either server: `Ctrl+C` in its terminal.

---

## Using the RAG

The backend must be running for the HTTP routes; the CLI works on its own.

### Pull your Confluence wiki

```bash
python -m backend.run_rag sync
```

### See who is a single point of failure

```bash
python -m backend.run_rag simulate E003 E004
```

```
ID     CAPABILITY                 BEFORE    AFTER     SCORE
C003   Database Recovery          HIGH      NONE      0.0000    <-- GAP
C005   Deployment & Rollback      HIGH      LOW       0.2598    <-- GAP
```

Employee IDs are `E001`–`E005` (Rahul, Amit, Sneha, Karan, Priya).

> One person alone rarely creates a gap in this dataset — the team has good
> redundancy. Try two: `simulate E003 E004`.

### Generate the handover document

```bash
python -m backend.run_rag package E003 E004 --formats md pdf docx
```

Files land in `data/rag/packages/`.

### Other commands

```bash
python -m backend.run_rag status
```

```bash
python -m backend.run_rag context E003 E004
```

```bash
python -m backend.run_rag retrieve C003
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `psycopg2.OperationalError ... port 5432 failed` | `DATABASE_URL=sqlite:///fallback.db` missing from `.env` |
| `UnicodeEncodeError: 'charmap' codec` | Set `PYTHONIOENCODING=utf-8` before `run_engine` |
| `ModuleNotFoundError` | `pip install -r requirements.txt` |
| Dashboard loads but is empty | Backend not running, or not on port 8000 — the frontend expects `http://localhost:8000` |
| `address already in use` | A server is already running on that port; use another with `--port 8001` |
| Sync returns 503 | Confluence credentials missing in `.env` |
| PDF/DOCX not produced | `pip install reportlab python-docx` |

When in doubt:

```bash
python doctor.py
```

---

## Current verified state

```
Database        sqlite:///fallback.db, 18 tables
Taxonomy        5 employees, 5 capabilities, 6 modules, 4 services
Evidence        106 records
Scores          18 capability scores
Confluence      connected, 14 pages / 41 sections indexed
Tests           185 passing
```

---

## Security note

Keep real credentials in `.env` only. **`.env` is gitignored; `.env.example`
is not** — anything pasted into `.env.example` gets committed and pushed to
GitHub. Check before every push:

```bash
git diff .env.example
```
