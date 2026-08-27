# Capability Gap RAG — Confluence Knowledge Transfer

Extends the existing scoring and coverage engine with a Confluence-backed
retrieval layer. The engine decides **where the capability gaps are**; this
subsystem decides **what organizational knowledge addresses them** and emits a
handover document.

Everything lives under `backend/rag/`. The scoring engine, ingestion
extractors, and frontend simulation are untouched.

---

## 1. The pipeline

```
existing engine  ──▶  employee × capability scores        (capability_scores)
                            │
                            ▼
                   simulate employee absence
                            │
                            ▼
              recompute coverage → keep LOW + NONE        ← the gaps
                            │
                            ▼
                   retrieve documentation per gap
                    ├── tier 1: structural (exact)
                    └── tier 2: keyword (BM25)
                            │
                            ▼
                    assemble transfer package
                            │
                            ▼
                   Markdown ──▶ PDF / DOCX
```

No language model is involved at any stage. Coverage figures come from the
existing engine; documentation text is copied verbatim from Confluence with
its source URL attached.

---

## 2. Setup

Add to `.env`:

```
CONFLUENCE_BASE_URL=https://your-site.atlassian.net/wiki
CONFLUENCE_EMAIL=you@example.com
CONFLUENCE_API_TOKEN=...
CONFLUENCE_SPACE_KEYS=            # optional, comma-separated; blank = all readable
```

The token comes from <https://id.atlassian.com/manage-profile/security/api-tokens>.
It is sent as HTTP Basic auth and needs only read access.

Create the three new tables:

```bash
alembic upgrade head
```

Install dependencies (`reportlab` and `python-docx` are optional — Markdown
works without them):

```bash
pip install -r requirements.txt
```

---

## 3. Usage

### CLI

```bash
python -m backend.run_rag status
```

```bash
python -m backend.run_rag sync
```

```bash
python -m backend.run_rag simulate E003 E004
```

Inspect the gaps and exactly what will be searched for, before any retrieval:

```bash
python -m backend.run_rag context E003 E004
```

```bash
python -m backend.run_rag package E003 --formats md pdf docx
```

### HTTP

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/rag/confluence/status` | Configuration and index state |
| `GET` | `/api/rag/confluence/settings` | Effective Confluence config (token never returned) |
| `POST` | `/api/rag/confluence/settings` | Save Confluence settings from the Setup tab |
| `POST` | `/api/rag/confluence/sync` | Pull Confluence into the index |
| `POST` | `/api/rag/simulate` | Absence → per-capability coverage |
| `POST` | `/api/rag/gap-context` | Gaps + the context retrieval will use |
| `POST` | `/api/rag/retrieve` | Documentation for one capability |
| `POST` | `/api/rag/transfer-package` | Full package, written to disk |
| `GET` | `/api/rag/transfer-package/{slug}/download?format=pdf` | Download |
| `GET` | `/api/rag/packages` | List generated packages |
| `POST` | `/api/rag/mapping/space` | Resolve an ambiguous space mapping |

```bash
curl -X POST localhost:8000/api/rag/transfer-package -H 'Content-Type: application/json' -d '{"employee_ids":["E003"],"formats":["md","pdf"]}'
```

---

## 4. How pages are matched to capabilities

Nothing is hand-configured. Every mapping is derived from metadata the
Confluence API already returns, matched against the taxonomy the scoring
engine already uses.

| Signal | Source | Matched against | Confidence |
|---|---|---|---|
| **Label** | page labels | `jira_component` in `modules.json`, normalized module names, and the curated aliases in `backend/mapper.py` | 1.0 |
| **Ancestor** | parent page titles | same rules | 0.8 |
| **Space** | space name + description | service name + description, via the engine's own `_keyword_overlap` | 0.6 |
| **Keyword** | page text | capability vocabulary, via BM25 | scored |

Because `jira_component` values (`database-recovery`, `api-gateway`, …) are
already slug-shaped and Confluence labels are too, a wiki that labels its
pages by component maps itself with zero configuration.

**The space signal only fires for pages nothing else placed.** A space maps to
a whole service, so applying it to an already-labelled page would attach every
capability of that service — a rollback runbook filed in the Payments space
would come back as Payment Reconciliation documentation. When an author has
labelled a page, they have already said what it covers.

### When a space can't be resolved

A generically-named space (`PLAT` / "Platform") may overlap two services
equally. Rather than guessing, the sync records it as `ambiguous` and lists it
in `status` output. Resolve it once:

```bash
python -m backend.run_rag map-space PLAT S003
```

`none` is a valid answer, for a space that genuinely maps to no service:

```bash
python -m backend.run_rag map-space HR none
```

Decisions land in `data/rag/confluence_mapping.json` marked `manual` and are
never overwritten by a later sync. Everything else is re-derived each time, so
renaming a space or adding a module is picked up automatically.

**An unresolved space is not a failure.** Its pages still reach the package
through labels and keyword search; only the space itself contributes no
signal.

---

## 5. The capability vocabulary

A capability's name is a poor search query — no runbook says "Database
Recovery"; they say `PITR`, `WAL archive`, `pg_basebackup`. The words that
actually find the right page are the ones the engineers used, and those are
already in the database.

Four sources, blended and weighted:

| Source | Weight | Example for C003 |
|---|---|---|
| Capability name + description | 3.0 | `database`, `recovery`, `corruption` |
| `CAPABILITY_KEYWORD_OVERRIDES` | 2.5 | `pitr`, `wal`, `point-in-time` |
| Historical evidence text | 2.0 | `acmepay-db`, `failover`, `postgresql` |
| Linked module names + descriptions | 1.5 | `archiving`, `integrity` |

Evidence text is recovered by joining `evidence_records.source_ref` back to the
`raw_*` tables — commit messages, Jira summaries, incident root causes.

Each term's source weight is then scaled by how well it separates capabilities
(`log(N / df)` across the capability set), so generic words fade out on their
own rather than at a configured line — see section 7.

---

## 5b. Gap context — the seam between coverage and retrieval

`build_gap_contexts(db, employee_ids)` in
[backend/rag/coverage/context.py](../backend/rag/coverage/context.py) does
steps 1 and 2 of the pipeline in one call and stops there:

1. simulate the absence, keep the LOW/NONE capabilities
2. assemble everything retrieval would use for each one

It runs **no retrieval**, so it works before any Confluence sync. Each context
carries the capability, its coverage figures and remaining engineers, its
modules and their services, its evidence counts by source, and the full
weighted query — every term with its weight, its discriminating power, and
whether it came from historical evidence.

Use it to see what the system is about to search for, or to feed the gap set
into a different retriever entirely:

```bash
python -m backend.run_rag context E003
```

`context.query()` returns the term set in the exact shape `BM25Index.search`
expects, so a replacement retriever needs nothing else.

---

## 6. What lands in the package

For each gap capability:

- **Whole document** when the page is structurally tagged to the capability.
  The page *is* about the gap, so it ships intact.
- **Extracted sections** when the page matched only on keywords. Sections are
  split on the author's own headings, so an extract is always a coherent unit
  — a whole procedure, never the back half of one.

Every entry carries its match reason (`label:database-recovery -> M003`, or
`matched terms: wal, restore, backup`) and a link to the original page.

Gaps with no matching documentation are called out explicitly in the executive
summary — those carry the highest risk, since there is neither a person nor a
document to hand over.

---

## 7. Retrieval scoring — no tuned thresholds

Every relevance cutoff is computed per query, from the query and the result
set. There is no `RAG_KEYWORD_MIN_SCORE` to calibrate against your wiki.

Each hit carries two independent numbers:

| | Meaning | Answers |
|---|---|---|
| `score` | relative — 1.0 is the best section for this capability | *where does quality fall off?* |
| `mass` | absolute — share of the query's IDF weight actually matched | *is anything here good enough?* |

**The absolute bar runs first.** A section must be worth more than one typical
query term, measured as a share of the query's own total weight. This is what
lets a whole result set be rejected — a capability with no documentation
returns nothing, instead of the least-bad page in the wiki. Reporting *"no
documentation exists for this gap"* is one of the most valuable things the
package can say, and a purely relative rule can never say it: the best of a
worthless set still scores 1.0.

Measured on the test corpus — the three capabilities with no matching
documentation all returned zero, despite their top hits scoring 1.0 relative:

```
C003 Database Recovery      5 sections kept   (masses 0.089-0.043, floor 0.023)
C005 Deployment & Rollback  2 sections kept   (masses 0.058-0.054, floor 0.019)
C001 API Logic              0 kept            (best mass 0.011, floor 0.022)
C002 Payment Reconciliation 0 kept            (best mass 0.012, floor 0.021)
C004 Incident Response      0 kept            (best mass 0.003, floor 0.020)
```

**Then the relative cut**, through whatever cleared the bar: cut at the first
point where a score is at least twice the next one. Real relevant/irrelevant
distributions separate by a much larger step than the steps within either
group — measured scores ran 1.00, 0.72, 0.67, 0.63, 0.51, then 0.12, 0.12,
0.11, 0.10, where every internal step was under 1.2x and the boundary step was
4.5x. A smooth run with no real drop is kept whole, since the quality bar has
already ruled on it.

### Vocabulary weighting

Terms are weighted by their source and then scaled by how well they tell
capabilities apart — `log(N / df)` across the capability set. A word under
every capability scales to exactly zero and drops out on its own; a word under
one keeps full weight. This replaced a hard "delete terms in over 60% of
capabilities" rule, which was a crude reimplementation of IDF with a cliff
edge at an arbitrary place.

### What constants remain, and why

| Constant | Value | Why it is not a tuning knob |
|---|---|---|
| BM25 `k1`, `b` | 1.5, 0.75 | Published Okapi defaults. Describe term saturation and length normalization — corpus-independent by construction. |
| `CLEAR_LEAD_RATIO` | 2.0 | A *definition* of "clearly ahead", not a level. It is a ratio, so it means the same at any scale and on any corpus size. Shared by retrieval and space matching. |
| `MAX_DOCS_PER_GAP`, `MAX_SECTIONS_PER_DOC` | 5, 4 | Size caps on the finished document, applied after relevance is decided. Raising them makes the package longer, never less accurate. |
| Band thresholds | 0.75 / 0.45 / 0.20 | Yours, from `scoring_config.py`. A business decision about what "covered" means — no algorithm can derive it. |

### Properties under test

[tests/test_rag_cutoff.py](../tests/test_rag_cutoff.py) asserts the properties
that have to hold on any corpus, so a tuned constant cannot quietly return:

- scale invariance — multiplying every score by 1000 changes nothing
- size independence — a 500-item tail does not move the cut
- query-size independence — an 8-term and an 800-term query each get a bar proportionate to themselves
- rejectability — an entire result set can fail the bar

[tests/test_rag_retrieval.py](../tests/test_rag_retrieval.py) additionally
asserts that adding 30 irrelevant pages does not change what any capability
retrieves.

## 8. Schema

| Table | Holds |
|---|---|
| `confluence_pages` | page id, space, title, URL, **version**, labels, ancestors, flat text |
| `confluence_sections` | heading-delimited chunks; the retrieval and extraction unit |
| `confluence_page_capabilities` | why a page is relevant: capability, match type, evidence, confidence |

Re-sync is idempotent by `version`: a page whose Confluence version has not
changed is not re-parsed. Capability links are always re-resolved, since the
mapping can change without the page changing.

---

## 9. Design constraints

Two rules from `PROJECT_RULES.md` shaped this:

- **#4, evidence must be traceable.** A vector similarity of 0.83 is not
  traceable. "This page carries label `database-recovery`, which maps to module
  M003, which declares capability C003" is. Structural matching does the heavy
  lifting for exactly this reason.
- **#10, the LLM must never decide.** It writes nothing here either. The
  executive summary is a table of numbers the engine computed; the prose is the
  organization's own documentation, quoted with attribution.

A consequence worth knowing: the package cannot *explain* a gap in narrative
terms, only state it factually — *"C003 Database Recovery: 0.00 (NONE) after
Sneha leaves. Previously 1.00 (HIGH), sole contributor. 16 evidence records: 4
commits, 4 incidents, 4 issues, 2 deployments, 1 PR, 1 document."*

---

## 10. Degradation

| Situation | Behaviour |
|---|---|
| Confluence not configured | Sync returns 503 naming the missing settings; everything else works |
| No pages synced yet | Package still generates with full coverage analysis, and says plainly that no documentation was attached |
| `reportlab` / `python-docx` missing | That format is skipped with a `pip install` hint; Markdown always written |
| Page has no labels and its space is unresolved | Still findable by keyword search |
| One page fails to parse | Logged, sync continues, other pages unaffected |
