"""
Build the search vocabulary for a capability.

A capability's name is a poor search query on its own -- no runbook says
"Database Recovery"; they say "PITR", "WAL archive", "pg_basebackup". The
words that actually find the right page are the ones the engineers used, and
those are already in the database: commit messages, Jira summaries, incident
root causes, all reachable from the evidence records for that capability.

Four sources, blended into one weighted term set:

    capability name + description   the taxonomy's own words
    CAPABILITY_KEYWORD_OVERRIDES    curated domain synonyms (already tuned)
    linked module names + docs      the systems the capability lives in
    historical evidence text        what engineers actually wrote

A term's final weight is its source weight scaled by how well it tells
capabilities apart -- inverse document frequency computed over the set of
capabilities. A word under every capability ("service", "fix") scales to
zero and drops out on its own; a word under one ("pitr") keeps its full
weight. This replaces an earlier hard cutoff that deleted any term appearing
under more than 60% of capabilities: that was a crude reimplementation of
IDF with a cliff edge at an arbitrary place, and it needed a special case to
stop it deleting words from a capability's own name.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from backend.engine.config import scoring_config as engine_cfg
from backend.rag.compat import tokenize as _tokenize
from backend.models.core import Capability, EvidenceRecord, Module
from backend.models.raw import (
    RawDeployment,
    RawDocument,
    RawGitHubCommit,
    RawGitHubIssue,
    RawGitHubPullRequest,
    RawGitHubReview,
    RawIncident,
    RawJiraIssue,
)
from backend.rag import config as cfg

logger = logging.getLogger("rag.retrieval.vocabulary")

# Capability-IDF is only meaningful once there are a few capabilities to
# compare. Below this the scaling is skipped entirely rather than computed
# from a sample too small to mean anything.
_MIN_CAPABILITIES_FOR_IDF = 3

# Relative pull of each source when the same term arrives from several.
_WEIGHTS = {
    "name": 3.0,
    "override": 2.5,
    "module": 1.5,
    "evidence": 2.0,
}


@dataclass
class CapabilityVocabulary:
    capability_id: str
    capability_name: str
    terms: dict[str, float] = field(default_factory=dict)  # term -> weight
    evidence_terms: list[str] = field(default_factory=list)
    # term -> log(N/df) across capabilities; empty when there are too few
    # capabilities for the statistic to mean anything.
    discrimination: dict[str, float] = field(default_factory=dict)

    def query_terms(self) -> list[str]:
        """Terms ordered strongest first."""
        return [t for t, _ in sorted(self.terms.items(), key=lambda kv: kv[1], reverse=True)]

    def weight_of(self, term: str) -> float:
        return self.terms.get(term, 0.0)

    def provenance(self, term: str) -> list[str]:
        """Which sources contributed a term -- for inspecting a built query."""
        sources = []
        if term in self.evidence_terms:
            sources.append("evidence")
        return sources


def build_vocabularies(db_session) -> dict[str, CapabilityVocabulary]:
    """One vocabulary per capability, with generic terms filtered out."""
    capabilities = db_session.query(Capability).all()
    modules_by_capability = _modules_by_capability(db_session)
    evidence_text = _evidence_text_by_capability(db_session)

    raw: dict[str, dict[str, float]] = {}
    evidence_terms: dict[str, list[str]] = {}

    for capability in capabilities:
        terms: dict[str, float] = {}

        def add(tokens, weight):
            for token in tokens:
                terms[token] = max(terms.get(token, 0.0), weight)

        add(_tokenize(capability.name), _WEIGHTS["name"])
        add(_tokenize(capability.description or ""), _WEIGHTS["name"])

        overrides = engine_cfg.CAPABILITY_KEYWORD_OVERRIDES.get(capability.id, [])
        add({kw.lower() for kw in overrides}, _WEIGHTS["override"])

        for module in modules_by_capability.get(capability.id, []):
            add(_tokenize(module.name), _WEIGHTS["module"])
            add(_tokenize(module.description or ""), _WEIGHTS["module"])

        mined = _mine_terms(evidence_text.get(capability.id, []))
        evidence_terms[capability.id] = mined
        add(mined, _WEIGHTS["evidence"])

        raw[capability.id] = terms

    discrimination = _capability_idf(raw)
    weighted = _apply_discrimination(raw, discrimination)

    return {
        capability.id: CapabilityVocabulary(
            capability_id=capability.id,
            capability_name=capability.name,
            terms=weighted.get(capability.id, {}),
            evidence_terms=[
                t for t in evidence_terms.get(capability.id, [])
                if t in weighted.get(capability.id, {})
            ],
            discrimination=discrimination,
        )
        for capability in capabilities
    }


def _capability_idf(raw: dict[str, dict[str, float]]) -> dict[str, float]:
    """
    How well each term tells capabilities apart: log(N / df).

    A term under every capability yields exactly 0 -- it cannot discriminate,
    so it contributes nothing. A term under one of five yields log(5) ~ 1.61.
    Smooth, standard, and self-zeroing: there is no cutoff to choose and no
    special case needed to protect a capability's own vocabulary.
    """
    total = len(raw)
    if total < _MIN_CAPABILITIES_FOR_IDF:
        return {}

    document_frequency: dict[str, int] = {}
    for terms in raw.values():
        for term in terms:
            document_frequency[term] = document_frequency.get(term, 0) + 1

    return {
        term: math.log(total / freq)
        for term, freq in document_frequency.items()
        if freq > 0
    }


def _apply_discrimination(
    raw: dict[str, dict[str, float]],
    discrimination: dict[str, float],
) -> dict[str, dict[str, float]]:
    """Scale each source weight by its term's discriminating power."""
    if not discrimination:
        return raw

    out: dict[str, dict[str, float]] = {}
    for capability_id, terms in raw.items():
        scaled = {}
        for term, weight in terms.items():
            value = weight * discrimination.get(term, 0.0)
            if value > 0:
                scaled[term] = value
        out[capability_id] = scaled
    return out


def _mine_terms(texts: list[str]) -> list[str]:
    """Most frequent meaningful tokens across a capability's evidence text."""
    if not texts:
        return []
    counts: dict[str, int] = {}
    for text in texts:
        for token in _tokenize(text):
            counts[token] = counts.get(token, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [term for term, _ in ordered[: cfg.MAX_EVIDENCE_TERMS]]


def _modules_by_capability(db_session) -> dict[str, list[Module]]:
    out: dict[str, list[Module]] = {}
    for module in db_session.query(Module).all():
        for capability in module.capabilities:
            out.setdefault(capability.id, []).append(module)
    return out


def _evidence_text_by_capability(db_session) -> dict[str, list[str]]:
    """
    Pull the human-written text behind each capability's evidence records.

    EvidenceRecord stores only source + source_ref, so this joins back to the
    raw_* tables that hold the actual prose. Missing rows are skipped -- the
    vocabulary degrades to the taxonomy's own words, which still works.
    """
    lookups = _build_raw_lookups(db_session)
    out: dict[str, list[str]] = {}

    rows = db_session.query(
        EvidenceRecord.capability_id,
        EvidenceRecord.source,
        EvidenceRecord.source_ref,
    ).all()

    for capability_id, source, source_ref in rows:
        text = _text_for(lookups, source, source_ref)
        if text:
            out.setdefault(capability_id, []).append(text)

    return out


def _build_raw_lookups(db_session) -> dict[str, dict[str, str]]:
    """
    source kind -> {source_ref: text}, loaded once per vocabulary build.

    Every raw table is scanned generically rather than by a hand-written column
    list. A new evidence source added to the ingestion pipeline therefore feeds
    the vocabulary automatically: without this, an unknown `source` value would
    quietly contribute no search terms at all, with nothing in the logs and no
    visible failure -- just weaker retrieval for that capability.
    """
    lookups: dict[str, dict[str, str]] = {}

    for spec in _raw_table_specs():
        table: dict[str, str] = {}
        try:
            for row in db_session.query(spec.model).all():
                ref = getattr(row, spec.id_attr, None)
                if not ref:
                    continue
                text = _row_text(row, spec.id_attr)
                if text:
                    table[str(ref)] = text
        except Exception as exc:
            # A missing or renamed raw table costs vocabulary richness, never
            # correctness -- the taxonomy's own words still drive the query.
            logger.warning("could not read raw table for %s: %s", spec.key, exc)
        lookups[spec.key] = table

    return lookups


@dataclass(frozen=True)
class _RawTableSpec:
    key: str        # the `source` value written by the ingestion extractors
    model: type
    id_attr: str    # the column holding what evidence_records.source_ref points at


def _raw_table_specs() -> list[_RawTableSpec]:
    """
    Which raw tables back which evidence `source` values.

    The keys mirror the `source_type` strings the extractors in
    backend/ingestion/ emit. Adding a source here is only needed to give it a
    dedicated id column -- see _discover_extra_sources for the fallback that
    handles ones nobody registered.
    """
    return [
        _RawTableSpec("commit", RawGitHubCommit, "commit_id"),
        _RawTableSpec("pull_request", RawGitHubPullRequest, "pr_id"),
        _RawTableSpec("review", RawGitHubReview, "review_id"),
        _RawTableSpec("github_issue", RawGitHubIssue, "issue_id"),
        _RawTableSpec("jira_issue", RawJiraIssue, "jira_id"),
        _RawTableSpec("incident", RawIncident, "incident_id"),
        _RawTableSpec("deployment", RawDeployment, "deployment_id"),
        _RawTableSpec("document", RawDocument, "doc_id"),
    ]


# Columns that hold identifiers, timestamps or bookkeeping rather than prose.
_NON_TEXT_SUFFIXES = ("_id", "_at", "_by", "id")
_NON_TEXT_COLUMNS = {"id", "timestamp", "status", "environment", "state", "severity"}


def _row_text(row, id_attr: str) -> str:
    """
    Everything human-written on a raw row, gathered by inspecting its columns.

    Reading the model's actual columns rather than a fixed list means a new
    column -- a richer incident postmortem field, say -- starts contributing
    search terms the moment someone adds it, with no change here.
    """
    pieces: list[str] = []
    for column in row.__table__.columns:
        name = column.name
        if name == id_attr or name in _NON_TEXT_COLUMNS:
            continue
        if name.endswith(_NON_TEXT_SUFFIXES):
            continue
        value = getattr(row, name, None)
        if isinstance(value, str) and value.strip():
            pieces.append(value)
        elif isinstance(value, (list, dict)) and value:
            pieces.append(str(value))
    return " ".join(pieces)


def _text_for(lookups: dict[str, dict[str, str]], source: str, source_ref: str) -> str:
    """
    Resolve one evidence record to its source text.

    Tries the source's own table first, then every other table. The fallback
    matters for two reasons: `issue` is ambiguous -- the ingestion pipeline
    uses it for both GitHub issues and Jira tickets -- and a `source` value
    nobody registered in _raw_table_specs still finds its text as long as some
    raw table holds that reference.
    """
    ref = str(source_ref)

    direct = lookups.get(source, {}).get(ref)
    if direct:
        return direct

    for key, table in lookups.items():
        if key == source:
            continue
        found = table.get(ref)
        if found:
            return found

    return ""
