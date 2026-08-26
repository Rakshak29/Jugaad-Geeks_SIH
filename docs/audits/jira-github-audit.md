# Engineering Continuity Engine — Jira + GitHub Audit

## 1. Audit Scope
This document records the official read-only audit of the Jira Cloud project and GitHub monorepo used by the Engineering Continuity Engine.

* **Jira Write Operations:** **None.** No Jira write operations were performed during the audit.
* **GitHub Operations:** **None.** GitHub commit history and source code were not modified.
* **Audit Purpose:** Verify structure, historical timelines, data inventory, and cross-source correlation between Jira Cloud and GitHub evidence.

---

## 2. Jira Workspace / Project
* **Jira Base URL:** [`https://acmepay-engineering.atlassian.net`](https://acmepay-engineering.atlassian.net)
* **Workspace Name:** `acmepay-engineering`
* **Project Name:** `Acmepay engineering`
* **Project Key:** `SCRUM`
* **Project Type / Style:** `software` / `next-gen` (team-managed Software Project)
* **Project & Board URL:** `https://acmepay-engineering.atlassian.net/jira/software/projects/SCRUM/boards`
* **Issue Browse URL Format:** `https://acmepay-engineering.atlassian.net/browse/SCRUM-6`

---

## 3. Jira Data Inventory
* **Total Issues:** **140 issues**
* **Original Sample Issues:** **5 issues** (`SCRUM-1` through `SCRUM-5`)
* **Synthetic AcmePay Issues:** **135 issues** (`SCRUM-6` through `SCRUM-140`)
* **Epics:** **12** (`SCRUM-6` through `SCRUM-17`)
* **Stories:** **57**
* **Tasks:** **48**
* **Bug Representations:** **18** (Bug fixes tagged `[Bug]` linked to Epics)
* **Jira Components:** **12**
* **Threaded Comments:** **60** technical/code-review comments
* **Available Statuses:** **4** (`To Do`, `In Progress`, `In Review`, `Done`)

### Verified 12 Jira Components
1. `payment-service`
2. `fraud-service`
3. `auth-service`
4. `ledger-service`
5. `notification-service`
6. `user-service`
7. `reporting-service`
8. `settlement-service`
9. `api-gateway`
10. `deployment-service`
11. `monitoring-service`
12. `compliance-service`

---

## 4. Jira Issue Structure
* **Epic Hierarchy:** Epics (`SCRUM-6`..`17`) represent the 12 engineering modules. Stories, Tasks, and Bugs are child issues linked to their parent Epic via the `parent` field (`"parent": {"key": "SCRUM-X"}`).
* **Component Tagging:** Issues are tagged with Jira Components corresponding 1-to-1 with engineering module directories.
* **Payload Formatting:** Issue descriptions use Atlassian Document Format (ADF) storing engineering problem statements, author attributions, and telemetry timestamps.
* **Threaded Comments:** Comments contain code review feedback, QA triage notes, and postmortem references.

---

## 5. Jira Timeline
* **Jira API / System Creation Window:** `2026-08-26T14:35:00Z` to `2026-08-26T14:41:00Z` *(Wall-clock ingestion time assigned by Atlassian Cloud).*
* **Historical Jira Telemetry Date Range:** `2023-01-20T10:00:00Z` to `2026-08-19T14:20:00Z` *(True historical engineering period).*

*Note:* The 2026 API creation timestamps are ingestion/creation timestamps generated at payload transmission time and do NOT represent the engineering activity history.

### Historical Jira Issue Distribution by Year
* **2023:** 31 issues
* **2024:** 38 issues
* **2025:** 41 issues
* **2026:** 25 issues

---

## 6. GitHub Timeline
* **GitHub Commit Date Range:** `2023-01-18T17:22:00Z` to `2026-08-20T16:25:00Z`
* **Total Commits:** **338 commits** (337 synthetic commits + 1 final working-tree sync commit)

### Commit Distribution by Year
* **2023:** 101 commits
* **2024:** 81 commits
* **2025:** 92 commits
* **2026:** 64 commits

### Contributor & Module Scope
* **Contributors:** 19 active commit authors + 1 doc-only author (Pooja Bhatia) = 20 blueprint employees (`E01`–`E20`).
* **Modules:** All 12 monorepo services (`payment-service`, `fraud-service`, `auth-service`, `ledger-service`, etc.) are represented.

---

## 7. GitHub ↔️ Jira Correlation
The audit verified strong 1-to-1 correlation across all core data dimensions (**STRONG MATCH / 100%**):

* **Employee Identity:** `Rakshak Shetty` / `Rakshak29` / `rakshak@acmepay.io` in GitHub correlates with `rakshak.shetty` / `Rakshak Shetty` in Jira (`E01`).
* **Engineering Module / Component:** Git repository path `services/ledger/` correlates 1-to-1 with Jira component `ledger-service`.
* **Commits ↔️ Issues:** Commit `fix(payment): resolve state machine deadlock` correlates directly with Jira bug fix `[Bug] Fix state machine deadlock during card charge retry` (`SCRUM-75`).
* **Historical Overlap:** Both GitHub commit dates (`2023-01-18` to `2026-08-20`) and Jira historical telemetry (`2023-01-20` to `2026-08-19`) span the same 3.5-year engineering period.

---

## 8. Demonstration Cases

### 1. Knowledge Concentration
Rohan Gupta (`rohan.gupta` / `E10`) authored 35/61 commits in `services/ledger/` and is assigned 32/38 `ledger-service` issues in Jira (**84.2% concentration**). Both sources prove Rohan is the sole deep subject matter expert on double-entry ledger balance matching.

### 2. Stale Evidence
Vikram Malhotra (`vikram.malhotra` / `E08`) authored 25 auth commits in Git strictly in 2023 and has 18 Jira issues in `auth-service` strictly between Jan 2023 and Nov 2023. Zero activity in 2024–2026 in both sources. Recency decay correctly degrades Vikram's active credibility score to `LOW`/`NONE`.

### 3. Multi-Module Employees
`E01` (Rakshak Shetty), `E04` (Krish Trivedi), and `E06` (Parth More) show multi-module commits in Git and multi-component tickets in Jira spanning 3+ engineering domains.

### 4. Distributed Knowledge
`api-gateway` commits and Jira tickets are distributed evenly across 6 engineers (`E01`, `E02`, `E04`, `E06`, `E11`, `E15`), maintaining capability coverage if any single engineer is marked `UNAVAILABLE`.

### 5. Cross-Source Identity Resolution
Identity Resolver aggregates `Rakshak29` (GitHub), `rakshak.shetty` (Jira), `rakshak@acmepay.io` (Email), `r.shetty` (Deployments), and `Rakshak` (Incidents) to `E01`.

### 6. Ambiguous / Conflicting Evidence
Pooja Bhatia (`pooja.bhatia` / `E17`) is assigned 14 Documentation Stories in Jira but has **0 code commits** in GitHub, allowing the evidence engine to weight implementation commits over documentation authorship.

---

## 9. Evidence Gaps / Conflicts
* **Discrepancy Audit:** No structural or chronological discrepancies were identified in the synthetic Jira/GitHub dataset.
* **Sample Data Isolation:** Original issues `SCRUM-1` through `SCRUM-5` are isolated sample onboarding issues and are excluded from synthetic AcmePay engineering telemetry.

---

## 10. Engineering Continuity Readiness

| Analysis Feature | Status | Evidence Justification |
| :--- | :--- | :--- |
| **Knowledge Concentration** | **SUPPORTED** | Rohan Gupta `E10` 84.2% concentration on `ledger-service` |
| **Ownership Mapping** | **SUPPORTED** | 1-to-1 module path to component mapping |
| **Stale Evidence Handling** | **SUPPORTED** | Vikram Malhotra `E08` 2023-only activity |
| **Employee-to-Module Mapping** | **SUPPORTED** | All 20 employees mapped across 12 modules |
| **Distributed Knowledge** | **SUPPORTED** | API Gateway 6-engineer distribution |
| **Cross-Source Identity Resolution** | **SUPPORTED** | 5-way persona correlation for `E01` |
| **Ambiguous / Conflicting Evidence** | **SUPPORTED** | Pooja Bhatia `E17` docs vs code contrast |
| **Historical Continuity** | **SUPPORTED** | 3.5 years of aligned timeline telemetry (2023–2026) |
| **Bus-Factor / Dependency Risk** | **SUPPORTED** | Simulation engine accurately calculates status drop to `LOST` |
| **Module & Employee Coverage** | **SUPPORTED** | 100% coverage across all 12 modules and 20 employees |

---

## 11. Important Interpretation

"The Jira dataset is synthetic engineering evidence generated for the Engineering Continuity Engine. Its historical timestamps are embedded telemetry used to simulate a multi-year engineering history. The Jira API creation timestamps represent ingestion/creation time and must not be interpreted as the beginning of the engineering history."

"GitHub and Jira are intentionally correlated datasets for this project. The correlation is based on identities, modules/components, engineering work, and overlapping historical timelines."

---

## 12. Audit Status
* **Jira read-only audit:** **COMPLETE**
* **GitHub timeline audit:** **COMPLETE**
* **Jira ↔️ GitHub correlation audit:** **COMPLETE**
* **Write Operations:** **No Jira/GitHub write operations performed during this audit.**
* **Status:** **Ready for Step 4 only after this audit artifact is saved and verified.**
