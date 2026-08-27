# Instructions

How to set up and run the Engineering Continuity Platform, including the
Capability Gap RAG that turns a simulated absence into a handover document.

If you only read one thing, read section 1.

---

## 0. What the system does

```
GitHub / Jira / incidents  ──▶  evidence records
                                      │
                                      ▼
                          scoring engine  ──▶  who knows what (capability_scores)
                                      │
                                      ▼
                          simulate an engineer's absence
                                      │
                                      ▼
                    capabilities that fall to LOW or NONE   ← the gaps
                                      │
                                      ▼
                    find the Confluence docs that cover them
                                      │
                                      ▼
                       Markdown / PDF / DOCX handover document
```

The first half already existed. The RAG is the second half, from "simulate"
downwards. It lives entirely in `backend/rag/` and does not modify anything
above it.

---

## 1. Check your machine

Run this first, always. It tells you exactly what is missing and how to fix it.

```bash
python doctor.py
```

To have it install packages and create missing tables for you:

```bash
python doctor.py --fix
```

It checks the Python version, every package, the database connection, the
schema, whether the scoring engine has been run, and whether Confluence is
configured. It changes nothing unless you pass `--fix`.

Exit code is `0` when nothing is blocking, `1` when something is.

---

## 2. First-time setup

### 2.1 Install dependencies

```bash
pip install -r requirements.txt
```

### 2.2 Create the database

Either PostgreSQL:

```sql
CREATE DATABASE engineering_continuity;
```

…or skip Postgres entirely and use SQLite, which needs no server:

```
DATABASE_URL=sqlite:///fallback.db
```

### 2.3 Configure

```bash
cp .env.example .env
```

Then edit `.env` and set your database password (or the `DATABASE_URL` above).

### 2.4 Create the tables

```bash
alembic upgrade head
```

> **On SQLite this fails** at the project's original migration, which uses
> PostgreSQL-only syntax. That is a pre-existing issue unrelated to the RAG.
> Use `python doctor.py --fix` instead — it creates the tables directly from
> the models.

### 2.5 Load data and compute scores

```bash
python -m backend.run_pipeline
```

```bash
python -m backend.run_engine
```

The RAG needs `capability_scores` to exist — without them every capability
looks uncovered.

### 2.6 Confirm

```bash
python doctor.py
```

---

## 3. Connect Confluence

### 3.1 Get an API token

Go to <https://id.atlassian.com/manage-profile/security/api-tokens> and create
one. It needs read access only.

### 3.2 Add it to `.env`

```
CONFLUENCE_BASE_URL=https://your-site.atlassian.net/wiki
CONFLUENCE_EMAIL=you@example.com
CONFLUENCE_API_TOKEN=your_token_here
CONFLUENCE_SPACE_KEYS=
```

`CONFLUENCE_BASE_URL` must include the `/wiki` suffix.

Leave `CONFLUENCE_SPACE_KEYS` blank to sync every space the token can read, or
list space keys comma-separated to narrow it.

### 3.3 Start with one small space

The client has been tested against a stand-in, not against a live Confluence.
Point it at a single space first so any surprise is small and obvious:

```bash
CONFLUENCE_SPACE_KEYS=YOURSPACE python -m backend.run_rag sync
```

Then check what came back:

```bash
python -m backend.run_rag status
```

If pages and sections are non-zero and the counts look about right, the client
works — remove `CONFLUENCE_SPACE_KEYS` and sync the rest.

### 3.4 Resolve anything the sync could not decide

The sync maps Confluence spaces to services by comparing their names and
descriptions. A generically-named space ("Platform") may be too close to call
between two services. Those are reported, never guessed:

```bash
python -m backend.run_rag status
```

```bash
python -m backend.run_rag map-space PLAT S003
```

`none` is a valid answer for a space that maps to no service at all:

```bash
python -m backend.run_rag map-space HR none
```

Your answer is saved as `manual` in `data/rag/confluence_mapping.json` and is
never overwritten by a later sync.

**An unresolved space is not a failure.** Its pages are still found by their
labels and by keyword search; only the space itself contributes no signal.

---

## 4. Daily use

### 4.1 Run the app

```bash
uvicorn backend.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Dashboard at <http://localhost:5173>, API at <http://localhost:8000>.

### 4.2 See who is a single point of failure

```bash
python -m backend.run_rag simulate E003
```

```
ID     CAPABILITY                 BEFORE    AFTER     SCORE
C003   Database Recovery          HIGH      NONE      0.0000    <-- GAP
C005   Deployment & Rollback      HIGH      LOW       0.2598    <-- GAP
```

Multiple people at once:

```bash
python -m backend.run_rag simulate E003 E004
```

### 4.3 See what will be searched for, before searching

```bash
python -m backend.run_rag context E003
```

Shows each gap with its coverage figures, its modules, its evidence counts, and
the exact search vocabulary — including which terms came from your engineers'
own commit messages and incident reports.

### 4.4 Generate the handover document

```bash
python -m backend.run_rag package E003 --formats md pdf docx
```

Files land in `data/rag/packages/`.

### 4.5 Keep Confluence current

```bash
python -m backend.run_rag sync
```

Safe to run on a schedule. Pages whose content has not changed are not
re-processed.

---

## 5. HTTP API

All under `/api/rag`. The existing `/api/graph/*` endpoints are unchanged.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/rag/confluence/status` | Configuration and index state |
| `GET` | `/api/rag/confluence/settings` | Effective Confluence config (token never returned) |
| `POST` | `/api/rag/confluence/settings` | Save Confluence settings from the Setup tab |
| `POST` | `/api/rag/confluence/sync` | Pull Confluence into the index |
| `POST` | `/api/rag/simulate` | Absence → per-capability coverage |
| `POST` | `/api/rag/gap-context` | Gaps + the context retrieval will use |
| `POST` | `/api/rag/retrieve` | Documentation for one capability |
| `POST` | `/api/rag/transfer-package` | Build the package, write it to disk |
| `GET` | `/api/rag/transfer-package/{slug}/download?format=pdf` | Download |
| `GET` | `/api/rag/packages` | List generated packages |
| `POST` | `/api/rag/mapping/space` | Resolve an ambiguous space mapping |

```bash
curl -X POST localhost:8000/api/rag/transfer-package -H 'Content-Type: application/json' -d '{"employee_ids":["E003"],"formats":["md","pdf"]}'
```

Interactive docs at <http://localhost:8000/docs>.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `password authentication failed for user "postgres"` | Wrong password, or Postgres not running | Fix `.env`, or use `DATABASE_URL=sqlite:///fallback.db` |
| `alembic upgrade head` fails on `CASCADE` | You are on SQLite; the original migration is Postgres-only | `python doctor.py --fix` |
| Sync returns HTTP 503 | Confluence credentials not set | Add them to `.env`, then `python doctor.py` |
| Sync returns HTTP 502 | Confluence rejected the request | Check the token is valid and the account can read those spaces |
| `retrieve` returns HTTP 409 | Nothing synced yet | `python -m backend.run_rag sync` |
| Package generated but no documents | No Confluence page matched | Expected and correct — see below |
| PDF or DOCX missing from output | `reportlab` / `python-docx` not installed | `pip install reportlab python-docx` |
| Every capability shows NONE | Scoring engine never ran | `python -m backend.run_engine` |
| Simulation finds no gaps | Your data has good redundancy | Try two people: `simulate E003 E004` |

### "No documentation matched this capability"

This is a real answer, not a bug. The system rejects weak matches rather than
attaching the least-bad page in the wiki, because a gap with **no person and no
document** is the highest-risk finding in the report. It is called out
explicitly in the executive summary.

If you believe documentation does exist, check how it is labelled:

```bash
python -m backend.run_rag retrieve C003
```

That prints the search terms and every candidate with its score.

---

## 7. When other parts of the project change

The RAG reads the taxonomy, the evidence tables, and parts of the scoring
engine. Ordinary work elsewhere is handled automatically:

| Change | Effect on the RAG |
|---|---|
| New capability added | Picked up automatically, including its search vocabulary |
| New module added | Its name becomes a working Confluence label immediately |
| Module or space renamed | Re-derived on the next sync |
| Band thresholds retuned in `scoring_config.py` | Followed automatically — they are imported, never restated |
| New evidence source added to ingestion | Its text feeds the vocabulary automatically |
| New column on a raw table | Starts contributing search terms with no code change |
| A private engine helper renamed | Falls back to a local implementation and logs a warning |
| Frontend changed | No effect — there is no coupling |

`tests/test_rag_resilience.py` asserts each of these.

After any such change, the honest check is:

```bash
python -m pytest tests/ -q
```

```bash
python doctor.py
```

---

## 8. Where things live

```
backend/rag/
├── config.py            settings and env vars
├── compat.py            engine imports, with fallbacks
├── models.py            the three Confluence tables
├── confluence/          API client, storage-format parser, sync
├── mapping/             page → capability derivation
├── coverage/            absence simulation, gap context
├── retrieval/           vocabulary, BM25, cutoffs, retrieval
├── packaging/           package assembly, Markdown, PDF/DOCX
└── api.py               the HTTP endpoints

doctor.py                environment check and setup
backend/run_rag.py       the CLI
docs/rag.md              how the RAG works internally
```

Generated packages go to `data/rag/packages/` (git-ignored). Space mapping
decisions go to `data/rag/confluence_mapping.json` (committed, because it
records human decisions).

---

## 9. Design guarantees

Two things this system will not do, by design:

**No language model writes any part of the output.** Coverage figures come from
the deterministic scoring engine; documentation text is copied verbatim from
Confluence with its source URL attached. The executive summary is a table of
computed facts, not prose. This follows `PROJECT_RULES.md` #10.

**Every result can explain itself.** A document appears in a package either
because a Confluence label maps to a module that declares the capability, or
because specific terms matched — and the package says which, per document.
This follows `PROJECT_RULES.md` #4.

For how retrieval decides relevance without hand-tuned thresholds, see
[docs/rag.md](docs/rag.md) section 7.
