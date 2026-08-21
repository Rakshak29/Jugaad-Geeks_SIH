# Engineering Continuity MVP Rules

## Core idea

Engineering continuity is modeled as a capability-coverage problem,
not a person-replacement problem.

## Vocabulary

Coverage Team:
Selected set of remaining employees proposed to cover affected capabilities.

Minimum Coverage Team:
A Coverage Team with the fewest possible people.

Coverage Plan:
Team + residual gaps + supporting evidence + transfer actions.

Evidence Band:
HIGH / MODERATE / LOW / NONE.

Coverage Status:
MAINTAINED / DEGRADED / LOST.

Capability:
An independently actionable technical responsibility.

## Architecture

RAW ENGINEERING DATA
→ SOURCE EXTRACTION
→ NORMALIZED EVIDENCE
→ CAPABILITY MAPPING
→ PROVENANCE + RECENCY
→ COVERAGE ANALYSIS
→ OPTIMIZATION
→ HUMAN DECISION

## Rules

1. Never create an overall employee expertise score.
2. Never rank employees as people.
3. Never claim someone "doesn't know" something.
4. Evidence must be traceable to its source.
5. Technical dependency edges and evidence relationships are separate.
6. MVP coverage means at least one evidence-qualified engineer per capability.
7. This prototype models single-person coverage, not N-of-M redundancy.
8. Primary optimizer objective: minimize number of people.
9. Secondary optimizer objective: minimize context-switching penalty among equally-sized teams.
10. LLM must never decide who should be selected.
11. No numeric readiness percentage in the UI.
12. No automated reassignment.
13. Capability taxonomy is configurable per system.
14. Synthetic source data must not contain final capability scores.

